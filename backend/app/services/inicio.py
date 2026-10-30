"""Tela inicial: os números que dizem como a fazenda está e o que pede atenção.

Escolhas feitas olhando os dados reais (estudo em docs/dashboard_inicio.md):
- GMD do rebanho = kg ganhos ÷ animal-dias, dia a dia entre pesagens. Não é média de
  médias: animal pesado há pouco tempo não pesa igual a quem tem o ano inteiro.
- Comparação sempre com o MESMO período do ano anterior: o ganho varia muito com a época.
- Financeiro por setor: o resultado da fazenda inteira mistura arrendamento e gastos
  pessoais; quem mede a pecuária é o setor Pecuária, com a compra de gado à parte.
- Tudo em poucas consultas: o banco fica em São Paulo e o servidor nos EUA.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    Animal,
    AnimalLote,
    Compra,
    Lote,
    LotePiquete,
    Pesagem,
    Piquete,
    SessaoPesagem,
    StatusAnimal,
    StatusSessao,
    TipoSessao,
    Venda,
    cor_do_lote,
)
from ..models_campo import OcorrenciaSanitaria
from ..models_financeiro import FinFechamento, FinLancamento, FinNota, FinParcela
from . import peso_estimado as pe
from .alertas import carregar_limites
from .fin_lancamentos import parcela_realizada
from .fin_resultado import SEM
from .pastos import KG_POR_UA
from .venda import KG_POR_ARROBA, rendimento_padrao

# Intervalos entre pesagens que não medem ganho: pesagem repetida ou erro de digitação.
INTERVALO_MIN_DIAS = 7
GMD_MIN, GMD_MAX = -1.5, 3.0
# Mês com pouca base (poucos animais pesados) não entra no gráfico: oscila demais.
ANIMAL_DIAS_MIN_MES = 300
# Preço de referência pra estimar o valor do rebanho: vendas dos últimos 6 meses.
DIAS_PRECO_REFERENCIA = 180

SETOR_PECUARIA = "Pecuária"
GRUPO_COMPRA = "Aquisição de rebanho"
# Na pecuária, o que não é custo de produzir: entra no saldo, mas não no custo da arroba.
GRUPOS_FORA_DO_CUSTEIO = {"Investimentos", "Captação de crédito", "Retirada de lucro"}

SEM_TIPO = "Sem classificação"
FAIXAS_PESAGEM = ("ate_60", "ate_120", "mais_120", "sem_peso")


def _periodo(inicio: date | None, fim: date | None, hoje: date) -> tuple[date, date]:
    """Padrão: últimos 12 meses. O fim nunca passa de hoje (safra em andamento)."""
    fim = min(fim or hoje, hoje)
    return inicio or _um_ano_antes(fim) + timedelta(days=1), fim


def _um_ano_antes(d: date) -> date:
    try:
        return d.replace(year=d.year - 1)
    except ValueError:  # 29 de fevereiro
        return d.replace(year=d.year - 1, day=28)


def _meses_do_periodo(inicio: date, fim: date) -> list[str]:
    meses, ano, mes = [], inicio.year, inicio.month
    while (ano, mes) <= (fim.year, fim.month):
        meses.append(f"{ano}-{mes:02d}")
        ano, mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    return meses


def _fim_do_mes(ano: int, mes: int) -> date:
    return (date(ano + 1, 1, 1) if mes == 12 else date(ano, mes + 1, 1)) - timedelta(days=1)


# ---------------------------------------------------------------- Rebanho hoje

def _animais_ativos(db: Session, hoje: date) -> tuple[list[dict], dict]:
    """Cada animal ativo com lote, último peso e peso estimado até hoje (4 consultas).
    Devolve também o resumo de cada lote."""
    linhas = db.execute(
        select(Animal.id, Animal.brinco, Animal.tipo, AnimalLote.lote_id)
        .outerjoin(AnimalLote, (AnimalLote.animal_id == Animal.id) & AnimalLote.data_fim.is_(None))
        .where(Animal.status == StatusAnimal.ATIVO)
    ).all()
    pesos = pe.pesagens_por_animal(db)
    referencia = pe.carregar_referencia(db)
    nomes = dict(db.execute(select(Lote.id, Lote.nome)).all())

    vistos: set[int] = set()
    animais = []
    por_lote: dict[int | None, list[int]] = defaultdict(list)
    for animal_id, brinco, tipo, lote_id in linhas:
        if animal_id in vistos:  # vínculo aberto duplicado: conta o animal uma vez só
            continue
        vistos.add(animal_id)
        por_lote[lote_id].append(animal_id)
        animais.append({"id": animal_id, "brinco": brinco, "tipo": (tipo or "").strip() or SEM_TIPO,
                        "lote_id": lote_id, "lote": nomes.get(lote_id)})

    # O GMD usado na projeção é o do lote; sem ele, o de referência da época.
    resumos = {lote_id: pe.resumo_grupo(ids, pesos, hoje, referencia) for lote_id, ids in por_lote.items()}
    for a in animais:
        r = resumos[a["lote_id"]]
        datas = sorted(d for d in pesos.get(a["id"], {}) if d <= hoje)
        if not datas:
            a.update(ultimo_peso=None, data_peso=None, dias_sem_pesar=None, peso=None)
            continue
        ultimo = pesos[a["id"]][datas[-1]]
        dias = (hoje - datas[-1]).days
        a.update(ultimo_peso=ultimo, data_peso=datas[-1].isoformat(), dias_sem_pesar=dias,
                 peso=ultimo + (r["gmd_usado"] or 0) * min(dias, pe.LIMITE_DIAS))
    return animais, resumos


def _faixa_pesagem(dias: int | None) -> str:
    if dias is None:
        return "sem_peso"
    if dias <= 60:
        return "ate_60"
    return "ate_120" if dias <= pe.LIMITE_DIAS else "mais_120"


def animais_filtrados(db: Session, hoje: date, tipo: str | None = None, faixa: str | None = None,
                      lote: int | None = None) -> list[dict]:
    """A lista que está por trás de um número da tela (categoria, lote ou tempo sem pesar)."""
    animais, _ = _animais_ativos(db, hoje)
    saida = [a for a in animais
             if (not tipo or a["tipo"] == tipo) and (not lote or a["lote_id"] == lote)
             and (not faixa or _faixa_pesagem(a["dias_sem_pesar"]) == faixa)]
    for a in saida:
        a["peso"] = round(a["peso"], 1) if a["peso"] else None
        del a["lote_id"]
    return saida


def _preco_arroba(db: Session, inicio: date, fim: date) -> float | None:
    """Preço médio da @ nas vendas do período, ponderado pelas arrobas de cada animal."""
    linhas = db.execute(
        select(Venda.preco_arroba, Venda.peso_carcaca, Venda.peso, Venda.rendimento)
        .where(Venda.data >= inicio, Venda.data <= fim, Venda.preco_arroba.is_not(None),
               Venda.preco_arroba > 0, Venda.pendente.is_(False))
    ).all()
    if not linhas:
        return None
    soma = peso_total = 0.0
    for preco, carcaca, peso, rendimento in linhas:
        kg = carcaca or ((peso or 0) * (rendimento or 0)) or 1.0  # sem peso: conta como 1
        soma += preco * kg
        peso_total += kg
    return round(soma / peso_total, 2)


def rebanho(db: Session, hoje: date, dono: bool) -> dict:
    """Foto de hoje: quanto gado, onde, com que peso e o que pede atenção."""
    limites = carregar_limites(db)
    animais, resumos = _animais_ativos(db, hoje)

    categorias: dict[str, dict] = defaultdict(lambda: {"cabecas": 0, "com_peso": 0, "peso": 0.0, "arrobas": 0.0})
    faixas = dict.fromkeys(FAIXAS_PESAGEM, 0)
    for a in animais:
        c = categorias[a["tipo"]]
        c["cabecas"] += 1
        faixas[_faixa_pesagem(a["dias_sem_pesar"])] += 1
        if a["peso"]:
            c["com_peso"] += 1
            c["peso"] += a["peso"]
            c["arrobas"] += a["peso"] * rendimento_padrao(a["tipo"]) / KG_POR_ARROBA

    peso_total = sum(c["peso"] for c in categorias.values())
    arrobas = sum(c["arrobas"] for c in categorias.values())
    total = len(animais)
    em_dia = faixas["ate_60"] + faixas["ate_120"]

    # Lotes com piquete atual (a última ocupação aberta de cada lote vale).
    ocupacoes = db.execute(
        select(LotePiquete.lote_id, Piquete.nome, Piquete.hectares)
        .join(Piquete, Piquete.id == LotePiquete.piquete_id)
        .where(LotePiquete.data_saida.is_(None))
        .order_by(LotePiquete.data_entrada)
    ).all()
    piquete_do_lote = {lote_id: nome for lote_id, nome, _ in ocupacoes}
    ids_lotes = [i for i in resumos if i is not None]
    lotes_db = db.query(Lote).filter(Lote.id.in_(ids_lotes)).all() if ids_lotes else []
    lotes = []
    for lote in lotes_db:
        r = resumos[lote.id]
        lotes.append({
            "id": lote.id, "nome": lote.nome, "cor": cor_do_lote(lote), "icone": lote.icone,
            "piquete": piquete_do_lote.get(lote.id),
            "cabecas": r["cabecas"],
            "peso_medio": round(r["peso"] / r["com_peso"], 1) if r["com_peso"] else None,
            "ua": round(r["peso"] / KG_POR_UA, 1),
            "ugmd": r["gmd_lote"],
            "dias_sem_pesar": r["dias_max"] if r["com_peso"] else None,
            "velha": r["velha"],
        })
    lotes.sort(key=lambda x: -x["cabecas"])

    # Lotação só faz sentido com o gado quase todo no mapa; senão daria um número baixo falso.
    cab_com_piquete = sum(x["cabecas"] for x in lotes if x["piquete"])
    ua_com_piquete = sum(x["ua"] for x in lotes if x["piquete"])
    hectares = db.scalar(select(func.sum(Piquete.hectares)).where(Piquete.ativo.is_(True))) or 0
    cobertura = round(cab_com_piquete / total * 100) if total else 0

    saida = {
        "hoje": hoje.isoformat(),
        "cabecas": total,
        "peso_total": round(peso_total),
        "arrobas": round(arrobas),
        "ua": round(peso_total / KG_POR_UA, 1),
        "categorias": sorted(
            ({"tipo": t, "cabecas": c["cabecas"],
              "peso_medio": round(c["peso"] / c["com_peso"], 1) if c["com_peso"] else None,
              "ua": round(c["peso"] / KG_POR_UA, 1)} for t, c in categorias.items()),
            key=lambda x: -x["cabecas"]),
        "pesagem": {**faixas, "em_dia_pct": round(em_dia / total * 100) if total else None,
                    "limite_dias": pe.LIMITE_DIAS, "meta_pct": limites["pesados_min_pct"]},
        "lotes": lotes,
        "lotacao": {"ua_ha": round(ua_com_piquete / hectares, 2) if hectares and cobertura >= 80 else None,
                    "cobertura_pct": cobertura, "hectares": round(hectares, 1),
                    "lotes_sem_piquete": sum(1 for x in lotes if not x["piquete"])},
        "sessoes_abertas": db.scalar(select(func.count()).select_from(SessaoPesagem)
                                     .where(SessaoPesagem.status == StatusSessao.ABERTA)) or 0,
        "em_carencia": db.scalar(
            select(func.count(func.distinct(OcorrenciaSanitaria.animal_id)))
            .join(Animal, Animal.id == OcorrenciaSanitaria.animal_id)
            .where(OcorrenciaSanitaria.carencia_ate >= hoje, Animal.status == StatusAnimal.ATIVO)) or 0,
    }
    if dono:
        preco = _preco_arroba(db, hoje - timedelta(days=DIAS_PRECO_REFERENCIA), hoje)
        saida["preco_arroba_ref"] = preco
        saida["valor_rebanho"] = round(arrobas * preco) if preco else None
    return saida


# ---------------------------------------------------------------- Produção

def _intervalos(db: Session) -> tuple[list[tuple], int]:
    """(início, fim, ganho por dia, kg de carcaça por kg vivo) entre pesagens seguidas de
    TODOS os animais: vendido também produziu enquanto esteve aqui. Devolve também quantos
    intervalos foram descartados (pesagem repetida ou ganho impossível)."""
    linhas = db.execute(
        select(Pesagem.animal_id, Pesagem.data, Pesagem.peso, Animal.tipo)
        .join(Animal, Animal.id == Pesagem.animal_id)
    ).all()
    por_animal: dict[int, dict] = defaultdict(dict)
    tipos: dict[int, str | None] = {}
    for animal_id, dia, peso, tipo in linhas:
        por_animal[animal_id][dia] = max(peso, por_animal[animal_id].get(dia, 0))
        tipos[animal_id] = tipo
    saida, descartados = [], 0
    for animal_id, dias in por_animal.items():
        rendimento = rendimento_padrao(tipos[animal_id])
        ordem = sorted(dias)
        for d1, d2 in zip(ordem, ordem[1:]):
            n = (d2 - d1).days
            g = (dias[d2] - dias[d1]) / n
            if n < INTERVALO_MIN_DIAS or not GMD_MIN <= g <= GMD_MAX:
                descartados += 1
                continue
            saida.append((d1, d2, g, rendimento))
    return saida, descartados


def _ganho(intervalos: list[tuple], inicio: date, fim: date) -> dict:
    """Soma o ganho dia a dia dentro do período (intervalo pela metade conta pela metade)."""
    antes = inicio - timedelta(days=1)
    kg = arrobas = 0.0
    animal_dias = 0
    for d1, d2, g, rendimento in intervalos:
        dias = (min(d2, fim) - max(d1, antes)).days
        if dias > 0:
            kg += g * dias
            arrobas += g * dias * rendimento / KG_POR_ARROBA
            animal_dias += dias
    return {"kg": round(kg), "arrobas": round(arrobas), "animal_dias": animal_dias,
            "gmd": round(kg / animal_dias, 3) if animal_dias else None}


def _serie_gmd(intervalos: list[tuple], hoje: date) -> list[dict]:
    """GMD mês a mês dos últimos 12 meses, ao lado do mesmo mês do ano anterior."""
    def gmd_mes(ano: int, mes: int) -> float | None:
        r = _ganho(intervalos, date(ano, mes, 1), min(_fim_do_mes(ano, mes), hoje))
        return r["gmd"] if r["animal_dias"] >= ANIMAL_DIAS_MIN_MES else None

    inicio_serie = date(hoje.year - 1, hoje.month, 1) + timedelta(days=32)
    serie = []
    for m in _meses_do_periodo(inicio_serie.replace(day=1), hoje):
        ano, mes = int(m[:4]), int(m[5:])
        serie.append({"mes": m, "gmd": gmd_mes(ano, mes), "gmd_ano_anterior": gmd_mes(ano - 1, mes)})
    return serie


def _contar_saidas(db: Session, inicio: date, fim: date) -> dict[str, int]:
    linhas = db.execute(
        select(Animal.status, func.count())
        .where(Animal.data_evento >= inicio, Animal.data_evento <= fim, Animal.status != StatusAnimal.ATIVO)
        .group_by(Animal.status)
    ).all()
    return {s.value: n for s, n in linhas}


def producao(db: Session, hoje: date, inicio: date | None, fim: date | None, dono: bool) -> dict:
    """Quanto o gado ganhou no período, comparado com o mesmo período do ano anterior."""
    inicio, fim = _periodo(inicio, fim, hoje)
    ant_ini, ant_fim = _um_ano_antes(inicio), _um_ano_antes(fim)
    intervalos, descartados = _intervalos(db)
    atual, anterior = _ganho(intervalos, inicio, fim), _ganho(intervalos, ant_ini, ant_fim)
    saidas, saidas_ant = _contar_saidas(db, inicio, fim), _contar_saidas(db, ant_ini, ant_fim)

    def mortalidade(contagem: dict, r: dict, dias: int) -> float | None:
        # Mortes e sumiços ÷ rebanho médio (animal-dias ÷ dias do período).
        rebanho_medio = r["animal_dias"] / dias if dias else 0
        if rebanho_medio < 1:
            return None
        return round((contagem.get("morto", 0) + contagem.get("perdido", 0)) / rebanho_medio * 100, 1)

    dias = (fim - inicio).days + 1
    nascimentos = db.scalar(select(func.count()).select_from(Animal)
                            .where(Animal.nascimento >= inicio, Animal.nascimento <= fim)) or 0
    saida = {
        "inicio": inicio.isoformat(), "fim": fim.isoformat(),
        "anterior": {"inicio": ant_ini.isoformat(), "fim": ant_fim.isoformat(), **anterior,
                     "mortalidade_pct": mortalidade(saidas_ant, anterior, dias)},
        **atual,
        "rebanho_medio": round(atual["animal_dias"] / dias) if dias else 0,
        "mortalidade_pct": mortalidade(saidas, atual, dias),
        "mortalidade_limite": carregar_limites(db)["mortalidade_max_pct"],
        "descartados": descartados,
        "serie": _serie_gmd(intervalos, hoje),
        "movimento": {"nascimentos": nascimentos, "mortos": saidas.get("morto", 0),
                      "perdidos": saidas.get("perdido", 0)},
    }
    if dono:  # compra e venda são informação só do dono
        saida["movimento"]["vendidos"] = saidas.get("vendido", 0)
        saida["movimento"]["comprados"] = db.scalar(
            select(func.count()).select_from(Compra).where(Compra.data >= inicio, Compra.data <= fim)) or 0
        saida["preco_arroba"] = _preco_arroba(db, inicio, fim)
    return saida


# ---------------------------------------------------------------- Financeiro

def financeiro(db: Session, hoje: date, inicio: date | None, fim: date | None) -> dict:
    """Só o que já aconteceu (mesma regra da aba Resultado: venceu = realizado), por setor."""
    inicio, fim = _periodo(inicio, fim, hoje)
    ant_ini, ant_fim = _um_ano_antes(inicio), _um_ano_antes(fim)
    em_30_dias = hoje + timedelta(days=30)
    linhas = db.execute(
        select(FinLancamento.tipo, FinLancamento.setor, FinLancamento.grupo,
               FinParcela.vencimento, FinParcela.pago, func.sum(FinParcela.valor))
        .join(FinParcela, FinParcela.lancamento_id == FinLancamento.id)
        .where(FinLancamento.excluido.is_(False), FinParcela.vencimento >= ant_ini,
               FinParcela.vencimento <= max(em_30_dias, fim))
        .group_by(FinLancamento.tipo, FinLancamento.setor, FinLancamento.grupo,
                  FinParcela.vencimento, FinParcela.pago)
    ).all()

    def vazio() -> dict:
        return {"receita": 0.0, "custeio": 0.0, "compra": 0.0, "investimentos": 0.0}

    atual, anterior = vazio(), vazio()
    setores: dict[str, dict] = defaultdict(lambda: {"receita": 0.0, "despesa": 0.0})
    meses = {m: vazio() for m in _meses_do_periodo(inicio, fim)}
    a_pagar = a_receber = a_confirmar_valor = 0.0
    a_confirmar = 0

    def somar(destino: dict, tipo: str, grupo: str | None, valor: float) -> None:
        if tipo == "receita":
            destino["receita"] += valor
        elif grupo == GRUPO_COMPRA:
            destino["compra"] += valor
        elif grupo in GRUPOS_FORA_DO_CUSTEIO:
            destino["investimentos"] += valor
        else:
            destino["custeio"] += valor

    for tipo, setor, grupo, vencimento, pago, valor in linhas:
        linha_parcela = _Parcela(pago, vencimento)
        realizado = parcela_realizada(linha_parcela, hoje)
        if realizado and inicio <= vencimento <= fim:
            setores[setor or SEM]["receita" if tipo == "receita" else "despesa"] += valor
            if setor == SETOR_PECUARIA:
                somar(atual, tipo, grupo, valor)
                somar(meses[vencimento.strftime("%Y-%m")], tipo, grupo, valor)
        elif realizado and ant_ini <= vencimento <= ant_fim and setor == SETOR_PECUARIA:
            somar(anterior, tipo, grupo, valor)
        if not realizado and hoje < vencimento <= em_30_dias:
            if tipo == "receita":
                a_receber += valor
            else:
                a_pagar += valor
        if pago is False and vencimento <= hoje:
            a_confirmar += 1
            a_confirmar_valor += valor

    def fechar(v: dict) -> dict:
        saldo = v["receita"] - v["custeio"] - v["compra"] - v["investimentos"]
        return {**{k: round(x, 2) for k, x in v.items()}, "saldo": round(saldo, 2)}

    # Custo da @ produzida: custeio da pecuária ÷ arrobas que o gado ganhou no período.
    intervalos, _ = _intervalos(db)
    ganho, ganho_ant = _ganho(intervalos, inicio, fim), _ganho(intervalos, ant_ini, ant_fim)
    custo_arroba = round(atual["custeio"] / ganho["arrobas"], 2) if ganho["arrobas"] > 0 else None
    custo_ant = round(anterior["custeio"] / ganho_ant["arrobas"], 2) if ganho_ant["arrobas"] > 0 else None
    preco = _preco_arroba(db, inicio, fim)

    return {
        "inicio": inicio.isoformat(), "fim": fim.isoformat(),
        "pecuaria": fechar(atual),
        "pecuaria_anterior": fechar(anterior),
        "arrobas": ganho["arrobas"],
        "custo_arroba": custo_arroba,
        "custo_arroba_anterior": custo_ant,
        "preco_arroba": preco,
        "margem_arroba": round(preco - custo_arroba, 2) if preco and custo_arroba else None,
        "meses": [{"mes": m, **{k: round(x, 2) for k, x in v.items()}} for m, v in meses.items()],
        "setores": sorted(
            ({"setor": s, "receita": round(v["receita"], 2), "despesa": round(v["despesa"], 2),
              "saldo": round(v["receita"] - v["despesa"], 2)} for s, v in setores.items()),
            key=lambda x: -(x["receita"] + x["despesa"])),
        "proximos_30": {"a_pagar": round(a_pagar, 2), "a_receber": round(a_receber, 2)},
        "a_confirmar": a_confirmar,
        "a_confirmar_valor": round(a_confirmar_valor, 2),
        "revisar": db.scalar(select(func.count()).select_from(FinLancamento)
                             .where(FinLancamento.revisar.is_(True), FinLancamento.excluido.is_(False))) or 0,
        "notas_novas": db.scalar(select(func.count()).select_from(FinNota)
                                 .where(FinNota.situacao.in_(("nova", "completa")))) or 0,
        "manejos_sem_fechar": db.scalar(
            select(func.count()).select_from(SessaoPesagem)
            .outerjoin(FinFechamento, FinFechamento.sessao_id == SessaoPesagem.id)
            .where(SessaoPesagem.status == StatusSessao.FINALIZADA,
                   SessaoPesagem.tipo != TipoSessao.MANEJO,
                   FinFechamento.id.is_(None))) or 0,
    }


class _Parcela:
    """O mínimo que parcela_realizada lê, sem carregar a parcela inteira do banco."""
    __slots__ = ("pago", "vencimento")

    def __init__(self, pago: bool | None, vencimento: date) -> None:
        self.pago, self.vencimento = pago, vencimento
