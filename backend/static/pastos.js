// Aba Pastos: piquetes, onde cada lote está e a mudança de piquete pelo celular.
//
// Fluxo principal (pensado pro dedo, no campo): toca no lote → toca no piquete de
// destino → confirma. Também dá pra SEGURAR o lote e arrastar até o piquete.
// Toda mudança pode ser desfeita. Sem sinal, a mudança fica guardada no aparelho
// (fila offline) e a tela já mostra o resultado.

const CHAVE_PASTOS_OFFLINE = "gat_cache_pastos";
const PT_SEGURAR_MS = 350;     // tempo segurando o lote pra começar a arrastar
const PT_TOLERANCIA_PX = 10;   // mexeu mais que isso antes do tempo = está rolando a tela

const pt = {
  dados: null,        // resposta de /api/pastos
  offline: false,
  modo: "lista",
  sel: null,          // { lote, piqueteId } — lote escolhido pra mudar
  mapa: null,
  camadaPiquetes: null,
  desenho: null,      // { pontos, linha, poligono, piqueteId } enquanto desenha
  toastTimer: null,
};

const ptEl = (id) => document.getElementById(id);
const ptEhDono = () => typeof usuarioAtual !== "undefined" && usuarioAtual && usuarioAtual.papel === "dono";
const ptHoje = () => hojeLocal();

function ptNum(v, casas = 1) {
  if (v == null) return "—";
  return Number(v).toLocaleString("pt-BR", { maximumFractionDigits: casas });
}

function ptDataBR(iso) {
  if (!iso) return "";
  const [a, m, d] = iso.split("-");
  return `${d}/${m}/${a}`;
}

// ---------------------------------------------------------------- Carregar

async function ptCarregar() {
  try {
    const dados = await api.get("/api/pastos?hoje=" + ptHoje(), 20000);
    pt.dados = dados;
    pt.offline = false;
    salvarOffline(CHAVE_PASTOS_OFFLINE, { ...dados, salvoEm: Date.now() });
  } catch (e) {
    const salvo = lerOffline(CHAVE_PASTOS_OFFLINE);
    if (!(e instanceof TypeError) || !salvo) {
      ptEl("pt-aviso").textContent = "Não foi possível carregar os pastos: " + e.message;
      return;
    }
    pt.dados = salvo;
    pt.offline = true;
  }
  ptRender();
}

function ptAbrir() {
  ptEl("pt-ferramentas").classList.toggle("escondido", !ptEhDono());
  if (pt.dados) ptRender();
  ptCarregar();
}
window.ptAbrir = ptAbrir;

// ---------------------------------------------------------------- Ajudantes de dados

function ptPiquete(id) {
  return pt.dados.piquetes.find((p) => p.id === id);
}

function ptNomePiquete(id) {
  if (id == null) return "sem piquete";
  const p = ptPiquete(id);
  if (!p) return "?";
  return p.area ? `${p.nome} (${p.area})` : p.nome;
}

// Todos os lotes com gado, com o piquete onde estão (null = sem piquete).
function ptTodosLotes() {
  const lista = [];
  for (const p of pt.dados.piquetes) for (const l of p.lotes) lista.push({ ...l, piqueteId: p.id });
  for (const l of pt.dados.sem_piquete) lista.push({ ...l, piqueteId: null });
  return lista.sort((a, b) => a.nome.localeCompare(b.nome, "pt-BR", { numeric: true }));
}

function ptLoteDescricao(l) {
  return `${l.cabecas} cab.` + (l.peso_medio ? ` · ${ptNum(l.peso_medio, 0)} kg méd.` : "");
}

function ptTextoStatus(p) {
  const meta = p.descanso_meta_dias ? ` (meta ${p.descanso_meta_dias})` : "";
  if (p.status === "ocupado") return `🐂 Ocupado há ${p.dias} dia${p.dias === 1 ? "" : "s"}`;
  if (p.status === "pronto") return `✅ Pronto — vazio há ${p.dias} dias${meta}`;
  if (p.status === "descansando") return `⏳ Descansando há ${p.dias} dia${p.dias === 1 ? "" : "s"}${meta}`;
  return "— sem registro de uso";
}

// ---------------------------------------------------------------- Render geral

function ptRender() {
  const d = pt.dados;
  if (!d) return;
  const salvoEm = d.salvoEm ? new Date(d.salvoEm).toLocaleString("pt-BR") : "";
  ptEl("pt-aviso").textContent = pt.offline
    ? `📡 Sem sinal — mostrando os dados salvos no aparelho${salvoEm ? ` (atualizados em ${salvoEm})` : ""}. As mudanças são enviadas quando a rede voltar.`
    : "";

  const cont = { ocupado: 0, descansando: 0, pronto: 0 };
  let ha = 0;
  for (const p of d.piquetes) {
    if (cont[p.status] != null) cont[p.status]++;
    ha += p.hectares || 0;
  }
  ptEl("pt-resumo").innerHTML = d.piquetes.length ? `
    <span><b>${d.piquetes.length}</b> piquetes · ${ptNum(ha)} ha</span>
    <span>🐂 ${cont.ocupado} ocupados</span>
    <span>⏳ ${cont.descansando} descansando</span>
    <span>✅ ${cont.pronto} prontos</span>` : "";

  ptRenderSemPiquete();
  if (pt.modo === "lista") ptRenderLista();
  else ptRenderMapa();
  ptRenderMovs();
  ptRenderBarra();
}

function ptBotaoLote(l, piqueteId) {
  const sel = pt.sel && pt.sel.lote.id === l.id ? " selecionado" : "";
  return `<button type="button" class="pt-lote${sel}" data-lote-id="${l.id}" data-piquete-id="${piqueteId ?? ""}"
      style="--cor-lote:${esc(l.cor || "#2e7d32")}">
    <b>${ptMarcaLote(l)} ${esc(l.nome)}</b><small>${ptLoteDescricao(l)}${l.dias != null ? ` · ${l.dias}d aqui` : ""}${l.ultima_salga ? ` · 🧂 ${textoDiasSalga(l.ultima_salga)}` : ""}</small>
  </button>`;
}

// Bolinha na cor do lote com o ícone dentro — a mesma do mapa.
function ptMarcaLote(l, grande) {
  return `<span class="pt-marca${grande ? " grande" : ""}" style="background:${esc(l.cor || "#2e7d32")};color:${ptCorTexto(l.cor)}">${esc(l.icone || "")}</span>`;
}

// Texto escuro sobre cor clara (amarelo, branco), claro sobre cor escura.
function ptCorTexto(cor) {
  const c = (cor || "#2e7d32").replace("#", "");
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(c.substr(i, 2), 16));
  return (r * 299 + g * 587 + b * 114) / 1000 > 160 ? "#1f2937" : "#fff";
}

function ptRenderSemPiquete() {
  const lotes = pt.dados.sem_piquete;
  ptEl("pt-sem-piquete").innerHTML = lotes.length ? `
    <div class="pt-sem-box">
      <h3>Lotes sem piquete (${lotes.length})</h3>
      <div class="info">Toque num lote e depois no piquete onde ele está.</div>
      <div class="pt-lotes">${lotes.map((l) => ptBotaoLote(l, null)).join("")}</div>
    </div>` : "";
  ptLigarLotes(ptEl("pt-sem-piquete"));
}

function ptRenderLista() {
  const d = pt.dados;
  const box = ptEl("pt-lista");
  if (!d.piquetes.length) {
    box.innerHTML = `<div class="destaque">Nenhum piquete cadastrado ainda.
      ${ptEhDono() ? "Use <b>Importar arquivo de áreas</b> ou <b>Desenhar piquete</b> aqui em cima." :
        "Peça ao dono para cadastrar os piquetes."}</div>`;
    return;
  }
  const grupos = new Map();
  for (const p of d.piquetes) {
    const k = p.area || "Sem área";
    if (!grupos.has(k)) grupos.set(k, []);
    grupos.get(k).push(p);
  }
  const ordemNome = (a, b) => a.nome.localeCompare(b.nome, "pt-BR", { numeric: true });
  let html = "";
  for (const [area, piquetes] of [...grupos.entries()].sort((a, b) => a[0].localeCompare(b[0], "pt-BR"))) {
    html += `<div class="pt-grupo"><h3>${esc(area)}</h3>`;
    for (const p of piquetes.sort(ordemNome)) {
      const levar = pt.sel && pt.sel.piqueteId !== p.id
        ? `<button type="button" class="pt-levar" data-levar="${p.id}">➜ Levar ${esc(pt.sel.lote.nome)} para cá</button>` : "";
      const lotacao = p.cabecas
        ? ` · ${p.cabecas} cab. · ${ptNum(p.ua)} UA${p.ua_ha ? ` · ${ptNum(p.ua_ha, 2)} UA/ha` : ""}` : "";
      html += `
        <div class="pt-piquete ${p.status}" data-piquete="${p.id}">
          <div class="pt-piquete-topo">
            <div>
              <div class="pt-piquete-nome">${esc(p.nome)}</div>
              <div class="pt-piquete-sub">${p.hectares ? ptNum(p.hectares, 2) + " ha" : "área não informada"}${p.capim ? " · " + esc(p.capim) : ""}${lotacao}</div>
              <span class="pt-status ${p.status}">${ptTextoStatus(p)}</span>
            </div>
            ${ptEhDono() ? `<button type="button" class="pt-editar" data-editar="${p.id}">⚙</button>` : ""}
          </div>
          ${p.lotes.length ? `<div class="pt-lotes">${p.lotes.map((l) => ptBotaoLote(l, p.id)).join("")}</div>` : ""}
          ${levar}
        </div>`;
    }
    html += "</div>";
  }
  box.innerHTML = html;
  ptLigarLotes(box);
  box.querySelectorAll("[data-levar]").forEach((b) => {
    b.onclick = () => ptConfirmarMover(Number(b.dataset.levar));
  });
  box.querySelectorAll("[data-editar]").forEach((b) => {
    b.onclick = () => ptFormPiquete(ptPiquete(Number(b.dataset.editar)));
  });
}

