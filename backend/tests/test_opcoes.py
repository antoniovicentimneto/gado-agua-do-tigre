"""Testes das opções pré-cadastradas (tipos e raças)."""
from app.services import opcoes as svc


def test_semeia_tipos_dos_animais_existentes(db):
    # O fixture cria animais com tipos Novilha, Boi, Vaca.
    tipos = {o.nome for o in svc.listar(db, "tipo")}
    assert {"Novilha", "Boi", "Vaca"} <= tipos


def test_criar_e_remover_opcao(db):
    nova = svc.criar(db, "raca", "Angus")
    assert nova.id is not None
    assert "Angus" in {o.nome for o in svc.listar(db, "raca")}
    # Não duplica.
    svc.criar(db, "raca", "Angus")
    assert sum(1 for o in svc.listar(db, "raca") if o.nome == "Angus") == 1
    assert svc.remover(db, "raca", nova.id) is True
    assert "Angus" not in {o.nome for o in svc.listar(db, "raca")}
