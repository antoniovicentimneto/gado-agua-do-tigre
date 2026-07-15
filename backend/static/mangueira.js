// Tela de lançamento de peso na mangueira (sessão de pesagem).

const mg = {
  sessaoId: null,
  loteAtivo: null,   // sublote "grudado" onde caem os animais pesados
  estado: null,
};

const el = (id) => document.getElementById(id);

// ----------------------------------------------------------- Inicialização da aba
async function mgInit() {
  if (!el("mg-data").value) el("mg-data").value = new Date().toISOString().slice(0, 10);
  await mgCarregarLotes();
  await mgCarregarAbertas();
  await mgPreencherOpcoes();
}

// Preenche os selects de tipo/raça das "mais opções" com as listas da config.
async function mgPreencherOpcoes() {
  const [tipos, racas] = [await opcoes("tipo"), await opcoes("raca")];
  if (el("mg-op-tipo")) el("mg-op-tipo").innerHTML = opcoesHTML(tipos, "", "— manter —");
  if (el("mg-op-raca")) el("mg-op-raca").innerHTML = opcoesHTML(racas, "", "— manter —");
}

// Liga/desliga o painel de "mais opções".
el("mg-mais-toggle").onclick = () => el("mg-mais").classList.toggle("escondido");

function mgLimparMaisOpcoes() {
  el("mg-mais").classList.add("escondido");
  el("mg-op-tipo").value = "";
  el("mg-op-raca").value = "";
  el("mg-op-dentes").value = "";
  el("mg-op-obs").value = "";
}

// Reage ao clique na aba Mangueira (em adição ao handler de troca de aba do app.js).
document.querySelector('.abas button[data-aba="mangueira"]')
  .addEventListener("click", mgInit);

async function mgCarregarLotes() {
  // Só lotes que têm animais ativos na fazenda (com a contagem).
  const lotes = await api.get("/api/lotes?somente_ativos=true");
  const sel = el("mg-origens");
  sel.innerHTML = "";
  lotes.forEach((l) => {
    const o = document.createElement("option");
    o.value = l.nome;
    o.textContent = `${l.nome} (${l.ativos})`;
    sel.appendChild(o);
  });
}

async function mgCarregarAbertas() {
  const abertas = await api.get("/api/sessoes/abertas");
  const box = el("mg-abertas");
  if (!abertas.length) { box.innerHTML = ""; return; }
  box.innerHTML = "<label>Sessões abertas (retomar)</label>";
  abertas.forEach((s) => {
    const div = document.createElement("div");
    div.className = "mg-aberta";
    div.innerHTML = `<span>#${s.id} · ${s.tipo} · ${s.origens.join(", ")} · ${s.pesados} pesados</span>`;
    const b = document.createElement("button");
    b.textContent = "Retomar";
    b.onclick = () => mgAbrirSessao(s.id);
    div.appendChild(b);
    box.appendChild(div);
  });
}

// Mostra os campos certos conforme o tipo de sessão.
el("mg-tipo").onchange = async () => {
  const t = el("mg-tipo").value;
  const ehCompra = t === "compra";
  el("mg-campos-compra").classList.toggle("escondido", !ehCompra);
  el("mg-campos-venda").classList.toggle("escondido", t !== "venda_fazenda" && t !== "venda_morto");
  // Na compra não se escolhe lote de origem (são animais novos) — só o destino.
  el("mg-bloco-origens").classList.toggle("escondido", ehCompra);
  if (ehCompra && !el("mg-compra-destino").dataset.pronto) {
    el("mg-compra-destino").innerHTML = await seletorLoteHTML("mg-compra", "");
    ligarSeletorLote("mg-compra");
    el("mg-compra-destino").dataset.pronto = "1";
  }
};

// ----------------------------------------------------------- Sublotes na abertura
el("mg-separar").onchange = async (e) => {
  el("mg-sublotes-area").classList.toggle("escondido", !e.target.checked);
  if (e.target.checked && !el("mg-sublotes-lista").children.length) {
    await mgAddSubloteInput(); await mgAddSubloteInput();
  }
};

let mgSubloteSeq = 0;
// Cada sublote é escolhido de uma lista (lotes já cadastrados) ou criado novo.
async function mgAddSubloteInput() {
  const prefixo = "mg-sub-ab-" + (mgSubloteSeq++);
  const row = document.createElement("div");
  row.className = "mg-sublote-row";
  row.dataset.prefixo = prefixo;
  row.style.marginBottom = "6px";
  row.innerHTML = await seletorLoteHTML(prefixo, "", true);
  el("mg-sublotes-lista").appendChild(row);
  ligarSeletorLote(prefixo);
}
el("mg-add-sublote").onclick = mgAddSubloteInput;

