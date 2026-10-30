"""Alertas do campo (o sininho 🔔): o que precisa de atenção hoje.

Calculados na hora a partir do painel de pastos — não ficam gravados. Tipos:
- mudar_lote: lote passou do máximo de dias no piquete (do piquete ou o padrão);
- piquete_pronto: piquete vazio que já cumpriu o descanso desejado;
- salgar: lote sem salga há mais dias que o limite (só lotes que já usam o controle de sal);
- pesar: lote com estimativa de peso "velha" (muito tempo sem balança);
- cronograma / sal_fora_da_faixa: entram quando esses módulos existirem (ver os geradores).
"""
from __future__ import annotations

import json
from datetime import date

from sqlalchemy.orm import Session

from ..models_campo import ConfigValor
from . import peso_estimado as pe
from .pastos import _hoje, painel

CHAVE = "alertas_limites"
# Os dois últimos são as faixas de cor da tela inicial (verde até o limite).
PADRAO = {"ocupacao_max_dias": 7, "sal_dias": 7, "mortalidade_max_pct": 2, "pesados_min_pct": 80}

# Outros módulos registram funções extras: f(db, hoje, dados_painel) -> list[dict]
GERADORES_EXTRAS = []


def carregar_limites(db: Session) -> dict:
    linha = db.get(ConfigValor, CHAVE)
    limites = dict(PADRAO)
    if linha is not None:
        try:
            limites.update(json.loads(linha.valor))
        except ValueError:
            pass
    return limites


def salvar_limites(db: Session, dados: dict) -> dict:
    limites = carregar_limites(db)
    for k in PADRAO:
        if k in dados and dados[k] not in (None, ""):
            v = int(dados[k])
            if not 1 <= v <= 365:
                raise ValueError("Os limites precisam ficar entre 1 e 365 dias.")
            limites[k] = v
    linha = db.get(ConfigValor, CHAVE) or ConfigValor(chave=CHAVE)
    linha.valor = json.dumps(limites)
    db.add(linha)
    db.commit()
    return limites


def _alerta(tipo: str, nivel: str, titulo: str, detalhe: str, alvo: dict) -> dict:
    # id estável no dia: o aparelho usa pra esconder o que a pessoa já marcou como visto
    return {"id": f"{tipo}:{alvo.get('tipo')}:{alvo.get('id')}", "tipo": tipo, "nivel": nivel,
            "titulo": titulo, "detalhe": detalhe, "alvo": alvo}


def alertas(db: Session, hoje: date | None = None) -> dict:
    hoje = hoje or _hoje()
    limites = carregar_limites(db)
    dados = painel(db, hoje)
    lista: list[dict] = []

    from .cronograma import proximos_por_lote
    proximos = proximos_por_lote(db)
    for p in dados["piquetes"]:
        for l in p["lotes"]:
            # Dias planejados no cronograma valem mais que o máximo do piquete/padrão.
            planejado = l.get("dias_previstos")
            maximo = planejado or p.get("ocupacao_max_dias") or limites["ocupacao_max_dias"]
            if (planejado and l["dias"] >= planejado) or (not planejado and l["dias"] > maximo):
                prox = proximos.get(l["id"])
                lista.append(_alerta(
                    "mudar_lote", "vermelho",
                    f"Mudar o lote {l['nome']}" + (f" para o {prox}" if prox else ""),
                    f"Está há {l['dias']} dias no {p['nome']} ({'previsto' if planejado else 'máximo'} {maximo}).",
                    {"tipo": "lote", "id": l["id"], "piquete_id": p["id"]}))
        if p["status"] == "pronto":
            lista.append(_alerta(
                "piquete_pronto", "verde", f"{p['nome']} pronto para receber gado",
                f"Descansou {p['dias']} dias (meta {p['descanso_meta_dias']}).",
                {"tipo": "piquete", "id": p["id"]}))

    todos_lotes = [l for p in dados["piquetes"] for l in p["lotes"]] + dados["sem_piquete"]
    for l in todos_lotes:
        s = l.get("ultima_salga")
        if s:
            dias_sal = (hoje - date.fromisoformat(s["data_hora"][:10])).days
            if dias_sal > limites["sal_dias"]:
                lista.append(_alerta(
                    "salgar", "amarelo", f"Salgar o cocho do {l['nome']}",
                    f"Última salga há {dias_sal} dias ({s['quantidade_kg']:g} kg de {s['produto']}).",
                    {"tipo": "lote", "id": l["id"]}))
        if l.get("estimativa_velha"):
            lista.append(_alerta(
                "pesar", "amarelo", f"Pesar o lote {l['nome']}",
                f"Tem animal há {l.get('dias_sem_pesar')} dias sem pesar (o peso estimado vale até "
                f"{pe.LIMITE_DIAS} dias).", {"tipo": "lote", "id": l["id"]}))

    from .campo import consumo_fora_da_faixa
    for c in consumo_fora_da_faixa(db, hoje):
        f = c["faixa"]
        faixa_txt = " a ".join(f"{v:g}" for v in (f.get("min"), f.get("max")) if v is not None)
        lista.append(_alerta(
            "sal_fora_da_faixa", "amarelo", f"Consumo de {c['produto']} {c['situacao']} no {c['lote']}",
            f"{c['g_cab_dia']} g por cabeça/dia (faixa {faixa_txt} g).",
            {"tipo": "lote", "id": c["lote_id"]}))

    for gerar in GERADORES_EXTRAS:
        lista.extend(gerar(db, hoje, dados))

    ordem = {"vermelho": 0, "amarelo": 1, "verde": 2}
    lista.sort(key=lambda a: (ordem.get(a["nivel"], 9), a["titulo"]))
    return {"hoje": hoje.isoformat(), "limites": limites, "alertas": lista}
