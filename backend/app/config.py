"""Configurações da aplicação, lidas de variáveis de ambiente / arquivo .env."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Caminho absoluto do banco SQLite (pasta backend), independente do diretório atual.
_BANCO_PADRAO = (Path(__file__).resolve().parent.parent / "gado.db").as_posix()


class Configuracoes(BaseSettings):
    # URL do banco. Padrão: SQLite local. Trocar para Postgres ao subir na nuvem.
    database_url: str = f"sqlite:///{_BANCO_PADRAO}"

    # Rendimentos padrão de carcaça por tipo de animal (editável na hora da venda).
    rendimento_vaca: float = 0.48
    rendimento_novilha: float = 0.50
    rendimento_boi: float = 0.52

    # Segredo para assinar os tokens de login. Em produção, definir AUTH_SECRET no .env.
    auth_secret: str = "troque-este-segredo-em-producao-gado-agua-do-tigre"
    # Validade do login em dias (longo: o app fica logado no celular).
    token_dias: int = 60

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


config = Configuracoes()
