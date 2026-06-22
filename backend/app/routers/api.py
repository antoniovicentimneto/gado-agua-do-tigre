"""Endpoints JSON da API."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    Animal,
    AnimalLote,
    Denticao,
    Lote,
    Pesagem,
    Score,
    StatusAnimal,
    Venda,
)
from .. import schemas
from ..services.auth import requer_dono, usuario_atual
from ..services.consultas import lote_atual, montar_resumo, pontos_pesagem
from ..services.exportacao import gerar_planilha, nome_arquivo
from ..services.gmd import gmd_periodo
from ..services.sessao import completar_venda_morto
from ..services.venda import calcular_venda, rendimento_padrao

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# Todo o router exige login. Endpoints sensíveis exigem DONO (Depends(requer_dono)).
router = APIRouter(prefix="/api", tags=["api"], dependencies=[Depends(usuario_atual)])


def _buscar_animal(db: Session, animal_id: int) -> Animal:
    animal = db.get(Animal, animal_id)
    if animal is None:
        raise HTTPException(status_code=404, detail="Animal não encontrado")
    return animal


# ---------------------------------------------------------------- Animais

@router.get("/animais")
def listar_animais(
    db: Session = Depends(get_db),
    busca: str | None = Query(None, description="Filtra por brinco"),
    lote: str | None = None,
    tipo: str | None = None,
    status: StatusAnimal | None = None,
):
    """Lista animais com último peso, GMD e uGMD calculados."""
    q = db.query(Animal)
    if busca:
        q = q.filter(Animal.brinco.contains(busca))
    if tipo:
        q = q.filter(Animal.tipo == tipo)
    if status:
        q = q.filter(Animal.status == status)

    resultado = []
    for animal in q.order_by(Animal.brinco).all():
        resumo = montar_resumo(animal)
        if lote and resumo["lote_atual"] != lote:
            continue
        resultado.append(resumo)
    return resultado


@router.post("/animais", status_code=201)
def criar_animal(dados: schemas.AnimalCriar, db: Session = Depends(get_db),
                 _dono=Depends(requer_dono)):
    animal = Animal(**dados.model_dump())
    db.add(animal)
    db.commit()
    db.refresh(animal)
    return montar_resumo(animal)


@router.get("/animais/{animal_id}")
def detalhar_animal(animal_id: int, db: Session = Depends(get_db)):
    animal = _buscar_animal(db, animal_id)
    resumo = montar_resumo(animal)
    resumo["pesagens"] = [
        {"id": p.id, "data": p.data, "peso": p.peso} for p in animal.pesagens
    ]
    resumo["denticoes"] = [
        {"id": d.id, "data": d.data, "dentes": d.dentes} for d in animal.denticoes
    ]
    resumo["scores"] = [
        {"id": s.id, "data": s.data, "valor": s.valor} for s in animal.scores
    ]
    resumo["lotes"] = [
        {
            "lote": al.lote.nome,
            "data_inicio": al.data_inicio,
            "data_fim": al.data_fim,
        }
        for al in animal.lotes
    ]
    return resumo


@router.put("/animais/{animal_id}")
def atualizar_animal(
    animal_id: int, dados: schemas.AnimalAtualizar, db: Session = Depends(get_db),
    _dono=Depends(requer_dono),
):
    animal = _buscar_animal(db, animal_id)
    for campo, valor in dados.model_dump(exclude_unset=True).items():
        setattr(animal, campo, valor)
    db.commit()
    db.refresh(animal)
    return montar_resumo(animal)


# ---------------------------------------------------------------- Pesagens

@router.post("/animais/{animal_id}/pesagens", status_code=201)
def adicionar_pesagem(
    animal_id: int, dados: schemas.PesagemCriar, db: Session = Depends(get_db)
):
    _buscar_animal(db, animal_id)
    # Se já existe pesagem nessa data, atualiza o peso (evita duplicar).
    existente = (
        db.query(Pesagem)
        .filter(Pesagem.animal_id == animal_id, Pesagem.data == dados.data)
        .first()
    )
    if existente:
        existente.peso = dados.peso
    else:
        db.add(Pesagem(animal_id=animal_id, data=dados.data, peso=dados.peso))
    db.commit()
    return {"ok": True}


@router.post("/pesagem-rapida")
def pesagem_rapida(dados: schemas.PesagemRapida, db: Session = Depends(get_db)):
    """Registro de curral: encontra o animal pelo brinco e lança o peso.

    Se houver mais de um animal com o mesmo brinco (brincos repetidos existem na
    base antiga), retorna a lista para o usuário escolher.
    """
    animais = db.query(Animal).filter(Animal.brinco == dados.brinco).all()
    if not animais:
        raise HTTPException(status_code=404, detail=f"Brinco {dados.brinco} não encontrado")
    if len(animais) > 1:
        return {
            "ambiguidade": True,
            "mensagem": f"Existem {len(animais)} animais com o brinco {dados.brinco}.",
            "animais": [montar_resumo(a) for a in animais],
        }
    animal = animais[0]
    existente = (
        db.query(Pesagem)
        .filter(Pesagem.animal_id == animal.id, Pesagem.data == dados.data)
        .first()
    )
    if existente:
        existente.peso = dados.peso
    else:
        db.add(Pesagem(animal_id=animal.id, data=dados.data, peso=dados.peso))
    db.commit()
    return {"ok": True, "animal": montar_resumo(animal)}


# ---------------------------------------------------- Dentição e Score

@router.post("/animais/{animal_id}/denticoes", status_code=201)
def adicionar_denticao(
    animal_id: int, dados: schemas.DenticaoCriar, db: Session = Depends(get_db)
):
    _buscar_animal(db, animal_id)
    db.add(Denticao(animal_id=animal_id, data=dados.data, dentes=dados.dentes))
    db.commit()
    return {"ok": True}


@router.post("/animais/{animal_id}/scores", status_code=201)
def adicionar_score(
    animal_id: int, dados: schemas.ScoreCriar, db: Session = Depends(get_db)
):
    _buscar_animal(db, animal_id)
    db.add(Score(animal_id=animal_id, data=dados.data, valor=dados.valor))
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- GMD período

@router.get("/animais/{animal_id}/gmd-periodo")
def gmd_por_periodo(
    animal_id: int,
    inicio: date | None = None,
    fim: date | None = None,
    db: Session = Depends(get_db),
):
    """GMD do animal dentro de um intervalo (para comparar pastagens/safras)."""
    animal = _buscar_animal(db, animal_id)
    resultado = gmd_periodo(pontos_pesagem(animal), inicio, fim)
    if resultado is None:
        raise HTTPException(
            status_code=400,
            detail="Pesagens insuficientes no período para calcular GMD",
        )
    return resultado


# ---------------------------------------------------------------- Lotes

@router.get("/lotes")
def listar_lotes(somente_ativos: bool = False, db: Session = Depends(get_db)):
    """Lista os lotes. Com `somente_ativos=true`, devolve apenas os lotes que têm
    animais ATIVOS na fazenda agora (com a contagem) — usado na tela de pesagem."""
    if somente_ativos:
        ids_por_nome = {l.nome: l.id for l in db.query(Lote).all()}
        contagem: dict[str, int] = {}
        for animal in db.query(Animal).filter(Animal.status == StatusAnimal.ATIVO).all():
            nome = lote_atual(animal)
            if nome:
                contagem[nome] = contagem.get(nome, 0) + 1
        return [
            {"id": ids_por_nome.get(nome), "nome": nome, "ativos": qtd}
            for nome, qtd in sorted(contagem.items())
        ]
    return [{"id": l.id, "nome": l.nome} for l in db.query(Lote).order_by(Lote.nome).all()]


@router.put("/lotes/{lote_id}")
def renomear_lote(lote_id: int, dados: schemas.LoteRenomear, db: Session = Depends(get_db)):
    """Renomeia um lote (mantém o histórico, pois é a mesma entidade)."""
    lote = db.get(Lote, lote_id)
    if lote is None:
        raise HTTPException(status_code=404, detail="Lote não encontrado")
    novo = dados.nome.strip()
    existente = db.query(Lote).filter(Lote.nome == novo, Lote.id != lote_id).first()
    if existente:
        raise HTTPException(
            status_code=400,
            detail=f"Já existe um lote '{novo}'. Use 'Juntar' para fundir os dois.",
        )
    lote.nome = novo
    db.commit()
    return {"ok": True, "id": lote.id, "nome": lote.nome}


def _mover_animal(db: Session, animal: Animal, destino: Lote, quando: date) -> None:
    """Fecha o vínculo de lote atual e abre um novo no destino (preserva histórico)."""
    for al in animal.lotes:
        if al.data_fim is None:
            al.data_fim = quando
    db.add(AnimalLote(animal_id=animal.id, lote_id=destino.id, data_inicio=quando))


@router.post("/lotes/mover")
def mover_animais(dados: schemas.LoteMover, db: Session = Depends(get_db)):
    """Move os animais selecionados para outro lote."""
    destino = db.query(Lote).filter(Lote.nome == dados.destino.strip()).first()
    if destino is None:
        destino = Lote(nome=dados.destino.strip())
        db.add(destino)
        db.flush()
    hoje = date.today()
    movidos = 0
    for animal_id in dados.animal_ids:
        animal = db.get(Animal, animal_id)
        if animal is None:
            continue
        if lote_atual(animal) == destino.nome:
            continue
        _mover_animal(db, animal, destino, hoje)
        movidos += 1
    db.commit()
    return {"ok": True, "movidos": movidos, "destino": destino.nome}


@router.post("/lotes/juntar")
def juntar_lotes(dados: schemas.LoteJuntar, db: Session = Depends(get_db)):
    """Junta um lote em outro: move todos os animais ativos da origem para o destino."""
    origem = db.get(Lote, dados.origem_id)
    if origem is None:
        raise HTTPException(status_code=404, detail="Lote de origem não encontrado")
    destino = db.query(Lote).filter(Lote.nome == dados.destino.strip()).first()
    if destino is None:
        destino = Lote(nome=dados.destino.strip())
        db.add(destino)
        db.flush()
    if destino.id == origem.id:
        raise HTTPException(status_code=400, detail="Origem e destino são o mesmo lote")

    hoje = date.today()
    movidos = 0
    for animal in db.query(Animal).filter(Animal.status == StatusAnimal.ATIVO).all():
        if lote_atual(animal) == origem.nome:
            _mover_animal(db, animal, destino, hoje)
            movidos += 1
    db.commit()
    return {"ok": True, "movidos": movidos, "origem": origem.nome, "destino": destino.nome}


@router.post("/animais/{animal_id}/lote")
def mudar_lote(
    animal_id: int,
    nome_lote: str = Query(..., description="Nome do novo lote"),
    data_mudanca: date | None = None,
    db: Session = Depends(get_db),
):
    """Move o animal para um novo lote, fechando o vínculo anterior (histórico)."""
    animal = _buscar_animal(db, animal_id)
    hoje = data_mudanca or date.today()

    lote = db.query(Lote).filter(Lote.nome == nome_lote).first()
    if lote is None:
        lote = Lote(nome=nome_lote)
        db.add(lote)
        db.flush()

    for al in animal.lotes:
        if al.data_fim is None:
            al.data_fim = hoje

    db.add(AnimalLote(animal_id=animal.id, lote_id=lote.id, data_inicio=hoje))
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- Venda

@router.get("/animais/{animal_id}/venda/simular")
def simular_venda(
    animal_id: int,
    preco_arroba: float,
    rendimento: float | None = None,
    peso: float | None = None,
    db: Session = Depends(get_db),
    _dono=Depends(requer_dono),
):
    """Simula a venda: puxa rendimento padrão pelo tipo e peso da última pesagem."""
    animal = _buscar_animal(db, animal_id)
    if rendimento is None:
        rendimento = rendimento_padrao(animal.tipo)
    if peso is None:
        if not animal.pesagens:
            raise HTTPException(status_code=400, detail="Animal sem pesagem")
        peso = animal.pesagens[-1].peso
    calc = calcular_venda(peso, rendimento, preco_arroba)
    return {"peso": peso, "rendimento": rendimento, "preco_arroba": preco_arroba, **calc}


@router.get("/vendas/pendentes")
def vendas_pendentes(db: Session = Depends(get_db), _dono=Depends(requer_dono)):
    """Vendas no gancho aguardando a tabela do frigorífico (rendimento + carcaça)."""
    vendas = db.query(Venda).filter(Venda.pendente == True).all()  # noqa: E712
    return [
        {
            "animal_id": v.animal_id,
            "brinco": v.animal.brinco,
            "tipo": v.animal.tipo,
            "data": v.data,
            "peso_vivo": v.peso,
        }
        for v in vendas
    ]


@router.post("/animais/{animal_id}/venda/completar")
def completar_venda(
    animal_id: int, dados: schemas.CompletarVendaMorto, db: Session = Depends(get_db),
    _dono=Depends(requer_dono),
):
    """Fecha a venda no gancho com rendimento + peso de carcaça + preço da @."""
    animal = _buscar_animal(db, animal_id)
    r = completar_venda_morto(db, animal, dados.rendimento, dados.peso_carcaca,
                              dados.preco_arroba)
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=r.get("erro", "Erro"))
    return r


@router.post("/animais/{animal_id}/venda")
def registrar_venda(
    animal_id: int, dados: schemas.VendaCriar, db: Session = Depends(get_db),
    _dono=Depends(requer_dono),
):
    """Registra a venda e marca o animal como VENDIDO."""
    animal = _buscar_animal(db, animal_id)
    calc = calcular_venda(dados.peso, dados.rendimento, dados.preco_arroba)

    venda = animal.venda or Venda(animal_id=animal.id)
    venda.data = dados.data or date.today()
    venda.peso = dados.peso
    venda.rendimento = dados.rendimento
    venda.preco_arroba = dados.preco_arroba
    venda.valor_recebido = calc["valor_recebido"]
    db.add(venda)
    animal.status = StatusAnimal.VENDIDO
    db.commit()
    return {"ok": True, **calc}


# ---------------------------------------------------------------- Dashboard

@router.get("/exportar/excel")
def exportar_excel(db: Session = Depends(get_db), _dono=Depends(requer_dono)):
    """Gera e baixa uma planilha .xlsx completa do rebanho (backup de fácil acesso)."""
    conteudo = gerar_planilha(db)
    return Response(
        content=conteudo,
        media_type=XLSX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{nome_arquivo()}"'},
    )


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    """Números gerais do rebanho."""
    total = db.query(func.count(Animal.id)).scalar()
    ativos = (
        db.query(func.count(Animal.id))
        .filter(Animal.status == StatusAnimal.ATIVO)
        .scalar()
    )
    vendidos = (
        db.query(func.count(Animal.id))
        .filter(Animal.status == StatusAnimal.VENDIDO)
        .scalar()
    )

    # GMD médio do rebanho ativo (média dos GMDs individuais).
    gmds = []
    for animal in db.query(Animal).filter(Animal.status == StatusAnimal.ATIVO).all():
        r = montar_resumo(animal)
        if r["gmd"] is not None:
            gmds.append(r["gmd"])
    gmd_medio = round(sum(gmds) / len(gmds), 3) if gmds else None

    return {
        "total": total,
        "ativos": ativos,
        "vendidos": vendidos,
        "gmd_medio": gmd_medio,
        "pesagens": db.query(func.count(Pesagem.id)).scalar(),
    }
