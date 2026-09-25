// Rebanho › Planilha: todos os animais numa tabela com filtros combináveis,
// ordenação por qualquer coluna e "Baixar Excel" do que está na tela.
// Os dados vêm numa chamada só (/api/animais) e o filtro roda no aparelho —
// assim cada clique é instantâneo, sem ida ao banco (que fica longe).

const PL_PESO_UA = 450; // 1 UA = 450 kg vivos

const pl = {
  animais: [],
  carregado: false,
  ordem: { coluna: "peso", dir: -1 }, // começa do mais pesado pro mais leve
};

// Colunas da tabela: rótulo, valor pra ordenar e como exibir.
const PL_COLUNAS = [
  { id: "brinco", rotulo: "Brinco", valor: (a) => a.brinco, texto: true,
    html: (a) => `<a href="#" class="pl-brinco" data-id="${a.id}"><b>${esc(a.brinco)}</b></a>` },
  { id: "tipo", rotulo: "Tipo", valor: (a) => a.tipo, texto: true, html: (a) => esc(a.tipo || "—") },
  { id: "raca", rotulo: "Raça", valor: (a) => a.raca, texto: true, html: (a) => esc(a.raca || "—") },
  { id: "lote", rotulo: "Lote", valor: (a) => a.lote_atual, texto: true, html: (a) => esc(a.lote_atual || "—") },
  { id: "peso", rotulo: "Último peso", valor: (a) => a.ultimo_peso, html: (a) => fmt.peso(a.ultimo_peso) },
  { id: "data", rotulo: "Data últ. peso", valor: (a) => a.data_ultimo, texto: true, html: (a) => fmt.data(a.data_ultimo) },
  { id: "gmd", rotulo: "GMD", valor: (a) => a.gmd, html: (a) => (a.gmd == null ? "—" : a.gmd.toFixed(3)) },
  { id: "ugmd", rotulo: "uGMD", valor: (a) => a.ugmd, html: (a) => (a.ugmd == null ? "—" : a.ugmd.toFixed(3)) },
  { id: "dentes", rotulo: "Dentes", valor: (a) => a.dentes,
    html: (a) => (a.dentes == null ? "—" : `${a.dentes} <span class="info">${fmt.data(a.data_dentes)}</span>`) },
  { id: "status", rotulo: "Situação", valor: (a) => a.status, texto: true, html: (a) => esc(a.status) },
  { id: "obs", rotulo: "Observação", valor: (a) => a.observacao, texto: true, html: (a) => esc(a.observacao || "") },
];

async function carregarPlanilha(forcar = false) {
  const box = document.getElementById("lista-planilha");
  if (!pl.carregado || forcar) {
    box.innerHTML = "<div class='info'>⏳ Carregando animais...</div>";
    try {
      pl.animais = await api.get("/api/animais");
      pl.carregado = true;
    } catch (e) {
      box.innerHTML = `<div class="info">⚠ Erro ao carregar: ${esc(e.message)}. <a href="#" id="pl-retentar">Tentar de novo</a></div>`;
      document.getElementById("pl-retentar").onclick = (ev) => { ev.preventDefault(); carregarPlanilha(true); };
      return;
    }
  }
  plMontarFiltros();
  plRender();
}

// Valores distintos de um campo (pra montar as opções dos filtros).
function plDistintos(fn) {
  return [...new Set(pl.animais.map(fn).filter((v) => v != null && v !== ""))];
}

