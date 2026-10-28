"""Busca das NF-e emitidas contra um CPF/CNPJ na SEFAZ (Ambiente Nacional).

Fluxo (NT 2014.002 — NFeDistribuicaoDFe + Manifestação do Destinatário):
1. distNSU: pede os documentos a partir do último NSU recebido (50 por vez).
   Chega o RESUMO da nota (resNFe) — emitente, valor, data, chave.
2. Ciência da Operação (evento 210210, assinado com o certificado): não aceita nem
   recusa a nota, só libera o XML completo.
3. O XML completo (procNFe) chega numa próxima consulta ou pela consulta por chave.

Exige certificado digital A1 (e-CPF ou e-CNPJ) do próprio CPF/CNPJ consultado.
Regra da SEFAZ: sem documento novo (cStat 137) ou consumo indevido (656) -> esperar 1 h.
A espera vale só para a busca de documentos NOVOS (distNSU). A Ciência e a busca do XML
completo pela chave continuam rodando a cada clique — assim as notas que chegaram só com o
resumo baixam inteiras sem esperar a próxima hora.
"""
from __future__ import annotations

import base64
import gzip
import os
import ssl
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from hashlib import sha1

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models_financeiro import FinContribuinte, FinNota
from . import fin_cripto, fin_notas
from .fin_plano import agora_utc

NS_NFE = "http://www.portalfiscal.inf.br/nfe"
NS_DS = "http://www.w3.org/2000/09/xmldsig#"
URLS = {
    1: {"dist": "https://www1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx",
        "evento": "https://www.nfe.fazenda.gov.br/NFeRecepcaoEvento4/NFeRecepcaoEvento4.asmx"},
    2: {"dist": "https://hom1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx",
        "evento": "https://hom1.nfe.fazenda.gov.br/NFeRecepcaoEvento4/NFeRecepcaoEvento4.asmx"},
}
ACAO_DIST = "http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe/nfeDistDFeInteresse"
ACAO_EVENTO = "http://www.portalfiscal.inf.br/nfe/wsdl/NFeRecepcaoEvento4/nfeRecepcaoEvento"
CODIGOS_UF = {"RO": "11", "AC": "12", "AM": "13", "RR": "14", "PA": "15", "AP": "16", "TO": "17",
              "MA": "21", "PI": "22", "CE": "23", "RN": "24", "PB": "25", "PE": "26", "AL": "27",
              "SE": "28", "BA": "29", "MG": "31", "ES": "32", "RJ": "33", "SP": "35", "PR": "41",
              "SC": "42", "RS": "43", "MS": "50", "MT": "51", "GO": "52", "DF": "53"}
ESPERA = timedelta(hours=1, minutes=5)  # a SEFAZ pede 1 h; 5 min de folga
MAX_LOTES_POR_CONSULTA = 20  # 20 x 50 = até 1000 documentos por vez
# Durante a espera de 1 h, completar (ciência + XML por chave) no máximo a cada 5 min — a tela
# de Notas busca sozinha ao abrir e, sem freio, viraria "consumo indevido" (656).
INTERVALO_COMPLETAR = timedelta(minutes=5)
_ultimo_completar: dict[int, datetime] = {}


class ErroSefaz(Exception):
    """Falha de comunicação ou recusa da SEFAZ (mensagem amigável)."""


# ---------------------------------------------------------------- transporte (troca nos testes)

def _enviar_https(url: str, envelope: str, acao: str, pem_cert: bytes, pem_chave: bytes) -> str:
    """POST SOAP 1.2 com o certificado do cliente (TLS mútuo)."""
    import httpx

    contexto = ssl.create_default_context()
    arquivos = []
    try:
        for conteudo in (pem_cert, pem_chave):
            f = tempfile.NamedTemporaryFile(delete=False, suffix=".pem")
            f.write(conteudo)
            f.close()
            arquivos.append(f.name)
        contexto.load_cert_chain(arquivos[0], arquivos[1])
    finally:
        for caminho in arquivos:  # a chave não fica no disco
            try:
                os.remove(caminho)
            except OSError:
                pass
    try:
        r = httpx.post(url, content=envelope.encode("utf-8"), verify=contexto, timeout=40,
                       headers={"Content-Type": f'application/soap+xml; charset=utf-8; action="{acao}"'})
    except httpx.HTTPError as e:
        raise ErroSefaz(f"Não consegui falar com a SEFAZ ({e.__class__.__name__}). Tente mais tarde.")
    if r.status_code >= 500 and "Fault" not in r.text:
        raise ErroSefaz(f"A SEFAZ respondeu com erro {r.status_code}. Tente mais tarde.")
    return r.text


