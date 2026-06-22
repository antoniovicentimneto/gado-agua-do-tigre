"""Modelos do banco de dados (tabelas) do controle de gado."""
from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class StatusAnimal(str, enum.Enum):
    """Estado do animal no rebanho. Só ATIVO conta como na fazenda;
    vendido/perdido/morto são inativos (saem das listas de pesagem)."""
    ATIVO = "ativo"
    VENDIDO = "vendido"
    PERDIDO = "perdido"
    MORTO = "morto"


# Status que NÃO estão mais ativos na fazenda.
STATUS_INATIVOS = {StatusAnimal.VENDIDO, StatusAnimal.PERDIDO, StatusAnimal.MORTO}


class PapelUsuario(str, enum.Enum):
    """Perfil de acesso. DONO = tudo; PEAO = limitado (lança peso e mexe em lotes)."""
    DONO = "dono"
    PEAO = "peao"


class Usuario(Base):
    """Usuário do app (login)."""
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(100))
    usuario: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    senha_hash: Mapped[str] = mapped_column(String(255))
    papel: Mapped[PapelUsuario] = mapped_column(Enum(PapelUsuario), default=PapelUsuario.PEAO)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class TipoSessao(str, enum.Enum):
    """Tipo de sessão de pesagem na mangueira."""
    MANEJO = "manejo"            # controle de peso/ganho
    COMPRA = "compra"            # lote novo comprado (registra preço/kg)
    VENDA_FAZENDA = "venda_fazenda"  # vendido no peso vivo, rendimento por tipo
    VENDA_MORTO = "venda_morto"      # vendido no gancho, fecha depois com o frigorífico


class StatusSessao(str, enum.Enum):
    ABERTA = "aberta"
    FINALIZADA = "finalizada"


class ModoVenda(str, enum.Enum):
    FAZENDA = "fazenda"  # peso vivo x rendimento
    MORTO = "morto"      # peso de carcaça informado pelo frigorífico


class Animal(Base):
    """Cada animal do rebanho, identificado pelo brinco."""
    __tablename__ = "animais"

    id: Mapped[int] = mapped_column(primary_key=True)
    brinco: Mapped[str] = mapped_column(String(50), index=True)
    tipo: Mapped[str | None] = mapped_column(String(30))  # Novilha, Boi, Vaca, Bezerro
    raca: Mapped[str | None] = mapped_column(String(50))
    cor: Mapped[str | None] = mapped_column(String(50))
    vendedor: Mapped[str | None] = mapped_column(String(100))
    nascimento: Mapped[date | None] = mapped_column(Date)  # opcional (poucos nascem na fazenda)
    capado: Mapped[bool] = mapped_column(Boolean, default=False)
    sem_brinco: Mapped[bool] = mapped_column(Boolean, default=False)  # provisório, sem brinco físico
    status: Mapped[StatusAnimal] = mapped_column(
        Enum(StatusAnimal), default=StatusAnimal.ATIVO, index=True
    )
    observacao: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    pesagens: Mapped[list[Pesagem]] = relationship(
        back_populates="animal", cascade="all, delete-orphan", order_by="Pesagem.data"
    )
    denticoes: Mapped[list[Denticao]] = relationship(
        back_populates="animal", cascade="all, delete-orphan", order_by="Denticao.data"
    )
    scores: Mapped[list[Score]] = relationship(
        back_populates="animal", cascade="all, delete-orphan", order_by="Score.data"
    )
    lotes: Mapped[list[AnimalLote]] = relationship(
        back_populates="animal", cascade="all, delete-orphan", order_by="AnimalLote.data_inicio"
    )
    compra: Mapped[Compra | None] = relationship(
        back_populates="animal", cascade="all, delete-orphan", uselist=False
    )
    venda: Mapped[Venda | None] = relationship(
        back_populates="animal", cascade="all, delete-orphan", uselist=False
    )
    historico_brincos: Mapped[list[HistoricoBrinco]] = relationship(
        back_populates="animal", cascade="all, delete-orphan", order_by="HistoricoBrinco.id"
    )


