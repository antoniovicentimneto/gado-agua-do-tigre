// Frontend do app de controle de gado. Conversa com a API em /api.

const TOKEN_KEY = "gat_token";

function cabecalhos(extra) {
  const h = { ...extra };
  const t = localStorage.getItem(TOKEN_KEY);
  if (t) h["Authorization"] = "Bearer " + t;
  return h;
}

async function _resposta(r) {
  if (r.status === 401) {
    // Sessão expirada / sem login: volta para a tela de login.
    if (window.logout) window.logout(true);
    throw new Error("Faça login");
  }
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || "Erro");
  return r.json();
}

const api = {
  async get(url) {
    return _resposta(await fetch(url, { headers: cabecalhos() }));
  },
  async post(url, dados) {
    return _resposta(await fetch(url, {
      method: "POST",
      headers: cabecalhos({ "Content-Type": "application/json" }),
      body: JSON.stringify(dados),
    }));
  },
  async put(url, dados) {
    return _resposta(await fetch(url, {
      method: "PUT",
      headers: cabecalhos({ "Content-Type": "application/json" }),
      body: JSON.stringify(dados),
    }));
  },
  async delete(url) {
    return _resposta(await fetch(url, { method: "DELETE", headers: cabecalhos() }));
  },
};

function estaLogado() {
  return !!localStorage.getItem(TOKEN_KEY);
}

// ----------------------------------------------------------- Login / primeiro acesso
const USUARIO_KEY = "gat_usuario";
let usuarioAtual = null;

function logout(expirou) {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USUARIO_KEY);
  usuarioAtual = null;
  document.getElementById("app-conteudo").classList.add("escondido");
  document.getElementById("login-form-area").classList.remove("escondido");
  document.getElementById("setup-form-area").classList.add("escondido");
  document.getElementById("tela-login").classList.remove("escondido");
  document.getElementById("login-msg").textContent = expirou ? "Sessão expirada, entre novamente." : "";
}
window.logout = logout;

function aplicarPermissoes() {
  const ehDono = usuarioAtual && usuarioAtual.papel === "dono";
  document.getElementById("aba-btn-usuarios").classList.toggle("escondido", !ehDono);
  document.getElementById("aba-btn-config").classList.toggle("escondido", !ehDono);
  document.getElementById("btn-exportar").classList.toggle("escondido", !ehDono);
  // Tipos de sessão de compra/venda na mangueira são só do dono.
  document.querySelectorAll("#mg-tipo option[value=compra], #mg-tipo option[value=venda_fazenda], #mg-tipo option[value=venda_morto]")
    .forEach((o) => (o.disabled = !ehDono));
}

function entrarNoApp(dados) {
  localStorage.setItem(TOKEN_KEY, dados.token);
  usuarioAtual = { nome: dados.nome, usuario: dados.usuario, papel: dados.papel };
  localStorage.setItem(USUARIO_KEY, JSON.stringify(usuarioAtual));
  document.getElementById("tela-login").classList.add("escondido");
  document.getElementById("app-conteudo").classList.remove("escondido");
  document.getElementById("usuario-logado-nome").textContent = `${dados.nome} (${dados.papel})`;
  aplicarPermissoes();
  carregarLista();
  carregarCacheAnimais().catch(() => {});   // pré-carrega os animais (consulta local)
  if (typeof mgInit === "function") mgInit();
}

document.getElementById("login-entrar").onclick = async () => {
  const usuario = document.getElementById("login-usuario").value.trim();
  const senha = document.getElementById("login-senha").value;
  const msg = document.getElementById("login-msg");
  if (!usuario || !senha) { msg.textContent = "Preencha usuário e senha."; return; }
  try {
    const r = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ usuario, senha }),
    });
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || "Erro ao entrar");
    entrarNoApp(await r.json());
  } catch (e) {
    msg.textContent = e.message;
  }
};

document.getElementById("setup-criar").onclick = async () => {
  const nome = document.getElementById("setup-nome").value.trim();
  const usuario = document.getElementById("setup-usuario").value.trim();
  const senha = document.getElementById("setup-senha").value;
  const msg = document.getElementById("setup-msg");
  if (!nome || !usuario || !senha) { msg.textContent = "Preencha todos os campos."; return; }
  try {
    const r = await fetch("/api/auth/setup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nome, usuario, senha }),
    });
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || "Erro ao criar conta");
    entrarNoApp(await r.json());
  } catch (e) {
    msg.textContent = e.message;
  }
};

document.getElementById("btn-logout").onclick = () => logout(false);

async function iniciarTelaLogin() {
  const r = await fetch("/api/auth/status").then((x) => x.json());
  if (!r.tem_usuarios) {
    document.getElementById("login-form-area").classList.add("escondido");
    document.getElementById("setup-form-area").classList.remove("escondido");
  }
  document.getElementById("tela-login").classList.remove("escondido");
}

// ----------------------------------------------------------- Gestão de usuários (dono)
async function carregarUsuarios() {
  const usuarios = await api.get("/api/auth/usuarios");
  const box = document.getElementById("lista-usuarios");
  box.innerHTML = "";
  usuarios.forEach((u) => {
    const div = document.createElement("div");
    div.className = "card-usuario";
    div.innerHTML = `
      <div>
        <div class="nome">${u.nome}</div>
        <div class="sub">${u.usuario} · ${u.papel}</div>
      </div>
      <button data-id="${u.id}">remover</button>`;
    div.querySelector("button").onclick = async () => {
      if (!confirm(`Remover o usuário ${u.nome}?`)) return;
      try {
        await api.delete("/api/auth/usuarios/" + u.id);
        carregarUsuarios();
      } catch (e) { alert(e.message); }
    };
    box.appendChild(div);
  });
}