// ----------------------------------------------------------- Iniciar sessão
el("mg-iniciar").onclick = async () => {
  const tipo = el("mg-tipo").value;
  const ehCompra = tipo === "compra";

  let origens, separar, sublotes;
  if (ehCompra) {
    // Compra: sem lote de origem; o destino vira o lote ativo (onde entram os comprados).
    const destino = valorLote("mg-compra");
    if (!destino) { alert("Escolha o lote de destino dos animais comprados."); return; }
    origens = [];
    separar = true;
    sublotes = [destino];
  } else {
    origens = [...el("mg-origens").selectedOptions].map((o) => o.value);
    if (!origens.length) { alert("Escolha pelo menos um lote para pesar."); return; }
    separar = el("mg-separar").checked;
    sublotes = separar
      ? [...document.querySelectorAll(".mg-sublote-row")].map((r) => valorLote(r.dataset.prefixo)).filter(Boolean)
      : [];
  }

  const dados = {
    tipo,
    data: el("mg-data").value,
    lotes_origem: origens,
    separar_lotes: separar,
    sublotes,
    preco_kg: parseFloat(el("mg-preco-kg").value) || null,
    preco_arroba: parseFloat(el("mg-preco-arroba").value) || null,
    vendedor: el("mg-vendedor").value || null,
  };
  const btn = el("mg-iniciar");
  const textoOriginal = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Abrindo...";
  try {
    mgUltimoTipoCompra = mgUltimaRacaCompra = "";   // cada compra começa sem padrão
    const estado = await api.post("/api/sessoes", dados);
    mg.sessaoId = estado.sessao.id;
    mgRenderEstado(estado);
    mgMostrarSessao();
    await carregarCacheAnimais();   // carrega os animais na memória p/ consulta local
  } catch (e) {
    alert("Erro ao iniciar a pesagem: " + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = textoOriginal;
  }
};

function mgMostrarSessao() {
  el("mg-abertura").classList.add("escondido");
  el("mg-sessao").classList.remove("escondido");
}

el("mg-cancelar").onclick = async () => {
  if (!confirm("Cancelar esta sessão? Ela será apagada (só funciona porque ainda não tem nenhuma pesagem).")) return;
  try {
    await api.delete(`/api/sessoes/${mg.sessaoId}`);
  } catch (e) {
    alert("Erro ao cancelar: " + e.message);
    return;
  }
  mg.sessaoId = null;
  el("mg-sessao").classList.add("escondido");
  el("mg-abertura").classList.remove("escondido");
  await mgInit();
};

el("mg-encerrar").onclick = async () => {
  // Volta para a abertura; a sessão continua aberta e pode ser retomada.
  mg.sessaoId = null;
  el("mg-sessao").classList.add("escondido");
  el("mg-abertura").classList.remove("escondido");
  await mgInit();
};

async function mgAbrirSessao(id) {
  mg.sessaoId = id;
  const estado = await api.get("/api/sessoes/" + id);
  mgRenderEstado(estado);
  mgMostrarSessao();
  await carregarCacheAnimais();   // carrega os animais na memória p/ consulta local
}

// ----------------------------------------------------------- Render do estado
function mgRenderEstado(estado) {
  mg.estado = estado;
  const s = estado.sessao;
  el("mg-titulo").textContent = `#${s.id} · ${s.tipo}`;
  el("mg-subtitulo").textContent = `${s.data.split("-").reverse().join("/")} · ${s.origens.join(", ")}`;
  // Só dá pra cancelar enquanto não foi pesado nenhum animal.
  el("mg-cancelar").classList.toggle("escondido", estado.contadores.pesados > 0);

  // Botões de lote ativo (sublotes).
  const box = el("mg-lotes-ativos");
  box.innerHTML = "";
  if (s.sublotes.length) {
    if (!mg.loteAtivo || !s.sublotes.includes(mg.loteAtivo)) mg.loteAtivo = s.sublotes[0];
    s.sublotes.forEach((nome) => {
      const b = document.createElement("button");
      b.textContent = nome;
      b.className = nome === mg.loteAtivo ? "ativo" : "";
      b.onclick = () => { mg.loteAtivo = nome; mgRenderEstado(mg.estado); };
      box.appendChild(b);
    });
    const add = document.createElement("button");
    add.textContent = "+";
    add.title = "novo sublote";
    add.onclick = mgNovoSubloteRapido;
    box.appendChild(add);
  } else {
    mg.loteAtivo = null;
  }

  // A pesar.
  el("mg-falta").textContent = estado.contadores.a_pesar;
  const ap = el("mg-a-pesar");
  ap.innerHTML = "";
  estado.a_pesar.forEach((a) => {
    const d = document.createElement("div");
    d.className = "mg-item";
    d.innerHTML = `<span><b>${a.brinco}</b> <span class="info">${a.tipo || ""}</span></span>`;
    ap.appendChild(d);
  });

  // Pesados.
  el("mg-total").textContent = estado.contadores.pesados;
  const ps = el("mg-pesados");
  ps.innerHTML = "";
  estado.pesados.slice().reverse().forEach((p) => {
    const d = document.createElement("div");
    d.className = "mg-item";
    const destino = p.destino ? `<span class="destino-tag">${p.destino}</span>` : "";
    d.innerHTML = `
      <span><span class="ordem">${p.ordem}</span><b>${p.brinco}</b> ${p.peso} kg ${destino}</span>
      <button class="remover" title="remover">×</button>`;
    d.querySelector(".remover").onclick = () => mgRemover(p.pesagem_id);
    ps.appendChild(d);
  });

  // Totais dos pesados: peso somado + uGMD médio do lote em pesagem.
  const c = estado.contadores;
  const totais = [];
  if (c.peso_total) totais.push(`total <b>${c.peso_total} kg</b>`);
  if (c.ugmd_medio != null) totais.push(`uGMD médio <b>${c.ugmd_medio.toFixed(3)}</b>`);
  el("mg-totais").innerHTML = totais.join(" · ");

  // Contagem por sublote.
  const porSub = estado.contadores.por_sublote;
  el("mg-por-sublote").innerHTML = Object.entries(porSub)
    .map(([k, v]) => `<span><b>${v}</b> ${k}</span>`).join("");

  mgAtualizarCompraPadrao();   // mostra/esconde o "padrão da compra"
}

async function mgNovoSubloteRapido() {
  mgModal(`
    <h2>Adicionar sublote</h2>
    <p class="info">Escolha um lote já existente ou crie um novo. Os animais pesados vão pra ele.</p>
    <div id="mg-sub-caixa">${await seletorLoteHTML("mg-sub", "", true)}</div>
    <button id="mg-sub-ok" style="width:100%;margin-top:12px">Adicionar</button>`);
  ligarSeletorLote("mg-sub");
  el("mg-sub-ok").onclick = async () => {
    const nome = valorLote("mg-sub");
    if (!nome) { alert("Escolha ou digite o nome do sublote."); return; }
    const estado = await api.post(`/api/sessoes/${mg.sessaoId}/sublotes`, { nome });
    mg.loteAtivo = nome;
    el("mg-modal").classList.add("escondido");
    mgRenderEstado(estado);
  };
}

// ----------------------------------------------------------- Info ao digitar o brinco
// Consulta LOCAL (no cache carregado na abertura da sessão): instantânea, sem
// internet a cada tecla e sem risco de "puxar o brinco errado" por resposta atrasada.
el("mg-brinco").oninput = () => {
  const brinco = el("mg-brinco").value.trim();
  const box = el("mg-info-animal");
  if (!brinco) { box.textContent = ""; box.className = "mg-info-animal"; return; }
  const ehCompra = mg.estado && mg.estado.sessao.tipo === "compra";
  const cands = animaisPorBrinco(brinco);

  if (!cands.length) {
    box.textContent = ehCompra ? "novo — cadastre o tipo/raça ao enviar" : "⚠ brinco não cadastrado";
    box.className = ehCompra ? "mg-info-animal" : "mg-info-animal fora";
    return;
  }
  if (ehCompra) {
    box.textContent = `⚠ já existe ${cands.length} animal com esse brinco — vai cadastrar um novo`;
    box.className = "mg-info-animal fora";
    return;
  }
  if (cands.length > 1) {
    box.textContent = `⚠ ${cands.length} animais com esse brinco — escolha ao enviar`;
    box.className = "mg-info-animal fora";
    return;
  }
  const a = cands[0];
  const gmd = a.gmd == null ? "—" : a.gmd.toFixed(3);
  const nomesOrig = new Set((mg.estado.sessao.origens) || []);
  const fora = !nomesOrig.has(a.lote);
  const dados = `${a.tipo || ""}${a.raca ? " · " + a.raca : ""} · ${a.lote || "sem lote"} · último ${a.ultimo_peso ?? "—"} kg · GMD ${gmd}`;
  box.textContent = dados + (fora ? " · ⚠ fora do lote" : "");
  box.className = fora ? "mg-info-animal fora" : "mg-info-animal";
};

// ----------------------------------------------------------- Enviar pesagem
// Lê os campos opcionais de "mais opções" (só os preenchidos).
function mgOpcoesExtras() {
  const e = {};
  const t = el("mg-op-tipo").value; if (t) e.novo_tipo = t;
  const r = el("mg-op-raca").value; if (r) e.nova_raca = r;
  const d = el("mg-op-dentes").value.trim(); if (d) e.dentes = parseInt(d, 10);
  const o = el("mg-op-obs").value.trim(); if (o) e.observacao = o;
  return e;
}

function mgEnviar(extra) {
  return api.post(`/api/sessoes/${mg.sessaoId}/pesar`, {
    brinco: el("mg-brinco").value.trim(),
    peso: parseFloat(el("mg-peso").value),
    destino_lote: mg.loteAtivo,
    ...mgOpcoesExtras(),
    ...extra,
  });
}

async function mgSucesso(r) {
  const msg = el("mg-msg");
  msg.textContent = `✓ ${r.brinco}: ${r.peso} kg${r.destino ? " → " + r.destino : ""} (${r.ordem}º)`;
  msg.className = "mg-msg ok";
  el("mg-form").classList.add("mg-flash");
  setTimeout(() => el("mg-form").classList.remove("mg-flash"), 500);
  // Mantém o cache local atualizado (animal novo ou peso/tipo/raça mudados).
  if (r.animal_id) {
    cacheUpsertAnimal({
      id: r.animal_id, brinco: r.brinco, tipo: r.tipo, raca: r.raca,
      lote: r.destino || r.lote_atual, ultimo_peso: r.peso, gmd: r.gmd,
    });
  }
  el("mg-brinco").value = "";
  el("mg-peso").value = "";
  el("mg-info-animal").textContent = "";
  el("mg-alerta").classList.add("escondido");
  mgLimparMaisOpcoes();
  el("mg-brinco").focus();
  mgRenderEstado(await api.get(`/api/sessoes/${mg.sessaoId}`));
}

// Mostra a pesagem na hora, mesmo sem ter ido pro servidor ainda (fila offline).
function mgSucessoOffline(brinco, peso) {
  const msg = el("mg-msg");
  msg.textContent = `✓ ${brinco}: ${peso} kg (offline, aguardando envio)`;
  msg.className = "mg-msg ok";
  el("mg-form").classList.add("mg-flash");
  setTimeout(() => el("mg-form").classList.remove("mg-flash"), 500);
  el("mg-brinco").value = "";
  el("mg-peso").value = "";
  el("mg-info-animal").textContent = "";
  el("mg-alerta").classList.add("escondido");
  mgLimparMaisOpcoes();
  el("mg-brinco").focus();
}

// Desabilita o botão (com texto de "carregando") enquanto a ação assíncrona roda —
// mostra que o app está trabalhando em vez de parecer travado.
async function mgComCarregando(btn, textoCarregando, fn) {
  const textoOriginal = btn.textContent;
  btn.disabled = true;
  btn.textContent = textoCarregando;
  try {
    return await fn();
  } finally {
    btn.disabled = false;
    btn.textContent = textoOriginal;
  }
}

// Faz o envio de fato: online manda pro servidor; offline guarda na fila.
async function mgEnviarOuFila(extra) {
  const brinco = el("mg-brinco").value.trim();
  const peso = parseFloat(el("mg-peso").value);
  const btn = el("mg-enviar");
  const textoOriginal = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Enviando...";
  try {
    if (!navigator.onLine) {
      filaAdicionar({
        sessaoId: mg.sessaoId, tipo: "pesar",
        dados: { brinco, peso, destino_lote: mg.loteAtivo, forcar: true, ...mgOpcoesExtras(), ...extra },
      });
      mgSucessoOffline(brinco, peso);
      return;
    }
    try {
      const r = await mgEnviar({ forcar: false, ...extra });
      if (r.alerta) return mgMostrarAlerta(r);
      if (r.ok) await mgSucesso(r);
    } catch (e) {
      if (e instanceof TypeError) {
        // Caiu o sinal durante o envio: guarda na fila e segue.
        filaAdicionar({
          sessaoId: mg.sessaoId, tipo: "pesar",
          dados: { brinco, peso, destino_lote: mg.loteAtivo, forcar: true, ...mgOpcoesExtras(), ...extra },
        });
        mgSucessoOffline(brinco, peso);
        return;
      }
      el("mg-msg").textContent = "Erro: " + e.message;
      el("mg-msg").className = "mg-msg erro";
    }
  } finally {
    btn.disabled = false;
    btn.textContent = textoOriginal;
  }
}

el("mg-form").onsubmit = async (ev) => {
  ev.preventDefault();
  const brinco = el("mg-brinco").value.trim();
  const peso = parseFloat(el("mg-peso").value);
  if (!brinco || !peso) return;
  el("mg-alerta").classList.add("escondido");

  const ehCompra = mg.estado && mg.estado.sessao.tipo === "compra";
  const cands = animaisPorBrinco(brinco);   // consulta local (cache)

  // Compra: cadastra um animal NOVO. Se já definiu o padrão (tipo/raça) e o brinco
  // é novo, cadastra direto (ágil). Senão, ou se o brinco já existe, abre a caixa.
  if (ehCompra) {
    if (mgUltimoTipoCompra && cands.length === 0) {
      return mgEnviarOuFila({
        criar_animal: true,
        novo_tipo: mgUltimoTipoCompra || null,
        nova_raca: mgUltimaRacaCompra || null,
      });
    }
    return mgCadastroCompra(brinco, cands.length);
  }

  // Brinco repetido: escolhe localmente qual pesar (funciona online e offline).
  if (cands.length > 1) return mgEscolherDuplicadoLocal(cands);

  await mgEnviarOuFila({});
};

// Seletor de brinco repetido montado a partir do cache (sem depender da rede).
function mgEscolherDuplicadoLocal(cands) {
  const box = el("mg-alerta");
  box.innerHTML = `<p>⚠ ${cands.length} animais com esse brinco. Escolha qual pesar:</p><div class="acoes" id="al-ambiguo"></div>`;
  box.classList.remove("escondido");
  cands.forEach((c) => {
    const b = document.createElement("button");
    b.className = "secundario";
    b.textContent = `${c.tipo || "?"}${c.raca ? " " + c.raca : ""} · ${c.lote || "sem lote"} · ${c.ultimo_peso ?? "—"} kg`;
    b.onclick = () => mgEnviarOuFila({ animal_id: c.id, forcar: true });
    el("al-ambiguo").appendChild(b);
  });
}

// Lembra a última escolha de tipo/raça na compra (o lote costuma ser igual).
let mgUltimoTipoCompra = "";
let mgUltimaRacaCompra = "";

// Cadastro rápido de compra: pede tipo e raça, cria e pesa. Já vem com a última
// escolha selecionada pra não precisar repetir a cada animal do lote.
function mgCadastroCompra(brinco, jaExiste) {
  const box = el("mg-alerta");
  box.innerHTML = `
    ${jaExiste ? `<p>⚠ Já existe ${jaExiste} animal com o brinco ${brinco}. Vai cadastrar um NOVO.</p>` : `<p>Novo animal (compra) — brinco ${brinco}.</p>`}
    <label>Classificação</label>
    <select id="al-c-tipo">${mgTiposOpcoesHTML()}</select>
    <label>Raça</label>
    <select id="al-c-raca">${mgRacasOpcoesHTML()}</select>
    <div class="acoes">
      <button id="al-c-ok">Cadastrar e pesar</button>
      <button id="al-c-cancelar" class="secundario">Cancelar</button>
    </div>`;
  box.classList.remove("escondido");
  // Restaura a última seleção, se ainda existir nas opções.
  if (mgUltimoTipoCompra) el("al-c-tipo").value = mgUltimoTipoCompra;
  if (mgUltimaRacaCompra) el("al-c-raca").value = mgUltimaRacaCompra;
  el("al-c-ok").onclick = () => {
    mgUltimoTipoCompra = el("al-c-tipo").value;
    mgUltimaRacaCompra = el("al-c-raca").value;
    mgAtualizarCompraPadrao();
    mgComCarregando(el("al-c-ok"), "Cadastrando...", () => mgEnviarOuFila({
      criar_animal: true,
      novo_tipo: mgUltimoTipoCompra || null,
      nova_raca: mgUltimaRacaCompra || null,
    }));
  };
  el("al-c-cancelar").onclick = () => box.classList.add("escondido");
}

// Indicador do "padrão da compra" (tipo/raça lembrados) com opção de trocar.
function mgAtualizarCompraPadrao() {
  const box = el("mg-compra-padrao");
  const ehCompra = mg.estado && mg.estado.sessao.tipo === "compra";
  if (!ehCompra || !mgUltimoTipoCompra) { box.classList.add("escondido"); return; }
  box.innerHTML = `Cadastrando como <b>${mgUltimoTipoCompra}${mgUltimaRacaCompra ? " · " + mgUltimaRacaCompra : ""}</b> · <a href="#" id="mg-compra-trocar">trocar</a>`;
  box.classList.remove("escondido");
  el("mg-compra-trocar").onclick = (e) => { e.preventDefault(); mgEditarPadraoCompra(); };
}

// Troca o padrão da compra (só define tipo/raça, sem pesar).
function mgEditarPadraoCompra() {
  const box = el("mg-alerta");
  box.innerHTML = `
    <p>Padrão da compra (vale para os próximos brincos novos):</p>
    <label>Classificação</label>
    <select id="al-c-tipo">${mgTiposOpcoesHTML()}</select>
    <label>Raça</label>
    <select id="al-c-raca">${mgRacasOpcoesHTML()}</select>
    <div class="acoes">
      <button id="al-c-salvar">Salvar padrão</button>
      <button id="al-c-cancelar" class="secundario">Cancelar</button>
    </div>`;
  box.classList.remove("escondido");
  if (mgUltimoTipoCompra) el("al-c-tipo").value = mgUltimoTipoCompra;
  if (mgUltimaRacaCompra) el("al-c-raca").value = mgUltimaRacaCompra;
  el("al-c-salvar").onclick = () => {
    mgUltimoTipoCompra = el("al-c-tipo").value;
    mgUltimaRacaCompra = el("al-c-raca").value;
    box.classList.add("escondido");
    mgAtualizarCompraPadrao();
  };
  el("al-c-cancelar").onclick = () => box.classList.add("escondido");
}

// Opções de tipo/raça (da config) pra usar nos selects síncronos do painel de aviso.
function mgTiposOpcoesHTML() {
  const tipos = (typeof cache !== "undefined" && cache.tipo) || ["Novilha", "Boi", "Vaca", "Bezerro"];
  return tipos.map((t) => `<option>${t}</option>`).join("");
}
function mgRacasOpcoesHTML() {
  const racas = (typeof cache !== "undefined" && cache.raca) || [];
  return `<option value="">— sem raça —</option>` + racas.map((r) => `<option>${r}</option>`).join("");
}

// Painel de aviso conforme o tipo de alerta.
function mgMostrarAlerta(r) {
  const box = el("mg-alerta");
  if (r.alerta === "compra_novo") {
    // Servidor pediu cadastro de compra (rede de segurança se o front não pegou).
    return mgCadastroCompra(r.brinco, r.ja_existe || 0);
  }
  if (r.alerta === "ambiguo") {
    // Brinco repetido: deixa o usuário escolher qual animal pesar.
    box.innerHTML = `<p>⚠ ${r.mensagem}</p><div class="acoes" id="al-ambiguo"></div>`;
    box.classList.remove("escondido");
    r.candidatos.forEach((c) => {
      const b = document.createElement("button");
      b.className = "secundario";
      b.textContent = `${c.tipo || "?"}${c.raca ? " " + c.raca : ""} · ${c.lote || "sem lote"} · ${c.ultimo_peso ?? "—"} kg`;
      b.onclick = () => mgComCarregando(b, "Pesando...", async () => {
        const r2 = await mgEnviar({ animal_id: c.animal_id, forcar: true });
        if (r2.alerta) return mgMostrarAlerta(r2);
        if (r2.ok) await mgSucesso(r2);
      });
      el("al-ambiguo").appendChild(b);
    });
  } else if (r.alerta === "inexistente") {
    box.innerHTML = `
      <p>⚠ ${r.mensagem}</p>
      <select id="al-tipo">${mgTiposOpcoesHTML()}</select>
      <div class="acoes">
        <button id="al-cadastrar">Cadastrar e pesar</button>
        <button id="al-semb" class="secundario">Pesar sem brinco</button>
        <button id="al-cancelar" class="secundario">Cancelar</button>
      </div>`;
    box.classList.remove("escondido");
    el("al-cadastrar").onclick = () => mgComCarregando(el("al-cadastrar"), "Cadastrando...", async () => {
      const r2 = await mgEnviar({ criar_animal: true, tipo: el("al-tipo").value, forcar: true });
      if (r2.ok) await mgSucesso(r2);
    });
    el("al-semb").onclick = mgPesarSemBrinco;
    el("al-cancelar").onclick = () => box.classList.add("escondido");
  } else {
    // fora_do_lote ou ja_pesado: confirma com observação.
    box.innerHTML = `
      <p>⚠ ${r.mensagem}</p>
      <input id="al-obs" placeholder="Observação (opcional)" />
      <div class="acoes">
        <button id="al-forcar">Pesar mesmo assim</button>
        <button id="al-cancelar" class="secundario">Cancelar</button>
      </div>`;
    box.classList.remove("escondido");
    el("al-forcar").onclick = () => mgComCarregando(el("al-forcar"), "Pesando...", async () => {
      const r2 = await mgEnviar({ forcar: true, observacao: el("al-obs").value || null });
      if (r2.ok) await mgSucesso(r2);
    });
    el("al-cancelar").onclick = () => box.classList.add("escondido");
  }
}

// ----------------------------------------------------------- Pesar sem brinco
// Botão compartilhado (mg-sem-brinco e al-semb) — pega o botão clicado pelo evento.
async function mgPesarSemBrinco(ev) {
  const peso = parseFloat(el("mg-peso").value);
  if (!peso) { alert("Digite o peso primeiro."); return; }

  const btn = ev && ev.currentTarget;
  const textoOriginal = btn && btn.textContent;
  if (btn) { btn.disabled = true; btn.textContent = "Pesando..."; }
  try {
    if (!navigator.onLine) {
      filaAdicionar({
        sessaoId: mg.sessaoId,
        tipo: "pesar-sem-brinco",
        dados: { peso, destino_lote: mg.loteAtivo },
      });
      mgSucessoOffline("(sem brinco)", peso);
      return;
    }

    try {
      const r = await api.post(`/api/sessoes/${mg.sessaoId}/pesar-sem-brinco`, {
        peso, destino_lote: mg.loteAtivo,
      });
      if (r.ok) await mgSucesso(r);
    } catch (e) {
      if (e instanceof TypeError) {
        filaAdicionar({
          sessaoId: mg.sessaoId,
          tipo: "pesar-sem-brinco",
          dados: { peso, destino_lote: mg.loteAtivo },
        });
        mgSucessoOffline("(sem brinco)", peso);
        return;
      }
      el("mg-msg").textContent = "Erro: " + e.message;
      el("mg-msg").className = "mg-msg erro";
    }
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = textoOriginal; }
  }
}
el("mg-sem-brinco").onclick = mgPesarSemBrinco;

