"""Lançamentos do Financeiro: criar/editar/excluir, parcelas, fornecedores, recorrentes."""
from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models_financeiro import (
    TIPOS_LANCAMENTO,
    FinFornecedor,
    FinLancamento,
    FinParcela,
    FinRecorrente,
)
from .fin_plano import ErroFinanceiro, agora_utc, garantir_categoria, iso_utc


# ---------------------------------------------------------------- utilidades

def so_digitos(txt) -> str:
    return re.sub(r"\D", "", str(txt or ""))


def normalizar(txt) -> str:
    """Pra comparar nomes: sem acento, minúsculo, sem espaço sobrando."""
    s = unicodedata.normalize("NFKD", str(txt or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().lower()


def somar_meses(d: date, meses: int, dia: int | None = None) -> date:
    """Mesma data N meses depois (dia 31 vira o último dia do mês)."""
    total = d.month - 1 + meses
    ano, mes = d.year + total // 12, total % 12 + 1
    dia = dia or d.day
    for tentativa in (dia, 30, 29, 28):
        try:
            return date(ano, mes, min(tentativa, 31))
        except ValueError:
            continue
    return date(ano, mes, 28)


def _data(valor, campo="data") -> date:
    if isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor)[:10])
    except ValueError:
        raise ErroFinanceiro(f"Data inválida em '{campo}'")


def _num(valor, campo="valor") -> float:
    if valor in (None, ""):
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    s = str(valor).strip().replace("R$", "").replace(" ", "")
    if "," in s:  # formato brasileiro 1.234,56
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        raise ErroFinanceiro(f"Valor inválido em '{campo}'")


def parcela_realizada(p: FinParcela, hoje: date | None = None) -> bool:
    """Pago marcado na mão vale; senão, venceu = realizado (igual à CONSIPA)."""
    if p.pago is not None:
        return p.pago
    return p.vencimento <= (hoje or date.today())


# ---------------------------------------------------------------- fornecedores

def achar_ou_criar_fornecedor(db: Session, nome: str | None, documento: str | None = None,
                              criar: bool = True) -> FinFornecedor | None:
    """Acha pelo CNPJ/CPF; senão pelo nome (ou apelido) sem acento; senão cria."""
    doc = so_digitos(documento) or None
    nome = (nome or "").strip()
    if not doc and not nome:
        return None
    if doc:
        f = db.scalar(select(FinFornecedor).where(FinFornecedor.documento == doc))
        if f:
            return f
    if nome:
        alvo = normalizar(nome)
        candidatos = db.scalars(select(FinFornecedor)).all()
        for f in candidatos:
            nomes = [f.nome] + [a for a in (f.apelidos or "").split(";") if a.strip()]
            if any(normalizar(n) == alvo for n in nomes):
                if doc and not f.documento:
                    f.documento = doc  # aprende o CNPJ de quem só tinha nome
                return f
    if not criar:
        return None
    f = FinFornecedor(nome=nome or doc, documento=doc)
    db.add(f)
    db.flush()
    return f


def listar_fornecedores(db: Session) -> list[dict]:
    from sqlalchemy import func
    contagem = dict(db.execute(
        select(FinLancamento.fornecedor_id, func.count()).where(FinLancamento.excluido.is_(False))
        .group_by(FinLancamento.fornecedor_id)).all())
    return [{
        "id": f.id, "nome": f.nome, "documento": f.documento, "apelidos": f.apelidos,
        "ativo": f.ativo, "lancamentos": contagem.get(f.id, 0),
        "padrao": {"tipo": f.pad_tipo, "fazenda": f.pad_fazenda, "setor": f.pad_setor,
                   "grupo": f.pad_grupo, "categoria": f.pad_categoria, "conta": f.pad_conta},
    } for f in db.scalars(select(FinFornecedor).order_by(FinFornecedor.nome))]


def salvar_fornecedor(db: Session, dados: dict, fid: int | None) -> dict:
    nome = (dados.get("nome") or "").strip()
    if not nome:
        raise ErroFinanceiro("Informe o nome do fornecedor")
    f = FinFornecedor(nome=nome) if fid is None else db.get(FinFornecedor, fid)
    if f is None:
        raise ErroFinanceiro("Fornecedor não encontrado")
    f.nome = nome
    f.documento = so_digitos(dados.get("documento")) or None
    f.apelidos = (dados.get("apelidos") or "").strip() or None
    if "ativo" in dados:
        f.ativo = bool(dados["ativo"])
    db.add(f)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise ErroFinanceiro("Já existe outro fornecedor com esse CNPJ/CPF")
    return {"id": f.id}


