"""Testes do manejo de campo: salga de cocho (consumo por cabeça) e sanidade (carência)."""
from datetime import date, datetime, timedelta

import pytest

from app.models import Animal, Lote, PapelUsuario, Piquete, Usuario
from app.services import campo as svc
from app.services import opcoes
from app.services import pastos as svc_pastos


def _lote(db, nome):
    return db.query(Lote).filter(Lote.nome == nome).first()


def _animal(db, brinco):
    return db.query(Animal).filter(Animal.brinco == brinco).first()


def _usuario(db, papel=PapelUsuario.PEAO, nome="Romário"):
    u = Usuario(nome=nome, usuario=nome.lower(), senha_hash="x", papel=papel)
    db.add(u)
    db.commit()
    return u


AGORA = datetime.utcnow().replace(microsecond=0)


# ---------------------------------------------------------------- Sal

def test_salgar_guarda_cabecas_e_piquete(db):
    p = Piquete(nome="P1", ativo=True)
    db.add(p)
    db.commit()
    lote = _lote(db, "LOTEA")
    svc_pastos.mover(db, lote.id, p.id)
    r = svc.salgar(db, lote.id, "Proteinado", 25, AGORA, usuario=_usuario(db))
    s = r["salga"]
    assert s["cabecas"] == 2 and s["piquete_id"] == p.id and s["usuario"] == "Romário"


def test_salgar_mesma_chave_nao_duplica(db):
    lote = _lote(db, "LOTEA")
    a = svc.salgar(db, lote.id, "Sal mineral", 10, AGORA, chave="k1")
    b = svc.salgar(db, lote.id, "Sal mineral", 10, AGORA, chave="k1")
    assert b["repetida"] and a["salga"]["id"] == b["salga"]["id"]


def test_salgar_valida_campos(db):
    lote = _lote(db, "LOTEA")
    with pytest.raises(svc.ErroCampo):
        svc.salgar(db, lote.id, "", 10)
    with pytest.raises(svc.ErroCampo):
        svc.salgar(db, lote.id, "Sal mineral", 0)
    with pytest.raises(svc.ErroCampo):
        svc.salgar(db, lote.id, "Sal mineral", 10, AGORA + timedelta(days=3))


def test_consumo_em_gramas_por_cabeca_por_dia(db):
    lote = _lote(db, "LOTEA")  # 2 cabeças
    inicio = AGORA - timedelta(days=20)
    svc.salgar(db, lote.id, "Sal mineral", 6, inicio)                       # durou 10 dias
    svc.salgar(db, lote.id, "Sal mineral", 3, inicio + timedelta(days=10))  # durou 10 dias
    svc.salgar(db, lote.id, "Sal mineral", 5, inicio + timedelta(days=20))  # ainda no cocho
    h = svc.historico_sal(db, lote.id, hoje=AGORA.date())
    # 6 kg / (2 cab × 10 dias) = 300 g; 3 kg / 20 cab-dias = 150 g; média = 9 kg / 40 = 225 g
    por_salga = sorted(s["g_cab_dia"] for s in h["salgas"] if s["g_cab_dia"])
    assert por_salga == [150, 300]
    assert h["media_g_cab_dia"] == 225
    assert h["ultima"]["quantidade_kg"] == 5 and h["dias_desde_ultima"] == 0


def test_painel_de_pastos_mostra_ultima_salga(db):
    p = Piquete(nome="P1", ativo=True)
    db.add(p)
    db.commit()
    lote = _lote(db, "LOTEA")
    svc_pastos.mover(db, lote.id, p.id)
    svc.salgar(db, lote.id, "Ureado", 40, AGORA)
    item = next(x for x in svc_pastos.painel(db)["piquetes"] if x["id"] == p.id)
    assert item["lotes"][0]["ultima_salga"]["produto"] == "Ureado"


def test_peao_apaga_so_o_que_lancou_dono_apaga_tudo(db):
    peao = _usuario(db)
    outro = _usuario(db, nome="Taborda")
    dono = _usuario(db, PapelUsuario.DONO, "Antonio")
    s = svc.salgar(db, _lote(db, "LOTEA").id, "Sal mineral", 5, AGORA, usuario=peao)["salga"]
    with pytest.raises(svc.ErroCampo):
        svc.apagar_salga(db, s["id"], outro)
    assert svc.apagar_salga(db, s["id"], peao)["ok"]
    s2 = svc.salgar(db, _lote(db, "LOTEA").id, "Sal mineral", 5, AGORA, usuario=peao)["salga"]
    assert svc.apagar_salga(db, s2["id"], dono)["ok"]


# ---------------------------------------------------------------- Sanidade

def test_registrar_tratamento_calcula_carencia(db):
    a = _animal(db, "101")
    r = svc.registrar_ocorrencia(db, a.id, "Pneumonia", produto="Oxitetraciclina",
                                 dose="20 ml", carencia_dias=28, data_hora=AGORA,
                                 usuario=_usuario(db))
    o = r["ocorrencia"]
    assert o["brinco"] == "101" and o["lote"] == "LOTEA"
    assert o["carencia_ate"] == (AGORA.date() + timedelta(days=28)).isoformat()
    assert svc.carencias_ativas(db, AGORA.date()) == {a.id: AGORA.date() + timedelta(days=28)}


