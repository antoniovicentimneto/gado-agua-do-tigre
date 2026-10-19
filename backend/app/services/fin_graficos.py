"""Dados dos gráficos do Financeiro: por ano, mês a mês, por setor e maiores categorias.

Usa o mesmo gerador do Resultado (visão caixa = vencimento de cada parcela; competência =
data da compra), então os números batem com a tabela do Resultado."""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session

from .fin_resultado import SEM, SEM_CATEGORIA, _linhas

TOP_CATEGORIAS = 10


def graficos(db: Session, filtros: dict) -> dict:
    ano = str(filtros.get("ano") or "")
    base = {k: v for k, v in filtros.items() if k in ("visao", "fazenda", "status")}
    por_ano = defaultdict(lambda: {"despesa": 0.0, "receita": 0.0})
    por_mes = {f"{ano}-{m:02d}": {"despesa": 0.0, "receita": 0.0} for m in range(1, 13)} if ano else {}
    por_setor = defaultdict(float)
    por_categoria = defaultdict(float)
    for lc, _p, mes, valor in _linhas(db, base):
        por_ano[mes[:4]][lc.tipo] += valor
        if ano and mes.startswith(ano):
            por_mes[mes][lc.tipo] += valor
            if lc.tipo == "despesa":
                por_setor[lc.setor or SEM] += valor
                por_categoria[lc.categoria or SEM_CATEGORIA] += valor

    cats = sorted(por_categoria.items(), key=lambda x: -x[1])
    top = cats[:TOP_CATEGORIAS]
    resto = sum(v for _, v in cats[TOP_CATEGORIAS:])
    if resto:
        top.append(("Outras categorias", resto))
    arred = lambda v: round(v, 2)  # noqa: E731
    total_ano = por_ano.get(ano, {"despesa": 0.0, "receita": 0.0})
    return {
        "anos": sorted(por_ano),
        "ano": ano,
        "por_ano": [{"ano": a, "despesa": arred(v["despesa"]), "receita": arred(v["receita"])}
                    for a, v in sorted(por_ano.items())],
        "por_mes": [{"mes": m, "despesa": arred(v["despesa"]), "receita": arred(v["receita"])}
                    for m, v in sorted(por_mes.items())],
        "por_setor": [{"nome": k, "valor": arred(v)} for k, v in sorted(por_setor.items(), key=lambda x: -x[1])],
        "por_categoria": [{"nome": k, "valor": arred(v)} for k, v in top],
        "total": {"despesa": arred(total_ano["despesa"]), "receita": arred(total_ano["receita"]),
                  "resultado": arred(total_ano["receita"] - total_ano["despesa"])},
    }
