"""Leitura de arquivos de áreas (KML, KMZ, GeoJSON) e cálculo de hectares.

Tudo em Python puro (sem biblioteca de GIS): os arquivos de fazenda são pequenos e
só precisamos dos polígonos, do nome e da pasta de cada um.
"""
from __future__ import annotations

import io
import json
import math
import unicodedata
import zipfile
import xml.etree.ElementTree as ET

RAIO_TERRA_M = 6378137.0  # raio equatorial WGS84 (mesmo usado pelo Google/turf)


class ArquivoInvalido(ValueError):
    """Arquivo que não deu pra ler — a mensagem vai direto pro usuário."""


# ---------------------------------------------------------------- Área (hectares)

def _area_anel_m2(anel: list[list[float]]) -> float:
    """Área de um anel (lista de [lon, lat]) sobre a esfera, em m² (sempre positiva).

    Fórmula do excesso esférico (Chamberlain & Duquette), a mesma do turf.js —
    erro desprezível pra áreas de fazenda.
    """
    n = len(anel)
    if n < 3:
        return 0.0
    total = 0.0
    for i in range(n):
        lon1, lat1 = anel[i][0], anel[i][1]
        lon2, lat2 = anel[(i + 1) % n][0], anel[(i + 1) % n][1]
        total += math.radians(lon2 - lon1) * (
            2 + math.sin(math.radians(lat1)) + math.sin(math.radians(lat2))
        )
    return abs(total * RAIO_TERRA_M * RAIO_TERRA_M / 2.0)


def hectares(geometria: dict) -> float:
    """Hectares de um Polygon/MultiPolygon GeoJSON (furos são descontados)."""
    tipo = geometria.get("type")
    if tipo == "Polygon":
        poligonos = [geometria["coordinates"]]
    elif tipo == "MultiPolygon":
        poligonos = geometria["coordinates"]
    else:
        return 0.0
    m2 = 0.0
    for aneis in poligonos:
        if not aneis:
            continue
        m2 += _area_anel_m2(aneis[0])
        for furo in aneis[1:]:
            m2 -= _area_anel_m2(furo)
    return round(max(m2, 0.0) / 10000.0, 2)


def validar_geometria(geometria: dict) -> dict:
    """Confere se é um polígono utilizável; devolve a geometria normalizada."""
    if not isinstance(geometria, dict) or geometria.get("type") not in ("Polygon", "MultiPolygon"):
        raise ArquivoInvalido("O desenho precisa ser uma área fechada (polígono).")
    if hectares(geometria) <= 0:
        raise ArquivoInvalido("A área desenhada ficou com tamanho zero — marque pelo menos 3 pontos.")
    return geometria


# ---------------------------------------------------------------- Atributos (nome / área)

# Campos que costumam trazer o nome da área nos arquivos de agrimensura, CAR e GPS.
CAMPOS_NOME = ("nome", "name", "talhao", "talhoes", "piquete", "pasto", "gleba", "descricao", "id")


def _chave(texto: str) -> str:
    """Normaliza o nome do campo: minúsculas, sem acento e sem espaço/pontuação."""
    t = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().lower()
    return "".join(c for c in t if c.isalnum())


def numero_br(valor) -> float | None:
    if valor is None:
        return None
    t = str(valor).strip()
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        n = float(t)
    except ValueError:
        return None
    return n if n > 0 else None


def _nome_dos_atributos(attrs: dict) -> str | None:
    por_chave = {_chave(k): v for k, v in attrs.items() if v not in (None, "")}
    for campo in CAMPOS_NOME:
        if por_chave.get(campo):
            return str(por_chave[campo]).strip()
    return None


def _hectares_dos_atributos(attrs: dict) -> float | None:
    """Área informada no próprio arquivo (ex.: campo 'AREA (HA)'), quando existir."""
    for k, v in attrs.items():
        c = _chave(k)
        if c in ("areaha", "hectares", "ha", "areahectares", "areaemha") or (c.startswith("area") and c.endswith("ha")):
            n = numero_br(v)
            if n:
                return round(n, 2)
    return None


# ---------------------------------------------------------------- KML / KMZ

def _local(tag: str) -> str:
    """Nome da tag sem o namespace ({http://www.opengis.net/kml/2.2}Placemark → Placemark)."""
    return tag.rsplit("}", 1)[-1]


def _filho(el, nome: str):
    for f in el:
        if _local(f.tag) == nome:
            return f
    return None


def _texto_filho(el, nome: str) -> str | None:
    f = _filho(el, nome)
    return f.text.strip() if f is not None and f.text and f.text.strip() else None


def _coordenadas(texto: str | None) -> list[list[float]]:
    """'lon,lat[,alt] lon,lat ...' → [[lon, lat], ...] (anel fechado)."""
    pontos = []
    for trecho in (texto or "").split():
        partes = trecho.split(",")
        if len(partes) < 2:
            continue
        try:
            pontos.append([float(partes[0]), float(partes[1])])
        except ValueError:
            continue
    if len(pontos) >= 3 and pontos[0] != pontos[-1]:
        pontos.append(pontos[0])
    return pontos


def _aneis_poligono(poligono) -> list[list[list[float]]]:
    aneis = []
    for f in poligono.iter():
        nome = _local(f.tag)
        if nome in ("outerBoundaryIs", "innerBoundaryIs"):
            for c in f.iter():
                if _local(c.tag) == "coordinates":
                    anel = _coordenadas(c.text)
                    if len(anel) >= 4:
                        # O contorno externo vai sempre na frente.
                        if nome == "outerBoundaryIs":
                            aneis.insert(0, anel)
                        else:
                            aneis.append(anel)
    return aneis


