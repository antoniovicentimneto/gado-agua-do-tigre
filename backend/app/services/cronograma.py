"""Cronograma de rotação: a fila de próximos piquetes de cada lote, com os dias previstos.

As datas são calculadas a partir da ocupação atual: o lote sai do piquete atual quando
completar os dias previstos (do cronograma, do piquete ou o padrão dos alertas) e entra no
próximo da fila, e assim por diante. Se a entrada prevista cair antes de o piquete
cumprir o descanso desejado, o item vem marcado com o aviso.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from ..models import LotePiquete, Lote, Piquete
from ..models_campo import CronogramaItem
from .pastos import ErroPasto, _hoje, _ocupacao_aberta, mover, painel


def _dias_atual(ocup: LotePiquete | None, piquete: Piquete | None, padrao: int) -> int:
    if ocup is not None and ocup.dias_previstos:
        return ocup.dias_previstos
    if piquete is not None and piquete.ocupacao_max_dias:
        return piquete.ocupacao_max_dias
    return padrao


def cronograma_lote(db: Session, lote_id: int, hoje: date | None = None,
                    dados_painel: dict | None = None) -> dict:
    from .alertas import carregar_limites
    hoje = hoje or _hoje()
    lote = db.get(Lote, lote_id)
    if lote is None:
        raise ErroPasto("Lote não encontrado.")
    dados = dados_painel or painel(db, hoje)
    status = {p["id"]: p for p in dados["piquetes"]}
    padrao = carregar_limites(db)["ocupacao_max_dias"]

    ocup = _ocupacao_aberta(db, lote_id)
    atual = db.get(Piquete, ocup.piquete_id) if ocup else None
    saida_prevista = None
    if ocup:
        saida_prevista = ocup.data_entrada + timedelta(days=_dias_atual(ocup, atual, padrao))

    itens = (db.query(CronogramaItem).filter(CronogramaItem.lote_id == lote_id)
             .order_by(CronogramaItem.ordem, CronogramaItem.id).all())
    lista = []
    entrada = max(saida_prevista or hoje, hoje)
    for it in itens:
        p = db.get(Piquete, it.piquete_id)
        st = status.get(it.piquete_id, {})
        aviso = None
        if p is None or not p.ativo:
            aviso = "piquete não existe mais (foi dividido ou removido)"
        elif st.get("status") in ("descansando",) and p.descanso_meta_dias and st.get("ultima_saida"):
            pronto_em = date.fromisoformat(st["ultima_saida"]) + timedelta(days=p.descanso_meta_dias)
            if entrada < pronto_em:
                aviso = f"entra {(pronto_em - entrada).days} dia(s) antes de cumprir o descanso"
        elif st.get("status") == "ocupado":
            outros = [l["nome"] for l in st.get("lotes", []) if l["id"] != lote_id]
            if outros:
                aviso = f"hoje está com {', '.join(outros)}"
        saida = entrada + timedelta(days=it.dias_previstos)
        lista.append({
            "id": it.id, "piquete_id": it.piquete_id, "piquete": p.nome if p else "?",
            "hectares": p.hectares if p else None, "dias": it.dias_previstos,
            "entrada_prevista": entrada.isoformat(), "saida_prevista": saida.isoformat(),
            "aviso": aviso,
        })
        entrada = saida
    return {
        "lote": {"id": lote.id, "nome": lote.nome},
        "atual": {"piquete_id": atual.id, "piquete": atual.nome,
                  "entrada": ocup.data_entrada.isoformat(),
                  "dias_previstos": _dias_atual(ocup, atual, padrao),
                  "saida_prevista": saida_prevista.isoformat()} if ocup and atual else None,
        "itens": lista,
    }


def salvar(db: Session, lote_id: int, itens: list[dict], dias_atual: int | None = None) -> dict:
    """Troca a fila inteira do lote: [{piquete_id, dias}] na ordem. Opcionalmente ajusta
    quantos dias o lote deve ficar no piquete atual."""
    if db.get(Lote, lote_id) is None:
        raise ErroPasto("Lote não encontrado.")
    limpos = []
    for i, it in enumerate(itens or []):
        try:
            pid, dias = int(it["piquete_id"]), int(it["dias"])
        except (KeyError, TypeError, ValueError):
            raise ErroPasto("Cada item precisa de piquete e dias.")
        p = db.get(Piquete, pid)
        if p is None or not p.ativo:
            raise ErroPasto("Piquete do cronograma não encontrado.")
        if not 1 <= dias <= 365:
            raise ErroPasto("Dias previstos devem ficar entre 1 e 365.")
        limpos.append(CronogramaItem(lote_id=lote_id, ordem=i, piquete_id=pid, dias_previstos=dias))
    db.query(CronogramaItem).filter(CronogramaItem.lote_id == lote_id).delete()
    db.add_all(limpos)
    if dias_atual is not None:
        ocup = _ocupacao_aberta(db, lote_id)
        if ocup is not None:
            if not 1 <= int(dias_atual) <= 365:
                raise ErroPasto("Dias previstos devem ficar entre 1 e 365.")
            ocup.dias_previstos = int(dias_atual)
    db.commit()
    return cronograma_lote(db, lote_id)


def avancar(db: Session, lote_id: int, quando: date | None = None, chave: str | None = None,
            usuario: str | None = None) -> dict:
    """Leva o lote para o próximo piquete da fila (a fila anda e os dias previstos do item
    viram o planejado da nova ocupação)."""
    primeiro = (db.query(CronogramaItem).filter(CronogramaItem.lote_id == lote_id)
                .order_by(CronogramaItem.ordem, CronogramaItem.id).first())
    if primeiro is None:
        raise ErroPasto("O cronograma desse lote está vazio.")
    dias = primeiro.dias_previstos
    r = mover(db, lote_id, primeiro.piquete_id, quando, chave, usuario)
    ocup = _ocupacao_aberta(db, lote_id)
    if ocup is not None and ocup.piquete_id == primeiro.piquete_id:
        ocup.dias_previstos = dias
    db.delete(primeiro)
    db.commit()
    return r


def visao_geral(db: Session, hoje: date | None = None) -> list[dict]:
    """Cronograma de todos os lotes que estão em piquete (pra tela geral)."""
    hoje = hoje or _hoje()
    dados = painel(db, hoje)
    saida = []
    for p in dados["piquetes"]:
        for l in p["lotes"]:
            c = cronograma_lote(db, l["id"], hoje, dados)
            c["lote"].update({"cor": l["cor"], "icone": l["icone"], "cabecas": l["cabecas"]})
            saida.append(c)
    return sorted(saida, key=lambda c: (c["atual"] or {}).get("saida_prevista") or "9999")


def proximos_por_lote(db: Session) -> dict[int, str]:
    """Nome do próximo piquete da fila de cada lote (pro texto do alerta)."""
    saida: dict[int, str] = {}
    itens = db.query(CronogramaItem).order_by(CronogramaItem.lote_id, CronogramaItem.ordem, CronogramaItem.id)
    for it in itens:
        if it.lote_id not in saida:
            p = db.get(Piquete, it.piquete_id)
            saida[it.lote_id] = p.nome if p else "?"
    return saida
