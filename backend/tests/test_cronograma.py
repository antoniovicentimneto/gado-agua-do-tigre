"""Testes do cronograma de rotação."""
from datetime import date, timedelta

import pytest

from app.models import Lote, LotePiquete, Piquete
from app.services import alertas
from app.services import cronograma as svc
from app.services import pastos

HOJE = date.today()


def _base(db):
    ps = [Piquete(nome=f"P{i}", hectares=10, ativo=True) for i in (1, 2, 3)]
    db.add_all(ps)
    db.commit()
    lote = db.query(Lote).filter(Lote.nome == "LOTEA").one()
    pastos.mover(db, lote.id, ps[0].id, HOJE - timedelta(days=3))
    return lote, ps


def test_datas_previstas_em_sequencia(db):
    lote, (p1, p2, p3) = _base(db)
    c = svc.salvar(db, lote.id, [{"piquete_id": p2.id, "dias": 5}, {"piquete_id": p3.id, "dias": 4}],
                   dias_atual=6)
    assert c["atual"]["saida_prevista"] == (HOJE + timedelta(days=3)).isoformat()  # entrou há 3, fica 6
    assert c["itens"][0]["entrada_prevista"] == (HOJE + timedelta(days=3)).isoformat()
    assert c["itens"][1]["entrada_prevista"] == (HOJE + timedelta(days=8)).isoformat()


def test_aviso_de_descanso_nao_cumprido(db):
    lote, (p1, p2, p3) = _base(db)
    p2.descanso_meta_dias = 30
    db.commit()
    outro = db.query(Lote).filter(Lote.nome == "LOTEB").one()
    pastos.mover(db, outro.id, p2.id, HOJE - timedelta(days=10))
    pastos.mover(db, outro.id, p3.id, HOJE - timedelta(days=5))  # P2 vazio há 5 dias
    c = svc.salvar(db, lote.id, [{"piquete_id": p2.id, "dias": 5}], dias_atual=4)
    assert "antes de cumprir o descanso" in c["itens"][0]["aviso"]


def test_avancar_move_e_anda_a_fila(db):
    lote, (p1, p2, p3) = _base(db)
    svc.salvar(db, lote.id, [{"piquete_id": p2.id, "dias": 5}, {"piquete_id": p3.id, "dias": 4}])
    svc.avancar(db, lote.id)
    ocup = db.query(LotePiquete).filter(LotePiquete.lote_id == lote.id,
                                        LotePiquete.data_saida.is_(None)).one()
    assert ocup.piquete_id == p2.id and ocup.dias_previstos == 5
    c = svc.cronograma_lote(db, lote.id)
    assert [i["piquete"] for i in c["itens"]] == ["P3"]
    svc.avancar(db, lote.id)
    with pytest.raises(pastos.ErroPasto):
        svc.avancar(db, lote.id)  # fila vazia


def test_alerta_usa_dias_planejados_e_diz_o_proximo(db):
    lote, (p1, p2, p3) = _base(db)
    svc.salvar(db, lote.id, [{"piquete_id": p2.id, "dias": 5}], dias_atual=3)
    a = [x for x in alertas.alertas(db, HOJE)["alertas"] if x["tipo"] == "mudar_lote"]
    assert a and "para o P2" in a[0]["titulo"]


def test_validacao(db):
    lote, (p1, p2, p3) = _base(db)
    with pytest.raises(pastos.ErroPasto):
        svc.salvar(db, lote.id, [{"piquete_id": p2.id, "dias": 0}])
    with pytest.raises(pastos.ErroPasto):
        svc.salvar(db, lote.id, [{"piquete_id": 9999, "dias": 3}])