def juntar_fornecedores(db: Session, manter_id: int, juntar_ids: list[int]) -> dict:
    """Une grafias duplicadas (Frísia/Frisia): os lançamentos passam pro que fica e o
    nome do outro vira apelido."""
    manter = db.get(FinFornecedor, manter_id)
    if manter is None:
        raise ErroFinanceiro("Fornecedor não encontrado")
    apelidos = [a for a in (manter.apelidos or "").split(";") if a.strip()]
    for fid in juntar_ids:
        outro = db.get(FinFornecedor, fid)
        if outro is None or outro.id == manter.id:
            continue
        for lanc in db.scalars(select(FinLancamento).where(FinLancamento.fornecedor_id == outro.id)):
            lanc.fornecedor_id = manter.id
        for rec in db.scalars(select(FinRecorrente).where(FinRecorrente.fornecedor_id == outro.id)):
            rec.fornecedor_id = manter.id
        apelidos += [outro.nome] + [a for a in (outro.apelidos or "").split(";") if a.strip()]
        if outro.documento and not manter.documento:
            doc = outro.documento
            outro.documento = None
            db.flush()
            manter.documento = doc
        db.delete(outro)
    manter.apelidos = ";".join(dict.fromkeys(a.strip() for a in apelidos if a.strip())) or None
    db.commit()
    return {"id": manter.id}


def aprender_fornecedor(f: FinFornecedor | None, lanc: FinLancamento) -> None:
    """A última classificação usada vira a sugestão da próxima vez."""
    if f is None or not lanc.categoria:
        return
    f.pad_tipo, f.pad_fazenda, f.pad_setor = lanc.tipo, lanc.fazenda, lanc.setor
    f.pad_grupo, f.pad_categoria = lanc.grupo, lanc.categoria
    if lanc.conta:
        f.pad_conta = lanc.conta


def sugestao_fornecedor(db: Session, nome: str | None, documento: str | None = None) -> dict | None:
    f = achar_ou_criar_fornecedor(db, nome, documento, criar=False)
    if f is None or not f.pad_categoria:
        return None
    return {"fornecedor_id": f.id, "tipo": f.pad_tipo, "fazenda": f.pad_fazenda, "setor": f.pad_setor,
            "grupo": f.pad_grupo, "categoria": f.pad_categoria, "conta": f.pad_conta}


# ---------------------------------------------------------------- lançamentos

def montar_parcelas(dados: dict, total: float, data_compra: date) -> list[dict]:
    """Parcelas explícitas (lista) ou geradas: N vezes, a 1ª no vencimento informado
    (padrão = data da compra), as outras de mês em mês. Centavos que sobram vão na última."""
    lista = dados.get("parcelas")
    if lista:
        out = []
        for i, p in enumerate(lista, start=1):
            out.append({"numero": i, "vencimento": _data(p.get("vencimento"), "vencimento"),
                        "valor": round(_num(p.get("valor")), 2), "conta": p.get("conta") or None,
                        "pago": p.get("pago")})
        return out
    n = max(1, int(dados.get("n_parcelas") or 1))
    primeiro = _data(dados.get("primeiro_vencimento") or data_compra, "vencimento")
    base = round(total / n, 2)
    out = [{"numero": i + 1, "vencimento": somar_meses(primeiro, i), "valor": base,
            "conta": None, "pago": dados.get("pago")} for i in range(n)]
    out[-1]["valor"] = round(total - base * (n - 1), 2)
    return out


