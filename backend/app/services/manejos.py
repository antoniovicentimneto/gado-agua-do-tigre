"""Histórico de manejos (sessões de pesagem) para consulta na aba Rebanho.

Junta as sessões feitas pelo app com as pesagens antigas importadas da
planilha (que não têm sessão) — assim o histórico completo, incluindo o de
antes do app existir, aparece navegável num único lugar, agrupado por data.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from .gmd import PontoPesagem, resumo_animal
from ..models import Animal, Pesagem, SessaoPesagem


def _gmd(animal: Animal) -> float | None:
    return resumo_animal([PontoPesagem(p.data, p.peso) for p in animal.pesagens])["gmd"]


def _animais_por_id(db: Session, ids: list[int]) -> dict[int, Animal]:
    if not ids:
        return {}
    animais = (
        db.query(Animal)
        .filter(Animal.id.in_(ids))
        .options(selectinload(Animal.pesagens))
        .all()
    )
    return {a.id: a for a in animais}


def _montar_pesados(pesagens: list[Pesagem], animais: dict[int, Animal],
                    com_destino: bool) -> tuple[list[dict], list[float]]:
    pesados, gmds = [], []
    for p in pesagens:
        a = animais.get(p.animal_id)
        gmd = _gmd(a) if a else None
        if gmd is not None:
            gmds.append(gmd)
        item = {
            "id": p.id,
            "animal_id": p.animal_id,
            "brinco": a.brinco if a else "?",
            "tipo": a.tipo if a else None,
            "raca": a.raca if a else None,
            "peso": p.peso,
            "ordem": p.ordem,
            "observacao": p.observacao,
        }
        if com_destino:
            item["destino"] = p.destino_lote.nome if p.destino_lote else None
        pesados.append(item)
    return pesados, gmds


def listar(db: Session) -> list[dict]:
    """Lista todos os manejos: sessões do app + pesagens antigas agrupadas por data."""
    sessoes = (
        db.query(SessaoPesagem)
        .options(
            selectinload(SessaoPesagem.pesagens),
            selectinload(SessaoPesagem.origens),
            selectinload(SessaoPesagem.sublotes),
        )
        .all()
    )
    resultado = []
    for s in sessoes:
        pesos = [p.peso for p in s.pesagens]
        lotes = sorted({*(l.nome for l in s.origens), *(l.nome for l in s.sublotes)})
        resultado.append({
            "chave": f"s:{s.id}",
            "tipo": s.tipo.value,
            "data": s.data,
            "status": s.status.value,
            "lotes": lotes,
            "total": len(pesos),
            "peso_medio": round(sum(pesos) / len(pesos), 1) if pesos else None,
        })

    # Pesagens sem sessão (importadas da planilha ou lançadas fora da mangueira),
    # agrupadas por data — cada data vira um "manejo legado" navegável.
    legado = (
        db.query(Pesagem.data, func.count(Pesagem.id), func.avg(Pesagem.peso))
        .filter(Pesagem.sessao_id.is_(None))
        .group_by(Pesagem.data)
        .all()
    )
    for d, qtd, media in legado:
        resultado.append({
            "chave": f"d:{d.isoformat()}",
            "tipo": "legado",
            "data": d,
            "status": None,
            "lotes": [],
            "total": qtd,
            "peso_medio": round(media, 1) if media is not None else None,
        })

    resultado.sort(key=lambda r: (r["data"], r["chave"]), reverse=True)
    return resultado


def detalhe_sessao(db: Session, sessao_id: int) -> dict | None:
    """Detalhe de uma sessão feita pelo app: cada animal pesado, com destino."""
    sessao = db.get(SessaoPesagem, sessao_id)
    if sessao is None:
        return None
    pesagens = sorted(sessao.pesagens, key=lambda p: p.ordem or 0)
    animais = _animais_por_id(db, [p.animal_id for p in pesagens])
    pesados, gmds = _montar_pesados(pesagens, animais, com_destino=True)
    # Renumera pela posição (1, 2, 3...) em vez do número bruto salvo no banco, pra
    # não mostrar "buraco" na numeração quando um lançamento foi apagado.
    for i, item in enumerate(pesados, start=1):
        item["ordem"] = i
    pesos = [p.peso for p in pesagens]
    return {
        "sessao": {
            "id": sessao.id, "tipo": sessao.tipo.value, "data": sessao.data,
            "status": sessao.status.value,
            "origens": [l.nome for l in sessao.origens],
            "sublotes": [l.nome for l in sessao.sublotes],
        },
        "pesados": pesados,
        "total": len(pesos),
        "peso_medio": round(sum(pesos) / len(pesos), 1) if pesos else None,
        "gmd_medio": round(sum(gmds) / len(gmds), 3) if gmds else None,
    }


def detalhe_legado(db: Session, data: date) -> dict:
    """Detalhe de um dia de pesagens antigas (sem sessão), ordenado por brinco."""
    pesagens = (
        db.query(Pesagem)
        .filter(Pesagem.sessao_id.is_(None), Pesagem.data == data)
        .all()
    )
    animais = _animais_por_id(db, [p.animal_id for p in pesagens])
    pesados, gmds = _montar_pesados(pesagens, animais, com_destino=False)
    pesados.sort(key=lambda item: item["brinco"])
    pesos = [p.peso for p in pesagens]
    return {
        "sessao": {"id": None, "tipo": "legado", "data": data, "status": None,
                   "origens": [], "sublotes": []},
        "pesados": pesados,
        "total": len(pesos),
        "peso_medio": round(sum(pesos) / len(pesos), 1) if pesos else None,
        "gmd_medio": round(sum(gmds) / len(gmds), 3) if gmds else None,
    }
