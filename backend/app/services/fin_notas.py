"""Caixa de entrada de notas fiscais: receber XML, sugerir classificação, lançar, aprender.

A sugestão vem do que já foi lançado antes (FinRegra): primeiro fornecedor + tipo de
produto (NCM), depois fornecedor, depois só o tipo de produto, por fim a classificação
padrão do fornecedor. Nada é lançado sem a pessoa confirmar."""
from __future__ import annotations

import io
import zipfile
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models_financeiro import FinContribuinte, FinLancamento, FinNota, FinRegra
from . import fin_lancamentos as lanc_svc
from . import fin_nfe_xml
from .fin_plano import ErroFinanceiro

CAMPOS_CLASSE = ("tipo", "fazenda", "setor", "grupo", "categoria", "conta")


def _ncm4(ncm: str | None) -> str:
    return (ncm or "")[:4]


# ---------------------------------------------------------------- receber

def guardar_nota(db: Session, xml: str, origem: str = "xml", contribuinte_id: int | None = None,
                 nsu: str | None = None) -> FinNota:
    """Grava/atualiza a nota pela chave. Um XML completo substitui o resumo."""
    dados = fin_nfe_xml.ler(xml)
    if not dados.get("chave") or len(dados["chave"]) != 44:
        raise fin_nfe_xml.XmlInvalido("Não achei a chave de acesso (44 dígitos) no XML")
    nota = db.scalar(select(FinNota).where(FinNota.chave == dados["chave"]))
    if nota is None:
        nota = FinNota(chave=dados["chave"], origem=origem, situacao="nova")
        db.add(nota)
    if contribuinte_id and not nota.contribuinte_id:
        nota.contribuinte_id = contribuinte_id
    if nsu:
        nota.nsu = nsu
    nota.emitente_doc = dados.get("emitente_doc") or nota.emitente_doc
    nota.emitente_nome = dados.get("emitente_nome") or nota.emitente_nome
    nota.data_emissao = dados.get("data_emissao") or nota.data_emissao
    nota.valor = dados.get("valor") or nota.valor
    if dados["completa"]:
        nota.xml = xml if isinstance(xml, str) else xml.decode("utf-8", "replace")
        nota.numero = dados.get("numero")
        nota.destinatario_doc = dados.get("destinatario_doc")
        if nota.situacao == "nova":
            nota.situacao = "completa"
    # Já lançada à mão antes (mesma chave)? Liga e tira da caixa de entrada.
    if nota.situacao in ("nova", "completa"):
        ja = db.scalar(select(FinLancamento.id).where(FinLancamento.nf_chave == nota.chave,
                                                      FinLancamento.excluido.is_(False)))
        if ja:
            nota.situacao, nota.lancamento_id = "lancada", ja
    db.flush()
    return nota


def receber_arquivos(db: Session, arquivos: list[tuple[str, bytes]]) -> dict:
    """Aceita .xml soltos ou .zip com vários XML (como os fornecedores mandam)."""
    ok, erros = 0, []
    for nome, conteudo in arquivos:
        pacotes = []
        if nome.lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
                    pacotes = [(n, z.read(n)) for n in z.namelist() if n.lower().endswith(".xml")]
            except zipfile.BadZipFile:
                erros.append(f"{nome}: arquivo .zip com defeito")
                continue
        else:
            pacotes = [(nome, conteudo)]
        for n, c in pacotes:
            try:
                guardar_nota(db, c.decode("utf-8", "replace"))
                ok += 1
            except fin_nfe_xml.XmlInvalido as e:
                erros.append(f"{n}: {e}")
    db.commit()
    return {"importadas": ok, "erros": erros}


# ---------------------------------------------------------------- sugerir

def _regra(db: Session, doc: str, ncm: str) -> FinRegra | None:
    return db.scalar(select(FinRegra).where(FinRegra.fornecedor_doc == doc, FinRegra.ncm == ncm))


def _de_regra(r: FinRegra | None, origem: str) -> dict | None:
    if r is None or not r.categoria:
        return None
    return {**{c: getattr(r, c) for c in CAMPOS_CLASSE}, "origem": origem}