async function mgRemover(pesagemId) {
  if (!confirm("Remover esta pesagem?")) return;
  try {
    await api.delete(`/api/sessoes/${mg.sessaoId}/pesagens/${pesagemId}`);
    mgRenderEstado(await api.get(`/api/sessoes/${mg.sessaoId}`));
    // Atualiza o cache local — senão o "último peso" mostrado ao digitar o brinco
    // de novo continua com o valor apagado (errado).
    await carregarCacheAnimais();
    el("mg-msg").textContent = "";
  } catch (e) {
    alert("Erro ao remover: " + e.message);
  }
}

// ----------------------------------------------------------- Modal (resumo / vincular)
function mgModal(html) {
  el("mg-modal-conteudo").innerHTML = html;
  el("mg-modal").classList.remove("escondido");
}
el("mg-modal-fechar").onclick = () => el("mg-modal").classList.add("escondido");
// Clicar fora do conteúdo (no fundo escuro) também fecha.
el("mg-modal").addEventListener("click", (e) => {
  if (e.target === el("mg-modal")) el("mg-modal").classList.add("escondido");
});

// ----------------------------------------------------------- Finalizar + resumo
el("mg-finalizar").onclick = async () => {
  if (!confirm("Finalizar a sessão? Os animais vão para os sublotes escolhidos.")) return;
  const res = await api.post(`/api/sessoes/${mg.sessaoId}/finalizar`, {});
  const sub = Object.entries(res.por_sublote).map(([k, v]) => `${v} ${k}`).join(" · ") || "—";
  let html = `
    <h2>Resumo da sessão</h2>
    <div class="grid-2 ficha-secao">
      <div class="destaque"><div class="rotulo">Pesados</div><div class="num">${res.total_pesados}</div></div>
      <div class="destaque"><div class="rotulo">Peso médio</div><div class="num">${res.peso_medio ?? "—"}</div></div>
      <div class="destaque"><div class="rotulo">GMD médio</div><div class="num">${res.gmd_medio ?? "—"}</div></div>
      <div class="destaque"><div class="rotulo">Faltantes</div><div class="num">${res.qtde_faltantes}</div></div>
    </div>
    <p><b>Por sublote:</b> ${sub}</p>
    <p><a href="/api/sessoes/${mg.sessaoId}/exportar">⬇ Exportar CSV</a></p>`;
  if (res.vendas_pendentes.length) {
    html += `<h3>Vendas no gancho pendentes</h3><div id="mg-pend"></div>`;
  }
  mgModal(html);
  if (res.vendas_pendentes.length) mgRenderPendentes();
};

