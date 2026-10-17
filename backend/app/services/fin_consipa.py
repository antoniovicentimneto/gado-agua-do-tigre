"""Importa os lançamentos da planilha CONSIPA (aba CentralReal) para o Financeiro.

Na CONSIPA cada PARCELA é uma linha solta. Aqui as linhas da mesma compra (mesma data,
classificação, fornecedor, descrição, nota e valor) viram UM lançamento com N parcelas.
Decisões aplicadas (16/10/2026): "Pecuária de leite" = fazenda Castro; agricultura -> Sede;
sem categoria vai pra fila de revisão; 3 categorias no galho errado são corrigidas.
Pode rodar de novo: o que já foi importado (chave_origem) é pulado, nada é apagado."""
from __future__ import annotations

import hashlib
import io
import warnings
from collections import defaultdict
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models_financeiro import FinFornecedor, FinLancamento, FinParcela, FinPlano
from .fin_lancamentos import normalizar
from .fin_plano import SETORES_CONSIPA, ErroFinanceiro, garantir_cadastros, limpar_nome

ABA = "CentralReal"
# Categoria cujo código é de outra central -> central certa (os 3 casos achados na planilha).
CORRECOES_GRUPO = {
    "1.04.02": "1.04. MATERIAIS DE CONSUMO, OPERAÇÃO E MANUTENÇÃO",
    "1.13.04": "1.13. CAPTAÇÃO DE CRÉDITO",
    "2.02.04": "2.02. VENDA DE ANIMAIS",
}
# Colunas digitadas da tabela tblCentralReal (a partir da coluna B).
COLUNAS = ["data", "data_fluxo", "status", "setor", "es", "central", "categoria", "item", "subitem",
           "nf", "fornecedor", "descricao", "n_parcelas", "qtde", "valor_unit", "arroba", "unidade",
           "rendimento", "desconto", "obs", "conta", "fazenda", "valor"]


def _vazio(v):
    return v is None or (isinstance(v, str) and v.strip() in ("", "0")) or v == 0


def _txt(v):
    return None if _vazio(v) else str(v).strip()