def sugerir(db: Session, nota: FinNota, dados: dict) -> dict:
    """Classificação sugerida pra nota toda e pra cada item."""
    doc = nota.emitente_doc or ""
    forn = lanc_svc.achar_ou_criar_fornecedor(db, nota.emitente_nome, doc, criar=False)
    contrib = db.get(FinContribuinte, nota.contribuinte_id) if nota.contribuinte_id else None
    padrao_forn = None
    if forn and forn.pad_categoria:
        padrao_forn = {"tipo": forn.pad_tipo, "fazenda": forn.pad_fazenda, "setor": forn.pad_setor,
                       "grupo": forn.pad_grupo, "categoria": forn.pad_categoria, "conta": forn.pad_conta,
                       "origem": "último lançamento deste fornecedor"}
    geral = (_de_regra(_regra(db, doc, ""), "notas anteriores deste fornecedor") or padrao_forn)
    itens = []
    for it in dados.get("itens", []):
        n4 = _ncm4(it.get("ncm"))
        s = (_de_regra(_regra(db, doc, n4), "este produto deste fornecedor")
             or _de_regra(_regra(db, "", n4), "mesmo tipo de produto (NCM) de outro fornecedor")
             or geral)
        itens.append(s)
    if geral is None:
        geral = next((s for s in itens if s), None)
    if geral is not None and contrib and contrib.fazenda and not geral.get("fazenda"):
        geral = {**geral, "fazenda": contrib.fazenda}
    return {"geral": geral, "itens": itens, "fornecedor_id": forn.id if forn else None}


def dict_nota(db: Session, nota: FinNota, com_sugestao: bool = False) -> dict:
    out = {"id": nota.id, "chave": nota.chave, "origem": nota.origem, "situacao": nota.situacao,
           "emitente_doc": nota.emitente_doc, "emitente_nome": nota.emitente_nome, "numero": nota.numero,
           "data_emissao": nota.data_emissao.isoformat() if nota.data_emissao else None,
           "valor": nota.valor, "completa": bool(nota.xml), "lancamento_id": nota.lancamento_id,
           "contribuinte_id": nota.contribuinte_id,
           "recebida_em": nota.recebida_em.isoformat() if nota.recebida_em else None}
    if com_sugestao:
        dados = fin_nfe_xml.ler(nota.xml) if nota.xml else {"itens": [], "duplicatas": [], "pagamentos": []}
        out["itens"] = dados.get("itens", [])
        out["duplicatas"] = [{**d, "vencimento": d["vencimento"].isoformat()} for d in dados.get("duplicatas", [])]
        out["pagamentos"] = dados.get("pagamentos", [])
        out["forma_pagamento"] = fin_nfe_xml.forma_principal(dados) if nota.xml else None
        out["info"] = dados.get("info")
        out["sugestao"] = sugerir(db, nota, dados)
    return out


def listar(db: Session, situacao: str | None = None) -> list[dict]:
    q = select(FinNota).order_by(FinNota.data_emissao.desc().nulls_last(), FinNota.id.desc())
    if situacao == "pendentes":
        q = q.where(FinNota.situacao.in_(("nova", "completa")))
    elif situacao:
        q = q.where(FinNota.situacao == situacao)
    return [dict_nota(db, n) for n in db.scalars(q)]


def detalhe(db: Session, nota_id: int) -> dict:
    nota = db.get(FinNota, nota_id)
    if nota is None:
        raise ErroFinanceiro("Nota não encontrada")
    return dict_nota(db, nota, com_sugestao=True)


# ---------------------------------------------------------------- lançar

def _ratear(valores: list[float], total: float) -> list[float]:
    """Divide `total` na proporção de `valores` (centavos que sobram na última)."""
    soma = sum(valores) or 1
    partes = [round(total * v / soma, 2) for v in valores]
    if partes:
        partes[-1] = round(total - sum(partes[:-1]), 2)
    return partes


