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
    # Cada animal traz o último peso pra mostrar na lista.
    assert all("ultimo_peso" in a for a in est["a_pesar"])


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


def test_brinco_duplicado_com_vendido_nao_conta_como_ambiguo(db):
    # Segundo animal "101", mas VENDIDO — não pode ser candidato (nem pesado).
    from app.models import AnimalLote
    dup = Animal(brinco="101", tipo="Boi", status=StatusAnimal.VENDIDO)
    db.add(dup)
    db.flush()
    db.add(AnimalLote(animal_id=dup.id, lote_id=1, data_inicio=HOJE, data_fim=HOJE))
    db.commit()

    s = _abrir_manejo(db)
    r = svc.registrar_pesagem(db, s, "101", 400, destino_lote="Gordo")
    assert r["ok"]  # não pede escolha — o vendido nem entra na lista de candidatos
    ativo = db.query(Animal).filter(Animal.brinco == "101", Animal.status == StatusAnimal.ATIVO).first()
    assert r["animal_id"] == ativo.id


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


def test_pesagem_devolve_dentes_lancados(db):
    # A tela usa isso pra atualizar o cache local e mostrar os dentes na próxima pesagem.
    s = _abrir_manejo(db)
    r = svc.registrar_pesagem(db, s, "101", 410, destino_lote="Gordo", dentes=6)
    assert r["dentes"] == 6 and r["data_dentes"] == HOJE
    r2 = svc.registrar_pesagem(db, s, "102", 330, destino_lote="Gordo")
    assert "dentes" not in r2  # sem dentição lançada, não sobrescreve a anterior


def test_sem_brinco_grava_dentes_e_vinculo_leva_junto(db):
    from app.models import Denticao
    s = _abrir_manejo(db)
    sb = svc.pesar_sem_brinco(db, s, 280, destino_lote="Magro", dentes=2)
    temp = db.query(Animal).filter(Animal.brinco == sb["brinco"]).first()
    faltante = db.query(Animal).filter(Animal.brinco == "101").first()
    svc.vincular(db, s.data, temp.id, faltante.id)
    d = db.query(Denticao).filter(Denticao.animal_id == faltante.id).all()
    assert [x.dentes for x in d] == [2]  # antes o cascade apagava junto com o provisório


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


def test_refinalizar_manejo_antigo_nao_desfaz_troca_mais_recente(db):
    from datetime import timedelta

    # Manejo 1 (antigo): 101 vai pro "Gordo".
    antigo = _abrir_manejo(db)
    svc.registrar_pesagem(db, antigo, "101", 410, destino_lote="Gordo")
    svc.finalizar(db, antigo)
    # Manejo 2 (2 meses depois): 101 sai do "Gordo" pro "Prontas".
    novo = svc.criar_sessao(db, TipoSessao.MANEJO, HOJE + timedelta(days=60), ["Gordo"],
                            True, ["Prontas"])
    svc.registrar_pesagem(db, novo, "101", 470, destino_lote="Prontas")
    svc.finalizar(db, novo)
    # Reabre e finaliza de novo o manejo ANTIGO: o 101 tem que continuar no "Prontas".
    svc.reabrir(db, antigo)
    svc.finalizar(db, antigo)
    a = db.query(Animal).filter(Animal.brinco == "101").first()
    db.refresh(a)
    assert lote_atual(a) == "Prontas"
    assert len([al for al in a.lotes if al.data_fim is None]) == 1


def test_remover_pesagem_devolve_ao_lote_anterior(db):
    # Pesou, mandou pro "Gordo", finalizou, reabriu e apagou o peso errado:
    # o animal tem que voltar pro LOTEA (e pra lista "a pesar").
    s = _abrir_manejo(db)
    r = svc.registrar_pesagem(db, s, "101", 410, destino_lote="Gordo")
    svc.finalizar(db, s)
    svc.reabrir(db, s)
    assert svc.remover_pesagem(db, s, r["pesagem_id"])
    a = db.query(Animal).filter(Animal.brinco == "101").first()
    db.refresh(a)
    assert lote_atual(a) == "LOTEA"
    assert len([al for al in a.lotes if al.data_fim is None]) == 1
    assert "101" in {x["brinco"] for x in svc.estado_sessao(db, s)["a_pesar"]}


