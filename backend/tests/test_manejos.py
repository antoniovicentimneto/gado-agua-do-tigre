"""Testes do histórico de manejos (sessões do app + pesagens antigas/legado)."""
from datetime import date

from app.models import TipoSessao
from app.services import manejos as svc
from app.services import sessao as svc_sessao

HOJE = date(2026, 6, 15)


def test_lista_inclui_legado_das_pesagens_sem_sessao(db):
    # O fixture semeia pesagens em 2026-01-01 (3 animais) e 2026-05-01 (1 animal),
    # nenhuma ligada a sessão — devem aparecer como manejos "legado".
    lista = svc.listar(db)
    legados = {m["data"]: m for m in lista if m["tipo"] == "legado"}
    assert date(2026, 1, 1) in legados
    assert legados[date(2026, 1, 1)]["total"] == 3
    assert date(2026, 5, 1) in legados
    assert legados[date(2026, 5, 1)]["total"] == 1


def test_lista_inclui_sessoes_do_app(db):
    s = svc_sessao.criar_sessao(db, TipoSessao.MANEJO, HOJE, ["LOTEA"], True, ["Gordo"])
    svc_sessao.registrar_pesagem(db, s, "101", 410, destino_lote="Gordo")
    lista = svc.listar(db)
    sessoes = [m for m in lista if m["tipo"] == "manejo"]
    assert len(sessoes) == 1
    assert sessoes[0]["chave"] == f"s:{s.id}"
    assert sessoes[0]["total"] == 1
    assert sessoes[0]["lotes"] == ["Gordo", "LOTEA"]


def test_detalhe_sessao_traz_pesados_com_destino(db):
    s = svc_sessao.criar_sessao(db, TipoSessao.MANEJO, HOJE, ["LOTEA"], True, ["Gordo"])
    svc_sessao.registrar_pesagem(db, s, "101", 410, destino_lote="Gordo")
    svc_sessao.registrar_pesagem(db, s, "102", 330, destino_lote="Gordo")
    d = svc.detalhe_sessao(db, s.id)
    assert d["total"] == 2
    brincos = {p["brinco"]: p["destino"] for p in d["pesados"]}
    assert brincos == {"101": "Gordo", "102": "Gordo"}


def test_detalhe_sessao_inexistente_retorna_none(db):
    assert svc.detalhe_sessao(db, 9999) is None


def test_detalhe_legado_ordena_por_brinco(db):
    d = svc.detalhe_legado(db, date(2026, 1, 1))
    assert d["total"] == 3
    assert [p["brinco"] for p in d["pesados"]] == ["101", "102", "201"]
    # Não tem sessão, então não tem campo "destino".
    assert "destino" not in d["pesados"][0]