def _aplicar(db: Session, lanc: FinLancamento, dados: dict, usuario: str) -> None:
    tipo = dados.get("tipo") or lanc.tipo or "despesa"
    if tipo not in TIPOS_LANCAMENTO:
        raise ErroFinanceiro("Tipo deve ser despesa ou receita")
    lanc.tipo = tipo
    lanc.data = _data(dados.get("data") or lanc.data)
    for campo in ("fazenda", "setor", "grupo", "categoria", "descricao", "conta",
                  "forma_pagamento", "nf_numero", "observacao"):
        if campo in dados:
            valor = dados.get(campo)
            setattr(lanc, campo, (str(valor).strip() or None) if valor is not None else None)
    if "nf_chave" in dados:
        lanc.nf_chave = so_digitos(dados.get("nf_chave")) or None
    total = round(_num(dados.get("valor_total", lanc.valor_total)), 2)
    if total <= 0:
        raise ErroFinanceiro("Informe um valor maior que zero")
    lanc.valor_total = total

    if "fornecedor_id" in dados or "fornecedor_nome" in dados or "fornecedor_documento" in dados:
        f = db.get(FinFornecedor, dados["fornecedor_id"]) if dados.get("fornecedor_id") else None
        if f is None:
            f = achar_ou_criar_fornecedor(db, dados.get("fornecedor_nome"), dados.get("fornecedor_documento"))
        lanc.fornecedor_id = f.id if f else None
        lanc.fornecedor_nome = f.nome if f else None

    soma_atual = round(sum(p.valor for p in lanc.parcelas), 2)
    if "parcelas" in dados or "n_parcelas" in dados or not lanc.parcelas or abs(soma_atual - total) > 0.05:
        if lanc.parcelas and "parcelas" not in dados and "n_parcelas" not in dados:
            # Mudou só o total: refaz as parcelas mantendo quantidade e 1º vencimento.
            dados = {**dados, "n_parcelas": len(lanc.parcelas),
                     "primeiro_vencimento": lanc.parcelas[0].vencimento}
        novas = montar_parcelas(dados, total, lanc.data)
        lanc.parcelas.clear()
        db.flush()
        for p in novas:
            lanc.parcelas.append(FinParcela(**p))
    soma = round(sum(p.valor for p in lanc.parcelas), 2)
    if abs(soma - total) > 0.05:
        raise ErroFinanceiro(f"A soma das parcelas (R$ {soma:.2f}) não bate com o total (R$ {total:.2f})")

    # Sai da fila de revisão quando tem categoria e alguém salvou conferindo.
    if dados.get("conferido"):
        lanc.revisar, lanc.revisar_motivo = False, None
    if not lanc.categoria:
        lanc.revisar, lanc.revisar_motivo = True, "Sem categoria"
    garantir_categoria(db, lanc.tipo, lanc.setor, lanc.grupo, lanc.categoria)
    if lanc.fornecedor_id:
        aprender_fornecedor(db.get(FinFornecedor, lanc.fornecedor_id), lanc)


def criar(db: Session, dados: dict, usuario: str, origem: str = "manual", commit=True) -> FinLancamento:
    lanc = FinLancamento(origem=origem, criado_por=usuario, criado_em=agora_utc(),
                         data=_data(dados.get("data") or date.today()))
    db.add(lanc)
    _aplicar(db, lanc, dados, usuario)
    if commit:
        db.commit()
    return lanc


def atualizar(db: Session, lanc_id: int, dados: dict, usuario: str) -> FinLancamento:
    lanc = _buscar(db, lanc_id)
    _aplicar(db, lanc, dados, usuario)
    lanc.alterado_por, lanc.alterado_em = usuario, agora_utc()
    db.commit()
    return lanc


def excluir(db: Session, lanc_id: int, motivo: str, usuario: str) -> None:
    """Não apaga: marca excluído (sai dos relatórios, fica no histórico)."""
    lanc = _buscar(db, lanc_id)
    lanc.excluido, lanc.excluido_motivo = True, (motivo or "Excluído").strip()[:200]
    lanc.excluido_em, lanc.alterado_por = agora_utc(), usuario
    db.commit()


def restaurar(db: Session, lanc_id: int, usuario: str) -> None:
    lanc = _buscar(db, lanc_id)
    lanc.excluido, lanc.excluido_motivo, lanc.excluido_em = False, None, None
    lanc.alterado_por, lanc.alterado_em = usuario, agora_utc()
    db.commit()


def marcar_parcela(db: Session, parcela_id: int, pago: bool | None, valor=None) -> None:
    p = db.get(FinParcela, parcela_id)
    if p is None:
        raise ErroFinanceiro("Parcela não encontrada")
    p.pago = pago
    if valor not in (None, ""):
        novo = round(_num(valor), 2)
        p.lancamento.valor_total = round(p.lancamento.valor_total - p.valor + novo, 2)
        p.valor = novo
    db.commit()


