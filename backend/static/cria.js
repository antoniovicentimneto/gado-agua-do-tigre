// Rebanho › Cria: vacas e bezerros em formato de planilha, com duas visões:
//  - Vacas: situação (com bezerro / solteira), prenhez, bezerro ao pé, "+ bezerro".
//  - Bezerros: TODOS os bezerros, com mãe e nascimento editáveis na própria linha.
// Os dados vêm numa chamada só (/api/cria); filtro, busca e ordenação rodam no aparelho.

const cr = {
  dados: null,
  visao: "vacas",             // vacas | bezerros
  filtroV: "todas",           // todas | com_bezerro | solteiras | prenhes | frigorifico
  filtroB: "todos",           // todos | sem_mae | sem_data | femeas | machos
  busca: "",
  novilhas: false,            // incluir novilhas na visão Vacas (1ª cria)
  ordem: { vacas: { col: "brinco", dir: 1 }, bezerros: { col: "brinco", dir: 1 } },
  editando: null,             // { id, campo } da célula em edição na visão Bezerros
};

const CR_PRENHEZ = { prenhe: "Prenhe (toque)", mojando: "Mojando", vazia: "Vazia (toque)" };
const CR_SEXO = { F: "Fêmea", M: "Macho" };
const crHoje = () => new Date().toLocaleDateString("sv-SE");   // data local AAAA-MM-DD

// Idade legível do bezerro a partir dos dias de vida.
function crIdade(dias) {
  if (dias == null) return "";
  if (dias < 60) return `${dias} dias`;
  const meses = Math.floor(dias / 30.4);
  return meses < 24 ? `${meses} meses` : `${Math.floor(meses / 12)} anos`;
}

async function carregarCria() {
  const box = document.getElementById("lista-cria");
  if (!cr.dados) box.innerHTML = "<div class='info'>⏳ Carregando vacas e bezerros...</div>";
  try {
    cr.dados = await api.get("/api/cria" + (cr.novilhas ? "?novilhas=true" : ""));
  } catch (e) {
    box.innerHTML = `<div class="info">⚠ Erro ao carregar: ${esc(e.message)}. <a href="#" id="cr-retentar">Tentar de novo</a></div>`;
    document.getElementById("cr-retentar").onclick = (ev) => { ev.preventDefault(); carregarCria(); };
    return;
  }
  crRender();
}

// ----------------------------------------------------------- Colunas das duas visões
// valor: usado pra ordenar · texto: o que vai pro Excel · html: o que aparece na tela
const crBezerroAoPe = (m) => m.crias.filter((c) => c.ao_pe);

