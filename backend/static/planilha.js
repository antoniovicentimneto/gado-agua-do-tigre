// Rebanho › Planilha: todos os animais numa tabela com filtro por coluna no
// estilo do Excel (pesquisar, marcar vários valores, "(Vazias)", ordenar) e
// "Baixar Excel" do que está na tela.
// Os dados vêm numa chamada só (/api/animais) e o filtro roda no aparelho —
// assim cada clique é instantâneo, sem ida ao banco (que fica longe).

const PL_PESO_UA = 450; // 1 UA = 450 kg vivos
const PL_VAZIO = "";    // chave dos valores em branco ("(Vazias)")

const pl = {
  animais: [],
  carregado: false,
  ordem: { coluna: "peso", dir: -1 }, // começa do mais pesado pro mais leve
  // Filtro de lista por coluna: id da coluna -> Set das chaves que PASSAM.
  // Coluna sem entrada = sem filtro. Começa mostrando só os ativos.
  filtros: { status: new Set(["ativo"]) },
  // Faixa numérica por coluna (peso, GMD...): id -> { min, max }.
  faixas: {},
};

const plNum = (v, casas) => (v == null ? "—" : v.toFixed(casas));

// Colunas da tabela.
//  valor: usado pra ordenar · chave: agrupa no filtro · rotuloValor: texto no filtro
//  numero: tem filtro de faixa (de/até)
const PL_COLUNAS = [
  { id: "brinco", rotulo: "Brinco", valor: (a) => a.brinco, texto: true,
    html: (a) => `<a href="#" class="pl-brinco" data-id="${a.id}"><b>${esc(a.brinco)}</b></a>` },
  { id: "tipo", rotulo: "Tipo", valor: (a) => a.tipo, texto: true, html: (a) => esc(a.tipo || "—") },
  { id: "raca", rotulo: "Raça", valor: (a) => a.raca, texto: true, html: (a) => esc(a.raca || "—") },
  { id: "lote", rotulo: "Lote", valor: (a) => a.lote_atual, texto: true, html: (a) => esc(a.lote_atual || "—") },
  { id: "peso", rotulo: "Último peso", valor: (a) => a.ultimo_peso, numero: true,
    rotuloValor: (v) => `${v} kg`, html: (a) => fmt.peso(a.ultimo_peso) },
  { id: "data", rotulo: "Data últ. peso", valor: (a) => a.data_ultimo, texto: true, data: true,
    rotuloValor: (v) => fmt.data(v), html: (a) => fmt.data(a.data_ultimo) },
  { id: "gmd", rotulo: "GMD", valor: (a) => a.gmd, numero: true, casas: 3, html: (a) => plNum(a.gmd, 3) },
  { id: "ugmd", rotulo: "uGMD", valor: (a) => a.ugmd, numero: true, casas: 3, html: (a) => plNum(a.ugmd, 3) },
  { id: "dentes", rotulo: "Dentes", valor: (a) => a.dentes, numero: true, semFaixa: true,
    rotuloValor: (v) => `${v} dentes`,
    html: (a) => (a.dentes == null ? "—" : `${a.dentes} <span class="info">${fmt.data(a.data_dentes)}</span>`) },
  { id: "status", rotulo: "Situação", valor: (a) => a.status, texto: true, html: (a) => esc(a.status) },
  { id: "obs", rotulo: "Observação", valor: (a) => a.observacao, texto: true, html: (a) => esc(a.observacao || "") },
];
const plColuna = (id) => PL_COLUNAS.find((c) => c.id === id);

// Chave do valor pro filtro de lista (texto; "" = vazio).
function plChave(col, a) {
  const v = col.valor(a);
  if (v == null || v === "") return PL_VAZIO;
  return col.casas ? v.toFixed(col.casas) : String(v);
}

function plRotuloChave(col, k) {
  if (k === PL_VAZIO) return "(Vazias)";
  return col.rotuloValor ? col.rotuloValor(k) : k;
}

