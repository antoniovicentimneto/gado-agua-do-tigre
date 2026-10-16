"""Endpoints da aba Pastos (piquetes, mudança de piquete, importação de áreas)."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import TipoArea, Usuario
from .. import schemas
from ..services import geo
from ..services import pastos as svc
from ..services.auth import requer_dono, usuario_atual

router = APIRouter(prefix="/api/pastos", tags=["pastos"], dependencies=[Depends(usuario_atual)])

TAMANHO_MAX_ARQUIVO = 15 * 1024 * 1024  # arquivo de áreas de fazenda é bem menor que isso


def _executar(funcao, *args, **kwargs):
    """Erro de regra de negócio vira 400 com a mensagem amigável (sem stack trace)."""
    try:
        return funcao(*args, **kwargs)
    except (svc.ErroPasto, geo.ArquivoInvalido) as e:
        raise HTTPException(status_code=400, detail=str(e))


def _tipo_area(valor: str | None) -> TipoArea:
    try:
        return TipoArea(valor or "propria")
    except ValueError:
        raise HTTPException(status_code=400, detail="Tipo de área inválido")


# ---------------------------------------------------------------- Consulta (todos)

@router.get("")
def painel(hoje: date | None = None, db: Session = Depends(get_db)):
    """Piquetes, lotes em cada um, descanso, lotes sem piquete e últimas mudanças.

    `hoje` vem do aparelho: o servidor roda em UTC e, à noite no Brasil, já estaria
    no dia seguinte (os dias de descanso sairiam com 1 a mais)."""
    return svc.painel(db, hoje)


@router.get("/lotes/{lote_id}/animais")
def animais_do_lote(lote_id: int, db: Session = Depends(get_db)):
    """Animais ativos do lote (tela de separar)."""
    return svc.animais_do_lote(db, lote_id)


# ---------------------------------------------------------------- Mudanças (peão também)

@router.post("/mover")
def mover(dados: schemas.PastoMover, db: Session = Depends(get_db),
          usuario: Usuario = Depends(usuario_atual)):
    return _executar(svc.mover, db, dados.lote_id, dados.piquete_id, dados.data,
                     dados.chave, usuario.nome)


@router.post("/juntar")
def juntar(dados: schemas.PastoJuntar, db: Session = Depends(get_db),
           usuario: Usuario = Depends(usuario_atual)):
    return _executar(svc.juntar, db, dados.origem_id, dados.destino_id, dados.data,
                     dados.chave, usuario.nome)


@router.post("/separar")
def separar(dados: schemas.PastoSeparar, db: Session = Depends(get_db),
            usuario: Usuario = Depends(usuario_atual)):
    return _executar(
        svc.separar, db, dados.origem_id, dados.animal_ids,
        novo_lote=dados.novo_lote, lote_destino_id=dados.lote_destino_id,
        piquete_id=dados.piquete_id, quando=dados.data, chave=dados.chave,
        usuario=usuario.nome,
    )


@router.post("/movimentacoes/{mov_id}/desfazer")
def desfazer(mov_id: int, db: Session = Depends(get_db)):
    return _executar(svc.desfazer, db, mov_id)


# ---------------------------------------------------------------- Cadastro (só dono)

@router.post("/areas", status_code=201)
def criar_area(dados: schemas.AreaPastoEntrada, db: Session = Depends(get_db),
               _dono=Depends(requer_dono)):
    return _executar(svc.salvar_area, db, dados.nome, _tipo_area(dados.tipo), dados.observacao)


@router.put("/areas/{area_id}")
def editar_area(area_id: int, dados: schemas.AreaPastoEntrada, db: Session = Depends(get_db),
                _dono=Depends(requer_dono)):
    return _executar(svc.salvar_area, db, dados.nome, _tipo_area(dados.tipo),
                     dados.observacao, area_id)


@router.post("/piquetes", status_code=201)
def criar_piquete(dados: schemas.PiqueteEntrada, db: Session = Depends(get_db),
                  _dono=Depends(requer_dono)):
    return _executar(svc.salvar_piquete, db, dados.model_dump(exclude_unset=True))


@router.put("/piquetes/{piquete_id}")
def editar_piquete(piquete_id: int, dados: schemas.PiqueteEntrada,
                   db: Session = Depends(get_db), _dono=Depends(requer_dono)):
    return _executar(svc.salvar_piquete, db, dados.model_dump(exclude_unset=True), piquete_id)


@router.delete("/piquetes/{piquete_id}")
def remover_piquete(piquete_id: int, db: Session = Depends(get_db), _dono=Depends(requer_dono)):
    return _executar(svc.remover_piquete, db, piquete_id)


@router.post("/importar/ler")
async def importar_ler(arquivo: UploadFile = File(...), _dono=Depends(requer_dono)):
    """1º passo: lê o arquivo e devolve as áreas encontradas (nada é gravado ainda)."""
    conteudo = await arquivo.read(TAMANHO_MAX_ARQUIVO + 1)
    if len(conteudo) > TAMANHO_MAX_ARQUIVO:
        raise HTTPException(status_code=400, detail="Arquivo grande demais (máximo 15 MB).")
    achados = _executar(geo.ler_arquivo_areas, arquivo.filename or "", conteudo)
    return {"arquivo": arquivo.filename, "areas": achados}


@router.post("/importar/confirmar")
def importar_confirmar(
    areas: list[dict] = Body(...),
    selecionados: list[int] | None = Body(None),
    area_padrao: str | None = Body(None),
    tipo_area: str | None = Body(None),
    db: Session = Depends(get_db),
    _dono=Depends(requer_dono),
):
    """2º passo: grava os piquetes que o dono marcou na prévia."""
    limpos = []
    for a in areas:
        g = _executar(geo.validar_geometria, a.get("geometria"))
        limpos.append({
            "nome": str(a.get("nome") or "").strip()[:80] or f"Piquete {len(limpos) + 1}",
            "area": (str(a.get("area") or "").strip()[:80] or None),
            "geometria": g,
            # Área informada no arquivo (prévia) vale mais que a calculada.
            "hectares": geo.numero_br(a.get("hectares_arquivo")) or geo.hectares(g),
        })
    return _executar(svc.importar, db, limpos, selecionados, area_padrao, _tipo_area(tipo_area))