def test_excluir_pesagem_pela_ficha_devolve_ao_lote_anterior(db):
    from app.routers.api import excluir_pesagem_animal

    s = _abrir_manejo(db)
    r = svc.registrar_pesagem(db, s, "101", 410, destino_lote="Gordo")
    svc.finalizar(db, s)
    excluir_pesagem_animal(r["animal_id"], r["pesagem_id"], db=db, _dono=None)
    a = db.query(Animal).filter(Animal.brinco == "101").first()
    db.refresh(a)
    assert lote_atual(a) == "LOTEA"


def test_a_pesar_em_ordem_de_brinco(db):
    assert svc.chave_brinco("2") < svc.chave_brinco("10") < svc.chave_brinco("A1")
    s = _abrir_manejo(db, separar=False)
    brincos = [a["brinco"] for a in svc.estado_sessao(db, s)["a_pesar"]]
    assert brincos == ["101", "102"]
    assert all("dentes" in a for a in svc.estado_sessao(db, s)["a_pesar"])


def test_faltantes_projeta_peso_pelo_ugmd_do_lote(db):
    s = _abrir_manejo(db, separar=False)
    d = svc.faltantes(db, s)
    por_brinco = {f["brinco"]: f for f in d}

    # uGMD do LOTEA = uGMD só do 101 (o único com 2 pesagens): (400-300)/120 dias.
    # 101: último peso 400 kg há 45 dias (01/05 -> 15/06) — projeta pra ~437.5 kg.
    assert por_brinco["101"]["ultimo_peso"] == 400
    assert por_brinco["101"]["dias_sem_pesar"] == 45
    assert por_brinco["101"]["peso_projetado"] == pytest.approx(400 + (100 / 120) * 45, abs=0.5)

    # 102: último peso só 320 kg, mas há 165 dias (01/01 -> 15/06) — projetado
    # (usando o uGMD do LOTE, não o dele, que nem existe) passa o do 101.
    assert por_brinco["102"]["ultimo_peso"] == 320
    assert por_brinco["102"]["dias_sem_pesar"] == 165
    assert por_brinco["102"]["peso_projetado"] == pytest.approx(320 + (100 / 120) * 165, abs=0.5)

    # Ordenado pelo peso PROJETADO (não o último peso bruto) — 102 vem primeiro.
    assert [f["brinco"] for f in d] == ["102", "101"]
    assert d[0]["tipo"] == "Boi"
    assert "raca" in d[0]


def test_faltantes_sem_ugmd_do_lote_fica_sem_estimativa(db):
    # LOTEB só tem o 201, com uma única pesagem — não dá pra calcular uGMD do lote.
    s = svc.criar_sessao(db, TipoSessao.MANEJO, HOJE, ["LOTEB"], False)
    d = svc.faltantes(db, s)
    assert len(d) == 1
    assert d[0]["brinco"] == "201"
    assert d[0]["ultimo_peso"] == 450
    assert d[0]["peso_projetado"] is None


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


def test_lotes_mostram_peso_medio(db):
    from app.routers.api import listar_lotes

    por_nome = {l["nome"]: l for l in listar_lotes(somente_ativos=True, db=db)}
    # LOTEA: 101 (último 400) e 102 (último 320) -> média 360 kg; UA = 720/450.
    assert por_nome["LOTEA"]["peso_medio"] == 360
    assert por_nome["LOTEA"]["ua"] == 1.6
    assert por_nome["LOTEB"]["peso_medio"] == 450


