"""Aplicação FastAPI: API + interface web responsiva do controle de gado."""
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from .database import Base, engine
from .routers import api, auth, sessoes

# Cria as tabelas no primeiro start (idempotente).
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Gado Água do Tigre", version="0.1.0")
app.include_router(auth.router)
app.include_router(api.router)
app.include_router(sessoes.router)


@app.middleware("http")
async def sem_cache_estaticos(request: Request, call_next):
    """Evita que o navegador segure versões antigas do frontend (HTML/CSS/JS)."""
    resposta = await call_next(request)
    if request.url.path in ("/", "/sw.js") or request.url.path.startswith("/static"):
        resposta.headers["Cache-Control"] = "no-store"
    return resposta

# Pasta de arquivos estáticos (frontend).
ESTATICOS = Path(__file__).resolve().parent.parent / "static"


@app.get("/", response_class=HTMLResponse)
def home() -> HTMLResponse:
    """Entrega a página principal do app."""
    return HTMLResponse((ESTATICOS / "index.html").read_text(encoding="utf-8"))


@app.get("/sw.js")
def service_worker() -> Response:
    """Service worker servido na raiz para o escopo cobrir todo o app."""
    conteudo = (ESTATICOS / "service-worker.js").read_text(encoding="utf-8")
    return Response(content=conteudo, media_type="application/javascript")


# Demais arquivos estáticos (CSS/JS) ficam sob /static.
app.mount("/static", StaticFiles(directory=ESTATICOS), name="static")
