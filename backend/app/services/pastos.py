"""Regras de negócio dos pastos: piquetes, onde cada lote está e as mudanças de piquete.

Cada mudança (mover, separar, juntar) vira uma MovimentacaoPasto que guarda as linhas
criadas e fechadas — é isso que permite o "Desfazer" exato, sem adivinhação.
"""
from __future__ import annotations

import json
from datetime import date

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, selectinload

from ..models import (
    Animal,
    AnimalLote,
    AreaPasto,
    LotePiquete,
    Lote,
    MovimentacaoPasto,
    Pesagem,
    Piquete,
    StatusAnimal,
    TipoArea,
    sessao_origem,
    sessao_sublote,
)
from . import geo

KG_POR_UA = 450  # 1 UA = 450 kg de peso vivo (mesma regra do resto do app)


class ErroPasto(ValueError):
    """Erro de regra de negócio — a mensagem é mostrada ao usuário como está."""


# ---------------------------------------------------------------- Consultas de apoio

def _rebanho_por_lote(db: Session) -> dict[int, dict]:
    """Cabeças ativas e soma do último peso de cada lote — em 2 consultas, não 1 por animal
    (o banco fica longe do servidor; consulta por animal deixa a tela lenta)."""
    vinculos = db.execute(
        select(AnimalLote.lote_id, AnimalLote.animal_id)
        .join(Animal, Animal.id == AnimalLote.animal_id)
        .where(AnimalLote.data_fim.is_(None), Animal.status == StatusAnimal.ATIVO)
    ).all()
    if not vinculos:
        return {}

    ultima = (
        select(Pesagem.animal_id, func.max(Pesagem.data).label("d"))
        .group_by(Pesagem.animal_id)
        .subquery()
    )
    pesos: dict[int, float] = {}
    for animal_id, peso in db.execute(
        select(Pesagem.animal_id, Pesagem.peso).join(
            ultima, and_(Pesagem.animal_id == ultima.c.animal_id, Pesagem.data == ultima.c.d)
        )
    ):
        # Duas pesagens no mesmo dia: fica a maior (evita somar o animal duas vezes).
        pesos[animal_id] = max(peso, pesos.get(animal_id, 0))

    por_lote: dict[int, dict] = {}
    vistos: set[int] = set()
    for lote_id, animal_id in vinculos:
        if animal_id in vistos:  # vínculo aberto duplicado: conta o animal uma vez só
            continue
        vistos.add(animal_id)
        r = por_lote.setdefault(lote_id, {"cabecas": 0, "peso": 0.0, "com_peso": 0})
        r["cabecas"] += 1
        if animal_id in pesos:
            r["peso"] += pesos[animal_id]
            r["com_peso"] += 1
    return por_lote


def _resumo_lote(lote: Lote, reb: dict | None) -> dict:
    reb = reb or {"cabecas": 0, "peso": 0.0, "com_peso": 0}
    return {
        "id": lote.id,
        "nome": lote.nome,
        "cabecas": reb["cabecas"],
        "ua": round(reb["peso"] / KG_POR_UA, 1) if reb["peso"] else 0,
        "peso_medio": round(reb["peso"] / reb["com_peso"], 1) if reb["com_peso"] else None,
    }


def _ocupacao_aberta(db: Session, lote_id: int) -> LotePiquete | None:
    return (
        db.query(LotePiquete)
        .filter(LotePiquete.lote_id == lote_id, LotePiquete.data_saida.is_(None))
        .order_by(LotePiquete.data_entrada.desc(), LotePiquete.id.desc())
        .first()
    )


def _hoje() -> date:
    return date.today()


# ---------------------------------------------------------------- Painel

