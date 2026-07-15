"""Endpoints da sessão de pesagem na mangueira."""
from __future__ import annotations

import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import PapelUsuario, SessaoPesagem, StatusSessao, TipoSessao, Usuario
from .. import schemas
from ..services import sessao as svc
from ..services.auth import requer_dono, usuario_atual

router = APIRouter(prefix="/api/sessoes", tags=["sessoes"],
                   dependencies=[Depends(usuario_atual)])


def _buscar_sessao(db: Session, sessao_id: int) -> SessaoPesagem:
    s = db.get(SessaoPesagem, sessao_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    return s


@router.post("", status_code=201)
def criar(dados: schemas.SessaoCriar, db: Session = Depends(get_db),
          usuario: Usuario = Depends(usuario_atual)):
    # Peão só pode abrir sessão de MANEJO (compra/venda são financeiro = só dono).
    if dados.tipo != TipoSessao.MANEJO and usuario.papel != PapelUsuario.DONO:
        raise HTTPException(status_code=403, detail="Compra/venda é só para o dono")
    s = svc.criar_sessao(
        db,
        tipo=dados.tipo,
        data_sessao=dados.data or date.today(),
        lotes_origem=dados.lotes_origem,
        separar_lotes=dados.separar_lotes,
        sublotes=dados.sublotes,
        preco_kg=dados.preco_kg,
        preco_arroba=dados.preco_arroba,
        vendedor=dados.vendedor,
    )
    return svc.estado_sessao(db, s)


@router.delete("/{sessao_id}")
def cancelar(sessao_id: int, db: Session = Depends(get_db)):
    """Cancela (apaga) uma sessão aberta sem nenhuma pesagem — desistir de lançar."""
    s = _buscar_sessao(db, sessao_id)
    try:
        svc.cancelar_sessao(db, s)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True}


@router.get("/abertas")
def listar_abertas(db: Session = Depends(get_db)):
    """Sessões ainda abertas (para retomar de onde parou)."""
    abertas = (
        db.query(SessaoPesagem)
        .filter(SessaoPesagem.status == StatusSessao.ABERTA)
        .order_by(SessaoPesagem.id.desc())
        .all()
    )
    return [
        {
            "id": s.id,
            "tipo": s.tipo.value,
            "data": s.data,
            "origens": [l.nome for l in s.origens],
            "pesados": len(s.pesagens),
        }
        for s in abertas
    ]


@router.get("/{sessao_id}")
def estado(sessao_id: int, db: Session = Depends(get_db)):
    return svc.estado_sessao(db, _buscar_sessao(db, sessao_id))


@router.get("/{sessao_id}/info")
def info(sessao_id: int, brinco: str, db: Session = Depends(get_db)):
    """Consulta rápida ao digitar o brinco (tipo, último peso, GMD)."""
    return svc.info_animal(db, _buscar_sessao(db, sessao_id), brinco)


@router.post("/{sessao_id}/sublotes", status_code=201)
def criar_sublote(sessao_id: int, dados: schemas.SubloteCriar, db: Session = Depends(get_db)):
    s = _buscar_sessao(db, sessao_id)
    svc.adicionar_sublote(db, s, dados.nome)
    return svc.estado_sessao(db, s)


@router.post("/{sessao_id}/pesar")
def pesar(sessao_id: int, dados: schemas.PesarDados, db: Session = Depends(get_db)):
    s = _buscar_sessao(db, sessao_id)
    if s.status != StatusSessao.ABERTA:
        raise HTTPException(status_code=400, detail="Sessão já finalizada")
    return svc.registrar_pesagem(
        db, s,
        brinco=dados.brinco,
        peso=dados.peso,
        destino_lote=dados.destino_lote,
        observacao=dados.observacao,
        forcar=dados.forcar,
        criar_animal=dados.criar_animal,
        tipo=dados.tipo,
        animal_id=dados.animal_id,
        novo_tipo=dados.novo_tipo,
        nova_raca=dados.nova_raca,
        dentes=dados.dentes,
    )


