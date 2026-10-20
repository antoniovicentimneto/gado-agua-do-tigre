"""Modelos do módulo Financeiro (despesas e receitas da fazenda).

Substitui a planilha CONSIPA. Um LANÇAMENTO é uma compra/receita; as PARCELAS são
os pagamentos dela (data de vencimento + valor). Plano de contas em 3 níveis:
setor › grupo › categoria (decisão do Antonio, ver docs/financeiro_consipa_engenharia_reversa.md).
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

TIPOS_LANCAMENTO = ("despesa", "receita")


class FinFazenda(Base):
    """Fazenda dona do lançamento (Água do Tigre, Castro...)."""
    __tablename__ = "fin_fazendas"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(80), unique=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class FinConta(Base):
    """Conta de onde sai/entra o dinheiro: banco, cartão, dinheiro."""
    __tablename__ = "fin_contas"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(80), unique=True)
    tipo: Mapped[str] = mapped_column(String(20), default="banco")  # banco | cartao | outro
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class FinPlano(Base):
    """Uma categoria do plano de contas: tipo › setor › grupo › categoria."""
    __tablename__ = "fin_plano"
    __table_args__ = (UniqueConstraint("tipo", "setor", "grupo", "categoria", name="uq_fin_plano"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(10), index=True)  # despesa | receita
    setor: Mapped[str] = mapped_column(String(60))
    grupo: Mapped[str] = mapped_column(String(80))
    categoria: Mapped[str] = mapped_column(String(100))
    codigo: Mapped[str | None] = mapped_column(String(20))  # ex.: 1.01.09 (só pra ordenar)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class FinFornecedor(Base):
    """Fornecedor/cliente. O CNPJ/CPF (quando houver) é a chave de verdade — o nome
    pode ter várias grafias (apelidos). Guarda a classificação usada por último,
    que vira a sugestão do próximo lançamento."""
    __tablename__ = "fin_fornecedores"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(150), index=True)
    documento: Mapped[str | None] = mapped_column(String(14), unique=True)  # só dígitos
    apelidos: Mapped[str | None] = mapped_column(Text)  # outras grafias, separadas por ";"
    # Classificação padrão (aprendida).
    pad_tipo: Mapped[str | None] = mapped_column(String(10))
    pad_fazenda: Mapped[str | None] = mapped_column(String(80))
    pad_setor: Mapped[str | None] = mapped_column(String(60))
    pad_grupo: Mapped[str | None] = mapped_column(String(80))
    pad_categoria: Mapped[str | None] = mapped_column(String(100))
    pad_conta: Mapped[str | None] = mapped_column(String(80))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class FinLancamento(Base):
    """Uma compra (despesa) ou receita. As parcelas dizem quando o dinheiro sai/entra."""
    __tablename__ = "fin_lancamentos"

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(10), index=True)  # despesa | receita
    data: Mapped[date] = mapped_column(Date, index=True)  # competência (data da compra)
    fazenda: Mapped[str | None] = mapped_column(String(80))
    setor: Mapped[str | None] = mapped_column(String(60))
    grupo: Mapped[str | None] = mapped_column(String(80))
    categoria: Mapped[str | None] = mapped_column(String(100))  # vazia = "sem categoria" (revisar)
    fornecedor_id: Mapped[int | None] = mapped_column(ForeignKey("fin_fornecedores.id"), index=True)
    fornecedor_nome: Mapped[str | None] = mapped_column(String(150))  # como veio (nota/planilha)
    descricao: Mapped[str | None] = mapped_column(String(300))
    valor_total: Mapped[float] = mapped_column(Float, default=0)
    conta: Mapped[str | None] = mapped_column(String(80))
    forma_pagamento: Mapped[str | None] = mapped_column(String(30))
    nf_numero: Mapped[str | None] = mapped_column(String(20))
    nf_chave: Mapped[str | None] = mapped_column(String(44), index=True)
    observacao: Mapped[str | None] = mapped_column(Text)
    origem: Mapped[str] = mapped_column(String(15), default="manual")  # manual|consipa|nota|recorrente
    chave_origem: Mapped[str | None] = mapped_column(String(64), unique=True)  # evita importar 2x
    recorrente_id: Mapped[int | None] = mapped_column(ForeignKey("fin_recorrentes.id"))
    recorrente_mes: Mapped[str | None] = mapped_column(String(7))  # AAAA-MM gerado
    # Fila de revisão: aparece em vermelho até alguém conferir.
    revisar: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    revisar_motivo: Mapped[str | None] = mapped_column(String(200))
    # Conferido "não é duplicado" (compra repetida de verdade): sai do alerta de duplicados.
    dup_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    # Excluir = inativar (fica no histórico, sai dos relatórios).
    excluido: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    excluido_motivo: Mapped[str | None] = mapped_column(String(200))
    excluido_em: Mapped[datetime | None] = mapped_column(DateTime)
    criado_por: Mapped[str | None] = mapped_column(String(100))
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    alterado_por: Mapped[str | None] = mapped_column(String(100))
    alterado_em: Mapped[datetime | None] = mapped_column(DateTime)

    parcelas: Mapped[list["FinParcela"]] = relationship(
        back_populates="lancamento", cascade="all, delete-orphan", order_by="FinParcela.numero")
    fornecedor: Mapped[FinFornecedor | None] = relationship()


class FinParcela(Base):
    """Pagamento (ou recebimento) de um lançamento."""
    __tablename__ = "fin_parcelas"

    id: Mapped[int] = mapped_column(primary_key=True)
    lancamento_id: Mapped[int] = mapped_column(ForeignKey("fin_lancamentos.id"), index=True)
    numero: Mapped[int] = mapped_column(Integer, default=1)
    vencimento: Mapped[date] = mapped_column(Date, index=True)
    valor: Mapped[float] = mapped_column(Float)
    conta: Mapped[str | None] = mapped_column(String(80))  # vazia = a do lançamento
    pago: Mapped[bool | None] = mapped_column(Boolean)  # None = automático (vencimento <= hoje)
    # Valor que estava previsto quando a parcela "a confirmar" foi confirmada com outro valor
    # (ex.: salário lançado pro ano todo e corrigido mês a mês). Nulo = não mudou.
    valor_previsto: Mapped[float | None] = mapped_column(Float)

    lancamento: Mapped[FinLancamento] = relationship(back_populates="parcelas")


class FinRecorrente(Base):
    """Modelo de lançamento que se repete todo mês (salário, Copel, tarifas...).
    Todo mês o app cria o lançamento 'previsto' e a pessoa confirma o valor."""
    __tablename__ = "fin_recorrentes"

    id: Mapped[int] = mapped_column(primary_key=True)
    descricao: Mapped[str] = mapped_column(String(300))
    tipo: Mapped[str] = mapped_column(String(10), default="despesa")
    fazenda: Mapped[str | None] = mapped_column(String(80))
    setor: Mapped[str | None] = mapped_column(String(60))
    grupo: Mapped[str | None] = mapped_column(String(80))
    categoria: Mapped[str | None] = mapped_column(String(100))
    fornecedor_id: Mapped[int | None] = mapped_column(ForeignKey("fin_fornecedores.id"))
    fornecedor_nome: Mapped[str | None] = mapped_column(String(150))
    valor: Mapped[float] = mapped_column(Float, default=0)
    conta: Mapped[str | None] = mapped_column(String(80))
    dia: Mapped[int] = mapped_column(Integer, default=10)  # dia do vencimento
    inicio: Mapped[date | None] = mapped_column(Date)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class FinRegra(Base):
    """O que o app aprendeu: 'nota deste fornecedor (e deste tipo de produto) vai
    para esta categoria'. Atualizada sempre que alguém lança uma nota."""
    __tablename__ = "fin_regras"
    __table_args__ = (UniqueConstraint("fornecedor_doc", "ncm", name="uq_fin_regra"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    fornecedor_doc: Mapped[str] = mapped_column(String(14), default="")  # "" = qualquer fornecedor
    ncm: Mapped[str] = mapped_column(String(8), default="")  # 4 primeiros dígitos; "" = nota toda
    tipo: Mapped[str] = mapped_column(String(10), default="despesa")
    fazenda: Mapped[str | None] = mapped_column(String(80))
    setor: Mapped[str | None] = mapped_column(String(60))
    grupo: Mapped[str | None] = mapped_column(String(80))
    categoria: Mapped[str | None] = mapped_column(String(100))
    conta: Mapped[str | None] = mapped_column(String(80))
    vezes: Mapped[int] = mapped_column(Integer, default=0)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class FinContribuinte(Base):
    """CPF/CNPJ cadastrado na tela pra buscar as notas emitidas contra ele na SEFAZ.
    O certificado A1 (.pfx) e a senha ficam CRIPTOGRAFADOS (services/fin_cripto.py)."""
    __tablename__ = "fin_contribuintes"

    id: Mapped[int] = mapped_column(primary_key=True)
    documento: Mapped[str] = mapped_column(String(14), unique=True)  # só dígitos
    nome: Mapped[str] = mapped_column(String(150))
    uf: Mapped[str] = mapped_column(String(2), default="PR")
    fazenda: Mapped[str | None] = mapped_column(String(80))  # sugestão de fazenda das notas dele
    ambiente: Mapped[int] = mapped_column(Integer, default=1)  # 1 produção, 2 homologação
    cert_pfx: Mapped[bytes | None] = mapped_column(LargeBinary)
    cert_senha: Mapped[str | None] = mapped_column(Text)
    cert_titular: Mapped[str | None] = mapped_column(String(200))
    cert_validade: Mapped[datetime | None] = mapped_column(DateTime)
    ult_nsu: Mapped[str] = mapped_column(String(15), default="0")
    max_nsu: Mapped[str | None] = mapped_column(String(15))
    ultima_consulta: Mapped[datetime | None] = mapped_column(DateTime)
    pode_consultar_apos: Mapped[datetime | None] = mapped_column(DateTime)
    ultimo_retorno: Mapped[str | None] = mapped_column(String(300))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class FinNota(Base):
    """Nota fiscal recebida (da SEFAZ ou de um XML enviado). Fica na 'caixa de
    entrada' até alguém lançar ou ignorar."""
    __tablename__ = "fin_notas"

    id: Mapped[int] = mapped_column(primary_key=True)
    chave: Mapped[str] = mapped_column(String(44), unique=True)
    contribuinte_id: Mapped[int | None] = mapped_column(ForeignKey("fin_contribuintes.id"))
    nsu: Mapped[str | None] = mapped_column(String(15))
    origem: Mapped[str] = mapped_column(String(10), default="xml")  # sefaz | xml
    emitente_doc: Mapped[str | None] = mapped_column(String(14), index=True)
    emitente_nome: Mapped[str | None] = mapped_column(String(150))
    destinatario_doc: Mapped[str | None] = mapped_column(String(14))
    numero: Mapped[str | None] = mapped_column(String(20))
    data_emissao: Mapped[date | None] = mapped_column(Date, index=True)
    valor: Mapped[float | None] = mapped_column(Float)
    xml: Mapped[str | None] = mapped_column(Text)  # procNFe/NFe completo (None = só o resumo)
    # nova = chegou o resumo · completa = XML completo · lancada · ignorada
    situacao: Mapped[str] = mapped_column(String(10), default="nova", index=True)
    ciencia_em: Mapped[datetime | None] = mapped_column(DateTime)
    lancamento_id: Mapped[int | None] = mapped_column(ForeignKey("fin_lancamentos.id"))
    recebida_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class FinMovimento(Base):
    """Linha do extrato bancário (OFX) — pra conferir se tudo que saiu do banco
    foi lançado. `parcela_id` preenchido = conciliado."""
    __tablename__ = "fin_movimentos"
    __table_args__ = (UniqueConstraint("conta", "fitid", name="uq_fin_movimento"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    conta: Mapped[str] = mapped_column(String(80), index=True)
    fitid: Mapped[str] = mapped_column(String(80))  # id da transação no banco
    data: Mapped[date] = mapped_column(Date, index=True)
    valor: Mapped[float] = mapped_column(Float)  # negativo = saída
    descricao: Mapped[str | None] = mapped_column(String(300))
    parcela_id: Mapped[int | None] = mapped_column(ForeignKey("fin_parcelas.id"))
    ignorado: Mapped[bool] = mapped_column(Boolean, default=False)
    importado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