function ptRenderMovs() {
  const movs = (pt.dados.movimentacoes || []);
  ptEl("pt-movs").innerHTML = movs.length ? `
    <div class="pt-movs"><h3>Últimas mudanças</h3>
      ${movs.map((m) => `
        <div class="pt-mov${m.desfeita ? " desfeita" : ""}">
          <div>${esc(m.resumo)}<br><small>${ptDataBR(m.data)}${m.usuario ? " · " + esc(m.usuario) : ""}${m.pendente ? " · 📡 aguardando a rede" : ""}${m.desfeita ? " · desfeita" : ""}</small></div>
          ${m.desfeita ? "" : `<button type="button" class="secundario" data-desfazer="${m.id}">↶ Desfazer</button>`}
        </div>`).join("")}
    </div>` : "";
  ptEl("pt-movs").querySelectorAll("[data-desfazer]").forEach((b) => {
    b.onclick = () => ptDesfazer(b.dataset.desfazer);
  });
}

// ---------------------------------------------------------------- Seleção e arraste

function ptSelecionar(loteId, piqueteId) {
  if (pt.sel && pt.sel.lote.id === loteId) { ptCancelarSelecao(); return; }
  const lote = ptTodosLotes().find((l) => l.id === loteId);
  if (!lote) return;
  pt.sel = { lote, piqueteId };
  ptRender();
}

function ptCancelarSelecao() {
  pt.sel = null;
  ptRender();
}

function ptRenderBarra() {
  const barra = ptEl("pt-barra");
  const visivel = !!pt.sel && ptEl("aba-pastos").classList.contains("ativa");
  barra.classList.toggle("escondido", !visivel);
  document.body.classList.toggle("pt-com-barra", visivel);
  if (!visivel) return;
  const l = pt.sel.lote;
  barra.innerHTML = `
    <div class="pt-barra-titulo">${esc(l.nome)} · ${ptLoteDescricao(l)}</div>
    <div class="pt-barra-dica">Está em: ${esc(ptNomePiquete(pt.sel.piqueteId))}. ${pt.modo === "mapa"
      ? "Toque no piquete de destino no mapa." : "Toque em <b>➜ Levar para cá</b> no piquete de destino."}</div>
    <button type="button" id="pt-b-salgar" class="pt-salgar">🧂 Salgar cocho${l.ultima_salga ? ` <small>· última ${textoDiasSalga(l.ultima_salga)}</small>` : ""}</button>
    <div class="pt-barra-botoes">
      <button type="button" id="pt-b-ficha" class="secundario">ℹ Ficha / cor</button>
      <button type="button" id="pt-b-separar" class="secundario">✂ Separar animais</button>
      <button type="button" id="pt-b-juntar" class="secundario">🔗 Juntar lotes</button>
      <button type="button" id="pt-b-cancelar" class="secundario">✖ Cancelar</button>
    </div>`;
  ptEl("pt-b-ficha").onclick = () => ptFichaLote(pt.sel.lote.id);
  ptEl("pt-b-salgar").onclick = () => salFormulario(pt.sel.lote);
  ptEl("pt-b-separar").onclick = ptFormSeparar;
  ptEl("pt-b-juntar").onclick = ptFormJuntar;
  ptEl("pt-b-cancelar").onclick = ptCancelarSelecao;
}

// Toque = seleciona. Segurar e arrastar = leva direto até um piquete.
function ptLigarLotes(raiz) {
  raiz.querySelectorAll(".pt-lote").forEach((b) => {
    const loteId = Number(b.dataset.loteId);
    const piqueteId = b.dataset.piqueteId ? Number(b.dataset.piqueteId) : null;
    let timer = null, inicio = null, arrastando = false, fantasma = null, alvo = null;

    const limpar = () => {
      clearTimeout(timer);
      timer = null;
      if (fantasma) fantasma.remove();
      fantasma = null;
      document.body.classList.remove("pt-arrastando");
      document.querySelectorAll(".alvo-arraste").forEach((x) => x.classList.remove("alvo-arraste"));
      window.removeEventListener("pointermove", mover);
      window.removeEventListener("pointerup", soltar);
      window.removeEventListener("pointercancel", cancelar);
      document.removeEventListener("touchmove", travarRolagem);
    };
    const travarRolagem = (e) => { if (arrastando) e.preventDefault(); };
    const mover = (e) => {
      if (!arrastando) {
        if (inicio && Math.hypot(e.clientX - inicio.x, e.clientY - inicio.y) > PT_TOLERANCIA_PX) limpar();
        return;
      }
      fantasma.style.left = e.clientX + "px";
      fantasma.style.top = e.clientY + "px";
      const sob = document.elementFromPoint(e.clientX, e.clientY);
      const card = sob && sob.closest(".pt-piquete");
      const novo = card && Number(card.dataset.piquete) !== piqueteId ? card : null;
      if (alvo !== novo) {
        if (alvo) alvo.classList.remove("alvo-arraste");
        alvo = novo;
        if (alvo) alvo.classList.add("alvo-arraste");
      }
    };
    const soltar = () => {
      const destino = arrastando && alvo ? Number(alvo.dataset.piquete) : null;
      const eraArraste = arrastando;
      arrastando = false;
      limpar();
      if (eraArraste) {
        // O clique que vem depois do arraste não pode desmarcar o lote.
        pt.ignorarCliqueAte = Date.now() + 400;
        ptRender();  // mostra o lote marcado e os "Levar para cá" (se soltou fora)
        if (destino) ptConfirmarMover(destino);
      }
    };
    const cancelar = () => { arrastando = false; limpar(); };

    b.addEventListener("pointerdown", (e) => {
      if (e.button !== 0) return;
      inicio = { x: e.clientX, y: e.clientY };
      window.addEventListener("pointermove", mover);
      window.addEventListener("pointerup", soltar);
      window.addEventListener("pointercancel", cancelar);
      document.addEventListener("touchmove", travarRolagem, { passive: false });
      timer = setTimeout(() => {
        if (pt.modo !== "lista") return;
        arrastando = true;
        if (!pt.sel || pt.sel.lote.id !== loteId) {
          const lote = ptTodosLotes().find((l) => l.id === loteId);
          if (lote) pt.sel = { lote, piqueteId };
          ptRenderBarra();
        }
        document.body.classList.add("pt-arrastando");
        fantasma = b.cloneNode(true);
        fantasma.classList.add("pt-fantasma", "selecionado");
        fantasma.style.left = inicio.x + "px";
        fantasma.style.top = inicio.y + "px";
        document.body.appendChild(fantasma);
        if (navigator.vibrate) navigator.vibrate(30);
      }, PT_SEGURAR_MS);
    });
    b.addEventListener("click", () => {
      if (Date.now() < (pt.ignorarCliqueAte || 0)) return;
      ptSelecionar(loteId, piqueteId);
    });
    b.addEventListener("contextmenu", (e) => e.preventDefault());  // segurar não abre menu
  });
}

// ---------------------------------------------------------------- Modal

function ptModal(html) {
  ptEl("pt-modal-corpo").innerHTML = html;
  ptEl("pt-modal").classList.remove("escondido");
}
function ptFecharModal() {
  ptEl("pt-modal").classList.add("escondido");
  ptEl("pt-modal-corpo").innerHTML = "";
}
ptEl("pt-fechar-modal").onclick = ptFecharModal;
ptEl("pt-modal").addEventListener("click", (e) => { if (e.target === ptEl("pt-modal")) ptFecharModal(); });

function ptCampoData() {
  return `<label>Data da mudança</label><input type="date" id="pt-data" value="${ptHoje()}" max="${ptHoje()}" />`;
}

