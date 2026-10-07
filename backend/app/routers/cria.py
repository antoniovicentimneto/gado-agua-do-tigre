"""Endpoints da aba Cria (vacas e bezerros)."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Animal
from .. import schemas
from ..services import cria as svc
from ..services.auth import requer_dono, usuario_atual

router = APIRouter(prefix="/api/cria", tags=["cria"], dependencies=[Depends(usuario_atual)])


def _animal(db: Session, animal_id: int) -> Animal:
    a = db.get(Animal, animal_id)
    if a is None:
        raise HTTPException(status_code=404, detail="Animal não encontrado")
    return a


@router.get("")
def painel(novilhas: bool = False, db: Session = Depends(get_db)):
    """Matrizes com a situação (com bezerro / solteira / prenhe) e todos os bezerros."""
    return svc.painel(db, novilhas=novilhas)


@router.post("/excel")
def excel(dados: schemas.CriaExcel, _dono=Depends(requer_dono)):
    """Baixa em Excel a tabela que está na tela (vacas ou bezerros)."""
    nome = f"cria_{dados.titulo.lower()}_{date.today():%Y%m%d}.xlsx"
    return Response(
        content=svc.gerar_excel(dados.titulo, dados.cabecalho, dados.linhas),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


@router.post("/nascimento", status_code=201)
def nascimento(dados: schemas.NascimentoCriar, db: Session = Depends(get_db)):
    """Registra o nascimento: cria o bezerro ligado à mãe (peão também lança)."""
    mae = _animal(db, dados.mae_id)
    try:
        b = svc.registrar_nascimento(db, mae, dados.data, dados.sexo, dados.brinco, dados.peso)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "id": b.id, "brinco": b.brinco, "tipo": b.tipo}


@router.put("/prenhez/{animal_id}")
def prenhez(animal_id: int, dados: schemas.PrenhezMarcar, db: Session = Depends(get_db)):
    """Marca a vaca como prenhe / mojando / vazia (ou limpa a marcação)."""
    try:
        svc.marcar_prenhez(db, _animal(db, animal_id), dados.prenhez, dados.data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True}


@router.put("/mae/{animal_id}")
def mae(animal_id: int, dados: schemas.MaeDefinir, db: Session = Depends(get_db)):
    """Salva a mãe e/ou a data de nascimento do animal, juntos (peão também lança).

    Só altera o que veio no pedido: mae_id nulo desliga a mãe; nascimento nulo limpa.
    """
    cria = _animal(db, animal_id)
    enviados = dados.model_fields_set
    try:
        if "nascimento" in enviados:
            svc.definir_nascimento(cria, dados.nascimento)
        if "mae_id" in enviados:
            svc.definir_mae(db, cria, _animal(db, dados.mae_id) if dados.mae_id else None)
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e
    db.commit()
    return {"ok": True}


@router.post("/desmama/{animal_id}")
def desmama(animal_id: int, dados: schemas.DesmamaMarcar, db: Session = Depends(get_db),
            _dono=Depends(requer_dono)):
    """Desmama o bezerro (grava a data e troca o tipo pra Novilha/Boi)."""
    svc.desmamar(db, _animal(db, animal_id), dados.data, dados.novo_tipo)
    return {"ok": True}