async function mgRenderPendentes() {
  const pend = await api.get("/api/vendas/pendentes");
  const box = el("mg-pend");
  if (!box) return;
  box.innerHTML = "";
  pend.forEach((v) => {
    const d = document.createElement("div");
    d.className = "mg-opcao";
    d.innerHTML = `<b>${v.brinco}</b> · ${v.tipo || ""} · vivo ${v.peso_vivo} kg
      <button class="secundario" style="float:right">Lançar frigorífico</button>`;
    d.querySelector("button").onclick = () => mgCompletarVenda(v.animal_id, v.brinco);
    box.appendChild(d);
  });
  if (!pend.length) box.innerHTML = "<p class='info'>Nenhuma pendente.</p>";
}

async function mgCompletarVenda(animalId, brinco) {
  const rendimento = parseFloat(prompt(`Brinco ${brinco} — rendimento (ex.: 0.52):`));
  const peso_carcaca = parseFloat(prompt("Peso de carcaça (kg):"));
  const preco_arroba = parseFloat(prompt("Preço da @ (R$):"));
  const r = await api.post(`/api/animais/${animalId}/venda/completar`, {
    rendimento: rendimento || null, peso_carcaca: peso_carcaca || null, preco_arroba: preco_arroba || null,
  });
  alert(`Fechado: ${r.arrobas} @ · R$ ${r.valor_recebido}`);
  mgRenderPendentes();
}

