"""Histórico dos piquetes: qual pasto cada um teve, divisão de piquete e o histórico de
ocupações com a "foto" de cada uma (cabeças, peso, área naquela data).

Regra de ouro: o passado não muda. Dividir um piquete encerra o original com a área que
ele tinha; trocar o pasto encerra o período anterior. É isso que permite comparar, mais
tarde, o desempenho do Tifton com o da braquiária, ou a lotação de cada período.
"""
from __future__ import annotations

import json
from datetime import date, timedelta

from sqlalchemy.orm import Session, selectinload

from ..models import LotePiquete, MovimentacaoPasto, Piquete
from ..models_campo import PastoPeriodo
from . import geo
from .pastos import (
    KG_POR_UA,
    ErroPasto,
    _abrir_ocupacao,
    _fechar_ocupacao,
    _foto_lote,
    _hoje,
    _novo_alt,
    _validar_data,
)


# ---------------------------------------------------------------- Pasto (forrageira)

def _periodo_dict(per: PastoPeriodo) -> dict:
    return {"id": per.id, "especie": per.especie, "inicio": per.inicio.isoformat(),
            "fim": per.fim.isoformat() if per.fim else None, "observacao": per.observacao}


def _sincronizar_capim(db: Session, piquete_id: int) -> None:
    """Piquete.capim = pasto atual (texto), pra telas antigas e exportações."""
    p = db.get(Piquete, piquete_id)
    atuais = (db.query(PastoPeriodo)
              .filter(PastoPeriodo.piquete_id == piquete_id, PastoPeriodo.fim.is_(None))
              .order_by(PastoPeriodo.inicio).all())
    p.capim = " + ".join(x.especie for x in atuais)[:60] or None


def periodos(db: Session, piquete_id: int) -> list[dict]:
    lista = (db.query(PastoPeriodo).filter(PastoPeriodo.piquete_id == piquete_id)
             .order_by(PastoPeriodo.inicio.desc(), PastoPeriodo.id.desc()).all())
    return [_periodo_dict(x) for x in lista]


def adicionar_pasto(db: Session, piquete_id: int, especie: str, inicio: date | None = None,
                    substitui: bool = True, observacao: str | None = None,
                    commit: bool = True) -> dict:
    """Registra o pasto do piquete a partir de uma data.

    substitui=True: troca/reforma — encerra o(s) pasto(s) atual(is) na véspera.
    substitui=False: sobressemeadura — o novo convive com o atual (ex.: azevém no Tifton).
    """
    p = db.get(Piquete, piquete_id)
    if p is None:
        raise ErroPasto("Piquete não encontrado.")
    especie = (especie or "").strip()
    if not especie:
        raise ErroPasto("Escolha o pasto (ex.: Tifton 85, Marandu, Azevém).")
    inicio = inicio or _hoje()
    if inicio > _hoje() + timedelta(days=1):
        raise ErroPasto("A data não pode ser no futuro.")
    if substitui:
        for atual in db.query(PastoPeriodo).filter(
            PastoPeriodo.piquete_id == piquete_id, PastoPeriodo.fim.is_(None)
        ):
            if inicio <= atual.inicio:
                raise ErroPasto(
                    f"O pasto atual ({atual.especie}) começou em "
                    f"{atual.inicio.strftime('%d/%m/%Y')}: a troca precisa ser depois disso."
                )
            atual.fim = inicio - timedelta(days=1)
    per = PastoPeriodo(piquete_id=piquete_id, especie=especie[:60], inicio=inicio,
                       observacao=(observacao or "").strip() or None)
    db.add(per)
    db.flush()
    _sincronizar_capim(db, piquete_id)
    if commit:
        db.commit()
    return _periodo_dict(per)


def encerrar_pasto(db: Session, periodo_id: int, fim: date | None = None) -> dict:
    """Fecha um pasto (ex.: fim do azevém na primavera)."""
    per = db.get(PastoPeriodo, periodo_id)
    if per is None:
        raise ErroPasto("Período de pasto não encontrado.")
    fim = fim or _hoje()
    if fim < per.inicio:
        raise ErroPasto("O fim não pode ser antes do início.")
    per.fim = fim
    _sincronizar_capim(db, per.piquete_id)
    db.commit()
    return _periodo_dict(per)