@router.post("/{sessao_id}/pesar-sem-brinco")
def pesar_sem_brinco(sessao_id: int, dados: schemas.PesarSemBrinco,
                     db: Session = Depends(get_db)):
    s = _buscar_sessao(db, sessao_id)
    if s.status != StatusSessao.ABERTA:
        raise HTTPException(status_code=400, detail="Sessão já finalizada")
    return svc.pesar_sem_brinco(db, s, dados.peso, dados.destino_lote,
                                dados.observacao, dados.tipo)


@router.get("/{sessao_id}/faltantes")
def faltantes(sessao_id: int, db: Session = Depends(get_db)):
    s = _buscar_sessao(db, sessao_id)
    return {
        "faltantes": svc.faltantes(db, s),
        "provisorios": svc.pesados_provisorios(db, s),
    }


@router.post("/{sessao_id}/vincular")
def vincular(sessao_id: int, dados: schemas.VincularBrinco, db: Session = Depends(get_db),
             _dono=Depends(requer_dono)):
    s = _buscar_sessao(db, sessao_id)
    r = svc.vincular(db, s.data, dados.animal_temp_id, dados.animal_faltante_id, dados.novo_brinco)
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=r.get("erro", "Erro ao vincular"))
    return r


@router.get("/{sessao_id}/resumo")
def resumo(sessao_id: int, db: Session = Depends(get_db)):
    return svc.resumo(db, _buscar_sessao(db, sessao_id))


@router.post("/{sessao_id}/finalizar")
def finalizar(sessao_id: int, db: Session = Depends(get_db)):
    s = _buscar_sessao(db, sessao_id)
    return svc.finalizar(db, s)


@router.post("/{sessao_id}/reabrir")
def reabrir(sessao_id: int, db: Session = Depends(get_db), _dono=Depends(requer_dono)):
    """Reabre um manejo já finalizado, pra lançar animais esquecidos ou corrigir algo."""
    s = _buscar_sessao(db, sessao_id)
    svc.reabrir(db, s)
    return svc.estado_sessao(db, s)


@router.get("/{sessao_id}/exportar")
def exportar(sessao_id: int, db: Session = Depends(get_db)):
    """Exporta as pesagens da sessão em CSV."""
    s = _buscar_sessao(db, sessao_id)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["ordem", "brinco", "tipo", "peso_kg", "destino", "observacao", "data"])
    for p in sorted(s.pesagens, key=lambda x: x.ordem or 0):
        w.writerow([
            p.ordem, p.animal.brinco, p.animal.tipo or "", p.peso,
            p.destino_lote.nome if p.destino_lote else "",
            p.observacao or "", s.data.isoformat(),
        ])
    nome = f"sessao_{s.id}_{s.data.isoformat()}.csv"
    return Response(
        content=buf.getvalue().encode("utf-8-sig"),  # BOM p/ abrir certo no Excel
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


@router.put("/{sessao_id}/pesagens/{pesagem_id}")
def editar(sessao_id: int, pesagem_id: int, dados: schemas.PesagemEditar,
           db: Session = Depends(get_db), _dono=Depends(requer_dono)):
    s = _buscar_sessao(db, sessao_id)
    ok = svc.editar_pesagem(db, s, pesagem_id, dados.peso, dados.destino_lote, dados.observacao)
    if not ok:
        raise HTTPException(status_code=404, detail="Pesagem não encontrada nesta sessão")
    return {"ok": True}


@router.delete("/{sessao_id}/pesagens/{pesagem_id}")
def remover(sessao_id: int, pesagem_id: int, db: Session = Depends(get_db),
            _dono=Depends(requer_dono)):
    s = _buscar_sessao(db, sessao_id)
    ok = svc.remover_pesagem(db, s, pesagem_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Pesagem não encontrada nesta sessão")
    return {"ok": True}
