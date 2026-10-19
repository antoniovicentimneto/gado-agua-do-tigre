"""Testes de solo: análise (SB, CTC, V%), calagem e aplicação de insumos."""
import pytest

from app.models import Piquete
from app.services import solo as svc


def _p(db, ha=10.0):
    p = Piquete(nome="P1", hectares=ha, ativo=True)
    db.add(p)
    db.commit()
    return p


def test_analise_calcula_sb_ctc_e_v(db):
    p = _p(db)
    a = svc.salvar_analise(db, p.id, {"data": "2026-09-01", "ph_cacl2": "4,8", "ca": "2,0", "mg": "0,8",
                                      "k": "0,2", "h_al": "5,0", "al": "0,3", "p": "4"})
    assert a["sb"] == 3.0 and a["ctc"] == 8.0 and a["v_pct"] == 37.5
    assert a["m_pct"] == pytest.approx(0.3 / 3.3 * 100, abs=0.1)
    assert svc.resumo_solo(db)[0]["v_pct"] == 37.5


def test_calagem_saturacao_por_bases():
    # (60 − 37,5) × 8 ÷ 80 = 2,25 t/ha
    assert svc.necessidade_calagem(37.5, 8.0, 60, 80) == 2.25
    assert svc.necessidade_calagem(70, 8.0, 60, 80) == 0  # já está acima
    with pytest.raises(svc.ErroSolo):
        svc.necessidade_calagem(37.5, 8.0, 60, 0)


def test_analise_valida(db):
    p = _p(db)
    with pytest.raises(svc.ErroSolo):
        svc.salvar_analise(db, p.id, {"ph_cacl2": "15"})
    with pytest.raises(svc.ErroSolo):
        svc.salvar_analise(db, p.id, {"ca": "abc"})


def test_aplicacao_de_insumo(db):
    p = _p(db, 12)
    x = svc.registrar_aplicacao(db, p.id, {"data": "2026-09-10", "tipo": "calcario",
                                           "produto": "Calcário dolomítico PRNT 80", "dose": "2,5",
                                           "unidade": "t/ha", "custo_total": "4500"}, "Antonio")
    assert x["area_ha"] == 12 and x["quantidade_total"] == 30 and x["custo_ha"] == 375
    s = svc.solo_do_piquete(db, p.id)
    assert s["custo_total"] == 4500 and s["aplicacoes"][0]["tipo_nome"] == "Calcário"
    with pytest.raises(svc.ErroSolo):
        svc.registrar_aplicacao(db, p.id, {"tipo": "foguete", "produto": "x", "dose": 1})
    with pytest.raises(svc.ErroSolo):
        svc.registrar_aplicacao(db, p.id, {"tipo": "adubo", "produto": "Ureia"})  # sem dose
