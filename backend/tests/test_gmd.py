"""Testes dos cálculos de GMD."""
from datetime import date

from app.services.gmd import (
    PontoPesagem,
    gmd_periodo,
    gmd_total,
    resumo_animal,
    ugmd,
)


def _pontos():
    # Mesmo exemplo do brinco 3 da planilha: 310 -> 355 -> 370.
    return [
        PontoPesagem(date(2025, 6, 2), 310),
        PontoPesagem(date(2025, 9, 3), 355),
        PontoPesagem(date(2025, 10, 14), 370),
    ]


def test_gmd_total_bate_com_a_planilha():
    # (370 - 310) / 134 dias = 0.4477...
    assert round(gmd_total(_pontos()), 4) == 0.4478


def test_ugmd_usa_as_duas_ultimas():
    # (370 - 355) / 41 dias = 0.3658...
    assert round(ugmd(_pontos()), 4) == 0.3659


def test_gmd_uma_pesagem_retorna_none():
    assert gmd_total([PontoPesagem(date(2025, 1, 1), 200)]) is None
    assert ugmd([]) is None


def test_gmd_periodo_filtra_intervalo():
    res = gmd_periodo(_pontos(), inicio=date(2025, 9, 1), fim=date(2025, 10, 31))
    assert res["peso_inicio"] == 355
    assert res["peso_fim"] == 370
    assert res["dias"] == 41


def test_resumo_animal():
    r = resumo_animal(_pontos())
    assert r["primeiro_peso"] == 310
    assert r["ultimo_peso"] == 370
    assert r["qtde_pesagens"] == 3
