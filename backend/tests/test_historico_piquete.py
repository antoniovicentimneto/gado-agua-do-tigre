"""Testes do histórico dos piquetes: peso estimado, foto da ocupação, pasto por período,
proteção do contorno e divisão de piquete."""
from datetime import date, timedelta

import pytest

from app.models import Animal, Lote, LotePiquete, Pesagem, Piquete
from app.services import pastos as svc
from app.services import pastos_historico as hist
from app.services import peso_estimado as pe

QUADRADO = {"type": "Polygon", "coordinates": [[[0, 0], [0.002, 0], [0.002, 0.002], [0, 0.002], [0, 0]]]}
METADE_A = {"type": "Polygon", "coordinates": [[[0, 0], [0.001, 0], [0.001, 0.002], [0, 0.002], [0, 0]]]}
METADE_B = {"type": "Polygon", "coordinates": [[[0.001, 0], [0.002, 0], [0.002, 0.002], [0.001, 0.002], [0.001, 0]]]}
HOJE = date.today()


def _lote(db, nome):
    return db.query(Lote).filter(Lote.nome == nome).first()


def _piquete(db, nome="P1", geometria=QUADRADO):
    r = svc.salvar_piquete(db, {"nome": nome, "geometria": geometria})
    return db.get(Piquete, r["id"])


# ---------------------------------------------------------------- Peso estimado

REF = [{"nome": "Águas", "inicio": 10, "fim": 3, "gmd": 0.5},
       {"nome": "Seca", "inicio": 4, "fim": 9, "gmd": 0.2}]


def test_estima_com_gmd_do_lote():
    d0 = date(2026, 1, 1)
    pesos = {1: {d0: 300, d0 + timedelta(days=100): 400},   # ugmd 1,0
             2: {d0: 300, d0 + timedelta(days=100): 360}}   # ugmd 0,6 → lote 0,8
    r = pe.resumo_grupo([1, 2], pesos, d0 + timedelta(days=130), REF)
    assert r["gmd_lote"] == 0.8 and r["fonte"] == "lote"
    assert r["peso_real"] == 760
    assert r["peso"] == pytest.approx(760 + 2 * 0.8 * 30)
    assert r["n_estimados"] == 2 and not r["velha"]


def test_sem_gmd_usa_referencia_da_epoca():
    compra = date(2026, 7, 1)  # julho = seca (0,2)
    r = pe.resumo_grupo([1], {1: {compra: 250}}, compra + timedelta(days=10), REF)
    assert r["fonte"].startswith("referência (Seca)")
    assert r["peso"] == pytest.approx(252)


def test_projecao_limitada_e_marcada_como_velha():
    d0 = date(2026, 1, 1)
    r = pe.resumo_grupo([1], {1: {d0: 300, d0 + timedelta(days=10): 310}}, d0 + timedelta(days=310), REF)
    assert r["peso"] == pytest.approx(310 + 1.0 * pe.LIMITE_DIAS)
    assert r["velha"]


def test_pesado_hoje_nao_e_estimado():
    r = pe.resumo_grupo([1], {1: {HOJE: 400}}, HOJE, REF)
    assert r["peso"] == 400 and r["n_estimados"] == 0


def test_salvar_referencia_valida_meses(db):
    assert pe.carregar_referencia(db) == pe.REFERENCIA_PADRAO
    with pytest.raises(ValueError):  # falta mês
        pe.salvar_referencia(db, [{"nome": "Águas", "inicio": 10, "fim": 3, "gmd": 0.5}])
    with pytest.raises(ValueError):  # mês repetido
        pe.salvar_referencia(db, REF + [{"nome": "Azevém", "inicio": 6, "fim": 8, "gmd": 0.8}])
    nova = [{"nome": "Águas", "inicio": 10, "fim": 3, "gmd": "0,6"},
            {"nome": "Seca", "inicio": 4, "fim": 9, "gmd": 0.15}]
    pe.salvar_referencia(db, nova)
    assert pe.carregar_referencia(db)[0]["gmd"] == 0.6


# ---------------------------------------------------------------- Foto da ocupação

def test_foto_na_entrada_e_na_saida(db):
    p1, p2 = _piquete(db, "P1"), _piquete(db, "P2", METADE_A)
    lote = _lote(db, "LOTEA")
    # Pesa os dois animais hoje pra foto não depender de estimativa.
    for a in db.query(Animal).filter(Animal.brinco.in_(["101", "102"])):
        db.add(Pesagem(animal_id=a.id, data=HOJE - timedelta(days=10), peso=450))
    db.commit()
    svc.mover(db, lote.id, p1.id, HOJE - timedelta(days=10))
    svc.mover(db, lote.id, p2.id, HOJE)
    lp = db.query(LotePiquete).filter(LotePiquete.piquete_id == p1.id).one()
    assert lp.hectares == p1.hectares and lp.cabecas == 2
    assert lp.peso_entrada == 900 and lp.entrada_estimada is False
    assert lp.cabecas_saida == 2 and lp.saida_estimada is True and lp.peso_saida > 900
    h = hist.historico(db, p1.id)
    o = h["ocupacoes"][0]
    assert o["ua_entrada"] == 2.0 and o["dias"] == 10 and o["gmd_periodo"] is not None