// ---------------------------------------------------------------- Mover

function ptConfirmarMover(piqueteId) {
  if (!pt.sel) return;
  const l = pt.sel.lote;
  const destino = ptPiquete(piqueteId);
  if (!destino || pt.sel.piqueteId === piqueteId) return;
  const outros = destino.lotes;
  const opcoesJuntar = outros.length ? `
    <label>O ${esc(destino.nome)} já tem gado. O que fazer?</label>
    <label class="pt-opcao"><input type="radio" name="pt-jt" value="" checked>
      Deixar os lotes separados no mesmo piquete</label>
    ${outros.map((o) => `<label class="pt-opcao"><input type="radio" name="pt-jt" value="${o.id}">
      Juntar ${esc(l.nome)} dentro do lote ${esc(o.nome)} (${o.cabecas} cab.)</label>`).join("")}` : "";
  ptModal(`
    <h2>Mudar de piquete</h2>
    <p><b>${esc(l.nome)}</b> (${l.cabecas} cab.)<br>
      ${esc(ptNomePiquete(pt.sel.piqueteId))} ➜ <b>${esc(ptNomePiquete(piqueteId))}</b></p>
    ${opcoesJuntar}
    ${ptCampoData()}
    <div class="pt-linha-botoes">
      <button type="button" class="secundario" id="pt-m-cancelar">Cancelar</button>
      <button type="button" id="pt-m-ok">✔ Confirmar</button>
    </div>`);
  ptEl("pt-m-cancelar").onclick = ptFecharModal;
  ptEl("pt-m-ok").onclick = () => {
    const data = ptEl("pt-data").value || ptHoje();
    const juntarCom = (document.querySelector('input[name="pt-jt"]:checked') || {}).value;
    ptFecharModal();
    if (juntarCom) {
      const alvo = outros.find((o) => o.id === Number(juntarCom));
      ptExecutar("/api/pastos/juntar", { origem_id: l.id, destino_id: alvo.id, data },
        `${l.nome} (${l.cabecas} cab.) juntado ao ${alvo.nome}`,
        (d) => ptOtimistaJuntar(d, l.id, alvo.id));
    } else {
      ptExecutar("/api/pastos/mover", { lote_id: l.id, piquete_id: piqueteId, data },
        `${l.nome} (${l.cabecas} cab.): ${ptNomePiquete(pt.sel.piqueteId)} → ${ptNomePiquete(piqueteId)}`,
        (d) => ptOtimistaMover(d, l.id, piqueteId, data));
    }
  };
}

// ---------------------------------------------------------------- Juntar

function ptFormJuntar() {
  if (!pt.sel) return;
  const l = pt.sel.lote;
  const outros = ptTodosLotes().filter((o) => o.id !== l.id);
  if (!outros.length) { alert("Não há outro lote com gado para juntar."); return; }
  ptModal(`
    <h2>Juntar ${esc(l.nome)} (${l.cabecas} cab.)</h2>
    <p class="info">Os animais do ${esc(l.nome)} vão para o lote escolhido, no piquete onde ele está.</p>
    <div id="pt-j-lista">${outros.map((o) => `
      <button type="button" class="pt-lote-escolha" data-lote="${o.id}">
        <b>${esc(o.nome)}</b> · ${ptLoteDescricao(o)}<br><small>${esc(ptNomePiquete(o.piqueteId))}</small>
      </button>`).join("")}</div>
    ${ptCampoData()}
    <div class="pt-linha-botoes">
      <button type="button" class="secundario" id="pt-j-cancelar">Cancelar</button>
      <button type="button" id="pt-j-ok" disabled>✔ Juntar</button>
    </div>`);
  let escolhido = null;
  document.querySelectorAll("#pt-j-lista .pt-lote-escolha").forEach((b) => {
    b.onclick = () => {
      document.querySelectorAll("#pt-j-lista .pt-lote-escolha").forEach((x) => x.classList.remove("ativo"));
      b.classList.add("ativo");
      escolhido = outros.find((o) => o.id === Number(b.dataset.lote));
      ptEl("pt-j-ok").disabled = false;
      ptEl("pt-j-ok").textContent = `✔ Juntar no ${escolhido.nome}`;
    };
  });
  ptEl("pt-j-cancelar").onclick = ptFecharModal;
  ptEl("pt-j-ok").onclick = () => {
    if (!escolhido) return;
    const data = ptEl("pt-data").value || ptHoje();
    ptFecharModal();
    ptExecutar("/api/pastos/juntar", { origem_id: l.id, destino_id: escolhido.id, data },
      `${l.nome} (${l.cabecas} cab.) juntado ao ${escolhido.nome}`,
      (d) => ptOtimistaJuntar(d, l.id, escolhido.id));
  };
}

// ---------------------------------------------------------------- Separar

async function ptAnimaisDoLote(lote) {
  try {
    return await api.get(`/api/pastos/lotes/${lote.id}/animais`, 15000);
  } catch (e) {
    if (!(e instanceof TypeError)) throw e;
    // Sem sinal: usa os animais salvos no aparelho (cache da mangueira).
    hidratarCacheAnimaisOfflineSeVazio();
    return [...cacheAnimais.porBrinco.values()].flat()
      .filter((a) => a.lote === lote.nome)
      .map((a) => ({ id: a.id, brinco: a.brinco, tipo: a.tipo, raca: a.raca, ultimo_peso: a.ultimo_peso }))
      .sort((a, b) => comparaBrinco(a.brinco, b.brinco));
  }
}

