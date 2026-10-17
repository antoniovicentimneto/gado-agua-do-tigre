"""Leitura do XML da NF-e (nota completa, nota com protocolo ou só o resumo da SEFAZ).

Tira do XML o que interessa pro lançamento: emitente (CNPJ/CPF + nome), data, número,
valor, cada produto (descrição, NCM, qtde, valor), as duplicatas (vencimentos) e a forma
de pagamento. Usa só a biblioteca padrão (xml.etree)."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date

NS = "{http://www.portalfiscal.inf.br/nfe}"

# Tabela tPag da NF-e (meio de pagamento).
FORMAS_PAGAMENTO = {
    "01": "Dinheiro", "02": "Cheque", "03": "Cartão de crédito", "04": "Cartão de débito",
    "05": "Crédito loja", "10": "Vale alimentação", "11": "Vale refeição", "12": "Vale presente",
    "13": "Vale combustível", "15": "Boleto", "16": "Depósito", "17": "Pix",
    "18": "Transferência", "19": "Programa de fidelidade", "90": "Sem pagamento", "99": "Outros",
}


class XmlInvalido(Exception):
    """O arquivo não é um XML de NF-e que o app saiba ler."""


def _t(no, caminho: str) -> str | None:
    if no is None:
        return None
    el = no.find(_ns(caminho))
    return el.text.strip() if el is not None and el.text else None


def _ns(caminho: str) -> str:
    return "/".join(NS + parte for parte in caminho.split("/"))


def _f(no, caminho: str) -> float:
    v = _t(no, caminho)
    try:
        return float(v) if v else 0.0
    except ValueError:
        return 0.0


def _data(txt: str | None) -> date | None:
    if not txt:
        return None
    try:
        return date.fromisoformat(txt[:10])
    except ValueError:
        return None


def _doc(no) -> str | None:
    return _t(no, "CNPJ") or _t(no, "CPF")


def ler(xml: str | bytes) -> dict:
    """Devolve um dicionário com a nota. `completa=False` quando é só o resumo (resNFe)."""
    try:
        raiz = ET.fromstring(xml if isinstance(xml, bytes) else xml.encode("utf-8"))
    except ET.ParseError:
        raise XmlInvalido("O arquivo não é um XML válido")
    tag = raiz.tag.replace(NS, "")

    if tag == "resNFe":  # resumo que a SEFAZ manda antes da ciência
        return {
            "completa": False, "chave": _t(raiz, "chNFe"), "emitente_doc": _doc(raiz),
            "emitente_nome": _t(raiz, "xNome"), "data_emissao": _data(_t(raiz, "dhEmi")),
            "valor": _f(raiz, "vNF"), "numero": None, "serie": None, "itens": [], "duplicatas": [],
            "pagamentos": [], "destinatario_doc": None, "info": None,
        }

    inf = raiz.find(f".//{NS}infNFe")
    if inf is None:
        raise XmlInvalido("Este XML não é de NF-e (não achei a tag infNFe)")
    chave = (inf.get("Id") or "").replace("NFe", "") or _t(raiz, "protNFe/infProt/chNFe")
    ide, emit, dest = inf.find(NS + "ide"), inf.find(NS + "emit"), inf.find(NS + "dest")
    itens = []
    for det in inf.findall(NS + "det"):
        prod = det.find(NS + "prod")
        itens.append({
            "n": int(det.get("nItem") or len(itens) + 1),
            "codigo": _t(prod, "cProd"), "descricao": _t(prod, "xProd"), "ncm": _t(prod, "NCM"),
            "cfop": _t(prod, "CFOP"), "qtde": _f(prod, "qCom"), "unidade": _t(prod, "uCom"),
            "valor_unit": _f(prod, "vUnCom"),
            "valor": round(_f(prod, "vProd") - _f(prod, "vDesc") + _f(prod, "vFrete")
                           + _f(prod, "vOutro") + _f(prod, "vSeg"), 2),
        })
    duplicatas = [{"numero": _t(d, "nDup"), "vencimento": _data(_t(d, "dVenc")), "valor": _f(d, "vDup")}
                  for d in inf.findall(f"{NS}cobr/{NS}dup")]
    pagamentos = [{"forma": FORMAS_PAGAMENTO.get(_t(p, "tPag") or "", "Outros"), "codigo": _t(p, "tPag"),
                   "valor": _f(p, "vPag")} for p in inf.findall(f"{NS}pag/{NS}detPag")]
    total = _f(inf, "total/ICMSTot/vNF")
    return {
        "completa": True, "chave": chave, "modelo": _t(ide, "mod"), "numero": _t(ide, "nNF"),
        "serie": _t(ide, "serie"), "data_emissao": _data(_t(ide, "dhEmi") or _t(ide, "dEmi")),
        "emitente_doc": _doc(emit), "emitente_nome": _t(emit, "xFant") or _t(emit, "xNome"),
        "emitente_razao": _t(emit, "xNome"), "destinatario_doc": _doc(dest),
        "destinatario_nome": _t(dest, "xNome"), "valor": total or round(sum(i["valor"] for i in itens), 2),
        "itens": itens, "duplicatas": [d for d in duplicatas if d["vencimento"]], "pagamentos": pagamentos,
        "info": _t(inf, "infAdic/infCpl"),
    }


def forma_principal(nota: dict) -> str | None:
    """Forma de pagamento que mais pesa na nota (pra preencher o campo)."""
    pags = [p for p in nota.get("pagamentos") or [] if p["codigo"] != "90"]
    if not pags:
        return "Boleto" if nota.get("duplicatas") else None
    return max(pags, key=lambda p: p["valor"])["forma"]