transporte = _enviar_https


# ---------------------------------------------------------------- certificado

def _credenciais(c: FinContribuinte):
    if not c.cert_pfx or not c.cert_senha:
        raise ErroSefaz("Este CPF/CNPJ ainda não tem certificado digital cadastrado")
    pfx = fin_cripto.decifrar(c.cert_pfx)
    senha = fin_cripto.decifrar(c.cert_senha.encode()).decode()
    chave, cert, _info = fin_cripto.ler_certificado(pfx, senha)
    pem_cert = cert.public_bytes(serialization.Encoding.PEM)
    pem_chave = chave.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                    serialization.NoEncryption())
    return chave, cert, pem_cert, pem_chave


def guardar_certificado(db: Session, c: FinContribuinte, pfx: bytes, senha: str) -> dict:
    _chave, _cert, info = fin_cripto.ler_certificado(pfx, senha)
    doc_cert = fin_cripto.documento_do_certificado(info["titular"])
    if doc_cert and c.documento and doc_cert != c.documento:
        # e-CNPJ serve pra filiais (mesma raiz); e-CPF tem que ser do mesmo CPF.
        if not (len(doc_cert) == 14 and len(c.documento) == 14 and doc_cert[:8] == c.documento[:8]):
            raise fin_cripto.CertificadoInvalido(
                f"Este certificado é de outro documento ({doc_cert}). Use o certificado de {c.documento}.")
    c.cert_pfx = fin_cripto.cifrar(pfx)
    c.cert_senha = fin_cripto.cifrar(senha.encode()).decode()
    c.cert_titular, c.cert_validade = info["titular"], info["validade"]
    db.commit()
    return {"titular": info["titular"], "validade": info["validade"].isoformat()}


# ---------------------------------------------------------------- XML

def _envelope(corpo: str) -> str:
    return ('<?xml version="1.0" encoding="utf-8"?>'
            '<soap12:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            'xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">'
            f"<soap12:Body>{corpo}</soap12:Body></soap12:Envelope>")


def _tag_doc(doc: str) -> str:
    return f"<CNPJ>{doc}</CNPJ>" if len(doc) == 14 else f"<CPF>{doc}</CPF>"


def xml_dist_nsu(c: FinContribuinte, ult_nsu: str) -> str:
    dist = (f'<distDFeInt xmlns="{NS_NFE}" versao="1.01"><tpAmb>{c.ambiente}</tpAmb>'
            f"<cUFAutor>{CODIGOS_UF.get(c.uf, '41')}</cUFAutor>{_tag_doc(c.documento)}"
            f"<distNSU><ultNSU>{str(ult_nsu).zfill(15)}</ultNSU></distNSU></distDFeInt>")
    return _envelope('<nfeDistDFeInteresse xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe">'
                     f"<nfeDadosMsg>{dist}</nfeDadosMsg></nfeDistDFeInteresse>")


def xml_cons_chave(c: FinContribuinte, chave: str) -> str:
    dist = (f'<distDFeInt xmlns="{NS_NFE}" versao="1.01"><tpAmb>{c.ambiente}</tpAmb>'
            f"<cUFAutor>{CODIGOS_UF.get(c.uf, '41')}</cUFAutor>{_tag_doc(c.documento)}"
            f"<consChNFe><chNFe>{chave}</chNFe></consChNFe></distDFeInt>")
    return _envelope('<nfeDistDFeInteresse xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe">'
                     f"<nfeDadosMsg>{dist}</nfeDadosMsg></nfeDistDFeInteresse>")


