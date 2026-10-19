"""Modelos do manejo de campo: salga de cocho (por lote) e sanidade (por animal)."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class SalgaCocho(Base):
    """Uma reposição de sal/suplemento no cocho de um lote ("salgar o cocho")."""
    __tablename__ = "salgas_cocho"

    id: Mapped[int] = mapped_column(primary_key=True)
    lote_id: Mapped[int] = mapped_column(ForeignKey("lotes.id"), index=True)
    # Fotografia do momento: onde o lote estava e quantas cabeças tinha (o consumo por
    # cabeça é calculado com isso, mesmo que o lote mude depois).
    piquete_id: Mapped[int | None] = mapped_column(ForeignKey("piquetes.id"))
    cabecas: Mapped[int | None] = mapped_column(Integer)
    produto: Mapped[str] = mapped_column(String(60))  # Mineral, Proteinado, Ureado...
    quantidade_kg: Mapped[float] = mapped_column(Float)
    data_hora: Mapped[datetime] = mapped_column(DateTime, index=True)
    observacao: Mapped[str | None] = mapped_column(Text)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    usuario_nome: Mapped[str | None] = mapped_column(String(100))
    # Gerada no aparelho: reenvio da fila offline não duplica.
    chave_cliente: Mapped[str | None] = mapped_column(String(40), index=True)
    # Cocho dividido entre lotes: as linhas da mesma salga têm o mesmo grupo (a quantidade
    # foi repartida pelas cabeças de cada lote).
    grupo: Mapped[str | None] = mapped_column(String(40), index=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    lote = relationship("Lote")


class OcorrenciaSanitaria(Base):
    """Um animal tratado no campo: o problema, o remédio, a dose e a carência.

    A fazenda trata só quem precisa (método SICOPA), então o registro é por animal.
    """
    __tablename__ = "ocorrencias_sanitarias"

    id: Mapped[int] = mapped_column(primary_key=True)
    animal_id: Mapped[int] = mapped_column(ForeignKey("animais.id"), index=True)
    lote_nome: Mapped[str | None] = mapped_column(String(80))  # lote no momento do tratamento
    data_hora: Mapped[datetime] = mapped_column(DateTime, index=True)
    problema: Mapped[str] = mapped_column(String(60))  # bicheira, pneumonia, casco...
    produto: Mapped[str | None] = mapped_column(String(60))
    dose: Mapped[str | None] = mapped_column(String(40))  # "10 ml", "1 frasco"...
    carencia_dias: Mapped[int | None] = mapped_column(Integer)
    carencia_ate: Mapped[date | None] = mapped_column(Date, index=True)  # pode abater a partir do dia seguinte
    observacao: Mapped[str | None] = mapped_column(Text)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    usuario_nome: Mapped[str | None] = mapped_column(String(100))
    chave_cliente: Mapped[str | None] = mapped_column(String(40), index=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    animal = relationship("Animal")


class PastoPeriodo(Base):
    """Qual pasto (forrageira) o piquete teve e quando. Períodos abertos (fim nulo) são o
    pasto atual; dois abertos ao mesmo tempo = sobressemeadura (ex.: azevém no Tifton)."""
    __tablename__ = "pasto_periodos"

    id: Mapped[int] = mapped_column(primary_key=True)
    piquete_id: Mapped[int] = mapped_column(ForeignKey("piquetes.id"), index=True)
    especie: Mapped[str] = mapped_column(String(60))  # Marandu, Tifton 85, Azevém...
    inicio: Mapped[date] = mapped_column(Date)
    fim: Mapped[date | None] = mapped_column(Date)
    observacao: Mapped[str | None] = mapped_column(Text)  # ex.: reforma, sobressemeadura
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ConfigValor(Base):
    """Configurações simples do app guardadas como JSON (ex.: GMD de referência por época)."""
    __tablename__ = "config_valores"

    chave: Mapped[str] = mapped_column(String(60), primary_key=True)
    valor: Mapped[str] = mapped_column(Text)


class CronogramaItem(Base):
    """Próximo piquete planejado de um lote, na ordem, com os dias previstos lá."""
    __tablename__ = "cronograma_rotacao"

    id: Mapped[int] = mapped_column(primary_key=True)
    lote_id: Mapped[int] = mapped_column(ForeignKey("lotes.id"), index=True)
    ordem: Mapped[int] = mapped_column(Integer)
    piquete_id: Mapped[int] = mapped_column(ForeignKey("piquetes.id"))
    dias_previstos: Mapped[int] = mapped_column(Integer)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
