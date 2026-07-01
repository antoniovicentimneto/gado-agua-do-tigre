"""Lógica da sessão de pesagem na mangueira (a tela principal do dia a dia).

Cuida de: abrir a sessão, montar o estado (a pesar / pesados / contadores),
registrar cada pesagem com a ordem, e editar/remover lançamentos.
Os avisos (fora do lote, já pesado, inexistente) e a re-etiquetagem entram nas
etapas seguintes, mas o registrar_pesagem já devolve os "alertas" prontos.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session, selectinload

from ..models import (
    Animal,
    AnimalLote,
    Compra,
    Denticao,
    HistoricoBrinco,
    Lote,
    ModoVenda,
    Pesagem,
    SessaoPesagem,
    StatusAnimal,
    StatusSessao,
    TipoSessao,
    Venda,
)
from .consultas import lote_atual
from .gmd import PontoPesagem, resumo_animal
from .venda import calcular_venda, rendimento_padrao


# ----------------------------------------------------------- Lotes (apoio)

def obter_ou_criar_lote(db: Session, nome: str) -> Lote:
    """Busca um lote pelo nome ou cria se não existir."""
    nome = nome.strip()
    lote = db.query(Lote).filter(Lote.nome == nome).first()
    if lote is None:
        lote = Lote(nome=nome)
        db.add(lote)
        db.flush()
    return lote


# ----------------------------------------------------------- Abertura

def criar_sessao(
    db: Session,
    tipo: TipoSessao,
    data_sessao: date,
    lotes_origem: list[str],
    separar_lotes: bool,
    sublotes: list[str] | None = None,
    preco_kg: float | None = None,
    preco_arroba: float | None = None,
    vendedor: str | None = None,
) -> SessaoPesagem:
    """Abre uma nova sessão de pesagem."""
    sessao = SessaoPesagem(
        tipo=tipo,
        data=data_sessao,
        status=StatusSessao.ABERTA,
        separar_lotes=separar_lotes,
        preco_kg=preco_kg,
        preco_arroba=preco_arroba,
        vendedor=vendedor,
    )
    for nome in lotes_origem:
        sessao.origens.append(obter_ou_criar_lote(db, nome))
    if separar_lotes and sublotes:
        for nome in sublotes:
            sessao.sublotes.append(obter_ou_criar_lote(db, nome))
    db.add(sessao)
    db.commit()
    db.refresh(sessao)
    return sessao


def adicionar_sublote(db: Session, sessao: SessaoPesagem, nome: str) -> Lote:
    """Cria/adiciona um sublote à sessão durante a pesagem."""
    lote = obter_ou_criar_lote(db, nome)
    if lote not in sessao.sublotes:
        sessao.sublotes.append(lote)
    sessao.separar_lotes = True
    db.commit()
    return lote


# ----------------------------------------------------------- Estado da tela

def _gmd_animal(animal: Animal) -> float | None:
    return resumo_animal([PontoPesagem(p.data, p.peso) for p in animal.pesagens])["gmd"]


def animais_a_pesar(db: Session, sessao: SessaoPesagem) -> list[Animal]:
    """Animais ativos nos lotes de origem que ainda não foram pesados na sessão."""
    nomes_origem = {l.nome for l in sessao.origens}
    ja_pesados = {p.animal_id for p in sessao.pesagens}
    resultado = []
    animais = (
        db.query(Animal)
        .filter(Animal.status == StatusAnimal.ATIVO)
        .options(selectinload(Animal.lotes).selectinload(AnimalLote.lote))
        .all()
    )
    for animal in animais:
        if animal.id in ja_pesados:
            continue
        if lote_atual(animal) in nomes_origem:
            resultado.append(animal)
    return resultado


def estado_sessao(db: Session, sessao: SessaoPesagem) -> dict:
    """Monta tudo que a tela precisa: a pesar, pesados e contadores."""
    a_pesar = animais_a_pesar(db, sessao)

    pesados = []
    por_sublote: dict[str, int] = {}
    for p in sorted(sessao.pesagens, key=lambda x: x.ordem or 0):
        destino = p.destino_lote.nome if p.destino_lote else None
        pesados.append(
            {
                "ordem": p.ordem,
                "pesagem_id": p.id,
                "animal_id": p.animal_id,
                "brinco": p.animal.brinco,
                "peso": p.peso,
                "destino": destino,
                "observacao": p.observacao,
                "sem_brinco": p.animal.sem_brinco,
            }
        )
        chave = destino or "(sem separação)"
        por_sublote[chave] = por_sublote.get(chave, 0) + 1

    return {
        "sessao": {
            "id": sessao.id,
            "tipo": sessao.tipo.value,
            "data": sessao.data,
            "status": sessao.status.value,
            "separar_lotes": sessao.separar_lotes,
            "origens": [l.nome for l in sessao.origens],
            "sublotes": [l.nome for l in sessao.sublotes],
            "preco_kg": sessao.preco_kg,
            "preco_arroba": sessao.preco_arroba,
            "vendedor": sessao.vendedor,
        },
        "a_pesar": [
            {
                "animal_id": a.id,
                "brinco": a.brinco,
                "tipo": a.tipo,
                "lote": lote_atual(a),
            }
            for a in a_pesar
        ],
        "pesados": pesados,
        "contadores": {
            "a_pesar": len(a_pesar),
            "pesados": len(pesados),
            "por_sublote": por_sublote,
        },
    }


# ----------------------------------------------------------- Registrar pesagem

def _proxima_ordem(sessao: SessaoPesagem) -> int:
    return max((p.ordem or 0 for p in sessao.pesagens), default=0) + 1


def _criar_animal_na_sessao(
    db: Session, sessao: SessaoPesagem, brinco: str, tipo: str | None,
    destino: Lote | None, sem_brinco: bool = False,
) -> Animal:
    """Cadastra um animal novo durante a sessão e o coloca num lote (cadastro rápido)."""
    animal = Animal(brinco=brinco, tipo=tipo, sem_brinco=sem_brinco, status=StatusAnimal.ATIVO)
    db.add(animal)
    db.flush()
    # Coloca no lote de destino (se separa) ou no 1º lote de origem.
    lote = destino or (sessao.origens[0] if sessao.origens else None)
    if lote is not None:
        db.add(AnimalLote(animal_id=animal.id, lote_id=lote.id, data_inicio=sessao.data))
    return animal


def _aplicar_financeiro(db: Session, sessao: SessaoPesagem, animal: Animal, peso: float) -> None:
    """Registra compra/venda conforme o tipo da sessão (na hora de pesar)."""
    if sessao.tipo == TipoSessao.COMPRA:
        compra = animal.compra or Compra(animal_id=animal.id)
        compra.data = sessao.data
        compra.kg = peso
        compra.preco_kg = sessao.preco_kg
        compra.valor = round(peso * sessao.preco_kg, 2) if sessao.preco_kg else None
        db.add(compra)

    elif sessao.tipo == TipoSessao.VENDA_FAZENDA:
        rendimento = rendimento_padrao(animal.tipo)
        calc = calcular_venda(peso, rendimento, sessao.preco_arroba or 0)
        venda = animal.venda or Venda(animal_id=animal.id)
        venda.modo = ModoVenda.FAZENDA
        venda.pendente = False
        venda.data = sessao.data
        venda.peso = peso
        venda.rendimento = rendimento
        venda.preco_arroba = sessao.preco_arroba
        venda.valor_recebido = calc["valor_recebido"] if sessao.preco_arroba else None
        db.add(venda)
        animal.status = StatusAnimal.VENDIDO

    elif sessao.tipo == TipoSessao.VENDA_MORTO:
        venda = animal.venda or Venda(animal_id=animal.id)
        venda.modo = ModoVenda.MORTO
        venda.pendente = True  # fecha depois com a tabela do frigorífico
        venda.data = sessao.data
        venda.peso = peso
        db.add(venda)
        animal.status = StatusAnimal.VENDIDO


def registrar_pesagem(
    db: Session,
    sessao: SessaoPesagem,
    brinco: str,
    peso: float,
    destino_lote: str | None = None,
    observacao: str | None = None,
    forcar: bool = False,
    criar_animal: bool = False,
    tipo: str | None = None,
    animal_id: int | None = None,
    novo_tipo: str | None = None,
    nova_raca: str | None = None,
    dentes: int | None = None,
) -> dict:
    """Registra a pesagem de um animal na sessão.

    Devolve {"ok": True, ...} ou {"alerta": "<tipo>", ...} quando precisa de
    confirmação do usuário (ambíguo / fora do lote / já pesado / inexistente).
    """
    brinco = brinco.strip()
    nomes_origem = {l.nome for l in sessao.origens}
    destino = obter_ou_criar_lote(db, destino_lote) if destino_lote else None

    # Encontra o animal pelo brinco (pode haver brincos repetidos na base).
    candidatos = db.query(Animal).filter(Animal.brinco == brinco).all()

    if not candidatos:
        # Em sessão de COMPRA os brincos são novos: cadastra automático.
        if criar_animal or sessao.tipo == TipoSessao.COMPRA:
            animal = _criar_animal_na_sessao(db, sessao, brinco, tipo, destino)
        else:
            return {"alerta": "inexistente", "brinco": brinco,
                    "mensagem": f"Brinco {brinco} não existe no sistema."}
    else:
        # Brinco repetido: pede pro usuário escolher qual animal pesar.
        if animal_id is not None:
            animal = next((a for a in candidatos if a.id == animal_id), None) or candidatos[0]
        elif len(candidatos) > 1:
            return {
                "alerta": "ambiguo", "brinco": brinco,
                "mensagem": f"Há {len(candidatos)} animais com o brinco {brinco}. Escolha qual pesar.",
                "candidatos": [
                    {"animal_id": a.id, "tipo": a.tipo, "raca": a.raca,
                     "lote": lote_atual(a),
                     "ultimo_peso": a.pesagens[-1].peso if a.pesagens else None}
                    for a in candidatos
                ],
            }
        else:
            # Prioriza um animal que esteja em um lote de origem.
            no_lote = [a for a in candidatos if lote_atual(a) in nomes_origem]
            animal = (no_lote or candidatos)[0]

        # Aviso: brinco não está em nenhum lote de origem.
        if lote_atual(animal) not in nomes_origem and not forcar:
            return {"alerta": "fora_do_lote", "brinco": brinco, "animal_id": animal.id,
                    "lote": lote_atual(animal),
                    "mensagem": f"Brinco {brinco} não está no(s) lote(s) desta pesagem (está em {lote_atual(animal)})."}

        # Aviso: já pesado nesta sessão.
        ja = next((p for p in sessao.pesagens if p.animal_id == animal.id), None)
        if ja and not forcar:
            return {"alerta": "ja_pesado", "brinco": brinco, "animal_id": animal.id,
                    "peso_anterior": ja.peso,
                    "mensagem": f"Brinco {brinco} já foi pesado nesta sessão ({ja.peso} kg)."}

    # Edições opcionais do animal feitas na hora da pesagem (não obrigatórias).
    if novo_tipo:
        animal.tipo = novo_tipo.strip()
    if nova_raca:
        animal.raca = nova_raca.strip()
    if dentes is not None:
        d = (
            db.query(Denticao)
            .filter(Denticao.animal_id == animal.id, Denticao.data == sessao.data)
            .first()
        )
        if d:
            d.dentes = dentes
        else:
            db.add(Denticao(animal_id=animal.id, data=sessao.data, dentes=dentes))

    # Procura pesagem do animal NA MESMA DATA (mesma sessão ou outra do dia) p/ atualizar
    # em vez de duplicar (respeita a unicidade animal+data).
    pesagem = (
        db.query(Pesagem)
        .filter(Pesagem.animal_id == animal.id, Pesagem.data == sessao.data)
        .first()
    )
    if pesagem:
        pesagem.peso = peso
        pesagem.sessao_id = sessao.id
        if pesagem.ordem is None:
            pesagem.ordem = _proxima_ordem(sessao)
        if destino:
            pesagem.destino_lote_id = destino.id
        if observacao:
            pesagem.observacao = observacao
    else:
        pesagem = Pesagem(
            animal_id=animal.id,
            data=sessao.data,
            peso=peso,
            sessao_id=sessao.id,
            ordem=_proxima_ordem(sessao),
            observacao=observacao,
            destino_lote_id=destino.id if destino else None,
        )
        db.add(pesagem)

    _aplicar_financeiro(db, sessao, animal, peso)

    db.commit()
    db.refresh(pesagem)
    return {
        "ok": True,
        "pesagem_id": pesagem.id,
        "ordem": pesagem.ordem,
        "brinco": animal.brinco,
        "peso": pesagem.peso,
        "destino": destino.nome if destino else None,
        # Dados de apoio que a tela mostra ao digitar o brinco.
        "ultimo_peso": (animal.pesagens[-2].peso if len(animal.pesagens) >= 2 else None),
        "gmd": _gmd_animal(animal),
    }


def pesar_sem_brinco(
    db: Session, sessao: SessaoPesagem, peso: float,
    destino_lote: str | None = None, observacao: str | None = None,
    tipo: str | None = None,
) -> dict:
    """Pesa um animal sem brinco (cria um registro provisório p/ vincular depois)."""
    destino = obter_ou_criar_lote(db, destino_lote) if destino_lote else None
    # Brinco provisório legível: S/B-<id da sessão>-<sequência>.
    seq = sum(1 for p in sessao.pesagens if p.animal.sem_brinco) + 1
    brinco = f"S/B-{sessao.id}-{seq}"
    animal = _criar_animal_na_sessao(db, sessao, brinco, tipo, destino, sem_brinco=True)
    pesagem = Pesagem(
        animal_id=animal.id, data=sessao.data, peso=peso, sessao_id=sessao.id,
        ordem=_proxima_ordem(sessao), observacao=observacao,
        destino_lote_id=destino.id if destino else None,
    )
    db.add(pesagem)
    _aplicar_financeiro(db, sessao, animal, peso)
    db.commit()
    db.refresh(pesagem)
    return {"ok": True, "pesagem_id": pesagem.id, "ordem": pesagem.ordem,
            "brinco": brinco, "peso": peso, "destino": destino.nome if destino else None,
            "sem_brinco": True}


def info_animal(db: Session, sessao: SessaoPesagem, brinco: str) -> dict:
    """Consulta rápida ao digitar o brinco: tipo, último peso e GMD."""
    candidatos = db.query(Animal).filter(Animal.brinco == brinco.strip()).all()
    if not candidatos:
        return {"encontrado": False, "brinco": brinco}
    nomes_origem = {l.nome for l in sessao.origens}
    no_lote = [a for a in candidatos if lote_atual(a) in nomes_origem]
    animal = (no_lote or candidatos)[0]
    return {
        "encontrado": True,
        "animal_id": animal.id,
        "brinco": animal.brinco,
        "tipo": animal.tipo,
        "raca": animal.raca,
        "lote": lote_atual(animal),
        "no_lote_origem": bool(no_lote),
        "ultimo_peso": animal.pesagens[-1].peso if animal.pesagens else None,
        "gmd": _gmd_animal(animal),
        "varios": len(candidatos),
    }


def editar_pesagem(db: Session, sessao: SessaoPesagem, pesagem_id: int,
                   peso: float | None = None, destino_lote: str | None = None,
                   observacao: str | None = None) -> bool:
    """Edita peso/destino/observação de uma pesagem da sessão."""
    pesagem = db.get(Pesagem, pesagem_id)
    if pesagem is None or pesagem.sessao_id != sessao.id:
        return False
    if peso is not None:
        pesagem.peso = peso
    if destino_lote is not None:
        pesagem.destino_lote_id = obter_ou_criar_lote(db, destino_lote).id
    if observacao is not None:
        pesagem.observacao = observacao
    db.commit()
    return True


def cancelar_sessao(db: Session, sessao: SessaoPesagem) -> None:
    """Cancela (apaga) uma sessão aberta que ainda não tem nenhuma pesagem."""
    if sessao.pesagens:
        raise ValueError(
            "Essa sessão já tem pesagens lançadas — remova as pesagens primeiro "
            "ou finalize a sessão em vez de cancelar."
        )
    db.delete(sessao)
    db.commit()


def remover_pesagem(db: Session, sessao: SessaoPesagem, pesagem_id: int) -> bool:
    """Remove uma pesagem da sessão (correção de erro)."""
    pesagem = db.get(Pesagem, pesagem_id)
    if pesagem is None or pesagem.sessao_id != sessao.id:
        return False
    animal = pesagem.animal
    db.delete(pesagem)
    # Se era um animal provisório (sem brinco) e ficou sem pesagens, remove também.
    if animal.sem_brinco and len(animal.pesagens) <= 1:
        db.delete(animal)
    db.commit()
    return True


# ----------------------------------------------------------- Faltantes e vínculo

def faltantes(db: Session, sessao: SessaoPesagem) -> list[dict]:
    """Animais esperados que NÃO foram pesados (candidatos a perda de brinco)."""
    return [
        {"animal_id": a.id, "brinco": a.brinco, "tipo": a.tipo, "lote": lote_atual(a)}
        for a in animais_a_pesar(db, sessao)
    ]


def pesados_provisorios(db: Session, sessao: SessaoPesagem) -> list[dict]:
    """Animais NOVOS nesta sessão (sem brinco OU cadastrados com brinco novo),
    candidatos a vincular a um animal antigo que perdeu o brinco."""
    out = []
    vistos = set()
    for p in sessao.pesagens:
        a = p.animal
        if a.id in vistos:
            continue
        # "Novo" = todas as pesagens do animal são desta sessão (não tem histórico anterior).
        novo = a.pesagens and all(x.sessao_id == sessao.id for x in a.pesagens)
        if a.sem_brinco or novo:
            vistos.add(a.id)
            out.append({"animal_id": a.id, "brinco": a.brinco,
                        "peso": p.peso, "ordem": p.ordem, "sem_brinco": a.sem_brinco})
    return out


def vincular(db: Session, sessao: SessaoPesagem, animal_temp_id: int,
             animal_faltante_id: int, novo_brinco: str | None = None) -> dict:
    """Vincula um animal provisório (sem brinco / brinco novo) a um animal antigo.

    O animal antigo herda a pesagem e o histórico. O brinco que o animal passa a
    usar é: `novo_brinco` (se informado), senão o brinco do provisório (se ele
    tiver um número), senão mantém o brinco antigo.
    """
    temp = db.get(Animal, animal_temp_id)
    faltante = db.get(Animal, animal_faltante_id)
    if temp is None or faltante is None:
        return {"ok": False, "erro": "Animal não encontrado"}

    # Move as pesagens do provisório para o animal antigo. Usa a relação (append)
    # para transferir a POSSE — senão o cascade delete-orphan apaga a pesagem junto
    # com o animal provisório.
    for p in list(temp.pesagens):
        existente = next((x for x in faltante.pesagens if x.data == p.data), None)
        if existente:
            existente.peso = p.peso
            existente.sessao_id = p.sessao_id
            existente.ordem = p.ordem
            existente.destino_lote_id = p.destino_lote_id
            # p continua em temp e será apagado junto (cascade) — sem duplicar.
        else:
            faltante.pesagens.append(p)  # transfere a posse para o animal antigo

    # Move compra/venda, se houver (sessões de compra/venda).
    if temp.compra and not faltante.compra:
        faltante.compra = temp.compra
    if temp.venda and not faltante.venda:
        faltante.venda = temp.venda

    # Define qual brinco o animal antigo passa a usar.
    brinco_alvo = None
    if novo_brinco and novo_brinco.strip():
        brinco_alvo = novo_brinco.strip()
    elif not temp.sem_brinco and temp.brinco:
        brinco_alvo = temp.brinco
    if brinco_alvo and brinco_alvo != faltante.brinco:
        db.add(HistoricoBrinco(animal_id=faltante.id, brinco_antigo=faltante.brinco,
                               data_troca=sessao.data))
        faltante.brinco = brinco_alvo
    faltante.sem_brinco = False

    db.delete(temp)
    db.commit()
    return {"ok": True, "brinco": faltante.brinco}


# ----------------------------------------------------------- Finalização

def finalizar(db: Session, sessao: SessaoPesagem) -> dict:
    """Aplica as mudanças de lote (sublotes) e fecha a sessão."""
    for p in sessao.pesagens:
        if p.destino_lote_id is None:
            continue
        animal = p.animal
        # Já está no lote de destino?
        atual = next((al for al in animal.lotes if al.data_fim is None), None)
        if atual and atual.lote_id == p.destino_lote_id:
            continue
        if atual:
            atual.data_fim = sessao.data
        db.add(AnimalLote(animal_id=animal.id, lote_id=p.destino_lote_id,
                          data_inicio=sessao.data))
    sessao.status = StatusSessao.FINALIZADA
    db.commit()
    return resumo(db, sessao)


def resumo(db: Session, sessao: SessaoPesagem) -> dict:
    """Resumo da sessão: total, peso médio, GMD médio, distribuição e faltantes."""
    pesos = [p.peso for p in sessao.pesagens]
    gmds = [g for g in (_gmd_animal(p.animal) for p in sessao.pesagens) if g is not None]
    por_sublote: dict[str, int] = {}
    for p in sessao.pesagens:
        chave = p.destino_lote.nome if p.destino_lote else "(sem separação)"
        por_sublote[chave] = por_sublote.get(chave, 0) + 1
    falt = faltantes(db, sessao)
    pendentes = [p.animal.brinco for p in sessao.pesagens
                 if p.animal.venda and p.animal.venda.pendente]
    return {
        "tipo": sessao.tipo.value,
        "data": sessao.data,
        "total_pesados": len(pesos),
        "peso_medio": round(sum(pesos) / len(pesos), 1) if pesos else None,
        "gmd_medio": round(sum(gmds) / len(gmds), 3) if gmds else None,
        "por_sublote": por_sublote,
        "faltantes": falt,
        "qtde_faltantes": len(falt),
        "vendas_pendentes": pendentes,
    }


def completar_venda_morto(db: Session, animal: Animal, rendimento: float | None,
                          peso_carcaca: float | None, preco_arroba: float | None) -> dict:
    """Fecha a venda no gancho com os dados do frigorífico (rendimento + carcaça)."""
    venda = animal.venda
    if venda is None:
        return {"ok": False, "erro": "Animal não tem venda registrada"}
    if peso_carcaca is not None:
        venda.peso_carcaca = peso_carcaca
        # Rendimento derivado do peso vivo, se não informado.
        if rendimento is None and venda.peso:
            rendimento = round(peso_carcaca / venda.peso, 4)
    if rendimento is not None:
        venda.rendimento = rendimento
    if preco_arroba is not None:
        venda.preco_arroba = preco_arroba

    # Valor = arrobas de carcaça x preço (@ = 15 kg de carcaça).
    if venda.peso_carcaca and venda.preco_arroba:
        venda.valor_recebido = round((venda.peso_carcaca / 15.0) * venda.preco_arroba, 2)
    venda.pendente = False
    db.commit()
    return {"ok": True, "valor_recebido": venda.valor_recebido,
            "arrobas": round(venda.peso_carcaca / 15.0, 2) if venda.peso_carcaca else None}
