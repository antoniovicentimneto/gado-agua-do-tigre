// Tela inicial: como o rebanho está, o que pede atenção, o desempenho do gado e (só dono)
// o resultado da pecuária. O porquê de cada número está em docs/dashboard_inicio.md.
// Abre na hora com os últimos dados salvos no aparelho e atualiza por cima: o servidor pode
// estar "dormindo" (30-60 s) e no campo pode não ter sinal.

const CHAVE_INICIO_OFFLINE = "gat_cache_inicio";
const IN_RECARREGAR_APOS = 5 * 60 * 1000;   // trocar de aba e voltar não recalcula tudo
const IN_COR_COMPRA = "#8f5a1e";            // validada junto com receita e despesa (CVD/contraste)
const IN_COR_ANO_ANTERIOR = "#8a9694";      // contexto: cinza atrás da linha principal

const ini = {
  rebanho: null, producao: null, financeiro: null, atualizadoEm: 0,
  periodoProducao: "12m", periodoFinanceiro: "12m", carregando: false, semSinal: false,
};

const inEhDono = () => usuarioAtual && usuarioAtual.papel === "dono";

// ---------------------------------------------------------------- Formatação

function inNum(v, casas = 0) {
  if (v === null || v === undefined) return "—";
  return Number(v).toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
}
function inReais(v) {
  return `R$ ${fgCurto(v)}`;
}
function inMesCurto(m) {
  return `${FG_MESES[Number(m.slice(5)) - 1]}/${m.slice(2, 4)}`;
}

// Comparação com o mesmo período do ano anterior, em palavras e com seta (nunca só cor).
function inDelta(atual, anterior, maiorEhMelhor, formatar) {
  if (atual === null || atual === undefined || !anterior) return '<small class="in-delta">sem base no ano anterior</small>';
  const dif = atual - anterior;
  if (Math.abs(dif) < 1e-9) return '<small class="in-delta">igual ao ano anterior</small>';
  const bom = (dif > 0) === maiorEhMelhor;
  return `<small class="in-delta ${bom ? "bom" : "ruim"}">${dif > 0 ? "▲" : "▼"} ${formatar(Math.abs(dif))} ${dif > 0 ? "a mais" : "a menos"} que o ano anterior (${formatar(anterior)})</small>`;
}

function inSituacao(nivel, texto) {
  const icone = { bom: "🟢", atencao: "🟡", ruim: "🔴" }[nivel];
  return `<small class="in-situacao">${icone} ${esc(texto)}</small>`;
}

// ---------------------------------------------------------------- Períodos

function inPeriodos() {
  const h = hojeLocal();
  const ano = Number(h.slice(0, 4));
  const safraIni = Number(h.slice(5, 7)) >= 7 ? ano : ano - 1;
  const curta = (a) => String(a).slice(2);
  return [
    { id: "12m", nome: "Últimos 12 meses" },
    { id: "safra", nome: `Safra ${curta(safraIni)}/${curta(safraIni + 1)} (jul-jun)`, inicio: `${safraIni}-07-01`, fim: `${safraIni + 1}-06-30` },
    { id: "safra-1", nome: `Safra ${curta(safraIni - 1)}/${curta(safraIni)}`, inicio: `${safraIni - 1}-07-01`, fim: `${safraIni}-06-30` },
    { id: "ano", nome: `Ano de ${ano}`, inicio: `${ano}-01-01`, fim: `${ano}-12-31` },
    { id: "ano-1", nome: `Ano de ${ano - 1}`, inicio: `${ano - 1}-01-01`, fim: `${ano - 1}-12-31` },
  ];
}

function inSeletor(id, atual) {
  return `<label class="in-periodo">Período
    <select id="${id}">${inPeriodos().map((p) => `<option value="${p.id}" ${p.id === atual ? "selected" : ""}>${esc(p.nome)}</option>`).join("")}</select>
  </label>`;
}

function inUrl(base, periodoId) {
  const p = inPeriodos().find((x) => x.id === periodoId) || {};
  const q = new URLSearchParams({ hoje: hojeLocal() });
  if (p.inicio) { q.set("inicio", p.inicio); q.set("fim", p.fim); }
  return `${base}?${q}`;
}

// ---------------------------------------------------------------- Navegação

function inIrAba(aba) {
  document.querySelector(`.abas button[data-aba="${aba}"]`).click();
}
function inIrRebanho(modo, status) {
  inIrAba("rebanho");
  document.querySelector(`[data-modo="${modo}"]`).click();
  if (status !== undefined) {
    document.getElementById("filtro-status").value = status;
    carregarLista();
  }
}
function inIrFinanceiro(modo) {
  fin.modo = modo;
  inIrAba("financeiro");
}
async function inIrPastos(modo) {
  inIrAba("pastos");
  if (modo) { if (!pt.dados) await ptCarregar(); ptMudarModo(modo); }
}

// ---------------------------------------------------------------- Tabela ordenável

const inOrdens = {};  // tabela → [{campo, asc}, ...]: ordem em cascata, a última clicada manda

function inComparar(a, b) {
  const vazioA = a === null || a === undefined || a === "";
  const vazioB = b === null || b === undefined || b === "";
  if (vazioA || vazioB) return vazioA && vazioB ? 0 : (vazioA ? 1 : -1);  // vazio sempre no fim
  if (typeof a === "number" && typeof b === "number") return a - b;
  return String(a).localeCompare(String(b), "pt-BR", { numeric: true, sensitivity: "base" });
}

