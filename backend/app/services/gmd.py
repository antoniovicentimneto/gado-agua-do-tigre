"""Cálculos de GMD (Ganho Médio Diário) a partir das pesagens.

GMD       = (último peso - primeiro peso) / dias totais  -> índice principal
uGMD      = GMD do último período (entre as duas últimas pesagens)
GMD período = GMD entre duas pesagens dentro de um intervalo escolhido (compara pastagens)
"""
from __future__ import annotations

from datetime import date
from typing import Iterable, NamedTuple


class PontoPesagem(NamedTuple):
    data: date
    peso: float


def _ordenar(pesagens: Iterable[PontoPesagem]) -> list[PontoPesagem]:
    return sorted(pesagens, key=lambda p: p.data)


def gmd_entre(p_ini: PontoPesagem, p_fim: PontoPesagem) -> float | None:
    """GMD em kg/dia entre dois pontos. None se as datas forem iguais."""
    dias = (p_fim.data - p_ini.data).days
    if dias <= 0:
        return None
    return (p_fim.peso - p_ini.peso) / dias


def gmd_total(pesagens: Iterable[PontoPesagem]) -> float | None:
    """GMD do período inteiro (primeira à última pesagem)."""
    pts = _ordenar(pesagens)
    if len(pts) < 2:
        return None
    return gmd_entre(pts[0], pts[-1])


def ugmd(pesagens: Iterable[PontoPesagem]) -> float | None:
    """GMD do último período (entre as duas últimas pesagens)."""
    pts = _ordenar(pesagens)
    if len(pts) < 2:
        return None
    return gmd_entre(pts[-2], pts[-1])


def gmd_periodo(
    pesagens: Iterable[PontoPesagem],
    inicio: date | None = None,
    fim: date | None = None,
) -> dict | None:
    """GMD entre a primeira e a última pesagem dentro do intervalo [inicio, fim].

    Usa as pesagens reais mais próximas das bordas do intervalo. Útil para comparar
    o desempenho do animal em uma pastagem/safra específica.
    """
    pts = _ordenar(pesagens)
    if inicio is not None:
        pts = [p for p in pts if p.data >= inicio]
    if fim is not None:
        pts = [p for p in pts if p.data <= fim]
    if len(pts) < 2:
        return None

    valor = gmd_entre(pts[0], pts[-1])
    return {
        "data_inicio": pts[0].data,
        "data_fim": pts[-1].data,
        "peso_inicio": pts[0].peso,
        "peso_fim": pts[-1].peso,
        "dias": (pts[-1].data - pts[0].data).days,
        "ganho": pts[-1].peso - pts[0].peso,
        "gmd": valor,
        "qtde_pesagens": len(pts),
    }


def resumo_animal(pesagens: Iterable[PontoPesagem]) -> dict:
    """Resumo de pesos e GMDs para a ficha do animal."""
    pts = _ordenar(pesagens)
    return {
        "qtde_pesagens": len(pts),
        "primeiro_peso": pts[0].peso if pts else None,
        "ultimo_peso": pts[-1].peso if pts else None,
        "data_primeiro": pts[0].data if pts else None,
        "data_ultimo": pts[-1].data if pts else None,
        "gmd": gmd_total(pts),
        "ugmd": ugmd(pts),
    }