def painel(db: Session, hoje: date | None = None) -> dict:
    """Tudo o que a aba Pastos precisa numa chamada só: áreas, piquetes com os lotes que
    estão em cada um, status de descanso, lotes sem piquete e as últimas mudanças."""
    hoje = hoje or _hoje()
    reb = _rebanho_por_lote(db)

    piquetes = (
        db.query(Piquete).filter(Piquete.ativo.is_(True))
        .options(selectinload(Piquete.area))
        .order_by(Piquete.nome).all()
    )
    abertas = (
        db.query(LotePiquete).filter(LotePiquete.data_saida.is_(None))
        .options(selectinload(LotePiquete.lote)).all()
    )
    ultima_saida = dict(db.execute(
        select(LotePiquete.piquete_id, func.max(LotePiquete.data_saida))
        .where(LotePiquete.data_saida.is_not(None))
        .group_by(LotePiquete.piquete_id)
    ).all())

    # Lote que esvaziou fora daqui (venda, mangueira...) continua com a ocupação aberta.
    # Pra não mostrar piquete "ocupado" por 0 cabeças, a saída efetiva dele é a data em
    # que o último animal saiu do lote.
    vazios = {o.lote_id for o in abertas if reb.get(o.lote_id, {}).get("cabecas", 0) == 0}
    saida_lote_vazio = dict(db.execute(
        select(AnimalLote.lote_id, func.max(AnimalLote.data_fim))
        .where(AnimalLote.lote_id.in_(vazios))
        .group_by(AnimalLote.lote_id)
    ).all()) if vazios else {}

    ocupantes: dict[int, list[dict]] = {}
    lotes_com_piquete: set[int] = set()
    for o in abertas:
        lotes_com_piquete.add(o.lote_id)
        if o.lote_id in vazios:
            fim = saida_lote_vazio.get(o.lote_id) or o.data_entrada
            if fim and (ultima_saida.get(o.piquete_id) is None or fim > ultima_saida[o.piquete_id]):
                ultima_saida[o.piquete_id] = fim
            continue
        item = _resumo_lote(o.lote, reb.get(o.lote_id))
        item["data_entrada"] = o.data_entrada.isoformat()
        item["dias"] = (hoje - o.data_entrada).days
        ocupantes.setdefault(o.piquete_id, []).append(item)

    lista = []
    for p in piquetes:
        lotes = sorted(ocupantes.get(p.id, []), key=lambda x: x["nome"])
        saida = ultima_saida.get(p.id)
        if lotes:
            status = "ocupado"
            dias = max(l["dias"] for l in lotes)
        elif saida is None:
            status, dias = "sem_registro", None
        else:
            dias = (hoje - saida).days
            meta = p.descanso_meta_dias
            status = "pronto" if (meta and dias >= meta) else "descansando"
        cab = sum(l["cabecas"] for l in lotes)
        ua = round(sum(l["ua"] for l in lotes), 1)
        lista.append({
            "id": p.id,
            "nome": p.nome,
            "area_id": p.area_id,
            "area": p.area.nome if p.area else None,
            "hectares": p.hectares,
            "capim": p.capim,
            "descanso_meta_dias": p.descanso_meta_dias,
            "observacao": p.observacao,
            "geometria": json.loads(p.geometria) if p.geometria else None,
            "status": status,
            "dias": dias,
            "ultima_saida": saida.isoformat() if saida else None,
            "lotes": lotes,
            "cabecas": cab,
            "ua": ua,
            "ua_ha": round(ua / p.hectares, 2) if (p.hectares and ua) else None,
        })

    ocupando = {o.lote_id for o in abertas if o.lote_id not in vazios}
    sem_piquete = []
    ids_sem = [lid for lid, r in reb.items() if r["cabecas"] > 0 and lid not in ocupando]
    if ids_sem:
        for lote in db.query(Lote).filter(Lote.id.in_(ids_sem)).order_by(Lote.nome).all():
            sem_piquete.append(_resumo_lote(lote, reb[lote.id]))

    areas = [
        {"id": a.id, "nome": a.nome, "tipo": a.tipo.value, "observacao": a.observacao}
        for a in db.query(AreaPasto).order_by(AreaPasto.nome).all()
    ]
    return {
        "hoje": hoje.isoformat(),
        "areas": areas,
        "piquetes": lista,
        "sem_piquete": sem_piquete,
        "movimentacoes": movimentacoes_recentes(db),
    }


def movimentacoes_recentes(db: Session, limite: int = 15) -> list[dict]:
    movs = (
        db.query(MovimentacaoPasto)
        .order_by(MovimentacaoPasto.id.desc())
        .limit(limite).all()
    )
    return [_mov_dict(m) for m in movs]


def _mov_dict(m: MovimentacaoPasto) -> dict:
    return {
        "id": m.id,
        "tipo": m.tipo,
        "data": m.data.isoformat(),
        "resumo": m.resumo,
        "usuario": m.usuario_nome,
        "desfeita": m.desfeita,
        "chave": m.chave_cliente,
    }


