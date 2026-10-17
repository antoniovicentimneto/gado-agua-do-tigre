"""Extrato bancário (OFX) e conciliação com as parcelas lançadas.

OFX é o arquivo que BB, Santander, Sicoob, Itaú e os cartões exportam ("Exportar extrato
> OFX/Money"). Cada movimento é casado com uma parcela da MESMA conta, mesmo valor e
vencimento a até 5 dias. O que sobra sem par = saiu do banco e não foi lançado."""
from __future__ import annotations

import re
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models_financeiro import FinLancamento, FinMovimento, FinParcela
from .fin_plano import ErroFinanceiro

TOLERANCIA_DIAS = 5


def _tag(bloco: str, nome: str) -> str | None:
    """OFX 1.x é SGML (tags sem fechar); OFX 2 é XML. Este regex lê os dois."""
    m = re.search(rf"<{nome}>([^<\r\n]*)", bloco, re.I)
    return m.group(1).strip() if m else None


def _data_ofx(txt: str | None) -> date | None:
    if not txt or len(txt) < 8 or not txt[:8].isdigit():
        return None
    return date(int(txt[:4]), int(txt[4:6]), int(txt[6:8]))


def ler_ofx(conteudo: bytes) -> list[dict]:
    texto = conteudo.decode("latin-1") if b"\x00" not in conteudo[:50] else conteudo.decode("utf-16")
    if "<OFX>" not in texto.upper():
        raise ErroFinanceiro("O arquivo não é um extrato OFX")
    movimentos = []
    for bloco in re.findall(r"<STMTTRN>(.*?)(?:</STMTTRN>|(?=<STMTTRN>)|(?=</BANKTRANLIST>))", texto, re.S | re.I):
        valor_txt = (_tag(bloco, "TRNAMT") or "0").replace(",", ".")
        try:
            valor = round(float(valor_txt), 2)
        except ValueError:
            continue
        d = _data_ofx(_tag(bloco, "DTPOSTED"))
        if d is None:
            continue
        descricao = " ".join(x for x in (_tag(bloco, "NAME"), _tag(bloco, "MEMO")) if x)
        fitid = _tag(bloco, "FITID") or f"{d.isoformat()}|{valor}|{descricao}"[:80]
        movimentos.append({"data": d, "valor": valor, "descricao": descricao[:300], "fitid": fitid[:80]})
    if not movimentos:
        raise ErroFinanceiro("Não achei movimentos neste OFX")
    return movimentos


def importar(db: Session, conta: str, conteudo: bytes) -> dict:
    if not conta:
        raise ErroFinanceiro("Escolha a conta do extrato")
    movs = ler_ofx(conteudo)
    existentes = set(db.scalars(select(FinMovimento.fitid).where(FinMovimento.conta == conta)))
    novos = 0
    for m in movs:
        if m["fitid"] in existentes:
            continue
        db.add(FinMovimento(conta=conta, **m))
        existentes.add(m["fitid"])
        novos += 1
    db.commit()
    conciliados = conciliar(db, conta)
    return {"movimentos": len(movs), "novos": novos, "conciliados_agora": conciliados}


def _parcelas_da_conta(db: Session, conta: str, inicio: date, fim: date) -> list[FinParcela]:
    q = (select(FinParcela).join(FinLancamento).options(selectinload(FinParcela.lancamento))
         .where(FinLancamento.excluido.is_(False), FinParcela.vencimento >= inicio, FinParcela.vencimento <= fim))
    return [p for p in db.scalars(q) if (p.conta or p.lancamento.conta) == conta]


