"""Testes das notas fiscais (XML, sugestão, lançar), da busca na SEFAZ (com a SEFAZ
simulada — nunca acessa a internet) e do extrato OFX."""
import base64
import gzip
from datetime import datetime, timedelta, timezone
from hashlib import sha1

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from lxml import etree
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models_financeiro import FinContribuinte, FinLancamento, FinNota
from app.services import fin_cripto, fin_extrato, fin_lancamentos, fin_nfe_xml, fin_notas, fin_plano, fin_sefaz

CHAVE = "41261012345678000195550010000123451000123456"
EMITENTE = "12345678000195"
CPF = "52998224725"


def nfe_xml(chave=CHAVE, dup=True):
    dups = ("<cobr><dup><nDup>001</nDup><dVenc>2026-11-10</dVenc><vDup>600.00</vDup></dup>"
            "<dup><nDup>002</nDup><dVenc>2026-12-10</dVenc><vDup>400.00</vDup></dup></cobr>") if dup else ""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00"><NFe><infNFe Id="NFe{chave}" versao="4.00">
<ide><mod>55</mod><serie>1</serie><nNF>12345</nNF><dhEmi>2026-10-10T09:30:00-03:00</dhEmi></ide>
<emit><CNPJ>{EMITENTE}</CNPJ><xNome>COOPERATIVA FRISIA LTDA</xNome><xFant>Frísia</xFant></emit>
<dest><CPF>{CPF}</CPF><xNome>PRODUTOR</xNome></dest>
<det nItem="1"><prod><cProd>10</cProd><xProd>SAL MINERAL 30KG</xProd><NCM>23099090</NCM><CFOP>5102</CFOP>
<uCom>SC</uCom><qCom>10.0000</qCom><vUnCom>80.00</vUnCom><vProd>800.00</vProd></prod></det>
<det nItem="2"><prod><cProd>20</cProd><xProd>ARAME FARPADO 500M</xProd><NCM>73130000</NCM><CFOP>5102</CFOP>
<uCom>RL</uCom><qCom>1.0000</qCom><vUnCom>200.00</vUnCom><vProd>200.00</vProd></prod></det>
<total><ICMSTot><vNF>1000.00</vNF></ICMSTot></total>{dups}
<pag><detPag><tPag>15</tPag><vPag>1000.00</vPag></detPag></pag>
</infNFe></NFe><protNFe><infProt><chNFe>{chave}</chNFe></infProt></protNFe></nfeProc>"""


def res_xml(chave=CHAVE):
    return (f'<resNFe xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.01"><chNFe>{chave}</chNFe>'
            f"<CNPJ>{EMITENTE}</CNPJ><xNome>COOPERATIVA FRISIA LTDA</xNome><dhEmi>2026-10-10T09:30:00-03:00</dhEmi>"
            "<vNF>1000.00</vNF><cSitNFe>1</cSitNFe></resNFe>")


@pytest.fixture
def fdb():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    fin_plano.garantir_cadastros(s)
    yield s
    s.close()


# ---------------------------------------------------------------- XML

def test_ler_xml_completo():
    n = fin_nfe_xml.ler(nfe_xml())
    assert n["completa"] and n["chave"] == CHAVE and n["numero"] == "12345"
    assert n["emitente_doc"] == EMITENTE and n["emitente_nome"] == "Frísia" and n["valor"] == 1000
    assert [i["ncm"] for i in n["itens"]] == ["23099090", "73130000"]
    assert [d["valor"] for d in n["duplicatas"]] == [600, 400]
    assert fin_nfe_xml.forma_principal(n) == "Boleto"


def test_ler_resumo_e_xml_invalido():
    r = fin_nfe_xml.ler(res_xml())
    assert not r["completa"] and r["valor"] == 1000 and r["emitente_doc"] == EMITENTE
    with pytest.raises(fin_nfe_xml.XmlInvalido):
        fin_nfe_xml.ler("<html>isso não é nota</html>")


# ---------------------------------------------------------------- caixa de entrada

def test_resumo_depois_completo_atualiza_a_mesma_nota(fdb):
    fin_notas.guardar_nota(fdb, res_xml(), origem="sefaz")
    nota = fin_notas.guardar_nota(fdb, nfe_xml(), origem="sefaz")
    fdb.commit()
    assert fdb.scalar(select(FinNota.id).where(FinNota.chave == CHAVE)) == nota.id
    assert nota.situacao == "completa" and nota.numero == "12345"


def test_receber_zip_com_xml(fdb):
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("a.xml", nfe_xml())
        z.writestr("leia.txt", "nada")
    r = fin_notas.receber_arquivos(fdb, [("notas.zip", buf.getvalue()), ("ruim.xml", b"<x/>")])
    assert r["importadas"] == 1 and len(r["erros"]) == 1


def test_lancar_nota_dividida_e_aprender(fdb):
    nota = fin_notas.guardar_nota(fdb, nfe_xml())
    fdb.commit()
    det = fin_notas.detalhe(fdb, nota.id)
    assert det["sugestao"]["geral"] is None  # primeira vez: não sabe nada ainda
    assert [d["vencimento"] for d in det["duplicatas"]] == ["2026-11-10", "2026-12-10"]
    fin_notas.lancar(fdb, nota.id, {
        "fazenda": "Água do Tigre", "conta": "Sicoob", "forma_pagamento": "Boleto",
        "parcelas": det["duplicatas"],
        "partes": [
            {"itens": [1], "setor": "Pecuária", "grupo": "Alimentos", "categoria": "Minerais"},
            {"itens": [2], "setor": "Pecuária", "grupo": "Materiais de consumo, operação e manutenção",
             "categoria": "Cercas"},
        ]}, "Letícia")
    lancs = fdb.scalars(select(FinLancamento).order_by(FinLancamento.valor_total.desc())).all()
    assert [lc.valor_total for lc in lancs] == [800, 200]
    assert [p.valor for p in lancs[0].parcelas] == [480, 320]  # 60%/40% das duplicatas
    assert lancs[0].nf_chave == CHAVE and lancs[0].fornecedor.documento == EMITENTE
    assert fdb.get(FinNota, nota.id).situacao == "lancada"

    # Próxima nota do mesmo fornecedor: cada produto já vem classificado.
    outra = fin_notas.guardar_nota(fdb, nfe_xml(chave=CHAVE[:-1] + "7"))
    fdb.commit()
    sug = fin_notas.detalhe(fdb, outra.id)["sugestao"]
    assert [s["categoria"] for s in sug["itens"]] == ["Minerais", "Cercas"]


def test_nota_ja_lancada_a_mao_nao_volta_pra_caixa(fdb):
    fin_lancamentos.criar(fdb, {"tipo": "despesa", "data": "2026-10-10", "setor": "Sede", "grupo": "G",
                                "categoria": "C", "valor_total": 1000, "nf_chave": CHAVE}, "Letícia")
    nota = fin_notas.guardar_nota(fdb, nfe_xml())
    assert nota.situacao == "lancada"


# ---------------------------------------------------------------- certificado + SEFAZ simulada

def _pfx(doc=CPF, senha="1234", vencido=False):
    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"PRODUTOR TESTE:{doc}")])
    agora = datetime.now(timezone.utc)
    fim = agora - timedelta(days=1) if vencido else agora + timedelta(days=365)
    cert = (x509.CertificateBuilder().subject_name(nome).issuer_name(nome).public_key(chave.public_key())
            .serial_number(1).not_valid_before(agora - timedelta(days=30)).not_valid_after(fim)
            .sign(chave, hashes.SHA256()))
    return pkcs12.serialize_key_and_certificates(b"t", chave, cert, None,
                                                 serialization.BestAvailableEncryption(senha.encode())), chave, cert


def _contribuinte(fdb):
    c = FinContribuinte(documento=CPF, nome="Produtor", uf="PR")
    fdb.add(c)
    fdb.commit()
    return c


def test_certificado_guardado_criptografado_e_validado(fdb):
    c = _contribuinte(fdb)
    pfx, _, _ = _pfx()
    with pytest.raises(fin_cripto.CertificadoInvalido):
        fin_sefaz.guardar_certificado(fdb, c, pfx, "senha-errada")
    with pytest.raises(fin_cripto.CertificadoInvalido):
        fin_sefaz.guardar_certificado(fdb, c, _pfx(doc="11144477735")[0], "1234")  # de outro CPF
    with pytest.raises(fin_cripto.CertificadoInvalido):
        fin_sefaz.guardar_certificado(fdb, c, _pfx(vencido=True)[0], "1234")
    info = fin_sefaz.guardar_certificado(fdb, c, pfx, "1234")
    assert info["titular"].endswith(CPF)
    assert c.cert_pfx != pfx and b"1234" not in c.cert_senha.encode()  # nada em texto puro
    assert fin_cripto.decifrar(c.cert_pfx) == pfx


def test_evento_ciencia_assinado_confere():
    _, chave, cert = _pfx()
    c = FinContribuinte(documento=CPF, nome="P", uf="PR", ambiente=1)
    assinado = fin_sefaz.assinar_evento(fin_sefaz.xml_ciencia(c, [CHAVE]), chave, cert)
    raiz = etree.fromstring(assinado.encode())
    ns = {"n": fin_sefaz.NS_NFE, "d": fin_sefaz.NS_DS}
    inf = raiz.find(".//n:infEvento", ns)
    assert inf.get("Id") == f"ID210210{CHAVE}01"
    assert raiz.find(".//n:CPF", ns).text == CPF
    digest = raiz.find(".//d:DigestValue", ns).text
    assert digest == base64.b64encode(sha1(etree.tostring(inf, method="c14n")).digest()).decode()
    si = raiz.find(".//d:SignedInfo", ns)
    assinatura = base64.b64decode(raiz.find(".//d:SignatureValue", ns).text)
    cert.public_key().verify(assinatura, etree.tostring(si, method="c14n"), padding.PKCS1v15(), hashes.SHA1())


def _soap(corpo):
    return (f'<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">'
            f"<soap:Body>{corpo}</soap:Body></soap:Envelope>")


def _doczip(nsu, schema, xml):
    b64 = base64.b64encode(gzip.compress(xml.encode())).decode()
    return f'<docZip NSU="{nsu}" schema="{schema}">{b64}</docZip>'


def _ret_dist(cstat, ult, mx, docs=""):
    return _soap(f'<nfeDistDFeInteresseResponse><nfeDistDFeInteresseResult><retDistDFeInt '
                 f'xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.01"><tpAmb>1</tpAmb><cStat>{cstat}</cStat>'
                 f"<xMotivo>ok</xMotivo><ultNSU>{ult}</ultNSU><maxNSU>{mx}</maxNSU>"
                 f"<loteDistDFeInt>{docs}</loteDistDFeInt></retDistDFeInt></nfeDistDFeInteresseResult>"
                 "</nfeDistDFeInteresseResponse>")


def test_sincronizar_com_sefaz_simulada(fdb, monkeypatch):
    c = _contribuinte(fdb)
    pfx, _, _ = _pfx()
    fin_sefaz.guardar_certificado(fdb, c, pfx, "1234")
    chamadas = []

    def falsa(url, envelope, acao, pem_cert, pem_chave):
        chamadas.append((acao.rsplit("/", 1)[1], envelope))
        assert b"PRIVATE KEY" in pem_chave
        if "RecepcaoEvento" in url:
            assert "<Signature" in envelope and "<tpEvento>210210</tpEvento>" in envelope
            return _soap('<retEnvEvento xmlns="http://www.portalfiscal.inf.br/nfe"><cStat>128</cStat>'
                         f"<retEvento><infEvento><cStat>135</cStat><chNFe>{CHAVE}</chNFe></infEvento></retEvento>"
                         "</retEnvEvento>")
        if "<consChNFe>" in envelope:
            return _ret_dist("138", "000000000000002", "000000000000002",
                             _doczip("000000000000002", "procNFe_v4.00.xsd", nfe_xml()))
        assert f"<CPF>{CPF}</CPF>" in envelope and "<cUFAutor>41</cUFAutor>" in envelope
        return _ret_dist("138", "000000000000001", "000000000000001",
                         _doczip("000000000000001", "resNFe_v1.01.xsd", res_xml()))

    monkeypatch.setattr(fin_sefaz, "transporte", falsa)
    r = fin_sefaz.sincronizar(fdb, c)
    assert r["ok"] and r["novas"] == 1 and r["ciencias"] == 1 and r["completas"] == 1
    nota = fdb.scalar(select(FinNota).where(FinNota.chave == CHAVE))
    assert nota.situacao == "completa" and nota.ciencia_em and nota.contribuinte_id == c.id
    assert c.ult_nsu == "000000000000001" and c.pode_consultar_apos > datetime.now()
    # Respeita a espera de 1 h da SEFAZ (não consulta de novo).
    antes = len(chamadas)
    r2 = fin_sefaz.sincronizar(fdb, c)
    assert not r2["ok"] and "min" in r2["mensagem"] and len(chamadas) == antes


def test_sefaz_consumo_indevido_vira_erro_e_espera(fdb, monkeypatch):
    c = _contribuinte(fdb)
    fin_sefaz.guardar_certificado(fdb, c, _pfx()[0], "1234")
    monkeypatch.setattr(fin_sefaz, "transporte", lambda *a: _ret_dist("656", "0", "0"))
    with pytest.raises(fin_sefaz.ErroSefaz):
        fin_sefaz.sincronizar(fdb, c)
    assert c.pode_consultar_apos > datetime.now()


# ---------------------------------------------------------------- extrato OFX

OFX = b"""OFXHEADER:100
DATA:OFXSGML
<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><BANKTRANLIST>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20261012120000[-3:BRT]<TRNAMT>-600.00<FITID>A1<MEMO>BOLETO FRISIA</STMTTRN>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20261013<TRNAMT>-55,90<FITID>A2<MEMO>TARIFA PACOTE</STMTTRN>
<STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20261014<TRNAMT>5000.00<FITID>A3<MEMO>PIX RECEBIDO</STMTTRN>
</BANKTRANLIST></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>"""


def test_ofx_importa_concilia_e_nao_duplica(fdb):
    fin_lancamentos.criar(fdb, {"tipo": "despesa", "data": "2026-10-01", "setor": "Pecuária", "grupo": "Alimentos",
                                "categoria": "Minerais", "valor_total": 1000, "conta": "Sicoob",
                                "parcelas": [{"vencimento": "2026-10-10", "valor": 600},
                                             {"vencimento": "2026-11-10", "valor": 400}]}, "Letícia")
    r = fin_extrato.importar(fdb, "Sicoob", OFX)
    assert r == {"movimentos": 3, "novos": 3, "conciliados_agora": 1}
    lista = fin_extrato.listar(fdb, "Sicoob")["movimentos"]
    soltos = [m for m in lista if not m["parcela_id"]]
    assert {m["valor"] for m in soltos} == {-55.9, 5000.0}
    assert fin_extrato.importar(fdb, "Sicoob", OFX)["novos"] == 0
    tarifa = next(m for m in soltos if m["valor"] == -55.9)
    assert fin_extrato.candidatas(fdb, tarifa["id"]) == []
    fin_extrato.vincular(fdb, tarifa["id"], None, ignorar=True)
    assert next(m for m in fin_extrato.listar(fdb)["movimentos"] if m["id"] == tarifa["id"])["ignorado"]


def test_ofx_invalido(fdb):
    with pytest.raises(fin_plano.ErroFinanceiro):
        fin_extrato.importar(fdb, "Sicoob", b"nada a ver")
