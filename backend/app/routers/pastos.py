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
from ..services import pastos_historico as hist
from ..services import peso_estimado as pe
from ..services import indicadores_pasto as ind
from ..services import alertas as svc_alertas
from ..services import cronograma as svc_crono
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


@router.put("/lotes/{lote_id}/visual")
def visual_lote(lote_id: int, dados: schemas.LoteVisual, db: Session = Depends(get_db)):
    """Cor e ícone do lote no mapa (qualquer usuário: ajuda o peão a reconhecer o lote)."""
    return _executar(svc.salvar_visual_lote, db, lote_id, dados.cor, dados.icone)


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
    destino: str = Body("piquetes"),  # piquetes / divisa / uso
    uso: str | None = Body(None),     # com destino "uso": lavoura, madeira, reserva...
    pasto: str | None = Body(None),   # piquetes: pastagem padrão (cada linha pode ter a sua)
    uso_piquete: str | None = Body(None),  # piquetes: perene / inverno / verao
    db: Session = Depends(get_db),
    _dono=Depends(requer_dono),
):
    """2º passo: grava o que o dono marcou na prévia — como piquetes do gado, como a
    divisa da fazenda ou como áreas de outros usos (só aparecem no mapa)."""
    limpos = []
    for a in areas:
        g = _executar(geo.validar_geometria, a.get("geometria"))
        limpos.append({
            "nome": str(a.get("nome") or "").strip()[:80] or f"Piquete {len(limpos) + 1}",
            "area": (str(a.get("area") or "").strip()[:80] or None),
            "geometria": g,
            # Área informada no arquivo (prévia) vale mais que a calculada.
            "hectares": geo.numero_br(a.get("hectares_arquivo")) or geo.hectares(g),
            "pasto": (str(a.get("pasto") or "").strip()[:60] or None),
            "uso": (str(a.get("uso") or "").strip() or None),
        })
    if destino in ("divisa", "uso"):
        return _executar(svc.importar_camadas, db, limpos, selecionados, destino, uso)
    return _executar(svc.importar, db, limpos, selecionados, area_padrao, _tipo_area(tipo_area),
                     pasto, uso_piquete)


@router.put("/camadas/{camada_id}")
def editar_camada(camada_id: int, dados: schemas.CamadaEditar, db: Session = Depends(get_db),
                  _dono=Depends(requer_dono)):
    return _executar(svc.editar_camada, db, camada_id, dados.nome, dados.uso)


@router.delete("/camadas/{camada_id}")
def remover_camada(camada_id: int, db: Session = Depends(get_db), _dono=Depends(requer_dono)):
    return _executar(svc.remover_camada, db, camada_id)



# ---------------------------------------------------------------- Histórico do piquete

@router.get("/piquetes/{piquete_id}/historico")
def historico_piquete(piquete_id: int, hoje: date | None = None, db: Session = Depends(get_db)):
    """Ocupações com a foto de cada uma (cabeças, UA, UA/ha), pastos e divisões."""
    return _executar(hist.historico, db, piquete_id, hoje)


@router.post("/piquetes/{piquete_id}/pasto", status_code=201)
def adicionar_pasto(piquete_id: int, dados: schemas.PastoEntrada, db: Session = Depends(get_db),
                    _dono=Depends(requer_dono)):
    return _executar(hist.adicionar_pasto, db, piquete_id, dados.especie, dados.inicio,
                     dados.substitui, dados.observacao)


@router.put("/pasto/{periodo_id}/encerrar")
def encerrar_pasto(periodo_id: int, dados: schemas.PastoEncerrar, db: Session = Depends(get_db),
                   _dono=Depends(requer_dono)):
    return _executar(hist.encerrar_pasto, db, periodo_id, dados.fim)


@router.delete("/pasto/{periodo_id}")
def apagar_pasto(periodo_id: int, db: Session = Depends(get_db), _dono=Depends(requer_dono)):
    return _executar(hist.apagar_pasto, db, periodo_id)