document.getElementById("nu-criar").onclick = async () => {
  const nome = document.getElementById("nu-nome").value.trim();
  const usuario = document.getElementById("nu-usuario").value.trim();
  const senha = document.getElementById("nu-senha").value;
  const papel = document.getElementById("nu-papel").value;
  const msg = document.getElementById("nu-msg");
  if (!nome || !usuario || !senha) { msg.textContent = "Preencha todos os campos."; return; }
  try {
    await api.post("/api/auth/usuarios", { nome, usuario, senha, papel });
    document.getElementById("nu-nome").value = "";
    document.getElementById("nu-usuario").value = "";
    document.getElementById("nu-senha").value = "";
    msg.textContent = "Usuário criado!";
    carregarUsuarios();
  } catch (e) {
    msg.textContent = e.message;
  }
};

// ----------------------------------------------------------- Config (tipos/raças)
async function carregarConfig() {
  await renderConfigLista("tipo", "cfg-tipos");
  await renderConfigLista("raca", "cfg-racas");
}

async function renderConfigLista(categoria, boxId) {
  const itens = await api.get("/api/opcoes/" + categoria);
  const box = document.getElementById(boxId);
  box.innerHTML = itens.length
    ? itens.map((o) => `
        <span class="cfg-tag">${esc(o.nome)}
          <button data-id="${o.id}" title="remover">×</button>
        </span>`).join("")
    : "<span class='info'>Nenhum cadastrado ainda.</span>";
  box.querySelectorAll("button").forEach((b) => {
    b.onclick = async () => {
      try {
        await api.delete(`/api/opcoes/${categoria}/${b.dataset.id}`);
        cache[categoria] = null;       // invalida o cache pra recarregar atualizado
        renderConfigLista(categoria, boxId);
      } catch (e) { document.getElementById("cfg-msg").textContent = e.message; }
    };
  });
}

async function adicionarOpcao(categoria, inputId, boxId) {
  const inp = document.getElementById(inputId);
  const nome = inp.value.trim();
  if (!nome) return;
  try {
    await api.post("/api/opcoes/" + categoria, { nome });
    inp.value = "";
    cache[categoria] = null;
    document.getElementById("cfg-msg").textContent = "";
    renderConfigLista(categoria, boxId);
  } catch (e) { document.getElementById("cfg-msg").textContent = e.message; }
}

document.getElementById("cfg-tipo-add").onclick = () => adicionarOpcao("tipo", "cfg-tipo-nome", "cfg-tipos");
document.getElementById("cfg-raca-add").onclick = () => adicionarOpcao("raca", "cfg-raca-nome", "cfg-racas");

const fmt = {
  gmd: (v) => (v == null ? "—" : v.toFixed(3) + " kg/dia"),
  peso: (v) => (v == null ? "—" : v.toFixed(0) + " kg"),
  data: (v) => (v == null ? "—" : v.split("-").reverse().join("/")),
  real: (v) => (v == null ? "—" : "R$ " + v.toLocaleString("pt-BR", { minimumFractionDigits: 2 })),
};

// Escapa texto pra usar com segurança dentro de HTML/atributos.
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ----------------------------------------------------- Opções (tipos/raças) e lotes
const cache = { tipo: null, raca: null, lotes: null };

async function opcoes(categoria) {
  if (!cache[categoria]) {
    cache[categoria] = (await api.get("/api/opcoes/" + categoria)).map((o) => o.nome);
  }
  return cache[categoria];
}

async function nomesLotes() {
  if (!cache.lotes) {
    cache.lotes = (await api.get("/api/lotes")).map((l) => l.nome).sort((a, b) => a.localeCompare(b));
  }
  return cache.lotes;
}

function limparCacheLotes() { cache.lotes = null; }

// Cache dos animais ATIVOS carregado uma vez (fica na memória da página).
// Assim a consulta do brinco é local e instantânea, sem ir à internet a cada tecla.
const cacheAnimais = { porBrinco: new Map(), carregadoEm: 0 };

async function carregarCacheAnimais() {
  const lista = await api.get("/api/animais-cache");
  const m = new Map();
  for (const a of lista) {
    const k = String(a.brinco);
    if (!m.has(k)) m.set(k, []);
    m.get(k).push(a);
  }
  cacheAnimais.porBrinco = m;
  cacheAnimais.carregadoEm = Date.now();
}

function animaisPorBrinco(brinco) {
  return cacheAnimais.porBrinco.get(String(brinco).trim()) || [];
}

// Insere/atualiza um animal no cache local (após pesar/cadastrar), sem ir à rede.
function cacheUpsertAnimal(a) {
  const k = String(a.brinco);
  let arr = cacheAnimais.porBrinco.get(k);
  if (!arr) { arr = []; cacheAnimais.porBrinco.set(k, arr); }
  const i = arr.findIndex((x) => x.id === a.id);
  if (i >= 0) arr[i] = { ...arr[i], ...a };
  else arr.push(a);
}

// Monta as <option> de um select a partir de uma lista de nomes.
function opcoesHTML(nomes, atual, rotuloVazio = "—") {
  const temAtual = atual && nomes.includes(atual);
  let html = `<option value="">${rotuloVazio}</option>`;
  // Se o valor atual não está na lista (ex.: dado antigo), mantém como opção.
  if (atual && !temAtual) html += `<option value="${esc(atual)}" selected>${esc(atual)} (atual)</option>`;
  html += nomes.map((n) => `<option value="${esc(n)}" ${n === atual ? "selected" : ""}>${esc(n)}</option>`).join("");
  return html;
}

// Seletor de lote: dropdown dos lotes já cadastrados + opção de criar um novo.
// Retorna o HTML; depois chame ligarSeletorLote(prefixo) e leia com valorLote(prefixo).
async function seletorLoteHTML(prefixo, atual = "") {
  const lotes = await nomesLotes();
  return `
    <select id="${prefixo}-sel">
      <option value="">— escolher lote —</option>
      ${lotes.map((n) => `<option value="${esc(n)}" ${n === atual ? "selected" : ""}>${esc(n)}</option>`).join("")}
      <option value="__novo__">➕ novo lote...</option>
    </select>
    <input id="${prefixo}-novo" class="escondido" placeholder="Nome do novo lote" style="margin-top:6px" />`;
}

