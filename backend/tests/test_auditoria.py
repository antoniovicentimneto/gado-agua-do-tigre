"""Testes do log de auditoria: services/auditoria.py e GET /api/logs."""
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import LogAlteracao, PapelUsuario, Usuario
from app.routers import api
from app.services import auditoria
from app.services.auth import criar_token


class FakeRequest:
    """Substituto leve de fastapi.Request — só precisa de headers/método/rota."""
    def __init__(self, caminho, metodo="POST", token=None):
        self.method = metodo
        self.url = SimpleNamespace(path=caminho)
        self.headers = {"authorization": f"Bearer {token}"} if token else {}


def _sessao_isolada(monkeypatch):
    """Engine em memória própria pro log — imita a sessão independente que
    services/auditoria.registrar abre de verdade (SessaoLocal())."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Sessao = sessionmaker(bind=engine)
    monkeypatch.setattr(auditoria, "SessaoLocal", Sessao)
    return Sessao


def test_registrar_grava_usuario_metodo_rota(monkeypatch):
    Sessao = _sessao_isolada(monkeypatch)
    usuario = Usuario(id=7, nome="Antonio", papel=PapelUsuario.DONO)
    token = criar_token(usuario)
    req = FakeRequest("/api/animais/1", "PUT", token)

    auditoria.registrar(req, b'{"tipo": "Vaca"}', 200)

    s = Sessao()
    log = s.query(LogAlteracao).one()
    assert log.usuario_id == 7
    assert log.usuario_nome == "Antonio"
    assert log.metodo == "PUT"
    assert log.rota == "/api/animais/1"
    assert log.status_code == 200
    assert "Vaca" in log.corpo
    s.close()


def test_registrar_tira_senha_do_corpo(monkeypatch):
    Sessao = _sessao_isolada(monkeypatch)
    usuario = Usuario(id=1, nome="Dono", papel=PapelUsuario.DONO)
    token = criar_token(usuario)
    req = FakeRequest("/api/auth/usuarios", "POST", token)

    auditoria.registrar(req, b'{"nome": "Joao", "senha": "segredo123"}', 201)

    s = Sessao()
    log = s.query(LogAlteracao).one()
    assert "segredo123" not in log.corpo
    assert "***" in log.corpo
    s.close()


def test_registrar_sem_token_usa_desconhecido(monkeypatch):
    Sessao = _sessao_isolada(monkeypatch)
    req = FakeRequest("/api/lotes/mover", "POST")

    auditoria.registrar(req, b"{}", 200)

    s = Sessao()
    log = s.query(LogAlteracao).one()
    assert log.usuario_id is None
    assert log.usuario_nome == "desconhecido"
    s.close()


def test_listar_logs_pagina_e_filtra_por_usuario(db):
    db.add_all([
        LogAlteracao(usuario_id=1, usuario_nome="Antonio", metodo="PUT",
                     rota="/api/animais/1", corpo="{}", status_code=200),
        LogAlteracao(usuario_id=2, usuario_nome="Peao", metodo="POST",
                     rota="/api/animais/1/pesagens", corpo="{}", status_code=201),
    ])
    db.commit()

    todos = api.listar_logs(db=db, pagina=1)
    assert todos["total"] == 2

    so_antonio = api.listar_logs(usuario_id=1, db=db, pagina=1)
    assert so_antonio["total"] == 1
    assert so_antonio["itens"][0]["usuario_nome"] == "Antonio"
