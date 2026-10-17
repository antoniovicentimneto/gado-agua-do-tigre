"""Endpoints do manejo de campo: sal no cocho (por lote) e sanidade (por animal).

Peão e dono lançam; apagar é do dono (o peão só corrige o que lançou no mesmo dia).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Usuario
from .. import schemas
from ..services import campo as svc
from ..services.auth import usuario_atual

router = APIRouter(prefix="/api", tags=["campo"], dependencies=[Depends(usuario_atual)])


def _executar(funcao, *args, **kwargs):
    """Erro de regra de negócio vira 400 com a mensagem amigável (sem stack trace)."""
    try:
        return funcao(*args, **kwargs)
    except svc.ErroCampo as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------- Sal

@router.get("/sal")
def historico_sal(lote_id: int, db: Session = Depends(get_db)):
    """Salgas do lote, consumo em g/cabeça/dia e a última salga."""
    return svc.historico_sal(db, lote_id)


@router.post("/sal")
def salgar(dados: schemas.SalgaEntrada, db: Session = Depends(get_db),
           usuario: Usuario = Depends(usuario_atual)):
    return _executar(svc.salgar, db, dados.lote_id, dados.produto, dados.quantidade_kg,
                     dados.data_hora, dados.observacao, dados.chave, usuario)


@router.delete("/sal/{salga_id}")
def apagar_salga(salga_id: int, db: Session = Depends(get_db),
                 usuario: Usuario = Depends(usuario_atual)):
    return _executar(svc.apagar_salga, db, salga_id, usuario)


# ---------------------------------------------------------------- Sanidade

@router.get("/sanidade")
def listar_sanidade(animal_id: int | None = None, dias: int | None = None,
                    db: Session = Depends(get_db)):
    """Tratamentos (mais recentes primeiro). `dias` limita ao período."""
    return svc.listar_ocorrencias(db, animal_id, dias)


@router.post("/sanidade")
def registrar_sanidade(dados: schemas.OcorrenciaEntrada, db: Session = Depends(get_db),
                       usuario: Usuario = Depends(usuario_atual)):
    return _executar(
        svc.registrar_ocorrencia, db, dados.animal_id, dados.problema,
        produto=dados.produto, dose=dados.dose, carencia_dias=dados.carencia_dias,
        data_hora=dados.data_hora, observacao=dados.observacao, chave=dados.chave,
        usuario=usuario,
    )


@router.delete("/sanidade/{ocorrencia_id}")
def apagar_sanidade(ocorrencia_id: int, db: Session = Depends(get_db),
                    usuario: Usuario = Depends(usuario_atual)):
    return _executar(svc.apagar_ocorrencia, db, ocorrencia_id, usuario)