def test_carencia_vencida_nao_conta(db):
    a = _animal(db, "102")
    svc.registrar_ocorrencia(db, a.id, "Bicheira", carencia_dias=5,
                             data_hora=AGORA - timedelta(days=30))
    assert svc.carencias_ativas(db, AGORA.date()) == {}


def test_tratamento_sem_carencia_e_mesma_chave(db):
    a = _animal(db, "201")
    r1 = svc.registrar_ocorrencia(db, a.id, "Casco / manqueira", chave="z")
    r2 = svc.registrar_ocorrencia(db, a.id, "Casco / manqueira", chave="z")
    assert r2["repetida"] and r1["ocorrencia"]["carencia_ate"] is None
    assert len(svc.listar_ocorrencias(db, animal_id=a.id)) == 1


def test_tratamento_valida(db):
    a = _animal(db, "201")
    with pytest.raises(svc.ErroCampo):
        svc.registrar_ocorrencia(db, a.id, "")
    with pytest.raises(svc.ErroCampo):
        svc.registrar_ocorrencia(db, a.id, "Bicheira", carencia_dias=999)
    with pytest.raises(svc.ErroCampo):
        svc.registrar_ocorrencia(db, 99999, "Bicheira")


def test_listar_por_periodo(db):
    a = _animal(db, "101")
    svc.registrar_ocorrencia(db, a.id, "Bicheira", data_hora=AGORA - timedelta(days=100))
    svc.registrar_ocorrencia(db, a.id, "Olho (ceratite)", data_hora=AGORA)
    recentes = svc.listar_ocorrencias(db, dias=30, hoje=AGORA.date())
    assert [o["problema"] for o in recentes] == ["Olho (ceratite)"]


# ---------------------------------------------------------------- Listas do campo

def test_listas_do_campo_ja_vem_preenchidas(db):
    nomes = [o.nome for o in opcoes.listar(db, "problema")]
    assert "Bicheira" in nomes and "Pneumonia" in nomes
    assert "Proteinado" in [o.nome for o in opcoes.listar(db, "sal")]
    assert opcoes.listar(db, "medicamento") == []
    opcoes.criar(db, "medicamento", "Ivermectina 1%")
    assert [o.nome for o in opcoes.listar(db, "medicamento")] == ["Ivermectina 1%"]


# ---------------------------------------------------------------- Cocho dividido e faixa

def test_cocho_dividido_reparte_pelas_cabecas(db):
    a, b = _lote(db, "LOTEA"), _lote(db, "LOTEB")  # 2 e 1 cabeças
    r = svc.salgar(db, a.id, "Sal mineral", 30, AGORA, outros_lotes=[b.id])
    partes = {d["lote"]: d["quantidade_kg"] for d in r["divisao"]}
    assert partes == {"LOTEA": 20, "LOTEB": 10}
    # Apagar a salga de um lote apaga a parte dos dois (era um cocho só).
    assert svc.apagar_salga(db, r["salga"]["id"], _usuario(db, PapelUsuario.DONO, "Dono"))["apagadas"] == 2


def test_consumo_separado_por_sal(db):
    lote = _lote(db, "LOTEA")  # 2 cabeças
    t0 = AGORA - timedelta(days=20)
    svc.salgar(db, lote.id, "Sal mineral", 4, t0)
    svc.salgar(db, lote.id, "Proteinado", 20, t0 + timedelta(days=1))
    svc.salgar(db, lote.id, "Sal mineral", 4, t0 + timedelta(days=10))
    h = svc.historico_sal(db, lote.id, hoje=AGORA.date())
    medias = {p["produto"]: p["media_g_cab_dia"] for p in h["por_produto"]}
    # Mineral: 4 kg / (2 cab × 10 dias) = 200 g — o proteinado no meio não atrapalha.
    assert medias["Sal mineral"] == 200 and medias["Proteinado"] is None


def test_faixa_de_consumo_e_alerta(db):
    from app.services import alertas
    lote = _lote(db, "LOTEA")
    t0 = AGORA - timedelta(days=10)
    svc.salgar(db, lote.id, "Sal mineral", 4, t0)             # 200 g/cab/dia
    svc.salgar(db, lote.id, "Sal mineral", 4, t0 + timedelta(days=10))
    assert svc.consumo_fora_da_faixa(db, AGORA.date()) == []   # sem faixa configurada: nada
    svc.salvar_faixas(db, {"Sal mineral": {"min": "60", "max": "120"}})
    fora = svc.consumo_fora_da_faixa(db, AGORA.date())
    assert fora[0]["situacao"] == "alto" and fora[0]["g_cab_dia"] == 200
    tipos = {a["tipo"] for a in alertas.alertas(db, AGORA.date())["alertas"]}
    assert "sal_fora_da_faixa" in tipos
    with pytest.raises(svc.ErroCampo):
        svc.salvar_faixas(db, {"Sal mineral": {"min": 200, "max": 100}})
