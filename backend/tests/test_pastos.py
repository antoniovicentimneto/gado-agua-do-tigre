"""Testes do módulo de pastos: leitura de arquivos de áreas, mudança de piquete e desfazer."""
import io
import json
import zipfile
from datetime import date, timedelta

import pytest

from app.models import Animal, Lote, LotePiquete, Piquete, StatusAnimal
from app.services import geo
from app.services import pastos as svc
from app.services.consultas import lote_atual

# Quadrado de ~100 m x 100 m perto da linha do equador (≈ 1 ha).
QUADRADO = {
    "type": "Polygon",
    "coordinates": [[[0, 0], [0.000898315, 0], [0.000898315, 0.000898315],
                     [0, 0.000898315], [0, 0]]],
}

KML = b"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>Fazenda</name>
  <Folder><name>Sede</name>
    <Placemark><name>Piquete 1</name><Polygon><outerBoundaryIs><LinearRing>
      <coordinates>0,0,0 0.000898315,0,0 0.000898315,0.000898315,0 0,0.000898315,0 0,0,0</coordinates>
    </LinearRing></outerBoundaryIs></Polygon></Placemark>
    <Placemark><name>Porteira</name><Point><coordinates>0,0,0</coordinates></Point></Placemark>
  </Folder>
  <Placemark><name>Castro</name><MultiGeometry>
    <Polygon><outerBoundaryIs><LinearRing><coordinates>0,0 0.001,0 0.001,0.001 0,0.001</coordinates></LinearRing></outerBoundaryIs></Polygon>
    <Polygon><outerBoundaryIs><LinearRing><coordinates>1,1 1.001,1 1.001,1.001 1,1.001</coordinates></LinearRing></outerBoundaryIs></Polygon>
  </MultiGeometry></Placemark>
