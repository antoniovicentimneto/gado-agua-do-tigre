"""Listas de opções pré-cadastradas (tipos de animal e raças).

Servem para preencher os campos do animal escolhendo de uma lista, em vez de
digitar livre. Na primeira vez que uma categoria é consultada e está vazia, é
semeada com os valores distintos que já existem no cadastro dos animais.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import Animal, OpcaoCadastro

CATEGORIAS = {"tipo", "raca"}


def _semear_se_vazio(db: Session, categoria: str) -> None:
    """Popula a categoria com os valores já usados nos animais, se ainda vazia."""
    tem = db.query(OpcaoCadastro).filter(OpcaoCadastro.categoria == categoria).first()
    if tem is not None:
        return
    campo = Animal.tipo if categoria == "tipo" else Animal.raca
    distintos = {
        (v[0] or "").strip()
        for v in db.query(campo).distinct().all()
        if v[0] and v[0].strip()
    }
    for nome in sorted(distintos):
        db.add(OpcaoCadastro(categoria=categoria, nome=nome))
    if distintos:
        db.commit()


def listar(db: Session, categoria: str) -> list[OpcaoCadastro]:
    _semear_se_vazio(db, categoria)
    return (
        db.query(OpcaoCadastro)
        .filter(OpcaoCadastro.categoria == categoria)
        .order_by(OpcaoCadastro.nome)
        .all()
    )


def criar(db: Session, categoria: str, nome: str) -> OpcaoCadastro:
    nome = nome.strip()
    if not nome:
        raise ValueError("Informe um nome.")
    existente = (
        db.query(OpcaoCadastro)
        .filter(OpcaoCadastro.categoria == categoria, OpcaoCadastro.nome == nome)
        .first()
    )
    if existente:
        return existente
    opcao = OpcaoCadastro(categoria=categoria, nome=nome)
    db.add(opcao)
    db.commit()
    db.refresh(opcao)
    return opcao


def remover(db: Session, categoria: str, opcao_id: int) -> bool:
    opcao = db.get(OpcaoCadastro, opcao_id)
    if opcao is None or opcao.categoria != categoria:
        return False
    db.delete(opcao)
    db.commit()
    return True