def animais_do_lote(db: Session, lote_id: int) -> list[dict]:
    """Animais ativos do lote, com o último peso (pra tela de separar)."""
    animais = (
        db.query(Animal)
        .join(AnimalLote, AnimalLote.animal_id == Animal.id)
        .filter(AnimalLote.lote_id == lote_id, AnimalLote.data_fim.is_(None),
                Animal.status == StatusAnimal.ATIVO)
        .options(selectinload(Animal.pesagens))
        .all()
    )
    saida = []
    for a in animais:
        ultima = max(a.pesagens, key=lambda p: (p.data, p.id)) if a.pesagens else None
        saida.append({
            "id": a.id,
            "brinco": a.brinco,
            "tipo": a.tipo,
            "raca": a.raca,
            "ultimo_peso": ultima.peso if ultima else None,
        })
    return sorted(saida, key=lambda x: (len(x["brinco"] or ""), x["brinco"] or ""))


# ---------------------------------------------------------------- Movimentações

def _ja_feita(db: Session, chave: str | None) -> MovimentacaoPasto | None:
    if not chave:
        return None
    return db.query(MovimentacaoPasto).filter(MovimentacaoPasto.chave_cliente == chave).first()


def _validar_data(quando: date | None) -> date:
    quando = quando or _hoje()
    if quando > _hoje():
        raise ErroPasto("A data não pode ser no futuro.")
    return quando


def _piquete_ativo(db: Session, piquete_id: int) -> Piquete:
    p = db.get(Piquete, piquete_id)
    if p is None or not p.ativo:
        raise ErroPasto("Piquete não encontrado.")
    return p


def _lote(db: Session, lote_id: int) -> Lote:
    lote = db.get(Lote, lote_id)
    if lote is None:
        raise ErroPasto("Lote não encontrado.")
    return lote


def _vinculos_abertos(db: Session, lote_id: int, animal_ids: list[int] | None = None):
    q = (
        db.query(AnimalLote)
        .join(Animal, Animal.id == AnimalLote.animal_id)
        .filter(AnimalLote.lote_id == lote_id, AnimalLote.data_fim.is_(None),
                Animal.status == StatusAnimal.ATIVO)
    )
    if animal_ids is not None:
        q = q.filter(AnimalLote.animal_id.in_(animal_ids))
    return q.all()


def _fechar_ocupacao(db: Session, lote_id: int, quando: date, alt: dict) -> LotePiquete | None:
    atual = _ocupacao_aberta(db, lote_id)
    if atual is None:
        return None
    if quando < atual.data_entrada:
        raise ErroPasto(
            f"A data é anterior à entrada do lote nesse piquete "
            f"({atual.data_entrada.strftime('%d/%m/%Y')})."
        )
    atual.data_saida = quando
    alt["lp_fechados"].append(atual.id)
    return atual


def _abrir_ocupacao(db: Session, lote_id: int, piquete_id: int, quando: date,
                    cabecas: int, alt: dict) -> LotePiquete:
    nova = LotePiquete(lote_id=lote_id, piquete_id=piquete_id, data_entrada=quando, cabecas=cabecas)
    db.add(nova)
    db.flush()
    alt["lp_criados"].append(nova.id)
    return nova


def _trocar_lote(db: Session, vinculos: list[AnimalLote], destino_id: int, quando: date,
                 alt: dict) -> int:
    """Fecha o vínculo atual de cada animal e abre no lote destino (histórico preservado)."""
    for v in vinculos:
        if v.data_inicio and quando < v.data_inicio:
            raise ErroPasto("A data é anterior à entrada de algum animal no lote atual.")
        v.data_fim = quando
        alt["al_fechados"].append(v.id)
        novo = AnimalLote(animal_id=v.animal_id, lote_id=destino_id, data_inicio=quando)
        db.add(novo)
        db.flush()
        alt["al_criados"].append(novo.id)
    return len(vinculos)


def _novo_alt() -> dict:
    return {"lp_criados": [], "lp_fechados": [], "al_criados": [], "al_fechados": [],
            "lotes_criados": []}


def _registrar(db: Session, tipo: str, quando: date, resumo: str, alt: dict,
               chave: str | None, usuario: str | None) -> dict:
    mov = MovimentacaoPasto(
        tipo=tipo, data=quando, resumo=resumo, alteracoes=json.dumps(alt),
        chave_cliente=chave, usuario_nome=usuario,
    )
    db.add(mov)
    db.commit()
    return {"ok": True, "movimentacao": _mov_dict(mov)}


def _nome_piquete(p: Piquete | None) -> str:
    if p is None:
        return "sem piquete"
    return f"{p.nome} ({p.area.nome})" if p.area else p.nome


