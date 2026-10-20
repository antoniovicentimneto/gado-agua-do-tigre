"""Endpoints do Financeiro (/api/fin/*). Só o DONO acessa (peão não vê dinheiro)."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Usuario
from ..models_financeiro import FinConta, FinContribuinte, FinFazenda
from ..services import (
    fin_consipa,
    fin_graficos,
    fin_cripto,
    fin_extrato,
    fin_fechamento,
    fin_lancamentos,
    fin_nfe_xml,
    fin_notas,
    fin_plano,
    fin_resultado,
    fin_sefaz,
)
from ..services.auth import requer_dono

router = APIRouter(prefix="/api/fin", tags=["financeiro"], dependencies=[Depends(requer_dono)])

TAMANHO_MAX = 30 * 1024 * 1024  # a CONSIPA tem ~12 MB


def _executar(funcao, *args, **kwargs):
    """Erro de regra vira 400 com mensagem amigável (sem stack trace)."""
    try:
        return funcao(*args, **kwargs)
    except (fin_plano.ErroFinanceiro, fin_nfe_xml.XmlInvalido, fin_cripto.CertificadoInvalido,
            fin_sefaz.ErroSefaz) as e:
        raise HTTPException(status_code=400, detail=str(e))


async def _ler(arquivo: UploadFile) -> bytes:
    conteudo = await arquivo.read()
    if len(conteudo) > TAMANHO_MAX:
        raise HTTPException(status_code=400, detail="Arquivo grande demais (máx. 30 MB)")
    return conteudo


# ---------------------------------------------------------------- cadastros

@router.get("/cadastros")
def cadastros(db: Session = Depends(get_db)):
    fin_lancamentos.gerar_recorrentes(db)
    return {**fin_plano.cadastros(db), "fornecedores": fin_lancamentos.listar_fornecedores(db)}


@router.post("/plano")
def plano_criar(dados: dict = Body(...), db: Session = Depends(get_db)):
    return _executar(fin_plano.salvar_plano, db, dados)


@router.put("/plano/{pid}")
def plano_editar(pid: int, dados: dict = Body(...), db: Session = Depends(get_db)):
    return _executar(fin_plano.salvar_plano, db, dados, pid)


@router.post("/fazendas")
def fazenda_criar(dados: dict = Body(...), db: Session = Depends(get_db)):
    return _executar(fin_plano.salvar_simples, db, FinFazenda, dados)


@router.put("/fazendas/{fid}")
def fazenda_editar(fid: int, dados: dict = Body(...), db: Session = Depends(get_db)):
    return _executar(fin_plano.salvar_simples, db, FinFazenda, dados, fid)


@router.post("/contas")
def conta_criar(dados: dict = Body(...), db: Session = Depends(get_db)):
    return _executar(fin_plano.salvar_simples, db, FinConta, dados)


@router.put("/contas/{cid}")
def conta_editar(cid: int, dados: dict = Body(...), db: Session = Depends(get_db)):
    return _executar(fin_plano.salvar_simples, db, FinConta, dados, cid)


@router.post("/fornecedores")
def fornecedor_criar(dados: dict = Body(...), db: Session = Depends(get_db)):
    return _executar(fin_lancamentos.salvar_fornecedor, db, dados, None)


@router.put("/fornecedores/{fid}")
def fornecedor_editar(fid: int, dados: dict = Body(...), db: Session = Depends(get_db)):
    return _executar(fin_lancamentos.salvar_fornecedor, db, dados, fid)


@router.post("/fornecedores/{fid}/juntar")
def fornecedor_juntar(fid: int, dados: dict = Body(...), db: Session = Depends(get_db)):
    return _executar(fin_lancamentos.juntar_fornecedores, db, fid, [int(i) for i in dados.get("ids", [])])


@router.get("/sugestao")
def sugestao(nome: str = "", documento: str = "", db: Session = Depends(get_db)):
    return fin_lancamentos.sugestao_fornecedor(db, nome, documento)


# ---------------------------------------------------------------- lançamentos

@router.get("/lancamentos")
def lancamentos(excluidos: bool = False, db: Session = Depends(get_db)):
    return fin_lancamentos.listar(db, excluidos)


@router.get("/lancamentos/{lid}")
def lancamento(lid: int, db: Session = Depends(get_db)):
    return _executar(fin_lancamentos.detalhe, db, lid)


@router.post("/lancamentos")
def lancamento_criar(dados: dict = Body(...), db: Session = Depends(get_db),
                     usuario: Usuario = Depends(requer_dono)):
    lanc = _executar(fin_lancamentos.criar, db, dados, usuario.nome)
    return fin_lancamentos.detalhe(db, lanc.id)


@router.put("/lancamentos/{lid}")
def lancamento_editar(lid: int, dados: dict = Body(...), db: Session = Depends(get_db),
                      usuario: Usuario = Depends(requer_dono)):
    lanc = _executar(fin_lancamentos.atualizar, db, lid, dados, usuario.nome)
    return fin_lancamentos.detalhe(db, lanc.id)


@router.post("/lancamentos/{lid}/excluir")
def lancamento_excluir(lid: int, dados: dict = Body(default={}), db: Session = Depends(get_db),
                       usuario: Usuario = Depends(requer_dono)):
    _executar(fin_lancamentos.excluir, db, lid, dados.get("motivo") or "", usuario.nome)
    return {"ok": True}


@router.post("/lancamentos/{lid}/restaurar")
def lancamento_restaurar(lid: int, db: Session = Depends(get_db), usuario: Usuario = Depends(requer_dono)):
    _executar(fin_lancamentos.restaurar, db, lid, usuario.nome)
    return {"ok": True}


@router.get("/fechamento/{sessao_id}")
def fechamento_resumo(sessao_id: int, db: Session = Depends(get_db)):
    """Números do manejo de venda/compra + fechamento já lançado (se houver)."""
    return _executar(fin_fechamento.resumo, db, sessao_id)


@router.put("/fechamento/{sessao_id}")
def fechamento_salvar(sessao_id: int, dados: dict = Body(...), db: Session = Depends(get_db),
                      usuario: Usuario = Depends(requer_dono)):
    return _executar(fin_fechamento.salvar, db, sessao_id, dados, usuario.nome)


@router.delete("/fechamento/{sessao_id}")
def fechamento_desfazer(sessao_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(requer_dono)):
    _executar(fin_fechamento.desfazer, db, sessao_id, usuario.nome)
    return {"ok": True}


@router.get("/fechamentos")
def fechamentos(db: Session = Depends(get_db)):
    """Selo 'lançado no Financeiro' por manejo (sessao_id → valores)."""
    return fin_fechamento.por_sessao(db)


@router.put("/parcelas/{pid}")
def parcela_marcar(pid: int, dados: dict = Body(...), db: Session = Depends(get_db)):
    _executar(fin_lancamentos.marcar_parcela, db, pid, dados.get("pago"), dados.get("valor"))
    return {"ok": True}


@router.post("/lancamentos/nao-duplicado")
def nao_duplicado(dados: dict = Body(...), db: Session = Depends(get_db)):
    fin_lancamentos.marcar_nao_duplicado(db, [int(i) for i in dados.get("ids", [])])
    return {"ok": True}


@router.get("/conferencia")
def conferencia(db: Session = Depends(get_db)):
    """Alertas da tela Revisar: duplicados possíveis e recorrentes a confirmar."""
    fin_lancamentos.gerar_recorrentes(db)
    return {"duplicados": fin_lancamentos.possiveis_duplicados(db), "a_confirmar": fin_lancamentos.a_confirmar(db)}


# ---------------------------------------------------------------- resultado por mês

@router.get("/resultado")
def resultado(inicio: str = "", fim: str = "", visao: str = "caixa", status: str = "todos",
              fazenda: str = "", setor: str = "", db: Session = Depends(get_db)):
    return fin_resultado.resultado(db, {"inicio": inicio, "fim": fim, "visao": visao, "status": status,
                                        "fazenda": fazenda, "setor": setor})


@router.get("/graficos")
def graficos(ano: str = "", visao: str = "caixa", fazenda: str = "", status: str = "todos",
             db: Session = Depends(get_db)):
    """Receita × despesa por ano e por mês, despesa por setor e maiores categorias."""
    return fin_graficos.graficos(db, {"ano": ano, "visao": visao, "fazenda": fazenda, "status": status})


@router.post("/resultado/detalhe")
def resultado_detalhe(dados: dict = Body(...), db: Session = Depends(get_db)):
    return fin_resultado.detalhar(db, dados.get("filtros") or {}, dados.get("caminho") or [], dados.get("mes"))


# ---------------------------------------------------------------- recorrentes

@router.get("/recorrentes")
def recorrentes(db: Session = Depends(get_db)):
    return fin_lancamentos.listar_recorrentes(db)


@router.post("/recorrentes")
def recorrente_criar(dados: dict = Body(...), db: Session = Depends(get_db)):
    return _executar(fin_lancamentos.salvar_recorrente, db, dados, None)


@router.put("/recorrentes/{rid}")
def recorrente_editar(rid: int, dados: dict = Body(...), db: Session = Depends(get_db)):
    return _executar(fin_lancamentos.salvar_recorrente, db, dados, rid)


# ---------------------------------------------------------------- importação da CONSIPA

@router.post("/importar-consipa")
async def importar_consipa(arquivo: UploadFile = File(...), antiga: UploadFile | None = File(None),
                           db: Session = Depends(get_db), usuario: Usuario = Depends(requer_dono)):
    """CONSIPA atual + (opcional) planilha antiga com os anos anteriores."""
    conteudo = await _ler(arquivo)
    conteudo_antiga = await _ler(antiga) if antiga is not None else None
    return _executar(fin_consipa.importar, db, conteudo, usuario.nome, conteudo_antiga)


# ---------------------------------------------------------------- notas fiscais

@router.get("/notas")
def notas(situacao: str = "pendentes", db: Session = Depends(get_db)):
    return fin_notas.listar(db, situacao or None)


@router.get("/notas/{nid}")
def nota(nid: int, db: Session = Depends(get_db)):
    return _executar(fin_notas.detalhe, db, nid)


@router.post("/notas/xml")
async def notas_xml(arquivos: list[UploadFile] = File(...), db: Session = Depends(get_db)):
    lidos = [(a.filename or "nota.xml", await _ler(a)) for a in arquivos]
    return _executar(fin_notas.receber_arquivos, db, lidos)


@router.post("/notas/{nid}/lancar")
def nota_lancar(nid: int, dados: dict = Body(...), db: Session = Depends(get_db),
                usuario: Usuario = Depends(requer_dono)):
    return _executar(fin_notas.lancar, db, nid, dados, usuario.nome)


@router.post("/notas/{nid}/ignorar")
def nota_ignorar(nid: int, dados: dict = Body(default={}), db: Session = Depends(get_db)):
    _executar(fin_notas.ignorar, db, nid, bool(dados.get("voltar")))
    return {"ok": True}


# ---------------------------------------------------------------- CPF/CNPJ + certificado + SEFAZ

def _dict_contribuinte(c: FinContribuinte) -> dict:
    return {"id": c.id, "documento": c.documento, "nome": c.nome, "uf": c.uf, "fazenda": c.fazenda,
            "ambiente": c.ambiente, "ativo": c.ativo, "tem_certificado": bool(c.cert_pfx),
            "cert_titular": c.cert_titular,
            "cert_validade": c.cert_validade.isoformat() if c.cert_validade else None,
            "ult_nsu": c.ult_nsu, "max_nsu": c.max_nsu,
            "ultima_consulta": fin_plano.iso_utc(c.ultima_consulta),
            "pode_consultar_apos": fin_plano.iso_utc(c.pode_consultar_apos),
            "ultimo_retorno": c.ultimo_retorno}


def _contribuinte(db: Session, cid: int) -> FinContribuinte:
    c = db.get(FinContribuinte, cid)
    if c is None:
        raise HTTPException(status_code=404, detail="CPF/CNPJ não encontrado")
    return c


@router.get("/contribuintes")
def contribuintes(db: Session = Depends(get_db)):
    from sqlalchemy import select
    return [_dict_contribuinte(c) for c in db.scalars(select(FinContribuinte).order_by(FinContribuinte.nome))]


@router.post("/contribuintes")
def contribuinte_criar(dados: dict = Body(...), db: Session = Depends(get_db)):
    return _salvar_contribuinte(db, FinContribuinte(), dados)


@router.put("/contribuintes/{cid}")
def contribuinte_editar(cid: int, dados: dict = Body(...), db: Session = Depends(get_db)):
    return _salvar_contribuinte(db, _contribuinte(db, cid), dados)


def _salvar_contribuinte(db: Session, c: FinContribuinte, dados: dict) -> dict:
    doc = fin_lancamentos.so_digitos(dados.get("documento") or c.documento)
    if len(doc) not in (11, 14):
        raise HTTPException(status_code=400, detail="Digite um CPF (11 números) ou CNPJ (14 números)")
    if not _documento_valido(doc):
        raise HTTPException(status_code=400, detail="CPF/CNPJ inválido (confira os dígitos)")
    if c.documento and c.documento != doc:
        c.ult_nsu, c.max_nsu = "0", None  # outro documento: recomeça a busca do zero
    c.documento = doc
    c.nome = (dados.get("nome") or c.nome or "").strip() or doc
    c.uf = (dados.get("uf") or c.uf or "PR").upper()[:2]
    c.fazenda = dados.get("fazenda", c.fazenda) or None
    c.ambiente = 2 if str(dados.get("ambiente", c.ambiente or 1)) == "2" else 1
    if "ativo" in dados:
        c.ativo = bool(dados["ativo"])
    db.add(c)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=400, detail="Este CPF/CNPJ já está cadastrado")
    return _dict_contribuinte(c)


def _documento_valido(doc: str) -> bool:
    """Confere os dígitos verificadores do CPF/CNPJ."""
    if len(set(doc)) == 1:
        return False
    if len(doc) == 11:
        for n in (9, 10):
            soma = sum(int(doc[i]) * (n + 1 - i) for i in range(n))
            if (soma * 10 % 11) % 10 != int(doc[n]):
                return False
        return True
    pesos = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    for n in (12, 13):
        soma = sum(int(doc[i]) * pesos[i + 13 - n] for i in range(n))
        dv = 0 if soma % 11 < 2 else 11 - soma % 11
        if dv != int(doc[n]):
            return False
    return True


@router.post("/contribuintes/{cid}/certificado")
async def contribuinte_certificado(cid: int, arquivo: UploadFile = File(...), senha: str = Form(...),
                                   db: Session = Depends(get_db)):
    c = _contribuinte(db, cid)
    conteudo = await _ler(arquivo)
    return _executar(fin_sefaz.guardar_certificado, db, c, conteudo, senha)


@router.delete("/contribuintes/{cid}/certificado")
def contribuinte_tirar_certificado(cid: int, db: Session = Depends(get_db)):
    c = _contribuinte(db, cid)
    c.cert_pfx = c.cert_senha = c.cert_titular = None
    c.cert_validade = None
    db.commit()
    return {"ok": True}


@router.post("/contribuintes/{cid}/buscar")
def contribuinte_buscar(cid: int, db: Session = Depends(get_db)):
    return _executar(fin_sefaz.sincronizar, db, _contribuinte(db, cid))


@router.post("/notas/buscar-sefaz")
def buscar_todos(db: Session = Depends(get_db)):
    """Consulta todos os CPF/CNPJ que já podem (a SEFAZ limita a 1 consulta por hora)."""
    return fin_sefaz.sincronizar_todos(db)


# ---------------------------------------------------------------- extrato (OFX)

@router.get("/extrato")
def extrato(conta: str = "", db: Session = Depends(get_db)):
    return fin_extrato.listar(db, conta or None)


@router.post("/extrato")
async def extrato_importar(conta: str = Form(...), arquivo: UploadFile = File(...), db: Session = Depends(get_db)):
    return _executar(fin_extrato.importar, db, conta, await _ler(arquivo))


@router.get("/extrato/{mid}/candidatas")
def extrato_candidatas(mid: int, db: Session = Depends(get_db)):
    return _executar(fin_extrato.candidatas, db, mid)


@router.put("/extrato/{mid}")
def extrato_vincular(mid: int, dados: dict = Body(...), db: Session = Depends(get_db)):
    _executar(fin_extrato.vincular, db, mid, dados.get("parcela_id"), dados.get("ignorado"))
    return {"ok": True}
