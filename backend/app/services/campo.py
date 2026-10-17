"""Manejo de campo: salga de cocho por lote e ocorrências sanitárias por animal.

Os dois são lançados pelo peão no celular, muitas vezes sem sinal — por isso toda
gravação aceita uma `chave` gerada no aparelho (o reenvio da fila não duplica).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..models import Animal, AnimalLote, Lote, LotePiquete, PapelUsuario, StatusAnimal, Usuario
from ..models_campo import OcorrenciaSanitaria, SalgaCocho
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
           chave: str | None = None, usuario: Usuario | None = None) -> dict:
    """Registra uma salga de cocho do lote (guarda piquete e cabeças do momento)."""
    if chave:
        feita = db.query(SalgaCocho).filter(SalgaCocho.chave_cliente == chave).first()
        if feita:
            return {"ok": True, "salga": _salga_dict(feita), "repetida": True}
    lote = db.get(Lote, lote_id)
    if lote is None:
        raise ErroCampo("Lote não encontrado.")
    produto = (produto or "").strip()
    if not produto:
        raise ErroCampo("Escolha qual sal foi colocado.")
    if quantidade_kg is None or quantidade_kg <= 0:
        raise ErroCampo("Informe a quantidade em kg.")
    if quantidade_kg > 20000:
        raise ErroCampo("Quantidade alta demais — confira se está em kg.")
    ocup = (
        db.query(LotePiquete)
        .filter(LotePiquete.lote_id == lote_id, LotePiquete.data_saida.is_(None))
        .first()
    )
    s = SalgaCocho(
        lote_id=lote.id, piquete_id=ocup.piquete_id if ocup else None,
        cabecas=_cabecas_ativas(db, lote.id), produto=produto[:60],
        quantidade_kg=round(float(quantidade_kg), 2),
        data_hora=_validar_data_hora(data_hora), observacao=(observacao or "").strip() or None,
        usuario_id=usuario.id if usuario else None,
        usuario_nome=usuario.nome if usuario else None, chave_cliente=chave,
    )
    db.add(s)
    db.commit()
    return {"ok": True, "salga": _salga_dict(s)}


def consumo(salgas: list[SalgaCocho], hoje: date) -> dict:
    """Consumo de sal em gramas por cabeça por dia.

    Cada salga é "consumida" até a salga seguinte: kg ÷ (cabeças × dias entre as duas).
    A última salga ainda não terminou, então não entra. Média = total de kg ÷ total de
    cabeça-dias das salgas fechadas nos últimos 60 dias.
    """
    ordenadas = sorted(salgas, key=lambda s: s.data_hora)
    intervalos = []
    for atual, prox in zip(ordenadas, ordenadas[1:]):
        dias = (prox.data_hora - atual.data_hora).total_seconds() / 86400
        if dias < 0.5 or not atual.cabecas:
            continue
        intervalos.append({
            "id": atual.id,
            "g_cab_dia": round(atual.quantidade_kg * 1000 / (atual.cabecas * dias)),
            "dias": round(dias, 1),
            "inicio": atual.data_hora.date(),
            "kg": atual.quantidade_kg,
            "cab_dias": atual.cabecas * dias,
        })
    limite = hoje - timedelta(days=JANELA_CONSUMO_DIAS)
    janela = [i for i in intervalos if i["inicio"] >= limite]
    cab_dias = sum(i["cab_dias"] for i in janela)
    return {
        "por_salga": {i["id"]: i["g_cab_dia"] for i in intervalos},
        "media_g_cab_dia": round(sum(i["kg"] for i in janela) * 1000 / cab_dias) if cab_dias else None,
    }


def historico_sal(db: Session, lote_id: int, hoje: date | None = None, limite: int = 30) -> dict:
    hoje = hoje or date.today()
    salgas = (
        db.query(SalgaCocho).filter(SalgaCocho.lote_id == lote_id)
        .options(selectinload(SalgaCocho.lote))
        .order_by(SalgaCocho.data_hora.desc()).limit(limite).all()
    )
    c = consumo(salgas, hoje)
    lista = []
    for s in salgas:
        d = _salga_dict(s)
        d["g_cab_dia"] = c["por_salga"].get(s.id)
        lista.append(d)
    ultima = salgas[0] if salgas else None
    return {
        "salgas": lista,
        "media_g_cab_dia": c["media_g_cab_dia"],
        "ultima": _salga_dict(ultima) if ultima else None,
        "dias_desde_ultima": (hoje - ultima.data_hora.date()).days if ultima else None,
    }


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
    s = db.get(SalgaCocho, salga_id)
    if s is None:
        raise ErroCampo("Salga não encontrada.")
    if not _pode_apagar(s, usuario, date.today()):
        raise ErroCampo("Só o dono apaga salgas antigas ou lançadas por outra pessoa.")
    db.delete(s)
    db.commit()
    return {"ok": True}


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