def mover(db: Session, lote_id: int, piquete_id: int, quando: date | None = None,
          chave: str | None = None, usuario: str | None = None) -> dict:
    """Leva o lote inteiro para outro piquete."""
    feita = _ja_feita(db, chave)
    if feita:
        return {"ok": True, "movimentacao": _mov_dict(feita), "repetida": True}
    quando = _validar_data(quando)
    lote = _lote(db, lote_id)
    destino = _piquete_ativo(db, piquete_id)
    cabecas = len(_vinculos_abertos(db, lote_id))
    if cabecas == 0:
        raise ErroPasto(f"O lote {lote.nome} não tem nenhum animal ativo.")

    alt = _novo_alt()
    atual = _ocupacao_aberta(db, lote_id)
    if atual and atual.piquete_id == destino.id:
        raise ErroPasto(f"O lote {lote.nome} já está nesse piquete.")
    origem = atual.piquete if atual else None
    _fechar_ocupacao(db, lote_id, quando, alt)
    _abrir_ocupacao(db, lote_id, destino.id, quando, cabecas, alt)
    resumo = (f"{lote.nome} ({cabecas} cab.): {_nome_piquete(origem)} → "
              f"{_nome_piquete(destino)}")
    return _registrar(db, "mover", quando, resumo, alt, chave, usuario)


def juntar(db: Session, origem_id: int, destino_id: int, quando: date | None = None,
           chave: str | None = None, usuario: str | None = None) -> dict:
    """Junta o lote de origem dentro do lote destino (os animais vão pra onde o destino está)."""
    feita = _ja_feita(db, chave)
    if feita:
        return {"ok": True, "movimentacao": _mov_dict(feita), "repetida": True}
    quando = _validar_data(quando)
    if origem_id == destino_id:
        raise ErroPasto("Escolha dois lotes diferentes para juntar.")
    origem = _lote(db, origem_id)
    destino = _lote(db, destino_id)
    vinculos = _vinculos_abertos(db, origem_id)
    if not vinculos:
        raise ErroPasto(f"O lote {origem.nome} não tem nenhum animal ativo.")

    alt = _novo_alt()
    _fechar_ocupacao(db, origem_id, quando, alt)
    n = _trocar_lote(db, vinculos, destino.id, quando, alt)
    ocup = _ocupacao_aberta(db, destino.id)
    onde = f" no {_nome_piquete(ocup.piquete)}" if ocup else ""
    resumo = f"{origem.nome} ({n} cab.) juntado ao {destino.nome}{onde}"
    return _registrar(db, "juntar", quando, resumo, alt, chave, usuario)


def separar(db: Session, origem_id: int, animal_ids: list[int], *,
            novo_lote: str | None = None, lote_destino_id: int | None = None,
            piquete_id: int | None = None, quando: date | None = None,
            chave: str | None = None, usuario: str | None = None) -> dict:
    """Tira alguns animais do lote: vão para um lote NOVO (num piquete escolhido) ou
    para um lote que já existe (e aí ficam onde esse lote está)."""
    feita = _ja_feita(db, chave)
    if feita:
        return {"ok": True, "movimentacao": _mov_dict(feita), "repetida": True}
    quando = _validar_data(quando)
    origem = _lote(db, origem_id)
    if not animal_ids:
        raise ErroPasto("Marque pelo menos um animal para separar.")
    vinculos = _vinculos_abertos(db, origem_id, animal_ids)
    if len({v.animal_id for v in vinculos}) != len(set(animal_ids)):
        raise ErroPasto("Algum animal marcado não está mais nesse lote. Atualize a tela.")

    alt = _novo_alt()
    if lote_destino_id:
        destino = _lote(db, lote_destino_id)
        if destino.id == origem.id:
            raise ErroPasto("O lote de destino é o mesmo de origem.")
    else:
        nome = (novo_lote or "").strip()
        if not nome:
            raise ErroPasto("Dê um nome para o lote novo.")
        if db.query(Lote).filter(Lote.nome == nome).first():
            raise ErroPasto(
                f"Já existe um lote '{nome}'. Escolha outro nome ou mande para o lote existente."
            )
        destino = Lote(nome=nome[:80])
        db.add(destino)
        db.flush()
        alt["lotes_criados"].append(destino.id)

    total_origem = len(_vinculos_abertos(db, origem_id))
    n = _trocar_lote(db, vinculos, destino.id, quando, alt)

    piquete = None
    if not lote_destino_id and piquete_id:
        piquete = _piquete_ativo(db, piquete_id)
        _abrir_ocupacao(db, destino.id, piquete.id, quando, n, alt)
    if n == total_origem:
        # Saíram todos: o lote de origem deixa o piquete.
        _fechar_ocupacao(db, origem_id, quando, alt)

    if lote_destino_id:
        ocup = _ocupacao_aberta(db, destino.id)
        onde = f" ({_nome_piquete(ocup.piquete)})" if ocup else ""
        resumo = f"{n} cab. separadas do {origem.nome} para o {destino.nome}{onde}"
    else:
        resumo = (f"{n} cab. separadas do {origem.nome} no lote novo {destino.nome} → "
                  f"{_nome_piquete(piquete)}")
    return _registrar(db, "separar", quando, resumo, alt, chave, usuario)


