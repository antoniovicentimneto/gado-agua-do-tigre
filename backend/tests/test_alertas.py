"""Testes dos alertas do sininho."""
from datetime import date, datetime, timedelta

import pytest

from app.models import Lote, Piquete
from app.services import alertas as svc
from app.services import campo
from app.services import pastos

HOJE = date.today()


def _lote(db, nome):
    return db.query(Lote).filter(Lote.nome == nome).first()


def _tipos(r):
    return {(a["tipo"], a["alvo"]["id"]) for a in r["alertas"]}


def test_lote_passou_do_maximo_no_piquete(db):
    p = Piquete(nome="P1", hectares=10, ativo=True)
    db.add(p)
    db.commit()
    lote = _lote(db, "LOTEA")
    pastos.mover(db, lote.id, p.id, HOJE - timedelta(days=9))
    assert ("mudar_lote", lote.id) in _tipos(svc.alertas(db, HOJE))
    p.ocupacao_max_dias = 15  # limite do próprio piquete vence o padrão (7)
    db.commit()
    assert ("mudar_lote", lote.id) not in _tipos(svc.alertas(db, HOJE))


def test_piquete_pronto(db):
    p1 = Piquete(nome="P1", hectares=10, ativo=True, descanso_meta_dias=20)
    p2 = Piquete(nome="P2", hectares=10, ativo=True)
    db.add_all([p1, p2])
    db.commit()
    lote = _lote(db, "LOTEA")
    pastos.mover(db, lote.id, p1.id, HOJE - timedelta(days=30))
    pastos.mover(db, lote.id, p2.id, HOJE - timedelta(days=25))
    assert ("piquete_pronto", p1.id) in _tipos(svc.alertas(db, HOJE))


def test_salgar_so_para_quem_usa_o_controle_de_sal(db):
    a, b = _lote(db, "LOTEA"), _lote(db, "LOTEB")
    campo.salgar(db, a.id, "Sal mineral", 20, datetime.combine(HOJE - timedelta(days=10), datetime.min.time()))
    r = _tipos(svc.alertas(db, HOJE))
    assert ("salgar", a.id) in r and ("salgar", b.id) not in r


def test_pesar_quando_estimativa_velha(db):
    # Fixture: pesagens de jan/mai de 2026 → hoje bem mais de 120 dias sem pesar
    assert ("pesar", _lote(db, "LOTEA").id) in _tipos(svc.alertas(db, HOJE))


def test_limites_configuraveis(db):
    assert svc.carregar_limites(db) == {"ocupacao_max_dias": 7, "sal_dias": 7,
                                        "mortalidade_max_pct": 2, "pesados_min_pct": 80}
    svc.salvar_limites(db, {"ocupacao_max_dias": 10})
    assert svc.carregar_limites(db)["ocupacao_max_dias"] == 10
    with pytest.raises(ValueError):
        svc.salvar_limites(db, {"sal_dias": 0})