// Ordena chaves do jeito que faz sentido pra coluna (vazias sempre no fim).
function plOrdenaChaves(col, chaves) {
  return chaves.sort((x, y) => {
    if (x === PL_VAZIO) return 1;
    if (y === PL_VAZIO) return -1;
    if (col.id === "brinco") return comparaBrinco(x, y);
    if (col.data) return y.localeCompare(x);           // data mais recente primeiro
    if (col.numero) return Number(x) - Number(y);
    return x.localeCompare(y, "pt-BR");
  });
}

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
  plMontarTela();
  plRender();
}

function plMontarTela() {
  const ehDono = usuarioAtual && usuarioAtual.papel === "dono";
  document.getElementById("lista-planilha").innerHTML = `
    <div class="info pl-dica">Toque no <b>⏷</b> do título da coluna pra filtrar (pode marcar vários) ou ordenar.</div>
    <div id="pl-ativos" class="pl-ativos"></div>
    <div class="pl-barra">
      <div id="pl-resumo" class="pl-resumo"></div>
      <div class="pl-acoes">
        <button id="pl-limpar" class="secundario">Limpar filtros</button>
        <button id="pl-atualizar" class="secundario">↻ Atualizar</button>
        ${ehDono ? `<button id="pl-excel">⬇ Baixar Excel</button>` : ""}
      </div>
    </div>
    <div class="pl-tabela" id="pl-tabela"></div>`;
  document.getElementById("pl-limpar").onclick = () => {
    pl.filtros = {};
    pl.faixas = {};
    plRender();
  };
  document.getElementById("pl-atualizar").onclick = () => carregarPlanilha(true);
  if (ehDono) document.getElementById("pl-excel").onclick = plBaixarExcel;
}

// O animal passa nos filtros? (ignorando uma coluna — usado pra montar a lista
// daquela coluna só com o que sobra dos OUTROS filtros, como o Excel faz)
function plPassa(a, ignorar) {
  for (const [id, permitidos] of Object.entries(pl.filtros)) {
    if (id === ignorar) continue;
    if (!permitidos.has(plChave(plColuna(id), a))) return false;
  }
  for (const [id, f] of Object.entries(pl.faixas)) {
    if (id === ignorar) continue;
    const v = plColuna(id).valor(a);
    if (f.min != null && !(v != null && v >= f.min)) return false;
    if (f.max != null && !(v != null && v <= f.max)) return false;
  }
  return true;
}