def test_desfazer_limpa_a_foto_da_saida(db):
    p1, p2 = _piquete(db, "P1"), _piquete(db, "P2", METADE_A)
    lote = _lote(db, "LOTEA")
    svc.mover(db, lote.id, p1.id, HOJE - timedelta(days=3))
    r = svc.mover(db, lote.id, p2.id, HOJE)
    svc.desfazer(db, r["movimentacao"]["id"])
    lp = db.query(LotePiquete).filter(LotePiquete.piquete_id == p1.id).one()
    assert lp.data_saida is None and lp.peso_saida is None and lp.cabecas_saida is None


# ---------------------------------------------------------------- Pasto por período

def test_trocar_pasto_e_sobressemeadura(db):
    p = _piquete(db)
    hist.adicionar_pasto(db, p.id, "Tifton 85", HOJE - timedelta(days=200))
    hist.adicionar_pasto(db, p.id, "Azevém", HOJE - timedelta(days=30), substitui=False)
    assert db.get(Piquete, p.id).capim == "Tifton 85 + Azevém"
    hist.adicionar_pasto(db, p.id, "Estrela", HOJE)  # reforma: encerra os dois
    pers = hist.periodos(db, p.id)
    assert [x["especie"] for x in pers if x["fim"] is None] == ["Estrela"]
    assert db.get(Piquete, p.id).capim == "Estrela"
    with pytest.raises(svc.ErroPasto):  # troca antes do pasto atual começar
        hist.adicionar_pasto(db, p.id, "Marandu", HOJE - timedelta(days=5))


def test_apagar_pasto_lancado_errado_reabre_o_anterior(db):
    p = _piquete(db)
    hist.adicionar_pasto(db, p.id, "Marandu", HOJE - timedelta(days=100))
    errado = hist.adicionar_pasto(db, p.id, "Mombaça", HOJE)
    hist.apagar_pasto(db, errado["id"])
    assert db.get(Piquete, p.id).capim == "Marandu"


def test_piquete_novo_com_capim_abre_periodo(db):
    r = svc.salvar_piquete(db, {"nome": "PX", "geometria": QUADRADO, "capim": "Piatã"})
    assert [x["especie"] for x in hist.periodos(db, r["id"])] == ["Piatã"]


def test_migra_capim_antigo(db):
    p = Piquete(nome="Velho", capim="Humidícola", ativo=True)
    db.add(p)
    db.commit()
    assert hist.migrar_capim_para_periodos(db) == 1
    assert hist.migrar_capim_para_periodos(db) == 0  # idempotente
    assert hist.periodos(db, p.id)[0]["especie"] == "Humidícola"


def test_historico_mostra_pasto_de_cada_ocupacao(db):
    p = _piquete(db)
    hist.adicionar_pasto(db, p.id, "Marandu", HOJE - timedelta(days=100))
    svc.mover(db, _lote(db, "LOTEA").id, p.id, HOJE - timedelta(days=50))
    hist.adicionar_pasto(db, p.id, "Tifton 85", HOJE - timedelta(days=10))
    assert hist.historico(db, p.id)["ocupacoes"][0]["pasto"] == "Marandu"


# ---------------------------------------------------------------- Proteção do contorno

def test_redesenhar_piquete_com_historico_exige_confirmacao(db):
    p = _piquete(db)
    svc.mover(db, _lote(db, "LOTEA").id, p.id)
    with pytest.raises(svc.ErroPasto):
        svc.salvar_piquete(db, {"nome": p.nome, "geometria": METADE_A}, p.id)
    with pytest.raises(svc.ErroPasto):
        svc.salvar_piquete(db, {"nome": p.nome, "hectares": 1.5}, p.id)
    # Nome/observação podem mudar à vontade.
    svc.salvar_piquete(db, {"nome": "P1 novo", "observacao": "cerca nova"}, p.id)
    # Correção explícita (desenho errado desde o início) passa.
    r = svc.salvar_piquete(db, {"nome": "P1 novo", "geometria": METADE_A, "corrigir": True}, p.id)
    assert r["hectares"] < 5


def test_reimportar_nao_muda_piquete_com_historico(db):
    p = _piquete(db, "Piquete 1")
    svc.mover(db, _lote(db, "LOTEA").id, p.id)
    r = svc.importar(db, [{"nome": "Piquete 1", "area": None, "geometria": METADE_A, "hectares": 1.0}],
                     None, None, svc.TipoArea.PROPRIA)
    assert r["protegidos"] == ["Piquete 1"] and db.get(Piquete, p.id).hectares != 1.0


