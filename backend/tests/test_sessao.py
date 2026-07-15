"""Testes da lógica da sessão de pesagem na mangueira."""
from datetime import date

import pytest

from app.models import Animal, Pesagem, SessaoPesagem, StatusAnimal, StatusSessao, TipoSessao
from app.services import sessao as svc
from app.services.consultas import lote_atual

HOJE = date(2026, 6, 15)


def _abrir_manejo(db, separar=True):
    return svc.criar_sessao(db, TipoSessao.MANEJO, HOJE, ["LOTEA"], separar,
                            ["Gordo", "Magro"] if separar else None)


def test_a_pesar_lista_animais_do_lote(db):
    s = _abrir_manejo(db, separar=False)
    est = svc.estado_sessao(db, s)
    brincos = {a["brinco"] for a in est["a_pesar"]}
    assert brincos == {"101", "102"}  # só os do LOTEA


def test_pesar_grava_ordem_e_destino(db):
    s = _abrir_manejo(db)
    svc.registrar_pesagem(db, s, "101", 410, destino_lote="Gordo")
    svc.registrar_pesagem(db, s, "102", 330, destino_lote="Magro")
    est = svc.estado_sessao(db, s)
    assert est["contadores"]["pesados"] == 2
    assert est["contadores"]["por_sublote"] == {"Gordo": 1, "Magro": 1}
    ordens = {p["brinco"]: p["ordem"] for p in est["pesados"]}
    assert ordens == {"101": 1, "102": 2}


def test_pesar_nao_pula_numero_apos_apagar(db):
    s = _abrir_manejo(db)
    svc.registrar_pesagem(db, s, "101", 410, destino_lote="Gordo")
    r2 = svc.registrar_pesagem(db, s, "102", 330, destino_lote="Magro")
    r3 = svc.registrar_pesagem(db, s, "103", 350, destino_lote="Gordo",
                               criar_animal=True, tipo="Boi")
    assert r3["ordem"] == 3
    # Apaga o do meio (corrige um lançamento errado) e pesa mais um.
    svc.remover_pesagem(db, s, r2["pesagem_id"])
    r4 = svc.registrar_pesagem(db, s, "104", 360, destino_lote="Magro",
                               criar_animal=True, tipo="Boi")
    # A numeração exibida (posição na lista) não deve pular nenhum número.
    assert r4["ordem"] == 3
    est = svc.estado_sessao(db, s)
    assert sorted(p["ordem"] for p in est["pesados"]) == [1, 2, 3]


def test_alerta_ja_pesado(db):
    s = _abrir_manejo(db)
    svc.registrar_pesagem(db, s, "101", 410, destino_lote="Gordo")
    r = svc.registrar_pesagem(db, s, "101", 415)
    assert r["alerta"] == "ja_pesado"
    # Com forçar, atualiza o peso.
    r2 = svc.registrar_pesagem(db, s, "101", 415, forcar=True)
    assert r2["ok"] and r2["peso"] == 415


def test_cancela_sessao_sem_pesagens(db):
    s = _abrir_manejo(db)
    sessao_id = s.id
    svc.cancelar_sessao(db, s)
    assert db.get(SessaoPesagem, sessao_id) is None


def test_nao_cancela_sessao_com_pesagem(db):
    s = _abrir_manejo(db)
    svc.registrar_pesagem(db, s, "101", 410, destino_lote="Gordo")
    with pytest.raises(ValueError, match="já tem pesagens"):
        svc.cancelar_sessao(db, s)


def test_alerta_fora_do_lote(db):
    s = _abrir_manejo(db)
    r = svc.registrar_pesagem(db, s, "201", 450)  # 201 está no LOTEB
    assert r["alerta"] == "fora_do_lote"


def test_brinco_duplicado_pede_escolha(db):
    # Cria um segundo animal "101" no mesmo lote (brinco repetido).
    from app.models import AnimalLote
    lote_a = db.query(Animal).filter(Animal.brinco == "101").first().lotes[0].lote
    dup = Animal(brinco="101", tipo="Boi", status=StatusAnimal.ATIVO)
    db.add(dup)
    db.flush()
    db.add(AnimalLote(animal_id=dup.id, lote_id=lote_a.id, data_inicio=HOJE))
    db.commit()

    r = svc.registrar_pesagem(db, s := _abrir_manejo(db), "101", 400)
    assert r["alerta"] == "ambiguo"
    assert len(r["candidatos"]) == 2
    # Escolhendo um id específico, registra naquele animal.
    escolhido = r["candidatos"][1]["animal_id"]
    r2 = svc.registrar_pesagem(db, s, "101", 400, animal_id=escolhido)
    assert r2["ok"]
    p = db.query(Pesagem).filter(Pesagem.animal_id == escolhido, Pesagem.data == HOJE).first()
    assert p is not None and p.peso == 400


