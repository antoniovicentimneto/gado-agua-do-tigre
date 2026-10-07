// Rebanho › Cria: vacas e bezerros. Qual vaca é mãe de qual bezerro, quem está com
// bezerro ao pé, quem está solteira (pode ir pro frigorífico), marcação de prenhe /
// mojando / vazia, registro de nascimento e desmama.
// Os dados vêm numa chamada só (/api/cria) e os filtros rodam no aparelho.

const cr = {
  dados: null,
  filtro: "todas",   // todas | com_bezerro | solteiras | prenhes | frigorifico
  busca: "",
};

const CR_PRENHEZ = { prenhe: "Prenhe (toque)", mojando: "Mojando", vazia: "Vazia (toque)" };
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
    cr.dados = await api.get("/api/cria");
  } catch (e) {
    box.innerHTML = `<div class="info">⚠ Erro ao carregar: ${esc(e.message)}. <a href="#" id="cr-retentar">Tentar de novo</a></div>`;
    document.getElementById("cr-retentar").onclick = (ev) => { ev.preventDefault(); carregarCria(); };
    return;
  }
  crRender();
}

function crPassa(m) {
  if (cr.busca) {
    const alvo = cr.busca.toLowerCase();
    const bate = m.brinco.toLowerCase().includes(alvo) ||
      m.crias.some((c) => c.brinco.toLowerCase().includes(alvo));
    if (!bate) return false;
  }
  if (cr.filtro === "com_bezerro") return m.situacao === "com_bezerro";
  if (cr.filtro === "solteiras") return m.situacao === "solteira";
  if (cr.filtro === "prenhes") return m.prenhez === "prenhe" || m.prenhez === "mojando";
  if (cr.filtro === "frigorifico") return m.pode_frigorifico;
  return true;
}

