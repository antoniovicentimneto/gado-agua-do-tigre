"""Funções auxiliares de consulta que montam dados derivados (lote atual, GMD)."""
from __future__ import annotations

from ..models import Animal
from .gmd import PontoPesagem, resumo_animal


def pontos_pesagem(animal: Animal) -> list[PontoPesagem]:
    """Converte as pesagens do animal em pontos para os cálculos de GMD."""
    return [PontoPesagem(p.data, p.peso) for p in animal.pesagens]


def lote_atual(animal: Animal) -> str | None:
    """Nome do lote atual (o vínculo sem data_fim, ou o mais recente)."""
    if not animal.lotes:
        return None
    abertos = [al for al in animal.lotes if al.data_fim is None]
    escolhido = abertos[-1] if abertos else animal.lotes[-1]
    return escolhido.lote.nome if escolhido.lote else None


def montar_resumo(animal: Animal) -> dict:
    """Monta o dicionário usado em AnimalResumo (lista de animais)."""
    r = resumo_animal(pontos_pesagem(animal))
    return {
        "id": animal.id,
        "brinco": animal.brinco,
        "tipo": animal.tipo,
        "raca": animal.raca,
        "cor": animal.cor,
        "vendedor": animal.vendedor,
        "nascimento": animal.nascimento,
        "capado": animal.capado,
        "sem_brinco": animal.sem_brinco,
        "status": animal.status,
        "observacao": animal.observacao,
        "lote_atual": lote_atual(animal),
        "ultimo_peso": r["ultimo_peso"],
        "data_ultimo": r["data_ultimo"],
        "gmd": r["gmd"],
        "ugmd": r["ugmd"],
    }