// ----------------------------------------------------------- Vincular sem brinco
el("mg-vincular-btn").onclick = async () => {
  const d = await api.get(`/api/sessoes/${mg.sessaoId}/faltantes`);
  mg.vincSel = { temp: null, falt: null };
  const prov = d.provisorios.map((p) => {
    const etq = p.sem_brinco ? '<span class="tag">sem brinco</span>' : "";
    return `<div class="mg-opcao" data-tipo="temp" data-id="${p.animal_id}">${p.brinco} · ${p.peso} kg ${etq}</div>`;
  }).join("") || "<p class='info'>Nenhum animal novo nesta sessão.</p>";
  const falt = d.faltantes.map((f) => {
    const peso = f.ultimo_peso != null ? `${f.ultimo_peso} kg` : "sem peso registrado";
    return `<div class="mg-opcao" data-tipo="falt" data-id="${f.animal_id}">
      ${f.brinco} · ${peso}<br><span class="info">${f.tipo || "?"}${f.raca ? " · " + f.raca : ""}</span>
    </div>`;
  }).join("") || "<p class='info'>Nenhum faltante.</p>";
  mgModal(`
    <h2>Vincular a um animal antigo</h2>
    <p class="info">O animal antigo herda o histórico. Escolha o animal novo (ou sem brinco)
      da sessão e o brinco antigo que ele tinha.</p>
    <div class="mg-vinc-cols">
      <div><h4>Novo / sem brinco</h4>${prov}</div>
      <div><h4>Faltantes (brinco antigo)</h4>${falt}</div>
    </div>
    <label style="font-weight:600;font-size:0.85rem;margin-top:10px;display:block">Brinco novo (opcional)</label>
    <input id="mg-vinc-brinco" placeholder="Deixe vazio p/ usar o brinco do animal escolhido" />
    <button id="mg-vinc-ok" style="width:100%;margin-top:10px">Vincular</button>`);

  el("mg-modal-conteudo").querySelectorAll(".mg-opcao").forEach((o) => {
    o.onclick = () => {
      const tipo = o.dataset.tipo;
      el("mg-modal-conteudo").querySelectorAll(`.mg-opcao[data-tipo="${tipo}"]`)
        .forEach((x) => x.classList.remove("sel"));
      o.classList.add("sel");
      mg.vincSel[tipo] = parseInt(o.dataset.id);
    };
  });
  el("mg-vinc-ok").onclick = async () => {
    if (!mg.vincSel.temp || !mg.vincSel.falt) { alert("Escolha um de cada lado."); return; }
    await api.post(`/api/sessoes/${mg.sessaoId}/vincular`, {
      animal_temp_id: mg.vincSel.temp,
      animal_faltante_id: mg.vincSel.falt,
      novo_brinco: el("mg-vinc-brinco").value.trim() || null,
    });
    el("mg-modal").classList.add("escondido");
    mgRenderEstado(await api.get(`/api/sessoes/${mg.sessaoId}`));
    await carregarCacheAnimais();   // vínculo pode ter mudado brincos
  };
};

// Carrega ao abrir a página (a aba Mangueira é a inicial).
mgInit();