function plMontarFiltros() {
  const box = document.getElementById("lista-planilha");
  const tipos = plDistintos((a) => a.tipo).sort();
  const lotes = plDistintos((a) => a.lote_atual).sort();
  const dentes = plDistintos((a) => a.dentes).sort((x, y) => x - y);
  // Datas de pesagem mais recentes (com quantos animais tiveram ali o último peso).
  const contaDatas = {};
  pl.animais.filter((a) => a.status === "ativo" && a.data_ultimo)
    .forEach((a) => (contaDatas[a.data_ultimo] = (contaDatas[a.data_ultimo] || 0) + 1));
  const datas = Object.keys(contaDatas).sort().reverse().slice(0, 30);
  const ehDono = usuarioAtual && usuarioAtual.papel === "dono";

  box.innerHTML = `
    <div class="pl-filtros">
      <div class="pl-f"><label>Brinco</label><input id="pl-busca" placeholder="Buscar..." /></div>
      <div class="pl-f"><label>Situação</label>
        <select id="pl-status">
          <option value="ativo">Ativos</option><option value="">Todos</option>
          <option value="vendido">Vendidos</option><option value="perdido">Perdidos</option>
          <option value="morto">Mortos</option>
        </select></div>
      <div class="pl-f"><label>Lote</label>
        <select id="pl-lote"><option value="">Todos</option>
          ${lotes.map((l) => `<option value="${esc(l)}">${esc(l)}</option>`).join("")}</select></div>
      <div class="pl-f"><label>Dentes</label>
        <select id="pl-dentes"><option value="">Todos</option><option value="sem">Sem registro</option>
          ${dentes.map((d) => `<option value="${d}">${d} dentes</option>`).join("")}</select></div>
      <div class="pl-f"><label>Peso (kg)</label>
        <div class="pl-par"><input id="pl-pmin" inputmode="numeric" placeholder="de" />
        <input id="pl-pmax" inputmode="numeric" placeholder="até" /></div></div>
      <div class="pl-f"><label>Pesados no dia</label>
        <select id="pl-manejo"><option value="">Qualquer data</option>
          ${datas.map((d) => `<option value="${d}">${fmt.data(d)} (${contaDatas[d]})</option>`).join("")}</select></div>
      <div class="pl-f"><label>Último peso entre</label>
        <div class="pl-par"><input id="pl-dde" type="date" /><input id="pl-date" type="date" /></div></div>
      <div class="pl-f pl-tipos"><label>Tipo</label>
        <div>${tipos.map((t) => `<label class="pl-chk"><input type="checkbox" class="pl-tipo" value="${esc(t)}"> ${esc(t)}</label>`).join("")}</div></div>
    </div>
    <div class="pl-barra">
      <div id="pl-resumo" class="pl-resumo"></div>
      <div class="pl-acoes">
        <button id="pl-limpar" class="secundario">Limpar filtros</button>
        <button id="pl-atualizar" class="secundario">↻ Atualizar</button>
        ${ehDono ? `<button id="pl-excel">⬇ Baixar Excel</button>` : ""}
      </div>
    </div>
    <div class="pl-tabela" id="pl-tabela"></div>`;

  box.querySelectorAll(".pl-filtros input, .pl-filtros select")
    .forEach((c) => (c.oninput = c.onchange = plRender));
  // "Pesados no dia" é um atalho do intervalo de datas.
  document.getElementById("pl-manejo").onchange = (ev) => {
    const d = ev.target.value;
    document.getElementById("pl-dde").value = d;
    document.getElementById("pl-date").value = d;
    plRender();
  };
  document.getElementById("pl-limpar").onclick = () => { plMontarFiltros(); plRender(); };
  document.getElementById("pl-atualizar").onclick = () => carregarPlanilha(true);
  if (ehDono) document.getElementById("pl-excel").onclick = plBaixarExcel;
}