const CR_COL_VACAS = [
  { id: "brinco", rot: "Brinco", valor: (m) => m.brinco, texto: (m) => m.brinco,
    html: (m) => `<a href="#" class="cr-ficha" data-id="${m.id}"><b>${esc(m.brinco)}</b></a> <span class="info">${esc(m.tipo || "")}</span>` },
  { id: "situacao", rot: "Situação", valor: (m) => m.situacao,
    texto: (m) => (m.situacao === "com_bezerro" ? "com bezerro" : "solteira"),
    html: (m) => (m.situacao === "com_bezerro"
      ? `<span class="tag cr-bezerro">com bezerro</span>` : `<span class="tag cr-solteira">solteira</span>`) },
  { id: "prenhez", rot: "Prenhez", valor: (m) => m.prenhez || "", texto: (m) => m.prenhez || "",
    html: (m) => `<select class="cr-prenhez" title="${m.prenhez ? "marcado em " + fmt.data(m.prenhez_data) : "marcar prenhez"}">
        <option value="">—</option>
        ${Object.entries(CR_PRENHEZ).map(([v, t]) => `<option value="${v}" ${m.prenhez === v ? "selected" : ""}>${t}</option>`).join("")}
      </select>` },
  { id: "bezerro", rot: "Bezerro ao pé", valor: (m) => (crBezerroAoPe(m)[0] || {}).brinco || "",
    texto: (m) => crBezerroAoPe(m).map((c) => c.brinco).join(", "),
    html: (m) => crBezerroAoPe(m).map((c) =>
      `<a href="#" class="cr-ficha" data-id="${c.id}"><b>${esc(c.brinco)}</b></a>${c.idade_dias != null ? ` <span class="info">${crIdade(c.idade_dias)}</span>` : ""}`).join("<br>") || "—" },
  { id: "nasceu", rot: "Nasceu", valor: (m) => (crBezerroAoPe(m)[0] || {}).nascimento || "",
    texto: (m) => crBezerroAoPe(m).map((c) => (c.nascimento ? fmt.data(c.nascimento) : "")).join(", "),
    html: (m) => crBezerroAoPe(m).map((c) => (c.nascimento ? fmt.data(c.nascimento) : "—")).join("<br>") || "—" },
  { id: "crias", rot: "Crias", num: true, valor: (m) => m.total_crias, texto: (m) => m.total_crias,
    html: (m) => `<span title="${m.ultimo_parto ? "último parto " + fmt.data(m.ultimo_parto) : ""}${m.intervalo_partos_dias ? " · intervalo " + Math.round(m.intervalo_partos_dias / 30.4) + " meses" : ""}">${m.total_crias}</span>` },
  { id: "peso", rot: "Último peso", num: true, valor: (m) => m.ultimo_peso, texto: (m) => m.ultimo_peso,
    html: (m) => fmt.peso(m.ultimo_peso) },
  { id: "lote", rot: "Lote", valor: (m) => m.lote || "", texto: (m) => m.lote || "", html: (m) => esc(m.lote || "—") },
  { id: "acao", rot: "", semOrdem: true, semExcel: true,
    html: () => `<button class="secundario cr-nasceu">+ bezerro</button>` },
];

const CR_COL_BEZERROS = [
  { id: "brinco", rot: "Brinco", valor: (b) => b.brinco, texto: (b) => b.brinco,
    html: (b) => `<a href="#" class="cr-ficha" data-id="${b.id}"><b>${esc(b.brinco)}</b></a>${b.sem_brinco ? ` <span class="tag neutro">sem brinco</span>` : ""}` },
  { id: "sexo", rot: "Sexo", valor: (b) => b.sexo || "", texto: (b) => CR_SEXO[b.sexo] || "",
    html: (b) => CR_SEXO[b.sexo] || esc(b.tipo || "—") },
  { id: "mae", rot: "Mãe", valor: (b) => (b.mae ? b.mae.brinco : ""), texto: (b) => (b.mae ? b.mae.brinco : ""),
    brinco: true, html: (b) => crCelulaEditavel(b, "mae") },
  { id: "nascimento", rot: "Nascimento", valor: (b) => b.nascimento || "",
    texto: (b) => (b.nascimento ? fmt.data(b.nascimento) : ""), html: (b) => crCelulaEditavel(b, "nascimento") },
  { id: "idade", rot: "Idade", num: true, valor: (b) => b.idade_dias, texto: (b) => crIdade(b.idade_dias),
    html: (b) => crIdade(b.idade_dias) || "—" },
  { id: "peso", rot: "Último peso", num: true, valor: (b) => b.ultimo_peso, texto: (b) => b.ultimo_peso,
    html: (b) => fmt.peso(b.ultimo_peso) },
  { id: "lote", rot: "Lote", valor: (b) => b.lote || "", texto: (b) => b.lote || "", html: (b) => esc(b.lote || "—") },
];

