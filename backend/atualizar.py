"""Atualiza o banco a partir de uma planilha SEM apagar nada (importação incremental).

Diferente do `importar.py` (que recria tudo), este só adiciona animais novos e
pesagens em datas que ainda não existem — seguro para usar depois que você já
começou a lançar dados pelo app.

Uso:
    python atualizar.py "C:/caminho/para/PLANILHA.xlsx"
"""
import shutil
import sys
from datetime import datetime

from app.database import Base, SessaoLocal, engine
from app.services.importacao import importar_incremental

CAMINHO_PADRAO = r"C:\Users\User\Downloads\2025_PLANILHA GADO BOAVISTINHA.xlsx"


def main() -> None:
    caminho = sys.argv[1] if len(sys.argv) > 1 else CAMINHO_PADRAO
    Base.metadata.create_all(bind=engine)

    # Backup automático do banco antes de mexer.
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    try:
        shutil.copy("gado.db", f"gado_backup_{ts}.db")
        print(f"Backup criado: gado_backup_{ts}.db")
    except FileNotFoundError:
        pass

    db = SessaoLocal()
    try:
        resumo = importar_incremental(caminho, db)
    finally:
        db.close()

    print("=== Atualização incremental concluída (nada foi apagado) ===")
    for chave, valor in resumo.items():
        print(f"{chave}: {valor}")


if __name__ == "__main__":
    main()
