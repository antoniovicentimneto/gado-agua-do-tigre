"""Testes dos indicadores de rotação (lotação, ocupação, descanso, uso da área)."""
from datetime import date, timedelta

import pytest

from app.models import Animal, Lote, LotePiquete, Pesagem, Piquete
from app.services import indicadores_pasto as ind
from app.services import pastos as svc

HOJE = date(2026, 10, 18)
QUADRADO = {"type": "Polygon", "coordinates": [[[0, 0], [0.002, 0], [0.002, 0.002], [0, 0.002], [0, 0]]]}


def _piquete(db, nome, ha=10.0):
    p = Piquete(nome=nome, hectares=ha, ativo=True)
    db.add(p)
    db.commit()
    return p


def _ocupacao(db, lote, piquete, entrada, saida, peso, cab=2, ha=None):
    db.add(LotePiquete(lote_id=lote.id, piquete_id=piquete.id, data_entrada=entrada, data_saida=saida,
                       cabecas=cab, peso_entrada=peso, entrada_estimada=False,
                       cabecas_saida=cab if saida else None, peso_saida=peso if saida else None,
                       hectares=ha or piquete.hectares))
    db.commit()


def test_safra_julho_a_junho():
    assert ind.safra_de(date(2026, 10, 18)) == (date(2026, 7, 1), date(2027, 6, 30))
    assert ind.safra_de(date(2026, 3, 1)) == (date(2025, 7, 1), date(2026, 6, 30))


def test_lotacao_ocupacao_e_descanso(db):
    lote = db.query(Lote).filter(Lote.nome == "LOTEA").one()
    p1, p2 = _piquete(db, "P1", 10), _piquete(db, "P2", 5)
    # P1: 900 kg (2 UA) por 10 dias; descanso de 20 dias; volta mais 10 dias
    _ocupacao(db, lote, p1, date(2026, 8, 1), date(2026, 8, 11), 900)
    _ocupacao(db, lote, p2, date(2026, 8, 11), date(2026, 8, 31), 900)
    _ocupacao(db, lote, p1, date(2026, 8, 31), date(2026, 9, 10), 900)
    r = ind.indicadores(db, date(2026, 8, 1), date(2026, 9, 30), HOJE)
    assert r["ocupacao_media_dias"] == pytest.approx((10 + 20 + 10) / 3, abs=0.1)
    assert r["descanso_medio_dias"] == 20
    # Σ(UA×dias)/Σ(ha×dias) = (2×10 + 2×20 + 2×10) / (10×10 + 5×20 + 10×10) = 80/300
    assert r["lotacao_media"] == pytest.approx(80 / 300, abs=0.01)
    linha_p2 = next(x for x in r["por_piquete"] if x["nome"] == "P2")
    assert linha_p2["lotacao"] == pytest.approx(2 / 5, abs=0.01) and linha_p2["dias_ocupado"] == 20


def test_area_do_piquete_na_epoca_vale_mesmo_depois_de_mudar(db):
    lote = db.query(Lote).filter(Lote.nome == "LOTEA").one()
    p = _piquete(db, "P1", 10)
    _ocupacao(db, lote, p, date(2026, 8, 1), date(2026, 8, 11), 900, ha=20)  # tinha 20 ha
    r = ind.indicadores(db, date(2026, 8, 1), date(2026, 8, 31), HOJE)
    assert r["lotacao_media"] == pytest.approx(2 / 20, abs=0.01)


def test_ocupacao_sem_foto_fica_de_fora_e_e_contada(db):
    lote = db.query(Lote).filter(Lote.nome == "LOTEA").one()
    p = _piquete(db, "P1", 10)
    db.add(LotePiquete(lote_id=lote.id, piquete_id=p.id, data_entrada=date(2026, 8, 1),
                       data_saida=date(2026, 8, 5), cabecas=2))
    db.commit()
    r = ind.indicadores(db, date(2026, 8, 1), date(2026, 8, 31), HOJE)
    assert r["ocupacoes_sem_foto"] == 1 and r["lotacao_media"] is None


def test_por_epoca_e_por_pasto(db):
    from app.services import pastos_historico as hist
    lote = db.query(Lote).filter(Lote.nome == "LOTEA").one()
    p = _piquete(db, "P1", 10)
    hist.adicionar_pasto(db, p.id, "Tifton 85", date(2026, 1, 1))
    db.add(LotePiquete(lote_id=lote.id, piquete_id=p.id, data_entrada=date(2026, 9, 21),
                       data_saida=date(2026, 10, 11), cabecas=2, peso_entrada=900, entrada_estimada=False,
                       cabecas_saida=2, peso_saida=940, hectares=10))
    db.commit()
    r = ind.indicadores(db, date(2026, 9, 1), date(2026, 10, 31), HOJE)
    epocas = {e["epoca"] for e in r["por_epoca"]}
    assert epocas == {"Seca", "Águas"}   # setembro é seca, outubro é águas (padrão)
    pasto = r["por_pasto"][0]
    assert pasto["pasto"] == "Tifton 85" and pasto["gmd"] == pytest.approx(40 / 2 / 20, abs=0.001)


def test_periodo_futuro_vazio(db):
    r = ind.indicadores(db, date(2027, 1, 1), date(2027, 2, 1), HOJE)
    assert r["vazio"]