// Célula de Mãe / Nascimento do bezerro: mostra o valor com um lápis, ou o botão
// "+ mãe" / "+ data" quando falta; em edição vira o campo com ✓ e ✕.
function crCelulaEditavel(b, campo) {
  const editando = cr.editando && cr.editando.id === b.id && cr.editando.campo === campo;
  if (editando) {
    const input = campo === "mae"
      ? `<input class="cr-ed-input" value="${b.mae ? esc(b.mae.brinco) : ""}" placeholder="brinco da mãe" inputmode="numeric" />`
      : `<input class="cr-ed-input" type="date" value="${b.nascimento || ""}" max="${crHoje()}" />`;
    return `<span class="cr-ed">${input}<button class="cr-ed-ok" title="salvar">✓</button><button class="cr-ed-x secundario" title="cancelar">✕</button></span>`;
  }
  if (campo === "mae") {
    return b.mae
      ? `<a href="#" class="cr-ficha" data-id="${b.mae.id}"><b>${esc(b.mae.brinco)}</b></a> <button class="cr-editar" data-campo="mae" title="trocar a mãe">✎</button>`
      : `<button class="cr-editar cr-falta" data-campo="mae">+ mãe</button>`;
  }
  return b.nascimento
    ? `${fmt.data(b.nascimento)} <button class="cr-editar" data-campo="nascimento" title="corrigir a data">✎</button>`
    : `<button class="cr-editar cr-falta" data-campo="nascimento">+ data</button>`;
}

// ----------------------------------------------------------- Filtro, busca e ordem
function crPassaVaca(m) {
  if (cr.busca) {
    const alvo = cr.busca.toLowerCase();
    if (!(m.brinco.toLowerCase().includes(alvo) ||
          m.crias.some((c) => c.brinco.toLowerCase().includes(alvo)))) return false;
  }
  if (cr.filtroV === "com_bezerro") return m.situacao === "com_bezerro";
  if (cr.filtroV === "solteiras") return m.situacao === "solteira";
  if (cr.filtroV === "prenhes") return m.prenhez === "prenhe" || m.prenhez === "mojando";
  if (cr.filtroV === "frigorifico") return m.pode_frigorifico;
  return true;
}

function crPassaBezerro(b) {
  if (cr.busca) {
    const alvo = cr.busca.toLowerCase();
    if (!(b.brinco.toLowerCase().includes(alvo) ||
          (b.mae && b.mae.brinco.toLowerCase().includes(alvo)))) return false;
  }
  if (cr.filtroB === "sem_mae") return !b.mae;
  if (cr.filtroB === "sem_data") return !b.nascimento;
  if (cr.filtroB === "femeas") return b.sexo === "F";
  if (cr.filtroB === "machos") return b.sexo === "M";
  return true;
}

// Linhas da visão atual, já filtradas e ordenadas (vazios sempre no fim).
function crLinhas() {
  const vacas = cr.visao === "vacas";
  const colunas = vacas ? CR_COL_VACAS : CR_COL_BEZERROS;
  const lista = (vacas ? cr.dados.matrizes.filter(crPassaVaca) : cr.dados.bezerros.filter(crPassaBezerro)).slice();
  const { col, dir } = cr.ordem[cr.visao];
  const c = colunas.find((x) => x.id === col) || colunas[0];
  lista.sort((x, y) => {
    const vx = c.valor(x), vy = c.valor(y);
    const semX = vx == null || vx === "", semY = vy == null || vy === "";
    if (semX || semY) return semX === semY ? comparaBrinco(x.brinco, y.brinco) : (semX ? 1 : -1);
    const r = c.num ? vx - vy : (c.id === "brinco" || c.brinco) ? comparaBrinco(vx, vy)
      : String(vx).localeCompare(String(vy), "pt-BR");
    return (r || comparaBrinco(x.brinco, y.brinco)) * dir;
  });
  return { colunas, lista };
}