function ligarSeletorLote(prefixo) {
  const sel = document.getElementById(prefixo + "-sel");
  const inp = document.getElementById(prefixo + "-novo");
  if (!sel || !inp) return;
  sel.onchange = () => {
    const novo = sel.value === "__novo__";
    inp.classList.toggle("escondido", !novo);
    if (novo) inp.focus();
  };
}

function valorLote(prefixo) {
  const sel = document.getElementById(prefixo + "-sel");
  if (!sel) return "";
  if (sel.value === "__novo__") return document.getElementById(prefixo + "-novo").value.trim();
  return sel.value;
}

// ----------------------------------------------------------- Navegação por abas
document.querySelectorAll(".abas button").forEach((b) => {
  b.onclick = () => {
    document.querySelectorAll(".abas button").forEach((x) => x.classList.remove("ativa"));
    document.querySelectorAll(".aba").forEach((x) => x.classList.remove("ativa"));
    b.classList.add("ativa");
    document.getElementById("aba-" + b.dataset.aba).classList.add("ativa");
    if (b.dataset.aba === "painel") carregarPainel();
    if (b.dataset.aba === "usuarios") carregarUsuarios();
    if (b.dataset.aba === "config") carregarConfig();
  };
});

// ----------------------------------------------------------- Lista de animais
async function carregarLista() {
  const busca = document.getElementById("busca").value.trim();
  const status = document.getElementById("filtro-status").value;
  const params = new URLSearchParams();
  if (busca) params.set("busca", busca);
  if (status) params.set("status", status);
  const animais = await api.get("/api/animais?" + params);
  document.getElementById("contador").textContent = `${animais.length} animais`;

  const lista = document.getElementById("lista");
  lista.innerHTML = "";
  animais.forEach((a) => {
    const div = document.createElement("div");
    div.className = "card-animal";
    const tag =
      a.status === "ativo" ? "" : `<span class="tag ${a.status}">${a.status}</span>`;
    const detalhes = [a.tipo, a.raca, a.lote_atual].filter(Boolean).join(" · ");
    const obs = a.observacao
      ? `<div class="sub obs" title="${a.observacao.replace(/"/g, "&quot;")}">📝 ${a.observacao}</div>`
      : "";
    div.innerHTML = `
      <div class="card-animal-info">
        <div class="brinco">${a.brinco}${tag}</div>
        <div class="sub">${detalhes}</div>
        <div class="sub">Último: ${fmt.peso(a.ultimo_peso)} em ${fmt.data(a.data_ultimo)}</div>
        ${obs}
      </div>
      <div class="gmd">
        <div class="sub">GMD</div>
        <b>${a.gmd == null ? "—" : a.gmd.toFixed(3)}</b>
        <div class="sub">uGMD ${a.ugmd == null ? "—" : a.ugmd.toFixed(3)}</div>
      </div>`;
    div.onclick = () => abrirFicha(a.id);
    lista.appendChild(div);
  });
}

let buscaTimer;
document.getElementById("busca").oninput = () => {
  clearTimeout(buscaTimer);
  buscaTimer = setTimeout(carregarLista, 250);
};
document.getElementById("filtro-status").onchange = carregarLista;

// ----------------------------------------------------------- Novo animal
document.getElementById("btn-novo").onclick = async () => {
  const brinco = prompt("Brinco do novo animal:");
  if (!brinco) return;
  const tipo = prompt("Tipo (Novilha / Boi / Vaca / Bezerro):", "Novilha");
  try {
    await api.post("/api/animais", { brinco, tipo });
    carregarLista();
  } catch (e) {
    alert("Erro: " + e.message);
  }
};

// ----------------------------------------------------------- Modo Por animal / Por lote
let modoRebanho = "animal";
document.querySelectorAll(".modo-toggle button").forEach((b) => {
  b.onclick = () => {
    document.querySelectorAll(".modo-toggle button").forEach((x) => x.classList.remove("ativa"));
    b.classList.add("ativa");
    modoRebanho = b.dataset.modo;
    const porAnimal = modoRebanho === "animal";
    const porLote = modoRebanho === "lote";
    const porManejo = modoRebanho === "manejos";
    document.getElementById("filtros-animal").style.display = porAnimal ? "flex" : "none";
    document.getElementById("lista").style.display = porAnimal ? "block" : "none";
    document.getElementById("lista-lotes").style.display = porLote ? "block" : "none";
    document.getElementById("lista-manejos").style.display = porManejo ? "block" : "none";
    document.getElementById("contador").style.display = porAnimal ? "block" : "none";
    if (porAnimal) carregarLista();
    else if (porLote) carregarLotes();
    else carregarManejos();
  };
});

async function carregarLotes() {
  const lotes = await api.get("/api/lotes?somente_ativos=true");
  const box = document.getElementById("lista-lotes");
  box.innerHTML = "";
  lotes.forEach((l) => {
    const div = document.createElement("div");
    div.className = "card-lote";
    const gmd = l.gmd_medio == null ? "—" : l.gmd_medio.toFixed(3);
    const ugmd = l.ugmd_medio == null ? "—" : l.ugmd_medio.toFixed(3);
    div.innerHTML = `
      <div class="card-lote-info">
        <span class="nome">${esc(l.nome)}</span>
        <div class="card-lote-ind">GMD ${gmd} · uGMD ${ugmd} · ${l.ua ?? 0} UA</div>
      </div>
      <span class="qtd">${l.ativos} animais</span>`;
    div.onclick = () => abrirLote(l.id, l.nome);
    box.appendChild(div);
  });
  if (!lotes.length) box.innerHTML = "<div class='info'>Nenhum lote com animais ativos.</div>";
}