def test_fechamento_venda_gancho_individual_por_animal(db):
    from app import schemas

    s = svc.criar_sessao(db, TipoSessao.VENDA_MORTO, HOJE, ["LOTEA"], False)
    svc.registrar_pesagem(db, s, "101", 500)
    svc.registrar_pesagem(db, s, "102", 480)
    a101 = db.query(Animal).filter(Animal.brinco == "101").first()
    a102 = db.query(Animal).filter(Animal.brinco == "102").first()
    # A venda grava a data do evento no animal.
    assert a101.status == StatusAnimal.VENDIDO and a101.data_evento == HOJE

    f = svc.fechamento_venda(db, s)
    assert f["totais"] == {**f["totais"], "animais": 2, "pendentes": 2, "valor": 0}
    assert f["acabamentos"] == ["Ausente", "Escasso", "Mediano", "Uniforme"]

    # Romaneio: cada animal com sua carcaça, rendimento, preço da @ e acabamento.
    r = svc.salvar_fechamento_venda(db, s, [
        schemas.FechamentoVendaItem(animal_id=a101.id, peso_carcaca=270, rendimento=0.545,
                                    preco_arroba=330, acabamento="Uniforme"),
        # Só carcaça, sem preço ainda: continua pendente; rendimento sai da conta.
        schemas.FechamentoVendaItem(animal_id=a102.id, peso_carcaca=240),
    ])
    assert r["ok"]
    por = {i["brinco"]: i for i in r["itens"]}
    assert por["101"]["valor_recebido"] == 5940.0     # 270/15 * 330
    assert por["101"]["rendimento"] == 0.545 and por["101"]["acabamento"] == "Uniforme"
    assert por["101"]["pendente"] is False
    assert por["102"]["pendente"] is True and por["102"]["rendimento"] == 0.5
    assert r["totais"]["pendentes"] == 1 and r["totais"]["valor"] == 5940.0

    # Completa o 102 com outro preço (classificação diferente).
    r = svc.salvar_fechamento_venda(db, s, [
        schemas.FechamentoVendaItem(animal_id=a102.id, peso_carcaca=240, preco_arroba=300,
                                    acabamento="Escasso"),
    ])
    assert r["totais"]["pendentes"] == 0
    assert r["totais"]["valor"] == 5940.0 + 4800.0    # 240/15 * 300
    assert r["totais"]["arrobas"] == 34.0
    assert r["totais"]["rendimento_medio"] == round(510 / 980, 4)

    # Acabamento fora da lista é recusado e nada é gravado.
    r = svc.salvar_fechamento_venda(db, s, [
        schemas.FechamentoVendaItem(animal_id=a102.id, acabamento="Gordão"),
    ])
    assert not r["ok"]
    db.refresh(a102.venda)
    assert a102.venda.acabamento == "Escasso" and a102.venda.peso_carcaca == 240

    # Linha mandada em branco limpa o lançamento (romaneio digitado no animal errado).
    r = svc.salvar_fechamento_venda(db, s, [schemas.FechamentoVendaItem(animal_id=a102.id)])
    por = {i["brinco"]: i for i in r["itens"]}
    assert por["102"]["pendente"] is True and por["102"]["peso_carcaca"] is None
    assert por["102"]["valor_recebido"] is None and r["totais"]["valor"] == 5940.0


def test_migrar_colunas_acrescenta_coluna_que_falta():
    from sqlalchemy import create_engine, inspect, text

    from app.database import migrar_colunas

    eng = create_engine("sqlite://")
    with eng.begin() as con:
        con.execute(text("CREATE TABLE vendas (id INTEGER PRIMARY KEY, peso FLOAT)"))
        con.execute(text("INSERT INTO vendas (id, peso) VALUES (1, 500)"))
    migrar_colunas(eng)
    migrar_colunas(eng)  # rodar de novo não dá erro
    assert "acabamento" in {c["name"] for c in inspect(eng).get_columns("vendas")}
    with eng.begin() as con:
        assert con.execute(text("SELECT peso FROM vendas")).scalar() == 500


def test_fechamento_venda_compara_dentes_anotados_com_os_do_frigorifico(db):
    from datetime import timedelta

    from app import schemas
    from app.models import Denticao

    s = svc.criar_sessao(db, TipoSessao.VENDA_MORTO, HOJE, ["LOTEA"], False)
    svc.registrar_pesagem(db, s, "101", 500, dentes=4)     # anotado 4 dentes na fazenda
    svc.registrar_pesagem(db, s, "102", 480)               # sem dentição anotada
    a101 = db.query(Animal).filter(Animal.brinco == "101").first()
    a102 = db.query(Animal).filter(Animal.brinco == "102").first()
    # Dentição lançada DEPOIS da venda não entra na comparação.
    db.add(Denticao(animal_id=a101.id, data=HOJE + timedelta(days=10), dentes=6))
    db.commit()

    r = svc.salvar_fechamento_venda(db, s, [
        schemas.FechamentoVendaItem(animal_id=a101.id, peso_carcaca=270, preco_arroba=330,
                                    dentes_frigorifico=6),
        schemas.FechamentoVendaItem(animal_id=a102.id, peso_carcaca=240, preco_arroba=330,
                                    dentes_frigorifico=2),
    ])
    por = {i["brinco"]: i for i in r["itens"]}
    assert (por["101"]["dentes"], por["101"]["dentes_frigorifico"]) == (4, 6)
    assert (por["102"]["dentes"], por["102"]["dentes_frigorifico"]) == (None, 2)
    assert r["totais"]["dentes_diferentes"] == 1          # só o 101 (o 102 não tinha anotação)

    r = svc.salvar_fechamento_venda(db, s, [
        schemas.FechamentoVendaItem(animal_id=a101.id, peso_carcaca=270, preco_arroba=330,
                                    dentes_frigorifico=9)])
    assert not r["ok"]
