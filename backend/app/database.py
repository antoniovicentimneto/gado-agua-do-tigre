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


# Colunas adicionadas depois que as tabelas já existiam em produção. O create_all só
# cria tabela nova — não acrescenta coluna — então elas são incluídas aqui (só ADD
# COLUMN, nunca apaga nem altera dado). Formato: (tabela, coluna, tipo SQL).
COLUNAS_NOVAS = [
    ("vendas", "acabamento", "VARCHAR(20)"),
    ("vendas", "dentes_frigorifico", "INTEGER"),
    ("pesagens", "chave_cliente", "VARCHAR(40)"),
    ("animais", "mae_id", "INTEGER REFERENCES animais(id)"),
    ("animais", "data_desmame", "DATE"),
    ("animais", "prenhez", "VARCHAR(10)"),
    ("animais", "prenhez_data", "DATE"),
]


def migrar_colunas(eng=None) -> None:
    """Acrescenta as colunas de COLUNAS_NOVAS que ainda não existem (idempotente)."""
    from sqlalchemy import inspect, text

    eng = eng or engine
    insp = inspect(eng)
    tabelas = set(insp.get_table_names())
    with eng.begin() as con:
        for tabela, coluna, tipo in COLUNAS_NOVAS:
            if tabela not in tabelas:
                continue
            if coluna not in {c["name"] for c in insp.get_columns(tabela)}:
                con.execute(text(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}"))


def get_db():
    """Fornece uma sessão de banco por requisição (dependência do FastAPI)."""
    db = SessaoLocal()
    try:
        yield db
    finally:
        db.close()