function inTabela(boxId, chave, colunas, linhas, aoClicar) {
  const box = document.getElementById(boxId);
  if (!box) return;
  const ordens = inOrdens[chave] || [];
  const ordenadas = linhas.slice().sort((x, y) => {
    for (const o of ordens) {
      // Vazio fica no fim nos dois sentidos, então a inversão não vale pra ele.
      const c = inComparar(x[o.campo], y[o.campo]);
      if (c) {
        const temVazio = [x[o.campo], y[o.campo]].some((v) => v === null || v === undefined || v === "");
        return o.asc || temVazio ? c : -c;
      }
    }
    return 0;
  });
  const seta = (campo) => {
    const i = ordens.findIndex((o) => o.campo === campo);
    if (i < 0) return "";
    const nivel = ordens.length > 1 ? "¹²³"[i] : "";
    return ` <span class="in-seta">${ordens[i].asc ? "▲" : "▼"}${nivel}</span>`;
  };
  box.innerHTML = `<div class="in-tabela-box"><table class="in-tabela">
    <thead><tr>${colunas.map((c) => `<th data-campo="${c.campo}" class="${c.num ? "num" : ""}" title="${esc(c.dica || "Clique para ordenar")}">${esc(c.rotulo)}${seta(c.campo)}</th>`).join("")}</tr></thead>
    <tbody>${ordenadas.map((l, i) => `<tr data-i="${i}" class="${aoClicar ? "clicavel" : ""}">${colunas.map((c) => `<td class="${c.num ? "num" : ""}">${c.fmt ? c.fmt(l) : esc(l[c.campo] ?? "—")}</td>`).join("")}</tr>`).join("")}</tbody>
  </table></div>`;
  box.querySelectorAll("th").forEach((th) => {
    th.onclick = () => {
      const col = colunas.find((c) => c.campo === th.dataset.campo);
      const atual = ordens.find((o) => o.campo === col.campo);
      const primeiroClique = col.num ? false : true;   // texto A→Z; número do maior pro menor
      const resto = ordens.filter((o) => o.campo !== col.campo).slice(0, 2);
      inOrdens[chave] = [{ campo: col.campo, asc: atual ? !atual.asc : primeiroClique }, ...resto];
      inTabela(boxId, chave, colunas, linhas, aoClicar);
    };
  });
  if (aoClicar) box.querySelectorAll("tbody tr").forEach((tr) => { tr.onclick = () => aoClicar(ordenadas[Number(tr.dataset.i)]); });
}

// ---------------------------------------------------------------- Lista por trás de um número

async function inAbrirAnimais(titulo, filtro) {
  ptModal(`<h2>${esc(titulo)}</h2><div class="info">⏳ Carregando…</div>`);
  const q = new URLSearchParams({ hoje: hojeLocal(), ...filtro });
  let animais;
  try {
    animais = await api.get(`/api/inicio/animais?${q}`);
  } catch (e) {
    ptModal(`<h2>${esc(titulo)}</h2><p class="info">Não foi possível abrir a lista agora: ${esc(e.message)}</p>`);
    return;
  }
  ptModal(`<h2>${esc(titulo)}</h2><p class="info">${inNum(animais.length)} animal(is). Toque na linha para abrir a ficha.</p><div id="in-lista-animais"></div>`);
  inTabela("in-lista-animais", "animais", [
    { campo: "brinco", rotulo: "Brinco" },
    { campo: "tipo", rotulo: "Tipo" },
    { campo: "lote", rotulo: "Lote" },
    { campo: "ultimo_peso", rotulo: "Último peso", num: true, fmt: (a) => (a.ultimo_peso ? `${inNum(a.ultimo_peso)} kg <small>${esc(fmt.data(a.data_peso))}</small>` : "—") },
    { campo: "dias_sem_pesar", rotulo: "Dias sem pesar", num: true, fmt: (a) => inNum(a.dias_sem_pesar) },
  ], animais, (a) => {
    ptFecharModal();
    abrirFicha(a.id, () => inAbrirAnimais(titulo, filtro));
  });
}

// ---------------------------------------------------------------- Rebanho hoje