// ----------------------------------------------------------- Manejos (histórico)
const TIPO_MANEJO_LABEL = {
  manejo: "Manejo", compra: "Compra", venda_fazenda: "Venda (fazenda)",
  venda_morto: "Venda (morto)", legado: "Pesagem (planilha)",
};

async function carregarManejos() {
  const box = document.getElementById("lista-manejos");
  box.innerHTML = "<div class='info'>⏳ Carregando manejos... (pode levar alguns segundos na primeira vez)</div>";
  let lista;
  try {
    lista = await api.get("/api/manejos");
  } catch (e) {
    box.innerHTML = `<div class="info">⚠ Erro ao carregar: ${esc(e.message)}. <a href="#" id="manejos-retentar">Tentar de novo</a></div>`;
    document.getElementById("manejos-retentar").onclick = (ev) => { ev.preventDefault(); carregarManejos(); };
    return;
  }
  box.innerHTML = "";
  if (!lista.length) { box.innerHTML = "<div class='info'>Nenhum manejo registrado ainda.</div>"; return; }
  lista.forEach((m) => {
    const div = document.createElement("div");
    div.className = "card-manejo";
    const badgeStatus = m.status === "aberta" ? `<span class="tag">em andamento</span>` : "";
    const lotesTxt = m.lotes.length ? m.lotes.join(", ") : "";
    div.innerHTML = `
      <div class="card-manejo-topo">
        <b>${fmt.data(m.data)}</b>
        <span class="tipo-manejo">${TIPO_MANEJO_LABEL[m.tipo] || m.tipo}</span>
        ${badgeStatus}
      </div>
      <div class="sub">${lotesTxt || (m.tipo === "legado" ? "Histórico anterior ao app" : "")}</div>
      <div class="card-manejo-numeros">
        <span><b>${m.total}</b> pesados</span>
        <span>peso médio <b>${fmt.peso(m.peso_medio)}</b></span>
      </div>`;
    div.onclick = () => abrirManejo(m.chave);
    box.appendChild(div);
  });
}

async function abrirManejo(chave) {
  const [prefixo, valor] = [chave.slice(0, 1), chave.slice(2)];
  const url = prefixo === "s" ? `/api/manejos/sessao/${valor}` : `/api/manejos/legado/${valor}`;
  let d;
  try {
    d = await api.get(url);
  } catch (e) {
    alert("Erro ao abrir o manejo: " + e.message);
    return;
  }
  const s = d.sessao;
  const ehDono = usuarioAtual && usuarioAtual.papel === "dono";
  const linhas = d.pesados
    .map((p) => `
      <tr data-id="${p.id}" data-animal="${p.animal_id}">
        <td>${p.ordem ?? "—"}</td>
        <td><b>${esc(p.brinco)}</b></td>
        <td>${esc(p.tipo || "")}${p.raca ? " · " + esc(p.raca) : ""}</td>
        <td>${ehDono
          ? `<input type="number" step="0.1" class="manejo-peso" value="${p.peso}" style="width:5.5em">`
          : fmt.peso(p.peso)}</td>
        ${"destino" in p ? `<td>${esc(p.destino || "—")}</td>` : ""}
        ${ehDono ? `<td style="white-space:nowrap">
          <button class="manejo-salvar" title="salvar peso">✓</button>
          <button class="manejo-apagar perigo" title="apagar esta pesagem">×</button>
        </td>` : ""}
      </tr>`)
    .join("");
  const colDestino = d.pesados.length && "destino" in d.pesados[0] ? "<th>Destino</th>" : "";
  const colAcoes = ehDono ? "<th></th>" : "";
  const ncols = 4 + (colDestino ? 1 : 0) + (colAcoes ? 1 : 0);

  const ficha = document.getElementById("ficha");
  ficha.innerHTML = `
    <h2>${TIPO_MANEJO_LABEL[s.tipo] || s.tipo} — ${fmt.data(s.data)}</h2>
    <div class="sub">${[...s.origens, ...s.sublotes].join(", ") || (s.tipo === "legado" ? "Histórico anterior ao app" : "")}</div>

    <div class="grid-2 ficha-secao">
      <div class="destaque"><div class="rotulo">Pesados</div><div class="num">${d.total}</div></div>
      <div class="destaque"><div class="rotulo">Peso médio</div><div class="num">${fmt.peso(d.peso_medio)}</div></div>
    </div>
    <div class="grid-2 ficha-secao">
      <div class="destaque"><div class="rotulo">GMD médio</div><div class="num">${d.gmd_medio == null ? "—" : d.gmd_medio.toFixed(3)}</div></div>
      ${s.status ? `<div class="destaque"><div class="rotulo">Situação</div><div class="num" style="font-size:1rem">${s.status === "aberta" ? "Em andamento" : "Finalizada"}</div></div>` : "<div></div>"}
    </div>

    <div class="ficha-secao">
      <h3>Animais pesados</h3>
      <table>
        <thead><tr><th>#</th><th>Brinco</th><th>Tipo/Raça</th><th>Peso</th>${colDestino}${colAcoes}</tr></thead>
        <tbody>${linhas || `<tr><td colspan=${ncols}>Nenhum animal</td></tr>`}</tbody>
      </table>
    </div>`;
  modal.classList.remove("escondido");

  if (ehDono) {
    const urlEditar = (pid, animalId) => prefixo === "s"
      ? `/api/sessoes/${valor}/pesagens/${pid}` : `/api/animais/${animalId}/pesagens/${pid}`;
    ficha.querySelectorAll(".manejo-salvar").forEach((btn) => {
      btn.onclick = async () => {
        const tr = btn.closest("tr");
        const peso = parseFloat(tr.querySelector(".manejo-peso").value);
        if (isNaN(peso) || peso <= 0) { alert("Peso inválido."); return; }
        try {
          await api.put(urlEditar(tr.dataset.id, tr.dataset.animal), { peso });
          abrirManejo(chave);
          carregarLista();
        } catch (e) { alert("Erro ao salvar: " + e.message); }
      };
    });
    ficha.querySelectorAll(".manejo-apagar").forEach((btn) => {
      btn.onclick = async () => {
        if (!confirm("Apagar esta pesagem do manejo? Não tem como desfazer.")) return;
        const tr = btn.closest("tr");
        try {
          await api.delete(urlEditar(tr.dataset.id, tr.dataset.animal));
          abrirManejo(chave);
          carregarLista();
        } catch (e) { alert("Erro ao apagar: " + e.message); }
      };
    });
  }
}