// ----------------------------------------------------------- Tela
function crRender() {
  const d = cr.dados, r = d.resumo;
  const vacas = cr.visao === "vacas";
  const ehDono = usuarioAtual && usuarioAtual.papel === "dono";
  const box = document.getElementById("lista-cria");
  const { colunas, lista } = crLinhas();
  const ordem = cr.ordem[cr.visao];

  const chip = (grupo, id, rotulo, n) => {
    const ativo = (grupo === "v" ? cr.filtroV : cr.filtroB) === id;
    return `<button data-grupo="${grupo}" data-filtro="${id}" class="${ativo ? "ativo" : ""}">${rotulo} <b>${n}</b></button>`;
  };
  const bz = d.bezerros;
  const filtros = vacas
    ? chip("v", "todas", "Todas", r.matrizes) + chip("v", "com_bezerro", "Com bezerro", r.com_bezerro) +
      chip("v", "solteiras", "Solteiras", r.solteiras) + chip("v", "prenhes", "Prenhes / mojando", r.prenhes) +
      chip("v", "frigorifico", "Podem ir pro frigorífico", r.pode_frigorifico)
    : chip("b", "todos", "Todos", r.bezerros) + chip("b", "sem_mae", "Sem mãe", r.bezerros_sem_mae) +
      chip("b", "sem_data", "Sem data de nascimento", r.bezerros_sem_nascimento) +
      chip("b", "femeas", "Fêmeas", bz.filter((b) => b.sexo === "F").length) +
      chip("b", "machos", "Machos", bz.filter((b) => b.sexo === "M").length);

  const cab = colunas.map((c) => c.semOrdem ? "<th></th>"
    : `<th class="cr-th" data-col="${c.id}">${c.rot}${ordem.col === c.id ? (ordem.dir === 1 ? " ▲" : " ▼") : ""}</th>`).join("");
  const corpo = lista.map((x) => `
    <tr data-id="${x.id}">${colunas.map((c) =>
      `<td class="cr-c-${c.id}" ${c.rot ? `data-rot="${c.rot}"` : ""}>${c.html(x)}</td>`).join("")}</tr>`).join("");

  box.innerHTML = `
    <div class="cr-visao">
      <button data-visao="vacas" class="${vacas ? "ativa" : ""}">🐄 Vacas <b>${r.matrizes}</b></button>
      <button data-visao="bezerros" class="${vacas ? "" : "ativa"}">🍼 Bezerros <b>${r.bezerros}</b></button>
    </div>
    <div class="cr-filtros">${filtros}</div>
    <div class="filtros">
      <input id="cr-busca" placeholder="Buscar brinco da vaca ou do bezerro..." value="${esc(cr.busca)}" />
      <button id="cr-novo">+ Nascimento</button>
    </div>
    <div class="pl-barra">
      <div class="info">${lista.length} ${vacas ? "vaca" : "bezerro"}${lista.length === 1 ? "" : "s"} na lista${vacas
        ? ` · ${r.bezerros_ao_pe} bezerro${r.bezerros_ao_pe === 1 ? "" : "s"} ao pé no total`
        : ` · faltam ${r.bezerros_sem_mae} sem mãe e ${r.bezerros_sem_nascimento} sem data`}</div>
      <div class="pl-acoes">
        ${vacas ? `<label class="check cr-novilhas"><input type="checkbox" id="cr-novilhas" ${cr.novilhas ? "checked" : ""}/> mostrar novilhas também</label>` : ""}
        ${ehDono ? `<button id="cr-excel" class="secundario">⬇ Baixar Excel</button>` : ""}
      </div>
    </div>
    <div class="cr-tabela">
      <table>
        <thead><tr>${cab}</tr></thead>
        <tbody>${corpo || `<tr><td colspan="${colunas.length}" class="cr-vazio">Nenhum ${vacas ? "animal" : "bezerro"} nesse filtro.</td></tr>`}</tbody>
      </table>
    </div>
    <div id="cr-escolha"></div>`;

  // Visão, filtros, busca, ordenação.
  box.querySelectorAll(".cr-visao button").forEach((b) => {
    b.onclick = () => { cr.visao = b.dataset.visao; cr.editando = null; crRender(); };
  });
  box.querySelectorAll(".cr-filtros button").forEach((b) => {
    b.onclick = () => {
      if (b.dataset.grupo === "v") cr.filtroV = b.dataset.filtro; else cr.filtroB = b.dataset.filtro;
      cr.editando = null;
      crRender();
    };
  });
  const busca = document.getElementById("cr-busca");
  busca.oninput = () => {
    cr.busca = busca.value.trim();
    crRender();
    const novo = document.getElementById("cr-busca");   // mantém o cursor ao redesenhar
    novo.focus(); novo.setSelectionRange(novo.value.length, novo.value.length);
  };
  box.querySelectorAll(".cr-th").forEach((th) => {
    th.onclick = () => {
      if (ordem.col === th.dataset.col) ordem.dir = -ordem.dir;
      else { ordem.col = th.dataset.col; ordem.dir = 1; }
      crRender();
    };
  });
  document.getElementById("cr-novo").onclick = () => crAbrirNascimento(null);
  const chkNov = document.getElementById("cr-novilhas");
  if (chkNov) chkNov.onchange = () => { cr.novilhas = chkNov.checked; carregarCria(); };
  if (ehDono) document.getElementById("cr-excel").onclick = crBaixarExcel;

  box.querySelectorAll(".cr-ficha").forEach((a) => {
    a.onclick = (ev) => { ev.preventDefault(); abrirFicha(Number(a.dataset.id)); };
  });

  // Ações por linha.
  box.querySelectorAll("tbody tr[data-id]").forEach((tr) => {
    const id = Number(tr.dataset.id);
    const sel = tr.querySelector(".cr-prenhez");
    if (sel) sel.onchange = () => crMarcarPrenhez(id, sel.value);
    const nasceu = tr.querySelector(".cr-nasceu");
    if (nasceu) nasceu.onclick = () => crAbrirNascimento(d.matrizes.find((m) => m.id === id));
    tr.querySelectorAll(".cr-editar").forEach((b) => {
      b.onclick = () => { cr.editando = { id, campo: b.dataset.campo }; crRender(); };
    });
    const ok = tr.querySelector(".cr-ed-ok");
    if (ok) {
      const input = tr.querySelector(".cr-ed-input");
      input.focus();
      const salvar = () => crSalvarCelula(id, cr.editando.campo, input.value.trim());
      ok.onclick = salvar;
      input.onkeydown = (ev) => {
        if (ev.key === "Enter") salvar();
        if (ev.key === "Escape") { cr.editando = null; crRender(); }
      };
      tr.querySelector(".cr-ed-x").onclick = () => { cr.editando = null; crRender(); };
    }
  });
}