function inDesenharRebanho() {
  const r = ini.rebanho;
  const box = document.getElementById("in-hero");
  if (!r) return;
  const item = (id, numero, rotulo, sub = "") => `
    <button type="button" class="in-hero-item" data-hero="${id}">
      <b>${numero}</b><span>${esc(rotulo)}</span>${sub ? `<small>${sub}</small>` : ""}
    </button>`;
  box.innerHTML = `
    ${item("cabecas", inNum(r.cabecas), "cabeças ativas")}
    ${item("arrobas", `~${inNum(r.arrobas)} @`, "em pé hoje", `~${inNum(r.peso_total / 1000, 1)} t de peso vivo`)}
    ${item("ua", inNum(r.ua, 0), "unidades animal", r.lotacao.ua_ha ? `${inNum(r.lotacao.ua_ha, 2)} UA/ha em ${inNum(r.lotacao.hectares)} ha` : "1 UA = 450 kg")}
    ${inEhDono() && r.valor_rebanho ? item("valor", `~${inReais(r.valor_rebanho)}`, "valor do rebanho", `a ${fgReal(r.preco_arroba_ref)}/@ das últimas vendas`) : ""}`;
  box.querySelectorAll("[data-hero]").forEach((b) => {
    b.onclick = () => (b.dataset.hero === "ua" ? inIrPastos() : inIrRebanho("lote"));
  });

  // Composição: ranking com o maior em cima; cada linha abre os animais.
  const max = Math.max(1, ...r.categorias.map((c) => c.cabecas));
  const cat = document.getElementById("in-categorias");
  cat.innerHTML = r.categorias.map((c) => `
    <button type="button" class="in-cat" data-tipo="${esc(c.tipo)}">
      <span class="in-cat-nome">${esc(c.tipo)}</span>
      <span class="in-cat-trilho"><span style="width:${(c.cabecas / max) * 100}%"></span></span>
      <span class="in-cat-num"><b>${inNum(c.cabecas)}</b> <small>${c.peso_medio ? `~${inNum(c.peso_medio)} kg` : "sem peso"}</small></span>
    </button>`).join("");
  cat.querySelectorAll("[data-tipo]").forEach((b) => {
    b.onclick = () => inAbrirAnimais(b.dataset.tipo, { tipo: b.dataset.tipo });
  });

  inTabela("in-lotes", "lotes", [
    { campo: "nome", rotulo: "Lote", fmt: (l) => `<i class="in-bolinha" style="background:${esc(l.cor)}"></i>${l.icone ? esc(l.icone) + " " : ""}${esc(l.nome)}` },
    { campo: "cabecas", rotulo: "Cabeças", num: true, fmt: (l) => inNum(l.cabecas) },
    { campo: "peso_medio", rotulo: "Kg médio", num: true, dica: "Peso estimado até hoje: último peso + ganho do lote", fmt: (l) => (l.peso_medio ? `~${inNum(l.peso_medio)}` : "—") },
    { campo: "ugmd", rotulo: "uGMD", num: true, dica: "Ganho por dia no último período (média dos animais do lote)", fmt: (l) => (l.ugmd === null ? "—" : inNum(l.ugmd, 3)) },
    { campo: "dias_sem_pesar", rotulo: "Sem pesar há", num: true, dica: "Dias desde a pesagem mais antiga do lote", fmt: (l) => (l.dias_sem_pesar === null ? "—" : `${l.velha ? "⚠ " : ""}${inNum(l.dias_sem_pesar)} d`) },
    { campo: "piquete", rotulo: "Piquete", fmt: (l) => esc(l.piquete || "não informado") },
  ], r.lotes, (l) => inAbrirAnimais(`Lote ${l.nome}`, { lote: l.id }));
  inAtualizarAtencao();
}

// O que pede atenção: cada linha diz o que é e leva até lá. Vem antes de qualquer gráfico
// na hora de decidir o dia; o sininho continua sendo o detalhe do campo.
function inAtualizarAtencao() {
  const box = document.getElementById("in-atencao");
  const r = ini.rebanho;
  if (!box || !r) return;
  const itens = [];
  const add = (nivel, texto, acao) => itens.push({ nivel, texto, acao });
  const pend = typeof alPendentes === "function" ? alPendentes() : [];
  const urgentes = pend.filter((a) => a.nivel === "vermelho").length;
  if (pend.length) {
    add(urgentes ? "ruim" : "atencao", `${pend.length} alerta(s) do campo${urgentes ? `, ${urgentes} urgente(s)` : ""}`, () => alAbrir());
  }
  if (r.sessoes_abertas) add("atencao", `${r.sessoes_abertas} pesagem(ns) em aberto na mangueira`, () => inIrAba("mangueira"));
  if (r.pesagem.mais_120) {
    add("atencao", `${inNum(r.pesagem.mais_120)} animais há mais de ${r.pesagem.limite_dias} dias sem balança`,
      () => inAbrirAnimais(`Mais de ${r.pesagem.limite_dias} dias sem pesar`, { faixa: "mais_120" }));
  }
  if (r.pesagem.sem_peso) {
    add("atencao", `${inNum(r.pesagem.sem_peso)} animal(is) sem nenhuma pesagem`, () => inAbrirAnimais("Sem nenhuma pesagem", { faixa: "sem_peso" }));
  }
  if (r.em_carencia) add("ruim", `${inNum(r.em_carencia)} animal(is) em carência: não abater`, () => inIrAba("sanidade"));
  if (r.lotacao.lotes_sem_piquete) {
    add("atencao", `${r.lotacao.lotes_sem_piquete} lote(s) sem piquete informado: a lotação não fecha`, () => inIrPastos());
  }
  const f = inEhDono() ? ini.financeiro : null;
  if (f) {
    if (f.manejos_sem_fechar) add("atencao", `${f.manejos_sem_fechar} venda(s)/compra(s) sem fechar no Financeiro`, () => inIrRebanho("manejos"));
    if (f.a_confirmar) add("atencao", `${inNum(f.a_confirmar)} parcela(s) prevista(s) vencida(s) para confirmar (${fgReal(f.a_confirmar_valor)})`, () => inIrFinanceiro("lancamentos"));
    if (f.revisar) add("atencao", `${inNum(f.revisar)} lançamento(s) para classificar`, () => inIrFinanceiro("revisar"));
    if (f.notas_novas) add("atencao", `${inNum(f.notas_novas)} nota(s) fiscal(is) para lançar`, () => inIrFinanceiro("notas"));
  }
  itens.sort((a, b) => (a.nivel === "ruim" ? 0 : 1) - (b.nivel === "ruim" ? 0 : 1));
  box.innerHTML = itens.length
    ? itens.map((it, i) => `<button type="button" class="in-atencao-item" data-i="${i}">
        <span>${it.nivel === "ruim" ? "🔴" : "🟡"}</span><span>${esc(it.texto)}</span><span class="in-chevron">›</span></button>`).join("")
    : '<p class="in-tudo-certo">🟢 Nada pendente. Tudo em dia.</p>';
  box.querySelectorAll("[data-i]").forEach((b) => { b.onclick = () => itens[Number(b.dataset.i)].acao(); });
}
window.inAtualizarAtencao = inAtualizarAtencao;