async function ptFormSeparar() {
  if (!pt.sel) return;
  const l = pt.sel.lote;
  const origemPiquete = pt.sel.piqueteId;
  ptModal(`<h2>Separar animais do ${esc(l.nome)}</h2><p class="info">Carregando animais…</p>`);
  let animais;
  try {
    animais = await ptAnimaisDoLote(l);
  } catch (e) {
    ptModal(`<h2>Separar animais</h2><p>Não foi possível carregar os animais: ${esc(e.message)}</p>`);
    return;
  }
  if (!animais.length) {
    ptModal(`<h2>Separar animais</h2><p>Não achei os animais desse lote${pt.offline ? " salvos no aparelho" : ""}.</p>`);
    return;
  }
  const outrosLotes = ptTodosLotes().filter((o) => o.id !== l.id);
  const opcoesPiquete = [
    `<option value="${origemPiquete ?? ""}">${esc(ptNomePiquete(origemPiquete))} (mesmo lugar)</option>`,
    ...pt.dados.piquetes.filter((p) => p.id !== origemPiquete)
      .sort((a, b) => ptNomePiquete(a.id).localeCompare(ptNomePiquete(b.id), "pt-BR", { numeric: true }))
      .map((p) => `<option value="${p.id}">${esc(ptNomePiquete(p.id))}</option>`),
    origemPiquete != null ? `<option value="">Sem piquete (curral, embarque…)</option>` : "",
  ].join("");

  ptModal(`
    <h2>Separar animais do ${esc(l.nome)}</h2>
    <input id="pt-s-busca" placeholder="Filtrar por brinco…" inputmode="numeric" autocomplete="off" />
    <div class="pt-linha-botoes" style="margin:8px 0">
      <button type="button" class="secundario" id="pt-s-todos">Marcar os visíveis</button>
      <button type="button" class="secundario" id="pt-s-nenhum">Desmarcar todos</button>
    </div>
    <div class="pt-animais" id="pt-s-lista">${animais.map((a) => `
      <label class="pt-animal" data-brinco="${esc(a.brinco)}">
        <input type="checkbox" value="${a.id}">
        <span class="pt-brinco">${esc(a.brinco)}</span>
        <span class="pt-det">${esc(a.tipo || "")}${a.raca ? " · " + esc(a.raca) : ""}${a.ultimo_peso ? " · " + ptNum(a.ultimo_peso, 0) + " kg" : ""}</span>
      </label>`).join("")}</div>
    <div class="info" id="pt-s-contador">Nenhum marcado</div>

    <label>Para onde vão os marcados?</label>
    <label class="pt-opcao"><input type="radio" name="pt-s-dest" value="novo" checked> Lote novo</label>
    <div id="pt-s-novo">
      <input id="pt-s-nome" placeholder="Nome do lote novo" />
      <label>Piquete do lote novo</label>
      <select id="pt-s-piquete">${opcoesPiquete}</select>
    </div>
    ${outrosLotes.length ? `
      <label class="pt-opcao"><input type="radio" name="pt-s-dest" value="existente"> Um lote que já existe</label>
      <select id="pt-s-lote" class="escondido">${outrosLotes.map((o) =>
        `<option value="${o.id}">${esc(o.nome)} — ${esc(ptNomePiquete(o.piqueteId))}</option>`).join("")}</select>` : ""}
    ${ptCampoData()}
    <div class="pt-linha-botoes">
      <button type="button" class="secundario" id="pt-s-cancelar">Cancelar</button>
      <button type="button" id="pt-s-ok">✔ Separar</button>
    </div>`);

  const marcados = () => [...document.querySelectorAll("#pt-s-lista input:checked")].map((i) => Number(i.value));
  const atualizarContador = () => {
    const n = marcados().length;
    ptEl("pt-s-contador").textContent = n ? `${n} de ${animais.length} marcado${n === 1 ? "" : "s"}` : "Nenhum marcado";
  };
  ptEl("pt-s-lista").addEventListener("change", atualizarContador);
  ptEl("pt-s-busca").oninput = () => {
    const t = ptEl("pt-s-busca").value.trim();
    document.querySelectorAll("#pt-s-lista .pt-animal").forEach((lin) => {
      lin.classList.toggle("escondido", !!t && !lin.dataset.brinco.includes(t));
    });
  };
  ptEl("pt-s-todos").onclick = () => {
    document.querySelectorAll("#pt-s-lista .pt-animal:not(.escondido) input").forEach((i) => (i.checked = true));
    atualizarContador();
  };
  ptEl("pt-s-nenhum").onclick = () => {
    document.querySelectorAll("#pt-s-lista input").forEach((i) => (i.checked = false));
    atualizarContador();
  };
  document.querySelectorAll('input[name="pt-s-dest"]').forEach((r) => {
    r.onchange = () => {
      const novo = r.value === "novo" && r.checked;
      ptEl("pt-s-novo").classList.toggle("escondido", !novo);
      if (ptEl("pt-s-lote")) ptEl("pt-s-lote").classList.toggle("escondido", novo);
    };
  });
  ptEl("pt-s-cancelar").onclick = ptFecharModal;
  ptEl("pt-s-ok").onclick = () => {
    const ids = marcados();
    if (!ids.length) { alert("Marque pelo menos um animal."); return; }
    const data = ptEl("pt-data").value || ptHoje();
    const destino = document.querySelector('input[name="pt-s-dest"]:checked').value;
    const corpo = { origem_id: l.id, animal_ids: ids, data };
    let rotulo, otimista;
    if (destino === "novo") {
      const nome = ptEl("pt-s-nome").value.trim();
      if (!nome) { alert("Dê um nome para o lote novo."); return; }
      if (ptTodosLotes().some((o) => o.nome.toLowerCase() === nome.toLowerCase())) {
        alert(`Já existe um lote "${nome}". Escolha outro nome ou "Um lote que já existe".`);
        return;
      }
      const piq = ptEl("pt-s-piquete").value;
      corpo.novo_lote = nome;
      corpo.piquete_id = piq ? Number(piq) : null;
      rotulo = `${ids.length} cab. separadas do ${l.nome} no lote novo ${nome}`;
      otimista = (d) => ptOtimistaSeparar(d, l.id, ids.length, { nome, piqueteId: corpo.piquete_id, data });
    } else {
      const alvo = outrosLotes.find((o) => o.id === Number(ptEl("pt-s-lote").value));
      corpo.lote_destino_id = alvo.id;
      rotulo = `${ids.length} cab. separadas do ${l.nome} para o ${alvo.nome}`;
      otimista = (d) => ptOtimistaSeparar(d, l.id, ids.length, { loteId: alvo.id });
    }
    ptFecharModal();
    ptExecutar("/api/pastos/separar", corpo, rotulo, otimista);
  };
}

// ---------------------------------------------------------------- Enviar (online ou fila)

// Envia a mudança. Sem rede (ou rede ruim) guarda na fila offline e já mostra o
// resultado na tela (atualização "otimista" dos dados salvos no aparelho).
async function ptExecutar(url, corpo, rotulo, otimista) {
  corpo.chave = novaChave();
  pt.sel = null;
  if (redeBoa()) {
    try {
      const r = await api.post(url, corpo, PRAZO_LANCAMENTO_MS);
      await ptCarregar();
      ptToast("✔ " + r.movimentacao.resumo, () => ptDesfazer(r.movimentacao.id));
      return;
    } catch (e) {
      if (!(e instanceof TypeError)) {
        alert(e.message);
        ptRender();
        return;
      }
      marcarRedeRuim();
    }
  }
  filaAdicionar({ url, corpo, rotulo: "Pastos: " + rotulo });
  const antes = JSON.stringify(pt.dados);
  try { otimista(pt.dados); } catch { /* se a simulação falhar, a tela só atualiza ao sincronizar */ }
  pt.dados.movimentacoes = [
    { id: "fila:" + corpo.chave, chave: corpo.chave, resumo: rotulo, data: corpo.data || ptHoje(),
      usuario: usuarioAtual && usuarioAtual.nome, pendente: true, desfeita: false },
    ...(pt.dados.movimentacoes || []),
  ];
  salvarOffline(CHAVE_PASTOS_OFFLINE, pt.dados);
  pt.offline = true;
  ptRender();
  ptToast("📡 Guardado no aparelho — será enviado quando tiver sinal.", () => {
    // Ainda não saiu do aparelho: desfazer = tirar da fila e voltar a tela.
    filaSalvar(filaLer().filter((x) => !(x.corpo && x.corpo.chave === corpo.chave)));
    pt.dados = JSON.parse(antes);
    salvarOffline(CHAVE_PASTOS_OFFLINE, pt.dados);
    ptRender();
  });
}

async function ptDesfazer(id) {
  if (String(id).startsWith("fila:")) {
    const chave = String(id).slice(5);
    const naFila = filaLer().some((x) => x.corpo && x.corpo.chave === chave);
    if (!naFila) { alert("Essa mudança já foi enviada. Atualize a tela e desfaça de novo."); return; }
    if (!confirm("Cancelar essa mudança que ainda não foi enviada?")) return;
    filaSalvar(filaLer().filter((x) => !(x.corpo && x.corpo.chave === chave)));
    pt.dados.movimentacoes = pt.dados.movimentacoes.filter((m) => m.id !== id);
    salvarOffline(CHAVE_PASTOS_OFFLINE, pt.dados);
    ptRender();
    ptToast("Cancelada. A tela volta ao normal quando a rede voltar e atualizar.");
    return;
  }
  if (!redeBoa()) { alert("Para desfazer uma mudança já gravada precisa de sinal."); return; }
  try {
    await api.post(`/api/pastos/movimentacoes/${id}/desfazer`, {}, PRAZO_LANCAMENTO_MS);
    ptEl("pt-toast").classList.add("escondido");
    await ptCarregar();
  } catch (e) {
    alert(e.message);
  }
}

function ptToast(texto, aoDesfazer) {
  const t = ptEl("pt-toast");
  t.innerHTML = `<span>${esc(texto)}</span>${aoDesfazer ? '<button type="button">↶ Desfazer</button>' : ""}`;
  t.classList.remove("escondido");
  if (aoDesfazer) t.querySelector("button").onclick = () => { t.classList.add("escondido"); aoDesfazer(); };
  clearTimeout(pt.toastTimer);
  pt.toastTimer = setTimeout(() => t.classList.add("escondido"), 12000);
}

// ---- Simulações locais (só pra tela sem sinal; o servidor é quem decide de verdade)

function ptTirarLote(d, loteId) {
  for (const p of d.piquetes) {
    const i = p.lotes.findIndex((l) => l.id === loteId);
    if (i >= 0) {
      const [l] = p.lotes.splice(i, 1);
      ptRecalcPiquete(p, d.hoje);
      return { lote: l, piquete: p };
    }
  }
  const i = d.sem_piquete.findIndex((l) => l.id === loteId);
  if (i >= 0) return { lote: d.sem_piquete.splice(i, 1)[0], piquete: null };
  return { lote: null, piquete: null };
}

function ptRecalcPiquete(p, hoje) {
  p.cabecas = p.lotes.reduce((s, l) => s + l.cabecas, 0);
  p.ua = Math.round(p.lotes.reduce((s, l) => s + (l.ua || 0), 0) * 10) / 10;
  p.ua_ha = p.hectares && p.ua ? Math.round((p.ua / p.hectares) * 100) / 100 : null;
  if (p.lotes.length) {
    p.status = "ocupado";
    p.dias = Math.max(...p.lotes.map((l) => l.dias || 0));
  } else {
    p.status = "descansando";
    p.dias = 0;
    p.ultima_saida = hoje || ptHoje();
  }
}

function ptOtimistaMover(d, loteId, piqueteId, data) {
  const { lote } = ptTirarLote(d, loteId);
  if (!lote) return;
  const destino = d.piquetes.find((p) => p.id === piqueteId);
  const dias = Math.max(0, Math.round((new Date(ptHoje() + "T00:00") - new Date(data + "T00:00")) / 86400000));
  destino.lotes.push({ ...lote, data_entrada: data, dias });
  ptRecalcPiquete(destino, d.hoje);
}

