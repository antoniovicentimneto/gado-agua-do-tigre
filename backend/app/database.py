"""Conexão com o banco de dados e sessão do SQLAlchemy."""
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import config

# O check_same_thread só é necessário no SQLite; ignorado em outros bancos.
conectar_args = {}
if config.database_url.startswith("sqlite"):
    conectar_args = {"check_same_thread": False}

engine = create_engine(config.database_url, connect_args=conectar_args)
SessaoLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Fornece uma sessão de banco por requisição (dependência do FastAPI)."""
    db = SessaoLocal()
    try:
        yield db
    finally:
        db.close()