// ---------------------------------------------------------------- Desempenho do gado

function inDesenharProducao() {
  const p = ini.producao;
  const box = document.getElementById("in-producao");
  if (!p || !ini.rebanho) return;
  const pes = ini.rebanho.pesagem;
  const nivelMort = p.mortalidade_pct === null ? null
    : p.mortalidade_pct <= p.mortalidade_limite ? "bom"
      : p.mortalidade_pct <= p.mortalidade_limite * 1.5 ? "atencao" : "ruim";
  const nivelPes = pes.em_dia_pct === null ? null
    : pes.em_dia_pct >= pes.meta_pct ? "bom" : pes.em_dia_pct >= pes.meta_pct - 20 ? "atencao" : "ruim";
  const m = p.movimento;
  box.innerHTML = `
    <div class="in-cards">
      <button type="button" class="in-card" data-acao="lotes" title="Quilos ganhos ÷ animal-dias entre as pesagens do período">
        <span class="in-rotulo">Ganho por dia (GMD)</span>
        <b>${p.gmd === null ? "—" : `${inNum(p.gmd, 3)} <small>kg/dia</small>`}</b>
        ${inDelta(p.gmd, p.anterior.gmd, true, (v) => inNum(v, 3))}
      </button>
      <button type="button" class="in-card" data-acao="lotes" title="Quilos ganhos × rendimento de carcaça ÷ 15 kg">
        <span class="in-rotulo">Arrobas produzidas</span>
        <b>${inNum(p.arrobas)} <small>@</small></b>
        ${inDelta(p.arrobas, p.anterior.arrobas, true, (v) => `${inNum(v)} @`)}
        <small class="in-sub">${inNum(p.kg)} kg ganhos, rebanho médio ${inNum(p.rebanho_medio)}</small>
      </button>
      <button type="button" class="in-card" data-acao="mortos" title="Mortes e sumiços ÷ rebanho médio do período">
        <span class="in-rotulo">Mortalidade</span>
        <b>${p.mortalidade_pct === null ? "—" : `${inNum(p.mortalidade_pct, 1)}%`}</b>
        ${nivelMort ? inSituacao(nivelMort, `limite de ${inNum(p.mortalidade_limite)}%`) : ""}
        <small class="in-sub">${inNum(m.mortos)} morto(s), ${inNum(m.perdidos)} perdido(s)</small>
      </button>
      <button type="button" class="in-card" data-acao="pesar" title="Animais ativos pesados nos últimos ${pes.limite_dias} dias. Os números acima valem tanto quanto essa cobertura.">
        <span class="in-rotulo">Em dia na balança</span>
        <b>${pes.em_dia_pct === null ? "—" : `${inNum(pes.em_dia_pct)}%`}</b>
        ${nivelPes ? inSituacao(nivelPes, `meta de ${inNum(pes.meta_pct)}%`) : ""}
        <small class="in-sub">${inNum(pes.mais_120)} há mais de ${pes.limite_dias} dias</small>
      </button>
    </div>
    <div class="in-movimento">
      ${m.comprados !== undefined ? `<span><b>${inNum(m.comprados)}</b> comprados</span>` : ""}
      <span><b>${inNum(m.nascimentos)}</b> nascidos</span>
      ${m.vendidos !== undefined ? `<button type="button" class="in-link" data-acao="vendidos"><b>${inNum(m.vendidos)}</b> vendidos</button>` : ""}
      ${p.preco_arroba ? `<span>@ vendida a <b>${fgReal(p.preco_arroba)}</b></span>` : ""}
    </div>
    <h3 class="in-subtitulo">Ganho por dia, mês a mês</h3>
    <div class="fg-legenda">
      <span><i style="background:var(--verde)"></i>Últimos 12 meses</span>
      <span><i style="background:${IN_COR_ANO_ANTERIOR}"></i>Mesmo mês do ano anterior</span>
    </div>
    <div id="in-grafico-gmd"></div>
    ${inFraseGmd(p.serie)}`;
  inDesenharGmd(p.serie);
  box.querySelectorAll("[data-acao]").forEach((b) => {
    b.onclick = () => {
      const a = b.dataset.acao;
      if (a === "lotes") inIrRebanho("lote");
      else if (a === "mortos") inIrRebanho("animal", "morto");
      else if (a === "vendidos") inIrRebanho("animal", "vendido");
      else inAbrirAnimais(`Mais de ${pes.limite_dias} dias sem pesar`, { faixa: "mais_120" });
    };
  });
}