def apagar_pasto(db: Session, periodo_id: int) -> dict:
    """Apaga um período lançado errado (o anterior, se tinha sido encerrado por ele, reabre)."""
    per = db.get(PastoPeriodo, periodo_id)
    if per is None:
        raise ErroPasto("Período de pasto não encontrado.")
    anterior = db.query(PastoPeriodo).filter(
        PastoPeriodo.piquete_id == per.piquete_id,
        PastoPeriodo.fim == per.inicio - timedelta(days=1),
    ).first()
    if anterior is not None and per.fim is None:
        anterior.fim = None
    piquete_id = per.piquete_id
    db.delete(per)
    db.flush()
    _sincronizar_capim(db, piquete_id)
    db.commit()
    return {"ok": True}


def migrar_capim_para_periodos(db: Session) -> int:
    """Piquetes antigos com 'capim' em texto e sem histórico ganham um período aberto
    desde o cadastro (idempotente; roda no start)."""
    com_periodo = {pid for (pid,) in db.query(PastoPeriodo.piquete_id).distinct()}
    n = 0
    for p in db.query(Piquete).filter(Piquete.capim.is_not(None)).all():
        if p.id in com_periodo or not (p.capim or "").strip():
            continue
        inicio = p.criado_em.date() if p.criado_em else _hoje()
        db.add(PastoPeriodo(piquete_id=p.id, especie=p.capim.strip()[:60], inicio=inicio,
                            observacao="cadastro inicial"))
        n += 1
    if n:
        db.commit()
    return n


# ---------------------------------------------------------------- Dividir piquete

def dividir(db: Session, piquete_id: int, partes: list[dict], quando: date | None = None,
            destinos: dict | None = None, usuario: str | None = None) -> dict:
    """Divide um piquete em dois ou mais.

    O original é ENCERRADO na data (fica com a área e o histórico que tinha, renomeado
    "Nome (até dd/mm/aaaa)"); cada parte vira um piquete novo, com o mesmo pasto e o mesmo
    descanso desejado. O gado que estava dentro vai pra parte escolhida em `destinos`
    ({lote_id: índice da parte}).
    """
    quando = _validar_data(quando)
    original = db.get(Piquete, piquete_id)
    if original is None or not original.ativo:
        raise ErroPasto("Piquete não encontrado.")
    if len(partes) < 2:
        raise ErroPasto("Desenhe pelo menos duas partes.")

    nomes = [(x.get("nome") or "").strip()[:80] for x in partes]
    if any(not n for n in nomes):
        raise ErroPasto("Dê um nome para cada parte.")
    if len(set(n.lower() for n in nomes)) != len(nomes):
        raise ErroPasto("As partes precisam ter nomes diferentes.")
    for n in nomes:
        q = db.query(Piquete).filter(Piquete.nome == n, Piquete.ativo.is_(True), Piquete.id != original.id)
        q = q.filter(Piquete.area_id.is_(None) if original.area_id is None
                     else Piquete.area_id == original.area_id)
        if q.first():
            raise ErroPasto(f"Já existe o piquete '{n}' nessa área.")
    geometrias = [geo.validar_geometria(x.get("geometria")) for x in partes]

    abertas = db.query(LotePiquete).filter(
        LotePiquete.piquete_id == original.id, LotePiquete.data_saida.is_(None)
    ).all()
    destinos = {int(k): int(v) for k, v in (destinos or {}).items()}
    for o in abertas:
        if o.data_entrada > quando:
            raise ErroPasto("A data da divisão é anterior à entrada do gado que está no piquete.")
        if _foto_lote(db, o.lote_id, quando)["cabecas"] and o.lote_id not in destinos:
            raise ErroPasto("Escolha em qual parte fica cada lote que está no piquete.")
        if o.lote_id in destinos and not 0 <= destinos[o.lote_id] < len(partes):
            raise ErroPasto("Parte de destino inválida.")

    # 1) Encerra o original (libera o nome pras partes).
    nome_original = original.nome
    original.ativo = False
    original.encerrado_em = quando
    original.nome = f"{nome_original} (até {quando.strftime('%d/%m/%Y')})"[:80]
    db.flush()

    # 2) Cria as partes, herdando pasto e descanso desejado.
    pastos_atuais = db.query(PastoPeriodo).filter(
        PastoPeriodo.piquete_id == original.id, PastoPeriodo.fim.is_(None)
    ).all()
    novos = []
    for nome, g, parte in zip(nomes, geometrias, partes):
        ha = round(float(parte["hectares"]), 2) if parte.get("hectares") else geo.hectares(g)
        n = Piquete(nome=nome, area_id=original.area_id, geometria=json.dumps(g), hectares=ha,
                    descanso_meta_dias=original.descanso_meta_dias, capim=original.capim,
                    observacao=original.observacao, ativo=True, origem_id=original.id)
        db.add(n)
        db.flush()
        for per in pastos_atuais:
            db.add(PastoPeriodo(piquete_id=n.id, especie=per.especie, inicio=quando,
                                observacao=f"herdado de {nome_original}"))
        novos.append(n)
    for per in pastos_atuais:
        per.fim = quando

    # 3) O gado que estava dentro sai do original e entra na parte escolhida.
    alt = _novo_alt()
    for o in abertas:
        _fechar_ocupacao(db, o.lote_id, quando, alt)
        if o.lote_id in destinos:
            _abrir_ocupacao(db, o.lote_id, novos[destinos[o.lote_id]].id, quando, 0, alt)

    resumo = f"{nome_original} dividido em " + ", ".join(
        f"{n.nome} ({n.hectares:.2f} ha)".replace(".", ",") for n in novos)
    db.add(MovimentacaoPasto(tipo="dividir", data=quando, resumo=resumo,
                             alteracoes=json.dumps(alt), usuario_nome=usuario))
    db.commit()
    return {"ok": True, "novos": [{"id": n.id, "nome": n.nome, "hectares": n.hectares} for n in novos],
            "resumo": resumo}