def test_pesagem_edita_tipo_raca_e_dentes(db):
    from app.models import Denticao
    s = _abrir_manejo(db)
    r = svc.registrar_pesagem(db, s, "101", 410, destino_lote="Gordo",
                              novo_tipo="Vaca", nova_raca="Nelore", dentes=4)
    assert r["ok"]
    a = db.query(Animal).filter(Animal.brinco == "101").first()
    assert a.tipo == "Vaca" and a.raca == "Nelore"
    d = db.query(Denticao).filter(Denticao.animal_id == a.id).first()
    assert d is not None and d.dentes == 4


def test_cadastro_rapido_inexistente(db):
    s = _abrir_manejo(db)
    assert svc.registrar_pesagem(db, s, "999", 300).get("alerta") == "inexistente"
    r = svc.registrar_pesagem(db, s, "999", 300, criar_animal=True, tipo="Boi",
                              destino_lote="Gordo")
    assert r["ok"]
    assert db.query(Animal).filter(Animal.brinco == "999").count() == 1


def test_sem_brinco_e_vinculo_herda_historico(db):
    s = _abrir_manejo(db)
    sb = svc.pesar_sem_brinco(db, s, 280, destino_lote="Magro")
    temp = db.query(Animal).filter(Animal.brinco == sb["brinco"]).first()
    faltante = db.query(Animal).filter(Animal.brinco == "101").first()
    qtd_antes = len(faltante.pesagens)
    svc.vincular(db, s.data, temp.id, faltante.id)
    db.refresh(faltante)
    assert len(faltante.pesagens) == qtd_antes + 1   # herdou a pesagem
    assert db.query(Animal).filter(Animal.brinco == sb["brinco"]).count() == 0  # provisório removido


def test_vincular_cadastro_brinco_novo_adota_numero(db):
    # Boi chega sem brinco, recebe um brinco novo (5001) e é cadastrado na hora.
    s = _abrir_manejo(db)
    svc.registrar_pesagem(db, s, "5001", 300, criar_animal=True, tipo="Boi", destino_lote="Gordo")
    # O animal novo aparece como candidato a vínculo (não só os "sem brinco").
    prov = svc.pesados_provisorios(db, s)
    assert any(p["brinco"] == "5001" for p in prov)

    temp = db.query(Animal).filter(Animal.brinco == "5001").first()
    faltante = db.query(Animal).filter(Animal.brinco == "101").first()
    svc.vincular(db, s.data, temp.id, faltante.id)
    db.refresh(faltante)
    # O animal antigo passa a usar o brinco novo e guarda o antigo no histórico.
    assert faltante.brinco == "5001"
    assert any(h.brinco_antigo == "101" for h in faltante.historico_brincos)


def test_vincular_sem_brinco_definindo_brinco_novo(db):
    s = _abrir_manejo(db)
    svc.pesar_sem_brinco(db, s, 280, destino_lote="Magro")
    temp = db.query(Animal).filter(Animal.sem_brinco.is_(True)).first()
    faltante = db.query(Animal).filter(Animal.brinco == "101").first()
    # Informa o brinco novo na hora de vincular.
    svc.vincular(db, s.data, temp.id, faltante.id, novo_brinco="9001")
    db.refresh(faltante)
    assert faltante.brinco == "9001"


def test_compra_pede_cadastro_e_calcula_valor(db):
    s = svc.criar_sessao(db, TipoSessao.COMPRA, HOJE, [], True, sublotes=["Novos"],
                         preco_kg=11.5)
    # Sem criar_animal, compra pede o cadastro (tipo/raça).
    r = svc.registrar_pesagem(db, s, "7001", 300)
    assert r["alerta"] == "compra_novo"
    # Com o cadastro, cria o animal novo (tipo/raça) e calcula o valor.
    r2 = svc.registrar_pesagem(db, s, "7001", 300, criar_animal=True,
                               novo_tipo="Boi", nova_raca="Nelore")
    assert r2["ok"]
    a = db.query(Animal).filter(Animal.brinco == "7001").first()
    assert a.tipo == "Boi" and a.raca == "Nelore"
    assert a.compra.valor == 300 * 11.5