function inFraseGmd(serie) {
  const com = serie.filter((s) => s.gmd !== null);
  if (com.length < 3) return "";
  const alto = com.reduce((a, b) => (b.gmd > a.gmd ? b : a));
  const baixo = com.reduce((a, b) => (b.gmd < a.gmd ? b : a));
  return `<p class="info">Melhor mês: <b>${inMesCurto(alto.mes)}</b> (${inNum(alto.gmd, 3)} kg/dia). Pior: <b>${inMesCurto(baixo.mes)}</b> (${inNum(baixo.gmd, 3)} kg/dia).
    O mês atual ainda é parcial: só entra o que já passou pela balança.</p>`;
}

function inLargura(el) {
  return Math.max(300, (el && el.clientWidth) || Math.min(window.innerWidth, 1400) - 28);
}

function inDesenharGmd(serie) {
  const box = document.getElementById("in-grafico-gmd");
  if (!box) return;
  const L = inLargura(box), A = 230, mE = 42, mD = 12, mT = 12, mB = 26;
  const valores = serie.flatMap((s) => [s.gmd, s.gmd_ano_anterior]).filter((v) => v !== null);
  if (!valores.length) { box.innerHTML = '<p class="info">Ainda não há pesagens suficientes para o gráfico.</p>'; return; }
  const { topo, passo } = fgEscala(Math.max(...valores, 0.1));
  const piso = Math.min(0, ...valores) < 0 ? -passo * Math.ceil(-Math.min(...valores) / passo) : 0;
  const x = (i) => mE + (L - mE - mD) * (i + 0.5) / serie.length;
  const y = (v) => mT + (A - mT - mB) * (1 - (v - piso) / (topo - piso));
  let grade = "";
  for (let v = piso; v <= topo + 1e-9; v += passo) {
    grade += `<line x1="${mE}" x2="${L - mD}" y1="${y(v)}" y2="${y(v)}" class="${Math.abs(v) < 1e-9 ? "fg-base" : "fg-grade"}"/>
      <text x="${mE - 6}" y="${y(v) + 4}" class="fg-eixo" text-anchor="end">${inNum(v, 1)}</text>`;
  }
  // Mês sem base suficiente interrompe a linha em vez de ligar pontos distantes.
  const trecho = (campo) => {
    let d = "", aberto = false;
    serie.forEach((s, i) => {
      if (s[campo] === null) { aberto = false; return; }
      d += `${aberto ? "L" : "M"}${x(i).toFixed(1)},${y(s[campo]).toFixed(1)} `;
      aberto = true;
    });
    return d;
  };
  const pulo = L < 480 ? 2 : 1;
  const rotulos = serie.map((s, i) => ((serie.length - 1 - i) % pulo === 0
    ? `<text x="${x(i)}" y="${A - 8}" class="fg-eixo" text-anchor="middle">${FG_MESES[Number(s.mes.slice(5)) - 1]}</text>` : "")).join("");
  const faixa = (L - mE - mD) / serie.length;
  const pontos = serie.map((s, i) => `<g class="fg-grupo" data-i="${i}">
      <rect x="${x(i) - faixa / 2}" y="${mT}" width="${faixa}" height="${A - mT - mB}" fill="transparent"/>
      ${s.gmd_ano_anterior !== null ? `<circle cx="${x(i)}" cy="${y(s.gmd_ano_anterior)}" r="3" fill="${IN_COR_ANO_ANTERIOR}" stroke="#fff" stroke-width="1.5"/>` : ""}
      ${s.gmd !== null ? `<circle cx="${x(i)}" cy="${y(s.gmd)}" r="4.5" fill="#275E60" stroke="#fff" stroke-width="2"/>` : ""}
    </g>`).join("");
  box.innerHTML = `<svg viewBox="0 0 ${L} ${A}" width="${L}" height="${A}" class="in-svg" role="img"
      aria-label="Ganho de peso por dia em cada mês, comparado com o mesmo mês do ano anterior">
    ${grade}${rotulos}
    <path d="${trecho("gmd_ano_anterior")}" fill="none" stroke="${IN_COR_ANO_ANTERIOR}" stroke-width="1.5" stroke-dasharray="4 3"/>
    <path d="${trecho("gmd")}" fill="none" stroke="#275E60" stroke-width="2.5" stroke-linejoin="round"/>
    ${pontos}</svg>`;
  inLigarDica(box, serie, (s) => `<b>${inMesCurto(s.mes)}</b><br>
    <i style="background:#7fb0b2"></i>Este período: <b>${s.gmd === null ? "sem base" : `${inNum(s.gmd, 3)} kg/dia`}</b><br>
    <i style="background:${IN_COR_ANO_ANTERIOR}"></i>Ano anterior: ${s.gmd_ano_anterior === null ? "sem base" : `${inNum(s.gmd_ano_anterior, 3)} kg/dia`}`);
}

