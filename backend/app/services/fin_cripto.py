"""Cofre do certificado digital: o .pfx e a senha ficam criptografados no banco.

Chave = FIN_CHAVE do .env (ou, se não houver, derivada do AUTH_SECRET). Se essa chave
mudar, os certificados precisam ser enviados de novo (o app avisa)."""
from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.serialization import pkcs12

from ..config import config


class CertificadoInvalido(Exception):
    """Arquivo/senha do certificado não conferem, ou certificado vencido."""


def _fernet() -> Fernet:
    segredo = (getattr(config, "fin_chave", "") or config.auth_secret).encode()
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(b"fin-cert:" + segredo).digest()))


def cifrar(dados: bytes) -> bytes:
    return _fernet().encrypt(dados)


def decifrar(dados: bytes) -> bytes:
    try:
        return _fernet().decrypt(dados)
    except InvalidToken:
        raise CertificadoInvalido("Não consegui abrir o certificado guardado (a chave do servidor "
                                  "mudou). Envie o certificado de novo.")


def ler_certificado(pfx: bytes, senha: str):
    """Abre o .pfx e devolve (chave privada, certificado, info). Valida senha e validade."""
    try:
        chave, cert, _extra = pkcs12.load_key_and_certificates(pfx, (senha or "").encode())
    except ValueError:
        raise CertificadoInvalido("Senha do certificado incorreta ou arquivo não é um certificado A1 (.pfx)")
    if chave is None or cert is None:
        raise CertificadoInvalido("O arquivo não tem a chave privada do certificado")
    validade = cert.not_valid_after_utc
    titular = cert.subject.rfc4514_string()
    nome = next((a.value for a in cert.subject if a.oid.dotted_string == "2.5.4.3"), titular)
    if validade < datetime.now(timezone.utc):
        raise CertificadoInvalido(f"Certificado vencido em {validade:%d/%m/%Y}")
    return chave, cert, {"titular": str(nome), "validade": validade.replace(tzinfo=None)}


def documento_do_certificado(nome_titular: str) -> str | None:
    """O CN do e-CPF/e-CNPJ termina com ':<CPF ou CNPJ>' (ex.: 'FULANO:12345678900')."""
    if ":" in nome_titular:
        doc = "".join(c for c in nome_titular.rsplit(":", 1)[1] if c.isdigit())
        return doc if len(doc) in (11, 14) else None
    return None