function ptOtimistaJuntar(d, origemId, destinoId) {
  const { lote } = ptTirarLote(d, origemId);
  if (!lote) return;
  for (const l of [...d.piquetes.flatMap((p) => p.lotes), ...d.sem_piquete]) {
    if (l.id === destinoId) {
      l.cabecas += lote.cabecas;
      l.ua = Math.round(((l.ua || 0) + (lote.ua || 0)) * 10) / 10;
    }
  }
  for (const p of d.piquetes) ptRecalcPiquete(p, d.hoje);
}

function ptOtimistaSeparar(d, origemId, n, destino) {
  let origem = null;
  for (const l of [...d.piquetes.flatMap((p) => p.lotes), ...d.sem_piquete]) if (l.id === origemId) origem = l;
  if (!origem) return;
  const uaPorCab = origem.cabecas ? (origem.ua || 0) / origem.cabecas : 0;
  origem.cabecas -= n;
  origem.ua = Math.round(uaPorCab * origem.cabecas * 10) / 10;
  if (origem.cabecas <= 0) ptTirarLote(d, origemId);
  const ua = Math.round(uaPorCab * n * 10) / 10;
  if (destino.loteId) {
    for (const l of [...d.piquetes.flatMap((p) => p.lotes), ...d.sem_piquete]) {
      if (l.id === destino.loteId) { l.cabecas += n; l.ua = Math.round(((l.ua || 0) + ua) * 10) / 10; }
    }
  } else {
    // Lote novo ainda não tem id no servidor: id provisório negativo (não dá pra
    // mexer nele de novo até sincronizar).
    const novo = { id: -Date.now(), nome: destino.nome, cabecas: n, ua, peso_medio: origem.peso_medio,
      data_entrada: destino.data, dias: 0 };
    const p = d.piquetes.find((x) => x.id === destino.piqueteId);
    if (p) p.lotes.push(novo); else d.sem_piquete.push(novo);
  }
  for (const p of d.piquetes) ptRecalcPiquete(p, d.hoje);
}

// ---------------------------------------------------------------- Mapa

const PT_CORES = { ocupado: "#ef6c00", descansando: "#f9a825", pronto: "#2e7d32", sem_registro: "#9e9e9e" };

function ptIniciarMapa() {
  if (pt.mapa || typeof L === "undefined") return;
  pt.mapa = L.map("pt-mapa", { zoomControl: true, tap: true });
  // Imagem de satélite gratuita (Esri). Sem sinal os polígonos continuam aparecendo.
  L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    { maxZoom: 19, attribution: "Imagens © Esri" },
  ).addTo(pt.mapa);
  // Ordem de baixo pra cima: outras áreas, divisa, piquetes, pinos dos lotes.
  pt.camadaUsos = L.featureGroup().addTo(pt.mapa);
  pt.camadaDivisa = L.featureGroup().addTo(pt.mapa);
  pt.camadaPiquetes = L.featureGroup().addTo(pt.mapa);
  pt.camadaPinos = L.featureGroup().addTo(pt.mapa);
  pt.pinos = {};
  pt.mapa.on("zoomend", ptAtualizarZoom);
  pt.mapa.setView([-23.5, -51], 5);
  pt.mapa.on("click", ptCliqueMapa);

  // Botão "onde estou" (ajuda a desenhar andando pelo piquete).
  const Local = L.Control.extend({
    onAdd() {
      const b = L.DomUtil.create("button", "");
      b.type = "button";
      b.textContent = "📍";
      b.title = "Onde estou";
      b.style.cssText = "width:42px;height:42px;padding:0;font-size:1.2rem;background:#fff;border:2px solid rgba(0,0,0,.2)";
      L.DomEvent.on(b, "click", (e) => {
        L.DomEvent.stop(e);
        pt.mapa.locate({ setView: true, maxZoom: 17 });
      });
      return b;
    },
  });
  new Local({ position: "topleft" }).addTo(pt.mapa);
  pt.mapa.on("locationfound", (e) => {
    if (pt.marcadorLocal) pt.marcadorLocal.remove();
    pt.marcadorLocal = L.circleMarker(e.latlng, { radius: 8, color: "#1565c0", fillOpacity: 0.9 }).addTo(pt.mapa);
  });
  pt.mapa.on("locationerror", () => alert("Não consegui pegar sua localização (GPS desligado ou sem permissão)."));
}

const PT_ZOOM_PERTO = 16;   // a partir daqui mostra nomes; antes, só os pinos coloridos
const PT_USOS = {
  lavoura: { nome: "Lavoura (soja, milho…)", cor: "#c9a227" },
  madeira: { nome: "Madeira / eucalipto", cor: "#4e342e" },
  reserva: { nome: "Reserva / mata", cor: "#1b5e20" },
  sede: { nome: "Sede / construções", cor: "#78909c" },
  outro: { nome: "Outro uso", cor: "#9e9e9e" },
};
const ptCamadasVisiveis = { lotes: true, piquetes: true, divisa: true, usos: true };

// Centro de um polígono (centroide do maior anel) — onde fica o pino do lote.
function ptCentro(geometria) {
  const aneis = geometria.type === "Polygon" ? [geometria.coordinates[0]]
    : geometria.coordinates.map((p) => p[0]);
  let melhor = null;
  for (const anel of aneis) {
    let a = 0, cx = 0, cy = 0;
    for (let i = 0; i < anel.length - 1; i++) {
      const [x1, y1] = anel[i], [x2, y2] = anel[i + 1];
      const f = x1 * y2 - x2 * y1;
      a += f; cx += (x1 + x2) * f; cy += (y1 + y2) * f;
    }
    if (!a) continue;
    const c = { area: Math.abs(a), lat: cy / (3 * a), lng: cx / (3 * a) };
    if (!melhor || c.area > melhor.area) melhor = c;
  }
  if (melhor) return L.latLng(melhor.lat, melhor.lng);
  return L.geoJSON(geometria).getBounds().getCenter();
}

function ptRenderMapa() {
  ptIniciarMapa();
  if (!pt.mapa) return;
  setTimeout(() => pt.mapa.invalidateSize(), 50);
  ptDesenharCamadas();
  pt.camadaPiquetes.clearLayers();
  pt.camadaPinos.clearLayers();
  pt.pinos = {};
  for (const p of pt.dados.piquetes) {
    if (!p.geometria) continue;
    const camada = L.geoJSON(p.geometria, {
      style: {
        color: "#fff", weight: 2, fillColor: PT_CORES[p.status] || PT_CORES.sem_registro,
        fillOpacity: pt.sel && pt.sel.piqueteId !== p.id ? 0.5 : 0.3,
      },
    });
    // Com lote dentro, o nome do piquete sobe pra não ficar em cima do pino.
    camada.bindTooltip(esc(p.nome), {
      permanent: true, direction: "center", className: "pt-rotulo pt-rotulo-piquete",
      offset: p.lotes.length ? [0, -38] : [0, 0],
    });
    camada.on("click", (e) => {
      L.DomEvent.stop(e);
      if (pt.desenho) { ptCliqueMapa(e); return; }
      if (pt.sel && pt.sel.piqueteId !== p.id) ptConfirmarMover(p.id);
      else ptFichaPiquete(p);
    });
    camada.addTo(pt.camadaPiquetes);

    // Um pino por lote, lado a lado quando há mais de um no mesmo piquete.
    const centro = ptCentro(p.geometria);
    p.lotes.forEach((l, i) => {
      const dx = (i - (p.lotes.length - 1) / 2) * 46;
      const sel = pt.sel && pt.sel.lote.id === l.id ? " selecionado" : "";
      const icone = L.divIcon({
        className: "pt-pino-box",
        html: `<div class="pt-pino${sel}" style="background:${esc(l.cor)};color:${ptCorTexto(l.cor)}">
                 <span class="pt-pino-icone">${esc(l.icone || "")}</span><span class="pt-pino-cab">${l.cabecas}</span>
               </div><div class="pt-pino-nome">${esc(l.nome)}</div>`,
        iconSize: [40, 40],
        iconAnchor: [20 - dx, 20],
      });
      const pino = L.marker(centro, { icon: icone, riseOnHover: true, zIndexOffset: sel ? 1000 : 0 });
      pino.on("click", (e) => {
        L.DomEvent.stop(e);
        if (pt.desenho) return;
        ptFichaLote(l.id);
      });
      pino.addTo(pt.camadaPinos);
      pt.pinos[l.id] = pino;
    });
  }
  ptAplicarVisibilidade();
  if (!pt.mapaEnquadrado) {
    const limites = L.featureGroup([...pt.camadaPiquetes.getLayers(), ...pt.camadaDivisa.getLayers()]);
    if (limites.getLayers().length) {
      pt.mapa.fitBounds(limites.getBounds(), { padding: [20, 20] });
      pt.mapaEnquadrado = true;
    }
  }
  ptAtualizarZoom();
  ptRenderLegendaLotes();
  const semMapa = pt.dados.piquetes.filter((p) => !p.geometria).length;
  ptEl("pt-lista").innerHTML = semMapa
    ? `<div class="info">${semMapa} piquete(s) sem contorno no mapa — veja na Lista.</div>` : "";
}