function crRender() {
  const d = cr.dados, r = d.resumo;
  const box = document.getElementById("lista-cria");
  const chip = (id, rotulo, n) =>
    `<button data-filtro="${id}" class="${cr.filtro === id ? "ativo" : ""}">${rotulo} <b>${n}</b></button>`;

  const matrizes = d.matrizes.filter(crPassa);
  const cartoes = matrizes.map((m) => {
    const noPe = m.crias.filter((c) => c.ao_pe);
    const tagSit = m.situacao === "com_bezerro"
      ? `<span class="tag cr-bezerro">com bezerro</span>` : `<span class="tag cr-solteira">solteira</span>`;
    const tagPrenhez = m.prenhez
      ? `<span class="tag cr-${m.prenhez}" title="marcado em ${fmt.data(m.prenhez_data)}">${m.prenhez}</span>` : "";
    const crias = noPe.map((c) => `
      <div class="cr-cria">🐄 <a href="#" class="cr-ficha" data-id="${c.id}"><b>${esc(c.brinco)}</b></a>
        <span class="info">${esc(c.tipo || "")}${c.nascimento ? ` · nasceu ${fmt.data(c.nascimento)} (${crIdade(c.idade_dias)})` : " · sem data de nascimento"}${c.ultimo_peso != null ? ` · ${fmt.peso(c.ultimo_peso)}` : ""}</span>
      </div>`).join("");
    const historico = m.total_crias
      ? `${m.total_crias} cria${m.total_crias > 1 ? "s" : ""}${m.ultimo_parto ? ` · último parto ${fmt.data(m.ultimo_parto)}` : ""}${m.intervalo_partos_dias ? ` · intervalo ${Math.round(m.intervalo_partos_dias / 30.4)} meses` : ""}`
      : "nenhuma cria registrada";
    return `
      <div class="card-cria" data-id="${m.id}">
        <div class="card-cria-topo">
          <a href="#" class="cr-ficha" data-id="${m.id}"><b>${esc(m.brinco)}</b></a>
          ${tagSit}${tagPrenhez}
        </div>
        <div class="sub">${[m.tipo, m.raca, m.lote, m.ultimo_peso != null ? fmt.peso(m.ultimo_peso) : null].filter(Boolean).map(esc).join(" · ")}</div>
        ${crias}
        <div class="info">${historico}</div>
        <div class="card-cria-acoes">
          <select class="cr-prenhez" title="marcar prenhez">
            <option value="">sem marcação</option>
            ${Object.entries(CR_PRENHEZ).map(([v, t]) => `<option value="${v}" ${m.prenhez === v ? "selected" : ""}>${t}</option>`).join("")}
          </select>
          <button class="secundario cr-nasceu">+ Nasceu bezerro</button>
        </div>
      </div>`;
  }).join("");

  const semMae = d.bezerros_sem_mae.length ? `
    <h3 style="margin-top:18px">Bezerros sem mãe informada (${d.bezerros_sem_mae.length})</h3>
    <div class="info">Toque no brinco pra abrir a ficha e informar a mãe e a data de nascimento.</div>
    ${d.bezerros_sem_mae.map((b) => `
      <div class="card-cria">
        <div class="card-cria-topo">
          <a href="#" class="cr-ficha" data-id="${b.id}"><b>${esc(b.brinco)}</b></a>
          <span class="info">${[b.tipo, b.lote, b.ultimo_peso != null ? fmt.peso(b.ultimo_peso) : null, b.nascimento ? "nasceu " + fmt.data(b.nascimento) : null].filter(Boolean).map(esc).join(" · ")}</span>
        </div>
      </div>`).join("")}` : "";

  box.innerHTML = `
    <div class="cr-filtros">
      ${chip("todas", "Todas", r.matrizes)}
      ${chip("com_bezerro", "Com bezerro", r.com_bezerro)}
      ${chip("solteiras", "Solteiras", r.solteiras)}
      ${chip("prenhes", "Prenhes / mojando", r.prenhes)}
      ${chip("frigorifico", "Podem ir pro frigorífico", r.pode_frigorifico)}
    </div>
    <div class="filtros">
      <input id="cr-busca" placeholder="Buscar brinco da vaca ou do bezerro..." value="${esc(cr.busca)}" />
      <button id="cr-novo">+ Nascimento</button>
    </div>
    <div class="info">${matrizes.length} vaca${matrizes.length === 1 ? "" : "s"} · ${r.bezerros_ao_pe} bezerro${r.bezerros_ao_pe === 1 ? "" : "s"} ao pé no total${cr.filtro === "frigorifico" ? " · solteiras e não marcadas como prenhe/mojando" : ""}</div>
    ${cartoes || "<div class='info' style='margin-top:10px'>Nenhuma vaca nesse filtro.</div>"}
    ${cr.filtro === "todas" && !cr.busca ? semMae : ""}`;

  box.querySelectorAll(".cr-filtros button").forEach((b) => {
    b.onclick = () => { cr.filtro = b.dataset.filtro; crRender(); };
  });
  const busca = document.getElementById("cr-busca");
  busca.oninput = () => {
    cr.busca = busca.value.trim();
    crRender();
    const novo = document.getElementById("cr-busca");   // mantém o cursor ao redesenhar
    novo.focus(); novo.setSelectionRange(novo.value.length, novo.value.length);
  };
  document.getElementById("cr-novo").onclick = () => crAbrirNascimento(null);
  box.querySelectorAll(".cr-ficha").forEach((a) => {
    a.onclick = (ev) => { ev.preventDefault(); abrirFicha(Number(a.dataset.id)); };
  });
  box.querySelectorAll(".card-cria[data-id]").forEach((card) => {
    const id = Number(card.dataset.id);
    const m = d.matrizes.find((x) => x.id === id);
    const sel = card.querySelector(".cr-prenhez");
    if (sel) sel.onchange = () => crMarcarPrenhez(id, sel.value);
    const nasceu = card.querySelector(".cr-nasceu");
    if (nasceu) nasceu.onclick = () => crAbrirNascimento(m);
  });
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
      <button id="cf-salvar" style="margin-top:8px;width:100%">Salvar mãe e nascimento</button>
      <div id="cf-msg" class="info"></div>
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

  // Um botão só: salva a mãe e/ou a data de nascimento JUNTOS (só o que mudou), pra
  // não perder um campo digitado ao salvar o outro.
  $("cf-salvar").onclick = async () => {
    const brinco = $("cf-mae").value.trim();
    const nasc = $("cf-nasc").value || null;
    const mudouMae = brinco !== (a.mae ? a.mae.brinco : "");
    const mudouNasc = nasc !== (a.nascimento || null);
    if (!mudouMae && !mudouNasc) { $("cf-msg").textContent = "Nada foi alterado."; return; }
    const dados = {};
    try {
      if (mudouNasc) dados.nascimento = nasc;
      if (mudouMae) {
        if (brinco) {
          // Procura entre os ativos; se não achar, entre todos (mãe já vendida/morta).
          let cands = (await crBuscarPorBrinco(brinco)).filter((x) => x.id !== id);
          if (!cands.length) {
            cands = (await api.get("/api/animais?busca=" + encodeURIComponent(brinco)))
              .filter((x) => x.brinco === brinco && x.id !== id);
          }
          if (!cands.length) { alert(`Não achei animal com o brinco ${brinco}.`); return; }
          const mae = cands.length === 1 ? cands[0] : await crEscolher($("cf-escolha"), cands);
          dados.mae_id = mae.id;
        } else {
          if (!confirm("Remover a mãe deste animal?")) return;
          dados.mae_id = null;
        }
      }
      await api.put(`/api/cria/mae/${id}`, dados);
      recarregar();
    } catch (e) { alert("Erro: " + e.message); }
  };
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
  if ($("cf-prenhez")) {
    $("cf-prenhez").onchange = async () => {
      try {
        await api.put(`/api/cria/prenhez/${id}`, { prenhez: $("cf-prenhez").value || null, data: crHoje() });
        recarregar();
      } catch (e) { alert("Erro: " + e.message); }
    };
  }
  if ($("cf-nasceu")) $("cf-nasceu").onclick = () => crAbrirNascimento({ id, brinco: a.brinco });
}