def test_remover_piquete_com_historico_libera_o_nome(db):
    p = _piquete(db, "P9")
    lote = _lote(db, "LOTEA")
    svc.mover(db, lote.id, p.id, HOJE - timedelta(days=5))
    p2 = _piquete(db, "P10", METADE_A)
    svc.mover(db, lote.id, p2.id)
    svc.remover_piquete(db, p.id)
    assert db.get(Piquete, p.id).nome.startswith("P9 (até ")
    assert _piquete(db, "P9").ativo  # nome livre de novo


# ---------------------------------------------------------------- Dividir

def test_dividir_preserva_o_passado_e_leva_o_gado(db):
    p = _piquete(db, "Grande")
    hist.adicionar_pasto(db, p.id, "Tifton 85", HOJE - timedelta(days=100))
    area_original = p.hectares
    lote = _lote(db, "LOTEA")
    svc.mover(db, lote.id, p.id, HOJE - timedelta(days=20))
    r = hist.dividir(db, p.id, [{"nome": "Grande A", "geometria": METADE_A},
                                {"nome": "Grande B", "geometria": METADE_B}],
                     HOJE, {lote.id: 1})
    a, b = (db.get(Piquete, x["id"]) for x in r["novos"])
    original = db.get(Piquete, p.id)
    assert not original.ativo and original.nome.startswith("Grande (até ")
    assert original.hectares == area_original                    # passado com a área antiga
    assert a.origem_id == b.origem_id == original.id
    assert a.hectares + b.hectares == pytest.approx(area_original, abs=0.05)
    assert a.capim == b.capim == "Tifton 85"                       # pasto herdado
    # Ocupação antiga fechada no original (com a área de antes); gado agora na parte B.
    velha = db.query(LotePiquete).filter(LotePiquete.piquete_id == original.id).one()
    assert velha.data_saida == HOJE and velha.hectares == area_original
    nova = db.query(LotePiquete).filter(LotePiquete.piquete_id == b.id).one()
    assert nova.data_saida is None and nova.hectares == b.hectares
    h = hist.historico(db, b.id)
    assert h["origem"]["id"] == original.id
    assert [x["id"] for x in hist.historico(db, original.id)["partes"]] == [a.id, b.id]


def test_dividir_exige_destino_do_gado_e_nomes(db):
    p = _piquete(db, "Grande")
    lote = _lote(db, "LOTEA")
    svc.mover(db, lote.id, p.id, HOJE - timedelta(days=2))
    partes = [{"nome": "A", "geometria": METADE_A}, {"nome": "B", "geometria": METADE_B}]
    with pytest.raises(svc.ErroPasto):
        hist.dividir(db, p.id, partes, HOJE, {})                   # sem destino do lote
    with pytest.raises(svc.ErroPasto):
        hist.dividir(db, p.id, partes[:1], HOJE, {lote.id: 0})     # uma parte só
    with pytest.raises(svc.ErroPasto):
        hist.dividir(db, p.id, [{"nome": "A", "geometria": METADE_A}, {"nome": "a", "geometria": METADE_B}],
                     HOJE, {lote.id: 0})                           # nomes iguais


def test_divisao_nao_se_desfaz_pelo_botao(db):
    p = _piquete(db, "Grande")
    hist.dividir(db, p.id, [{"nome": "A", "geometria": METADE_A}, {"nome": "B", "geometria": METADE_B}], HOJE)
    mov = svc.movimentacoes_recentes(db)[0]
    assert mov["tipo"] == "dividir"
    with pytest.raises(svc.ErroPasto):
        svc.desfazer(db, mov["id"])



# ---------------------------------------------------------------- Uso da área e pastagem na importação

def test_importar_com_pastagem_e_uso(db):
    linhas = [{"nome": "T1", "area": None, "geometria": METADE_A, "hectares": 1.0, "pasto": "Azevém"},
              {"nome": "T2", "area": None, "geometria": METADE_B, "hectares": 1.0}]
    svc.importar(db, linhas, None, "Sede", svc.TipoArea.PROPRIA, pasto_padrao="Tifton 85",
                 uso_padrao="inverno")
    t1 = db.query(Piquete).filter(Piquete.nome == "T1").one()
    t2 = db.query(Piquete).filter(Piquete.nome == "T2").one()
    assert t1.capim == "Azevém" and t2.capim == "Tifton 85"   # linha vence o padrão
    assert t1.uso == t2.uso == "inverno"
    assert hist.periodos(db, t1.id)[0]["especie"] == "Azevém"


def test_uso_invalido_da_erro(db):
    with pytest.raises(svc.ErroPasto):
        svc.salvar_piquete(db, {"nome": "X", "geometria": QUADRADO, "uso": "soja"})
    r = svc.salvar_piquete(db, {"nome": "X", "geometria": QUADRADO, "uso": "perene"})
    assert db.get(Piquete, r["id"]).uso == "perene"