// Divisa da fazenda e áreas de outros usos (soja, madeira…): só contexto, por baixo.
function ptDesenharCamadas() {
  pt.camadaDivisa.clearLayers();
  pt.camadaUsos.clearLayers();
  for (const c of pt.dados.camadas || []) {
    if (c.tipo === "divisa") {
      L.geoJSON(c.geometria, {
        style: { color: "#ffeb3b", weight: 4, dashArray: "10 6", fill: false },
        interactive: false,
      }).addTo(pt.camadaDivisa);
    } else {
      const uso = PT_USOS[c.uso] || PT_USOS.outro;
      const camada = L.geoJSON(c.geometria, {
        style: { color: uso.cor, weight: 1.5, fillColor: uso.cor, fillOpacity: 0.35 },
      });
      camada.bindTooltip(esc(c.nome), { permanent: true, direction: "center", className: "pt-rotulo pt-rotulo-uso" });
      camada.on("click", (e) => {
        L.DomEvent.stop(e);
        if (pt.desenho) { ptCliqueMapa(e); return; }
        ptFichaCamada(c);
      });
      camada.addTo(pt.camadaUsos);
    }
  }
}

function ptAplicarVisibilidade() {
  const pares = { lotes: pt.camadaPinos, piquetes: pt.camadaPiquetes, divisa: pt.camadaDivisa, usos: pt.camadaUsos };
  for (const [k, camada] of Object.entries(pares)) {
    if (ptCamadasVisiveis[k] && !pt.mapa.hasLayer(camada)) camada.addTo(pt.mapa);
    if (!ptCamadasVisiveis[k] && pt.mapa.hasLayer(camada)) pt.mapa.removeLayer(camada);
  }
}

// De longe: só pinos coloridos (sem texto). De perto: nomes de lotes e piquetes.
function ptAtualizarZoom() {
  if (!pt.mapa) return;
  ptEl("pt-mapa").classList.toggle("pt-zoom-perto", pt.mapa.getZoom() >= PT_ZOOM_PERTO);
}

function ptRenderLegendaLotes() {
  const lotes = ptTodosLotes();
  ptEl("pt-legenda-lotes").innerHTML = lotes.length ? lotes.map((l) => `
    <button type="button" class="pt-legenda-lote" data-lote="${l.id}">
      ${ptMarcaLote(l)} <b>${esc(l.nome)}</b> · ${l.cabecas} cab.
      <small>${esc(ptNomePiquete(l.piqueteId))}${l.piqueteId != null && !pt.pinos[l.id] ? " (sem contorno)" : ""}</small>
    </button>`).join("") : '<p class="info">Nenhum lote com gado.</p>';
  ptEl("pt-legenda-lotes").querySelectorAll("[data-lote]").forEach((b) => {
    b.onclick = () => {
      const id = Number(b.dataset.lote);
      const pino = pt.pinos[id];
      if (pino) {
        pt.mapa.flyTo(pino.getLatLng(), Math.max(pt.mapa.getZoom(), PT_ZOOM_PERTO), { duration: 0.8 });
        ptEl("pt-mapa").scrollIntoView({ behavior: "smooth", block: "center" });
      }
      ptFichaLote(id);
    };
  });
}

// Ficha rápida do lote: números básicos, ações e a cor/ícone.
function ptFichaLote(loteId) {
  const l = ptTodosLotes().find((x) => x.id === loteId);
  if (!l) return;
  const p = l.piqueteId != null ? ptPiquete(l.piqueteId) : null;
  const icones = ["", "🐂", "🐄", "🐮", "⭐", "▲", "◆", "●", "A", "B", "C", "1", "2", "3"];
  ptModal(`
    <h2>${ptMarcaLote(l, true)} ${esc(l.nome)}</h2>
    <div class="pt-ficha-grade">
      <div><b>${l.cabecas}</b><span>cabeças</span></div>
      <div><b>${ptNum(l.peso_medio, 0)}</b><span>kg médio</span></div>
      <div><b>${ptNum(l.ua)}</b><span>UA</span></div>
      <div><b>${l.ugmd_medio != null ? ptNum(l.ugmd_medio, 3) : "—"}</b><span>GMD médio (último)</span></div>
    </div>
    <p>${p ? `📍 <b>${esc(ptNomePiquete(p.id))}</b>${p.hectares ? ` · ${ptNum(p.hectares, 2)} ha` : ""}${p.ua_ha ? ` · ${ptNum(p.ua_ha, 2)} UA/ha` : ""}<br>
       Entrou em ${ptDataBR(l.data_entrada)} · há ${l.dias} dia${l.dias === 1 ? "" : "s"} nesse piquete` : "📍 Sem piquete"}</p>
    <button type="button" class="pt-salgar" id="pt-fl-salgar">🧂 Salgar cocho</button>
    <div id="pt-fl-sal" class="sal-resumo info">Carregando o sal…</div>
    <div class="pt-ficha-acoes">
      <button type="button" id="pt-fl-mover">➜ Mover</button>
      <button type="button" class="secundario" id="pt-fl-separar">✂ Separar</button>
      <button type="button" class="secundario" id="pt-fl-juntar">🔗 Juntar</button>
      <button type="button" class="secundario" id="pt-fl-animais">🐄 Ver animais</button>
    </div>
    <label>Cor do lote</label>
    <div class="pt-paleta">${(pt.dados.paleta || []).map((c) => `
      <button type="button" class="pt-cor-opcao${c === l.cor ? " ativa" : ""}" data-cor="${c}" style="background:${c}" aria-label="cor ${c}"></button>`).join("")}</div>
    <label>Ícone</label>
    <div class="pt-icones">${icones.map((ic) => `
      <button type="button" class="pt-icone-opcao${(l.icone || "") === ic ? " ativa" : ""}" data-icone="${esc(ic)}">${ic ? esc(ic) : "∅"}</button>`).join("")}</div>`);

  const selecionarEFechar = () => {
    ptFecharModal();
    pt.sel = { lote: l, piqueteId: l.piqueteId };
    ptRender();
  };
  ptEl("pt-fl-mover").onclick = () => {
    selecionarEFechar();
    ptToast(pt.modo === "mapa" ? "Toque no piquete de destino no mapa." : "Toque em ➜ Levar para cá no piquete de destino.");
  };
  ptEl("pt-fl-separar").onclick = () => { selecionarEFechar(); ptFormSeparar(); };
  ptEl("pt-fl-juntar").onclick = () => { selecionarEFechar(); ptFormJuntar(); };
  ptEl("pt-fl-animais").onclick = () => { ptFecharModal(); abrirLote(l.id, l.nome); };
  ptEl("pt-fl-salgar").onclick = () => salFormulario(l);
  salResumoNaFicha(l, "pt-fl-sal");
  const salvar = async (corpo) => {
    try {
      await api.put(`/api/pastos/lotes/${l.id}/visual`, corpo, PRAZO_LANCAMENTO_MS);
      await ptCarregar();
      ptFichaLote(l.id);
    } catch (e) {
      alert(e instanceof TypeError ? "Trocar a cor precisa de sinal." : e.message);
    }
  };
  document.querySelectorAll(".pt-cor-opcao").forEach((b) => { b.onclick = () => salvar({ cor: b.dataset.cor }); });
  document.querySelectorAll(".pt-icone-opcao").forEach((b) => { b.onclick = () => salvar({ icone: b.dataset.icone }); });
}

// Toque numa área de outro uso (soja, madeira…).
function ptFichaCamada(c) {
  const uso = PT_USOS[c.uso] || PT_USOS.outro;
  ptModal(`
    <h2>${esc(c.nome)}</h2>
    <p>${esc(uso.nome)}${c.hectares ? ` · ${ptNum(c.hectares, 2)} ha` : ""}</p>
    <p class="info">Área de outro uso — aparece no mapa só como referência (não recebe gado).</p>
    ${ptEhDono() ? '<button type="button" class="perigo" id="pt-c-remover" style="width:100%">Remover do mapa</button>' : ""}`);
  if (ptEl("pt-c-remover")) ptEl("pt-c-remover").onclick = async () => {
    if (!confirm(`Remover "${c.nome}" do mapa?`)) return;
    try {
      await api.delete(`/api/pastos/camadas/${c.id}`);
      ptFecharModal();
      await ptCarregar();
    } catch (e) {
      alert(e.message);
    }
  };
}