def conciliar(db: Session, conta: str) -> int:
    """Casa automaticamente movimento × parcela (valor igual, data próxima, mesma conta)."""
    soltos = db.scalars(select(FinMovimento).where(FinMovimento.conta == conta, FinMovimento.parcela_id.is_(None),
                                                   FinMovimento.ignorado.is_(False))).all()
    if not soltos:
        return 0
    inicio = min(m.data for m in soltos) - timedelta(days=TOLERANCIA_DIAS)
    fim = max(m.data for m in soltos) + timedelta(days=TOLERANCIA_DIAS)
    usadas = set(db.scalars(select(FinMovimento.parcela_id).where(FinMovimento.parcela_id.is_not(None))))
    parcelas = [p for p in _parcelas_da_conta(db, conta, inicio, fim) if p.id not in usadas]
    ok = 0
    for m in sorted(soltos, key=lambda x: x.data):
        sinal = -1 if m.valor < 0 else 1
        candidatas = [p for p in parcelas
                      if p.id not in usadas and abs(p.valor - abs(m.valor)) < 0.01
                      and (sinal < 0) == (p.lancamento.tipo == "despesa")
                      and abs((p.vencimento - m.data).days) <= TOLERANCIA_DIAS]
        if candidatas:
            p = min(candidatas, key=lambda x: abs((x.vencimento - m.data).days))
            m.parcela_id = p.id
            p.pago = True
            usadas.add(p.id)
            ok += 1
    db.commit()
    return ok


def listar(db: Session, conta: str | None = None) -> dict:
    q = select(FinMovimento).order_by(FinMovimento.data.desc())
    if conta:
        q = q.where(FinMovimento.conta == conta)
    movs = db.scalars(q).all()
    ids = {m.parcela_id for m in movs if m.parcela_id}
    parcelas = {p.id: p for p in db.scalars(select(FinParcela).options(selectinload(FinParcela.lancamento))
                                            .where(FinParcela.id.in_(ids)))} if ids else {}
    out = []
    for m in movs:
        p = parcelas.get(m.parcela_id)
        out.append({"id": m.id, "conta": m.conta, "data": m.data.isoformat(), "valor": m.valor,
                    "descricao": m.descricao, "ignorado": m.ignorado, "parcela_id": m.parcela_id,
                    "lancamento_id": p.lancamento_id if p else None,
                    "lancamento": (f"{p.lancamento.fornecedor_nome or ''} · {p.lancamento.descricao or ''}"
                                   .strip(" ·") if p else None)})
    contas = sorted(set(db.scalars(select(FinMovimento.conta).distinct())))
    return {"movimentos": out, "contas": contas}


def vincular(db: Session, mov_id: int, parcela_id: int | None, ignorar: bool | None = None) -> None:
    m = db.get(FinMovimento, mov_id)
    if m is None:
        raise ErroFinanceiro("Movimento não encontrado")
    if ignorar is not None:
        m.ignorado = ignorar
    if parcela_id is not None:
        p = db.get(FinParcela, parcela_id) if parcela_id else None
        if parcela_id and p is None:
            raise ErroFinanceiro("Parcela não encontrada")
        m.parcela_id = p.id if p else None
        if p:
            p.pago = True
    db.commit()


def candidatas(db: Session, mov_id: int) -> list[dict]:
    """Parcelas da conta com valor parecido (±10%) e data a até 15 dias — pra ligar à mão."""
    m = db.get(FinMovimento, mov_id)
    if m is None:
        raise ErroFinanceiro("Movimento não encontrado")
    usadas = set(db.scalars(select(FinMovimento.parcela_id).where(FinMovimento.parcela_id.is_not(None))))
    q = (select(FinParcela).join(FinLancamento).options(selectinload(FinParcela.lancamento))
         .where(FinLancamento.excluido.is_(False),
                FinParcela.vencimento.between(m.data - timedelta(days=15), m.data + timedelta(days=15))))
    out = []
    for p in db.scalars(q):
        if p.id in usadas or abs(p.valor - abs(m.valor)) > abs(m.valor) * 0.10 + 0.01:
            continue
        out.append({"parcela_id": p.id, "lancamento_id": p.lancamento_id, "vencimento": p.vencimento.isoformat(),
                    "valor": p.valor, "conta": p.conta or p.lancamento.conta,
                    "fornecedor": p.lancamento.fornecedor_nome, "descricao": p.lancamento.descricao})
    out.sort(key=lambda x: (abs(x["valor"] - abs(m.valor)), x["vencimento"]))
    return out[:30]
