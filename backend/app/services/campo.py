"""Manejo de campo: salga de cocho por lote e ocorrências sanitárias por animal.

Os dois são lançados pelo peão no celular, muitas vezes sem sinal — por isso toda
gravação aceita uma `chave` gerada no aparelho (o reenvio da fila não duplica).
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..models import Animal, AnimalLote, Lote, LotePiquete, PapelUsuario, StatusAnimal, Usuario
from ..models_campo import ConfigValor, OcorrenciaSanitaria, SalgaCocho
from .consultas import lote_atual

JANELA_CONSUMO_DIAS = 60  # consumo médio de sal olha as salgas dos últimos 60 dias


class ErroCampo(ValueError):
    """Erro de regra de negócio — a mensagem é mostrada ao usuário como está."""


def _validar_data_hora(quando: datetime | None, agora: datetime | None = None) -> datetime:
    """Data/hora vem do aparelho (hora local do campo). Aceita até 1 dia "no futuro"
    porque o servidor roda em UTC e o relógio do celular pode estar adiantado."""
    agora = agora or datetime.utcnow()
    quando = quando or agora
    if quando.tzinfo is not None:
        quando = quando.replace(tzinfo=None)
    if quando > agora + timedelta(days=1):
        raise ErroCampo("A data não pode ser no futuro.")
    return quando


def _pode_apagar(registro, usuario: Usuario, hoje: date) -> bool:
    """Dono apaga qualquer um; o peão só o que ele mesmo lançou hoje (corrigir engano)."""
    if usuario.papel == PapelUsuario.DONO:
        return True
    return registro.usuario_id == usuario.id and registro.criado_em.date() >= hoje - timedelta(days=1)


# ---------------------------------------------------------------- Sal no cocho

def _salga_dict(s: SalgaCocho) -> dict:
    return {
        "id": s.id,
        "lote_id": s.lote_id,
        "lote": s.lote.nome if s.lote else None,
        "piquete_id": s.piquete_id,
        "cabecas": s.cabecas,
        "produto": s.produto,
        "quantidade_kg": s.quantidade_kg,
        "data_hora": s.data_hora.isoformat(timespec="minutes"),
        "observacao": s.observacao,
        "usuario": s.usuario_nome,
        "chave": s.chave_cliente,
    }


def _cabecas_ativas(db: Session, lote_id: int) -> int:
    return db.execute(
        select(func.count(func.distinct(AnimalLote.animal_id)))
        .join(Animal, Animal.id == AnimalLote.animal_id)
        .where(AnimalLote.lote_id == lote_id, AnimalLote.data_fim.is_(None),
               Animal.status == StatusAnimal.ATIVO)
    ).scalar() or 0


def salgar(db: Session, lote_id: int, produto: str, quantidade_kg: float,
           data_hora: datetime | None = None, observacao: str | None = None,
           chave: str | None = None, usuario: Usuario | None = None,
           outros_lotes: list[int] | None = None) -> dict:
    """Registra uma salga de cocho (guarda piquete e cabeças do momento).

    Com `outros_lotes`, o cocho é dividido: a quantidade é repartida pelas cabeças de cada
    lote e cada um ganha sua linha (mesmo `grupo`), pra o consumo por cabeça sair certo.
    """
    if chave:
        feita = db.query(SalgaCocho).filter(SalgaCocho.chave_cliente == chave).first()
        if feita:
            return {"ok": True, "salga": _salga_dict(feita), "repetida": True}
    lote_ids = [lote_id] + [x for x in dict.fromkeys(outros_lotes or []) if x != lote_id]
    lotes = [db.get(Lote, x) for x in lote_ids]
    if any(l is None for l in lotes):
        raise ErroCampo("Lote não encontrado.")
    produto = (produto or "").strip()
    if not produto:
        raise ErroCampo("Escolha qual sal foi colocado.")
    if quantidade_kg is None or quantidade_kg <= 0:
        raise ErroCampo("Informe a quantidade em kg.")
    if quantidade_kg > 20000:
        raise ErroCampo("Quantidade alta demais — confira se está em kg.")
    quando = _validar_data_hora(data_hora)
    cabecas = [_cabecas_ativas(db, l.id) for l in lotes]
    total = sum(cabecas)
    dividido = len(lotes) > 1
    if dividido and not total:
        raise ErroCampo("Os lotes do cocho estão sem animais — não dá pra dividir.")
    grupo = (chave or f"g{int(quando.timestamp())}-{lote_id}")[:40] if dividido else None
    linhas = []
    for n, (l, cab) in enumerate(zip(lotes, cabecas)):
        ocup = (db.query(LotePiquete)
                .filter(LotePiquete.lote_id == l.id, LotePiquete.data_saida.is_(None)).first())
        parte = quantidade_kg * (cab / total) if dividido else quantidade_kg
        s = SalgaCocho(
            lote_id=l.id, piquete_id=ocup.piquete_id if ocup else None, cabecas=cab,
            produto=produto[:60], quantidade_kg=round(float(parte), 2), data_hora=quando,
            observacao=(observacao or "").strip() or None,
            usuario_id=usuario.id if usuario else None,
            usuario_nome=usuario.nome if usuario else None,
            chave_cliente=chave if n == 0 else (f"{chave}:{n}"[:40] if chave else None),
            grupo=grupo,
        )
        db.add(s)
        linhas.append(s)
    db.commit()
    r = {"ok": True, "salga": _salga_dict(linhas[0])}
    if dividido:
        r["divisao"] = [{"lote": x.lote.nome if x.lote else None, "cabecas": x.cabecas,
                         "quantidade_kg": x.quantidade_kg} for x in linhas]
    return r


# ---------------------------------------------------------------- Faixa de consumo por sal

CHAVE_FAIXAS = "faixas_sal"


def carregar_faixas(db: Session) -> dict:
    """{produto: {"min": g, "max": g}} — consumo esperado por cabeça/dia (do rótulo)."""
    linha = db.get(ConfigValor, CHAVE_FAIXAS)
    try:
        return json.loads(linha.valor) if linha else {}
    except ValueError:
        return {}


def salvar_faixas(db: Session, faixas: dict) -> dict:
    limpas = {}
    for produto, f in (faixas or {}).items():
        produto = str(produto).strip()[:60]
        f = f if isinstance(f, dict) else {}
        try:
            mn = float(str(f["min"]).replace(",", ".")) if f.get("min") not in (None, "") else None
            mx = float(str(f["max"]).replace(",", ".")) if f.get("max") not in (None, "") else None
        except ValueError:
            raise ErroCampo(f"{produto}: use números na faixa.")
        if mn is None and mx is None:
            continue
        if mn is not None and mx is not None and mn > mx:
            raise ErroCampo(f"{produto}: o mínimo é maior que o máximo.")
        if any(v is not None and not 0 <= v <= 5000 for v in (mn, mx)):
            raise ErroCampo(f"{produto}: faixa fora do razoável (0 a 5.000 g por cabeça/dia).")
        limpas[produto] = {"min": mn, "max": mx}
    linha = db.get(ConfigValor, CHAVE_FAIXAS) or ConfigValor(chave=CHAVE_FAIXAS)
    linha.valor = json.dumps(limpas)
    db.add(linha)
    db.commit()
    return limpas


def _situacao(g: float | None, faixa: dict | None) -> str | None:
    if g is None or not faixa:
        return None
    if faixa.get("min") is not None and g < faixa["min"]:
        return "baixo"
    if faixa.get("max") is not None and g > faixa["max"]:
        return "alto"
    return "ok"


def consumo(salgas: list[SalgaCocho], hoje: date) -> dict:
    """Consumo em gramas por cabeça por dia, separado por sal (o cocho do mineral e o do
    proteinado são cochos diferentes).

    Cada salga é "consumida" até a salga seguinte do MESMO sal: kg ÷ (cabeças × dias).
    A última ainda está no cocho e não entra. Média = kg ÷ cabeça-dias dos últimos 60 dias.
    """
    por_produto: dict[str, list] = {}
    for s in sorted(salgas, key=lambda x: x.data_hora):
        por_produto.setdefault(s.produto, []).append(s)
    por_salga, medias = {}, {}
    limite = hoje - timedelta(days=JANELA_CONSUMO_DIAS)
    for produto, lista in por_produto.items():
        kg = cab_dias = 0.0
        for atual, prox in zip(lista, lista[1:]):
            dias = (prox.data_hora - atual.data_hora).total_seconds() / 86400
            if dias < 0.5 or not atual.cabecas:
                continue
            por_salga[atual.id] = round(atual.quantidade_kg * 1000 / (atual.cabecas * dias))
            if atual.data_hora.date() >= limite:
                kg += atual.quantidade_kg
                cab_dias += atual.cabecas * dias
        medias[produto] = round(kg * 1000 / cab_dias) if cab_dias else None
    validas = [v for v in medias.values() if v is not None]
    return {"por_salga": por_salga, "por_produto": medias,
            "media_g_cab_dia": validas[0] if len(validas) == 1 else None}


def historico_sal(db: Session, lote_id: int, hoje: date | None = None, limite: int = 30) -> dict:
    hoje = hoje or date.today()
    salgas = (
        db.query(SalgaCocho).filter(SalgaCocho.lote_id == lote_id)
        .options(selectinload(SalgaCocho.lote))
        .order_by(SalgaCocho.data_hora.desc()).limit(limite).all()
    )
    faixas = carregar_faixas(db)
    c = consumo(salgas, hoje)
    lista = []
    for s in salgas:
        d = _salga_dict(s)
        d["g_cab_dia"] = c["por_salga"].get(s.id)
        d["situacao"] = _situacao(d["g_cab_dia"], faixas.get(s.produto))
        d["grupo"] = s.grupo
        lista.append(d)
    ultima = salgas[0] if salgas else None
    return {
        "salgas": lista,
        "media_g_cab_dia": c["media_g_cab_dia"],
        "por_produto": [{"produto": p, "media_g_cab_dia": m, "faixa": faixas.get(p),
                         "situacao": _situacao(m, faixas.get(p))} for p, m in c["por_produto"].items()],
        "ultima": _salga_dict(ultima) if ultima else None,
        "dias_desde_ultima": (hoje - ultima.data_hora.date()).days if ultima else None,
    }


def consumo_fora_da_faixa(db: Session, hoje: date) -> list[dict]:
    """Lotes cujo último consumo medido (de cada sal) saiu da faixa configurada."""
    faixas = carregar_faixas(db)
    if not faixas:
        return []
    desde = datetime.combine(hoje - timedelta(days=JANELA_CONSUMO_DIAS), datetime.min.time())
    salgas = (db.query(SalgaCocho).filter(SalgaCocho.data_hora >= desde)
              .options(selectinload(SalgaCocho.lote)).all())
    por_lote: dict[int, list] = {}
    for s in salgas:
        por_lote.setdefault(s.lote_id, []).append(s)
    saida = []
    for lote_id, lista in por_lote.items():
        c = consumo(lista, hoje)
        for produto in sorted({s.produto for s in lista}):
            faixa = faixas.get(produto)
            medidas = sorted((s for s in lista if s.produto == produto and s.id in c["por_salga"]),
                             key=lambda s: s.data_hora)
            if not faixa or not medidas:
                continue
            g = c["por_salga"][medidas[-1].id]
            sit = _situacao(g, faixa)
            if sit in ("baixo", "alto"):
                saida.append({"lote_id": lote_id, "lote": medidas[-1].lote.nome if medidas[-1].lote else "?",
                              "produto": produto, "g_cab_dia": g, "situacao": sit, "faixa": faixa})
    return saida


def ultimas_salgas_por_lote(db: Session) -> dict[int, dict]:
    """Última salga de cada lote, numa consulta só (pro painel de pastos)."""
    sub = (
        select(SalgaCocho.lote_id, func.max(SalgaCocho.data_hora).label("dh"))
        .group_by(SalgaCocho.lote_id).subquery()
    )
    linhas = db.execute(
        select(SalgaCocho).join(sub, (SalgaCocho.lote_id == sub.c.lote_id)
                                & (SalgaCocho.data_hora == sub.c.dh))
    ).scalars().all()
    return {s.lote_id: {"data_hora": s.data_hora.isoformat(timespec="minutes"),
                        "produto": s.produto, "quantidade_kg": s.quantidade_kg} for s in linhas}


def apagar_salga(db: Session, salga_id: int, usuario: Usuario) -> dict:
    """Apaga a salga; se o cocho era dividido, apaga a parte de todos os lotes."""
    s = db.get(SalgaCocho, salga_id)
    if s is None:
        raise ErroCampo("Salga não encontrada.")
    if not _pode_apagar(s, usuario, date.today()):
        raise ErroCampo("Só o dono apaga salgas antigas ou lançadas por outra pessoa.")
    linhas = db.query(SalgaCocho).filter(SalgaCocho.grupo == s.grupo).all() if s.grupo else [s]
    for x in linhas:
        db.delete(x)
    db.commit()
    return {"ok": True, "apagadas": len(linhas)}


# ---------------------------------------------------------------- Sanidade

def _ocorrencia_dict(o: OcorrenciaSanitaria) -> dict:
    return {
        "id": o.id,
        "animal_id": o.animal_id,
        "brinco": o.animal.brinco if o.animal else None,
        "tipo_animal": o.animal.tipo if o.animal else None,
        "lote": o.lote_nome,
        "data_hora": o.data_hora.isoformat(timespec="minutes"),
        "problema": o.problema,
        "produto": o.produto,
        "dose": o.dose,
        "carencia_dias": o.carencia_dias,
        "carencia_ate": o.carencia_ate.isoformat() if o.carencia_ate else None,
        "observacao": o.observacao,
        "usuario": o.usuario_nome,
    }


def registrar_ocorrencia(db: Session, animal_id: int, problema: str, *,
                         produto: str | None = None, dose: str | None = None,
                         carencia_dias: int | None = None, data_hora: datetime | None = None,
                         observacao: str | None = None, chave: str | None = None,
                         usuario: Usuario | None = None) -> dict:
    """Registra o tratamento de um animal. Com carência, calcula até quando ele não pode
    ir pro abate (data do tratamento + dias de carência)."""
    if chave:
        feita = db.query(OcorrenciaSanitaria).filter(OcorrenciaSanitaria.chave_cliente == chave).first()
        if feita:
            return {"ok": True, "ocorrencia": _ocorrencia_dict(feita), "repetida": True}
    animal = db.query(Animal).options(
        selectinload(Animal.lotes).selectinload(AnimalLote.lote)
    ).filter(Animal.id == animal_id).first()
    if animal is None:
        raise ErroCampo("Animal não encontrado.")
    problema = (problema or "").strip()
    if not problema:
        raise ErroCampo("Escolha o problema (ex.: bicheira, pneumonia, casco).")
    if carencia_dias is not None and (carencia_dias < 0 or carencia_dias > 365):
        raise ErroCampo("Carência deve ficar entre 0 e 365 dias.")
    quando = _validar_data_hora(data_hora)
    o = OcorrenciaSanitaria(
        animal_id=animal.id, lote_nome=lote_atual(animal), data_hora=quando,
        problema=problema[:60], produto=(produto or "").strip()[:60] or None,
        dose=(dose or "").strip()[:40] or None, carencia_dias=carencia_dias or None,
        carencia_ate=quando.date() + timedelta(days=carencia_dias) if carencia_dias else None,
        observacao=(observacao or "").strip() or None,
        usuario_id=usuario.id if usuario else None,
        usuario_nome=usuario.nome if usuario else None, chave_cliente=chave,
    )
    db.add(o)
    db.commit()
    return {"ok": True, "ocorrencia": _ocorrencia_dict(o)}


def listar_ocorrencias(db: Session, animal_id: int | None = None, dias: int | None = None,
                       hoje: date | None = None) -> list[dict]:
    hoje = hoje or date.today()
    q = db.query(OcorrenciaSanitaria).options(selectinload(OcorrenciaSanitaria.animal))
    if animal_id:
        q = q.filter(OcorrenciaSanitaria.animal_id == animal_id)
    if dias:
        q = q.filter(OcorrenciaSanitaria.data_hora >= datetime.combine(hoje - timedelta(days=dias), datetime.min.time()))
    return [_ocorrencia_dict(o) for o in q.order_by(OcorrenciaSanitaria.data_hora.desc()).all()]


def carencias_ativas(db: Session, hoje: date | None = None) -> dict[int, date]:
    """Animal → até quando está em carência (só os que ainda estão), numa consulta só."""
    hoje = hoje or date.today()
    return dict(db.execute(
        select(OcorrenciaSanitaria.animal_id, func.max(OcorrenciaSanitaria.carencia_ate))
        .where(OcorrenciaSanitaria.carencia_ate >= hoje)
        .group_by(OcorrenciaSanitaria.animal_id)
    ).all())


def apagar_ocorrencia(db: Session, ocorrencia_id: int, usuario: Usuario) -> dict:
    o = db.get(OcorrenciaSanitaria, ocorrencia_id)
    if o is None:
        raise ErroCampo("Registro não encontrado.")
    if not _pode_apagar(o, usuario, date.today()):
        raise ErroCampo("Só o dono apaga registros antigos ou lançados por outra pessoa.")
    db.delete(o)
    db.commit()
    return {"ok": True}
