"""Testes de edição/exclusão de animal e pesagem (correção de lançamento errado)."""
import pytest
from fastapi import HTTPException

from app.models import Animal, Pesagem
from app.routers import api


def test_editar_brinco(db):
    a = db.query(Animal).filter(Animal.brinco == "101").first()
    from app import schemas
    api.atualizar_animal(a.id, schemas.AnimalAtualizar(brinco="999"), db)
    db.refresh(a)
    assert a.brinco == "999"


def test_excluir_pesagem_do_animal(db):
    a = db.query(Animal).filter(Animal.brinco == "101").first()
    pesagem_id = a.pesagens[0].id
    api.excluir_pesagem_animal(a.id, pesagem_id, db)
    assert db.get(Pesagem, pesagem_id) is None


def test_excluir_pesagem_de_outro_animal_da_404(db):
    a101 = db.query(Animal).filter(Animal.brinco == "101").first()
    a102 = db.query(Animal).filter(Animal.brinco == "102").first()
    pesagem_de_101 = a101.pesagens[0].id
    with pytest.raises(HTTPException) as exc:
        api.excluir_pesagem_animal(a102.id, pesagem_de_101, db)
    assert exc.value.status_code == 404


def test_excluir_animal_apaga_tudo(db):
    a = db.query(Animal).filter(Animal.brinco == "101").first()
    animal_id = a.id
    api.excluir_animal(animal_id, db)
    assert db.get(Animal, animal_id) is None
    assert db.query(Pesagem).filter(Pesagem.animal_id == animal_id).count() == 0
