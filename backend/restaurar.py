"""Restaura o banco a partir do Excel exportado pelo PRÓPRIO app (Painel → Exportar).

Use isso se reinstalar o app, trocar de banco ou perder os dados: pega o
último Excel que você exportou (ou qualquer um que tenha baixado) e recria
tudo que estiver faltando. Não apaga nem sobrescreve nada que já exista.

Uso:
    python restaurar.py "C:/caminho/para/gado_agua_do_tigre_2026-06-22.xlsx"
"""
import sys

from app.database import Base, SessaoLocal, engine
from app.services.restauracao import restaurar_backup


def main() -> None:
    if len(sys.argv) < 2:
        print("Uso: python restaurar.py \"caminho/para/backup_exportado.xlsx\"")
        sys.exit(1)

    caminho = sys.argv[1]
    Base.metadata.create_all(bind=engine)

    db = SessaoLocal()
    try:
        resumo = restaurar_backup(caminho, db)
    except ValueError as e:
        print(f"Erro: {e}")
        sys.exit(1)
    finally:
        db.close()

    print("=== Restauração concluída (nada foi apagado) ===")
    for chave, valor in resumo.items():
        print(f"{chave}: {valor}")


if __name__ == "__main__":
    main()
