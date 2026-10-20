"""Fechamento de venda/compra de gado no Financeiro."""
from datetime import date

import pytest
from sqlalchemy import select

from app.models import TipoSessao
from app.models_financeiro import FinFechamento, FinLancamento
from app.services import fin_fechamento as svc
from app.services import fin_plano
from app.services import sessao as svc_sessao
from app.services.fin_plano import ErroFinanceiro

HOJE = date(2026, 10, 20)


def _venda(db):
    fin_plano.garantir_cadastros(db)
    s = svc_sessao.criar_sessao(db, TipoSessao.VENDA_FAZENDA, HOJE, ["LOTEA"], False, preco_arroba=300)
    svc_sessao.registrar_pesagem(db, s, "101", 400, forcar=True)  # Novilha 50%: 400×0,5÷15×300 = 4000
    svc_sessao.registrar_pesagem(db, s, "102", 500, forcar=True)  # Boi 52%: 5200
    return s


def _ativos(db, f_id):
    return db.scalars(select(FinLancamento).where(FinLancamento.fechamento_id == f_id,
                                                  FinLancamento.excluido.is_(False))).all()


def test_resumo_traz_os_numeros_da_mangueira(db):
    s = _venda(db)
    r = svc.resumo(db, s.id)
    m = r["manejo"]
    assert m["tipo"] == "venda" and m["cabecas"] == 2 and m["valor_bruto"] == 9200
    assert m["arrobas"] == pytest.approx(30.67, abs=0.01)
    assert m["grupo"] == "Venda de animais" and m["categoria"] in ("Novilha 1 ano", "Boi")
    assert r["fechamento"] is None and r["descontos_padrao"][0]["chave"] == "funrural"


def test_fechar_venda_lanca_receita_bruta_e_descontos(db):
    s = _venda(db)
    f = svc.salvar(db, s.id, {
        "valor_bruto": "9200", "contraparte": "Frigorífico Tibagi", "categoria": "Novilha 1 ano",
        "vencimento": "2026-11-19",
        "descontos": [
            {"chave": "funrural", "nome": "Funrural", "valor": "119,60", "descontado": True},
            {"chave": "senar", "nome": "SENAR", "valor": 18.4, "descontado": True},
            {"chave": "frete", "nome": "Frete", "valor": 0},  # zerado: não entra
        ]}, "Antonio")
    assert f["valor_liquido"] == 9062.0
    lancs = _ativos(db, f["id"])
    receita = [lc for lc in lancs if lc.tipo == "receita"]
    despesas = [lc for lc in lancs if lc.tipo == "despesa"]
    assert len(receita) == 1 and receita[0].valor_total == 9200
    assert receita[0].setor == "Pecuária" and receita[0].grupo == "Venda de animais"
    assert receita[0].fornecedor_nome == "Frigorífico Tibagi" and not receita[0].revisar
    assert sorted(lc.valor_total for lc in despesas) == [18.4, 119.6]
    assert all(lc.parcelas[0].vencimento == date(2026, 11, 19) for lc in despesas)
    assert all(lc.categoria == "Funrural, pis, cofins, iss, csll, darf" for lc in despesas)
    assert all(lc.fornecedor_id is None for lc in despesas)  # não "ensina" o comprador como imposto


def test_refazer_exclui_os_lancamentos_antigos(db):
    s = _venda(db)
    svc.salvar(db, s.id, {"valor_bruto": 9200, "descontos": [{"chave": "funrural", "valor": 100}]}, "Antonio")
    f = svc.salvar(db, s.id, {"valor_bruto": 9300, "descontos": [{"chave": "frete", "nome": "Frete", "valor": 50}]},
                   "Letícia")
    assert db.scalars(select(FinFechamento)).all().__len__() == 1
    ativos = _ativos(db, f["id"])
    assert sorted(lc.valor_total for lc in ativos) == [50, 9300]
    excluidos = db.scalars(select(FinLancamento).where(FinLancamento.excluido.is_(True))).all()
    assert len(excluidos) == 2 and all("refeito" in lc.excluido_motivo for lc in excluidos)
    frete = [lc for lc in ativos if lc.tipo == "despesa"][0]
    assert frete.grupo == "Comercialização" and frete.categoria == "Frete"


def test_desfazer_tira_do_financeiro(db):
    s = _venda(db)
    svc.salvar(db, s.id, {"valor_bruto": 9200}, "Antonio")
    svc.desfazer(db, s.id, "Antonio")
    assert svc.resumo(db, s.id)["fechamento"] is None
    assert all(lc.excluido for lc in db.scalars(select(FinLancamento)))


def test_compra_soma_custos_extras(db):
    fin_plano.garantir_cadastros(db)
    s = svc_sessao.criar_sessao(db, TipoSessao.COMPRA, HOJE, [], False, preco_kg=12, vendedor="João")
    svc_sessao.registrar_pesagem(db, s, "900", 250, forcar=True, criar_animal=True, novo_tipo="Novilha",
                                 nova_raca="Angus")
    r = svc.resumo(db, s.id)["manejo"]
    assert r["tipo"] == "compra" and r["valor_bruto"] == 3000
    f = svc.salvar(db, s.id, {"valor_bruto": 3000, "descontos": [{"chave": "frete", "nome": "Frete", "valor": 200}]},
                   "Antonio")
    assert f["valor_liquido"] == 3200 and f["contraparte"] == "João"
    principal = [lc for lc in _ativos(db, f["id"]) if lc.valor_total == 3000][0]
    assert principal.tipo == "despesa" and principal.grupo == "Aquisição de rebanho" and principal.categoria == "Bovinos"


def test_regras(db):
    s = _venda(db)
    with pytest.raises(ErroFinanceiro):
        svc.salvar(db, s.id, {"valor_bruto": 0}, "Antonio")
    with pytest.raises(ErroFinanceiro):
        svc.salvar(db, s.id, {"valor_bruto": 100, "descontos": [{"chave": "frete", "valor": 100}]}, "Antonio")
    m = svc_sessao.criar_sessao(db, TipoSessao.MANEJO, HOJE, ["LOTEA"], False)
    with pytest.raises(ErroFinanceiro):
        svc.resumo(db, m.id)