def _dt(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return None


def ler_planilha(conteudo: bytes) -> list[dict]:
    """Lê a aba CentralReal (só as colunas digitadas) — modo leitura rápida."""
    import openpyxl

    warnings.filterwarnings("ignore", module="openpyxl")
    try:
        wb = openpyxl.load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
    except Exception:
        raise ErroFinanceiro("Não consegui abrir o arquivo. Envie a planilha CONSIPA (.xlsm ou .xlsx).")
    if ABA not in wb.sheetnames:
        raise ErroFinanceiro("A planilha não tem a aba CentralReal — é mesmo a CONSIPA?")
    ws = wb[ABA]
    linhas = []
    cabecalho_ok = False
    for r in ws.iter_rows(min_row=1, min_col=2, max_col=24, values_only=True):
        if not cabecalho_ok:
            cabecalho_ok = str(r[0] or "").strip().upper().startswith("DATA CONT")
            continue
        if r[0] is None and r[4] is None:
            continue
        linhas.append(dict(zip(COLUNAS, r)))
    wb.close()
    if not cabecalho_ok:
        raise ErroFinanceiro("Não achei o cabeçalho da tabela na aba CentralReal")
    return linhas


def importar(db: Session, conteudo: bytes, usuario: str) -> dict:
    garantir_cadastros(db)
    linhas = ler_planilha(conteudo)

    # Agrupa as parcelas da mesma compra.
    grupos: dict[tuple, list[dict]] = defaultdict(list)
    ignoradas = 0
    for r in linhas:
        es = str(r["es"] or "").strip().upper()
        if es not in ("1. DESPESA", "2. RECEITA") or not _dt(r["data"]) or _vazio(r["valor"]):
            ignoradas += 1  # inventário, configurações, linha sem valor
            continue
        chave = tuple(str(r[c]) for c in ("data", "setor", "es", "central", "categoria", "item", "nf",
                                          "fornecedor", "descricao", "n_parcelas", "qtde", "valor_unit", "conta"))
        grupos[chave].append(r)

    ja_importadas = set(db.scalars(select(FinLancamento.chave_origem).where(FinLancamento.origem == "consipa")))
    fornecedores = {}
    for f in db.scalars(select(FinFornecedor)):
        for n in [f.nome] + (f.apelidos or "").split(";"):
            if n.strip():
                fornecedores.setdefault(normalizar(n), f)
    plano = {(p.tipo, p.setor, p.grupo, p.categoria) for p in db.scalars(select(FinPlano))}

    criados = pulados = revisar = parcelas_total = 0
    for chave, rows in grupos.items():
        rows.sort(key=lambda x: _dt(x["data_fluxo"]) or _dt(x["data"]))
        n = max(1, int(float(rows[0]["n_parcelas"] or 1)))
        # Duas compras idênticas no mesmo dia: quebra em blocos do tamanho do parcelamento.
        for bloco_i in range(0, len(rows), n):
            bloco = rows[bloco_i:bloco_i + n]
            origem = hashlib.sha1(repr((chave, bloco_i)).encode()).hexdigest()
            if origem in ja_importadas:
                pulados += 1
                continue
            lanc = _montar(bloco, usuario, origem, fornecedores, plano, db)
            db.add(lanc)
            criados += 1
            parcelas_total += len(lanc.parcelas)
            revisar += lanc.revisar
    db.flush()
    _aprender_padroes(db)
    db.commit()
    return {"lancamentos": criados, "parcelas": parcelas_total, "ja_existiam": pulados,
            "a_revisar": revisar, "linhas_ignoradas": ignoradas}


def _montar(bloco, usuario, origem, fornecedores, plano, db) -> FinLancamento:
    r = bloco[0]
    tipo = "despesa" if str(r["es"]).strip().upper().startswith("1") else "receita"
    setor_original = str(r["setor"] or "").strip().upper()
    setor = SETORES_CONSIPA.get(setor_original, (r["setor"] or "").strip().title() or None)
    obs = _txt(r["obs"])
    if obs and obs.replace(".", "").isdigit():
        obs = None  # a CONSIPA guardava número solto aqui (lixo do formulário)
    fazenda = "Castro" if setor_original == "PECUÁRIA DE LEITE" or "castro" in normalizar(obs) else "Água do Tigre"

    motivos = []
    central, categoria = _txt(r["central"]), _txt(r["categoria"])
    cod_cat = limpar_nome(categoria)[0] if categoria else None
    cod_cen = limpar_nome(central)[0] if central else None
    if cod_cat in CORRECOES_GRUPO and cod_cen and not cod_cat.startswith(cod_cen):
        central = CORRECOES_GRUPO[cod_cat]
        motivos.append("Categoria estava em outro grupo (corrigido na importação)")
    grupo = limpar_nome(central)[1] if central else None
    cat = limpar_nome(categoria)[1] if categoria else None
    if not cat:
        motivos.append("Sem categoria")
    if setor_original == "AGRICULTURA" and tipo == "despesa":
        motivos.append("Era 'Agricultura' na CONSIPA")
    if setor_original == "CONFIGURAÇÕES":
        motivos.append("Estava em 'Configurações' na CONSIPA")
    if cat and (tipo, setor, grupo, cat) not in plano:
        db.add(FinPlano(tipo=tipo, setor=setor, grupo=grupo, categoria=cat,
                        codigo=limpar_nome(categoria)[0] or limpar_nome(central)[0]))
        plano.add((tipo, setor, grupo, cat))

    nome_forn = _txt(r["fornecedor"])
    forn = None
    if nome_forn:
        forn = fornecedores.get(normalizar(nome_forn))
        if forn is None:
            forn = FinFornecedor(nome=nome_forn)
            db.add(forn)
            fornecedores[normalizar(nome_forn)] = forn

    item = _txt(r["item"])
    descricao = _txt(r["descricao"])
    if item and item not in (descricao or ""):
        descricao = f"{descricao} · {limpar_nome(item)[1]}" if descricao else limpar_nome(item)[1]

    lanc = FinLancamento(
        tipo=tipo, data=_dt(r["data"]), fazenda=fazenda, setor=setor, grupo=grupo, categoria=cat,
        fornecedor_nome=forn.nome if forn else None, descricao=descricao, conta=_txt(r["conta"]),
        nf_numero=_txt(r["nf"]), observacao=obs, origem="consipa", chave_origem=origem,
        criado_por=f"{usuario} (importação CONSIPA)", revisar=bool(motivos),
        revisar_motivo="; ".join(motivos) or None,
    )
    lanc.fornecedor = forn  # ligado abaixo (fornecedor pode ser novo, ainda sem id)
    for i, p in enumerate(bloco, start=1):
        lanc.parcelas.append(FinParcela(numero=i, vencimento=_dt(p["data_fluxo"]) or lanc.data,
                                        valor=round(float(p["valor"]), 2)))
    lanc.valor_total = round(sum(p.valor for p in lanc.parcelas), 2)
    return lanc


def _aprender_padroes(db: Session) -> None:
    """Cada fornecedor importado ganha como sugestão a classificação mais recente."""
    ult = {}
    q = (select(FinLancamento)
         .where(FinLancamento.categoria.is_not(None), FinLancamento.fornecedor_id.is_not(None))
         .order_by(FinLancamento.data))
    for lc in db.scalars(q):
        ult[lc.fornecedor_id] = lc
    for fid, lc in ult.items():
        f = db.get(FinFornecedor, fid)
        if f and not f.pad_categoria:
            f.pad_tipo, f.pad_fazenda, f.pad_setor = lc.tipo, lc.fazenda, lc.setor
            f.pad_grupo, f.pad_categoria, f.pad_conta = lc.grupo, lc.categoria, lc.conta