// Ordena "9" antes de "10" (numérico quando dá, senão por texto).
function comparaBrinco(a, b) {
  const na = parseFloat(a), nb = parseFloat(b);
  if (!isNaN(na) && !isNaN(nb)) return na - nb;
  return String(a).localeCompare(String(b));
}

async function abrirLote(loteId, nome) {
  const animais = await api.get("/api/animais?lote=" + encodeURIComponent(nome) + "&status=ativo");
  const ficha = document.getElementById("ficha");
  const ordem = { coluna: "brinco", dir: 1 };

  function renderTabela() {
    const marcadosAntes = new Set([...document.querySelectorAll(".lote-chk:checked")].map((c) => c.value));
    const ordenados = animais.slice().sort((a, b) => {
      const cmp = ordem.coluna === "peso"
        ? (a.ultimo_peso ?? -Infinity) - (b.ultimo_peso ?? -Infinity)
        : comparaBrinco(a.brinco, b.brinco);
      return cmp * ordem.dir;
    });
    const seta = (col) => (ordem.coluna === col ? (ordem.dir === 1 ? " ▲" : " ▼") : "");
    const box = document.querySelector(".lote-animais");
    box.innerHTML = ordenados.length ? `
      <table>
        <thead><tr>
          <th></th>
          <th class="lote-th" data-col="brinco" style="cursor:pointer">Brinco${seta("brinco")}</th>
          <th class="lote-th" data-col="peso" style="cursor:pointer">Último peso${seta("peso")}</th>
        </tr></thead>
        <tbody>
          ${ordenados.map((a) => `
            <tr>
              <td><input type="checkbox" class="lote-chk" value="${a.id}" ${marcadosAntes.has(String(a.id)) ? "checked" : ""}></td>
              <td><b>${a.brinco}</b> ${a.tipo ? `· ${a.tipo}` : ""}</td>
              <td>${fmt.peso(a.ultimo_peso)}</td>
            </tr>`).join("")}
        </tbody>
      </table>` : "<div class='info'>Sem animais ativos.</div>";
    box.querySelectorAll(".lote-th").forEach((th) => {
      th.onclick = () => {
        const col = th.dataset.col;
        ordem.dir = ordem.coluna === col ? -ordem.dir : 1;
        ordem.coluna = col;
        renderTabela();
      };
    });
  }

  ficha.innerHTML = `
    <h2>Lote ${nome}</h2>
    <div class="ficha-secao">
      <label style="font-weight:600;font-size:0.85rem">Renomear lote</label>
      <div class="linha-pesar">
        <input id="lote-novo-nome" value="${nome}" />
        <button id="lote-renomear">Salvar</button>
      </div>
    </div>

    <div class="ficha-secao">
      <h3>Juntar com outro lote</h3>
      ${await seletorLoteHTML("lote-juntar", "")}
      <button id="lote-juntar" style="margin-top:8px;width:100%">Juntar tudo</button>
      <div class="info">Move todos os ${animais.length} animais para o outro lote.</div>
    </div>

    <div class="ficha-secao">
      <h3>Animais (${animais.length})</h3>
      <div class="info"><a href="#" id="lote-sel-todos">marcar todos</a> · <a href="#" id="lote-sel-nada">desmarcar</a> · clique no título da coluna pra ordenar</div>
      <div class="lote-animais"></div>
      <label style="font-weight:600;font-size:0.85rem;margin-top:10px;display:block">Mover marcados para</label>
      ${await seletorLoteHTML("lote-mover", "")}
      <button id="lote-mover" style="margin-top:8px;width:100%">Mover marcados</button>
    </div>`;

  renderTabela();
  ligarSeletorLote("lote-juntar");
  ligarSeletorLote("lote-mover");
  modal.classList.remove("escondido");

  const marcados = () => [...document.querySelectorAll(".lote-chk:checked")].map((c) => parseInt(c.value));
  document.getElementById("lote-sel-todos").onclick = (e) => {
    e.preventDefault(); document.querySelectorAll(".lote-chk").forEach((c) => (c.checked = true));
  };
  document.getElementById("lote-sel-nada").onclick = (e) => {
    e.preventDefault(); document.querySelectorAll(".lote-chk").forEach((c) => (c.checked = false));
  };
  document.getElementById("lote-renomear").onclick = async () => {
    const novo = document.getElementById("lote-novo-nome").value.trim();
    if (!novo || novo === nome) return;
    try {
      await api.put("/api/lotes/" + loteId, { nome: novo });
      modal.classList.add("escondido");
      carregarLotes();
    } catch (e) { alert(e.message); }
  };
  document.getElementById("lote-mover").onclick = async (ev) => {
    const ids = marcados();
    const destino = valorLote("lote-mover");
    if (!ids.length) { alert("Marque pelo menos um animal."); return; }
    if (!destino) { alert("Escolha o lote destino."); return; }
    const btn = ev.currentTarget;
    btn.disabled = true; btn.textContent = "Movendo...";
    try {
      const r = await api.post("/api/lotes/mover", { animal_ids: ids, destino });
      limparCacheLotes();
      alert(`${r.movidos} animais movidos para ${r.destino}.`);
      abrirLote(loteId, nome);
    } catch (e) {
      alert("Erro ao mover: " + e.message);
      btn.disabled = false; btn.textContent = "Mover marcados";
    }
  };
  document.getElementById("lote-juntar").onclick = async (ev) => {
    const destino = valorLote("lote-juntar");
    if (!destino) { alert("Escolha o lote destino."); return; }
    if (destino === nome) { alert("Escolha um lote diferente do atual."); return; }
    if (!confirm(`Juntar todo o lote ${nome} em ${destino}?`)) return;
    const btn = ev.currentTarget;
    btn.disabled = true; btn.textContent = "Juntando...";
    try {
      const r = await api.post("/api/lotes/juntar", { origem_id: loteId, destino });
      limparCacheLotes();
      alert(`${r.movidos} animais movidos de ${r.origem} para ${r.destino}.`);
      modal.classList.add("escondido");
      carregarLotes();
    } catch (e) {
      alert("Erro ao juntar: " + e.message);
      btn.disabled = false; btn.textContent = "Juntar tudo";
    }
  };
}

