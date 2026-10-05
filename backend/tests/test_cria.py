"""Testes da cria: nascimento, vínculo mãe-bezerro, prenhez, desmama e situação."""
from datetime import date, timedelta

import pytest

from app import schemas
from app.models import Animal, PapelUsuario, Pesagem, StatusAnimal, Usuario
from app.routers import api
from app.services import cria as svc
from app.services import sessao as svc_sessao
from app.services.consultas import lote_atual

DONO = Usuario(papel=PapelUsuario.DONO)
ONTEM = date.today() - timedelta(days=1)


def _vaca(db, brinco="900"):
    """Vira o animal 101 (LOTEA) numa vaca pra servir de matriz."""
    v = db.query(Animal).filter(Animal.brinco == "101").first()
    v.tipo, v.brinco = "Vaca", brinco
    db.commit()
    return v


def _matriz(db, vaca):
    return next(m for m in svc.painel(db)["matrizes"] if m["id"] == vaca.id)


def test_nascimento_liga_bezerro_a_mae_no_mesmo_lote(db):
    vaca = _vaca(db)
    svc.marcar_prenhez(db, vaca, "mojando")
    assert _matriz(db, vaca)["situacao"] == "solteira"
    assert _matriz(db, vaca)["pode_frigorifico"] is False      # mojando não vai pro gancho

    b = svc.registrar_nascimento(db, vaca, ONTEM, "F", brinco="B1", peso=32)
    assert b.tipo == "Bez Fem" and b.mae_id == vaca.id and b.nascimento == ONTEM
    assert lote_atual(b) == "LOTEA"
    assert [p.peso for p in b.pesagens] == [32]

    m = _matriz(db, vaca)
    assert m["situacao"] == "com_bezerro" and m["pode_frigorifico"] is False
    assert m["prenhez"] is None                                   # pariu: limpa a marcação
    assert m["crias"][0]["brinco"] == "B1" and m["crias"][0]["ao_pe"] is True
    assert m["crias"][0]["idade_dias"] == 1


def test_nascimento_sem_brinco_ganha_provisorio(db):
    vaca = _vaca(db)
    b = svc.registrar_nascimento(db, vaca, ONTEM, "M")
    assert b.sem_brinco is True and b.tipo == "Bez Mach"
    assert b.brinco == f"S/B-900-{b.id}"
    with pytest.raises(ValueError):
        svc.registrar_nascimento(db, vaca, date.today() + timedelta(days=2), "M")
    with pytest.raises(ValueError):
        svc.registrar_nascimento(db, vaca, ONTEM, "X")


def test_desmama_deixa_a_vaca_solteira_e_guarda_o_peso(db):
    vaca = _vaca(db)
    b = svc.registrar_nascimento(db, vaca, date.today() - timedelta(days=210), "M", brinco="B2")
    db.add(Pesagem(animal_id=b.id, data=ONTEM, peso=190))
    db.commit()
    svc.desmamar(db, b, ONTEM)
    assert b.tipo == "Boi" and b.data_desmame == ONTEM

    m = _matriz(db, vaca)
    assert m["situacao"] == "solteira" and m["pode_frigorifico"] is True
    assert m["crias"][0]["peso_desmame"] == 190 and m["crias"][0]["ao_pe"] is False
    assert m["total_crias"] == 1


def test_trocar_tipo_na_mao_grava_data_do_desmame(db):
    vaca = _vaca(db)
    b = svc.registrar_nascimento(db, vaca, ONTEM, "F", brinco="B3")
    api.atualizar_animal(b.id, schemas.AnimalAtualizar(tipo="Novilha"), db, usuario=DONO)
    db.refresh(b)
    assert b.data_desmame == date.today()
    assert _matriz(db, vaca)["situacao"] == "solteira"


def test_bezerro_morto_deixa_a_vaca_solteira(db):
    vaca = _vaca(db)
    b = svc.registrar_nascimento(db, vaca, ONTEM, "F", brinco="B4")
    b.status = StatusAnimal.MORTO
    db.commit()
    assert _matriz(db, vaca)["situacao"] == "solteira"


def test_definir_mae_de_bezerro_ja_cadastrado_e_lista_sem_mae(db):
    vaca = _vaca(db)
    bez = db.query(Animal).filter(Animal.brinco == "102").first()
    bez.tipo = "Bez Mach"
    db.commit()
    assert [b["brinco"] for b in svc.painel(db)["bezerros_sem_mae"]] == ["102"]

    svc.definir_mae(db, bez, vaca)
    p = svc.painel(db)
    assert p["bezerros_sem_mae"] == []
    assert p["resumo"]["com_bezerro"] == 1 and p["resumo"]["bezerros_ao_pe"] == 1
    # A ficha do bezerro mostra a mãe; a da vaca mostra a cria.
    assert api.detalhar_animal(bez.id, db)["mae"]["brinco"] == "900"
    assert api.detalhar_animal(vaca.id, db)["cria"]["crias"][0]["brinco"] == "102"

    with pytest.raises(ValueError):
        svc.definir_mae(db, vaca, vaca)
    with pytest.raises(ValueError):
        svc.definir_mae(db, vaca, bez)      # a mãe não pode virar cria do próprio bezerro
    svc.definir_mae(db, bez, None)
    assert bez.mae_id is None


def test_prenhez_marca_limpa_e_valida(db):
    vaca = _vaca(db)
    svc.marcar_prenhez(db, vaca, "prenhe", ONTEM)
    assert (vaca.prenhez, vaca.prenhez_data) == ("prenhe", ONTEM)
    svc.marcar_prenhez(db, vaca, "vazia")
    assert _matriz(db, vaca)["pode_frigorifico"] is True
    svc.marcar_prenhez(db, vaca, None)
    assert vaca.prenhez is None and vaca.prenhez_data is None
    with pytest.raises(ValueError):
        svc.marcar_prenhez(db, vaca, "talvez")


def test_excluir_mae_so_desliga_as_crias(db):
    vaca = _vaca(db)
    b = svc.registrar_nascimento(db, vaca, ONTEM, "F", brinco="B5")
    api.excluir_animal(vaca.id, db)
    db.refresh(b)
    assert b.mae_id is None and b.status == StatusAnimal.ATIVO


def test_vincular_bezerro_sem_brinco_herda_a_mae(db):
    vaca = _vaca(db)
    provisorio = svc.registrar_nascimento(db, vaca, ONTEM, "M")
    antigo = db.query(Animal).filter(Animal.brinco == "102").first()
    r = svc_sessao.vincular(db, date.today(), provisorio.id, antigo.id)
    assert r["ok"]
    db.refresh(antigo)
    assert antigo.mae_id == vaca.id and antigo.nascimento == ONTEM
