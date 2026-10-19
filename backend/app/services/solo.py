"""Solo e insumos dos piquetes: análises, calagem (saturação por bases) e aplicações.

Calagem — método da saturação por bases (o mais usado em pastagem):
    SB  = Ca + Mg + K                        (cmolc/dm³)
    CTC = SB + (H+Al)                        (cmolc/dm³, a pH 7)
    V%  = SB ÷ CTC × 100
    NC (t/ha) = (V2 − V1) × CTC ÷ PRNT       (camada 0–20 cm)
V2 é a saturação desejada pra pastagem — quem define é o técnico (o app só sugere a faixa).
Recomendação de fósforo e potássio NÃO é calculada aqui: depende do manual regional.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from ..models import Piquete
from ..models_solo import AnaliseSolo, AplicacaoInsumo

TIPOS_INSUMO = {"calcario": "Calcário", "gesso": "Gesso", "adubo": "Adubo / fertilizante",
                "herbicida": "Herbicida", "semente": "Semente", "outro": "Outro"}
UNIDADES = {"kg/ha", "t/ha", "L/ha"}
CAMPOS_ANALISE = ("ph_cacl2", "mo", "p", "k", "ca", "mg", "al", "h_al", "argila")


class ErroSolo(ValueError):
    """Erro de regra de negócio — a mensagem é mostrada ao usuário como está."""


def _num(v, nome: str) -> float | None:
    if v in (None, ""):
        return None
    try:
        n = float(str(v).replace(",", "."))
    except ValueError:
        raise ErroSolo(f"{nome}: use um número.")
    if n < 0:
        raise ErroSolo(f"{nome}: não pode ser negativo.")
    return n


def _data(v) -> date:
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)) if v else date.today()
    except ValueError:
        raise ErroSolo("Data inválida.")


def calculos(a: AnaliseSolo) -> dict:
    """SB, CTC e V% da análise (quando os dados permitem)."""
    sb = None
    if None not in (a.ca, a.mg, a.k):
        sb = round(a.ca + a.mg + a.k, 2)
    ctc = round(sb + a.h_al, 2) if sb is not None and a.h_al is not None else None
    v = round(sb / ctc * 100, 1) if sb is not None and ctc else None
    m = round(a.al / (sb + a.al) * 100, 1) if a.al is not None and sb is not None and (sb + a.al) else None
    return {"sb": sb, "ctc": ctc, "v_pct": v, "m_pct": m}


def necessidade_calagem(v1: float, ctc: float, v2: float, prnt: float) -> float:
    """t/ha de calcário pra subir a saturação de V1 para V2 (0 se já está acima)."""
    if not prnt or prnt <= 0:
        raise ErroSolo("Informe o PRNT do calcário (%).")
    if not 0 < v2 <= 100:
        raise ErroSolo("A saturação desejada (V2) deve ficar entre 1 e 100%.")
    return round(max(0.0, (v2 - v1) * ctc / prnt), 2)


def _analise_dict(a: AnaliseSolo) -> dict:
    d = {"id": a.id, "piquete_id": a.piquete_id, "data": a.data.isoformat(),
         "laboratorio": a.laboratorio, "profundidade": a.profundidade, "observacao": a.observacao}
    d.update({c: getattr(a, c) for c in CAMPOS_ANALISE})
    d.update(calculos(a))
    return d


def salvar_analise(db: Session, piquete_id: int, dados: dict, analise_id: int | None = None) -> dict:
    p = db.get(Piquete, piquete_id)
    if p is None:
        raise ErroSolo("Piquete não encontrado.")
    a = db.get(AnaliseSolo, analise_id) if analise_id else AnaliseSolo(piquete_id=piquete_id)
    if a is None:
        raise ErroSolo("Análise não encontrada.")
    a.data = _data(dados.get("data"))
    a.laboratorio = (dados.get("laboratorio") or "").strip()[:80] or None
    a.profundidade = (dados.get("profundidade") or "").strip()[:20] or "0-20 cm"
    a.observacao = (dados.get("observacao") or "").strip() or None
    rotulos = {"ph_cacl2": "pH", "mo": "MO", "p": "P", "k": "K", "ca": "Ca", "mg": "Mg",
               "al": "Al", "h_al": "H+Al", "argila": "Argila"}
    for c in CAMPOS_ANALISE:
        setattr(a, c, _num(dados.get(c), rotulos[c]))
    if a.ph_cacl2 is not None and not 2 <= a.ph_cacl2 <= 9:
        raise ErroSolo("pH fora do razoável (2 a 9).")
    if a.argila is not None and a.argila > 100:
        raise ErroSolo("Argila em %, até 100.")
    if analise_id is None:
        db.add(a)
    db.commit()
    return _analise_dict(a)


def apagar_analise(db: Session, analise_id: int) -> dict:
    a = db.get(AnaliseSolo, analise_id)
    if a is None:
        raise ErroSolo("Análise não encontrada.")
    db.delete(a)
    db.commit()
    return {"ok": True}


def _aplicacao_dict(x: AplicacaoInsumo) -> dict:
    return {"id": x.id, "piquete_id": x.piquete_id, "data": x.data.isoformat(), "tipo": x.tipo,
            "tipo_nome": TIPOS_INSUMO.get(x.tipo, x.tipo), "produto": x.produto, "dose": x.dose,
            "unidade": x.unidade, "area_ha": x.area_ha,
            "quantidade_total": round(x.dose * x.area_ha, 2), "custo_total": x.custo_total,
            "custo_ha": round(x.custo_total / x.area_ha, 2) if x.custo_total and x.area_ha else None,
            "observacao": x.observacao, "usuario": x.usuario_nome}


def registrar_aplicacao(db: Session, piquete_id: int, dados: dict, usuario: str | None = None) -> dict:
    p = db.get(Piquete, piquete_id)
    if p is None:
        raise ErroSolo("Piquete não encontrado.")
    tipo = dados.get("tipo") or "outro"
    if tipo not in TIPOS_INSUMO:
        raise ErroSolo("Tipo de insumo inválido.")
    produto = (dados.get("produto") or "").strip()[:80]
    if not produto:
        raise ErroSolo("Informe o produto.")
    dose = _num(dados.get("dose"), "Dose")
    if not dose:
        raise ErroSolo("Informe a dose por hectare.")
    unidade = dados.get("unidade") or "kg/ha"
    if unidade not in UNIDADES:
        raise ErroSolo("Unidade inválida.")
    area = _num(dados.get("area_ha"), "Área") or p.hectares
    if not area:
        raise ErroSolo("Informe a área aplicada (o piquete está sem hectares).")
    x = AplicacaoInsumo(piquete_id=piquete_id, data=_data(dados.get("data")), tipo=tipo, produto=produto,
                        dose=dose, unidade=unidade, area_ha=area, custo_total=_num(dados.get("custo_total"), "Custo"),
                        observacao=(dados.get("observacao") or "").strip() or None, usuario_nome=usuario)
    db.add(x)
    db.commit()
    return _aplicacao_dict(x)


def apagar_aplicacao(db: Session, aplicacao_id: int) -> dict:
    x = db.get(AplicacaoInsumo, aplicacao_id)
    if x is None:
        raise ErroSolo("Aplicação não encontrada.")
    db.delete(x)
    db.commit()
    return {"ok": True}


def solo_do_piquete(db: Session, piquete_id: int) -> dict:
    p = db.get(Piquete, piquete_id)
    if p is None:
        raise ErroSolo("Piquete não encontrado.")
    analises = (db.query(AnaliseSolo).filter(AnaliseSolo.piquete_id == piquete_id)
                .order_by(AnaliseSolo.data.desc(), AnaliseSolo.id.desc()).all())
    aplicacoes = (db.query(AplicacaoInsumo).filter(AplicacaoInsumo.piquete_id == piquete_id)
                  .order_by(AplicacaoInsumo.data.desc(), AplicacaoInsumo.id.desc()).all())
    return {
        "piquete": {"id": p.id, "nome": p.nome, "hectares": p.hectares, "capim": p.capim},
        "analises": [_analise_dict(a) for a in analises],
        "aplicacoes": [_aplicacao_dict(x) for x in aplicacoes],
        "custo_total": round(sum(x.custo_total or 0 for x in aplicacoes), 2),
    }


def resumo_solo(db: Session) -> list[dict]:
    """Última análise de cada piquete ativo (pra tabela geral)."""
    ultimas: dict[int, AnaliseSolo] = {}
    for a in db.query(AnaliseSolo).order_by(AnaliseSolo.data, AnaliseSolo.id):
        ultimas[a.piquete_id] = a
    saida = []
    for p in db.query(Piquete).filter(Piquete.ativo.is_(True)).order_by(Piquete.nome):
        a = ultimas.get(p.id)
        linha = {"piquete_id": p.id, "piquete": p.nome, "hectares": p.hectares, "capim": p.capim,
                 "data": a.data.isoformat() if a else None}
        if a:
            linha.update({"ph_cacl2": a.ph_cacl2, "p": a.p, "k": a.k, "mo": a.mo, **calculos(a)})
        saida.append(linha)
    return saida