// ----------------------------------------------------------- Ficha do animal
const modal = document.getElementById("modal");
document.getElementById("fechar-modal").onclick = () => modal.classList.add("escondido");
// Clicar fora do conteúdo (no fundo escuro) também fecha.
modal.addEventListener("click", (e) => { if (e.target === modal) modal.classList.add("escondido"); });

async function abrirFicha(id) {
  const a = await api.get("/api/animais/" + id);
  const [tipos, racas] = [await opcoes("tipo"), await opcoes("raca")];
  const ficha = document.getElementById("ficha");
  const pesagens = a.pesagens
    .slice()
    .reverse()
    .map((p) => `<tr>
        <td>${fmt.data(p.data)}</td><td>${fmt.peso(p.peso)}</td>
        <td><button class="pesagem-apagar" data-id="${p.id}" title="apagar esta pesagem">×</button></td>
      </tr>`)
    .join("");

  // Histórico de lotes (com datas). a.lotes vem do detalhar_animal.
  const historicoLotes = (a.lotes || [])
    .slice()
    .reverse()
    .map((l) => {
      const fim = l.data_fim ? fmt.data(l.data_fim) : "<b>atual</b>";
      return `<tr><td>${esc(l.lote)}</td><td>${l.data_inicio ? fmt.data(l.data_inicio) : "—"}</td><td>${fim}</td></tr>`;
    }).join("") || "<tr><td colspan=3>Sem histórico</td></tr>";

  ficha.innerHTML = `
    <h2>Brinco ${esc(a.brinco)} ${a.status !== "ativo" ? `<span class="tag ${a.status}">${a.status}</span>` : ""}</h2>
    <div class="sub">${esc(a.tipo || "")} · ${esc(a.raca || "sem raça")} · ${esc(a.lote_atual || "sem lote")}</div>

    <div class="ficha-secao">
      <label style="font-weight:600;font-size:0.85rem">Brinco</label>
      <div class="linha-pesar">
        <input id="f-brinco" value="${esc(a.brinco)}" />
        <button id="f-brinco-salvar">Salvar</button>
      </div>
      <div class="info">Corrija aqui se o número foi digitado errado na hora de pesar.</div>
    </div>

    <div class="grid-2 ficha-secao">
      <div>
        <label style="font-weight:600;font-size:0.85rem">Classificação</label>
        <select id="f-tipo">${opcoesHTML(tipos, a.tipo)}</select>
      </div>
      <div>
        <label style="font-weight:600;font-size:0.85rem">Raça</label>
        <select id="f-raca">${opcoesHTML(racas, a.raca)}</select>
      </div>
    </div>

    <div class="ficha-secao">
      <label style="font-weight:600;font-size:0.85rem">Situação</label>
      <select id="f-status">
        <option value="ativo">Ativo</option>
        <option value="vendido">Vendido</option>
        <option value="perdido">Perdido</option>
        <option value="morto">Morto</option>
      </select>
    </div>

    <div class="ficha-secao">
      <label style="font-weight:600;font-size:0.85rem">Observação</label>
      <textarea id="f-obs" rows="2" style="width:100%">${esc(a.observacao || "")}</textarea>
      <button id="f-obs-salvar" class="secundario" style="margin-top:6px">Salvar observação</button>
    </div>

    <div class="grid-2 ficha-secao">
      <div class="destaque"><div class="rotulo">GMD total</div><div class="num">${a.gmd == null ? "—" : a.gmd.toFixed(3)}</div></div>
      <div class="destaque"><div class="rotulo">Último GMD (uGMD)</div><div class="num">${a.ugmd == null ? "—" : a.ugmd.toFixed(3)}</div></div>
    </div>

    <div class="ficha-secao">
      <h3>GMD por período (comparar pastagens)</h3>
      <div class="grid-2">
        <input type="date" id="gp-inicio" />
        <input type="date" id="gp-fim" />
      </div>
      <button id="gp-calcular" style="margin-top:8px;width:100%">Calcular GMD do período</button>
      <div id="gp-resultado" class="info"></div>
    </div>

    <div class="ficha-secao">
      <h3>Mudar lote</h3>
      <div id="ficha-lote-sel">${await seletorLoteHTML("ficha-lote", a.lote_atual || "")}</div>
      <button id="btn-lote" style="margin-top:8px;width:100%">Mover de lote</button>
    </div>

    <div class="ficha-secao">
      <h3>Histórico de lotes</h3>
      <table><thead><tr><th>Lote</th><th>Entrou</th><th>Saiu</th></tr></thead><tbody>${historicoLotes}</tbody></table>
    </div>

    <div class="ficha-secao">
      <h3>Vender</h3>
      <div class="grid-2">
        <input id="v-rend" placeholder="Rendimento (ex 0.50)" inputmode="decimal" />
        <input id="v-arroba" placeholder="Preço @ líquida" inputmode="decimal" />
      </div>
      <button id="btn-simular" style="margin-top:8px;width:100%">Simular venda</button>
      <div id="v-resultado" class="info"></div>
    </div>

    <div class="ficha-secao">
      <h3>Pesagens (${a.pesagens.length})</h3>
      <table><thead><tr><th>Data</th><th>Peso</th><th></th></tr></thead><tbody>${pesagens || "<tr><td colspan=3>Sem pesagens</td></tr>"}</tbody></table>
    </div>

    <div class="ficha-secao ficha-perigo">
      <h3>Excluir animal</h3>
      <p class="info">Apaga o animal e todo o histórico (pesagens, lotes...). Use só se foi um cadastro feito por engano — não tem como desfazer.</p>
      <button id="f-excluir" class="perigo" style="width:100%">Excluir este animal</button>
    </div>`;

  modal.classList.remove("escondido");
  modal.dataset.animalId = id;
  modal.dataset.tipo = a.tipo || "";

  ligarSeletorLote("ficha-lote");
  document.getElementById("gp-calcular").onclick = () => calcularGmdPeriodo(id);
  document.getElementById("btn-lote").onclick = () => moverLote(id);
  document.getElementById("btn-simular").onclick = () => simularVenda(id, a.tipo);

  // Brinco (corrige número digitado errado).
  document.getElementById("f-brinco-salvar").onclick = async () => {
    const novo = document.getElementById("f-brinco").value.trim();
    if (!novo) { alert("O brinco não pode ficar vazio."); return; }
    try {
      await api.put("/api/animais/" + id, { brinco: novo });
      carregarLista();
      abrirFicha(id);
    } catch (e) { alert("Erro: " + e.message); }
  };

  // Classificação e raça (salvam na hora ao trocar).
  document.getElementById("f-tipo").onchange = async (e) => {
    await api.put("/api/animais/" + id, { tipo: e.target.value || null });
    carregarLista();
  };
  document.getElementById("f-raca").onchange = async (e) => {
    await api.put("/api/animais/" + id, { raca: e.target.value || null });
    carregarLista();
  };
  document.getElementById("f-obs-salvar").onclick = async () => {
    await api.put("/api/animais/" + id, { observacao: document.getElementById("f-obs").value || null });
    document.getElementById("f-obs-salvar").textContent = "Salvo ✓";
    carregarLista();
  };

  // Situação do animal (ativo/vendido/perdido/morto).
  const selStatus = document.getElementById("f-status");
  selStatus.value = a.status;
  selStatus.onchange = async () => {
    await api.put("/api/animais/" + id, { status: selStatus.value });
    carregarLista();
  };

  // Apagar uma pesagem específica (lançamento errado).
  ficha.querySelectorAll(".pesagem-apagar").forEach((btn) => {
    btn.onclick = async () => {
      if (!confirm("Apagar esta pesagem?")) return;
      try {
        await api.delete(`/api/animais/${id}/pesagens/${btn.dataset.id}`);
        abrirFicha(id);
        carregarLista();
      } catch (e) { alert("Erro: " + e.message); }
    };
  });

  // Excluir o animal inteiro — exige digitar o brinco pra confirmar.
  document.getElementById("f-excluir").onclick = async () => {
    const digitado = prompt(`Isso vai apagar o animal ${a.brinco} e TODO o histórico dele.\n\nPra confirmar, digite o brinco (${a.brinco}):`);
    if (digitado === null) return;
    if (digitado.trim() !== a.brinco) { alert("Brinco não confere. Nada foi apagado."); return; }
    try {
      await api.delete("/api/animais/" + id);
      modal.classList.add("escondido");
      limparCacheLotes();
      carregarLista();
      if (cacheAnimais.porBrinco) carregarCacheAnimais().catch(() => {});
    } catch (e) { alert("Erro: " + e.message); }
  };

  // Peão não edita cadastro/pesagens antigas nem exclui nada — esconde esses controles.
  if (!usuarioAtual || usuarioAtual.papel !== "dono") {
    ["f-brinco", "f-brinco-salvar", "f-tipo", "f-raca", "f-obs", "f-obs-salvar",
     "f-status", "f-excluir"].forEach((elId) => {
      const el2 = document.getElementById(elId);
      if (el2) el2.disabled = true;
    });
    ficha.querySelectorAll(".pesagem-apagar").forEach((btn) => (btn.style.visibility = "hidden"));
    const secaoExcluir = document.getElementById("f-excluir").closest(".ficha-secao");
    if (secaoExcluir) secaoExcluir.classList.add("escondido");
  }
}

