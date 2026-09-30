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


def _ugmd_ate(pesagens_animal: list[Pesagem], p: Pesagem) -> float | None:
    """GMD do período que TERMINA nesta pesagem: da pesagem anterior do animal até ela."""
    anteriores = [x for x in pesagens_animal if x.data < p.data]
    if not anteriores or p.peso is None:
        return None
    ant = anteriores[-1]  # pesagens já vêm ordenadas por data
    dias = (p.data - ant.data).days
    return (p.peso - ant.peso) / dias if dias > 0 and ant.peso is not None else None


def _media(xs: list[float], casas: int = 3) -> float | None:
    return round(sum(xs) / len(xs), casas) if xs else None


def _ugmd_por_manejo(db: Session) -> dict[str, list[float]]:
    """uGMD de cada pesagem, agrupado pela chave do manejo ("s:<id>" ou "d:<data>").

    Busca só (animal, data, peso, sessão) de todas as pesagens numa consulta só —
    o banco fica longe, então nada de uma consulta por manejo/animal.
    """
    linhas = (
        db.query(Pesagem.animal_id, Pesagem.data, Pesagem.peso, Pesagem.sessao_id)
        .order_by(Pesagem.animal_id, Pesagem.data)
        .all()
    )
    por_manejo: dict[str, list[float]] = {}
    anterior = None
    for animal_id, d, peso, sessao_id in linhas:
        if anterior and anterior[0] == animal_id and peso is not None and anterior[2] is not None:
            dias = (d - anterior[1]).days
            if dias > 0:
                chave = f"s:{sessao_id}" if sessao_id else f"d:{d.isoformat()}"
                por_manejo.setdefault(chave, []).append((peso - anterior[2]) / dias)
        anterior = (animal_id, d, peso)
    return por_manejo


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
                    com_destino: bool) -> tuple[list[dict], list[float], list[float]]:
    pesados, gmds, ugmds = [], [], []
    for p in pesagens:
        a = animais.get(p.animal_id)
        gmd = _gmd(a) if a else None
        if gmd is not None:
            gmds.append(gmd)
        ugmd = _ugmd_ate(a.pesagens, p) if a else None
        if ugmd is not None:
            ugmds.append(ugmd)
        item = {
            "id": p.id,
            "animal_id": p.animal_id,
            "brinco": a.brinco if a else "?",
            "tipo": a.tipo if a else None,
            "raca": a.raca if a else None,
            "peso": p.peso,
            # Ganho diário desde a pesagem anterior do animal até esta.
            "ugmd": round(ugmd, 3) if ugmd is not None else None,
            "ordem": p.ordem,
            "observacao": p.observacao,
        }
        if com_destino:
            item["destino"] = p.destino_lote.nome if p.destino_lote else None
        pesados.append(item)
    return pesados, gmds, ugmds


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
    ugmd_por_manejo = _ugmd_por_manejo(db)
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
            "ugmd_medio": _media(ugmd_por_manejo.get(f"s:{s.id}", [])),
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
            "ugmd_medio": _media(ugmd_por_manejo.get(f"d:{d.isoformat()}", [])),
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
    pesados, gmds, ugmds = _montar_pesados(pesagens, animais, com_destino=True)
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
        # Média do ganho de cada animal desde a pesagem anterior até este manejo.
        "ugmd_medio": _media(ugmds),
    }


def detalhe_legado(db: Session, data: date) -> dict:
    """Detalhe de um dia de pesagens antigas (sem sessão), ordenado por brinco."""
    pesagens = (
        db.query(Pesagem)
        .filter(Pesagem.sessao_id.is_(None), Pesagem.data == data)
        .all()
    )
    animais = _animais_por_id(db, [p.animal_id for p in pesagens])
    pesados, gmds, ugmds = _montar_pesados(pesagens, animais, com_destino=False)
    pesados.sort(key=lambda item: item["brinco"])
    pesos = [p.peso for p in pesagens]
    return {
        "sessao": {"id": None, "tipo": "legado", "data": data, "status": None,
                   "origens": [], "sublotes": []},
        "pesados": pesados,
        "total": len(pesos),
        "peso_medio": round(sum(pesos) / len(pesos), 1) if pesos else None,
        "gmd_medio": round(sum(gmds) / len(gmds), 3) if gmds else None,
        # Média do ganho de cada animal desde a pesagem anterior até este manejo.
        "ugmd_medio": _media(ugmds),
    }