def lancar(db: Session, nota_id: int, dados: dict, usuario: str) -> dict:
    """Lança a nota. `partes` = lista de {itens: [n...], tipo, fazenda, setor, grupo,
    categoria, descricao}; sem itens = a nota toda. `parcelas` = vencimentos (da nota ou
    preenchidos à mão). Cada parte vira um lançamento com as parcelas rateadas."""
    nota = db.get(FinNota, nota_id)
    if nota is None:
        raise ErroFinanceiro("Nota não encontrada")
    if nota.situacao == "lancada":
        raise ErroFinanceiro("Esta nota já foi lançada")
    info = fin_nfe_xml.ler(nota.xml) if nota.xml else {"itens": [], "duplicatas": []}
    itens = {i["n"]: i for i in info.get("itens", [])}
    total_nota = round(float(dados.get("valor_total") or nota.valor or 0), 2)
    partes = dados.get("partes") or [{}]
    parcelas = dados.get("parcelas") or [{"vencimento": (nota.data_emissao or date.today()).isoformat(),
                                          "valor": total_nota}]
    soma_itens = sum(i["valor"] for i in itens.values()) or total_nota
    valores_partes = []
    for p in partes:
        sel = p.get("itens")
        valores_partes.append(sum(itens[n]["valor"] for n in sel if n in itens) if sel else soma_itens)
    if len(partes) > 1 and abs(sum(valores_partes) - soma_itens) > 0.05:
        raise ErroFinanceiro("Cada item da nota precisa estar em uma (e só uma) das partes")
    totais = _ratear(valores_partes, total_nota)

    forn = lanc_svc.achar_ou_criar_fornecedor(db, dados.get("fornecedor_nome") or nota.emitente_nome,
                                              nota.emitente_doc)
    criados = []
    for parte, total_parte in zip(partes, totais):
        if not parte.get("categoria"):
            raise ErroFinanceiro("Escolha a categoria (todas as partes)")
        valores = _ratear([float(p.get("valor") or 0) for p in parcelas], total_parte)
        descr = parte.get("descricao") or dados.get("descricao") or _descricao_itens(parte.get("itens"), itens)
        lanc = lanc_svc.criar(db, {
            "tipo": parte.get("tipo") or "despesa", "data": dados.get("data") or nota.data_emissao,
            **{c: parte.get(c) or dados.get(c) for c in ("fazenda", "setor", "grupo", "categoria")},
            "conta": parte.get("conta") or dados.get("conta"), "forma_pagamento": dados.get("forma_pagamento"),
            "fornecedor_id": forn.id if forn else None, "descricao": descr, "valor_total": total_parte,
            "nf_numero": nota.numero, "nf_chave": nota.chave, "observacao": dados.get("observacao"),
            "parcelas": [{"vencimento": p["vencimento"], "valor": v, "conta": p.get("conta")}
                         for p, v in zip(parcelas, valores)],
        }, usuario, origem="nota", commit=False)
        criados.append(lanc)
        itens_parte = [itens[n] for n in (parte.get("itens") or itens.keys()) if n in itens]
        _aprender(db, nota.emitente_doc or "", parte, itens_parte, inteira=len(partes) == 1)
    db.flush()
    nota.situacao, nota.lancamento_id = "lancada", criados[0].id
    db.commit()
    return {"lancamentos": [lc.id for lc in criados]}


def _descricao_itens(sel, itens: dict) -> str:
    nomes = [itens[n]["descricao"] for n in (sel or itens.keys()) if n in itens and itens[n]["descricao"]]
    if not nomes:
        return "Nota fiscal"
    texto = ", ".join(nomes[:3]) + (f" e mais {len(nomes) - 3}" if len(nomes) > 3 else "")
    return texto[:300]


def _aprender(db: Session, doc: str, parte: dict, itens: list[dict], inteira: bool) -> None:
    def gravar(d, ncm):
        r = _regra(db, d, ncm) or FinRegra(fornecedor_doc=d, ncm=ncm)
        for c in CAMPOS_CLASSE:
            if parte.get(c):
                setattr(r, c, parte.get(c))
        r.vezes = (r.vezes or 0) + 1
        db.add(r)
        db.flush()
    if inteira and doc:
        gravar(doc, "")
    for ncm in {_ncm4(i.get("ncm")) for i in itens if i.get("ncm")}:
        if doc:
            gravar(doc, ncm)
        gravar("", ncm)


def ignorar(db: Session, nota_id: int, voltar: bool = False) -> None:
    nota = db.get(FinNota, nota_id)
    if nota is None:
        raise ErroFinanceiro("Nota não encontrada")
    if voltar:
        nota.situacao = "completa" if nota.xml else "nova"
    elif nota.situacao != "lancada":
        nota.situacao = "ignorada"
    db.commit()
