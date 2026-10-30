"""Endpoints da tela inicial (o dashboard). Dinheiro, compra e venda só para o dono."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import PapelUsuario, Usuario
from ..services import inicio as svc
from ..services.auth import requer_dono, usuario_atual

router = APIRouter(prefix="/api/inicio", tags=["inicio"], dependencies=[Depends(usuario_atual)])


def _ehdono(usuario: Usuario) -> bool:
    return usuario.papel == PapelUsuario.DONO


# `hoje` vem do aparelho: o servidor roda em UTC e, à noite no Brasil, já estaria no dia seguinte.
@router.get("/rebanho")
def rebanho(hoje: date | None = None, db: Session = Depends(get_db),
            usuario: Usuario = Depends(usuario_atual)):
    return svc.rebanho(db, hoje or date.today(), _ehdono(usuario))


@router.get("/producao")
def producao(hoje: date | None = None, inicio: date | None = None, fim: date | None = None,
             db: Session = Depends(get_db), usuario: Usuario = Depends(usuario_atual)):
    return svc.producao(db, hoje or date.today(), inicio, fim, _ehdono(usuario))


@router.get("/financeiro")
def financeiro(hoje: date | None = None, inicio: date | None = None, fim: date | None = None,
               db: Session = Depends(get_db), _dono=Depends(requer_dono)):
    return svc.financeiro(db, hoje or date.today(), inicio, fim)


@router.get("/animais")
def animais(hoje: date | None = None, tipo: str | None = None, faixa: str | None = None,
            lote: int | None = None, db: Session = Depends(get_db)):
    """A lista por trás de um número: animais de uma categoria, de um lote ou há tanto tempo sem pesar."""
    return svc.animais_filtrados(db, hoje or date.today(), tipo, faixa, lote)
