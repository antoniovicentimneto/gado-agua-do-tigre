"""Fechamento de venda/compra de gado: liga o manejo da mangueira ao Financeiro.

Venda: uma RECEITA com o valor bruto (Pecuária › Venda de animais / Abate) e cada desconto
da nota (Funrural, SENAR, frete, comissão, GTA...) como DESPESA. Assim o Resultado mostra o
custo de cada desconto e o caixa fecha com o líquido que caiu na conta.
Compra: uma DESPESA da compra (Pecuária › Aquisição de rebanho › Bovinos) e os custos extras
(frete, comissão, GTA) como despesas.

Refazer o fechamento não apaga nada: os lançamentos antigos ficam excluídos (com motivo) e
os novos são criados — o histórico do Financeiro continua de pé."""
from __future__ import annotations

import json
from collections import Counter
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import Animal, Pesagem, SessaoPesagem, TipoSessao
from ..models_financeiro import FinFechamento, FinLancamento
from . import fin_lancamentos
from .fin_plano import ErroFinanceiro, agora_utc

ARROBA_KG = 15
SETOR = "Pecuária"
FAZENDA_PADRAO = "Água do Tigre"
TIPOS_VENDA = (TipoSessao.VENDA_FAZENDA, TipoSessao.VENDA_MORTO)

# Onde cada desconto/custo cai no plano de contas (grupo, categoria) — já existem no plano.
CLASSE_DESCONTO = {
    "funrural": ("Impostos e encargos", "Funrural, pis, cofins, iss, csll, darf"),
    "senar": ("Impostos e encargos", "Funrural, pis, cofins, iss, csll, darf"),
    "gta": ("Impostos e encargos", "Gta - guia de trânsito animal"),
    "comissao": ("Recursos humanos", "Comissão e premiação"),
    "frete": ("Comercialização", "Frete"),
    "outro": ("Comercialização", "Outros descontos e taxas"),
}
# Linhas sugeridas no formulário. Percentual é só sugestão: vale o que estiver na nota.
# (Produtor pessoa física: Funrural 1,2% + RAT 0,1% e SENAR 0,2% sobre o bruto.)
DESCONTOS_VENDA = [
    {"chave": "funrural", "nome": "Funrural (INSS + RAT)", "percentual": 1.3, "descontado": True},
    {"chave": "senar", "nome": "SENAR", "percentual": 0.2, "descontado": True},
    {"chave": "frete", "nome": "Frete", "percentual": None, "descontado": True},
    {"chave": "comissao", "nome": "Comissão do corretor", "percentual": None, "descontado": True},
    {"chave": "gta", "nome": "GTA / taxas", "percentual": None, "descontado": True},
]
CUSTOS_COMPRA = [
    {"chave": "frete", "nome": "Frete", "percentual": None},
    {"chave": "comissao", "nome": "Comissão do corretor", "percentual": None},
    {"chave": "gta", "nome": "GTA / taxas", "percentual": None},
]


def _categoria_por_tipo(tipos: Counter, abate: bool) -> str:
    """Sugere a categoria da receita pelo tipo de animal mais comum do manejo."""
    t = (tipos.most_common(1)[0][0] if tipos else "") or ""
    t = t.lower()
    if "boi" in t or "garrote" in t or "touro" in t:
        return "Boi"
    if "novilh" in t:
        return "Novilha mais 2 anos" if abate else "Novilha 1 ano"
    if "vaca" in t:
        return "Vaca descarte"
    if "bezerra" in t:
        return "Bezerra"
    if "bezer" in t:
        return "Bezerro"
    return "Boi" if abate else "Novilha 1 ano"


def _sessao(db: Session, sessao_id: int) -> SessaoPesagem:
    s = db.get(SessaoPesagem, sessao_id)
    if s is None:
        raise ErroFinanceiro("Manejo não encontrado")
    if s.tipo == TipoSessao.MANEJO:
        raise ErroFinanceiro("Só manejos de venda ou de compra vão pro Financeiro")
    return s


def _animais_da_sessao(db: Session, s: SessaoPesagem) -> list[Animal]:
    ids = list(dict.fromkeys(db.scalars(select(Pesagem.animal_id).where(Pesagem.sessao_id == s.id))))
    if not ids:
        return []
    q = (select(Animal).where(Animal.id.in_(ids))
         .options(selectinload(Animal.venda), selectinload(Animal.compra)))
    return list(db.scalars(q))