def desfazer(db: Session, mov_id: int) -> dict:
    """Desfaz uma mudança, desde que nada depois tenha mexido nos mesmos lotes/animais."""
    mov = db.get(MovimentacaoPasto, mov_id)
    if mov is None:
        raise ErroPasto("Mudança não encontrada.")
    if mov.desfeita:
        raise ErroPasto("Essa mudança já foi desfeita.")
    alt = json.loads(mov.alteracoes)
    conflito = ErroPasto(
        "Não dá pra desfazer: esses animais já tiveram outra mudança depois. "
        "Desfaça primeiro a mudança mais recente."
    )

    lp_criados = [db.get(LotePiquete, i) for i in alt["lp_criados"]]
    al_criados = [db.get(AnimalLote, i) for i in alt["al_criados"]]
    if any(x is None or x.data_saida is not None for x in lp_criados):
        raise conflito
    if any(x is None or x.data_fim is not None for x in al_criados):
        raise conflito

    lp_fechados = [db.get(LotePiquete, i) for i in alt["lp_fechados"]]
    al_fechados = [db.get(AnimalLote, i) for i in alt["al_fechados"]]
    ids_lp_criados = set(alt["lp_criados"])
    ids_al_criados = set(alt["al_criados"])
    for lp in lp_fechados:
        if lp is None:
            raise conflito
        outra = (
            db.query(LotePiquete)
            .filter(LotePiquete.lote_id == lp.lote_id, LotePiquete.data_saida.is_(None))
            .all()
        )
        if any(o.id not in ids_lp_criados for o in outra):
            raise conflito
    for al in al_fechados:
        if al is None:
            raise conflito
        outro = (
            db.query(AnimalLote)
            .filter(AnimalLote.animal_id == al.animal_id, AnimalLote.data_fim.is_(None))
            .all()
        )
        if any(o.id not in ids_al_criados for o in outro):
            raise conflito

    for x in lp_criados + al_criados:
        db.delete(x)
    db.flush()
    for lp in lp_fechados:
        lp.data_saida = None
    for al in al_fechados:
        al.data_fim = None

    # Lote criado pela mudança: some, se mais nada usa ele.
    for lote_id in alt["lotes_criados"]:
        lote = db.get(Lote, lote_id)
        if lote is None:
            continue
        usado = (
            db.query(AnimalLote).filter(AnimalLote.lote_id == lote_id).first()
            or db.query(LotePiquete).filter(LotePiquete.lote_id == lote_id).first()
            or db.execute(select(sessao_origem).where(sessao_origem.c.lote_id == lote_id)).first()
            or db.execute(select(sessao_sublote).where(sessao_sublote.c.lote_id == lote_id)).first()
        )
        if not usado:
            db.delete(lote)

    mov.desfeita = True
    db.commit()
    return {"ok": True, "movimentacao": _mov_dict(mov)}


# ---------------------------------------------------------------- Cadastro (dono)

def _area_por_nome(db: Session, nome: str | None, tipo: TipoArea | None = None) -> AreaPasto | None:
    nome = (nome or "").strip()
    if not nome:
        return None
    area = db.query(AreaPasto).filter(AreaPasto.nome == nome).first()
    if area is None:
        area = AreaPasto(nome=nome[:80], tipo=tipo or TipoArea.PROPRIA)
        db.add(area)
        db.flush()
    return area


