"""Relatório filtrado (Rebanho › Planilha) em Excel.

A tela filtra e ordena os animais no próprio aparelho e manda só a lista de ids,
na ordem em que aparecem. Aqui a planilha é montada exatamente nessa ordem.
"""
from __future__ import annotations

import io
from datetime import date

from openpyxl import Workbook
from openpyxl.styles import Font
from sqlalchemy.orm import Session, selectinload

from ..models import Animal, AnimalLote
from .consultas import montar_resumo

NEGRITO = Font(bold=True)
PESO_UA = 450  # 1 UA = 450 kg vivos

CABECALHO = [
    "Brinco", "Tipo", "Raça", "Lote", "Situação", "Último peso (kg)", "Data último peso",
    "GMD", "uGMD", "Dentes", "Data dentição", "Observação",
]


def gerar_relatorio(db: Session, ids: list[int]) -> bytes:
    """Monta o .xlsx com os animais pedidos, na ordem dos ids."""
    # Uma consulta só (com selectinload) — o banco fica longe, nada de N+1.
    animais = (
        db.query(Animal)
        .filter(Animal.id.in_(ids))
        .options(
            selectinload(Animal.pesagens),
            selectinload(Animal.lotes).selectinload(AnimalLote.lote),
            selectinload(Animal.denticoes),
        )
        .all()
    ) if ids else []
    por_id = {a.id: a for a in animais}

    wb = Workbook()
    ws = wb.active
    ws.title = "Relatório"
    ws.append(CABECALHO)
    for celula in ws[1]:
        celula.font = NEGRITO

    pesos = []
    for i in ids:
        a = por_id.get(i)
        if a is None:
            continue
        r = montar_resumo(a)
        status = r["status"].value if hasattr(r["status"], "value") else r["status"]
        ws.append([
            r["brinco"], r["tipo"], r["raca"], r["lote_atual"], status,
            r["ultimo_peso"], r["data_ultimo"],
            round(r["gmd"], 3) if r["gmd"] is not None else None,
            round(r["ugmd"], 3) if r["ugmd"] is not None else None,
            r["dentes"], r["data_dentes"], r["observacao"],
        ])
        if r["ultimo_peso"] is not None:
            pesos.append(r["ultimo_peso"])

    # Linha de totais no fim (mesmo resumo que a tela mostra).
    ws.append([])
    total = sum(pesos)
    ws.append(["Animais", len(por_id), "", "Peso total (kg)", round(total, 1),
               "Peso médio (kg)", round(total / len(pesos), 1) if pesos else None,
               "UA", round(total / PESO_UA, 1)])
    for celula in ws[ws.max_row]:
        celula.font = NEGRITO

    for col, largura in zip("ABCDEFGHIJKL", [9, 12, 12, 18, 10, 15, 15, 8, 8, 8, 13, 30]):
        ws.column_dimensions[col].width = largura
    for linha in ws.iter_rows(min_row=2):
        for c in (linha[6], linha[10]):  # colunas de data
            c.number_format = "DD/MM/YYYY"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def nome_relatorio() -> str:
    return f"relatorio_gado_{date.today().isoformat()}.xlsx"
