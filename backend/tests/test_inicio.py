"""Testes da tela inicial: conta do ganho, comparação e separação da pecuária."""
from datetime import date

import pytest

from app.models import (
    Animal,
    AnimalLote,
    Compra,
    Lote,
    LotePiquete,
    Pesagem,
    Piquete,
    SessaoPesagem,
    StatusAnimal,
    StatusSessao,
    TipoSessao,
    Venda,
)
from app.models_financeiro import FinLancamento, FinParcela
from app.services import inicio as svc

HOJE = date(2026, 6, 30)


def _animal(db, brinco, tipo, pesos, status=StatusAnimal.ATIVO, lote=None, evento=None):
    a = Animal(brinco=brinco, tipo=tipo, status=status, data_evento=evento)
    db.add(a)
    db.flush()
    for d, p in pesos:
        db.add(Pesagem(animal_id=a.id, data=d, peso=p))
    if lote is not None:
        db.add(AnimalLote(animal_id=a.id, lote_id=lote.id, data_inicio=date(2025, 1, 1)))
    db.commit()
    return a


def _lancamento(db, tipo, setor, grupo, valor, vencimento, pago=None):
    lc = FinLancamento(tipo=tipo, setor=setor, grupo=grupo, data=vencimento, valor_total=valor,
                       excluido=False, fazenda="Água do Tigre")
    db.add(lc)
    db.flush()
    db.add(FinParcela(lancamento_id=lc.id, numero=1, vencimento=vencimento, valor=valor, pago=pago))
    db.commit()
    return lc


def test_gmd_pondera_pelos_dias_e_nao_faz_media_de_medias(db):
    # Fixture: 101 ganhou 100 kg em 120 dias (0,833 kg/dia); os outros têm uma pesagem só.
    # Um animal com só 10 dias de ganho alto não pode puxar a média como se valesse igual.
    _animal(db, "300", "Boi", [(date(2026, 3, 1), 300), (date(2026, 3, 11), 320)])  # 2 kg/dia, 10 dias
    r = svc.producao(db, HOJE, date(2026, 1, 1), HOJE, dono=True)
    assert r["kg"] == 120
    assert r["animal_dias"] == 130
    assert r["gmd"] == pytest.approx(120 / 130, abs=0.001)  # a média das médias daria 1,42


def test_intervalo_que_atravessa_o_periodo_conta_so_a_parte_de_dentro(db):
    _animal(db, "300", "Boi", [(date(2025, 12, 22), 300), (date(2026, 1, 11), 320)])  # 1 kg/dia, 20 dias
    r = svc.producao(db, date(2026, 1, 31), date(2026, 1, 1), date(2026, 1, 31), dono=True)
    # 11 dias do animal 300 + 30 dias do 101 (da fixture, 01/01 a 01/05, 0,833 kg/dia)
    assert r["animal_dias"] == 11 + 30
    assert r["kg"] == round(11 * 1 + 30 * (100 / 120))


def test_descarta_pesagem_repetida_e_ganho_impossivel(db):
    _animal(db, "300", "Boi", [(date(2026, 2, 1), 300), (date(2026, 2, 3), 310)])     # 2 dias: repesagem
    _animal(db, "301", "Boi", [(date(2026, 2, 1), 300), (date(2026, 3, 1), 900)])     # 21 kg/dia: digitação
    r = svc.producao(db, HOJE, date(2026, 1, 1), HOJE, dono=True)
    assert r["descartados"] == 2
    assert r["kg"] == 100  # só o 101 da fixture


def test_arroba_produzida_usa_rendimento_do_tipo_e_15_kg(db):
    _animal(db, "300", "Boi", [(date(2026, 2, 1), 300), (date(2026, 4, 1), 330)])  # 30 kg × 52% ÷ 15
    r = svc.producao(db, HOJE, date(2026, 2, 1), date(2026, 4, 1), dono=True)
    fixture = 60 * (100 / 120) * 0.50 / 15  # Novilha da fixture no mesmo intervalo
    assert r["arrobas"] == round(30 * 0.52 / 15 + fixture)


def test_compara_com_o_mesmo_periodo_do_ano_anterior(db):
    _animal(db, "300", "Boi", [(date(2025, 2, 1), 300), (date(2025, 4, 1), 359)])  # 1 kg/dia em 2025
    r = svc.producao(db, HOJE, date(2026, 2, 1), date(2026, 4, 1), dono=True)
    assert r["anterior"]["inicio"] == "2025-02-01"
    assert r["anterior"]["gmd"] == 1.0