// Ficha do piquete ao tocar no mapa (sem lote selecionado).
function ptFichaPiquete(p) {
  ptModal(`
    <h2>${esc(p.nome)}</h2>
    <p class="info">${esc(p.area || "Sem área")} · ${p.hectares ? ptNum(p.hectares, 2) + " ha" : "área não informada"}${p.capim ? " · " + esc(p.capim) : ""}</p>
    <p class="pt-status ${p.status}">${ptTextoStatus(p)}</p>
    ${p.lotes.length ? `<p>Toque num lote para mudá-lo de lugar:</p><div class="pt-lotes" id="pt-f-lotes">${p.lotes.map((l) => ptBotaoLote(l, p.id)).join("")}</div>` : ""}
    ${ptEhDono() ? '<button type="button" class="secundario" id="pt-f-editar" style="width:100%;margin-top:14px">⚙ Editar piquete</button>' : ""}`);
  document.querySelectorAll("#pt-f-lotes .pt-lote").forEach((b) => {
    b.onclick = () => { ptFecharModal(); ptSelecionar(Number(b.dataset.loteId), p.id); };
  });
  if (ptEl("pt-f-editar")) ptEl("pt-f-editar").onclick = () => ptFormPiquete(p);
}

// ---------------------------------------------------------------- Desenho (dono)

function ptAreaHa(pontos) {
  // Mesma fórmula do servidor (excesso esférico), só pra mostrar enquanto desenha.
  if (pontos.length < 3) return 0;
  const R = 6378137, rad = Math.PI / 180;
  let total = 0;
  for (let i = 0; i < pontos.length; i++) {
    const a = pontos[i], b = pontos[(i + 1) % pontos.length];
    total += (b.lng - a.lng) * rad * (2 + Math.sin(a.lat * rad) + Math.sin(b.lat * rad));
  }
  return Math.abs((total * R * R) / 2) / 10000;
}

function ptIniciarDesenho(piqueteExistente) {
  ptEncerrarDesenho();  // um desenho por vez (limpa algum que ficou pela metade)
  ptMudarModo("mapa");
  ptCancelarSelecao();
  pt.desenho = { pontos: [], camada: L.layerGroup().addTo(pt.mapa), piquete: piqueteExistente || null };
  ptEl("pt-desenho-barra").classList.remove("escondido");
  ptAtualizarDesenho();
  ptEl("pt-mapa").scrollIntoView({ behavior: "smooth", block: "center" });
}

function ptCliqueMapa(e) {
  if (!pt.desenho) return;
  pt.desenho.pontos.push(e.latlng);
  ptAtualizarDesenho();
}

function ptAtualizarDesenho() {
  const dz = pt.desenho;
  dz.camada.clearLayers();
  if (dz.pontos.length >= 3) L.polygon(dz.pontos, { color: "#ffeb3b", weight: 3, fillOpacity: 0.25 }).addTo(dz.camada);
  else if (dz.pontos.length === 2) L.polyline(dz.pontos, { color: "#ffeb3b", weight: 3 }).addTo(dz.camada);
  dz.pontos.forEach((pto) => L.circleMarker(pto, { radius: 6, color: "#ffeb3b", fillOpacity: 1 }).addTo(dz.camada));
  const n = dz.pontos.length;
  ptEl("pt-desenho-info").innerHTML = (dz.piquete ? `Redesenhando <b>${esc(dz.piquete.nome)}</b>. ` : "") +
    (n < 3 ? `Toque no mapa para marcar os cantos do piquete (${n} de no mínimo 3).`
      : `${n} pontos · <b>${ptNum(ptAreaHa(dz.pontos), 2)} ha</b>. Continue marcando ou toque em Concluir.`);
  ptEl("pt-desenho-ok").disabled = n < 3;
}

function ptEncerrarDesenho() {
  if (pt.desenho) pt.desenho.camada.remove();
  pt.desenho = null;
  ptEl("pt-desenho-barra").classList.add("escondido");
}

ptEl("pt-desenho-voltar").onclick = () => {
  if (!pt.desenho) return;
  pt.desenho.pontos.pop();
  ptAtualizarDesenho();
};
ptEl("pt-desenho-cancelar").onclick = ptEncerrarDesenho;
ptEl("pt-desenho-ok").onclick = () => {
  const dz = pt.desenho;
  if (!dz || dz.pontos.length < 3) return;
  const anel = dz.pontos.map((p) => [p.lng, p.lat]);
  anel.push(anel[0]);
  const geometria = { type: "Polygon", coordinates: [anel] };
  const existente = dz.piquete;
  ptEncerrarDesenho();
  if (existente) ptFormPiquete(existente, geometria);
  else ptFormPiquete(null, geometria);
};

// ---------------------------------------------------------------- Cadastro do piquete (dono)

function ptFormPiquete(p, geometriaNova) {
  const areas = pt.dados.areas || [];
  const haCalc = geometriaNova ? ptAreaHa(geometriaNova.coordinates[0].slice(0, -1).map(([lng, lat]) => ({ lng, lat }))) : null;
  const ha = geometriaNova ? haCalc : (p && p.hectares);
  ptModal(`
    <h2>${p ? "Editar piquete" : "Novo piquete"}</h2>
    <label>Nome</label><input id="pt-p-nome" value="${esc(p ? p.nome : "")}" />
    <label>Área / retiro</label>
    <select id="pt-p-area">
      <option value="">— sem área —</option>
      ${areas.map((a) => `<option value="${a.id}" ${p && p.area_id === a.id ? "selected" : ""}>${esc(a.nome)}</option>`).join("")}
      <option value="__nova__">+ nova área…</option>
    </select>
    <div id="pt-p-area-nova" class="escondido">
      <input id="pt-p-area-nome" placeholder="Nome da área (ex.: Sede, Castro/Rosa)" />
      <select id="pt-p-area-tipo">
        <option value="propria">Própria</option>
        <option value="arrendada">Arrendada de terceiros</option>
        <option value="azevem">Azevém de inverno (área de lavoura)</option>
        <option value="outra">Outra</option>
      </select>
    </div>
    <div class="grid-2">
      <div><label>Hectares</label><input id="pt-p-ha" inputmode="decimal" value="${ha ? ptNum(ha, 2) : ""}" /></div>
      <div><label>Descanso desejado (dias)</label><input id="pt-p-meta" inputmode="numeric" value="${p && p.descanso_meta_dias ? p.descanso_meta_dias : ""}" /></div>
    </div>
    ${geometriaNova ? `<p class="info">Área calculada pelo desenho: ${ptNum(haCalc, 2)} ha (pode corrigir).</p>` : ""}
    <label>Capim</label><input id="pt-p-capim" placeholder="Ex.: Marandu, Mombaça, Azevém" value="${esc(p && p.capim ? p.capim : "")}" />
    <label>Observação</label><input id="pt-p-obs" value="${esc(p && p.observacao ? p.observacao : "")}" />
    <div class="pt-linha-botoes">
      <button type="button" class="secundario" id="pt-p-cancelar">Cancelar</button>
      <button type="button" id="pt-p-salvar">✔ Salvar</button>
    </div>
    ${p ? `
      <div class="pt-linha-botoes">
        <button type="button" class="secundario" id="pt-p-redesenhar">✏ ${p.geometria ? "Redesenhar contorno" : "Desenhar contorno"}</button>
        <button type="button" class="perigo" id="pt-p-remover">Remover piquete</button>
      </div>` : ""}`);

  ptEl("pt-p-area").onchange = () => {
    ptEl("pt-p-area-nova").classList.toggle("escondido", ptEl("pt-p-area").value !== "__nova__");
  };
  ptEl("pt-p-cancelar").onclick = ptFecharModal;
  ptEl("pt-p-salvar").onclick = async () => {
    const nome = ptEl("pt-p-nome").value.trim();
    if (!nome) { alert("Dê um nome para o piquete."); return; }
    // "1.234,5" (padrão BR) ou "22.5" (ponto como decimal, comum no teclado do celular).
    const num = (v) => {
      let t = String(v).trim();
      if (t.includes(",")) t = t.replace(/\./g, "").replace(",", ".");
      const n = parseFloat(t);
      return isNaN(n) ? null : n;
    };
    const corpo = {
      nome,
      hectares: num(ptEl("pt-p-ha").value),
      descanso_meta_dias: parseInt(ptEl("pt-p-meta").value, 10) || null,
      capim: ptEl("pt-p-capim").value.trim() || null,
      observacao: ptEl("pt-p-obs").value.trim() || null,
    };
    if (geometriaNova) corpo.geometria = geometriaNova;
    try {
      const area = ptEl("pt-p-area").value;
      if (area === "__nova__") {
        const nomeArea = ptEl("pt-p-area-nome").value.trim();
        if (!nomeArea) { alert("Dê um nome para a área nova."); return; }
        const a = await api.post("/api/pastos/areas", { nome: nomeArea, tipo: ptEl("pt-p-area-tipo").value });
        corpo.area_id = a.id;
      } else {
        corpo.area_id = area ? Number(area) : null;
      }
      if (p) await api.put(`/api/pastos/piquetes/${p.id}`, corpo);
      else await api.post("/api/pastos/piquetes", corpo);
      ptFecharModal();
      pt.mapaEnquadrado = !!p;
      await ptCarregar();
    } catch (e) {
      alert(e instanceof TypeError ? "Cadastrar piquete precisa de sinal." : e.message);
    }
  };
  if (p) {
    ptEl("pt-p-redesenhar").onclick = () => { ptFecharModal(); ptIniciarDesenho(p); };
    ptEl("pt-p-remover").onclick = async () => {
      if (!confirm(`Remover o piquete ${p.nome}? (Se ele tiver histórico, só sai da lista.)`)) return;
      try {
        await api.delete(`/api/pastos/piquetes/${p.id}`);
        ptFecharModal();
        await ptCarregar();
      } catch (e) {
        alert(e.message);
      }
    };
  }
}