def numeros_do_manejo(db: Session, s: SessaoPesagem) -> dict:
    """Cabeças, peso, arrobas, preço e valor bruto calculados pela mangueira."""
    animais = _animais_da_sessao(db, s)
    tipos = Counter(a.tipo for a in animais)
    venda = s.tipo in TIPOS_VENDA
    peso = arrobas = bruto = 0.0
    pendentes = 0
    for a in animais:
        if venda:
            v = a.venda
            if v is None:
                continue
            peso += v.peso or 0
            if v.pendente:
                pendentes += 1
            elif v.peso_carcaca:
                arrobas += v.peso_carcaca / ARROBA_KG
            elif v.peso and v.rendimento:
                arrobas += v.peso * v.rendimento / ARROBA_KG
            bruto += v.valor_recebido or 0
        else:
            c = a.compra
            if c is None:
                continue
            peso += c.kg or 0
            bruto += c.valor or 0
    return {
        "tipo": "venda" if venda else "compra",
        "modo": s.tipo.value,
        "cabecas": len(animais),
        "peso_total": round(peso, 1),
        "arrobas": round(arrobas, 2) if venda else None,
        "preco": s.preco_arroba if venda else s.preco_kg,
        "unidade": "@" if venda else "kg",
        "valor_bruto": round(bruto, 2),
        "pendentes": pendentes,  # venda no gancho ainda sem a tabela do frigorífico
        "grupo": ("Abate" if s.tipo == TipoSessao.VENDA_MORTO else "Venda de animais") if venda
        else "Aquisição de rebanho",
        "categoria": _categoria_por_tipo(tipos, s.tipo == TipoSessao.VENDA_MORTO) if venda else "Bovinos",
        "tipos": dict(tipos),
    }


def _dict(f: FinFechamento, db: Session) -> dict:
    lancs = db.scalars(select(FinLancamento).where(FinLancamento.fechamento_id == f.id,
                                                   FinLancamento.excluido.is_(False))).all()
    return {
        "id": f.id, "sessao_id": f.sessao_id, "tipo": f.tipo, "data": f.data.isoformat(),
        "contraparte": f.contraparte, "cabecas": f.cabecas, "peso_total": f.peso_total,
        "arrobas": f.arrobas, "valor_bruto": f.valor_bruto, "valor_liquido": f.valor_liquido,
        "descontos": json.loads(f.descontos or "[]"), "nf_numero": f.nf_numero,
        "observacao": f.observacao, "criado_por": f.criado_por,
        "lancamentos": [{"id": lc.id, "tipo": lc.tipo, "descricao": lc.descricao,
                         "valor_total": lc.valor_total, "categoria": lc.categoria} for lc in lancs],
    }


def resumo(db: Session, sessao_id: int) -> dict:
    """O que a tela de fechamento precisa: números do manejo + fechamento salvo (se houver)."""
    s = _sessao(db, sessao_id)
    f = db.scalar(select(FinFechamento).where(FinFechamento.sessao_id == s.id))
    nums = numeros_do_manejo(db, s)
    return {
        "sessao": {"id": s.id, "data": s.data.isoformat(), "tipo": s.tipo.value, "vendedor": s.vendedor,
                   "status": s.status.value},
        "manejo": nums,
        "descontos_padrao": DESCONTOS_VENDA if nums["tipo"] == "venda" else CUSTOS_COMPRA,
        "fechamento": _dict(f, db) if f else None,
    }


def _valor(v) -> float:
    try:
        return round(float(str(v).replace(",", ".")), 2) if v not in (None, "") else 0.0
    except ValueError:
        raise ErroFinanceiro(f"Valor inválido: {v}")


def _data(v, padrao: date) -> date:
    if not v:
        return padrao
    return v if isinstance(v, date) else date.fromisoformat(str(v)[:10])