# ---------------------------------------------------------------- Histórico do piquete

def historico(db: Session, piquete_id: int, hoje: date | None = None) -> dict:
    """Ocupações (com densidade de cada período), pastos e de onde o piquete veio."""
    hoje = hoje or _hoje()
    p = db.get(Piquete, piquete_id)
    if p is None:
        raise ErroPasto("Piquete não encontrado.")
    ocupacoes = (db.query(LotePiquete).filter(LotePiquete.piquete_id == piquete_id)
                 .options(selectinload(LotePiquete.lote))
                 .order_by(LotePiquete.data_entrada.desc(), LotePiquete.id.desc()).all())
    pers = (db.query(PastoPeriodo).filter(PastoPeriodo.piquete_id == piquete_id)
            .order_by(PastoPeriodo.inicio).all())

    def pasto_em(d: date) -> str | None:
        nomes = [x.especie for x in pers if x.inicio <= d and (x.fim is None or x.fim >= d)]
        return " + ".join(nomes) or None

    lista = []
    for o in ocupacoes:
        fim = o.data_saida or hoje
        ha = o.hectares or p.hectares
        ua_ent = o.peso_entrada / KG_POR_UA if o.peso_entrada else None
        ua_sai = o.peso_saida / KG_POR_UA if o.peso_saida else None
        ganho = None
        if o.peso_entrada and o.peso_saida and o.cabecas and o.cabecas_saida == o.cabecas:
            dias = (fim - o.data_entrada).days
            ganho = round((o.peso_saida - o.peso_entrada) / o.cabecas / dias, 3) if dias > 0 else None
        lista.append({
            "lote": o.lote.nome if o.lote else None,
            "entrada": o.data_entrada.isoformat(),
            "saida": o.data_saida.isoformat() if o.data_saida else None,
            "dias": (fim - o.data_entrada).days,
            "cabecas": o.cabecas,
            "cabecas_saida": o.cabecas_saida,
            "hectares": ha,
            "ua_entrada": round(ua_ent, 1) if ua_ent else None,
            "ua_saida": round(ua_sai, 1) if ua_sai else None,
            "ua_ha_entrada": round(ua_ent / ha, 2) if ua_ent and ha else None,
            "entrada_estimada": o.entrada_estimada,
            "saida_estimada": o.saida_estimada,
            "gmd_periodo": ganho,
            "pasto": pasto_em(o.data_entrada),
        })
    origem = db.get(Piquete, p.origem_id) if p.origem_id else None
    partes = db.query(Piquete).filter(Piquete.origem_id == p.id).all()
    destino = db.get(Piquete, p.destino_id) if p.destino_id else None
    unidos = db.query(Piquete).filter(Piquete.destino_id == p.id).all()
    return {
        "piquete": {"id": p.id, "nome": p.nome, "hectares": p.hectares, "ativo": p.ativo,
                    "encerrado_em": p.encerrado_em.isoformat() if p.encerrado_em else None},
        "origem": {"id": origem.id, "nome": origem.nome} if origem else None,
        "partes": [{"id": x.id, "nome": x.nome} for x in partes],
        "unido_em": {"id": destino.id, "nome": destino.nome} if destino else None,
        "uniao_de": [{"id": x.id, "nome": x.nome} for x in unidos],
        "ocupacoes": lista,
        "pastos": [_periodo_dict(x) for x in reversed(pers)],
    }


