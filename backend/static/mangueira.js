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
el("mg-tipo").onchange = () => {
  const t = el("mg-tipo").value;
  el("mg-campos-compra").classList.toggle("escondido", t !== "compra");
  el("mg-campos-venda").classList.toggle("escondido", t !== "venda_fazenda" && t !== "venda_morto");
};

// ----------------------------------------------------------- Sublotes na abertura
el("mg-separar").onchange = (e) => {
  el("mg-sublotes-area").classList.toggle("escondido", !e.target.checked);
  if (e.target.checked && !el("mg-sublotes-lista").children.length) {
    mgAddSubloteInput(); mgAddSubloteInput();
  }
};

function mgAddSubloteInput() {
  const inp = document.createElement("input");
  inp.placeholder = "Nome do sublote (ex.: Gordo)";
  inp.className = "mg-sublote-input";
  el("mg-sublotes-lista").appendChild(inp);
}
el("mg-add-sublote").onclick = mgAddSubloteInput;

// ----------------------------------------------------------- Iniciar sessão
el("mg-iniciar").onclick = async () => {
  const origens = [...el("mg-origens").selectedOptions].map((o) => o.value);
  if (!origens.length) { alert("Escolha pelo menos um lote para pesar."); return; }
  const separar = el("mg-separar").checked;
  const sublotes = separar
    ? [...document.querySelectorAll(".mg-sublote-input")].map((i) => i.value.trim()).filter(Boolean)
    : [];

  const dados = {
    tipo: el("mg-tipo").value,
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
    const estado = await api.post("/api/sessoes", dados);
    mg.sessaoId = estado.sessao.id;
    mgRenderEstado(estado);
    mgMostrarSessao();
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
}

// ----------------------------------------------------------- Render do estado
function mgRenderEstado(estado) {
  mg.estado = estado;
  const s = estado.sessao;
  el("mg-titulo").textContent = `#${s.id} · ${s.tipo}`;
  el("mg-subtitulo").textContent = `${s.data.split("-").reverse().join("/")} · ${s.origens.join(", ")}`;

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

  // Contagem por sublote.
  const porSub = estado.contadores.por_sublote;
  el("mg-por-sublote").innerHTML = Object.entries(porSub)
    .map(([k, v]) => `<span><b>${v}</b> ${k}</span>`).join("");
}

async function mgNovoSubloteRapido() {
  const nome = prompt("Nome do novo sublote:");
  if (!nome) return;
  const estado = await api.post(`/api/sessoes/${mg.sessaoId}/sublotes`, { nome });
  mg.loteAtivo = nome;
  mgRenderEstado(estado);
}

// ----------------------------------------------------------- Info ao digitar o brinco
let mgInfoTimer;
el("mg-brinco").oninput = () => {
  clearTimeout(mgInfoTimer);
  const brinco = el("mg-brinco").value.trim();
  const box = el("mg-info-animal");
  if (!brinco) { box.textContent = ""; box.className = "mg-info-animal"; return; }
  mgInfoTimer = setTimeout(async () => {
    if (!navigator.onLine) { box.textContent = "(sem conexão — sem consulta)"; box.className = "mg-info-animal"; return; }
    let info;
    try {
      info = await api.get(`/api/sessoes/${mg.sessaoId}/info?brinco=${encodeURIComponent(brinco)}`);
    } catch {
      box.textContent = "(sem conexão — sem consulta)"; box.className = "mg-info-animal"; return;
    }
    if (!info.encontrado) {
      box.textContent = "⚠ brinco não cadastrado";
      box.className = "mg-info-animal fora";
      return;
    }
    const gmd = info.gmd == null ? "—" : info.gmd.toFixed(3);
    box.textContent = `${info.tipo || ""} · último ${info.ultimo_peso ?? "—"} kg · GMD ${gmd}`
      + (info.no_lote_origem ? "" : ` · ⚠ fora do lote (${info.lote})`);
    box.className = info.no_lote_origem ? "mg-info-animal" : "mg-info-animal fora";
  }, 200);
};

// ----------------------------------------------------------- Enviar pesagem
function mgEnviar(extra) {
  return api.post(`/api/sessoes/${mg.sessaoId}/pesar`, {
    brinco: el("mg-brinco").value.trim(),
    peso: parseFloat(el("mg-peso").value),
    destino_lote: mg.loteAtivo,
    ...extra,
  });
}

async function mgSucesso(r) {
  const msg = el("mg-msg");
  msg.textContent = `✓ ${r.brinco}: ${r.peso} kg${r.destino ? " → " + r.destino : ""} (${r.ordem}º)`;
  msg.className = "mg-msg ok";
  el("mg-form").classList.add("mg-flash");
  setTimeout(() => el("mg-form").classList.remove("mg-flash"), 500);
  el("mg-brinco").value = "";
  el("mg-peso").value = "";
  el("mg-info-animal").textContent = "";
  el("mg-alerta").classList.add("escondido");
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
  el("mg-brinco").focus();
}

el("mg-form").onsubmit = async (ev) => {
  ev.preventDefault();
  const brinco = el("mg-brinco").value.trim();
  const peso = parseFloat(el("mg-peso").value);
  if (!brinco || !peso) return;
  el("mg-alerta").classList.add("escondido");

  if (!navigator.onLine) {
    // Sem sinal: não dá pra checar duplicidade/fora-do-lote, então lança direto.
    filaAdicionar({
      sessaoId: mg.sessaoId,
      tipo: "pesar",
      dados: { brinco, peso, destino_lote: mg.loteAtivo, forcar: true },
    });
    mgSucessoOffline(brinco, peso);
    return;
  }

  try {
    const r = await mgEnviar({ forcar: false });
    if (r.alerta) return mgMostrarAlerta(r);
    if (r.ok) await mgSucesso(r);
  } catch (e) {
    if (e instanceof TypeError) {
      // Caiu o sinal durante o envio: guarda na fila e segue.
      filaAdicionar({
        sessaoId: mg.sessaoId,
        tipo: "pesar",
        dados: { brinco, peso, destino_lote: mg.loteAtivo, forcar: true },
      });
      mgSucessoOffline(brinco, peso);
      return;
    }
    el("mg-msg").textContent = "Erro: " + e.message;
    el("mg-msg").className = "mg-msg erro";
  }
};

// Painel de aviso conforme o tipo de alerta.
function mgMostrarAlerta(r) {
  const box = el("mg-alerta");
  if (r.alerta === "inexistente") {
    box.innerHTML = `
      <p>⚠ ${r.mensagem}</p>
      <select id="al-tipo">
        <option>Novilha</option><option>Boi</option><option>Vaca</option><option>Bezerro</option>
      </select>
      <div class="acoes">
        <button id="al-cadastrar">Cadastrar e pesar</button>
        <button id="al-semb" class="secundario">Pesar sem brinco</button>
        <button id="al-cancelar" class="secundario">Cancelar</button>
      </div>`;
    box.classList.remove("escondido");
    el("al-cadastrar").onclick = async () => {
      const r2 = await mgEnviar({ criar_animal: true, tipo: el("al-tipo").value, forcar: true });
      if (r2.ok) await mgSucesso(r2);
    };
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
    el("al-forcar").onclick = async () => {
      const r2 = await mgEnviar({ forcar: true, observacao: el("al-obs").value || null });
      if (r2.ok) await mgSucesso(r2);
    };
    el("al-cancelar").onclick = () => box.classList.add("escondido");
  }
}

// ----------------------------------------------------------- Pesar sem brinco
async function mgPesarSemBrinco() {
  const peso = parseFloat(el("mg-peso").value);
  if (!peso) { alert("Digite o peso primeiro."); return; }

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
}
el("mg-sem-brinco").onclick = mgPesarSemBrinco;

async function mgRemover(pesagemId) {
  if (!confirm("Remover esta pesagem?")) return;
  await fetch(`/api/sessoes/${mg.sessaoId}/pesagens/${pesagemId}`, { method: "DELETE" });
  const estado = await api.get(`/api/sessoes/${mg.sessaoId}`);
  mgRenderEstado(estado);
}

// ----------------------------------------------------------- Modal (resumo / vincular)
function mgModal(html) {
  el("mg-modal-conteudo").innerHTML = html;
  el("mg-modal").classList.remove("escondido");
}
el("mg-modal-fechar").onclick = () => el("mg-modal").classList.add("escondido");

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
  const falt = d.faltantes.map((f) =>
    `<div class="mg-opcao" data-tipo="falt" data-id="${f.animal_id}">${f.brinco} · ${f.tipo || ""}</div>`
  ).join("") || "<p class='info'>Nenhum faltante.</p>";
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
  };
};

// Carrega ao abrir a página (a aba Mangueira é a inicial).
mgInit();
