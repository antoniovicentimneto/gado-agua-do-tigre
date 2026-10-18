"""Peso estimado entre uma pesagem e outra.

O gado continua ganhando peso depois da última balança. Pra lotação (UA/ha) e densidade
não ficarem subestimadas, o peso de cada animal é projetado até a data pedida:

    peso estimado = último peso + GMD × dias desde a pesagem

- GMD = média do ganho do último período (entre as duas últimas pesagens) dos animais do
  LOTE — mais estável que o do animal sozinho, que oscila com uma pesagem ruim.
- Sem GMD (lote recém-comprado, uma pesagem só): GMD de referência da época do ano,
  configurado pelo dono (ex.: águas 0,5 / seca 0,2).
- Projeção limitada a 120 dias; passou disso, a estimativa é marcada como "velha".

A estimativa nunca é gravada como pesagem — é sempre calculada na hora.
"""
from __future__ import annotations

import json
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Animal, Pesagem, StatusAnimal
from ..models_campo import ConfigValor

LIMITE_DIAS = 120  # projeta no máximo isso; além, a estimativa fica "velha"
CHAVE_REFERENCIA = "gmd_referencia_epocas"

# Épocas padrão (meses inclusive; atravessa a virada do ano quando início > fim).
REFERENCIA_PADRAO = [
    {"nome": "Águas", "inicio": 10, "fim": 3, "gmd": 0.5},
    {"nome": "Seca", "inicio": 4, "fim": 9, "gmd": 0.2},
]


# ---------------------------------------------------------------- Referência por época

def carregar_referencia(db: Session) -> list[dict]:
    linha = db.get(ConfigValor, CHAVE_REFERENCIA)
    if linha is None:
        return [dict(e) for e in REFERENCIA_PADRAO]
    try:
        return json.loads(linha.valor)
    except ValueError:
        return [dict(e) for e in REFERENCIA_PADRAO]


def salvar_referencia(db: Session, epocas: list[dict]) -> list[dict]:
    """Valida e grava as épocas. Todo mês precisa cair em exatamente uma época."""
    limpas = []
    meses_usados: dict[int, str] = {}
    for e in epocas:
        nome = str(e.get("nome") or "").strip()[:30]
        try:
            ini, fim = int(e["inicio"]), int(e["fim"])
            gmd = float(str(e["gmd"]).replace(",", "."))
        except (KeyError, TypeError, ValueError):
            raise ValueError("Cada época precisa de mês de início, mês de fim e GMD.")
        if not nome:
            raise ValueError("Dê um nome para cada época.")
        if not (1 <= ini <= 12 and 1 <= fim <= 12):
            raise ValueError("Mês deve ser de 1 a 12.")
        if not -1 <= gmd <= 3:
            raise ValueError(f"GMD de {nome} fora do razoável (entre -1 e 3 kg/dia).")
        for m in _meses(ini, fim):
            if m in meses_usados:
                raise ValueError(f"O mês {m} está em duas épocas ({meses_usados[m]} e {nome}).")
            meses_usados[m] = nome
        limpas.append({"nome": nome, "inicio": ini, "fim": fim, "gmd": round(gmd, 3)})
    faltando = [m for m in range(1, 13) if m not in meses_usados]
    if faltando:
        raise ValueError("Faltam meses sem época: " + ", ".join(map(str, faltando)) + ".")
    linha = db.get(ConfigValor, CHAVE_REFERENCIA) or ConfigValor(chave=CHAVE_REFERENCIA)
    linha.valor = json.dumps(limpas)
    db.add(linha)
    db.commit()
    return limpas


def _meses(ini: int, fim: int) -> list[int]:
    if ini <= fim:
        return list(range(ini, fim + 1))
    return list(range(ini, 13)) + list(range(1, fim + 1))


def gmd_referencia(referencia: list[dict], quando: date) -> tuple[float | None, str | None]:
    for e in referencia:
        if quando.month in _meses(e["inicio"], e["fim"]):
            return e["gmd"], e["nome"]
    return None, None


# ---------------------------------------------------------------- Pesagens e projeção

def pesagens_por_animal(db: Session, animal_ids: list[int] | None = None) -> dict[int, dict]:
    """{animal: {data: peso}} numa consulta só (só animais ativos, ou os ids pedidos).
    Duas pesagens no mesmo dia: fica a maior."""
    q = select(Pesagem.animal_id, Pesagem.data, Pesagem.peso)
    if animal_ids is None:
        q = q.join(Animal, Animal.id == Pesagem.animal_id).where(Animal.status == StatusAnimal.ATIVO)
    elif not animal_ids:
        return {}
    else:
        q = q.where(Pesagem.animal_id.in_(animal_ids))
    por_animal: dict[int, dict] = {}
    for animal_id, data_p, peso in db.execute(q):
        dias = por_animal.setdefault(animal_id, {})
        dias[data_p] = max(peso, dias.get(data_p, 0))
    return por_animal


def gmd_ultimo_periodo(pesos: dict, quando: date) -> float | None:
    """Ganho entre as duas últimas pesagens até a data (regra do uGMD do app)."""
    datas = sorted(d for d in pesos if d <= quando)
    if len(datas) < 2:
        return None
    d1, d2 = datas[-2], datas[-1]
    return (pesos[d2] - pesos[d1]) / (d2 - d1).days


def resumo_grupo(animal_ids: list[int], pesos: dict[int, dict], quando: date,
                 referencia: list[dict]) -> dict:
    """Peso real e estimado de um grupo de animais (um lote) numa data."""
    ugmds = [g for g in (gmd_ultimo_periodo(pesos.get(a, {}), quando) for a in animal_ids)
             if g is not None]
    gmd_lote = sum(ugmds) / len(ugmds) if ugmds else None
    if gmd_lote is not None:
        gmd_usado, fonte = gmd_lote, "lote"
    else:
        gmd_usado, nome_epoca = gmd_referencia(referencia, quando)
        fonte = f"referência ({nome_epoca})" if gmd_usado is not None else None

    r = {"cabecas": len(animal_ids), "com_peso": 0, "peso_real": 0.0, "peso": 0.0,
         "n_estimados": 0, "dias_max": 0, "velha": False,
         "gmd_lote": round(gmd_lote, 3) if gmd_lote is not None else None,
         "gmd_usado": round(gmd_usado, 3) if gmd_usado is not None else None, "fonte": fonte}
    for a in animal_ids:
        datas = sorted(d for d in pesos.get(a, {}) if d <= quando)
        if not datas:
            continue
        ultimo = pesos[a][datas[-1]]
        dias = (quando - datas[-1]).days
        r["com_peso"] += 1
        r["peso_real"] += ultimo
        if dias > 0 and gmd_usado is not None:
            r["peso"] += ultimo + gmd_usado * min(dias, LIMITE_DIAS)
            r["n_estimados"] += 1
            r["dias_max"] = max(r["dias_max"], dias)
            r["velha"] = r["velha"] or dias > LIMITE_DIAS
        else:
            r["peso"] += ultimo
    return r