// Dica ao passar o mouse ou tocar numa coluna do gráfico.
function inLigarDica(box, dados, conteudo) {
  const dica = document.getElementById("in-dica");
  box.querySelectorAll(".fg-grupo").forEach((g) => {
    const mostrar = (ev) => {
      dica.innerHTML = conteudo(dados[Number(g.dataset.i)]);
      dica.classList.remove("escondido");
      const p = ev.touches ? ev.touches[0] : ev;
      dica.style.left = Math.max(8, Math.min(window.innerWidth - 240, p.clientX + 12)) + "px";
      dica.style.top = (p.clientY + 14) + "px";
      box.querySelectorAll(".fg-grupo").forEach((x) => x.classList.toggle("fg-ativo", x === g));
    };
    g.addEventListener("mousemove", mostrar);
    g.addEventListener("touchstart", mostrar, { passive: true });
    g.addEventListener("mouseleave", () => { dica.classList.add("escondido"); g.classList.remove("fg-ativo"); });
  });
}

// ---------------------------------------------------------------- Financeiro (só dono)

function inDesenharFinanceiro() {
  const f = ini.financeiro;
  const box = document.getElementById("in-financeiro");
  if (!f || !inEhDono()) return;
  const pc = f.pecuaria;
  const ant = f.pecuaria_anterior;
  const temAnterior = ant.receita || ant.custeio || ant.compra;
  const prox = f.proximos_30;
  box.innerHTML = `
    <div class="in-cards">
      <button type="button" class="in-card" data-fin="resultado" title="Receita do setor Pecuária menos tudo que saiu do setor Pecuária, inclusive compra de gado">
        <span class="in-rotulo">Saldo da pecuária (caixa)</span>
        <b class="${pc.saldo < 0 ? "fg-neg" : ""}">${inReais(pc.saldo)}</b>
        ${temAnterior ? inDelta(pc.saldo, ant.saldo, true, inReais) : '<small class="in-delta">sem base no ano anterior</small>'}
        <small class="in-sub">${inReais(pc.receita)} de receita, ${inReais(pc.compra)} em compra de gado</small>
      </button>
      <button type="button" class="in-card" data-fin="resultado" title="Custeio do setor Pecuária ÷ arrobas ganhas. Não inclui compra de gado nem investimento, nem gastos lançados em Sede ou Máquinas.">
        <span class="in-rotulo">Custo da @ produzida</span>
        <b>${f.custo_arroba === null ? "—" : fgReal(f.custo_arroba)}</b>
        ${inDelta(f.custo_arroba, f.custo_arroba_anterior, false, fgReal)}
        <small class="in-sub">${inReais(pc.custeio)} de custeio ÷ ${inNum(f.arrobas)} @, sem contar Sede e Máquinas</small>
      </button>
      <button type="button" class="in-card" data-fin="graficos" title="Preço médio da @ nas vendas do período menos o custo da @ produzida">
        <span class="in-rotulo">Sobra por @</span>
        <b class="${f.margem_arroba < 0 ? "fg-neg" : ""}">${f.margem_arroba === null ? "—" : fgReal(f.margem_arroba)}</b>
        <small class="in-sub">${f.preco_arroba ? `@ vendida a ${fgReal(f.preco_arroba)}` : "sem preço de venda no período"}</small>
      </button>
      <button type="button" class="in-card" data-fin="lancamentos" title="Parcelas ainda não pagas que vencem nos próximos 30 dias, em todos os setores">
        <span class="in-rotulo">Próximos 30 dias</span>
        <b class="${prox.a_receber - prox.a_pagar < 0 ? "fg-neg" : ""}">${inReais(prox.a_receber - prox.a_pagar)}</b>
        <small class="in-sub">${inReais(prox.a_pagar)} a pagar, ${inReais(prox.a_receber)} a receber</small>
      </button>
    </div>
    <h3 class="in-subtitulo">Pecuária mês a mês</h3>
    <div class="fg-legenda in-legenda-3">
      <span><i style="background:${FG_COR.receita}"></i>Receita</span>
      <span><i style="background:${FG_COR.despesa}"></i>Despesas</span>
      <span><i style="background:${IN_COR_COMPRA}"></i>Compra de gado</span>
    </div>
    <div id="in-grafico-fin"></div>
    <h3 class="in-subtitulo">Fazenda inteira, por setor</h3>
    <div id="in-setores"></div>
    <p class="info">Só o que já aconteceu (venceu = realizado), como na aba Resultado. O saldo da fazenda inteira mistura
      arrendamento e gastos pessoais, por isso a pecuária aparece separada.</p>`;
  inDesenharGraficoFin(f.meses);
  inTabela("in-setores", "setores", [
    { campo: "setor", rotulo: "Setor" },
    { campo: "receita", rotulo: "Receita", num: true, fmt: (s) => fgReal(s.receita) },
    { campo: "despesa", rotulo: "Despesa", num: true, fmt: (s) => fgReal(s.despesa) },
    { campo: "saldo", rotulo: "Saldo", num: true, fmt: (s) => `<span class="${s.saldo < 0 ? "fg-neg" : ""}">${fgReal(s.saldo)}</span>` },
  ], f.setores, () => inIrFinanceiro("resultado"));
  box.querySelectorAll("[data-fin]").forEach((b) => { b.onclick = () => inIrFinanceiro(b.dataset.fin); });
}

