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

const fmt = {
  gmd: (v) => (v == null ? "—" : v.toFixed(3) + " kg/dia"),
  peso: (v) => (v == null ? "—" : v.toFixed(0) + " kg"),
  data: (v) => (v == null ? "—" : v.split("-").reverse().join("/")),
  real: (v) => (v == null ? "—" : "R$ " + v.toLocaleString("pt-BR", { minimumFractionDigits: 2 })),
};

// ----------------------------------------------------------- Navegação por abas
document.querySelectorAll(".abas button").forEach((b) => {
  b.onclick = () => {
    document.querySelectorAll(".abas button").forEach((x) => x.classList.remove("ativa"));
    document.querySelectorAll(".aba").forEach((x) => x.classList.remove("ativa"));
    b.classList.add("ativa");
    document.getElementById("aba-" + b.dataset.aba).classList.add("ativa");
    if (b.dataset.aba === "painel") carregarPainel();
    if (b.dataset.aba === "usuarios") carregarUsuarios();
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
    document.getElementById("filtros-animal").style.display = porAnimal ? "flex" : "none";
    document.getElementById("lista").style.display = porAnimal ? "block" : "none";
    document.getElementById("lista-lotes").style.display = porAnimal ? "none" : "block";
    document.getElementById("contador").style.display = porAnimal ? "block" : "none";
    if (porAnimal) carregarLista();
    else carregarLotes();
  };
});

async function carregarLotes() {
  const lotes = await api.get("/api/lotes?somente_ativos=true");
  const box = document.getElementById("lista-lotes");
  box.innerHTML = "";
  lotes.forEach((l) => {
    const div = document.createElement("div");
    div.className = "card-lote";
    div.innerHTML = `<span class="nome">${l.nome}</span><span class="qtd">${l.ativos} animais</span>`;
    div.onclick = () => abrirLote(l.id, l.nome);
    box.appendChild(div);
  });
  if (!lotes.length) box.innerHTML = "<div class='info'>Nenhum lote com animais ativos.</div>";
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
      <div class="linha-pesar">
        <input id="lote-juntar-destino" placeholder="Nome do lote destino" />
        <button id="lote-juntar">Juntar tudo</button>
      </div>
      <div class="info">Move todos os ${animais.length} animais para o outro lote.</div>
    </div>

    <div class="ficha-secao">
      <h3>Animais (${animais.length})</h3>
      <div class="info"><a href="#" id="lote-sel-todos">marcar todos</a> · <a href="#" id="lote-sel-nada">desmarcar</a> · clique no título da coluna pra ordenar</div>
      <div class="lote-animais"></div>
      <div class="linha-pesar">
        <input id="lote-mover-destino" placeholder="Mover marcados para..." />
        <button id="lote-mover">Mover</button>
      </div>
    </div>`;

  renderTabela();
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
  document.getElementById("lote-mover").onclick = async () => {
    const ids = marcados();
    const destino = document.getElementById("lote-mover-destino").value.trim();
    if (!ids.length) { alert("Marque pelo menos um animal."); return; }
    if (!destino) { alert("Informe o lote destino."); return; }
    const r = await api.post("/api/lotes/mover", { animal_ids: ids, destino });
    alert(`${r.movidos} animais movidos para ${r.destino}.`);
    abrirLote(loteId, nome);
  };
  document.getElementById("lote-juntar").onclick = async () => {
    const destino = document.getElementById("lote-juntar-destino").value.trim();
    if (!destino) { alert("Informe o lote destino."); return; }
    if (!confirm(`Juntar todo o lote ${nome} em ${destino}?`)) return;
    const r = await api.post("/api/lotes/juntar", { origem_id: loteId, destino });
    alert(`${r.movidos} animais movidos de ${r.origem} para ${r.destino}.`);
    modal.classList.add("escondido");
    carregarLotes();
  };
}

// ----------------------------------------------------------- Ficha do animal
const modal = document.getElementById("modal");
document.getElementById("fechar-modal").onclick = () => modal.classList.add("escondido");

async function abrirFicha(id) {
  const a = await api.get("/api/animais/" + id);
  const ficha = document.getElementById("ficha");
  const pesagens = a.pesagens
    .slice()
    .reverse()
    .map((p) => `<tr><td>${fmt.data(p.data)}</td><td>${fmt.peso(p.peso)}</td></tr>`)
    .join("");

  ficha.innerHTML = `
    <h2>Brinco ${a.brinco} ${a.status !== "ativo" ? `<span class="tag ${a.status}">${a.status}</span>` : ""}</h2>
    <div class="sub">${a.tipo || ""} · ${a.raca || "sem raça"} · ${a.lote_atual || "sem lote"}</div>

    <div class="ficha-secao">
      <label style="font-weight:600;font-size:0.85rem">Situação</label>
      <select id="f-status">
        <option value="ativo">Ativo</option>
        <option value="vendido">Vendido</option>
        <option value="perdido">Perdido</option>
        <option value="morto">Morto</option>
      </select>
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
      <div class="linha-pesar">
        <input id="novo-lote" placeholder="Novo lote" />
        <button id="btn-lote">Mover</button>
      </div>
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
      <table><thead><tr><th>Data</th><th>Peso</th></tr></thead><tbody>${pesagens || "<tr><td colspan=2>Sem pesagens</td></tr>"}</tbody></table>
    </div>`;

  modal.classList.remove("escondido");
  modal.dataset.animalId = id;
  modal.dataset.tipo = a.tipo || "";

  document.getElementById("gp-calcular").onclick = () => calcularGmdPeriodo(id);
  document.getElementById("btn-lote").onclick = () => moverLote(id);
  document.getElementById("btn-simular").onclick = () => simularVenda(id, a.tipo);

  // Situação do animal (ativo/vendido/perdido/morto).
  const selStatus = document.getElementById("f-status");
  selStatus.value = a.status;
  selStatus.onchange = async () => {
    await api.put("/api/animais/" + id, { status: selStatus.value });
    carregarLista();
  };
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
  const nome = document.getElementById("novo-lote").value.trim();
  if (!nome) return;
  await api.post(`/api/animais/${id}/lote?nome_lote=${encodeURIComponent(nome)}`, {});
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

document.getElementById("form-pesar").onsubmit = async (ev) => {
  ev.preventDefault();
  const brinco = document.getElementById("pesar-brinco").value.trim();
  const peso = parseFloat(document.getElementById("pesar-peso").value);
  const data = document.getElementById("pesar-data").value;
  const msg = document.getElementById("pesar-msg");
  if (!brinco || !peso || !data) return;

  try {
    const r = await api.post("/api/pesagem-rapida", { brinco, peso, data });
    if (r.ambiguidade) {
      msg.textContent = r.mensagem + " Use a aba Rebanho para escolher o animal certo.";
      return;
    }
    const li = document.createElement("li");
    li.textContent = `✓ Brinco ${brinco}: ${peso} kg`;
    document.getElementById("pesar-historico").prepend(li);
    msg.textContent = "Salvo!";
    document.getElementById("pesar-brinco").value = "";
    document.getElementById("pesar-peso").value = "";
    document.getElementById("pesar-brinco").focus();
  } catch (e) {
    msg.textContent = "Erro: " + e.message;
  }
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
    if (typeof mgInit === "function") mgInit();
  } catch (e) {
    iniciarTelaLogin();
  }
})();