def test_compra_avisa_brinco_ja_existente(db):
    # Já existe o brinco 101 no fixture; comprar outro 101 deve só avisar.
    s = svc.criar_sessao(db, TipoSessao.COMPRA, HOJE, [], True, sublotes=["Novos"])
    r = svc.registrar_pesagem(db, s, "101", 320)
    assert r["alerta"] == "compra_novo" and r["ja_existe"] >= 1
    r2 = svc.registrar_pesagem(db, s, "101", 320, criar_animal=True, novo_tipo="Vaca")
    assert r2["ok"]
    # Passou a existir mais de um animal com brinco 101.
    assert db.query(Animal).filter(Animal.brinco == "101").count() == 2


def test_venda_fazenda_valor_e_status(db):
    s = svc.criar_sessao(db, TipoSessao.VENDA_FAZENDA, HOJE, ["LOTEA"], False, preco_arroba=300)
    svc.registrar_pesagem(db, s, "102", 500, forcar=True)  # Boi 52%
    a = db.query(Animal).filter(Animal.brinco == "102").first()
    # 500 * 0.52 / 15 * 300 = 5200
    assert a.venda.valor_recebido == 5200.0
    assert a.status == StatusAnimal.VENDIDO


def test_venda_morto_pendente_e_fechamento(db):
    s = svc.criar_sessao(db, TipoSessao.VENDA_MORTO, HOJE, ["LOTEA"], False)
    svc.registrar_pesagem(db, s, "102", 500, forcar=True)
    a = db.query(Animal).filter(Animal.brinco == "102").first()
    assert a.venda.pendente is True
    svc.completar_venda_morto(db, a, rendimento=0.52, peso_carcaca=250, preco_arroba=330)
    # 250 / 15 * 330 = 5500
    assert a.venda.valor_recebido == 5500.0
    assert a.venda.pendente is False


def test_finalizar_move_para_sublote(db):
    s = _abrir_manejo(db)
    svc.registrar_pesagem(db, s, "101", 410, destino_lote="Gordo")
    svc.finalizar(db, s)
    a = db.query(Animal).filter(Animal.brinco == "101").first()
    assert lote_atual(a) == "Gordo"


def test_faltantes_traz_peso_e_ordena_do_mais_pesado(db):
    s = _abrir_manejo(db, separar=False)
    d = svc.faltantes(db, s)
    # 101 (400 kg) e 102 (320 kg) — nenhum foi pesado ainda nesta sessão.
    assert [f["brinco"] for f in d] == ["101", "102"]
    assert [f["ultimo_peso"] for f in d] == [400, 320]
    assert d[0]["tipo"] == "Novilha"
    assert "raca" in d[0]


def test_reabrir_permite_lancar_animal_esquecido(db):
    s = _abrir_manejo(db)
    svc.registrar_pesagem(db, s, "101", 410, destino_lote="Gordo")
    svc.finalizar(db, s)
    assert s.status == StatusSessao.FINALIZADA

    svc.reabrir(db, s)
    assert s.status == StatusSessao.ABERTA

    # Lança o animal esquecido (102) na sessão reaberta.
    r = svc.registrar_pesagem(db, s, "102", 330, destino_lote="Gordo")
    assert r["ok"]

    svc.finalizar(db, s)
    assert s.status == StatusSessao.FINALIZADA
    a = db.query(Animal).filter(Animal.brinco == "102").first()
    assert lote_atual(a) == "Gordo"
    # O 101 (já movido antes) continua no lote certo, sem duplicar histórico.
    a101 = db.query(Animal).filter(Animal.brinco == "101").first()
    assert lote_atual(a101) == "Gordo"
    assert len([al for al in a101.lotes if al.lote.nome == "Gordo"]) == 1


def test_lotes_somente_ativos(db):
    from app.routers.api import listar_lotes

    # No início: LOTEA (2 ativos) e LOTEB (1 ativo).
    nomes = {l["nome"]: l["ativos"] for l in listar_lotes(somente_ativos=True, db=db)}
    assert nomes == {"LOTEA": 2, "LOTEB": 1}

    # Vende os 2 do LOTEA -> o lote some da lista de pesagem.
    for b in ("101", "102"):
        db.query(Animal).filter(Animal.brinco == b).first().status = StatusAnimal.VENDIDO
    db.commit()
    nomes = {l["nome"]: l["ativos"] for l in listar_lotes(somente_ativos=True, db=db)}
    assert nomes == {"LOTEB": 1}