// Salva a mãe ou a data de nascimento digitada na própria linha do bezerro.
async function crSalvarCelula(id, campo, valor) {
  const b = cr.dados.bezerros.find((x) => x.id === id);
  const dados = {};
  try {
    if (campo === "nascimento") {
      dados.nascimento = valor || null;
    } else if (!valor) {
      if (b.mae && !confirm("Remover a mãe deste bezerro?")) return;
      dados.mae_id = null;
    } else {
      // Procura entre os ativos; se não achar, entre todos (mãe já vendida/morta).
      let cands = (await crBuscarPorBrinco(valor)).filter((x) => x.id !== id);
      if (!cands.length) {
        cands = (await api.get("/api/animais?busca=" + encodeURIComponent(valor)))
          .filter((x) => x.brinco === valor && x.id !== id);
      }
      if (!cands.length) { alert(`Não achei animal com o brinco ${valor}.`); return; }
      const mae = cands.length === 1 ? cands[0] : await crEscolher(document.getElementById("cr-escolha"), cands);
      dados.mae_id = mae.id;
    }
    await api.put(`/api/cria/mae/${id}`, dados);
    cr.editando = null;
    await carregarCria();
  } catch (e) { alert("Erro: " + e.message); }
}

async function crBaixarExcel() {
  const { colunas, lista } = crLinhas();
  if (!lista.length) { alert("Nenhum animal na lista."); return; }
  const cols = colunas.filter((c) => !c.semExcel);
  const btn = document.getElementById("cr-excel");
  btn.disabled = true; btn.textContent = "Gerando...";
  try {
    await baixarArquivo("/api/cria/excel", "cria.xlsx", {
      method: "POST",
      headers: cabecalhos({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        titulo: cr.visao === "vacas" ? "Vacas" : "Bezerros",
        cabecalho: cols.map((c) => c.rot),
        linhas: lista.map((x) => cols.map((c) => { const v = c.texto(x); return v == null ? "" : v; })),
      }),
    });
  } catch (e) {
    alert("Não foi possível gerar o Excel: " + e.message);
  } finally {
    btn.disabled = false; btn.textContent = "⬇ Baixar Excel";
  }
}

