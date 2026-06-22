"""Migra os dados do banco local (SQLite gado.db) para o banco na nuvem (Postgres/Supabase).

Lê a URL da nuvem do .env (DATABASE_URL). Copia todas as tabelas preservando os IDs
e ajusta as sequências do Postgres. Não roda se a nuvem já tiver animais (evita duplicar).

Uso:  python migrar_para_nuvem.py
"""
from pathlib import Path

from sqlalchemy import create_engine, insert, select, text

from app import models  # noqa: F401 (registra as tabelas no metadata)
from app.config import config
from app.database import Base

ORIGEM = "sqlite:///" + (Path(__file__).resolve().parent / "gado.db").as_posix()


def main() -> None:
    destino_url = config.database_url
    if destino_url.startswith("sqlite"):
        raise SystemExit("DATABASE_URL ainda aponta para SQLite. Configure o .env com a nuvem.")

    src = create_engine(ORIGEM)
    dst = create_engine(destino_url, connect_args={"connect_timeout": 20})

    # Cria as tabelas na nuvem.
    Base.metadata.create_all(dst)

    # Segurança: não migra se já houver animais na nuvem.
    with dst.connect() as c:
        ja = c.execute(text("SELECT COUNT(*) FROM animais")).scalar()
    if ja:
        raise SystemExit(f"A nuvem já tem {ja} animais. Migração cancelada para não duplicar.")

    # Copia tabela por tabela, na ordem de dependência (FKs).
    with src.connect() as s, dst.begin() as d:
        for tabela in Base.metadata.sorted_tables:
            linhas = [dict(r._mapping) for r in s.execute(select(tabela))]
            if linhas:
                d.execute(insert(tabela), linhas)
            print(f"{tabela.name}: {len(linhas)}")

    # Ajusta as sequências de ID no Postgres (pro próximo insert não colidir).
    with dst.begin() as d:
        for tabela in Base.metadata.sorted_tables:
            if "id" in tabela.c:
                d.execute(text(
                    f"SELECT setval(pg_get_serial_sequence('{tabela.name}', 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM {tabela.name}), 1))"
                ))

    print("=== Migração concluída ===")


if __name__ == "__main__":
    main()