def _geometria_placemark(placemark) -> dict | None:
    """Junta os polígonos do Placemark num Polygon ou MultiPolygon.

    Linha fechada (alguns GPS exportam o contorno assim) também vira polígono.
    """
    poligonos = []
    for el in placemark.iter():
        nome = _local(el.tag)
        if nome == "Polygon":
            aneis = _aneis_poligono(el)
            if aneis:
                poligonos.append(aneis)
        elif nome in ("LineString", "LinearRing") and not poligonos:
            c = _filho(el, "coordinates")
            anel = _coordenadas(c.text if c is not None else None)
            if len(anel) >= 4:
                poligonos.append([anel])
    if not poligonos:
        return None
    if len(poligonos) == 1:
        return {"type": "Polygon", "coordinates": poligonos[0]}
    return {"type": "MultiPolygon", "coordinates": poligonos}


def _atributos_kml(placemark) -> dict:
    """Dados extras do Placemark: <SimpleData name=...> e <Data name=...><value>."""
    attrs = {}
    for el in placemark.iter():
        nome = _local(el.tag)
        if nome == "SimpleData" and el.get("name"):
            attrs[el.get("name")] = (el.text or "").strip()
        elif nome == "Data" and el.get("name"):
            attrs[el.get("name")] = (_texto_filho(el, "value") or "").strip()
    return attrs


def _ler_kml(conteudo: bytes) -> list[dict]:
    try:
        raiz = ET.fromstring(conteudo)
    except ET.ParseError:
        raise ArquivoInvalido("O arquivo não é um KML/XML válido.")

    achados: list[dict] = []

    def percorrer(el, pasta: str | None):
        for filho in el:
            nome = _local(filho.tag)
            if nome == "Folder":
                percorrer(filho, _texto_filho(filho, "name") or pasta)
            elif nome == "Document":
                percorrer(filho, pasta)
            elif nome == "Placemark":
                geo = _geometria_placemark(filho)
                if geo:
                    attrs = _atributos_kml(filho)
                    achados.append({
                        "nome": _texto_filho(filho, "name") or _nome_dos_atributos(attrs) or "",
                        "area": pasta,
                        "geometria": geo,
                        "hectares_arquivo": _hectares_dos_atributos(attrs),
                    })

    percorrer(raiz, None)
    return achados


def _ler_kmz(conteudo: bytes) -> list[dict]:
    try:
        with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
            kmls = [n for n in z.namelist() if n.lower().endswith(".kml")]
            if not kmls:
                raise ArquivoInvalido("O KMZ não tem nenhum arquivo .kml dentro.")
            # O principal costuma ser o doc.kml; senão, o primeiro.
            principal = next((n for n in kmls if n.lower().endswith("doc.kml")), kmls[0])
            return _ler_kml(z.read(principal))
    except zipfile.BadZipFile:
        raise ArquivoInvalido("O arquivo KMZ está corrompido.")


# ---------------------------------------------------------------- GeoJSON

def _ler_geojson(conteudo: bytes) -> list[dict]:
    try:
        dado = json.loads(conteudo.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ArquivoInvalido("O arquivo não é um GeoJSON válido.")
    if dado.get("type") == "FeatureCollection":
        features = dado.get("features") or []
    elif dado.get("type") == "Feature":
        features = [dado]
    else:
        features = [{"type": "Feature", "geometry": dado, "properties": {}}]

    achados = []
    for f in features:
        geo = f.get("geometry") or {}
        if geo.get("type") not in ("Polygon", "MultiPolygon"):
            continue
        props = f.get("properties") or {}
        area = next((str(props[k]) for k in ("retiro", "pasta", "grupo") if props.get(k)), None)
        achados.append({
            "nome": _nome_dos_atributos(props) or "",
            "area": area,
            "geometria": geo,
            "hectares_arquivo": _hectares_dos_atributos(props),
        })
    return achados


# ---------------------------------------------------------------- Entrada única

def ler_arquivo_areas(nome_arquivo: str, conteudo: bytes) -> list[dict]:
    """Lê KML, KMZ (ou .xml com conteúdo KML) e GeoJSON.

    Devolve [{nome, area, geometria, hectares}] — os sem nome ganham "Piquete N".
    """
    nome = (nome_arquivo or "").lower()
    if not conteudo:
        raise ArquivoInvalido("O arquivo está vazio.")
    if nome.endswith(".kmz") or conteudo[:2] == b"PK":
        achados = _ler_kmz(conteudo)
    elif nome.endswith((".geojson", ".json")) or conteudo.lstrip()[:1] == b"{":
        achados = _ler_geojson(conteudo)
    else:
        achados = _ler_kml(conteudo)

    if not achados:
        raise ArquivoInvalido(
            "Não achei nenhuma área (polígono) no arquivo. Ele precisa ter os contornos "
            "das áreas — pontos soltos ou linhas abertas não servem."
        )
    for i, a in enumerate(achados, start=1):
        a["nome"] = (a["nome"] or f"Piquete {i}").strip()[:80]
        a["area"] = (a["area"] or "").strip()[:80] or None
        a["hectares_calculado"] = hectares(a["geometria"])
        # O arquivo de agrimensura/CAR traz a área medida em projeção UTM, que é a
        # referência do técnico — quando existe, é ela que vale.
        a["hectares"] = a.get("hectares_arquivo") or a["hectares_calculado"]
    return achados
