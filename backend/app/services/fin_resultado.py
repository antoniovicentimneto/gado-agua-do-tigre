"""Resultado por mês: a árvore tipo › setor › grupo › categoria × meses, igual à tabela
dinâmica da CONSIPA, e o "clicar no número" que lista os lançamentos por trás dele.

Duas visões: CAIXA (mês do vencimento de cada parcela) e COMPETÊNCIA (mês da compra,
valor total). Tudo numa consulta só — o banco fica em SP e o servidor nos EUA."""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models_financeiro import FinLancamento
from .fin_lancamentos import parcela_realizada

SEM_CATEGORIA = "(sem categoria)"
SEM = "(vazio)"


def _mes(d: date) -> str:
    return d.strftime("%Y-%m")


def _linhas(db: Session, filtros: dict):
    """Gera (lançamento, parcela|None, mês, valor) que passam nos filtros."""
    visao = filtros.get("visao") or "caixa"
    inicio, fim = filtros.get("inicio") or "0000-00", filtros.get("fim") or "9999-99"
    status = filtros.get("status") or "todos"  # todos | realizado | previsto
    fazenda, setor = filtros.get("fazenda"), filtros.get("setor")
    hoje = date.today()
    q = (select(FinLancamento).options(selectinload(FinLancamento.parcelas))
         .where(FinLancamento.excluido.is_(False)))
    if fazenda:
        q = q.where(FinLancamento.fazenda == fazenda) if fazenda != SEM else q.where(FinLancamento.fazenda.is_(None))
    if setor:
        q = q.where(FinLancamento.setor == setor)
    for lc in db.scalars(q):
        if visao == "competencia":
            mes = _mes(lc.data)
            if not (inicio <= mes <= fim):
                continue
            realizado = all(parcela_realizada(p, hoje) for p in lc.parcelas) if lc.parcelas else lc.data <= hoje
            if (status == "realizado" and not realizado) or (status == "previsto" and realizado):
                continue
            yield lc, None, mes, lc.valor_total
        else:
            for p in lc.parcelas:
                mes = _mes(p.vencimento)
                if not (inicio <= mes <= fim):
                    continue
                realizado = parcela_realizada(p, hoje)
                if (status == "realizado" and not realizado) or (status == "previsto" and realizado):
                    continue
                yield lc, p, mes, p.valor


def caminho(lc: FinLancamento) -> list[str]:
    return [lc.tipo, lc.setor or SEM, lc.grupo or SEM, lc.categoria or SEM_CATEGORIA]


def resultado(db: Session, filtros: dict) -> dict:
    """Árvore com totais por mês em cada nível + linha de resultado (receita − despesa)."""
    raiz: dict = {}
    meses: set[str] = set()
    for lc, _p, mes, valor in _linhas(db, filtros):
        meses.add(mes)
        nivel = raiz
        for nome in caminho(lc):
            no = nivel.setdefault(nome, {"nome": nome, "meses": {}, "total": 0.0, "n": 0, "filhos": {}})
            no["meses"][mes] = round(no["meses"].get(mes, 0) + valor, 2)
            no["total"] = round(no["total"] + valor, 2)
            no["n"] += 1
            nivel = no["filhos"]

    def lista(nos: dict) -> list:
        out = []
        for no in sorted(nos.values(), key=lambda n: -abs(n["total"])):
            out.append({**no, "filhos": lista(no["filhos"])})
        return out

    tipos = lista(raiz)
    rec = next((t for t in tipos if t["nome"] == "receita"), None)
    desp = next((t for t in tipos if t["nome"] == "despesa"), None)
    todos_meses = sorted(meses)
    saldo = {m: round((rec["meses"].get(m, 0) if rec else 0) - (desp["meses"].get(m, 0) if desp else 0), 2)
             for m in todos_meses}
    tipos.sort(key=lambda t: 0 if t["nome"] == "despesa" else 1)
    return {"meses": todos_meses, "arvore": tipos, "saldo": saldo,
            "saldo_total": round(sum(saldo.values()), 2)}


def detalhar(db: Session, filtros: dict, caminho_alvo: list[str], mes: str | None) -> list[dict]:
    """Os lançamentos (parcelas) que formam um número da árvore."""
    out = []
    for lc, p, m, valor in _linhas(db, filtros):
        if mes and m != mes:
            continue
        if caminho(lc)[:len(caminho_alvo)] != caminho_alvo:
            continue
        out.append({
            "lancamento_id": lc.id, "parcela_id": p.id if p else None,
            "parcela": f"{p.numero}/{len(lc.parcelas)}" if p else None,
            "data": lc.data.isoformat(), "vencimento": p.vencimento.isoformat() if p else None,
            "mes": m, "fazenda": lc.fazenda, "setor": lc.setor, "grupo": lc.grupo, "categoria": lc.categoria,
            "fornecedor": lc.fornecedor_nome, "descricao": lc.descricao, "valor": valor,
            "conta": (p.conta if p and p.conta else lc.conta), "nf_numero": lc.nf_numero,
            "origem": lc.origem, "revisar": lc.revisar, "criado_por": lc.criado_por,
        })
    out.sort(key=lambda r: (r["vencimento"] or r["data"]), reverse=True)
    return out