def test_vendido_conta_na_producao_mas_nao_no_rebanho(db):
    _animal(db, "300", "Boi", [(date(2026, 2, 1), 300), (date(2026, 3, 1), 328)],
            status=StatusAnimal.VENDIDO, evento=date(2026, 3, 1))
    assert svc.rebanho(db, HOJE, dono=True)["cabecas"] == 3
    r = svc.producao(db, HOJE, date(2026, 2, 1), date(2026, 3, 1), dono=True)
    assert r["kg"] == round(28 + 29 * 100 / 120)  # 29 dias do 101 da fixture no mesmo período
    assert r["movimento"]["vendidos"] == 1


def test_mortalidade_e_rebanho_medio(db):
    _animal(db, "300", "Boi", [(date(2026, 1, 1), 300), (date(2026, 6, 30), 400)],
            status=StatusAnimal.MORTO, evento=date(2026, 6, 30))
    r = svc.producao(db, HOJE, date(2026, 1, 1), HOJE, dono=True)
    # Rebanho médio: (120 dias do 101 + 180 dias do 300) ÷ 181 dias do período
    assert r["mortalidade_pct"] == pytest.approx(1 / (300 / 181) * 100, abs=0.1)
    assert r["mortalidade_limite"] == 2


def test_peao_nao_recebe_compra_nem_venda(db):
    a = _animal(db, "300", "Boi", [(date(2026, 1, 1), 300)])
    db.add(Compra(animal_id=a.id, data=date(2026, 1, 1), valor=1000))
    db.add(Venda(animal_id=a.id, data=date(2026, 1, 1), preco_arroba=300, peso_carcaca=200, pendente=False))
    db.commit()
    prod = svc.producao(db, HOJE, None, None, dono=False)
    assert "preco_arroba" not in prod and "vendidos" not in prod["movimento"] and "comprados" not in prod["movimento"]
    reb = svc.rebanho(db, HOJE, dono=False)
    assert "valor_rebanho" not in reb and "preco_arroba_ref" not in reb


def test_rebanho_valor_e_categorias(db):
    a = _animal(db, "300", "Boi", [(date(2026, 6, 1), 450)])
    db.add(Venda(animal_id=a.id, data=date(2026, 6, 1), preco_arroba=300, peso_carcaca=240, pendente=False))
    db.commit()
    r = svc.rebanho(db, HOJE, dono=True)
    assert r["cabecas"] == 4
    assert sum(c["cabecas"] for c in r["categorias"]) == 4
    assert r["categorias"][0]["tipo"] == "Boi"  # maior em cima
    assert r["preco_arroba_ref"] == 300
    assert r["valor_rebanho"] == pytest.approx(r["arrobas"] * 300, abs=150)  # @ na tela é arredondada


def test_animal_sem_lote_e_sem_peso_ainda_e_contado(db):
    _animal(db, "300", None, [])
    r = svc.rebanho(db, HOJE, dono=True)
    assert r["cabecas"] == 4
    assert r["pesagem"]["sem_peso"] == 1
    assert any(c["tipo"] == svc.SEM_TIPO for c in r["categorias"])


def test_faixas_de_pesagem_e_lista_por_tras_do_numero(db):
    r = svc.rebanho(db, HOJE, dono=True)
    # Fixture: 101 pesado em 01/05 (60 dias); 102 e 201 em 01/01 (180 dias)
    assert r["pesagem"]["ate_60"] == 1 and r["pesagem"]["mais_120"] == 2
    assert r["pesagem"]["em_dia_pct"] == 33
    assert sorted(a["brinco"] for a in svc.animais_filtrados(db, HOJE, faixa="mais_120")) == ["102", "201"]
    assert [a["brinco"] for a in svc.animais_filtrados(db, HOJE, tipo="Vaca")] == ["201"]
    lote_a = db.query(Lote).filter_by(nome="LOTEA").one()
    assert sorted(a["brinco"] for a in svc.animais_filtrados(db, HOJE, lote=lote_a.id)) == ["101", "102"]


def test_lotacao_so_aparece_com_o_gado_quase_todo_no_mapa(db):
    lote_a = db.query(Lote).filter_by(nome="LOTEA").one()
    lote_b = db.query(Lote).filter_by(nome="LOTEB").one()
    pq = Piquete(nome="P1", hectares=10.0, ativo=True)
    db.add(pq)
    db.flush()
    db.add(LotePiquete(lote_id=lote_a.id, piquete_id=pq.id, data_entrada=date(2026, 6, 1)))
    db.commit()
    r = svc.rebanho(db, HOJE, dono=True)["lotacao"]
    assert r["ua_ha"] is None and r["cobertura_pct"] == 67 and r["lotes_sem_piquete"] == 1  # 2 de 3 cabeças
    db.add(LotePiquete(lote_id=lote_b.id, piquete_id=pq.id, data_entrada=date(2026, 6, 1)))
    db.commit()
    assert svc.rebanho(db, HOJE, dono=True)["lotacao"]["ua_ha"] is not None