async function crMarcarPrenhez(animalId, valor) {
  try {
    await api.put(`/api/cria/prenhez/${animalId}`, { prenhez: valor || null, data: crHoje() });
    await carregarCria();
  } catch (e) {
    alert("Erro ao marcar: " + e.message);
    carregarCria();
  }
}

// Acha animais pelo brinco exato (pode haver brinco repetido). Só ativos.
async function crBuscarPorBrinco(brinco) {
  const lista = await api.get("/api/animais?status=ativo&busca=" + encodeURIComponent(brinco));
  return lista.filter((a) => a.brinco === brinco);
}

// Mostra botões pra escolher entre animais de brinco repetido; devolve o escolhido.
function crEscolher(box, candidatos) {
  return new Promise((resolver) => {
    box.innerHTML = `<p class="info">Há ${candidatos.length} animais com esse brinco. Qual é?</p>` +
      candidatos.map((c, i) => `<button class="secundario" data-i="${i}" style="display:block;width:100%;margin-top:6px">
        ${esc(c.tipo || "?")} · ${esc(c.lote_atual || "sem lote")} · ${fmt.peso(c.ultimo_peso)}</button>`).join("");
    box.querySelectorAll("button").forEach((b) => {
      b.onclick = () => { box.innerHTML = ""; resolver(candidatos[Number(b.dataset.i)]); };
    });
  });
}

// Resolve um brinco digitado num animal (pergunta qual, se repetido). null = não achou.
async function crResolverBrinco(brinco, boxEscolha) {
  const cands = await crBuscarPorBrinco(brinco);
  if (!cands.length) return null;
  return cands.length === 1 ? cands[0] : crEscolher(boxEscolha, cands);
}

// ----------------------------------------------------------- Nascimento
function crAbrirNascimento(mae) {
  modalVoltar = null;
  const ficha = document.getElementById("ficha");
  ficha.innerHTML = `
    <h2>Nascimento de bezerro</h2>
    <div class="ficha-secao">
      <label style="font-weight:600;font-size:0.85rem">Brinco da mãe</label>
      <input id="nb-mae" value="${mae ? esc(mae.brinco) : ""}" ${mae ? "readonly" : ""} inputmode="numeric" />
    </div>
    <div class="grid-2 ficha-secao">
      <div>
        <label style="font-weight:600;font-size:0.85rem">Data do nascimento</label>
        <input type="date" id="nb-data" value="${crHoje()}" max="${crHoje()}" />
      </div>
      <div>
        <label style="font-weight:600;font-size:0.85rem">Sexo</label>
        <select id="nb-sexo">
          <option value="">escolha…</option>
          <option value="F">Fêmea</option>
          <option value="M">Macho</option>
        </select>
      </div>
    </div>
    <div class="grid-2 ficha-secao">
      <div>
        <label style="font-weight:600;font-size:0.85rem">Brinco do bezerro</label>
        <input id="nb-brinco" placeholder="em branco = sem brinco ainda" inputmode="numeric" />
      </div>
      <div>
        <label style="font-weight:600;font-size:0.85rem">Peso ao nascer (opcional)</label>
        <input id="nb-peso" placeholder="kg" inputmode="decimal" />
      </div>
    </div>
    <div id="nb-escolha"></div>
    <button id="nb-salvar" style="width:100%">Registrar nascimento</button>
    <div class="info">O bezerro é cadastrado ligado à mãe e entra no mesmo lote dela. Sem brinco, fica com um número provisório — depois é só corrigir o brinco na ficha dele.</div>`;
  modal.classList.remove("escondido");

  document.getElementById("nb-salvar").onclick = async () => {
    const brincoMae = document.getElementById("nb-mae").value.trim();
    const data = document.getElementById("nb-data").value;
    const sexo = document.getElementById("nb-sexo").value;
    const brinco = document.getElementById("nb-brinco").value.trim();
    const peso = parseFloat(document.getElementById("nb-peso").value.replace(",", "."));
    if (!brincoMae) { alert("Informe o brinco da mãe."); return; }
    if (!data) { alert("Informe a data do nascimento."); return; }
    if (!sexo) { alert("Escolha o sexo do bezerro."); return; }
    try {
      let maeId = mae ? mae.id : null;
      if (!maeId) {
        const achada = await crResolverBrinco(brincoMae, document.getElementById("nb-escolha"));
        if (!achada) { alert(`Não achei animal ativo com o brinco ${brincoMae}.`); return; }
        maeId = achada.id;
      }
      if (brinco && (await crBuscarPorBrinco(brinco)).length &&
          !confirm(`Já existe animal ativo com o brinco ${brinco}. Cadastrar o bezerro com esse brinco mesmo assim?`)) return;
      const r = await api.post("/api/cria/nascimento", {
        mae_id: maeId, data, sexo, brinco: brinco || null, peso: isNaN(peso) ? null : peso,
      });
      modal.classList.add("escondido");
      limparCacheLotes();
      if (cacheAnimais.porBrinco) carregarCacheAnimais().catch(() => {});
      await carregarCria();
      alert(`✓ Bezerro ${r.brinco} (${r.tipo}) registrado.`);
    } catch (e) { alert("Erro: " + e.message); }
  };
}

