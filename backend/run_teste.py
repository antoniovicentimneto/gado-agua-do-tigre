"""Roda o backend com banco SQLite isolado (gado_teste.db) na porta 8078 — usado
pra testar no navegador sem tocar no Supabase de produção. Ver CLAUDE.md."""
import os
from pathlib import Path

BASE = Path(__file__).resolve().parent
os.chdir(BASE)
os.environ["DATABASE_URL"] = f"sqlite:///{(BASE / 'gado_teste.db').as_posix()}"

import uvicorn  # noqa: E402 (precisa do DATABASE_URL setado antes de importar o app)

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8078, reload=False)