</Document></kml>"""


def _lote(db, nome):
    return db.query(Lote).filter(Lote.nome == nome).first()


def _animal(db, brinco):
    return db.query(Animal).filter(Animal.brinco == brinco).first()


def _piquetes(db, *nomes):
    ps = [Piquete(nome=n, hectares=10, ativo=True, descanso_meta_dias=30) for n in nomes]
    db.add_all(ps)
    db.commit()
    return ps


def _no_painel(db, piquete_id):
    return next(p for p in svc.painel(db)["piquetes"] if p["id"] == piquete_id)


ONTEM = date.today() - timedelta(days=1)


# ---------------------------------------------------------------- Arquivos de áreas

def test_hectares_do_quadrado_de_100m():
    assert geo.hectares(QUADRADO) == pytest.approx(1.0, abs=0.02)


def test_furo_desconta_area():
    com_furo = {"type": "Polygon", "coordinates": [
        QUADRADO["coordinates"][0],
        [[0.0002, 0.0002], [0.0004, 0.0002], [0.0004, 0.0004], [0.0002, 0.0004], [0.0002, 0.0002]],
    ]}
    assert geo.hectares(com_furo) < geo.hectares(QUADRADO)


def test_le_kml_com_pastas_e_multipoligono():
    achados = geo.ler_arquivo_areas("fazenda.kml", KML)
    # O ponto (porteira) é ignorado; o MultiGeometry vira um piquete só.
    assert [a["nome"] for a in achados] == ["Piquete 1", "Castro"]
    assert achados[0]["area"] == "Sede"
    assert achados[0]["hectares"] == pytest.approx(1.0, abs=0.02)
    assert achados[1]["geometria"]["type"] == "MultiPolygon"


def test_le_kml_com_extensao_xml():
    assert len(geo.ler_arquivo_areas("areas.xml", KML)) == 2


def test_le_kmz():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("doc.kml", KML)
    assert len(geo.ler_arquivo_areas("fazenda.kmz", buf.getvalue())) == 2


def test_le_geojson():
    dado = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"nome": "P7"}, "geometry": QUADRADO}]}
    achados = geo.ler_arquivo_areas("a.geojson", json.dumps(dado).encode())
    assert achados[0]["nome"] == "P7"


def test_arquivo_sem_poligono_da_erro_amigavel():
    sem = b'<kml xmlns="http://www.opengis.net/kml/2.2"><Placemark><Point><coordinates>0,0</coordinates></Point></Placemark></kml>'
    with pytest.raises(geo.ArquivoInvalido):
        geo.ler_arquivo_areas("x.kml", sem)
    with pytest.raises(geo.ArquivoInvalido):
        geo.ler_arquivo_areas("x.kml", b"isso nao e xml")


def test_importar_cria_e_reimportar_atualiza(db):
    achados = geo.ler_arquivo_areas("fazenda.kml", KML)
    r = svc.importar(db, achados, None, "Geral", svc.TipoArea.PROPRIA)
    assert r == {"ok": True, "criados": 2, "atualizados": 0}
    r = svc.importar(db, achados, [0], "Geral", svc.TipoArea.PROPRIA)
    assert r["atualizados"] == 1 and r["criados"] == 0
    nomes_areas = {p["area"] for p in svc.painel(db)["piquetes"]}
    assert nomes_areas == {"Sede", "Geral"}


# ---------------------------------------------------------------- Painel e mudanças

def test_lotes_comecam_sem_piquete(db):
    _piquetes(db, "P1")
    sem = {l["nome"]: l["cabecas"] for l in svc.painel(db)["sem_piquete"]}
    assert sem == {"LOTEA": 2, "LOTEB": 1}


def test_mover_lote_ocupa_piquete_e_calcula_ua(db):
    p1, = _piquetes(db, "P1")
    svc.mover(db, _lote(db, "LOTEA").id, p1.id, ONTEM)
    item = _no_painel(db, p1.id)
    assert item["status"] == "ocupado"
    assert item["cabecas"] == 2
    assert item["ua"] == pytest.approx((400 + 320) / 450, abs=0.1)
    assert item["dias"] == 1
    assert "LOTEA" not in {l["nome"] for l in svc.painel(db)["sem_piquete"]}


def test_sair_do_piquete_comeca_descanso(db):
    p1, p2 = _piquetes(db, "P1", "P2")
    lote = _lote(db, "LOTEA")
    svc.mover(db, lote.id, p1.id, ONTEM - timedelta(days=5))
    svc.mover(db, lote.id, p2.id, ONTEM)
    item = _no_painel(db, p1.id)
    assert item["status"] == "descansando"
    assert item["dias"] == 1


def test_descanso_cumprido_fica_pronto(db):
    p1, p2 = _piquetes(db, "P1", "P2")
    lote = _lote(db, "LOTEA")
    svc.mover(db, lote.id, p1.id, date.today() - timedelta(days=40))
    svc.mover(db, lote.id, p2.id, date.today() - timedelta(days=31))
    assert _no_painel(db, p1.id)["status"] == "pronto"


def test_mover_para_o_mesmo_piquete_da_erro(db):
    p1, = _piquetes(db, "P1")
    lote = _lote(db, "LOTEA")
    svc.mover(db, lote.id, p1.id)
    with pytest.raises(svc.ErroPasto):
        svc.mover(db, lote.id, p1.id)


def test_data_no_futuro_da_erro(db):
    p1, = _piquetes(db, "P1")
    with pytest.raises(svc.ErroPasto):
        svc.mover(db, _lote(db, "LOTEA").id, p1.id, date.today() + timedelta(days=1))


def test_data_antes_da_entrada_da_erro(db):
    p1, p2 = _piquetes(db, "P1", "P2")
    lote = _lote(db, "LOTEA")
    svc.mover(db, lote.id, p1.id, ONTEM)
    with pytest.raises(svc.ErroPasto):
        svc.mover(db, lote.id, p2.id, ONTEM - timedelta(days=3))


def test_mesma_chave_nao_duplica(db):
    p1, p2 = _piquetes(db, "P1", "P2")
    lote = _lote(db, "LOTEA")
    r1 = svc.mover(db, lote.id, p1.id, chave="abc")
    r2 = svc.mover(db, lote.id, p1.id, chave="abc")  # reenvio da fila offline
    assert r2["repetida"] and r1["movimentacao"]["id"] == r2["movimentacao"]["id"]
    assert db.query(LotePiquete).count() == 1


def test_juntar_lotes(db):
    p1, p2 = _piquetes(db, "P1", "P2")
    a, b = _lote(db, "LOTEA"), _lote(db, "LOTEB")
    svc.mover(db, a.id, p1.id, ONTEM)
    svc.mover(db, b.id, p2.id, ONTEM)
    svc.juntar(db, b.id, a.id)
    assert lote_atual(_animal(db, "201")) == "LOTEA"
    assert _no_painel(db, p1.id)["cabecas"] == 3
    assert _no_painel(db, p2.id)["status"] == "descansando"


def test_separar_para_lote_novo_em_outro_piquete(db):
    p1, p2 = _piquetes(db, "P1", "P2")
    a = _lote(db, "LOTEA")
    svc.mover(db, a.id, p1.id, ONTEM)
    svc.separar(db, a.id, [_animal(db, "101").id], novo_lote="LOTEC", piquete_id=p2.id)
    assert lote_atual(_animal(db, "101")) == "LOTEC"
    assert lote_atual(_animal(db, "102")) == "LOTEA"
    assert _no_painel(db, p1.id)["cabecas"] == 1
    assert _no_painel(db, p2.id)["lotes"][0]["nome"] == "LOTEC"


def test_separar_com_nome_de_lote_existente_da_erro(db):
    a = _lote(db, "LOTEA")
    with pytest.raises(svc.ErroPasto):
        svc.separar(db, a.id, [_animal(db, "101").id], novo_lote="LOTEB")


def test_separar_todos_tira_o_lote_de_origem_do_piquete(db):
    p1, p2 = _piquetes(db, "P1", "P2")
    a = _lote(db, "LOTEA")
    svc.mover(db, a.id, p1.id, ONTEM)
    ids = [_animal(db, "101").id, _animal(db, "102").id]
    svc.separar(db, a.id, ids, novo_lote="LOTEC", piquete_id=p2.id)
    assert _no_painel(db, p1.id)["status"] == "descansando"


def test_separar_para_lote_existente_fica_onde_ele_esta(db):
    p1, p2 = _piquetes(db, "P1", "P2")
    a, b = _lote(db, "LOTEA"), _lote(db, "LOTEB")
    svc.mover(db, a.id, p1.id, ONTEM)
    svc.mover(db, b.id, p2.id, ONTEM)
    svc.separar(db, a.id, [_animal(db, "101").id], lote_destino_id=b.id)
    assert _no_painel(db, p2.id)["cabecas"] == 2


def test_desfazer_mover(db):
    p1, p2 = _piquetes(db, "P1", "P2")
    a = _lote(db, "LOTEA")
    svc.mover(db, a.id, p1.id, ONTEM)
    r = svc.mover(db, a.id, p2.id)
    svc.desfazer(db, r["movimentacao"]["id"])
    assert _no_painel(db, p1.id)["status"] == "ocupado"
    assert _no_painel(db, p2.id)["status"] == "sem_registro"


def test_desfazer_separar_volta_animais_e_apaga_lote_novo(db):
    p1, p2 = _piquetes(db, "P1", "P2")
    a = _lote(db, "LOTEA")
    svc.mover(db, a.id, p1.id, ONTEM)
    r = svc.separar(db, a.id, [_animal(db, "101").id], novo_lote="LOTEC", piquete_id=p2.id)
    svc.desfazer(db, r["movimentacao"]["id"])
    assert lote_atual(_animal(db, "101")) == "LOTEA"
    assert _lote(db, "LOTEC") is None
    assert _no_painel(db, p1.id)["cabecas"] == 2


def test_desfazer_juntar(db):
    a, b = _lote(db, "LOTEA"), _lote(db, "LOTEB")
    r = svc.juntar(db, b.id, a.id)
    svc.desfazer(db, r["movimentacao"]["id"])
    assert lote_atual(_animal(db, "201")) == "LOTEB"


def test_nao_desfaz_mudanca_antiga_com_outra_depois(db):
    p1, p2, p3 = _piquetes(db, "P1", "P2", "P3")
    a = _lote(db, "LOTEA")
    r1 = svc.mover(db, a.id, p1.id, ONTEM)
    svc.mover(db, a.id, p2.id)
    with pytest.raises(svc.ErroPasto):
        svc.desfazer(db, r1["movimentacao"]["id"])


def test_nao_desfaz_duas_vezes(db):
    p1, = _piquetes(db, "P1")
    r = svc.mover(db, _lote(db, "LOTEA").id, p1.id)
    svc.desfazer(db, r["movimentacao"]["id"])
    with pytest.raises(svc.ErroPasto):
        svc.desfazer(db, r["movimentacao"]["id"])


def test_lote_esvaziado_fora_daqui_libera_o_piquete(db):
    p1, = _piquetes(db, "P1")
    b = _lote(db, "LOTEB")
    svc.mover(db, b.id, p1.id, ONTEM)
    # Única vaca do LOTEB foi vendida (fora do módulo de pastos).
    vaca = _animal(db, "201")
    vaca.status = StatusAnimal.VENDIDO
    db.commit()
    item = _no_painel(db, p1.id)
    assert item["status"] != "ocupado" and item["cabecas"] == 0


def test_remover_piquete(db):
    p1, p2 = _piquetes(db, "P1", "P2")
    a = _lote(db, "LOTEA")
    svc.mover(db, a.id, p1.id, ONTEM)
    with pytest.raises(svc.ErroPasto):
        svc.remover_piquete(db, p1.id)  # tem gado agora
    svc.mover(db, a.id, p2.id)
    assert svc.remover_piquete(db, p1.id)["arquivado"] is True  # tem histórico
    p3, = _piquetes(db, "P3")
    assert svc.remover_piquete(db, p3.id)["arquivado"] is False  # nunca usado: apaga


def test_salvar_piquete_desenhado_calcula_hectares(db):
    r = svc.salvar_piquete(db, {"nome": "Desenhado", "area_nome": "Sede", "geometria": QUADRADO})
    assert r["hectares"] == pytest.approx(1.0, abs=0.02)
    with pytest.raises(svc.ErroPasto):
        svc.salvar_piquete(db, {"nome": "Desenhado", "area_nome": "Sede"})