function inDesenharGraficoFin(todos) {
  const box = document.getElementById("in-grafico-fin");
  if (!box) return;
  const meses = todos.slice(-12);   // "12 meses" começa no meio de um mês: não desenha a pontinha
  const L = inLargura(box), A = 240, mE = 50, mD = 8, mT = 10, mB = 26;
  const desp = (d) => d.custeio + d.investimentos;
  const max = Math.max(1, ...meses.flatMap((d) => [d.receita, desp(d) + d.compra]));
  const { topo, passo } = fgEscala(max);
  const y = (v) => mT + (A - mT - mB) * (1 - v / topo);
  const larg = (L - mE - mD) / meses.length;
  const barra = Math.max(4, Math.min(24, (larg - 6) / 2));
  let grade = "";
  for (let v = 0; v <= topo + 1e-9; v += passo) {
    grade += `<line x1="${mE}" x2="${L - mD}" y1="${y(v)}" y2="${y(v)}" class="${v ? "fg-grade" : "fg-base"}"/>
      <text x="${mE - 6}" y="${y(v) + 4}" class="fg-eixo" text-anchor="end">${fgCurto(v)}</text>`;
  }
  // Ponta arredondada (só em cima, ancorada na base).
  const topoRedondo = (cx, base, h, cor) => {
    if (h <= 0) return "";
    const r = Math.min(4, h, barra / 2);
    return `<path class="fg-barra" fill="${cor}" d="M${cx},${base} v${-(h - r)} q0,${-r} ${r},${-r} h${barra - 2 * r} q${r},0 ${r},${r} v${h - r} z"/>`;
  };
  const reto = (cx, base, h, cor) => (h > 0 ? `<rect class="fg-barra" fill="${cor}" x="${cx}" y="${base - h}" width="${barra}" height="${h}"/>` : "");
  const pulo = L < 480 && meses.length > 6 ? 2 : 1;
  const barras = meses.map((d, i) => {
    const centro = mE + larg * i + larg / 2;
    const hDesp = y(0) - y(desp(d));
    const hCompra = y(0) - y(d.compra);
    return `<g class="fg-grupo" data-i="${i}">
      <rect x="${mE + larg * i}" y="${mT}" width="${larg}" height="${A - mT - mB}" fill="transparent"/>
      ${topoRedondo(centro - barra - 1, y(0), y(0) - y(d.receita), FG_COR.receita)}
      ${hCompra > 0 ? reto(centro + 1, y(0), hDesp, FG_COR.despesa) + topoRedondo(centro + 1, y(0) - hDesp, hCompra, IN_COR_COMPRA) : topoRedondo(centro + 1, y(0), hDesp, FG_COR.despesa)}
      ${(meses.length - 1 - i) % pulo === 0 ? `<text x="${centro}" y="${A - 8}" class="fg-eixo" text-anchor="middle">${FG_MESES[Number(d.mes.slice(5)) - 1]}</text>` : ""}
    </g>`;
  }).join("");
  box.innerHTML = `<svg viewBox="0 0 ${L} ${A}" width="${L}" height="${A}" class="in-svg" role="img"
      aria-label="Receita, despesas e compra de gado da pecuária em cada mês">${grade}${barras}</svg>`;
  inLigarDica(box, meses, (d) => `<b>${inMesCurto(d.mes)}</b><br>
    <i style="background:${FG_COR.receita}"></i>Receita ${fgReal(d.receita)}<br>
    <i style="background:${FG_COR.despesa}"></i>Despesas ${fgReal(desp(d))}<br>
    <i style="background:${IN_COR_COMPRA}"></i>Compra de gado ${fgReal(d.compra)}<br>
    Saldo <b>${fgReal(d.receita - desp(d) - d.compra)}</b>`);
}

// ---------------------------------------------------------------- Carregamento

function inSalvarCache() {
  salvarOffline(CHAVE_INICIO_OFFLINE, {
    usuario: usuarioAtual.usuario, em: ini.atualizadoEm, rebanho: ini.rebanho,
    producao: ini.periodoProducao === "12m" ? ini.producao : null,
    financeiro: ini.periodoFinanceiro === "12m" ? ini.financeiro : null,
  });
}

function inLerCache() {
  const c = lerOffline(CHAVE_INICIO_OFFLINE);
  if (!c || !usuarioAtual || c.usuario !== usuarioAtual.usuario) return;
  ini.rebanho = ini.rebanho || c.rebanho;
  ini.producao = ini.producao || c.producao;
  ini.financeiro = ini.financeiro || (inEhDono() ? c.financeiro : null);
  ini.atualizadoEm = ini.atualizadoEm || c.em || 0;
}

function inMostrarEstado() {
  const box = document.getElementById("in-atualizado");
  if (!box) return;
  const quando = ini.atualizadoEm ? new Date(ini.atualizadoEm) : null;
  const texto = quando ? `${quando.toLocaleDateString("pt-BR")} às ${quando.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}` : "";
  if (ini.carregando) box.textContent = quando ? `⏳ Atualizando… (dados de ${texto})` : "⏳ Carregando os números…";
  else if (ini.semSinal) box.textContent = quando ? `📡 Sem sinal: mostrando os dados de ${texto}` : "📡 Sem sinal e ainda sem dados salvos neste aparelho.";
  else box.textContent = quando ? `Atualizado em ${texto}` : "";
}

