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


def test_data_evento_ao_marcar_inativo(db):
    from datetime import date
    from app import schemas

    a = db.query(Animal).filter(Animal.brinco == "101").first()
    api.atualizar_animal(
        a.id, schemas.AnimalAtualizar(status="vendido", data_evento=date(2025, 10, 12)), db
    )
    db.refresh(a)
    assert a.status.value == "vendido"
    assert a.data_evento == date(2025, 10, 12)

    # Reativar limpa a data do evento.
    api.atualizar_animal(a.id, schemas.AnimalAtualizar(status="ativo", data_evento=None), db)
    db.refresh(a)
    assert a.status.value == "ativo"
    assert a.data_evento is None


def test_duplicado_so_conta_entre_ativos(db):
    from app.models import StatusAnimal

    ativo1 = db.query(Animal).filter(Animal.brinco == "101").first()
    # Um segundo "101" ATIVO -> os dois ficam marcados como duplicado.
    dup_ativo = Animal(brinco="101", tipo="Boi", status=StatusAnimal.ATIVO)
    # Um terceiro "102" VENDIDO -> não conta pro duplicado do 102 ativo.
    dup_vendido = Animal(brinco="102", tipo="Boi", status=StatusAnimal.VENDIDO)
    db.add_all([dup_ativo, dup_vendido])
    db.commit()

    resultado = {r["id"]: r["duplicado"] for r in api.listar_animais(db=db, busca=None)}
    assert resultado[ativo1.id] is True
    assert resultado[dup_ativo.id] is True
    assert resultado[dup_vendido.id] is False  # vendido nunca conta como duplicado
    a102 = db.query(Animal).filter(Animal.brinco == "102", Animal.status == StatusAnimal.ATIVO).first()
    assert resultado[a102.id] is False  # só ele é ativo com brinco 102


def test_excluir_animal_apaga_tudo(db):
    a = db.query(Animal).filter(Animal.brinco == "101").first()
    animal_id = a.id
    api.excluir_animal(animal_id, db)
    assert db.get(Animal, animal_id) is None
    assert db.query(Pesagem).filter(Pesagem.animal_id == animal_id).count() == 0