@router.post("/piquetes/{piquete_id}/dividir")
def dividir_piquete(piquete_id: int, dados: schemas.DividirPiquete, db: Session = Depends(get_db),
                    dono: Usuario = Depends(requer_dono)):
    return _executar(hist.dividir, db, piquete_id, dados.partes, dados.data, dados.destinos, dono.nome)


# ---------------------------------------------------------------- GMD de referência por época

@router.get("/config-gmd")
def config_gmd(db: Session = Depends(get_db)):
    return {"epocas": pe.carregar_referencia(db), "limite_dias": pe.LIMITE_DIAS}


@router.put("/config-gmd")
def salvar_config_gmd(epocas: list[dict] = Body(..., embed=True), db: Session = Depends(get_db),
                      _dono=Depends(requer_dono)):
    try:
        return {"epocas": pe.salvar_referencia(db, epocas), "limite_dias": pe.LIMITE_DIAS}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))



# ---------------------------------------------------------------- Indicadores de rotação

@router.get("/indicadores")
def indicadores(inicio: date | None = None, fim: date | None = None, hoje: date | None = None,
                db: Session = Depends(get_db)):
    """Lotação (UA/ha), ocupação e descanso médios, uso da área; por época, piquete e pasto.
    Sem datas = safra atual (julho a junho)."""
    return ind.indicadores(db, inicio, fim, hoje)



# ---------------------------------------------------------------- Alertas (sininho)

@router.get("/alertas")
def alertas(hoje: date | None = None, db: Session = Depends(get_db)):
    """O que precisa de atenção hoje: mudar lote, piquete pronto, salgar, pesar."""
    return svc_alertas.alertas(db, hoje)


@router.put("/alertas/limites")
def salvar_limites_alertas(dados: dict = Body(...), db: Session = Depends(get_db),
                           _dono=Depends(requer_dono)):
    try:
        return svc_alertas.salvar_limites(db, dados)
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e) or "Valor inválido")



# ---------------------------------------------------------------- Cronograma de rotação

@router.get("/cronograma")
def cronograma_geral(hoje: date | None = None, db: Session = Depends(get_db)):
    """Fila de próximos piquetes de todos os lotes que estão em piquete, com as datas."""
    return svc_crono.visao_geral(db, hoje)


@router.get("/lotes/{lote_id}/cronograma")
def cronograma_lote(lote_id: int, hoje: date | None = None, db: Session = Depends(get_db)):
    return _executar(svc_crono.cronograma_lote, db, lote_id, hoje)


@router.put("/lotes/{lote_id}/cronograma")
def salvar_cronograma(lote_id: int, itens: list[dict] = Body(...), dias_atual: int | None = Body(None),
                      db: Session = Depends(get_db)):
    return _executar(svc_crono.salvar, db, lote_id, itens, dias_atual)


@router.post("/lotes/{lote_id}/cronograma/avancar")
def avancar_cronograma(lote_id: int, dados: dict = Body({}), db: Session = Depends(get_db),
                       usuario: Usuario = Depends(usuario_atual)):
    quando = date.fromisoformat(dados["data"]) if dados.get("data") else None
    return _executar(svc_crono.avancar, db, lote_id, quando, dados.get("chave"), usuario.nome)



# ---------------------------------------------------------------- Unir e editar em massa (dono)

@router.post("/piquetes/unir")
def unir_piquetes(dados: dict = Body(...), db: Session = Depends(get_db),
                  dono: Usuario = Depends(requer_dono)):
    quando = date.fromisoformat(dados["data"]) if dados.get("data") else None
    return _executar(hist.unir, db, dados.get("ids") or [], dados.get("nome"), quando,
                     dados.get("pasto"), dono.nome)


@router.post("/piquetes/massa")
def editar_piquetes_em_massa(dados: dict = Body(...), db: Session = Depends(get_db),
                             _dono=Depends(requer_dono)):
    return _executar(hist.editar_em_massa, db, dados.get("ids") or [], dados)
