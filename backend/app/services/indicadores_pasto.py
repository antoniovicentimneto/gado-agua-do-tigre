"""Indicadores de rotação de pasto num período (padrão: safra julho–junho).

Contas (a mesma base dos indicadores de consultoria):
- Lotação média (UA/ha) = Σ(UA × dias) ÷ Σ(hectares × dias) das ocupações do período.
  UA da ocupação = média entre a "foto" da entrada e a da saída (peso real ou estimado);
  ocupação ainda aberta usa o peso estimado de hoje como saída.
- Ocupação média = média de dias entre entrada e saída das ocupações que terminaram.
- Descanso médio = média dos intervalos sem gado entre duas ocupações do mesmo piquete.
- Uso da área = Σ(ha × dias com gado) ÷ (ha dos piquetes × dias do período).
Ocupações antigas sem "foto" (antes de existir o registro) ficam fora da lotação e são
contadas à parte, pra ninguém confundir número baixo com pasto vazio.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy.orm import Session, selectinload

from ..models import LotePiquete, Piquete
from ..models_campo import PastoPeriodo
from . import peso_estimado as pe
from .pastos import KG_POR_UA, _hoje, _rebanho_por_lote


def safra_de(d: date) -> tuple[date, date]:
    """Safra pecuária julho a junho que contém a data."""
    ini = date(d.year if d.month >= 7 else d.year - 1, 7, 1)
    return ini, date(ini.year + 1, 6, 30)


def _uniao(intervalos: list[tuple[date, date]]) -> list[tuple[date, date]]:
    """Junta intervalos que se sobrepõem (dois lotes no mesmo piquete ao mesmo tempo)."""
    saida: list[list[date]] = []
    for ini, fim in sorted(intervalos):
        if saida and ini <= saida[-1][1]:
            saida[-1][1] = max(saida[-1][1], fim)
        else:
            saida.append([ini, fim])
    return [(a, b) for a, b in saida]


def indicadores(db: Session, inicio: date | None = None, fim: date | None = None,
                hoje: date | None = None) -> dict:
    hoje = hoje or _hoje()
    if inicio is None or fim is None:
        inicio, fim = safra_de(hoje)
    fim_efetivo = min(fim, hoje)
    if fim_efetivo < inicio:
        return {"inicio": inicio.isoformat(), "fim": fim.isoformat(), "vazio": True}
    dias_periodo = (fim_efetivo - inicio).days + 1
    referencia = pe.carregar_referencia(db)
    reb_hoje = _rebanho_por_lote(db, hoje, referencia)

    piquetes = {p.id: p for p in db.query(Piquete).all()}
    ocupacoes = (
        db.query(LotePiquete)
        .options(selectinload(LotePiquete.lote))
        .filter(LotePiquete.data_entrada <= fim_efetivo)
        .all()
    )
    ocupacoes = [o for o in ocupacoes if (o.data_saida or hoje) >= inicio]
    pastos = defaultdict(list)
    for per in db.query(PastoPeriodo).all():
        pastos[per.piquete_id].append(per)

    def pasto_em(pid: int, d: date) -> str:
        nomes = [x.especie for x in pastos.get(pid, []) if x.inicio <= d and (x.fim is None or x.fim >= d)]
        return " + ".join(sorted(nomes)) or (piquetes[pid].capim if pid in piquetes and piquetes[pid].capim else "Não informado")

    def epoca_de(d: date) -> str:
        return pe.gmd_referencia(referencia, d)[1] or "—"

    tot = {"ua_dias": 0.0, "ha_dias": 0.0}
    por_epoca = defaultdict(lambda: {"ua_dias": 0.0, "ha_dias": 0.0})
    por_piquete = defaultdict(lambda: {"ua_dias": 0.0, "ha_dias": 0.0, "dias": 0, "ocupacoes": 0})
    por_pasto = defaultdict(lambda: {"ua_dias": 0.0, "ha_dias": 0.0, "ganho_cab_dias": 0.0, "cab_dias": 0.0})
    duracoes, sem_foto = [], 0
    intervalos_piquete = defaultdict(list)

    for o in ocupacoes:
        saida_real = o.data_saida
        fim_ocup = saida_real or hoje
        intervalos_piquete[o.piquete_id].append((o.data_entrada, fim_ocup))
        if saida_real and inicio <= saida_real <= fim_efetivo:
            duracoes.append((saida_real - o.data_entrada).days)
        a, b = max(o.data_entrada, inicio), min(fim_ocup, fim_efetivo)
        dias = (b - a).days + (0 if saida_real and b == saida_real else 1)
        if dias <= 0:
            continue
        pq = por_piquete[o.piquete_id]
        pq["dias"] += dias
        pq["ocupacoes"] += 1
        ha = o.hectares or (piquetes[o.piquete_id].hectares if o.piquete_id in piquetes else None)
        # UA média da ocupação (foto da entrada e da saída; aberta = estimativa de hoje)
        peso_ini = o.peso_entrada
        peso_fim = o.peso_saida
        if saida_real is None and o.lote_id in reb_hoje:
            peso_fim = reb_hoje[o.lote_id]["peso"] or None
        if not peso_ini or not ha:
            sem_foto += 1
            continue
        ua = ((peso_ini + (peso_fim or peso_ini)) / 2) / KG_POR_UA
        pasto = pasto_em(o.piquete_id, a)
        # Distribui dia a dia (a época muda no meio da ocupação)
        d = a
        for _ in range(dias):
            ep = epoca_de(d)
            por_epoca[ep]["ua_dias"] += ua
            por_epoca[ep]["ha_dias"] += ha
            d += timedelta(days=1)
        for alvo in (tot, pq, por_pasto[pasto]):
            alvo["ua_dias"] += ua * dias
            alvo["ha_dias"] += ha * dias
        # Ganho do período quando o lote não mudou de tamanho (média por cabeça)
        if saida_real and o.peso_saida and o.cabecas and o.cabecas_saida == o.cabecas:
            dur = (saida_real - o.data_entrada).days
            if dur > 0:
                g = (o.peso_saida - o.peso_entrada) / o.cabecas / dur
                por_pasto[pasto]["ganho_cab_dias"] += g * o.cabecas * dur
                por_pasto[pasto]["cab_dias"] += o.cabecas * dur

    # Descanso: intervalos sem gado entre ocupações do mesmo piquete (dentro do período)
    descansos_por_piquete = defaultdict(list)
    for pid, ints in intervalos_piquete.items():
        unidos = _uniao(ints)
        for (_, fim1), (ini2, _) in zip(unidos, unidos[1:]):
            if inicio <= ini2 <= fim_efetivo and (ini2 - fim1).days > 0:
                descansos_por_piquete[pid].append((ini2 - fim1).days)
    todos_descansos = [x for v in descansos_por_piquete.values() for x in v]

    ativos = [p for p in piquetes.values() if p.ativo and p.hectares]
    ha_ativos = sum(p.hectares for p in ativos)
    ha_dias_ocupados = 0.0
    for pid, v in por_piquete.items():
        ha = piquetes[pid].hectares if pid in piquetes else None
        if ha:
            ha_dias_ocupados += min(v["dias"], dias_periodo) * ha

    def _lot(v):
        return round(v["ua_dias"] / v["ha_dias"], 2) if v["ha_dias"] else None

    def _media(xs):
        return round(sum(xs) / len(xs), 1) if xs else None

    tabela_piquetes = []
    for pid, v in por_piquete.items():
        p = piquetes.get(pid)
        if p is None:
            continue
        tabela_piquetes.append({
            "id": pid, "nome": p.nome, "ativo": p.ativo, "hectares": p.hectares,
            "pasto": pasto_em(pid, fim_efetivo), "uso": p.uso,
            "ocupacoes": v["ocupacoes"], "dias_ocupado": v["dias"],
            "lotacao": _lot(v),
            "descanso_medio": _media(descansos_por_piquete.get(pid, [])),
        })
    for p in ativos:  # piquete sem uso no período também aparece (pra ver o que está parado)
        if p.id not in por_piquete:
            tabela_piquetes.append({"id": p.id, "nome": p.nome, "ativo": True, "hectares": p.hectares,
                                    "pasto": pasto_em(p.id, fim_efetivo), "uso": p.uso, "ocupacoes": 0,
                                    "dias_ocupado": 0, "lotacao": None, "descanso_medio": None})
    return {
        "inicio": inicio.isoformat(),
        "fim": fim.isoformat(),
        "dias": dias_periodo,
        "lotacao_media": _lot(tot),
        "ocupacao_media_dias": _media(duracoes),
        "descanso_medio_dias": _media(todos_descansos),
        "uso_area_pct": round(ha_dias_ocupados / (ha_ativos * dias_periodo) * 100, 1) if ha_ativos else None,
        "ocupacoes": len(ocupacoes),
        "ocupacoes_sem_foto": sem_foto,
        "por_epoca": [{"epoca": k, "lotacao": _lot(v)} for k, v in sorted(por_epoca.items())],
        "por_piquete": sorted(tabela_piquetes, key=lambda x: x["nome"]),
        "por_pasto": [
            {"pasto": k, "lotacao": _lot(v),
             "gmd": round(v["ganho_cab_dias"] / v["cab_dias"], 3) if v["cab_dias"] else None,
             "ha_dias": round(v["ha_dias"], 1)}
            for k, v in sorted(por_pasto.items())
        ],
    }
