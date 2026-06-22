"""Cálculo de venda: rendimento padrão por tipo e valor recebido pela arroba líquida."""
from __future__ import annotations

from ..config import config

# 1 arroba (@) = 15 kg de CARCAÇA (padrão do boi gordo no Brasil).
KG_POR_ARROBA = 15.0


def rendimento_padrao(tipo: str | None) -> float:
    """Rendimento de carcaça padrão por tipo (editável na venda)."""
    t = (tipo or "").strip().lower()
    if t.startswith("vaca"):
        return config.rendimento_vaca
    if t.startswith("boi"):
        return config.rendimento_boi
    # Novilha e demais usam o padrão de novilha.
    return config.rendimento_novilha


def calcular_venda(peso: float, rendimento: float, preco_arroba: float) -> dict:
    """Calcula arroba líquida e valor recebido.

    arroba_liquida = peso_vivo * rendimento / 30
    valor_recebido = arroba_liquida * preço_da_@_líquida
    """
    peso_carcaca = peso * rendimento
    arroba_liquida = peso_carcaca / KG_POR_ARROBA
    valor_recebido = arroba_liquida * preco_arroba
    return {
        "peso_carcaca": round(peso_carcaca, 2),
        "arroba_liquida": round(arroba_liquida, 2),
        "valor_recebido": round(valor_recebido, 2),
    }
