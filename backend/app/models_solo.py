"""Modelos de solo e insumos: análise de solo e aplicações (calcário, adubo...) por piquete."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class AnaliseSolo(Base):
    """Resultado de laboratório de um piquete (camada 0–20 cm, normalmente)."""
    __tablename__ = "analises_solo"

    id: Mapped[int] = mapped_column(primary_key=True)
    piquete_id: Mapped[int] = mapped_column(ForeignKey("piquetes.id"), index=True)
    data: Mapped[date] = mapped_column(Date, index=True)
    laboratorio: Mapped[str | None] = mapped_column(String(80))
    profundidade: Mapped[str | None] = mapped_column(String(20))  # "0-20 cm"
    ph_cacl2: Mapped[float | None] = mapped_column(Float)
    mo: Mapped[float | None] = mapped_column(Float)        # matéria orgânica, g/dm³
    p: Mapped[float | None] = mapped_column(Float)         # fósforo (Mehlich/resina), mg/dm³
    k: Mapped[float | None] = mapped_column(Float)         # potássio, cmolc/dm³
    ca: Mapped[float | None] = mapped_column(Float)        # cálcio, cmolc/dm³
    mg: Mapped[float | None] = mapped_column(Float)        # magnésio, cmolc/dm³
    al: Mapped[float | None] = mapped_column(Float)        # alumínio, cmolc/dm³
    h_al: Mapped[float | None] = mapped_column(Float)      # H+Al, cmolc/dm³
    argila: Mapped[float | None] = mapped_column(Float)    # %
    observacao: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    piquete = relationship("Piquete")


class AplicacaoInsumo(Base):
    """Insumo aplicado num piquete (calcário, gesso, adubo, herbicida, semente...)."""
    __tablename__ = "aplicacoes_insumo"

    id: Mapped[int] = mapped_column(primary_key=True)
    piquete_id: Mapped[int] = mapped_column(ForeignKey("piquetes.id"), index=True)
    data: Mapped[date] = mapped_column(Date, index=True)
    tipo: Mapped[str] = mapped_column(String(20))      # calcario / gesso / adubo / herbicida / semente / outro
    produto: Mapped[str] = mapped_column(String(80))   # ex.: Calcário dolomítico PRNT 80, 20-00-20, Ureia
    dose: Mapped[float] = mapped_column(Float)         # por hectare
    unidade: Mapped[str] = mapped_column(String(10))   # kg/ha, t/ha, L/ha
    area_ha: Mapped[float] = mapped_column(Float)      # área aplicada
    custo_total: Mapped[float | None] = mapped_column(Float)  # R$
    observacao: Mapped[str | None] = mapped_column(Text)
    usuario_nome: Mapped[str | None] = mapped_column(String(100))
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    piquete = relationship("Piquete")
