"""Testes de unir piquetes e editar em massa."""
from datetime import date, timedelta

import pytest

from app.models import Lote, LotePiquete, Piquete
from app.services import pastos as svc
from app.services import pastos_historico as hist

HOJE = date.today()
A = {"type": "Polygon", "coordinates": [[[0, 0], [0.001, 0], [0.001, 0.001], [0, 0.001], [0, 0]]]}
B = {"type": "Polygon", "coordinates": [[[0.001, 0], [0.002, 0], [0.002, 0.001], [0.001, 0.001], [0.001, 0]]]}


def _p(db, nome, geo, capim=None):
    r = svc.salvar_piquete(db, {"nome": nome, "geometria": geo, **({"capim": capim} if capim else {})})
    return db.get(Piquete, r["id"])


def test_unir_soma_area_herda_pasto_e_leva_o_gado(db):
    pa, pb = _p(db, "A", A, "Tifton 85"), _p(db, "B", B, "Tifton 85")
    lote = db.query(Lote).filter(Lote.nome == "LOTEA").one()
    svc.mover(db, lote.id, pb.id, HOJE - timedelta(days=4))
    r = hist.unir(db, [pa.id, pb.id], "AB", HOJE)
    novo = db.get(Piquete, r["novo"]["id"])
    assert novo.hectares == pytest.approx(pa.hectares + pb.hectares, abs=0.02)
    assert novo.capim == "Tifton 85" and r["pasto_herdado"] == ["Tifton 85"]
    assert not db.get(Piquete, pa.id).ativo and db.get(Piquete, pa.id).destino_id == novo.id
    ocup = db.query(LotePiquete).filter(LotePiquete.lote_id == lote.id, LotePiquete.data_saida.is_(None)).one()
    assert ocup.piquete_id == novo.id
    h = hist.historico(db, novo.id)
    assert {x["nome"] for x in h["uniao_de"]} == {db.get(Piquete, pa.id).nome, db.get(Piquete, pb.id).nome}
    assert hist.historico(db, pa.id)["unido_em"]["id"] == novo.id


def test_unir_pastos_diferentes_usa_o_informado(db):
    pa, pb = _p(db, "A", A, "Tifton 85"), _p(db, "B", B, "Marandu")
    r = hist.unir(db, [pa.id, pb.id], "AB", HOJE)
    assert r["pasto_herdado"] == []
    pc, pd = _p(db, "C", A, "Tifton 85"), _p(db, "D", B, "Marandu")
    r = hist.unir(db, [pc.id, pd.id], "CD", HOJE, pasto="Estrela-africana")
    assert db.get(Piquete, r["novo"]["id"]).capim == "Estrela-africana"


def test_unir_valida(db):
    pa = _p(db, "A", A)
    with pytest.raises(svc.ErroPasto):
        hist.unir(db, [pa.id], "X", HOJE)
    pb = _p(db, "B", B)
    with pytest.raises(svc.ErroPasto):
        hist.unir(db, [pa.id, pb.id], "", HOJE)


def test_editar_em_massa(db):
    pa, pb = _p(db, "A", A), _p(db, "B", B)
    # Como a tela manda: números e data em texto.
    r = hist.editar_em_massa(db, [pa.id, pb.id], {"uso": "inverno", "descanso_meta_dias": "30",
                                                  "area_nome": "Castro/Rosa", "pasto": "Azevém",
                                                  "pasto_inicio": HOJE.isoformat()})
    assert r["alterados"] == 2
    for p in (db.get(Piquete, pa.id), db.get(Piquete, pb.id)):
        assert p.uso == "inverno" and p.descanso_meta_dias == 30 and p.capim == "Azevém"
        assert p.area is not None and p.area.nome == "Castro/Rosa"
    with pytest.raises(svc.ErroPasto):
        hist.editar_em_massa(db, [pa.id], {"ocupacao_max_dias": 0})
