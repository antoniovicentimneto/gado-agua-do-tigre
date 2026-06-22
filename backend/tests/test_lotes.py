"""Testes de gestão de lotes: renomear, mover e juntar."""
import pytest

from app import schemas
from app.models import Animal, Lote
from app.routers.api import juntar_lotes, mover_animais, renomear_lote
from app.services.consultas import lote_atual


def _id_lote(db, nome):
    return db.query(Lote).filter(Lote.nome == nome).first().id


def _animal(db, brinco):
    return db.query(Animal).filter(Animal.brinco == brinco).first()


def test_renomear_lote(db):
    lid = _id_lote(db, "LOTEA")
    renomear_lote(lid, schemas.LoteRenomear(nome="LOTE A NOVO"), db=db)
    # O animal continua no mesmo lote (agora com o novo nome) — histórico preservado.
    assert lote_atual(_animal(db, "101")) == "LOTE A NOVO"


def test_renomear_para_nome_existente_falha(db):
    lid = _id_lote(db, "LOTEA")
    with pytest.raises(Exception):
        renomear_lote(lid, schemas.LoteRenomear(nome="LOTEB"), db=db)


def test_mover_animais_selecionados(db):
    a101 = _animal(db, "101")
    mover_animais(schemas.LoteMover(animal_ids=[a101.id], destino="LOTEB"), db=db)
    assert lote_atual(_animal(db, "101")) == "LOTEB"
    # O 102 continua no LOTEA.
    assert lote_atual(_animal(db, "102")) == "LOTEA"


def test_juntar_lotes(db):
    origem_id = _id_lote(db, "LOTEA")
    r = juntar_lotes(schemas.LoteJuntar(origem_id=origem_id, destino="LOTEB"), db=db)
    assert r["movidos"] == 2  # 101 e 102
    assert lote_atual(_animal(db, "101")) == "LOTEB"
    assert lote_atual(_animal(db, "102")) == "LOTEB"