def _buscar(db: Session, lanc_id: int) -> FinLancamento:
    lanc = db.get(FinLancamento, lanc_id)
    if lanc is None:
        raise ErroFinanceiro("Lançamento não encontrado")
    return lanc


def dict_lancamento(lc: FinLancamento, hoje: date | None = None) -> dict:
    hoje = hoje or date.today()
    return {
        "id": lc.id, "tipo": lc.tipo, "data": lc.data.isoformat(), "fazenda": lc.fazenda,
        "setor": lc.setor, "grupo": lc.grupo, "categoria": lc.categoria,
        "fornecedor_id": lc.fornecedor_id, "fornecedor_nome": lc.fornecedor_nome,
        "descricao": lc.descricao, "valor_total": lc.valor_total, "conta": lc.conta,
        "forma_pagamento": lc.forma_pagamento, "nf_numero": lc.nf_numero, "nf_chave": lc.nf_chave,
        "observacao": lc.observacao, "origem": lc.origem, "revisar": lc.revisar,
        "revisar_motivo": lc.revisar_motivo, "excluido": lc.excluido, "excluido_motivo": lc.excluido_motivo,
        "criado_por": lc.criado_por, "criado_em": iso_utc(lc.criado_em),
        "alterado_por": lc.alterado_por, "alterado_em": iso_utc(lc.alterado_em),
        "recorrente_id": lc.recorrente_id,
        "parcelas": [{"id": p.id, "numero": p.numero, "vencimento": p.vencimento.isoformat(),
                      "valor": p.valor, "conta": p.conta, "pago": p.pago,
                      "realizado": parcela_realizada(p, hoje)} for p in lc.parcelas],
    }


def listar(db: Session, excluidos: bool = False) -> list[dict]:
    """Todos os lançamentos (o filtro roda no aparelho, como na Planilha do rebanho)."""
    q = (select(FinLancamento).options(selectinload(FinLancamento.parcelas))
         .where(FinLancamento.excluido.is_(excluidos)).order_by(FinLancamento.data.desc(), FinLancamento.id.desc()))
    hoje = date.today()
    return [dict_lancamento(lc, hoje) for lc in db.scalars(q)]


def detalhe(db: Session, lanc_id: int) -> dict:
    return dict_lancamento(_buscar(db, lanc_id))


def possiveis_duplicados(db: Session) -> list[list[int]]:
    """Mesma chave de nota, ou mesmo fornecedor + mesmo valor + MESMA descrição com datas a até
    3 dias. Descrição com qualquer palavra diferente (ex.: parcela 1/2P × 2/2P) não é duplicado;
    só espaços e maiúsculas/minúsculas são ignorados."""
    lancs = db.scalars(select(FinLancamento).where(FinLancamento.excluido.is_(False),
                                                   FinLancamento.dup_ok.is_(False))
                       .order_by(FinLancamento.data)).all()
    grupos, vistos = [], set()
    por_chave: dict[str, list[FinLancamento]] = {}
    for lc in lancs:
        if lc.nf_chave:
            por_chave.setdefault(lc.nf_chave, []).append(lc)
    for lista in por_chave.values():
        # Nota dividida por produto gera várias partes com a mesma chave (origem "nota"): não é duplicado.
        if len(lista) > 1 and sum(lc.origem == "nota" for lc in lista) < len(lista):
            grupos.append([lc.id for lc in lista])
            vistos.update(lc.id for lc in lista)
    por_forn: dict[tuple, list[FinLancamento]] = {}
    for lc in lancs:
        if lc.fornecedor_id and lc.origem != "recorrente":
            desc = " ".join((lc.descricao or "").split()).casefold()
            por_forn.setdefault((lc.fornecedor_id, round(lc.valor_total, 2), desc), []).append(lc)
    for lista in por_forn.values():
        for a, b in zip(lista, lista[1:]):
            if (b.data - a.data).days <= 3 and a.id not in vistos and b.id not in vistos:
                if a.nf_numero and b.nf_numero and a.nf_numero != b.nf_numero:
                    continue  # notas diferentes: compra repetida de verdade
                grupos.append([a.id, b.id])
                vistos.update((a.id, b.id))
    return grupos


def marcar_nao_duplicado(db: Session, ids: list[int]) -> None:
    for lc in db.scalars(select(FinLancamento).where(FinLancamento.id.in_(ids))):
        lc.dup_ok = True
    db.commit()