class HistoricoBrinco(Base):
    """Brincos anteriores do animal (re-etiquetagem quando perde o brinco)."""
    __tablename__ = "historico_brincos"

    id: Mapped[int] = mapped_column(primary_key=True)
    animal_id: Mapped[int] = mapped_column(ForeignKey("animais.id"), index=True)
    brinco_antigo: Mapped[str] = mapped_column(String(50))
    data_troca: Mapped[date | None] = mapped_column(Date)

    animal: Mapped[Animal] = relationship(back_populates="historico_brincos")


class Pesagem(Base):
    """Peso de um animal numa data. Uma linha por pesagem (substitui as colunas-data)."""
    __tablename__ = "pesagens"
    __table_args__ = (UniqueConstraint("animal_id", "data", name="uq_pesagem_animal_data"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    animal_id: Mapped[int] = mapped_column(ForeignKey("animais.id"), index=True)
    data: Mapped[date] = mapped_column(Date, index=True)
    peso: Mapped[float] = mapped_column(Float)  # em kg

    # Vínculo com a sessão de pesagem na mangueira (nulo p/ pesagens avulsas/importadas).
    sessao_id: Mapped[int | None] = mapped_column(ForeignKey("sessoes_pesagem.id"), index=True)
    ordem: Mapped[int | None] = mapped_column(Integer)  # ordem em que foi pesado na sessão (1º, 2º...)
    observacao: Mapped[str | None] = mapped_column(Text)
    destino_lote_id: Mapped[int | None] = mapped_column(ForeignKey("lotes.id"))  # sublote escolhido

    animal: Mapped[Animal] = relationship(back_populates="pesagens")
    sessao: Mapped[SessaoPesagem | None] = relationship(back_populates="pesagens")
    destino_lote: Mapped[Lote | None] = relationship(foreign_keys=[destino_lote_id])


class Denticao(Base):
    """Avaliação de dentição (datada — os dentes aumentam com o tempo)."""
    __tablename__ = "denticoes"

    id: Mapped[int] = mapped_column(primary_key=True)
    animal_id: Mapped[int] = mapped_column(ForeignKey("animais.id"), index=True)
    data: Mapped[date] = mapped_column(Date, index=True)
    dentes: Mapped[int] = mapped_column(Integer)  # nº de dentes

    animal: Mapped[Animal] = relationship(back_populates="denticoes")


class Score(Base):
    """Score corporal (datado, opcional)."""
    __tablename__ = "scores"

    id: Mapped[int] = mapped_column(primary_key=True)
    animal_id: Mapped[int] = mapped_column(ForeignKey("animais.id"), index=True)
    data: Mapped[date] = mapped_column(Date, index=True)
    valor: Mapped[float] = mapped_column(Float)

    animal: Mapped[Animal] = relationship(back_populates="scores")


class Lote(Base):
    """Lote / grupo de manejo (ex.: pastagem, talhão)."""
    __tablename__ = "lotes"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(80), unique=True, index=True)

    animais: Mapped[list[AnimalLote]] = relationship(back_populates="lote")


# Lotes de ORIGEM de uma sessão (pode pesar vários lotes juntos).
sessao_origem = Table(
    "sessao_origem",
    Base.metadata,
    Column("sessao_id", ForeignKey("sessoes_pesagem.id"), primary_key=True),
    Column("lote_id", ForeignKey("lotes.id"), primary_key=True),
)

# SUBLOTES disponíveis na sessão (lotes criados para separar os animais).
sessao_sublote = Table(
    "sessao_sublote",
    Base.metadata,
    Column("sessao_id", ForeignKey("sessoes_pesagem.id"), primary_key=True),
    Column("lote_id", ForeignKey("lotes.id"), primary_key=True),
)


class SessaoPesagem(Base):
    """Uma sessão de pesagem na mangueira (a tela principal do dia a dia)."""
    __tablename__ = "sessoes_pesagem"

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[TipoSessao] = mapped_column(Enum(TipoSessao), default=TipoSessao.MANEJO)
    data: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[StatusSessao] = mapped_column(
        Enum(StatusSessao), default=StatusSessao.ABERTA, index=True
    )
    separar_lotes: Mapped[bool] = mapped_column(Boolean, default=False)
    observacao: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Parâmetros financeiros da sessão (compra/venda).
    preco_kg: Mapped[float | None] = mapped_column(Float)        # compra: preço por kg vivo
    preco_arroba: Mapped[float | None] = mapped_column(Float)    # venda: preço da @
    vendedor: Mapped[str | None] = mapped_column(String(100))    # compra: de quem comprou

    origens: Mapped[list[Lote]] = relationship(secondary=sessao_origem)
    sublotes: Mapped[list[Lote]] = relationship(secondary=sessao_sublote)
    pesagens: Mapped[list[Pesagem]] = relationship(
        back_populates="sessao", order_by="Pesagem.ordem"
    )


class AnimalLote(Base):
    """Histórico: em qual lote o animal esteve e quando (lote muda ao longo da vida)."""
    __tablename__ = "animal_lote"

    id: Mapped[int] = mapped_column(primary_key=True)
    animal_id: Mapped[int] = mapped_column(ForeignKey("animais.id"), index=True)
    lote_id: Mapped[int] = mapped_column(ForeignKey("lotes.id"), index=True)
    data_inicio: Mapped[date | None] = mapped_column(Date)
    data_fim: Mapped[date | None] = mapped_column(Date)  # nulo = lote atual

    animal: Mapped[Animal] = relationship(back_populates="lotes")
    lote: Mapped[Lote] = relationship(back_populates="animais")


class Compra(Base):
    """Dados de compra do animal."""
    __tablename__ = "compras"

    id: Mapped[int] = mapped_column(primary_key=True)
    animal_id: Mapped[int] = mapped_column(ForeignKey("animais.id"), unique=True, index=True)
    data: Mapped[date | None] = mapped_column(Date)
    kg: Mapped[float | None] = mapped_column(Float)
    preco_kg: Mapped[float | None] = mapped_column(Float)  # preço por kg vivo pago
    valor: Mapped[float | None] = mapped_column(Float)  # valor total pago (kg x preço/kg)

    animal: Mapped[Animal] = relationship(back_populates="compra")


class Venda(Base):
    """Dados de venda do animal. Recebimento = arroba líquida x preço da @ (arroba = 15 kg carcaça).

    - Peso fazenda: peso vivo x rendimento (por tipo) / 15.
    - Peso morto: o frigorífico manda rendimento + peso de carcaça; valor = carcaça / 15 x preço.
      Fica 'pendente' até o frigorífico mandar a tabela.
    """
    __tablename__ = "vendas"

    id: Mapped[int] = mapped_column(primary_key=True)
    animal_id: Mapped[int] = mapped_column(ForeignKey("animais.id"), unique=True, index=True)
    modo: Mapped[ModoVenda] = mapped_column(Enum(ModoVenda), default=ModoVenda.FAZENDA)
    pendente: Mapped[bool] = mapped_column(Boolean, default=False)  # aguardando dados do frigorífico
    data: Mapped[date | None] = mapped_column(Date)
    peso: Mapped[float | None] = mapped_column(Float)  # peso vivo na venda
    rendimento: Mapped[float | None] = mapped_column(Float)  # ex.: 0.50 (editável)
    peso_carcaca: Mapped[float | None] = mapped_column(Float)  # kg de carcaça (peso morto)
    preco_arroba: Mapped[float | None] = mapped_column(Float)  # preço da @
    valor_recebido: Mapped[float | None] = mapped_column(Float)  # calculado

    animal: Mapped[Animal] = relationship(back_populates="venda")