function plFiltrados() {
  const lista = pl.animais.filter((a) => plPassa(a));
  const col = plColuna(pl.ordem.coluna);
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

const plFiltroAtivo = (id) => id in pl.filtros || id in pl.faixas;

function plRender() {
  const lista = plFiltrados();
  const pesos = lista.map((a) => a.ultimo_peso).filter((p) => p != null);
  const total = pesos.reduce((s, p) => s + p, 0);
  document.getElementById("pl-resumo").innerHTML =
    `<b>${lista.length}</b> animais · total <b>${Math.round(total).toLocaleString("pt-BR")} kg</b>` +
    ` · médio <b>${pesos.length ? Math.round(total / pesos.length) : "—"} kg</b>` +
    ` · <b>${(total / PL_PESO_UA).toFixed(1)}</b> UA`;

  // Etiquetas dos filtros ligados (com ✕ pra tirar cada um).
  const ativos = PL_COLUNAS.filter((c) => plFiltroAtivo(c.id)).map((c) => {
    const partes = [];
    if (pl.filtros[c.id]) {
      const ks = plOrdenaChaves(c, [...pl.filtros[c.id]]);
      partes.push(ks.length > 3 ? `${ks.length} valores`
        : ks.length ? ks.map((k) => plRotuloChave(c, k)).join(", ") : "nenhum");
    }
    const f = pl.faixas[c.id];
    if (f) partes.push([f.min != null ? `≥ ${f.min}` : "", f.max != null ? `≤ ${f.max}` : ""].filter(Boolean).join(" e "));
    return `<span class="pl-chip" data-col="${c.id}">${esc(c.rotulo)}: ${esc(partes.join(" · "))} <b>✕</b></span>`;
  });
  const boxAtivos = document.getElementById("pl-ativos");
  boxAtivos.innerHTML = ativos.join("");
  boxAtivos.querySelectorAll(".pl-chip").forEach((ch) => {
    ch.onclick = () => {
      delete pl.filtros[ch.dataset.col];
      delete pl.faixas[ch.dataset.col];
      plRender();
    };
  });

  const seta = (id) => (pl.ordem.coluna === id ? (pl.ordem.dir === 1 ? " ▲" : " ▼") : "");
  const box = document.getElementById("pl-tabela");
  box.innerHTML = `
    <table>
      <thead><tr>${PL_COLUNAS.map((c) => `
        <th><span class="pl-th" data-col="${c.id}">${c.rotulo}${seta(c.id)}</span><button
          class="pl-funil${plFiltroAtivo(c.id) ? " ativo" : ""}" data-col="${c.id}" title="Filtrar">⏷</button></th>`).join("")}
      </tr></thead>
      <tbody>${lista.map((a) => `<tr>${PL_COLUNAS.map((c) => `<td>${c.html(a)}</td>`).join("")}</tr>`).join("")}</tbody>
    </table>
    ${lista.length ? "" : "<div class='info' style='padding:10px'>Nenhum animal com esses filtros.</div>"}`;

  box.querySelectorAll(".pl-th").forEach((th) => {
    th.onclick = () => {
      const id = th.dataset.col;
      // 1º clique: números do maior pro menor, textos de A a Z; 2º clique inverte.
      const padrao = plColuna(id).texto ? 1 : -1;
      pl.ordem.dir = pl.ordem.coluna === id ? -pl.ordem.dir : padrao;
      pl.ordem.coluna = id;
      plRender();
    };
  });
  box.querySelectorAll(".pl-funil").forEach((b) => {
    b.onclick = (ev) => { ev.stopPropagation(); plAbrirFiltro(b.dataset.col, b); };
  });
  box.querySelectorAll(".pl-brinco").forEach((a) => {
    a.onclick = (ev) => { ev.preventDefault(); abrirFicha(Number(a.dataset.id)); };
  });
}

// ------------------------------------------------ Caixa de filtro (estilo Excel)
function plFecharFiltro() {
  const p = document.getElementById("pl-pop");
  if (p) p.remove();
  document.removeEventListener("mousedown", plCliqueFora, true);
}

function plCliqueFora(ev) {
  const p = document.getElementById("pl-pop");
  if (p && !p.contains(ev.target)) plFecharFiltro();
}

function plAbrirFiltro(id, botao) {
  plFecharFiltro();
  const col = plColuna(id);

  // Valores possíveis = o que sobra aplicando os OUTROS filtros (com contagem).
  const contagem = new Map();
  pl.animais.filter((a) => plPassa(a, id)).forEach((a) => {
    const k = plChave(col, a);
    contagem.set(k, (contagem.get(k) || 0) + 1);
  });
  const chaves = plOrdenaChaves(col, [...contagem.keys()]);
  const atual = pl.filtros[id];                 // undefined = tudo marcado
  const marcado = new Set(atual ? chaves.filter((k) => atual.has(k)) : chaves);
  const faixa = pl.faixas[id] || {};

  const pop = document.createElement("div");
  pop.id = "pl-pop";
  pop.className = "pl-pop";
  pop.innerHTML = `
    <div class="pl-pop-tit">${esc(col.rotulo)}</div>
    <div class="pl-pop-ord">
      <button class="secundario" data-dir="1">${col.texto ? "A → Z" : "Menor → maior"}</button>
      <button class="secundario" data-dir="-1">${col.texto ? "Z → A" : "Maior → menor"}</button>
    </div>
    ${col.numero && !col.semFaixa ? `
      <div class="pl-pop-faixa">
        <input id="pl-pop-min" inputmode="decimal" placeholder="de" value="${faixa.min ?? ""}" />
        <input id="pl-pop-max" inputmode="decimal" placeholder="até" value="${faixa.max ?? ""}" />
      </div>` : ""}
    <input id="pl-pop-busca" class="pl-pop-busca" placeholder="Pesquisar..." />
    <label class="pl-pop-item pl-pop-todos"><input type="checkbox" id="pl-pop-todos"> (Selecionar tudo)</label>
    <div class="pl-pop-lista" id="pl-pop-lista"></div>
    <div class="pl-pop-acoes">
      <button class="secundario" id="pl-pop-limpar">Limpar</button>
      <button class="secundario" id="pl-pop-cancelar">Cancelar</button>
      <button id="pl-pop-ok">OK</button>
    </div>`;
  document.body.appendChild(pop);

  // Posiciona embaixo do botão (no celular vira painel de baixo, via CSS).
  if (window.innerWidth > 600) {
    const r = botao.getBoundingClientRect();
    pop.style.top = `${Math.min(r.bottom + 4, window.innerHeight - pop.offsetHeight - 8)}px`;
    pop.style.left = `${Math.max(8, Math.min(r.left - 10, window.innerWidth - pop.offsetWidth - 8))}px`;
  }

  const busca = pop.querySelector("#pl-pop-busca");
  const visiveis = () => {
    const t = busca.value.trim().toLowerCase();
    return t ? chaves.filter((k) => plRotuloChave(col, k).toLowerCase().includes(t)) : chaves;
  };
  const listaBox = pop.querySelector("#pl-pop-lista");
  const todos = pop.querySelector("#pl-pop-todos");

  function desenhaLista() {
    const vis = visiveis();
    listaBox.innerHTML = vis.map((k, i) => `
      <label class="pl-pop-item"><input type="checkbox" data-i="${i}" ${marcado.has(k) ? "checked" : ""}>
        <span>${esc(plRotuloChave(col, k))}</span><span class="info">${contagem.get(k)}</span></label>`).join("")
      || "<div class='info'>Nada encontrado.</div>";
    listaBox.querySelectorAll("input").forEach((chk) => {
      chk.onchange = () => {
        const k = vis[Number(chk.dataset.i)];
        if (chk.checked) marcado.add(k); else marcado.delete(k);
        atualizaTodos();
      };
    });
    atualizaTodos();
  }
  function atualizaTodos() {
    const vis = visiveis();
    const n = vis.filter((k) => marcado.has(k)).length;
    todos.checked = vis.length > 0 && n === vis.length;
    todos.indeterminate = n > 0 && n < vis.length;
  }
  todos.onchange = () => {
    visiveis().forEach((k) => (todos.checked ? marcado.add(k) : marcado.delete(k)));
    desenhaLista();
  };
  busca.oninput = () => {
    // Como no Excel: ao pesquisar, já marca só o que aparece.
    if (busca.value.trim()) {
      marcado.clear();
      visiveis().forEach((k) => marcado.add(k));
    }
    desenhaLista();
  };
  desenhaLista();

  pop.querySelectorAll(".pl-pop-ord button").forEach((b) => {
    b.onclick = () => {
      pl.ordem = { coluna: id, dir: Number(b.dataset.dir) };
      plFecharFiltro();
      plRender();
    };
  });
  pop.querySelector("#pl-pop-cancelar").onclick = plFecharFiltro;
  pop.querySelector("#pl-pop-limpar").onclick = () => {
    delete pl.filtros[id];
    delete pl.faixas[id];
    plFecharFiltro();
    plRender();
  };
  pop.querySelector("#pl-pop-ok").onclick = () => {
    // Tudo marcado = sem filtro de lista nessa coluna.
    if (chaves.every((k) => marcado.has(k))) delete pl.filtros[id];
    else pl.filtros[id] = new Set(marcado);
    if (col.numero && !col.semFaixa) {
      const num = (sel) => {
        const v = parseFloat(pop.querySelector(sel).value.replace(",", "."));
        return isNaN(v) ? null : v;
      };
      const min = num("#pl-pop-min"), max = num("#pl-pop-max");
      if (min == null && max == null) delete pl.faixas[id];
      else pl.faixas[id] = { min, max };
    }
    plFecharFiltro();
    plRender();
  };
  pop.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") pop.querySelector("#pl-pop-ok").click();
    if (ev.key === "Escape") plFecharFiltro();
  });
  setTimeout(() => document.addEventListener("mousedown", plCliqueFora, true), 0);
  if (window.innerWidth > 600) busca.focus();
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