def test_financeiro_separa_pecuaria_compra_e_custeio(db):
    d = date(2026, 3, 10)
    _lancamento(db, "receita", "Pecuária", "Venda de animais", 1000, d)
    _lancamento(db, "receita", "Sede", "Arrendamento", 9000, d)
    _lancamento(db, "despesa", "Pecuária", "Alimentos", 200, d)
    _lancamento(db, "despesa", "Pecuária", "Aquisição de rebanho", 500, d)
    _lancamento(db, "despesa", "Pecuária", "Investimentos", 50, d)
    _lancamento(db, "despesa", "Pessoal", "Gastos gerais", 700, d)
    r = svc.financeiro(db, HOJE, date(2026, 1, 1), HOJE)
    assert r["pecuaria"] == {"receita": 1000, "custeio": 200, "compra": 500, "investimentos": 50, "saldo": 250}
    setores = {s["setor"]: s for s in r["setores"]}
    assert setores["Pecuária"]["saldo"] == r["pecuaria"]["saldo"]  # a tabela bate com o cartão
    assert setores["Sede"]["receita"] == 9000
    mes = next(m for m in r["meses"] if m["mes"] == "2026-03")
    assert mes["compra"] == 500 and mes["custeio"] == 200


def test_custo_da_arroba_nao_inclui_compra_de_gado(db):
    d = date(2026, 3, 10)
    _lancamento(db, "despesa", "Pecuária", "Alimentos", 300, d)
    _lancamento(db, "despesa", "Pecuária", "Aquisição de rebanho", 99999, d)
    r = svc.financeiro(db, HOJE, date(2026, 1, 1), HOJE)
    # 100 kg × 50% ÷ 15 = 3,33 → 3 @ (Novilha da fixture)
    assert r["arrobas"] == 3
    assert r["custo_arroba"] == 100


def test_financeiro_so_conta_o_que_aconteceu_e_mostra_o_que_vem(db):
    _lancamento(db, "despesa", "Pecuária", "Alimentos", 100, date(2026, 6, 1), pago=False)  # vencida, a confirmar
    _lancamento(db, "despesa", "Pecuária", "Alimentos", 40, date(2026, 6, 10), pago=True)
    _lancamento(db, "despesa", "Pecuária", "Alimentos", 70, date(2026, 7, 15))              # a vencer em 15 dias
    _lancamento(db, "receita", "Pecuária", "Abate", 30, date(2026, 7, 20))
    _lancamento(db, "despesa", "Pecuária", "Alimentos", 500, date(2026, 12, 1))             # fora dos 30 dias
    r = svc.financeiro(db, HOJE, date(2026, 1, 1), HOJE)
    assert r["pecuaria"]["custeio"] == 40
    assert r["proximos_30"] == {"a_pagar": 70, "a_receber": 30}
    assert r["a_confirmar"] == 1 and r["a_confirmar_valor"] == 100


def test_lancamento_excluido_nao_entra(db):
    lc = _lancamento(db, "receita", "Pecuária", "Abate", 1000, date(2026, 3, 1))
    lc.excluido = True
    db.commit()
    assert svc.financeiro(db, HOJE, date(2026, 1, 1), HOJE)["pecuaria"]["receita"] == 0


def test_manejos_de_venda_sem_fechar_no_financeiro(db):
    db.add_all([
        SessaoPesagem(tipo=TipoSessao.VENDA_FAZENDA, data=date(2026, 3, 1), status=StatusSessao.FINALIZADA),
        SessaoPesagem(tipo=TipoSessao.MANEJO, data=date(2026, 3, 1), status=StatusSessao.FINALIZADA),
    ])
    db.commit()
    assert svc.financeiro(db, HOJE, None, None)["manejos_sem_fechar"] == 1


def test_serie_tem_12_meses_e_esconde_mes_sem_base(db):
    r = svc.producao(db, HOJE, None, None, dono=True)
    assert len(r["serie"]) == 12
    assert r["serie"][-1]["mes"] == "2026-06" and r["serie"][0]["mes"] == "2025-07"
    assert all(s["gmd"] is None for s in r["serie"])  # 1 animal não chega a 300 animal-dias/mês


def test_banco_vazio_nao_quebra(db):
    for modelo in (AnimalLote, Pesagem, Animal):
        db.query(modelo).delete()
    db.commit()
    assert svc.rebanho(db, HOJE, dono=True)["cabecas"] == 0
    p = svc.producao(db, HOJE, None, None, dono=True)
    assert p["gmd"] is None and p["mortalidade_pct"] is None
    f = svc.financeiro(db, HOJE, None, None)
    assert f["custo_arroba"] is None and f["margem_arroba"] is None


def test_29_de_fevereiro_nao_quebra_a_comparacao(db):
    r = svc.producao(db, date(2028, 2, 29), None, None, dono=True)
    assert r["anterior"]["fim"] == "2027-02-28"