function inDesenharTudo() {
  document.getElementById("in-bloco-financeiro").classList.toggle("escondido", !inEhDono());
  document.getElementById("in-seletor-producao").innerHTML = inSeletor("in-per-producao", ini.periodoProducao);
  document.getElementById("in-per-producao").onchange = (e) => inTrocarPeriodo("producao", e.target.value);
  if (inEhDono()) {
    document.getElementById("in-seletor-financeiro").innerHTML = inSeletor("in-per-financeiro", ini.periodoFinanceiro);
    document.getElementById("in-per-financeiro").onchange = (e) => inTrocarPeriodo("financeiro", e.target.value);
  }
  inDesenharRebanho();
  inDesenharProducao();
  inDesenharFinanceiro();
  inMostrarEstado();
}

// Um período por seção: trocar o do Financeiro não recalcula o do gado.
async function inTrocarPeriodo(secao, periodo) {
  const ehProducao = secao === "producao";
  const box = document.getElementById(ehProducao ? "in-producao" : "in-financeiro");
  if (ehProducao) ini.periodoProducao = periodo; else ini.periodoFinanceiro = periodo;
  box.classList.add("in-atualizando");
  try {
    const dados = await api.get(inUrl(`/api/inicio/${secao}`, periodo), 90000);
    if (ehProducao) { ini.producao = dados; inDesenharProducao(); } else { ini.financeiro = dados; inDesenharFinanceiro(); inAtualizarAtencao(); }
  } catch (e) {
    box.insertAdjacentHTML("afterbegin", `<p class="info in-erro">Não foi possível trocar o período: ${esc(e.message)}</p>`);
  } finally {
    box.classList.remove("in-atualizando");
  }
}

async function inCarregar() {
  if (ini.carregando || !estaLogado() || !usuarioAtual) return;
  ini.carregando = true;
  inMostrarEstado();
  const hoje = hojeLocal();
  const pedidos = [
    api.get(`/api/inicio/rebanho?hoje=${hoje}`, 90000),
    api.get(inUrl("/api/inicio/producao", ini.periodoProducao), 90000),
    inEhDono() ? api.get(inUrl("/api/inicio/financeiro", ini.periodoFinanceiro), 90000) : Promise.resolve(null),
  ];
  const [reb, prod, fina] = await Promise.allSettled(pedidos);
  ini.carregando = false;
  // Cada parte vale sozinha: uma falha não apaga o que as outras trouxeram.
  if (reb.status === "fulfilled") ini.rebanho = reb.value;
  if (prod.status === "fulfilled") ini.producao = prod.value;
  if (fina.status === "fulfilled") ini.financeiro = fina.value;
  const falhou = [reb, prod, fina].find((r) => r.status === "rejected");
  ini.semSinal = !!falhou;
  if (!falhou) {
    ini.atualizadoEm = Date.now();
    inSalvarCache();
  }
  if (!ini.rebanho && falhou) {
    document.getElementById("in-hero").innerHTML = `<p class="in-erro-hero">Não foi possível carregar os números agora.
      <button type="button" class="secundario" id="in-tentar">Tentar de novo</button></p>`;
    document.getElementById("in-tentar").onclick = inCarregar;
    inMostrarEstado();
    return;
  }
  inDesenharTudo();
}

function inAbrir() {
  const hora = new Date().getHours();
  const saudacao = hora < 12 ? "Bom dia" : hora < 18 ? "Boa tarde" : "Boa noite";
  const nome = usuarioAtual ? String(usuarioAtual.nome || "").split(" ")[0] : "";
  document.getElementById("in-saudacao").textContent = nome ? `${saudacao}, ${nome}` : saudacao;
  inLerCache();
  if (ini.rebanho) inDesenharTudo();
  if (Date.now() - ini.atualizadoEm > IN_RECARREGAR_APOS || !ini.rebanho) inCarregar();
}
window.inAbrir = inAbrir;

// Ao sair da conta, nenhum número fica na tela nem no aparelho para o próximo usuário.
function inLimpar() {
  Object.assign(ini, { rebanho: null, producao: null, financeiro: null, atualizadoEm: 0, semSinal: false,
    periodoProducao: "12m", periodoFinanceiro: "12m" });
  try { localStorage.removeItem(CHAVE_INICIO_OFFLINE); } catch (e) { /* armazenamento bloqueado */ }
  ["in-hero", "in-atencao", "in-categorias", "in-producao", "in-financeiro", "in-lotes"].forEach((id) => {
    document.getElementById(id).innerHTML = "";
  });
}
window.inLimpar = inLimpar;

document.getElementById("in-pesar").onclick = () => inIrAba("mangueira");

// Os gráficos são desenhados na largura real da tela (letra sempre legível no celular).
let inLarguraAnterior = window.innerWidth;
window.addEventListener("resize", () => {
  if (window.innerWidth === inLarguraAnterior) return;   // rolar a página no celular muda só a altura
  inLarguraAnterior = window.innerWidth;
  if (!document.getElementById("aba-inicio").classList.contains("ativa")) return;
  if (ini.producao) inDesenharGmd(ini.producao.serie);
  if (ini.financeiro && inEhDono()) inDesenharGraficoFin(ini.financeiro.meses);
});
