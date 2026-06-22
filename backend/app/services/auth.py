"""Autenticação: hash de senha, token assinado e dependências de permissão.

Usa só a biblioteca padrão (hashlib/hmac) — sem dependências extras. O token é
um mini-JWT: payload em base64 + assinatura HMAC-SHA256.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from ..config import config
from ..database import get_db
from ..models import PapelUsuario, Usuario

# ----------------------------------------------------------- Senha

def gerar_hash(senha: str) -> str:
    """Gera o hash da senha (PBKDF2-HMAC-SHA256 com sal aleatório)."""
    sal = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", senha.encode(), sal.encode(), 200_000)
    return f"{sal}${dk.hex()}"


def verificar_senha(senha: str, senha_hash: str) -> bool:
    """Confere a senha contra o hash guardado."""
    try:
        sal, esperado = senha_hash.split("$", 1)
    except ValueError:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", senha.encode(), sal.encode(), 200_000)
    return hmac.compare_digest(dk.hex(), esperado)


# ----------------------------------------------------------- Token

def _b64(dados: bytes) -> str:
    return base64.urlsafe_b64encode(dados).decode().rstrip("=")


def _unb64(txt: str) -> bytes:
    return base64.urlsafe_b64decode(txt + "=" * (-len(txt) % 4))


def criar_token(usuario: Usuario) -> str:
    """Cria um token assinado com id, papel e validade."""
    payload = {
        "uid": usuario.id,
        "papel": usuario.papel.value,
        "nome": usuario.nome,
        "exp": int(time.time()) + config.token_dias * 86400,
    }
    corpo = _b64(json.dumps(payload).encode())
    assinatura = hmac.new(config.auth_secret.encode(), corpo.encode(), hashlib.sha256).digest()
    return f"{corpo}.{_b64(assinatura)}"


def ler_token(token: str) -> dict | None:
    """Valida a assinatura e a validade; devolve o payload ou None."""
    try:
        corpo, sig = token.split(".", 1)
        esperada = hmac.new(config.auth_secret.encode(), corpo.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(_unb64(sig), esperada):
            return None
        payload = json.loads(_unb64(corpo))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


# ----------------------------------------------------------- Dependências

def usuario_atual(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Usuario:
    """Lê o token do cabeçalho Authorization e devolve o usuário logado."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Não autenticado")
    payload = ler_token(authorization.split(" ", 1)[1])
    if payload is None:
        raise HTTPException(status_code=401, detail="Sessão expirada, faça login de novo")
    usuario = db.get(Usuario, payload["uid"])
    if usuario is None:
        raise HTTPException(status_code=401, detail="Usuário não encontrado")
    return usuario


def requer_dono(usuario: Usuario = Depends(usuario_atual)) -> Usuario:
    """Garante que o usuário é DONO (acesso total)."""
    if usuario.papel != PapelUsuario.DONO:
        raise HTTPException(status_code=403, detail="Ação permitida só para o dono")
    return usuario
