"""Log de auditoria: grava toda escrita feita na API (quem, o quê, quando).

Usado pelo middleware em app/main.py — nunca chamado diretamente pelas rotas.
"""
from __future__ import annotations

import json
import sys

from fastapi import Request

from ..database import SessaoLocal
from ..models import LogAlteracao
from .auth import ler_token

CAMPOS_SENSIVEIS = {"senha", "senha_hash"}
TAMANHO_MAXIMO_CORPO = 4000


def _scrub(valor):
    """Remove campos sensíveis (senha) do corpo antes de gravar no log."""
    if isinstance(valor, dict):
        return {
            chave: ("***" if chave.lower() in CAMPOS_SENSIVEIS else _scrub(v))
            for chave, v in valor.items()
        }
    if isinstance(valor, list):
        return [_scrub(v) for v in valor]
    return valor


def _texto_corpo(corpo_bytes: bytes) -> str | None:
    if not corpo_bytes:
        return None
    try:
        dados = json.loads(corpo_bytes)
        return json.dumps(_scrub(dados), ensure_ascii=False)[:TAMANHO_MAXIMO_CORPO]
    except (json.JSONDecodeError, UnicodeDecodeError):
        return corpo_bytes.decode("utf-8", errors="replace")[:TAMANHO_MAXIMO_CORPO]


def registrar(request: Request, corpo_bytes: bytes, status_code: int) -> None:
    """Grava uma linha do log numa sessão de banco própria (independente da
    sessão da requisição), pra não interferir na escrita que está sendo logada."""
    cabecalho = request.headers.get("authorization", "")
    payload = None
    if cabecalho.lower().startswith("bearer "):
        payload = ler_token(cabecalho.split(" ", 1)[1])

    db = SessaoLocal()
    try:
        db.add(LogAlteracao(
            usuario_id=payload.get("uid") if payload else None,
            usuario_nome=payload.get("nome") if payload else "desconhecido",
            metodo=request.method,
            rota=request.url.path,
            corpo=_texto_corpo(corpo_bytes),
            status_code=status_code,
        ))
        db.commit()
    except Exception as e:  # nunca deixa o log quebrar a escrita que está sendo auditada
        print(f"[auditoria] falha ao gravar log: {e}", file=sys.stderr)
        db.rollback()
    finally:
        db.close()