// ----------------------------------------------------------- Seção "Cria" na ficha
// a = resposta de /api/animais/{id} (traz a.mae, a.cria, a.nascimento, a.data_desmame).
function criaSecaoFichaHTML(a) {
  const ehDono = usuarioAtual && usuarioAtual.papel === "dono";
  const c = a.cria || { crias: [] };
  const ehBezerro = (a.tipo || "").toLowerCase().startsWith("bez");
  const ehMatriz = (a.tipo || "").toLowerCase().startsWith("vaca") || c.crias.length > 0;

  const linhasCrias = c.crias.slice().reverse().map((x) => `
    <tr>
      <td><a href="#" class="cf-cria" data-id="${x.id}"><b>${esc(x.brinco)}</b></a> <span class="info">${esc(x.tipo || "")}${x.status !== "ativo" ? " · " + x.status : ""}</span></td>
      <td>${x.nascimento ? fmt.data(x.nascimento) : "—"}</td>
      <td>${x.ao_pe ? "<b>ao pé</b>" : x.data_desmame ? `desmamou ${fmt.data(x.data_desmame)}${x.peso_desmame != null ? " · " + fmt.peso(x.peso_desmame) : ""}` : "—"}</td>
    </tr>`).join("");

  const blocoMatriz = ehMatriz ? `
      <label style="font-weight:600;font-size:0.85rem;display:block;margin-top:10px">Prenhez</label>
      <select id="cf-prenhez">
        <option value="">sem marcação</option>
        ${Object.entries(CR_PRENHEZ).map(([v, t]) => `<option value="${v}" ${c.prenhez === v ? "selected" : ""}>${t}</option>`).join("")}
      </select>
      ${c.prenhez ? `<div class="info">marcado em ${fmt.data(c.prenhez_data)}</div>` : ""}
      <div class="info" style="margin-top:8px">${c.situacao === "com_bezerro" ? "Está <b>com bezerro ao pé</b>." : "Está <b>solteira</b>" + (c.pode_frigorifico ? " — pode ir pro frigorífico." : " (marcada como " + esc(c.prenhez || "") + ").")}${c.intervalo_partos_dias ? ` Intervalo entre partos: ${Math.round(c.intervalo_partos_dias / 30.4)} meses.` : ""}</div>
      ${linhasCrias ? `<table style="margin-top:8px"><thead><tr><th>Cria</th><th>Nasceu</th><th>Situação</th></tr></thead><tbody>${linhasCrias}</tbody></table>` : ""}
      <button id="cf-nasceu" class="secundario" style="margin-top:8px;width:100%">+ Nasceu bezerro desta vaca</button>` : "";

  const podeDesmamar = ehDono && ehBezerro && !a.data_desmame && a.status === "ativo";
  return `
    <div class="ficha-secao" id="cf-secao">
      <h3>Cria</h3>
      <div class="grid-2">
        <div>
          <label style="font-weight:600;font-size:0.85rem">Mãe (brinco)</label>
          <input id="cf-mae" value="${a.mae ? esc(a.mae.brinco) : ""}" placeholder="brinco da mãe" />
          ${a.mae ? `<div class="info"><a href="#" id="cf-mae-abrir">abrir ficha da mãe</a>${a.mae.status !== "ativo" ? " · " + a.mae.status : ""}</div>` : ""}
        </div>
        <div>
          <label style="font-weight:600;font-size:0.85rem">Nascimento</label>
          <input type="date" id="cf-nasc" value="${a.nascimento || ""}" max="${crHoje()}" />
        </div>
      </div>
      <div id="cf-escolha"></div>

      ${a.data_desmame ? `<div class="info" style="margin-top:6px">Desmamado em <b>${fmt.data(a.data_desmame)}</b>.</div>` : ""}
      ${podeDesmamar ? `
        <label style="font-weight:600;font-size:0.85rem;display:block;margin-top:10px">Desmama</label>
        <div class="linha-pesar">
          <input type="date" id="cf-desmama-data" value="${crHoje()}" max="${crHoje()}" />
          <button id="cf-desmamar" class="secundario">Desmamar</button>
        </div>
        <div class="info">Grava a data e muda o tipo pra Novilha/Boi. (Trocar o tipo na mão também grava a data de hoje.)</div>` : ""}
      ${blocoMatriz}
    </div>`;
}