def assinar_evento(xml_evento: str, chave_privada, certificado) -> str:
    """Assinatura XMLDSig (RSA-SHA1, C14N) do infEvento — padrão exigido pela NF-e."""
    from lxml import etree

    raiz = etree.fromstring(xml_evento.encode("utf-8"))
    for evento in raiz.iter(f"{{{NS_NFE}}}evento"):
        inf = evento.find(f"{{{NS_NFE}}}infEvento")
        digest = base64.b64encode(sha1(etree.tostring(inf, method="c14n")).digest()).decode()
        ds = f"{{{NS_DS}}}"
        sig = etree.SubElement(evento, ds + "Signature", nsmap={None: NS_DS})
        si = etree.SubElement(sig, ds + "SignedInfo")
        etree.SubElement(si, ds + "CanonicalizationMethod",
                         Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315")
        etree.SubElement(si, ds + "SignatureMethod", Algorithm="http://www.w3.org/2000/09/xmldsig#rsa-sha1")
        ref = etree.SubElement(si, ds + "Reference", URI="#" + inf.get("Id"))
        trs = etree.SubElement(ref, ds + "Transforms")
        etree.SubElement(trs, ds + "Transform", Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature")
        etree.SubElement(trs, ds + "Transform", Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315")
        etree.SubElement(ref, ds + "DigestMethod", Algorithm="http://www.w3.org/2000/09/xmldsig#sha1")
        etree.SubElement(ref, ds + "DigestValue").text = digest
        valor = chave_privada.sign(etree.tostring(si, method="c14n"), padding.PKCS1v15(), hashes.SHA1())
        etree.SubElement(sig, ds + "SignatureValue").text = base64.b64encode(valor).decode()
        x509 = etree.SubElement(etree.SubElement(sig, ds + "KeyInfo"), ds + "X509Data")
        der = certificado.public_bytes(serialization.Encoding.DER)
        etree.SubElement(x509, ds + "X509Certificate").text = base64.b64encode(der).decode()
    return etree.tostring(raiz, encoding="unicode")


def xml_ciencia(c: FinContribuinte, chaves: list[str], agora: datetime | None = None) -> str:
    agora = agora or datetime.now(timezone(timedelta(hours=-3)))
    dh = agora.strftime("%Y-%m-%dT%H:%M:%S") + "-03:00"
    eventos = "".join(
        f'<evento versao="1.00"><infEvento Id="ID210210{ch}01"><cOrgao>91</cOrgao>'
        f"<tpAmb>{c.ambiente}</tpAmb>{_tag_doc(c.documento)}<chNFe>{ch}</chNFe><dhEvento>{dh}</dhEvento>"
        "<tpEvento>210210</tpEvento><nSeqEvento>1</nSeqEvento><verEvento>1.00</verEvento>"
        '<detEvento versao="1.00"><descEvento>Ciencia da Operacao</descEvento></detEvento></infEvento></evento>'
        for ch in chaves)
    lote = agora.strftime("%y%m%d%H%M%S%f")[:15]
    return f'<envEvento xmlns="{NS_NFE}" versao="1.00"><idLote>{lote}</idLote>{eventos}</envEvento>'


def _resposta(texto: str, tag: str) -> ET.Element:
    try:
        raiz = ET.fromstring(texto.encode("utf-8"))
    except ET.ParseError:
        raise ErroSefaz("Resposta da SEFAZ ilegível. Tente mais tarde.")
    el = raiz.find(f".//{{{NS_NFE}}}{tag}")
    if el is None:
        falha = raiz.find(".//{http://www.w3.org/2003/05/soap-envelope}Text")
        raise ErroSefaz("A SEFAZ recusou a consulta" + (f": {falha.text}" if falha is not None else ""))
    return el


def _txt(el, tag):
    x = el.find(f"{{{NS_NFE}}}{tag}")
    return x.text if x is not None else None


def ler_dist(texto: str) -> dict:
    ret = _resposta(texto, "retDistDFeInt")
    docs = []
    for dz in ret.iter(f"{{{NS_NFE}}}docZip"):
        try:
            xml = gzip.decompress(base64.b64decode(dz.text or "")).decode("utf-8")
        except (OSError, ValueError):
            continue
        docs.append({"nsu": dz.get("NSU"), "schema": dz.get("schema") or "", "xml": xml})
    return {"cStat": _txt(ret, "cStat"), "xMotivo": _txt(ret, "xMotivo"), "ultNSU": _txt(ret, "ultNSU"),
            "maxNSU": _txt(ret, "maxNSU"), "docs": docs}


# ---------------------------------------------------------------- sincronizar

def pode_consultar(c: FinContribuinte, agora: datetime | None = None) -> bool:
    agora = agora or agora_utc()
    return c.pode_consultar_apos is None or agora >= c.pode_consultar_apos


def _pendentes_xml(db: Session, c: FinContribuinte) -> int:
    return len(db.scalars(select(FinNota.id).where(FinNota.contribuinte_id == c.id,
                                                   FinNota.xml.is_(None))).all())


def sincronizar(db: Session, c: FinContribuinte, forcar_espera: bool = True) -> dict:
    """Uma rodada completa: baixa documentos novos, dá ciência e busca os XML completos.
    Durante a espera de 1 h da SEFAZ, pula só a busca de novos e completa as pendentes."""
    agora = agora_utc()
    chave_priv, cert, pem_cert, pem_chave = _credenciais(c)
    if forcar_espera and not pode_consultar(c, agora):
        falta = int((c.pode_consultar_apos - agora).total_seconds() // 60) + 1
        aviso = f"Notas novas: a SEFAZ só deixa buscar de novo daqui a {falta} min"
        ultimo = _ultimo_completar.get(c.id)
        if not _pendentes_xml(db, c) or (ultimo and agora - ultimo < INTERVALO_COMPLETAR):
            return {"ok": False, "mensagem": aviso, "novas": 0}
        _ultimo_completar[c.id] = agora
        extra = _completar(db, c, chave_priv, cert, pem_cert, pem_chave)
        return {"ok": True, "novas": 0, **extra, "mensagem": f"{aviso}. {extra['resumo']}"}
    url = URLS[c.ambiente]
    novas = 0
    ult = c.ult_nsu or "0"
    retorno = {}
    for _ in range(MAX_LOTES_POR_CONSULTA):
        retorno = ler_dist(transporte(url["dist"], xml_dist_nsu(c, ult), ACAO_DIST, pem_cert, pem_chave))
        if retorno["cStat"] not in ("137", "138"):
            break
        for d in retorno["docs"]:
            if d["schema"].startswith(("resNFe", "procNFe")):
                antes = db.scalar(select(FinNota.id).where(FinNota.chave == _chave_do_doc(d["xml"])))
                fin_notas.guardar_nota(db, d["xml"], origem="sefaz", contribuinte_id=c.id, nsu=d["nsu"])
                novas += antes is None
        ult = retorno["ultNSU"] or ult
        c.max_nsu = retorno["maxNSU"]
        if retorno["cStat"] == "137" or int(ult) >= int(retorno["maxNSU"] or 0):
            break
    c.ult_nsu, c.ultima_consulta = ult, agora
    cstat = retorno.get("cStat")
    c.ultimo_retorno = f"{cstat} - {retorno.get('xMotivo')}"[:300]
    if cstat in ("137", "656") or (cstat == "138" and int(ult) >= int(c.max_nsu or 0)):
        c.pode_consultar_apos = agora + ESPERA
    db.commit()
    if cstat not in ("137", "138"):
        raise ErroSefaz(f"SEFAZ: {c.ultimo_retorno}")

    extra = _completar(db, c, chave_priv, cert, pem_cert, pem_chave)
    return {"ok": True, "novas": novas, **extra, "mensagem": f"{c.ultimo_retorno}. {extra['resumo']}"}


def _completar(db: Session, c: FinContribuinte, chave_priv, cert, pem_cert, pem_chave) -> dict:
    """Ciência + XML completo das notas que só têm o resumo. Erro aqui não perde o que já
    foi baixado: vira aviso na tela (e fica gravado em "último retorno")."""
    avisos = []
    ciencias = completas = 0
    try:
        ciencias, aviso = _dar_ciencia(db, c, chave_priv, cert, pem_cert, pem_chave)
        if aviso:
            avisos.append(aviso)
        db.commit()
        completas, aviso = _buscar_completas(db, c, pem_cert, pem_chave)
        if aviso:
            avisos.append(aviso)
    except ErroSefaz as e:
        avisos.append(str(e))
    faltam = _pendentes_xml(db, c)
    resumo = f"{completas} nota(s) baixada(s) completas"
    if faltam:
        resumo += f"; {faltam} ainda só com o resumo"
    if avisos:
        resumo += " — " + " | ".join(avisos)
    c.ultimo_retorno = f"{(c.ultimo_retorno or '').split(' || ')[0]} || {resumo}"[:300]
    db.commit()
    return {"ciencias": ciencias, "completas": completas, "faltam": faltam, "resumo": resumo}


def _chave_do_doc(xml: str) -> str | None:
    try:
        raiz = ET.fromstring(xml.encode("utf-8"))
    except ET.ParseError:
        return None
    ch = raiz.find(f".//{{{NS_NFE}}}chNFe")
    if ch is not None:
        return ch.text
    inf = raiz.find(f".//{{{NS_NFE}}}infNFe")
    return (inf.get("Id") or "").replace("NFe", "") if inf is not None else None


def _dar_ciencia(db: Session, c: FinContribuinte, chave_priv, cert, pem_cert, pem_chave) -> tuple[int, str | None]:
    """Manda a Ciência da Operação (até 20 notas por lote, várias rodadas). Devolve quantas
    a SEFAZ registrou e, se recusou alguma, o motivo (cStat - xMotivo) pra mostrar na tela."""
    ok = 0
    recusas: dict[str, int] = {}
    tentadas: set[str] = set()  # recusadas nesta rodada: não reenviar
    for _ in range(5):
        pendentes = db.scalars(select(FinNota).where(FinNota.contribuinte_id == c.id, FinNota.xml.is_(None),
                                                     FinNota.ciencia_em.is_(None))
                               .where(FinNota.chave.not_in(list(tentadas) or [""]))
                               .limit(20)).all()
        if not pendentes:
            break
        assinado = assinar_evento(xml_ciencia(c, [n.chave for n in pendentes]), chave_priv, cert)
        corpo = f'<nfeDadosMsg xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeRecepcaoEvento4">{assinado}</nfeDadosMsg>'
        texto = transporte(URLS[c.ambiente]["evento"], _envelope(corpo), ACAO_EVENTO, pem_cert, pem_chave)
        ret = _resposta(texto, "retEnvEvento")
        lote = _txt(ret, "cStat")
        if lote and lote not in ("128",):  # 128 = lote processado; outro = recusou o lote inteiro
            return ok, f"Ciência recusada pela SEFAZ: {lote} - {_txt(ret, 'xMotivo')}"
        por_chave = {n.chave: n for n in pendentes}
        recusadas_agora = set(por_chave)
        for r in ret.iter(f"{{{NS_NFE}}}infEvento"):
            cst, ch = _txt(r, "cStat"), _txt(r, "chNFe")
            # 135/136 = registrado; 573 = já tinha ciência (duplicidade)
            if cst in ("135", "136", "573") and ch in por_chave:
                por_chave[ch].ciencia_em = agora_utc()
                recusadas_agora.discard(ch)
                ok += 1
            elif cst:
                motivo = f"{cst} - {_txt(r, 'xMotivo')}"
                recusas[motivo] = recusas.get(motivo, 0) + 1
        tentadas.update(recusadas_agora)
        db.flush()
    aviso = None
    if recusas:
        aviso = "Ciência recusada: " + "; ".join(f"{m} ({n})" for m, n in recusas.items())
    return ok, aviso


def _buscar_completas(db: Session, c: FinContribuinte, pem_cert, pem_chave) -> tuple[int, str | None]:
    """Pede pela chave o XML das notas que já têm ciência mas ainda não chegaram completas."""
    pendentes = db.scalars(select(FinNota).where(FinNota.contribuinte_id == c.id, FinNota.xml.is_(None),
                                                 FinNota.ciencia_em.is_not(None)).limit(20)).all()
    ok = 0
    aviso = None
    for n in pendentes:
        try:
            ret = ler_dist(transporte(URLS[c.ambiente]["dist"], xml_cons_chave(c, n.chave), ACAO_DIST,
                                      pem_cert, pem_chave))
        except ErroSefaz as e:
            aviso = str(e)
            break
        for d in ret["docs"]:
            if d["schema"].startswith("procNFe"):
                fin_notas.guardar_nota(db, d["xml"], origem="sefaz", contribuinte_id=c.id)
                ok += 1
        if ret["cStat"] == "656":
            c.pode_consultar_apos = agora_utc() + ESPERA
            aviso = "SEFAZ pediu pra esperar 1 h (consumo indevido) antes de baixar mais XML"
            break
        if ret["cStat"] not in ("138",) and not aviso:
            # ex.: 632 = XML ainda não disponível logo após a ciência — tenta na próxima busca
            aviso = f"XML completo ainda não liberado: {ret['cStat']} - {ret['xMotivo']}"
    return ok, aviso


def sincronizar_todos(db: Session) -> list[dict]:
    """Chamado ao abrir a caixa de notas: consulta quem já pode (respeitando 1 h)."""
    saida = []
    for c in db.scalars(select(FinContribuinte).where(FinContribuinte.ativo.is_(True),
                                                      FinContribuinte.cert_pfx.is_not(None))):
        # Na espera de 1 h, só segue se houver nota pendente de XML (sincronizar completa ela).
        if not pode_consultar(c) and not _pendentes_xml(db, c):
            continue
        try:
            saida.append({"documento": c.documento, **sincronizar(db, c)})
        except (ErroSefaz, fin_cripto.CertificadoInvalido) as e:
            db.rollback()
            saida.append({"documento": c.documento, "ok": False, "mensagem": str(e)})
    return saida