# ---------------------------------------------------------------- recorrentes

def salvar_recorrente(db: Session, dados: dict, rid: int | None) -> dict:
    r = FinRecorrente() if rid is None else db.get(FinRecorrente, rid)
    if r is None:
        raise ErroFinanceiro("Recorrente não encontrado")
    if not (dados.get("descricao") or "").strip():
        raise ErroFinanceiro("Informe a descrição")
    for campo in ("descricao", "tipo", "fazenda", "setor", "grupo", "categoria", "conta"):
        if campo in dados:
            setattr(r, campo, (dados.get(campo) or "").strip() or None)
    r.tipo = r.tipo or "despesa"
    r.valor = round(_num(dados.get("valor", r.valor)), 2)
    r.dia = min(31, max(1, int(dados.get("dia") or r.dia or 10)))
    r.inicio = _data(dados["inicio"]) if dados.get("inicio") else (r.inicio or date.today().replace(day=1))
    if "ativo" in dados:
        r.ativo = bool(dados["ativo"])
    if dados.get("fornecedor_nome") or dados.get("fornecedor_id"):
        f = db.get(FinFornecedor, dados["fornecedor_id"]) if dados.get("fornecedor_id") else \
            achar_ou_criar_fornecedor(db, dados.get("fornecedor_nome"))
        r.fornecedor_id, r.fornecedor_nome = f.id, f.nome
    db.add(r)
    db.commit()
    gerar_recorrentes(db)
    return {"id": r.id}


def listar_recorrentes(db: Session) -> list[dict]:
    return [{"id": r.id, "descricao": r.descricao, "tipo": r.tipo, "fazenda": r.fazenda, "setor": r.setor,
             "grupo": r.grupo, "categoria": r.categoria, "fornecedor_id": r.fornecedor_id,
             "fornecedor_nome": r.fornecedor_nome, "valor": r.valor, "conta": r.conta, "dia": r.dia,
             "inicio": r.inicio.isoformat() if r.inicio else None, "ativo": r.ativo}
            for r in db.scalars(select(FinRecorrente).order_by(FinRecorrente.descricao))]


def gerar_recorrentes(db: Session, hoje: date | None = None) -> int:
    """Cria o lançamento 'a confirmar' de cada recorrente ativo, do mês de início até o
    mês atual (+ o próximo, pra já aparecer no previsto). Não duplica (recorrente_mes)."""
    hoje = hoje or date.today()
    criados = 0
    for r in db.scalars(select(FinRecorrente).where(FinRecorrente.ativo.is_(True))):
        ja = set(db.scalars(select(FinLancamento.recorrente_mes)
                            .where(FinLancamento.recorrente_id == r.id)))
        mes = (r.inicio or hoje).replace(day=1)
        limite = somar_meses(hoje.replace(day=1), 1)
        while mes <= limite:
            chave = mes.strftime("%Y-%m")
            if chave not in ja:
                venc = somar_meses(mes, 0, r.dia)
                lanc = FinLancamento(
                    tipo=r.tipo, data=venc, fazenda=r.fazenda, setor=r.setor, grupo=r.grupo,
                    categoria=r.categoria, fornecedor_id=r.fornecedor_id, fornecedor_nome=r.fornecedor_nome,
                    descricao=r.descricao, valor_total=r.valor or 0, conta=r.conta, origem="recorrente",
                    recorrente_id=r.id, recorrente_mes=chave, criado_por="automático",
                    revisar=not r.categoria, revisar_motivo=None if r.categoria else "Sem categoria")
                lanc.parcelas.append(FinParcela(numero=1, vencimento=venc, valor=r.valor or 0, pago=False))
                db.add(lanc)
                criados += 1
            mes = somar_meses(mes, 1)
    if criados:
        db.commit()
    return criados


def a_confirmar(db: Session) -> list[dict]:
    """Recorrentes/parcelas marcadas 'a confirmar' (pago = False) já vencidas ou do mês."""
    limite = somar_meses(date.today().replace(day=1), 1) - timedelta(days=1)
    q = (select(FinLancamento).join(FinParcela)
         .where(FinLancamento.excluido.is_(False), FinParcela.pago.is_(False), FinParcela.vencimento <= limite)
         .options(selectinload(FinLancamento.parcelas)).distinct())
    return [dict_lancamento(lc) for lc in db.scalars(q)]
