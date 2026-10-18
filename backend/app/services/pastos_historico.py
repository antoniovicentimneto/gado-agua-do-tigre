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
    return {
        "piquete": {"id": p.id, "nome": p.nome, "hectares": p.hectares, "ativo": p.ativo,
                    "encerrado_em": p.encerrado_em.isoformat() if p.encerrado_em else None},
        "origem": {"id": origem.id, "nome": origem.nome} if origem else None,
        "partes": [{"id": x.id, "nome": x.nome} for x in partes],
        "ocupacoes": lista,
        "pastos": [_periodo_dict(x) for x in reversed(pers)],
    }
