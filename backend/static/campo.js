// Manejo de campo: "Salgar cocho" do lote (aba Pastos) e a aba Sanidade.
//
// Os dois são lançados no pasto, muitas vezes sem sinal: sem rede o lançamento vai pra
// fila offline (com `chave`, o servidor não duplica) e a tela já mostra o resultado.

const CHAVE_SAL_ULTIMO = "gat_sal_ultimo";              // último sal/quantidade por lote
const CHAVE_CARENCIA_PRODUTO = "gat_carencia_produto";  // carência lembrada por remédio
const CHAVE_SANIDADE_OFFLINE = "gat_cache_sanidade";

// "2026-10-17T14:30" na hora do aparelho (valor de <input type="datetime-local">).
function agoraLocalInput() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, "0");
  return `${hojeLocal()}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

function dataHoraBR(iso) {
  if (!iso) return "—";
  const [d, h] = iso.split("T");
  return fmt.data(d) + (h ? " " + h.slice(0, 5) : "");
}

// "hoje", "ontem", "há 5 dias" a partir da última salga.
function textoDiasSalga(s) {
  if (!s || !s.data_hora) return "";
  const dias = Math.round((new Date(hojeLocal() + "T00:00") - new Date(s.data_hora.slice(0, 10) + "T00:00")) / 86400000);
  return dias <= 0 ? "hoje" : dias === 1 ? "ontem" : `há ${dias} dias`;
}

// Select de uma lista do campo (sal, remédio, problema) com "+ novo" no fim.
async function campoSelectHTML(categoria, id, atual, rotuloVazio) {
  let nomes = [];
  try { nomes = await opcoes(categoria); } catch { /* sem rede e sem cache: só o "+ novo" */ }
  const lista = atual && !nomes.includes(atual) ? [atual, ...nomes] : nomes;
  return `
    <select id="${id}">
      ${rotuloVazio != null ? `<option value="">${esc(rotuloVazio)}</option>` : ""}
      ${lista.map((n) => `<option ${n === atual ? "selected" : ""}>${esc(n)}</option>`).join("")}
      <option value="__novo__">+ novo…</option>
    </select>
    <input id="${id}-novo" class="escondido" placeholder="Digite o nome" style="margin-top:6px" />`;
}

function ligarCampoSelect(id) {
  const sel = document.getElementById(id);
  sel.addEventListener("change", () => {
    const novo = sel.value === "__novo__";
    document.getElementById(id + "-novo").classList.toggle("escondido", !novo);
    if (novo) document.getElementById(id + "-novo").focus();
  });
}

// Valor escolhido; se for "+ novo", cadastra na lista (sem rede, só usa o texto).
async function valorCampoSelect(categoria, id) {
  const sel = document.getElementById(id);
  if (sel.value !== "__novo__") return sel.value;
  const campoNovo = document.getElementById(id + "-novo");
  const nome = campoNovo.value.trim();
  if (!nome) return "";
  try {
    await api.post("/api/opcoes/" + categoria, { nome }, PRAZO_LANCAMENTO_MS);
    cache[categoria] = null;
  } catch { /* sem rede: o nome vai no lançamento e entra na lista depois */ }
  // A opção nova passa a aparecer na lista, já escolhida (o próximo lançamento repete).
  const opt = document.createElement("option");
  opt.textContent = nome;
  sel.insertBefore(opt, sel.querySelector('option[value="__novo__"]'));
  sel.value = nome;
  campoNovo.value = "";
  campoNovo.classList.add("escondido");
  return nome;
}

// Envia online; sem rede (ou rede ruim) guarda na fila. Devolve a resposta do servidor
// ou null quando ficou na fila.
async function campoEnviar(url, corpo, rotulo) {
  corpo.chave = novaChave();
  if (redeBoa()) {
    try {
      return await api.post(url, corpo, PRAZO_LANCAMENTO_MS);
    } catch (e) {
      if (!semSinal(e)) throw e;
      marcarRedeRuim();
    }
  }
  filaAdicionar({ url, corpo, rotulo });
  return null;
}

// ---------------------------------------------------------------- Salgar cocho

async function salFormulario(lote) {
  const ultimo = (lerOffline(CHAVE_SAL_ULTIMO) || {})[lote.id] || {};
  ptModal(`<h2>🧂 Salgar cocho</h2><p class="info">Carregando…</p>`);
  ptModal(`
    <h2>🧂 Salgar cocho — ${ptMarcaLote(lote)} ${esc(lote.nome)}</h2>
    <p class="info">${lote.cabecas} cab. · ${esc(ptNomePiquete(lote.piqueteId))}${lote.ultima_salga
      ? `<br>Última salga ${textoDiasSalga(lote.ultima_salga)}: ${ptNum(lote.ultima_salga.quantidade_kg)} kg de ${esc(lote.ultima_salga.produto)}` : ""}</p>
    <label>Qual sal?</label>
    ${await campoSelectHTML("sal", "sal-produto", ultimo.produto || "Sal mineral")}
    <label>Quantidade (kg)</label>
    <input id="sal-kg" inputmode="decimal" placeholder="Ex.: 25" value="${ultimo.kg ? ptNum(ultimo.kg, 2) : ""}" />
    <div class="sal-rapidos">${[10, 25, 30, 50, 100].map((k) => `<button type="button" class="secundario" data-kg="${k}">${k} kg</button>`).join("")}</div>
    ${salOutrosLotesHTML(lote)}
    <label>Data e hora</label>
    <input type="datetime-local" id="sal-data" value="${agoraLocalInput()}" max="${agoraLocalInput()}" />
    <label>Observação</label>
    <input id="sal-obs" placeholder="Opcional (ex.: cocho estava vazio)" />
    <div class="pt-linha-botoes">
      <button type="button" class="secundario" id="sal-cancelar">Cancelar</button>
      <button type="button" id="sal-ok">✔ Salvar</button>
    </div>
    <p style="margin-top:14px"><a href="#" id="sal-historico">Ver histórico de sal deste lote</a></p>`);
  ligarCampoSelect("sal-produto");
  const atualizarDivisao = () => salPreviaDivisao(lote);
  document.querySelectorAll("[data-sal-outro]").forEach((c) => { c.onchange = atualizarDivisao; });
  document.getElementById("sal-kg").addEventListener("input", atualizarDivisao);
  document.querySelectorAll(".sal-rapidos [data-kg]").forEach((b) => {
    b.onclick = () => { document.getElementById("sal-kg").value = b.dataset.kg; salPreviaDivisao(lote); };
  });
  document.getElementById("sal-cancelar").onclick = ptFecharModal;
  document.getElementById("sal-historico").onclick = (e) => { e.preventDefault(); salHistorico(lote); };
  document.getElementById("sal-ok").onclick = async (ev) => {
    const btn = ev.currentTarget;
    const kg = parseFloat(String(document.getElementById("sal-kg").value).replace(",", "."));
    const produto = await valorCampoSelect("sal", "sal-produto");
    if (!produto) { alert("Escolha qual sal foi colocado."); return; }
    if (!kg || kg <= 0) { alert("Informe a quantidade em kg."); return; }
    const outros = [...document.querySelectorAll("[data-sal-outro]:checked")].map((c) => Number(c.value));
    const corpo = {
      lote_id: lote.id, produto, quantidade_kg: kg, outros_lotes: outros,
      data_hora: document.getElementById("sal-data").value || agoraLocalInput(),
      observacao: document.getElementById("sal-obs").value.trim() || null,
    };
    btn.disabled = true;
    btn.textContent = "Salvando…";
    try {
      const r = await campoEnviar("/api/sal", corpo, `Sal: ${lote.nome} — ${kg} kg de ${produto}`);
      const memoria = lerOffline(CHAVE_SAL_ULTIMO) || {};
      memoria[lote.id] = { produto, kg };
      salvarOffline(CHAVE_SAL_ULTIMO, memoria);
      // A tela já mostra a salga (mesmo que ainda esteja na fila).
      salAtualizarLoteLocal(lote.id, { data_hora: corpo.data_hora, produto, quantidade_kg: kg });
      for (const id of outros) salAtualizarLoteLocal(id, { data_hora: corpo.data_hora, produto, quantidade_kg: kg });
      ptFecharModal();
      pt.sel = null;
      ptRender();
      ptToast(r ? `✔ Cocho salgado: ${ptNum(kg)} kg de ${produto}` + (r.divisao
          ? ` (dividido: ${r.divisao.map((d) => `${d.lote} ${ptNum(d.quantidade_kg)} kg`).join(", ")}).` : ".")
        : "📡 Salga guardada no aparelho — será enviada quando tiver sinal.");
    } catch (e) {
      alert(e.message);
      btn.disabled = false;
      btn.textContent = "✔ Salvar";
    }
  };
}

// "Este cocho é dividido com…": outros lotes, os do mesmo piquete primeiro.
function salOutrosLotesHTML(lote) {
  const outros = ptTodosLotes().filter((l) => l.id !== lote.id && l.id > 0);
  if (!outros.length) return "";
  const mesmo = outros.filter((l) => l.piqueteId != null && l.piqueteId === lote.piqueteId);
  const resto = outros.filter((l) => !mesmo.includes(l));
  const caixa = (l) => `<label class="pt-opcao sal-outro"><input type="checkbox" data-sal-outro value="${l.id}">
    ${ptMarcaLote(l)} ${esc(l.nome)} <small class="info">${l.cabecas} cab. · ${esc(ptNomePiquete(l.piqueteId))}</small></label>`;
  return `
    <details class="sal-dividido" ${mesmo.length ? "open" : ""}>
      <summary>Cocho dividido com outro lote?</summary>
      ${mesmo.length ? `<p class="info">No mesmo piquete:</p>${mesmo.map(caixa).join("")}` : ""}
      ${resto.length ? `<p class="info">Outros lotes:</p>${resto.map(caixa).join("")}` : ""}
      <p class="info" id="sal-previa">A quantidade é repartida pelas cabeças de cada lote.</p>
    </details>`;
}

function salPreviaDivisao(lote) {
  const box = document.getElementById("sal-previa");
  if (!box) return;
  const ids = [...document.querySelectorAll("[data-sal-outro]:checked")].map((c) => Number(c.value));
  const kg = parseFloat(String(document.getElementById("sal-kg").value).replace(",", "."));
  if (!ids.length) { box.textContent = "A quantidade é repartida pelas cabeças de cada lote."; return; }
  const lotes = [lote, ...ptTodosLotes().filter((l) => ids.includes(l.id))];
  const total = lotes.reduce((s, l) => s + l.cabecas, 0);
  box.textContent = !kg || !total ? "Informe a quantidade para ver a divisão."
    : "Divisão: " + lotes.map((l) => `${l.nome} ${ptNum((kg * l.cabecas) / total)} kg`).join(" · ");
}

function salAtualizarLoteLocal(loteId, salga) {
  if (!pt.dados) return;
  for (const l of [...pt.dados.piquetes.flatMap((p) => p.lotes), ...pt.dados.sem_piquete]) {
    if (l.id === loteId) l.ultima_salga = salga;
  }
  salvarOffline(CHAVE_PASTOS_OFFLINE, pt.dados);
}

// Resumo de sal dentro da ficha do lote: última salga e consumo médio.
async function salResumoNaFicha(lote, boxId) {
  const box = document.getElementById(boxId);
  try {
    const h = await api.get(`/api/sal?lote_id=${lote.id}`, 15000);
    if (!document.getElementById(boxId)) return;  // ficha já foi fechada
    if (!h.ultima) { box.textContent = "Nenhuma salga registrada para este lote."; return; }
    box.innerHTML = `Última salga <b>${textoDiasSalga(h.ultima)}</b> (${dataHoraBR(h.ultima.data_hora)}):
      ${ptNum(h.ultima.quantidade_kg)} kg de ${esc(h.ultima.produto)}<br>
      Consumo médio (60 dias): <b>${h.por_produto.length ? h.por_produto.map((p) => `${esc(p.produto)} ${p.media_g_cab_dia != null ? p.media_g_cab_dia + " g/cab/dia" : "—"}${p.situacao === "baixo" ? " ⚠ baixo" : p.situacao === "alto" ? " ⚠ alto" : ""}`).join(" · ") : "precisa de 2 salgas"}</b>
      · <a href="#" id="${boxId}-hist">histórico</a>`;
    document.getElementById(boxId + "-hist").onclick = (e) => { e.preventDefault(); salHistorico(lote); };
  } catch (e) {
    box.textContent = lote.ultima_salga
      ? `Última salga ${textoDiasSalga(lote.ultima_salga)}: ${ptNum(lote.ultima_salga.quantidade_kg)} kg de ${lote.ultima_salga.produto}`
      : (semSinal(e) ? "Sem sinal para carregar o histórico de sal." : e.message);
  }
}

async function salHistorico(lote) {
  ptModal(`<h2>🧂 Sal — ${esc(lote.nome)}</h2><p class="info">Carregando…</p>`);
  let h;
  try {
    h = await api.get(`/api/sal?lote_id=${lote.id}`, 15000);
  } catch (e) {
    ptModal(`<h2>🧂 Sal — ${esc(lote.nome)}</h2><p>${esc(semSinal(e) ? "Precisa de sinal para ver o histórico." : e.message)}</p>`);
    return;
  }
  ptModal(`
    <h2>🧂 Sal — ${ptMarcaLote(lote)} ${esc(lote.nome)}</h2>
    ${h.por_produto.length ? h.por_produto.map((p) => `<p>${esc(p.produto)} — consumo médio (60 dias):
      <b class="sal-${p.situacao || ""}">${p.media_g_cab_dia != null ? p.media_g_cab_dia + " g por cabeça/dia" : "precisa de 2 salgas"}</b>
      ${p.faixa ? `<small class="info">(faixa ${[p.faixa.min, p.faixa.max].filter((v) => v != null).join(" a ")} g${p.situacao === "baixo" ? " — ABAIXO" : p.situacao === "alto" ? " — ACIMA" : ""})</small>` : ""}</p>`).join("") : ""}
    <p class="info">Consumo de cada salga = kg ÷ (cabeças × dias até a salga seguinte do mesmo sal). A última ainda está no cocho.</p>
    ${h.salgas.length ? `<div class="sn-tabela-box"><table class="sn-tabela">
      <tr><th>Data</th><th>Sal</th><th>kg</th><th>Cab.</th><th>g/cab/dia</th><th>Quem</th><th></th></tr>
      ${h.salgas.map((s) => `<tr>
        <td>${dataHoraBR(s.data_hora)}</td><td>${esc(s.produto)}</td><td>${ptNum(s.quantidade_kg)}</td>
        <td>${s.cabecas ?? "—"}${s.grupo ? " 🔗" : ""}</td><td class="sal-${s.situacao || ""}">${s.g_cab_dia ?? "—"}</td><td>${esc(s.usuario || "")}</td>
        <td><button type="button" class="sn-apagar" data-sal="${s.id}" title="apagar">🗑</button></td></tr>`).join("")}
    </table></div>` : "<p>Nenhuma salga registrada.</p>"}
    <button type="button" class="pt-salgar" id="sal-h-nova">🧂 Salgar cocho agora</button>`);
  document.getElementById("sal-h-nova").onclick = () => salFormulario(lote);
  document.querySelectorAll("[data-sal]").forEach((b) => {
    b.onclick = async () => {
      const s = h.salgas.find((x) => String(x.id) === b.dataset.sal);
      if (!confirm(s && s.grupo ? "Este cocho era dividido com outros lotes: apagar a salga de todos?" : "Apagar esta salga?")) return;
      try {
        await api.delete(`/api/sal/${b.dataset.sal}`);
        await ptCarregar();
        salHistorico(lote);
      } catch (e) { alert(semSinal(e) ? "Apagar precisa de sinal." : e.message); }
    };
  });
}

// ---------------------------------------------------------------- Aba Sanidade

const sn = { animal: null, lista: [], filtroCarencia: false, ordem: { col: "data_hora", dir: -1 }, montado: false };

async function snAbrir() {
  if (!sn.montado) await snMontarFormulario();
  snCarregarLista();
}
window.snAbrir = snAbrir;

async function snMontarFormulario() {
  sn.montado = true;
  document.getElementById("sn-data").value = agoraLocalInput();
  document.getElementById("sn-problema-box").innerHTML = await campoSelectHTML("problema", "sn-problema", "", "— escolha —");
  document.getElementById("sn-produto-box").innerHTML = await campoSelectHTML("medicamento", "sn-produto", "", "— nenhum —");
  ligarCampoSelect("sn-problema");
  ligarCampoSelect("sn-produto");
  // Remédio já usado: puxa a carência que foi usada da última vez.
  document.getElementById("sn-produto").addEventListener("change", () => {
    const mem = lerOffline(CHAVE_CARENCIA_PRODUTO) || {};
    const v = document.getElementById("sn-produto").value;
    if (mem[v] != null) document.getElementById("sn-carencia").value = mem[v];
  });
}

document.getElementById("sn-brinco").oninput = () => {
  sn.animal = null;
  const brinco = document.getElementById("sn-brinco").value.trim();
  const box = document.getElementById("sn-info");
  const escolha = document.getElementById("sn-escolha");
  escolha.classList.add("escondido");
  if (!brinco) { box.textContent = ""; box.className = "mg-info-animal"; return; }
  hidratarCacheAnimaisOfflineSeVazio();
  const cands = animaisPorBrinco(brinco);
  if (!cands.length) {
    box.textContent = "⚠ brinco não cadastrado (só animais ativos)";
    box.className = "mg-info-animal fora";
    return;
  }
  const mostrar = (a) => {
    sn.animal = a;
    box.textContent = `${a.tipo || ""}${a.raca ? " · " + a.raca : ""} · ${a.lote || "sem lote"} · ${textoUltimaPesagem(a)}${textoCarencia(a)}`;
    box.className = emCarencia(a) ? "mg-info-animal fora" : "mg-info-animal";
  };
  if (cands.length === 1) { mostrar(cands[0]); return; }
  box.textContent = `⚠ ${cands.length} animais com esse brinco — escolha qual:`;
  box.className = "mg-info-animal fora";
  escolha.innerHTML = cands.map((c, i) => `<button type="button" class="pt-lote-escolha" data-i="${i}">
    ${esc(c.tipo || "?")}${c.raca ? " " + esc(c.raca) : ""} · ${esc(c.lote || "sem lote")} · ${c.ultimo_peso ?? "—"} kg</button>`).join("");
  escolha.classList.remove("escondido");
  escolha.querySelectorAll("[data-i]").forEach((b) => {
    b.onclick = () => { mostrar(cands[Number(b.dataset.i)]); escolha.classList.add("escondido"); };
  });
};

document.getElementById("sn-salvar").onclick = async (ev) => {
  const btn = ev.currentTarget;
  const msg = document.getElementById("sn-msg");
  if (!sn.animal) { alert("Digite o brinco de um animal cadastrado."); return; }
  const problema = await valorCampoSelect("problema", "sn-problema");
  if (!problema) { alert("Escolha o problema."); return; }
  const produto = await valorCampoSelect("medicamento", "sn-produto");
  const carTxt = document.getElementById("sn-carencia").value.trim();
  const carencia = carTxt ? parseInt(carTxt, 10) : null;
  if (carTxt && (isNaN(carencia) || carencia < 0)) { alert("Carência em dias (número)."); return; }
  const corpo = {
    animal_id: sn.animal.id, problema, produto: produto || null,
    dose: document.getElementById("sn-dose").value.trim() || null,
    carencia_dias: carencia,
    data_hora: document.getElementById("sn-data").value || agoraLocalInput(),
    observacao: document.getElementById("sn-obs").value.trim() || null,
  };
  btn.disabled = true;
  btn.textContent = "Salvando…";
  try {
    const r = await campoEnviar("/api/sanidade", corpo, `Sanidade: brinco ${sn.animal.brinco} — ${problema}`);
    if (produto && carencia != null) {
      const mem = lerOffline(CHAVE_CARENCIA_PRODUTO) || {};
      mem[produto] = carencia;
      salvarOffline(CHAVE_CARENCIA_PRODUTO, mem);
    }
    // Aviso de carência já vale na mangueira, mesmo antes de sincronizar.
    if (carencia) {
      const ate = new Date(corpo.data_hora.slice(0, 10) + "T00:00");
      ate.setDate(ate.getDate() + carencia);
      const p = (n) => String(n).padStart(2, "0");
      const iso = `${ate.getFullYear()}-${p(ate.getMonth() + 1)}-${p(ate.getDate())}`;
      if (!sn.animal.carencia_ate || iso > sn.animal.carencia_ate) {
        cacheUpsertAnimal({ id: sn.animal.id, brinco: sn.animal.brinco, carencia_ate: iso });
        persistirCacheAnimaisAtual();
      }
    }
    msg.textContent = r ? `✓ Brinco ${sn.animal.brinco}: ${problema} salvo.`
      : `📡 Brinco ${sn.animal.brinco}: guardado no aparelho, envia quando tiver sinal.`;
    if (!r) {
      sn.lista.unshift({ id: "fila:" + corpo.chave, brinco: sn.animal.brinco, lote: sn.animal.lote,
        tipo_animal: sn.animal.tipo, ...corpo, pendente: true, usuario: usuarioAtual && usuarioAtual.nome,
        carencia_ate: null });
      snRenderLista();
    }
    // Limpa o animal e os detalhes; mantém data/problema/remédio (costuma repetir).
    document.getElementById("sn-brinco").value = "";
    document.getElementById("sn-info").textContent = "";
    document.getElementById("sn-dose").value = "";
    document.getElementById("sn-obs").value = "";
    sn.animal = null;
    if (r) snCarregarLista();
    document.getElementById("sn-brinco").focus();
  } catch (e) {
    alert(e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "✔ Salvar tratamento";
  }
};

async function snCarregarLista() {
  const dias = document.getElementById("sn-periodo").value;
  try {
    sn.lista = await api.get("/api/sanidade" + (dias ? `?dias=${dias}` : ""), 15000);
    salvarOffline(CHAVE_SANIDADE_OFFLINE, sn.lista);
  } catch (e) {
    sn.lista = lerOffline(CHAVE_SANIDADE_OFFLINE) || [];
    document.getElementById("sn-contador").textContent = semSinal(e)
      ? "📡 Sem sinal — mostrando a última lista salva no aparelho." : e.message;
  }
  snRenderLista();
}

const SN_COLUNAS = [
  ["data_hora", "Data"], ["brinco", "Brinco"], ["problema", "Problema"], ["produto", "Remédio"],
  ["dose", "Dose"], ["carencia_ate", "Carência até"], ["lote", "Lote"], ["usuario", "Quem"],
];

function snRenderLista() {
  const hoje = hojeLocal();
  const emCar = sn.lista.filter((o) => o.carencia_ate && o.carencia_ate >= hoje);
  const animaisCar = new Set(emCar.map((o) => o.animal_id)).size;
  const contagem = {};
  sn.lista.forEach((o) => { contagem[o.problema] = (contagem[o.problema] || 0) + 1; });
  const comum = Object.entries(contagem).sort((a, b) => b[1] - a[1])[0];
  document.getElementById("sn-cards").innerHTML = `
    <button type="button" class="sn-card${sn.filtroCarencia ? " ativo" : ""}" id="sn-card-carencia">
      <b>${animaisCar}</b><span>em carência agora</span></button>
    <button type="button" class="sn-card" id="sn-card-todos"><b>${sn.lista.length}</b><span>tratamentos no período</span></button>
    <div class="sn-card"><b>${comum ? esc(comum[0]) : "—"}</b><span>${comum ? `mais comum (${comum[1]})` : "problema mais comum"}</span></div>`;
  document.getElementById("sn-card-carencia").onclick = () => { sn.filtroCarencia = !sn.filtroCarencia; snRenderLista(); };
  document.getElementById("sn-card-todos").onclick = () => {
    sn.filtroCarencia = false; document.getElementById("sn-busca").value = ""; snRenderLista();
  };

  const termo = document.getElementById("sn-busca").value.trim().toLowerCase();
  let linhas = sn.filtroCarencia ? emCar : sn.lista.slice();
  if (termo) {
    linhas = linhas.filter((o) => [o.brinco, o.problema, o.produto, o.lote, o.usuario, o.observacao]
      .some((v) => String(v || "").toLowerCase().includes(termo)));
  }
  const { col, dir } = sn.ordem;
  linhas.sort((a, b) => {
    const va = a[col] ?? "", vb = b[col] ?? "";
    return String(va).localeCompare(String(vb), "pt-BR", { numeric: true }) * dir;
  });
  document.getElementById("sn-contador").textContent =
    `${linhas.length} tratamento${linhas.length === 1 ? "" : "s"}${sn.filtroCarencia ? " · só animais em carência (toque no card para ver todos)" : ""}`;
  const seta = (c) => (c === col ? (dir > 0 ? " ▲" : " ▼") : "");
  const tabela = document.getElementById("sn-tabela");
  tabela.innerHTML = `
    <tr>${SN_COLUNAS.map(([c, t]) => `<th data-col="${c}">${t}${seta(c)}</th>`).join("")}<th></th></tr>
    ${linhas.map((o) => `<tr class="${o.carencia_ate && o.carencia_ate >= hoje ? "sn-em-carencia" : ""}">
      <td>${dataHoraBR(o.data_hora)}${o.pendente ? " 📡" : ""}</td>
      <td><b>${esc(o.brinco || "")}</b></td>
      <td>${esc(o.problema)}${o.observacao ? `<br><small class="info">${esc(o.observacao)}</small>` : ""}</td>
      <td>${esc(o.produto || "")}</td><td>${esc(o.dose || "")}</td>
      <td>${o.carencia_ate ? fmt.data(o.carencia_ate) : ""}</td>
      <td>${esc(o.lote || "")}</td><td>${esc(o.usuario || "")}</td>
      <td>${o.pendente ? "" : `<button type="button" class="sn-apagar" data-oc="${o.id}" title="apagar">🗑</button>`}</td>
    </tr>`).join("")}`;
  tabela.querySelectorAll("th[data-col]").forEach((th) => {
    th.onclick = () => {
      const c = th.dataset.col;
      // 1º clique: data/carência do mais recente; texto de A a Z. 2º clique inverte.
      sn.ordem = sn.ordem.col === c ? { col: c, dir: -sn.ordem.dir }
        : { col: c, dir: ["data_hora", "carencia_ate"].includes(c) ? -1 : 1 };
      snRenderLista();
    };
  });
  tabela.querySelectorAll("[data-oc]").forEach((b) => {
    b.onclick = async () => {
      if (!confirm("Apagar este tratamento?")) return;
      try {
        await api.delete(`/api/sanidade/${b.dataset.oc}`);
        snCarregarLista();
        carregarCacheAnimais().catch(() => {});
      } catch (e) { alert(semSinal(e) ? "Apagar precisa de sinal." : e.message); }
    };
  });
}

document.getElementById("sn-busca").oninput = snRenderLista;
document.getElementById("sn-periodo").onchange = snCarregarLista;
window.addEventListener("fila-sincronizada", () => {
  if (document.getElementById("aba-sanidade").classList.contains("ativa")) {
    snCarregarLista();
    carregarCacheAnimais().catch(() => {});
  }
});


// ---------------------------------------------------------------- Faixa de consumo (Config)

async function salConfigFaixas(boxId) {
  const box = document.getElementById(boxId);
  if (!box) return;
  let faixas, sais;
  try {
    faixas = await api.get("/api/sal/faixas");
    sais = await opcoes("sal");
  } catch (e) { box.textContent = e.message; return; }
  const nomes = [...new Set([...sais, ...Object.keys(faixas)])];
  box.innerHTML = `
    <p class="info">Consumo esperado de cada sal em <b>gramas por cabeça por dia</b> — veja no rótulo do
      produto ou com o técnico. Com a faixa preenchida, o app avisa (🔔) quando o consumo medido sair dela.</p>
    <div class="sal-faixa sal-faixa-cab"><span>Sal</span><span>mínimo (g)</span><span>máximo (g)</span></div>
    ${nomes.map((n) => `<div class="sal-faixa" data-sal-nome="${esc(n)}"><span>${esc(n)}</span>
      <input data-k="min" inputmode="decimal" value="${faixas[n] && faixas[n].min != null ? faixas[n].min : ""}" />
      <input data-k="max" inputmode="decimal" value="${faixas[n] && faixas[n].max != null ? faixas[n].max : ""}" /></div>`).join("")}
    <button type="button" class="secundario" id="sal-faixa-salvar" style="width:100%;margin-top:8px">Salvar modificações</button>
    <div class="info" id="sal-faixa-msg"></div>`;
  document.getElementById("sal-faixa-salvar").onclick = async (ev) => {
    const btn = ev.currentTarget;
    btn.disabled = true;
    const dados = {};
    box.querySelectorAll("[data-sal-nome]").forEach((l) => {
      dados[l.dataset.salNome] = { min: l.querySelector('[data-k="min"]').value, max: l.querySelector('[data-k="max"]').value };
    });
    try {
      await api.put("/api/sal/faixas", { faixas: dados });
      document.getElementById("sal-faixa-msg").textContent = "✓ Salvo.";
      if (window.alCarregar) window.alCarregar();
    } catch (e) {
      document.getElementById("sal-faixa-msg").textContent = e.message;
    } finally {
      btn.disabled = false;
    }
  };
}
window.salConfigFaixas = salConfigFaixas;
