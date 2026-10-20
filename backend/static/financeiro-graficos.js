// Financeiro › 📈 Gráficos: receita × despesa por ano e mês a mês, despesa por setor e as
// maiores categorias. Desenhado em SVG puro (sem biblioteca), com dica ao passar o dedo/mouse.

const FG_COR = { receita: "#2a78d6", despesa: "#eb6834" };  // validado (CVD/contraste)
const FG_MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
const fg = { filtros: null };

function fgReal(v) {
  return "R$ " + Number(v || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function fgCurto(v) {
  const a = Math.abs(v);
  if (a >= 1e6) return (v / 1e6).toLocaleString("pt-BR", { maximumFractionDigits: 1 }) + " mi";
  if (a >= 1e3) return (v / 1e3).toLocaleString("pt-BR", { maximumFractionDigits: 0 }) + " mil";
  return v.toLocaleString("pt-BR", { maximumFractionDigits: 0 });
}

// Escala "bonita" pro eixo (0, 1, 2, 5 × 10ⁿ).
function fgEscala(max) {
  if (!max) return { topo: 1, passo: 1 };
  const bruto = max / 4;
  const pot = 10 ** Math.floor(Math.log10(bruto));
  const passo = [1, 2, 2.5, 5, 10].map((m) => m * pot).find((p) => p >= bruto);
  return { topo: Math.ceil(max / passo) * passo, passo };
}

// Colunas agrupadas (receita e despesa lado a lado) — um eixo só, base no zero.
function fgColunas(dados, rotulo, idSvg) {
  const L = 640, A = 240, mE = 56, mB = 26, mT = 8;
  const max = Math.max(1, ...dados.flatMap((d) => [d.receita, d.despesa]));
  const { topo, passo } = fgEscala(max);
  const larg = (L - mE) / dados.length;
  const barra = Math.max(4, Math.min(28, (larg - 10) / 2));
  const y = (v) => mT + (A - mT - mB) * (1 - v / topo);
  let grade = "";
  for (let v = 0; v <= topo + 1e-9; v += passo) {
    grade += `<line x1="${mE}" x2="${L}" y1="${y(v)}" y2="${y(v)}" class="fg-grade"/>
      <text x="${mE - 6}" y="${y(v) + 4}" class="fg-eixo" text-anchor="end">${fgCurto(v)}</text>`;
  }
  const barras = dados.map((d, i) => {
    const cx = mE + larg * i + larg / 2;
    const col = (tipo, dx) => {
      const h = Math.max(0, y(0) - y(d[tipo]));
      return h ? `<path class="fg-barra" fill="${FG_COR[tipo]}" d="M${cx + dx},${y(0)} v${-(h - 4)} q0,-4 4,-4 h${barra - 8} q4,0 4,4 v${h - 4} z"/>` : "";
    };
    return `<g class="fg-grupo" data-i="${i}">
      <rect x="${mE + larg * i}" y="${mT}" width="${larg}" height="${A - mT - mB}" fill="transparent"/>
      ${col("receita", -barra - 1)}${col("despesa", 1)}
      <text x="${cx}" y="${A - 8}" class="fg-eixo" text-anchor="middle">${esc(rotulo(d))}</text></g>`;
  }).join("");
  return `<svg id="${idSvg}" viewBox="0 0 ${L} ${A}" class="fg-svg" role="img">${grade}
    <line x1="${mE}" x2="${L}" y1="${y(0)}" y2="${y(0)}" class="fg-base"/>${barras}</svg>`;
}

// Barras deitadas (ranking, maior em cima) com o valor escrito na ponta.
function fgRanking(itens, cor) {
  const max = Math.max(1, ...itens.map((x) => x.valor));
  return `<div class="fg-ranking">${itens.map((x) => `
    <div class="fg-linha" title="${esc(x.nome)}: ${fgReal(x.valor)}">
      <span class="fg-nome">${esc(x.nome)}</span>
      <span class="fg-trilho"><span class="fg-cheio" style="width:${(x.valor / max) * 100}%;background:${cor}"></span></span>
      <span class="fg-valor">${fgCurto(x.valor)}</span>
    </div>`).join("") || '<p class="info">Sem despesas no período.</p>'}</div>`;
}

function fgLegenda() {
  return `<div class="fg-legenda"><span><i style="background:${FG_COR.receita}"></i>Receita</span>
    <span><i style="background:${FG_COR.despesa}"></i>Despesa</span></div>`;
}

// Dica (tooltip) ao passar por cima de um grupo de colunas.
function fgDica(svgId, dados, titulo) {
  const svg = document.getElementById(svgId);
  if (!svg) return;
  const dica = document.getElementById("fg-dica");
  svg.querySelectorAll(".fg-grupo").forEach((g) => {
    const mostrar = (ev) => {
      const d = dados[Number(g.dataset.i)];
      dica.innerHTML = `<b>${esc(titulo(d))}</b><br><i style="background:${FG_COR.receita}"></i>Receita ${fgReal(d.receita)}
        <br><i style="background:${FG_COR.despesa}"></i>Despesa ${fgReal(d.despesa)}<br>Resultado <b>${fgReal(d.receita - d.despesa)}</b>`;
      dica.classList.remove("escondido");
      const p = ev.touches ? ev.touches[0] : ev;
      dica.style.left = Math.min(window.innerWidth - 230, p.clientX + 12) + "px";
      dica.style.top = (p.clientY + 12) + "px";
      svg.querySelectorAll(".fg-grupo").forEach((x) => x.classList.toggle("fg-ativo", x === g));
    };
    g.addEventListener("mousemove", mostrar);
    g.addEventListener("touchstart", mostrar, { passive: true });
    g.addEventListener("mouseleave", () => { dica.classList.add("escondido"); g.classList.remove("fg-ativo"); });
  });
}

async function finTelaGraficos(alvo) {
  const f = fg.filtros || (fg.filtros = { ano: String(new Date().getFullYear()), visao: "caixa", fazenda: "" });
  alvo.innerHTML = '<div class="info">⏳ Calculando…</div>';
  const q = new URLSearchParams({ ano: f.ano, visao: f.visao, fazenda: f.fazenda });
  const d = await api.get(`/api/fin/graficos?${q}`);
  if (d.anos.length && !d.anos.includes(f.ano)) { f.ano = d.anos[d.anos.length - 1]; return finTelaGraficos(alvo); }
  const t = d.total;
  alvo.innerHTML = `
    <div class="fin-filtros">
      <select id="fg-ano">${d.anos.slice().reverse().map((a) => `<option ${a === f.ano ? "selected" : ""}>${a}</option>`).join("")}</select>
      <select id="fg-visao">
        <option value="caixa" ${f.visao === "caixa" ? "selected" : ""}>Caixa (mês do pagamento)</option>
        <option value="competencia" ${f.visao === "competencia" ? "selected" : ""}>Competência (mês da compra)</option>
      </select>
      <select id="fg-fazenda">${finOpcoes(fin.cad.fazendas.map((x) => x.nome), f.fazenda, "Todas as fazendas")}</select>
    </div>
    <div class="sn-cards fg-cards">
      <div class="sn-card"><b style="color:${FG_COR.receita}">${fgCurto(t.receita)}</b><span>receita ${esc(f.ano)}</span></div>
      <div class="sn-card"><b style="color:${FG_COR.despesa}">${fgCurto(t.despesa)}</b><span>despesa ${esc(f.ano)}</span></div>
      <div class="sn-card"><b class="${t.resultado < 0 ? "fg-neg" : ""}">${fgCurto(t.resultado)}</b><span>resultado ${esc(f.ano)}</span></div>
    </div>

    <h3 class="fg-titulo">Receita × despesa por ano</h3>${fgLegenda()}
    ${fgColunas(d.por_ano, (x) => x.ano, "fg-anos")}

    <h3 class="fg-titulo">Mês a mês — ${esc(f.ano)}</h3>${fgLegenda()}
    ${fgColunas(d.por_mes, (x) => FG_MESES[Number(x.mes.slice(5)) - 1], "fg-meses")}

    <h3 class="fg-titulo">Despesa por setor — ${esc(f.ano)}</h3>
    ${fgRanking(d.por_setor, FG_COR.despesa)}

    <h3 class="fg-titulo">Maiores categorias de despesa — ${esc(f.ano)}</h3>
    ${fgRanking(d.por_categoria, FG_COR.despesa)}
    <p class="info">"(sem categoria)" são lançamentos classificados só até o grupo (categoria é opcional). Toque/passe o mouse nas colunas para ver os valores.
      Os números batem com a aba Resultado (mesma visão).</p>
    <div id="fg-dica" class="fg-dica escondido"></div>`;
  ["ano", "visao", "fazenda"].forEach((c) => {
    alvo.querySelector(`#fg-${c}`).onchange = (e) => { f[c] = e.target.value; finTelaGraficos(alvo); };
  });
  fgDica("fg-anos", d.por_ano, (x) => x.ano);
  fgDica("fg-meses", d.por_mes, (x) => `${FG_MESES[Number(x.mes.slice(5)) - 1]}/${x.mes.slice(0, 4)}`);
}

FIN_TELAS.graficos = finTelaGraficos;