async function calcularGmdPeriodo(id) {
  const inicio = document.getElementById("gp-inicio").value;
  const fim = document.getElementById("gp-fim").value;
  const params = new URLSearchParams();
  if (inicio) params.set("inicio", inicio);
  if (fim) params.set("fim", fim);
  try {
    const r = await api.get(`/api/animais/${id}/gmd-periodo?` + params);
    document.getElementById("gp-resultado").innerHTML =
      `De ${fmt.data(r.data_inicio)} a ${fmt.data(r.data_fim)} · ${r.dias} dias · ` +
      `ganho ${r.ganho.toFixed(0)} kg · <b>GMD ${r.gmd.toFixed(3)} kg/dia</b>`;
  } catch (e) {
    document.getElementById("gp-resultado").textContent = e.message;
  }
}

async function moverLote(id) {
  const nome = valorLote("ficha-lote");
  if (!nome) { alert("Escolha ou digite o lote destino."); return; }
  await api.post(`/api/animais/${id}/lote?nome_lote=${encodeURIComponent(nome)}`, {});
  limparCacheLotes();
  abrirFicha(id);
  carregarLista();
}

async function simularVenda(id, tipo) {
  const rend = document.getElementById("v-rend").value;
  const arroba = document.getElementById("v-arroba").value;
  if (!arroba) {
    alert("Informe o preço da @");
    return;
  }
  const params = new URLSearchParams({ preco_arroba: arroba });
  if (rend) params.set("rendimento", rend);
  try {
    const r = await api.get(`/api/animais/${id}/venda/simular?` + params);
    document.getElementById("v-resultado").innerHTML =
      `Peso ${fmt.peso(r.peso)} · rend ${(r.rendimento * 100).toFixed(0)}% · ` +
      `${r.arroba_liquida} @ · <b>${fmt.real(r.valor_recebido)}</b>`;
  } catch (e) {
    document.getElementById("v-resultado").textContent = e.message;
  }
}