def salvar(db: Session, sessao_id: int, dados: dict, usuario: str) -> dict:
    """Cria (ou refaz) o fechamento e os lançamentos dele no Financeiro."""
    s = _sessao(db, sessao_id)
    nums = numeros_do_manejo(db, s)
    venda = nums["tipo"] == "venda"
    data = _data(dados.get("data"), s.data)
    bruto = _valor(dados.get("valor_bruto"))
    if bruto <= 0:
        raise ErroFinanceiro("Informe o valor bruto da nota")
    contraparte = (dados.get("contraparte") or (None if venda else s.vendedor) or "").strip() or None
    venc1 = _data(dados.get("vencimento"), data)
    n_parc = max(1, min(60, int(dados.get("n_parcelas") or 1)))

    linhas = []
    for d in dados.get("descontos") or []:
        valor = _valor(d.get("valor"))
        if valor <= 0:
            continue
        chave = d.get("chave") if d.get("chave") in CLASSE_DESCONTO else "outro"
        linhas.append({"chave": chave, "nome": (d.get("nome") or "Desconto").strip()[:80], "valor": valor,
                       "percentual": d.get("percentual"),
                       "descontado": bool(d.get("descontado", True)) if venda else False,
                       "vencimento": _data(d.get("vencimento"), venc1).isoformat()})
    soma_desc = round(sum(x["valor"] for x in linhas if x["descontado"]), 2)
    soma_extra = round(sum(x["valor"] for x in linhas), 2)
    if venda and soma_desc >= bruto:
        raise ErroFinanceiro("Os descontos não podem ser maiores que o valor bruto")
    liquido = round(bruto - soma_desc, 2) if venda else round(bruto + soma_extra, 2)

    f = db.scalar(select(FinFechamento).where(FinFechamento.sessao_id == s.id))
    if f is None:
        f = FinFechamento(sessao_id=s.id, criado_por=usuario, criado_em=agora_utc())
        db.add(f)
    else:
        f.alterado_por, f.alterado_em = usuario, agora_utc()
        for lc in db.scalars(select(FinLancamento).where(FinLancamento.fechamento_id == f.id,
                                                         FinLancamento.excluido.is_(False))):
            lc.excluido, lc.excluido_motivo = True, "Fechamento da venda/compra refeito"
            lc.excluido_em, lc.alterado_por = agora_utc(), usuario
    f.tipo, f.data, f.contraparte = nums["tipo"], data, contraparte
    f.cabecas, f.peso_total, f.arrobas = nums["cabecas"], nums["peso_total"], nums["arrobas"]
    f.valor_bruto, f.valor_liquido = bruto, liquido
    f.descontos = json.dumps(linhas, ensure_ascii=False)
    f.nf_numero = (dados.get("nf_numero") or "").strip()[:20] or None
    f.observacao = (dados.get("observacao") or "").strip() or None
    db.flush()

    fazenda = dados.get("fazenda") or FAZENDA_PADRAO
    quando = data.strftime("%d/%m/%Y")
    cab = f"{nums['cabecas']} cab."
    base = {"fazenda": fazenda, "setor": SETOR, "data": data.isoformat(), "conta": dados.get("conta"),
            "nf_numero": f.nf_numero, "fornecedor_nome": contraparte, "forma_pagamento": dados.get("forma_pagamento")}
    principal = fin_lancamentos.criar(db, {
        **base, "tipo": "receita" if venda else "despesa",
        "grupo": dados.get("grupo") or nums["grupo"], "categoria": dados.get("categoria") or nums["categoria"],
        "descricao": f"{'Venda' if venda else 'Compra'} de {cab} ({dados.get('categoria') or nums['categoria']})"
                     f" — manejo de {quando}",
        "observacao": f.observacao, "valor_total": bruto, "n_parcelas": n_parc,
        "primeiro_vencimento": venc1.isoformat(),
    }, usuario, origem="fechamento", commit=False)
    principal.fechamento_id = f.id
    for x in linhas:
        grupo, categoria = CLASSE_DESCONTO[x["chave"]]
        # Sem fornecedor: senão o app "aprende" que o comprador é Frete/Funrural e passa a
        # sugerir isso quando lançarem uma nota dele.
        lc = fin_lancamentos.criar(db, {
            **base, "fornecedor_nome": None, "tipo": "despesa", "grupo": grupo, "categoria": categoria,
            "descricao": f"{x['nome']} — {'venda' if venda else 'compra'} de {cab} de {quando}",
            "valor_total": x["valor"], "n_parcelas": 1, "primeiro_vencimento": x["vencimento"],
        }, usuario, origem="fechamento", commit=False)
        lc.fechamento_id = f.id  # categoria nova (ex.: Frete) entra no plano pelo próprio criar()
    db.commit()
    return _dict(f, db)


def desfazer(db: Session, sessao_id: int, usuario: str) -> None:
    """Tira o fechamento do Financeiro (lançamentos ficam excluídos, com motivo)."""
    f = db.scalar(select(FinFechamento).where(FinFechamento.sessao_id == sessao_id))
    if f is None:
        raise ErroFinanceiro("Esse manejo ainda não foi lançado no Financeiro")
    for lc in db.scalars(select(FinLancamento).where(FinLancamento.fechamento_id == f.id)):
        if not lc.excluido:
            lc.excluido, lc.excluido_motivo = True, "Fechamento da venda/compra desfeito"
            lc.excluido_em, lc.alterado_por = agora_utc(), usuario
        lc.fechamento_id = None
    db.delete(f)
    db.commit()


def por_sessao(db: Session) -> dict[int, dict]:
    """Selo "lançado no Financeiro" da lista de manejos (uma consulta só)."""
    return {f.sessao_id: {"valor_bruto": f.valor_bruto, "valor_liquido": f.valor_liquido, "tipo": f.tipo}
            for f in db.scalars(select(FinFechamento))}
