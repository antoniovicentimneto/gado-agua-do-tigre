"""Endpoints de login, primeiro acesso e gestão de usuários."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import PapelUsuario, Usuario
from .. import schemas
from ..services import auth

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/status")
def status(db: Session = Depends(get_db)):
    """Indica se já existe algum usuário (para a tela de primeiro acesso)."""
    return {"tem_usuarios": db.query(Usuario).count() > 0}


@router.post("/setup", status_code=201)
def primeiro_acesso(dados: schemas.SetupDono, db: Session = Depends(get_db)):
    """Cria o primeiro usuário (DONO). Só funciona enquanto não houver ninguém."""
    if db.query(Usuario).count() > 0:
        raise HTTPException(status_code=400, detail="Já existe usuário cadastrado")
    u = Usuario(
        nome=dados.nome.strip(),
        usuario=dados.usuario.strip().lower(),
        senha_hash=auth.gerar_hash(dados.senha),
        papel=PapelUsuario.DONO,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return {"token": auth.criar_token(u), "nome": u.nome, "papel": u.papel.value,
            "usuario": u.usuario}


@router.post("/login")
def login(dados: schemas.Login, db: Session = Depends(get_db)):
    u = db.query(Usuario).filter(Usuario.usuario == dados.usuario.strip().lower()).first()
    if u is None or not auth.verificar_senha(dados.senha, u.senha_hash):
        raise HTTPException(status_code=401, detail="Usuário ou senha incorretos")
    return {"token": auth.criar_token(u), "nome": u.nome, "papel": u.papel.value,
            "usuario": u.usuario}


@router.get("/eu")
def eu(usuario: Usuario = Depends(auth.usuario_atual)):
    return {"id": usuario.id, "nome": usuario.nome, "usuario": usuario.usuario,
            "papel": usuario.papel.value}


# ----------------------------------------------------- Gestão de usuários (dono)

@router.get("/usuarios", response_model=list[schemas.UsuarioSaida])
def listar_usuarios(dono: Usuario = Depends(auth.requer_dono), db: Session = Depends(get_db)):
    return db.query(Usuario).order_by(Usuario.nome).all()


@router.post("/usuarios", status_code=201, response_model=schemas.UsuarioSaida)
def criar_usuario(dados: schemas.UsuarioCriar, dono: Usuario = Depends(auth.requer_dono),
                  db: Session = Depends(get_db)):
    nome_login = dados.usuario.strip().lower()
    if db.query(Usuario).filter(Usuario.usuario == nome_login).first():
        raise HTTPException(status_code=400, detail=f"Já existe o usuário '{nome_login}'")
    u = Usuario(nome=dados.nome.strip(), usuario=nome_login,
                senha_hash=auth.gerar_hash(dados.senha), papel=dados.papel)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@router.delete("/usuarios/{usuario_id}")
def remover_usuario(usuario_id: int, dono: Usuario = Depends(auth.requer_dono),
                    db: Session = Depends(get_db)):
    if usuario_id == dono.id:
        raise HTTPException(status_code=400, detail="Você não pode remover a si mesmo")
    u = db.get(Usuario, usuario_id)
    if u is None:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    db.delete(u)
    db.commit()
    return {"ok": True}
