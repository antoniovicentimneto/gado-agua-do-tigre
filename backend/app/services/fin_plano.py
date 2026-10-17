"""Plano de contas, fazendas e contas do Financeiro (cadastros + carga inicial)."""
from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..models_financeiro import FinConta, FinFazenda, FinLancamento, FinPlano, FinRecorrente
from .fin_plano_padrao import PLANO_PADRAO

FAZENDAS_PADRAO = ["Água do Tigre", "Castro"]
CONTAS_PADRAO = [
    ("Banco do Brasil", "banco"), ("Santander", "banco"), ("Sicoob", "banco"),
    ("Itaú", "banco"), ("Bradesco", "banco"), ("Frísia", "outro"),
    ("Cartão de Crédito BB", "cartao"), ("Cartão de Crédito Sant.", "cartao"),
    ("Cartão de Crédito Sicoob", "cartao"), ("Dinheiro", "outro"),
]

# Setores da CONSIPA -> setores do app (decisões de 16/10/2026):
# "Pecuária de leite" era a fazenda de Castro; agricultura é só arrendamento (vai pra Sede).
SETORES_CONSIPA = {
    "PECUÁRIA DE CORTE": "Pecuária",
    "PECUÁRIA DE LEITE": "Pecuária",
    "MÁQUINAS E EQUIPAMENTOS": "Máquinas e equipamentos",
    "SEDE": "Sede",
    "PESSOAL": "Pessoal",
    "AGRICULTURA": "Sede",
    "CONFIGURAÇÕES": "Sede",
}

SIGLAS = {"itr": "ITR", "irpf": "IRPF", "ipva": "IPVA", "iof": "IOF", "13o": "13º", "inss": "INSS",
          "fgts": "FGTS", "cpf": "CPF", "cnpj": "CNPJ"}


def agora_utc() -> datetime:
    """Hora UTC sem fuso (o banco guarda tudo em UTC; a tela converte pra hora local).
    O servidor (Render) roda em UTC e o PC em horário de Brasília: usar sempre isto."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def iso_utc(d: datetime | None) -> str | None:
    """Data/hora UTC no formato que o navegador entende como UTC (termina em Z)."""
    return d.isoformat() + "Z" if d else None


class ErroFinanceiro(Exception):
    """Erro de regra de negócio do Financeiro (vira 400 com a mensagem)."""


def limpar_nome(texto) -> tuple[str | None, str]:
    """'1.01.09. PRÓ LABORE' -> ('1.01.09', 'Pró labore'). Mantém siglas em maiúsculas."""
    s = str(texto or "").strip()
    m = re.match(r"^([\d.]+?)\.?\s+(.*)$", s)
    codigo, nome = (m.group(1), m.group(2)) if m else (None, s)
    nome = nome.strip().lower()
    nome = re.sub(r"[a-z0-9º]+", lambda w: SIGLAS.get(w.group(0), w.group(0)), nome)
    return codigo, (nome[:1].upper() + nome[1:]) if nome else nome


def garantir_cadastros(db: Session) -> None:
    """Cria fazendas, contas e plano padrão se ainda não existirem (idempotente)."""
    if db.scalar(select(FinFazenda.id).limit(1)) is None:
        db.add_all([FinFazenda(nome=n) for n in FAZENDAS_PADRAO])
    if db.scalar(select(FinConta.id).limit(1)) is None:
        db.add_all([FinConta(nome=n, tipo=t) for n, t in CONTAS_PADRAO])
    if db.scalar(select(FinPlano.id).limit(1)) is None:
        db.add_all([FinPlano(tipo=t, setor=s, grupo=g, categoria=c, codigo=cod)
                    for t, s, g, c, cod in PLANO_PADRAO])
    db.commit()


def garantir_categoria(db: Session, tipo, setor, grupo, categoria, codigo=None) -> None:
    """Cria a categoria no plano se ainda não existir (usado na importação)."""
    if not (tipo and setor and grupo and categoria):
        return
    existe = db.scalar(select(FinPlano.id).where(
        FinPlano.tipo == tipo, FinPlano.setor == setor, FinPlano.grupo == grupo,
        FinPlano.categoria == categoria))
    if existe is None:
        db.add(FinPlano(tipo=tipo, setor=setor, grupo=grupo, categoria=categoria, codigo=codigo))
        db.flush()


def cadastros(db: Session) -> dict:
    """Tudo que os seletores das telas precisam, numa chamada só."""
    garantir_cadastros(db)
    plano = db.scalars(select(FinPlano).order_by(FinPlano.tipo, FinPlano.setor, FinPlano.codigo,
                                                 FinPlano.categoria)).all()
    return {
        "fazendas": [{"id": f.id, "nome": f.nome, "ativo": f.ativo}
                     for f in db.scalars(select(FinFazenda).order_by(FinFazenda.id))],
        "contas": [{"id": c.id, "nome": c.nome, "tipo": c.tipo, "ativo": c.ativo}
                   for c in db.scalars(select(FinConta).order_by(FinConta.nome))],
        "plano": [{"id": p.id, "tipo": p.tipo, "setor": p.setor, "grupo": p.grupo,
                   "categoria": p.categoria, "codigo": p.codigo, "ativo": p.ativo} for p in plano],
    }


# ---------------------------------------------------------------- edição dos cadastros

def salvar_plano(db: Session, dados: dict, plano_id: int | None = None) -> dict:
    """Cria ou renomeia uma categoria. Renomear atualiza os lançamentos que já usam o
    nome antigo (pra não sobrar categoria 'órfã' nos relatórios)."""
    campos = {k: (dados.get(k) or "").strip() for k in ("tipo", "setor", "grupo", "categoria")}
    if campos["tipo"] not in ("despesa", "receita") or not all(campos.values()):
        raise ErroFinanceiro("Preencha tipo, setor, grupo e categoria")
    if plano_id is None:
        p = FinPlano(**campos, codigo=(dados.get("codigo") or None))
        db.add(p)
    else:
        p = db.get(FinPlano, plano_id)
        if p is None:
            raise ErroFinanceiro("Categoria não encontrada")
        antigo = (p.tipo, p.setor, p.grupo, p.categoria)
        for k, v in campos.items():
            setattr(p, k, v)
        p.codigo = dados.get("codigo") or p.codigo
        if "ativo" in dados:
            p.ativo = bool(dados["ativo"])
        if antigo != tuple(campos.values()):
            for modelo in (FinLancamento, FinRecorrente):
                db.execute(update(modelo).where(
                    modelo.tipo == antigo[0], modelo.setor == antigo[1], modelo.grupo == antigo[2],
                    modelo.categoria == antigo[3]).values(
                    tipo=campos["tipo"], setor=campos["setor"], grupo=campos["grupo"],
                    categoria=campos["categoria"]))
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise ErroFinanceiro("Já existe essa categoria")
    return {"id": p.id}


def salvar_simples(db: Session, modelo, dados: dict, item_id: int | None = None) -> dict:
    """Cria/edita fazenda ou conta (nome, tipo, ativo)."""
    nome = (dados.get("nome") or "").strip()
    if not nome:
        raise ErroFinanceiro("Informe o nome")
    item = modelo(nome=nome) if item_id is None else db.get(modelo, item_id)
    if item is None:
        raise ErroFinanceiro("Cadastro não encontrado")
    item.nome = nome
    if "ativo" in dados:
        item.ativo = bool(dados["ativo"])
    if modelo is FinConta and dados.get("tipo"):
        item.tipo = dados["tipo"]
    db.add(item)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise ErroFinanceiro("Já existe um cadastro com esse nome")
    return {"id": item.id}