// Aplica os filtros escolhidos e a ordenação atual.
function plFiltrados() {
  const v = (id) => document.getElementById(id).value.trim();
  const busca = v("pl-busca");
  const status = v("pl-status");
  const lote = v("pl-lote");
  const dentes = v("pl-dentes");
  const pmin = parseFloat(v("pl-pmin"));
  const pmax = parseFloat(v("pl-pmax"));
  const dde = v("pl-dde");
  const date = v("pl-date");
  const tipos = [...document.querySelectorAll(".pl-tipo:checked")].map((c) => c.value);

  const lista = pl.animais.filter((a) => {
    if (busca && !String(a.brinco).includes(busca)) return false;
    if (status && a.status !== status) return false;
    if (lote && a.lote_atual !== lote) return false;
    if (tipos.length && !tipos.includes(a.tipo)) return false;
    if (dentes === "sem" && a.dentes != null) return false;
    if (dentes && dentes !== "sem" && a.dentes !== Number(dentes)) return false;
    if (!isNaN(pmin) && !(a.ultimo_peso >= pmin)) return false;
    if (!isNaN(pmax) && !(a.ultimo_peso <= pmax)) return false;
    // Datas em ISO (AAAA-MM-DD) comparam certo como texto.
    if (dde && !(a.data_ultimo && a.data_ultimo >= dde)) return false;
    if (date && !(a.data_ultimo && a.data_ultimo <= date)) return false;
    return true;
  });

  const col = PL_COLUNAS.find((c) => c.id === pl.ordem.coluna);
  lista.sort((a, b) => {
    const x = col.valor(a), y = col.valor(b);
    // Vazios sempre no fim, qualquer que seja a direção.
    if (x == null && y == null) return 0;
    if (x == null) return 1;
    if (y == null) return -1;
    const cmp = col.id === "brinco" ? comparaBrinco(x, y)
      : col.texto ? String(x).localeCompare(String(y), "pt-BR") : x - y;
    return cmp * pl.ordem.dir;
  });
  return lista;
}

function plRender() {
  const lista = plFiltrados();
  const pesos = lista.map((a) => a.ultimo_peso).filter((p) => p != null);
  const total = pesos.reduce((s, p) => s + p, 0);
  document.getElementById("pl-resumo").innerHTML =
    `<b>${lista.length}</b> animais · total <b>${Math.round(total).toLocaleString("pt-BR")} kg</b>` +
    ` · médio <b>${pesos.length ? Math.round(total / pesos.length) : "—"} kg</b>` +
    ` · <b>${(total / PL_PESO_UA).toFixed(1)}</b> UA`;

  const seta = (id) => (pl.ordem.coluna === id ? (pl.ordem.dir === 1 ? " ▲" : " ▼") : "");
  const box = document.getElementById("pl-tabela");
  box.innerHTML = lista.length ? `
    <table>
      <thead><tr>${PL_COLUNAS.map((c) => `<th class="pl-th" data-col="${c.id}">${c.rotulo}${seta(c.id)}</th>`).join("")}</tr></thead>
      <tbody>${lista.map((a) => `<tr>${PL_COLUNAS.map((c) => `<td>${c.html(a)}</td>`).join("")}</tr>`).join("")}</tbody>
    </table>` : "<div class='info'>Nenhum animal com esses filtros.</div>";

  box.querySelectorAll(".pl-th").forEach((th) => {
    th.onclick = () => {
      const id = th.dataset.col;
      // 1º clique: números do maior pro menor, textos de A a Z; 2º clique inverte.
      const padrao = PL_COLUNAS.find((c) => c.id === id).texto ? 1 : -1;
      pl.ordem.dir = pl.ordem.coluna === id ? -pl.ordem.dir : padrao;
      pl.ordem.coluna = id;
      plRender();
    };
  });
  box.querySelectorAll(".pl-brinco").forEach((a) => {
    a.onclick = (ev) => { ev.preventDefault(); abrirFicha(Number(a.dataset.id)); };
  });
}

async function plBaixarExcel() {
  const ids = plFiltrados().map((a) => a.id);
  if (!ids.length) { alert("Nenhum animal nos filtros."); return; }
  const btn = document.getElementById("pl-excel");
  btn.disabled = true;
  btn.textContent = "Gerando...";
  try {
    await baixarArquivo("/api/relatorio/excel", "relatorio_gado.xlsx", {
      method: "POST",
      headers: cabecalhos({ "Content-Type": "application/json" }),
      body: JSON.stringify({ ids }),
    });
  } catch (e) {
    alert("Não foi possível gerar o Excel: " + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "⬇ Baixar Excel";
  }
}
