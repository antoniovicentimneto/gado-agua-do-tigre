"""Script de linha de comando para importar a planilha para o banco.

Uso:
    python importar.py "C:/caminho/para/PLANILHA.xlsx"
Se o caminho não for informado, usa o padrão da área de trabalho.
"""
import sys

from app.database import Base, SessaoLocal, engine
from app.services.importacao import importar_planilha

CAMINHO_PADRAO = r"C:\Users\User\Desktop\2025_PLANILHA GADO BOAVISTINHA.xlsx"


def main() -> None:
    caminho = sys.argv[1] if len(sys.argv) > 1 else CAMINHO_PADRAO

    # Cria as tabelas (caso ainda não existam).
    Base.metadata.create_all(bind=engine)

    db = SessaoLocal()
    try:
        resumo = importar_planilha(caminho, db)
    finally:
        db.close()

    print("=== Importação concluída ===")
    for chave, valor in resumo.items():
        if chave == "datas_corrigidas":
            print(f"datas_corrigidas: {len(valor)}")
            for item in valor:
                print(f"   - {item}")
        else:
            print(f"{chave}: {valor}")


if __name__ == "__main__":
    main()