// ----------------------------------------------------------- Pesagem rápida
const hoje = new Date().toISOString().slice(0, 10);
document.getElementById("pesar-data").value = hoje;

// Mostra dados do animal ao digitar o brinco (igual à mangueira).
let pesarEscolhido = null;   // animal_id escolhido quando há brinco repetido
// Consulta LOCAL no cache (instantânea, sem internet a cada tecla / sem trocar brinco errado).
document.getElementById("pesar-brinco").oninput = () => {
  pesarEscolhido = null;
  document.getElementById("pesar-escolha").classList.add("escondido");
  const brinco = document.getElementById("pesar-brinco").value.trim();
  const box = document.getElementById("pesar-info");
  if (!brinco) { box.textContent = ""; box.className = "mg-info-animal"; return; }
  const cands = animaisPorBrinco(brinco);
  if (!cands.length) {
    box.textContent = "⚠ brinco não cadastrado"; box.className = "mg-info-animal fora"; return;
  }
  if (cands.length > 1) {
    box.textContent = `⚠ ${cands.length} animais com esse brinco — escolha ao salvar`;
    box.className = "mg-info-animal fora";
    return;
  }
  const a = cands[0];
  const gmd = a.gmd == null ? "—" : a.gmd.toFixed(3);
  box.textContent = `${a.tipo || ""}${a.raca ? " · " + a.raca : ""} · ${a.lote || "sem lote"} · último ${a.ultimo_peso ?? "—"} kg · GMD ${gmd}`;
  box.className = "mg-info-animal";
};

async function salvarPesagemRapida(animalId) {
  const brinco = document.getElementById("pesar-brinco").value.trim();
  const peso = parseFloat(document.getElementById("pesar-peso").value);
  const data = document.getElementById("pesar-data").value;
  const msg = document.getElementById("pesar-msg");
  if (!brinco || !peso || !data) return;

  try {
    const r = await api.post("/api/pesagem-rapida", { brinco, peso, data, animal_id: animalId });
    if (r.ambiguidade) {
      mostrarEscolhaPesarRapida(r.animais);
      return;
    }
    if (r.animal) {
      cacheUpsertAnimal({
        id: r.animal.id, brinco: r.animal.brinco, tipo: r.animal.tipo, raca: r.animal.raca,
        lote: r.animal.lote_atual, ultimo_peso: r.animal.ultimo_peso, gmd: r.animal.gmd,
      });
    }
    const li = document.createElement("li");
    li.textContent = `✓ Brinco ${brinco}: ${peso} kg`;
    document.getElementById("pesar-historico").prepend(li);
    msg.textContent = "Salvo!";
    document.getElementById("pesar-brinco").value = "";
    document.getElementById("pesar-peso").value = "";
    document.getElementById("pesar-info").textContent = "";
    document.getElementById("pesar-escolha").classList.add("escondido");
    pesarEscolhido = null;
    document.getElementById("pesar-brinco").focus();
  } catch (e) {
    msg.textContent = "Erro: " + e.message;
  }
}

function mostrarEscolhaPesarRapida(animais) {
  const box = document.getElementById("pesar-escolha");
  box.innerHTML = `<p>Qual animal pesar?</p><div class="acoes"></div>`;
  const acoes = box.querySelector(".acoes");
  animais.forEach((a) => {
    const b = document.createElement("button");
    b.className = "secundario";
    b.textContent = `${a.tipo || "?"} · ${a.lote_atual || "sem lote"} · ${fmt.peso(a.ultimo_peso)}`;
    b.onclick = () => { pesarEscolhido = a.id; salvarPesagemRapida(a.id); };
    acoes.appendChild(b);
  });
  box.classList.remove("escondido");
}

document.getElementById("form-pesar").onsubmit = (ev) => {
  ev.preventDefault();
  salvarPesagemRapida(pesarEscolhido);
};

// ----------------------------------------------------------- Painel
async function carregarPainel() {
  const d = await api.get("/api/dashboard");
  document.getElementById("cards-painel").innerHTML = `
    <div class="card"><div class="num">${d.total}</div><div class="rotulo">Total</div></div>
    <div class="card"><div class="num">${d.ativos}</div><div class="rotulo">Ativos</div></div>
    <div class="card"><div class="num">${d.vendidos}</div><div class="rotulo">Vendidos</div></div>
    <div class="card"><div class="num">${d.gmd_medio ?? "—"}</div><div class="rotulo">GMD médio</div></div>
    <div class="card"><div class="num">${d.pesagens}</div><div class="rotulo">Pesagens</div></div>`;
}

// Início: se já tem token salvo, tenta validar; senão mostra a tela de login.
(async function iniciar() {
  const token = localStorage.getItem(TOKEN_KEY);
  if (!token) { iniciarTelaLogin(); return; }
  try {
    const eu = await api.get("/api/auth/eu");
    usuarioAtual = eu;
    document.getElementById("tela-login").classList.add("escondido");
    document.getElementById("app-conteudo").classList.remove("escondido");
    document.getElementById("usuario-logado-nome").textContent = `${eu.nome} (${eu.papel})`;
    aplicarPermissoes();
    carregarLista();
    carregarCacheAnimais().catch(() => {});   // pré-carrega os animais (consulta local)
    if (typeof mgInit === "function") mgInit();
  } catch (e) {
    iniciarTelaLogin();
  }
})();