// Acha a mãe pelo brinco digitado na ficha (pergunta qual, se o brinco é repetido).
// Devolve o id, ou null se não achou (já avisa o usuário).
async function criaResolverMae(brinco, idCria, boxEscolha) {
  // Procura entre os ativos; se não achar, entre todos (mãe já vendida/morta).
  let cands = (await crBuscarPorBrinco(brinco)).filter((x) => x.id !== idCria);
  if (!cands.length) {
    cands = (await api.get("/api/animais?busca=" + encodeURIComponent(brinco)))
      .filter((x) => x.brinco === brinco && x.id !== idCria);
  }
  if (!cands.length) { alert(`Não achei animal com o brinco ${brinco} pra ser a mãe.`); return null; }
  return (cands.length === 1 ? cands[0] : await crEscolher(boxEscolha, cands)).id;
}

function criaLigarFicha(a, id) {
  const recarregar = () => {
    abrirFicha(id, modalVoltar);
    carregarLista();
    if (cr.dados) carregarCria();
  };
  const $ = (elId) => document.getElementById(elId);

  if ($("cf-mae-abrir")) {
    $("cf-mae-abrir").onclick = (ev) => { ev.preventDefault(); abrirFicha(a.mae.id, () => abrirFicha(id)); };
  }
  document.querySelectorAll("#cf-secao .cf-cria").forEach((el) => {
    el.onclick = (ev) => { ev.preventDefault(); abrirFicha(Number(el.dataset.id), () => abrirFicha(id)); };
  });

  if ($("cf-desmamar")) {
    $("cf-desmamar").onclick = async () => {
      if (!confirm("Desmamar este bezerro? O tipo muda pra Novilha/Boi.")) return;
      try {
        await api.post(`/api/cria/desmama/${id}`, { data: $("cf-desmama-data").value || null });
        if (cacheAnimais.porBrinco) carregarCacheAnimais().catch(() => {});
        recarregar();
      } catch (e) { alert("Erro: " + e.message); }
    };
  }
  if ($("cf-nasceu")) $("cf-nasceu").onclick = () => crAbrirNascimento({ id, brinco: a.brinco });
}