// ---------------------------------------------------------------- Importar arquivo (dono)

function ptFormImportar() {
  ptModal(`
    <h2>Importar arquivo de áreas</h2>
    <p class="info">Aceita KML ou KMZ (Google Earth, GPS, CAR), XML com conteúdo KML e GeoJSON.
      Cada contorno vira um piquete; as pastas do arquivo viram áreas.</p>
    <input type="file" id="pt-i-arquivo" accept=".kml,.kmz,.xml,.geojson,.json" />
    <div id="pt-i-previa"></div>`);
  ptEl("pt-i-arquivo").onchange = async () => {
    const arq = ptEl("pt-i-arquivo").files[0];
    if (!arq) return;
    ptEl("pt-i-previa").innerHTML = '<p class="info">Lendo o arquivo…</p>';
    const form = new FormData();
    form.append("arquivo", arq);
    let res;
    try {
      res = await _resposta(await fetch("/api/pastos/importar/ler", { method: "POST", headers: cabecalhos(), body: form }));
    } catch (e) {
      ptEl("pt-i-previa").innerHTML = `<p style="color:var(--vermelho)">${esc(e instanceof TypeError ? "Importar precisa de sinal." : e.message)}</p>`;
      return;
    }
    ptMostrarPrevia(res.areas);
  };
}

function ptMostrarPrevia(areas) {
  const totalHa = areas.reduce((s, a) => s + a.hectares, 0);
  ptEl("pt-i-previa").innerHTML = `
    <p><b>${areas.length}</b> área(s) encontrada(s) · ${ptNum(totalHa, 2)} ha no total. Confira os nomes:</p>
    <div class="pt-animais"><table class="pt-imp-tabela">
      <tr><th></th><th>Nome</th><th>Área (pasta)</th><th>ha</th></tr>
      ${areas.map((a, i) => `<tr>
        <td><input type="checkbox" data-i="${i}" checked style="width:22px;height:22px"></td>
        <td><input data-nome="${i}" value="${esc(a.nome)}"></td>
        <td><input data-area="${i}" value="${esc(a.area || "")}" placeholder="(padrão)"></td>
        <td>${ptNum(a.hectares, 2)}${a.hectares_arquivo && Math.abs(a.hectares_arquivo - a.hectares_calculado) >= 0.01
          ? `<br><small class="info" title="Área calculada pelo contorno">contorno: ${ptNum(a.hectares_calculado, 2)}</small>` : ""}</td></tr>`).join("")}
    </table></div>
    <label>O que é este arquivo?</label>
    <label class="pt-opcao"><input type="radio" name="pt-i-destino" value="piquetes" checked>
      Piquetes do gado (recebem lote e entram nos indicadores)</label>
    <label class="pt-opcao"><input type="radio" name="pt-i-destino" value="divisa">
      Divisa da fazenda (o contorno inteiro, sem divisões)</label>
    <label class="pt-opcao"><input type="radio" name="pt-i-destino" value="uso">
      Outras áreas da fazenda (soja, madeira, reserva…)</label>
    <div id="pt-i-bloco-piquetes">
      <label>Área para os que não têm pasta</label>
      <input id="pt-i-area" value="Sede" />
      <label>Tipo das áreas novas</label>
      <select id="pt-i-tipo">
        <option value="propria">Própria</option>
        <option value="arrendada">Arrendada de terceiros</option>
        <option value="azevem">Azevém de inverno (área de lavoura)</option>
        <option value="outra">Outra</option>
      </select>
    </div>
    <div id="pt-i-bloco-uso" class="escondido">
      <label>Uso dessas áreas</label>
      <select id="pt-i-uso">${Object.entries(PT_USOS).map(([k, u]) => `<option value="${k}">${esc(u.nome)}</option>`).join("")}</select>
    </div>
    <p class="info" id="pt-i-nota">Piquete com o mesmo nome na mesma área é atualizado (não duplica).
      Quando o arquivo informa a área, vale a área do arquivo (medida pelo técnico); o
      "contorno" é só a conferência calculada pelo app.</p>
    <div class="pt-linha-botoes">
      <button type="button" class="secundario" id="pt-i-cancelar">Cancelar</button>
      <button type="button" id="pt-i-ok">✔ Importar marcados</button>
    </div>`;
  const destino = () => document.querySelector('input[name="pt-i-destino"]:checked').value;
  document.querySelectorAll('input[name="pt-i-destino"]').forEach((r) => {
    r.onchange = () => {
      ptEl("pt-i-bloco-piquetes").classList.toggle("escondido", destino() !== "piquetes");
      ptEl("pt-i-bloco-uso").classList.toggle("escondido", destino() !== "uso");
      ptEl("pt-i-nota").textContent = destino() === "piquetes"
        ? "Piquete com o mesmo nome na mesma área é atualizado (não duplica)."
        : "Fica só no mapa, como referência: não recebe gado nem entra na lotação. Mesmo nome atualiza o contorno.";
    };
  });
  ptEl("pt-i-cancelar").onclick = ptFecharModal;
  ptEl("pt-i-ok").onclick = async () => {
    const editadas = areas.map((a, i) => ({
      ...a,
      nome: document.querySelector(`[data-nome="${i}"]`).value.trim() || a.nome,
      area: document.querySelector(`[data-area="${i}"]`).value.trim() || null,
    }));
    const selecionados = [...document.querySelectorAll("#pt-i-previa [data-i]:checked")].map((c) => Number(c.dataset.i));
    if (!selecionados.length) { alert("Marque pelo menos uma área."); return; }
    try {
      const r = await api.post("/api/pastos/importar/confirmar", {
        areas: editadas, selecionados,
        area_padrao: ptEl("pt-i-area").value.trim() || null,
        tipo_area: ptEl("pt-i-tipo").value,
        destino: destino(),
        uso: destino() === "uso" ? ptEl("pt-i-uso").value : null,
      });
      ptFecharModal();
      pt.mapaEnquadrado = false;
      await ptCarregar();
      ptMudarModo("mapa");
      const oQue = { piquetes: "piquete(s)", divisa: "divisa(s) da fazenda", uso: "área(s) de outro uso" }[destino()];
      ptToast(`✔ ${r.criados} ${oQue} criada(s)${r.atualizados ? `, ${r.atualizados} atualizada(s)` : ""}.`);
    } catch (e) {
      alert(e instanceof TypeError ? "Importar precisa de sinal." : e.message);
    }
  };
}

// ---------------------------------------------------------------- Ligações

function ptMudarModo(modo) {
  pt.modo = modo;
  document.querySelectorAll("[data-ptmodo]").forEach((b) => b.classList.toggle("ativa", b.dataset.ptmodo === modo));
  ptEl("pt-mapa-box").classList.toggle("escondido", modo !== "mapa");
  if (modo !== "mapa") ptEncerrarDesenho();
  ptRender();
}

document.querySelectorAll("[data-ptmodo]").forEach((b) => {
  b.onclick = () => ptMudarModo(b.dataset.ptmodo);
});
ptEl("pt-btn-importar").onclick = ptFormImportar;
document.querySelectorAll("[data-camada]").forEach((c) => {
  c.onchange = () => {
    ptCamadasVisiveis[c.dataset.camada] = c.checked;
    if (pt.mapa) ptAplicarVisibilidade();
  };
});
ptEl("pt-btn-desenhar").onclick = () => ptIniciarDesenho(null);

// A barra do lote selecionado só aparece dentro da aba Pastos.
document.querySelectorAll(".abas button").forEach((b) => {
  b.addEventListener("click", () => {
    if (b.dataset.aba !== "pastos") ptEncerrarDesenho();
    ptRenderBarra();
  });
});

// Quando a fila offline termina de enviar, atualiza a aba se ela estiver aberta.
window.addEventListener("fila-sincronizada", () => {
  if (ptEl("aba-pastos").classList.contains("ativa")) ptCarregar();
});