# ---------------------------------------------------------------- Unir piquetes

def unir(db: Session, piquete_ids: list[int], nome: str, quando: date | None = None,
         pasto: str | None = None, usuario: str | None = None) -> dict:
    """Une dois ou mais piquetes num só (tirou a cerca entre eles).

    Os originais são ENCERRADOS na data com a área e o histórico que tinham (renomeados
    "Nome (até dd/mm/aaaa)") e apontam pro novo; o novo tem a soma das áreas e os
    contornos juntos. O gado que estava em qualquer um deles passa pro novo.
    Pasto: se todos tinham o mesmo, o novo herda; senão vale o informado em `pasto`.
    """
    quando = _validar_data(quando)
    ids = list(dict.fromkeys(int(x) for x in piquete_ids))
    if len(ids) < 2:
        raise ErroPasto("Escolha pelo menos dois piquetes para unir.")
    originais = [db.get(Piquete, i) for i in ids]
    if any(p is None or not p.ativo for p in originais):
        raise ErroPasto("Piquete não encontrado.")
    nome = (nome or "").strip()[:80]
    if not nome:
        raise ErroPasto("Dê um nome para o piquete unido.")
    area_id = originais[0].area_id
    q = db.query(Piquete).filter(Piquete.nome == nome, Piquete.ativo.is_(True), Piquete.id.notin_(ids))
    q = q.filter(Piquete.area_id.is_(None) if area_id is None else Piquete.area_id == area_id)
    if q.first():
        raise ErroPasto(f"Já existe o piquete '{nome}' nesse grupo.")

    abertas = db.query(LotePiquete).filter(LotePiquete.piquete_id.in_(ids),
                                           LotePiquete.data_saida.is_(None)).all()
    if any(o.data_entrada > quando for o in abertas):
        raise ErroPasto("A data da união é anterior à entrada do gado que está num dos piquetes.")

    # Contornos juntos (MultiPolygon) e soma das áreas.
    poligonos = []
    for p in originais:
        if p.geometria:
            g = json.loads(p.geometria)
            poligonos.extend([g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"])
    geometria = {"type": "MultiPolygon", "coordinates": poligonos} if poligonos else None
    hectares = round(sum(p.hectares or 0 for p in originais), 2) or None

    especies = {tuple(sorted(x.especie for x in db.query(PastoPeriodo).filter(
        PastoPeriodo.piquete_id == p.id, PastoPeriodo.fim.is_(None)))) for p in originais}
    if pasto is None and len(especies) == 1:
        herdadas = list(next(iter(especies)))
    else:
        herdadas = [pasto] if pasto else []

    nomes_originais = [p.nome for p in originais]
    for p in originais:
        p.ativo = False
        p.encerrado_em = quando
        p.nome = f"{p.nome} (até {quando.strftime('%d/%m/%Y')})"[:80]
        for per in db.query(PastoPeriodo).filter(PastoPeriodo.piquete_id == p.id, PastoPeriodo.fim.is_(None)):
            per.fim = quando
    db.flush()
    novo = Piquete(
        nome=nome, area_id=area_id, geometria=json.dumps(geometria) if geometria else None,
        hectares=hectares, ativo=True, uso=originais[0].uso,
        descanso_meta_dias=max((p.descanso_meta_dias or 0) for p in originais) or None,
        ocupacao_max_dias=min((p.ocupacao_max_dias for p in originais if p.ocupacao_max_dias), default=None),
        observacao="União de " + ", ".join(nomes_originais),
    )
    db.add(novo)
    db.flush()
    for p in originais:
        p.destino_id = novo.id
    for especie in herdadas:
        db.add(PastoPeriodo(piquete_id=novo.id, especie=especie, inicio=quando,
                            observacao="união de piquetes"))
    db.flush()
    _sincronizar_capim(db, novo.id)

    alt = _novo_alt()
    for lote_id in dict.fromkeys(o.lote_id for o in abertas):
        tinha_gado = _foto_lote(db, lote_id, quando)["cabecas"]
        _fechar_ocupacao(db, lote_id, quando, alt)
        if tinha_gado:
            _abrir_ocupacao(db, lote_id, novo.id, quando, 0, alt)

    resumo = f"{', '.join(nomes_originais)} unidos em {nome}" + (
        f" ({hectares:.2f} ha)".replace(".", ",") if hectares else "")
    db.add(MovimentacaoPasto(tipo="unir", data=quando, resumo=resumo,
                             alteracoes=json.dumps(alt), usuario_nome=usuario))
    db.commit()
    return {"ok": True, "novo": {"id": novo.id, "nome": novo.nome, "hectares": novo.hectares},
            "resumo": resumo, "pasto_herdado": herdadas}


# ---------------------------------------------------------------- Editar em massa

def editar_em_massa(db: Session, piquete_ids: list[int], dados: dict) -> dict:
    """Aplica os mesmos campos a vários piquetes de uma vez (grupo, uso, descanso,
    máximo de dias, pastagem). Só muda o que veio preenchido."""
    from .pastos import _area_por_nome, _validar_uso
    ids = list(dict.fromkeys(int(x) for x in piquete_ids))
    if not ids:
        raise ErroPasto("Selecione pelo menos um piquete.")
    piquetes = [db.get(Piquete, i) for i in ids]
    if any(p is None or not p.ativo for p in piquetes):
        raise ErroPasto("Piquete não encontrado.")
    area_id = None
    if dados.get("area_nome"):
        area_id = _area_por_nome(db, dados["area_nome"]).id
    uso = _validar_uso(dados.get("uso")) if dados.get("uso") else None
    pasto = (dados.get("pasto") or "").strip()
    try:  # a tela manda a data como texto (AAAA-MM-DD)
        inicio_pasto = date.fromisoformat(dados["pasto_inicio"]) if dados.get("pasto_inicio") else _hoje()
    except (TypeError, ValueError):
        raise ErroPasto("Data da pastagem inválida.")
    for p in piquetes:
        if area_id is not None or dados.get("sem_grupo"):
            p.area_id = area_id
        if uso:
            p.uso = uso
        for campo in ("descanso_meta_dias", "ocupacao_max_dias"):
            if dados.get(campo) not in (None, ""):
                v = int(dados[campo])
                if not 1 <= v <= 365:
                    raise ErroPasto("Os dias precisam ficar entre 1 e 365.")
                setattr(p, campo, v)
        if pasto and pasto != (p.capim or ""):
            adicionar_pasto(db, p.id, pasto, inicio_pasto,
                            substitui=dados.get("pasto_substitui", True), commit=False)
    db.commit()
    return {"ok": True, "alterados": len(piquetes)}