def salvar_area(db: Session, nome: str, tipo: TipoArea, observacao: str | None = None,
                area_id: int | None = None) -> dict:
    nome = (nome or "").strip()
    if not nome:
        raise ErroPasto("Dê um nome para a área.")
    existente = db.query(AreaPasto).filter(AreaPasto.nome == nome).first()
    if area_id:
        area = db.get(AreaPasto, area_id)
        if area is None:
            raise ErroPasto("Área não encontrada.")
        if existente and existente.id != area.id:
            raise ErroPasto(f"Já existe uma área '{nome}'.")
    else:
        if existente:
            raise ErroPasto(f"Já existe uma área '{nome}'.")
        area = AreaPasto()
        db.add(area)
    area.nome, area.tipo, area.observacao = nome[:80], tipo, observacao
    db.commit()
    return {"id": area.id, "nome": area.nome, "tipo": area.tipo.value}


def salvar_piquete(db: Session, dados: dict, piquete_id: int | None = None) -> dict:
    """Cria ou edita um piquete. Com geometria nova, recalcula os hectares (a não ser que
    o dono tenha informado os hectares na mão)."""
    nome = (dados.get("nome") or "").strip()
    if not nome:
        raise ErroPasto("Dê um nome para o piquete.")
    if piquete_id:
        p = db.get(Piquete, piquete_id)
        if p is None:
            raise ErroPasto("Piquete não encontrado.")
        area_id = p.area_id
    else:
        p = None
        area_id = None

    if "area_id" in dados:
        area_id = dados["area_id"] or None
    if dados.get("area_nome"):
        area = _area_por_nome(db, dados["area_nome"])
        area_id = area.id if area else None

    q = db.query(Piquete).filter(Piquete.nome == nome, Piquete.ativo.is_(True))
    q = q.filter(Piquete.area_id.is_(None) if area_id is None else Piquete.area_id == area_id)
    if p is not None:
        q = q.filter(Piquete.id != p.id)
    if q.first():
        raise ErroPasto(f"Já existe o piquete '{nome}' nessa área.")

    if p is None:
        p = Piquete(ativo=True)
        db.add(p)
    p.area_id = area_id
    p.nome = nome[:80]
    for campo in ("capim", "observacao"):
        if campo in dados:
            setattr(p, campo, (dados[campo] or "").strip() or None)
    if "descanso_meta_dias" in dados:
        p.descanso_meta_dias = dados["descanso_meta_dias"] or None
    if dados.get("geometria"):
        g = geo.validar_geometria(dados["geometria"])
        p.geometria = json.dumps(g)
        if not dados.get("hectares"):
            p.hectares = geo.hectares(g)
    if dados.get("hectares"):
        p.hectares = round(float(dados["hectares"]), 2)
    db.commit()
    return {"id": p.id, "nome": p.nome, "hectares": p.hectares}


def remover_piquete(db: Session, piquete_id: int) -> dict:
    """Piquete sem histórico é apagado; com histórico, só sai da lista (fica no passado)."""
    p = db.get(Piquete, piquete_id)
    if p is None:
        raise ErroPasto("Piquete não encontrado.")
    if db.query(LotePiquete).filter(
        LotePiquete.piquete_id == p.id, LotePiquete.data_saida.is_(None)
    ).first():
        raise ErroPasto("Tem lote nesse piquete agora. Tire o gado antes de remover.")
    if p.ocupacoes:
        p.ativo = False
        db.commit()
        return {"ok": True, "arquivado": True}
    db.delete(p)
    db.commit()
    return {"ok": True, "arquivado": False}


def importar(db: Session, achados: list[dict], selecionados: list[int] | None,
             area_padrao: str | None, tipo_area: TipoArea) -> dict:
    """Cria os piquetes lidos do arquivo. Nome repetido na mesma área atualiza o
    contorno em vez de duplicar (dá pra reimportar o arquivo corrigido)."""
    criados = atualizados = 0
    for i, a in enumerate(achados):
        if selecionados is not None and i not in selecionados:
            continue
        area = _area_por_nome(db, a.get("area") or area_padrao, tipo_area)
        area_id = area.id if area else None
        existente = db.query(Piquete).filter(
            Piquete.nome == a["nome"],
            Piquete.area_id.is_(None) if area_id is None else Piquete.area_id == area_id,
            Piquete.ativo.is_(True),
        ).first()
        p = existente or Piquete(nome=a["nome"], area_id=area_id, ativo=True)
        if existente is None:
            db.add(p)
            criados += 1
        else:
            atualizados += 1
        p.geometria = json.dumps(a["geometria"])
        p.hectares = a["hectares"]
    db.commit()
    return {"ok": True, "criados": criados, "atualizados": atualizados}
