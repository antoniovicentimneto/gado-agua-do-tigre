// Seleção de vários piquetes (dono): editar em massa e unir piquetes.
// Também a cor do mapa por pastagem.

const ptMassa = { ativo: false, ids: new Set() };

function ptMassaAlternar() {
  ptMassa.ativo = !ptMassa.ativo;
  ptMassa.ids.clear();
  pt.sel = null;
  ptEl("pt-btn-selecionar").textContent = ptMassa.ativo ? "✖ Sair da seleção" : "☑ Selecionar piquetes";
  if (pt.modo !== "lista") ptMudarModo("lista"); else ptRender();
}

// Chamado pelo ptRenderLista: marca os cartões e liga o toque pra selecionar.
function ptMassaLigarCartoes(box) {
  if (!ptMassa.ativo) return;
  box.querySelectorAll(".pt-piquete").forEach((card) => {
    const id = Number(card.dataset.piquete);
    card.classList.add("pt-selecionavel");
    card.classList.toggle("pt-marcado", ptMassa.ids.has(id));
    card.onclick = (e) => {
      if (e.target.closest("button")) return;
      if (ptMassa.ids.has(id)) ptMassa.ids.delete(id); else ptMassa.ids.add(id);
      card.classList.toggle("pt-marcado", ptMassa.ids.has(id));
      ptMassaBarra();
    };
  });
  ptMassaBarra();
}

function ptMassaBarra() {
  const barra = ptEl("pt-barra");
  const visivel = ptMassa.ativo && ptEl("aba-pastos").classList.contains("ativa");
  if (!visivel) return false;
  barra.classList.remove("escondido");
  document.body.classList.add("pt-com-barra");
  const n = ptMassa.ids.size;
  barra.innerHTML = `
    <div class="pt-barra-titulo">☑ ${n} piquete(s) selecionado(s)</div>
    <div class="pt-barra-dica">Toque nos piquetes da lista para marcar ou desmarcar.</div>
    <div class="pt-barra-botoes">
      <button type="button" id="pt-m-editar" class="secundario" ${n ? "" : "disabled"}>✏ Editar em massa</button>
      <button type="button" id="pt-m-unir" class="secundario" ${n >= 2 ? "" : "disabled"}>🔗 Unir</button>
      <button type="button" id="pt-m-tudo" class="secundario">Marcar todos</button>
      <button type="button" id="pt-m-sair" class="secundario">✖ Sair</button>
    </div>`;
  ptEl("pt-m-editar").onclick = ptMassaEditar;
  ptEl("pt-m-unir").onclick = ptMassaUnir;
  ptEl("pt-m-tudo").onclick = () => { pt.dados.piquetes.forEach((p) => ptMassa.ids.add(p.id)); ptRender(); };
  ptEl("pt-m-sair").onclick = ptMassaAlternar;
  return true;
}

function ptMassaSelecionados() {
  return pt.dados.piquetes.filter((p) => ptMassa.ids.has(p.id));
}

async function ptMassaEditar() {
  const sel = ptMassaSelecionados();
  const grupos = (pt.dados.areas || []).map((a) => a.nome);
  ptModal(`
    <h2>✏ Editar ${sel.length} piquete(s)</h2>
    <p class="info">${sel.map((p) => esc(p.nome)).join(", ")}</p>
    <p class="info">Só muda o que você preencher — o resto fica como está.</p>
    <label>Grupo</label>
    <select id="pm-grupo"><option value="">— não alterar —</option><option value="__sem__">Sem grupo</option>
      ${grupos.map((g) => `<option>${esc(g)}</option>`).join("")}<option value="__novo__">+ novo grupo…</option></select>
    <input id="pm-grupo-novo" class="escondido" placeholder="Nome do grupo novo" />
    <label>Uso da área</label>
    <select id="pm-uso"><option value="">— não alterar —</option>
      ${Object.entries(PT_USOS_PIQUETE).map(([k, t]) => `<option value="${k}">${esc(t)}</option>`).join("")}</select>
    <div class="grid-2">
      <div><label>Descanso desejado (dias)</label><input id="pm-descanso" inputmode="numeric" /></div>
      <div><label>Máx. de dias com gado</label><input id="pm-ocup" inputmode="numeric" /></div>
    </div>
    <label>Pastagem</label>
    ${await campoSelectHTML("pasto", "pm-pasto", "", "— não alterar —")}
    <div class="grid-2">
      <div><label>Desde</label><input type="date" id="pm-pasto-inicio" value="${ptHoje()}" max="${ptHoje()}" /></div>
      <div><label>Como?</label><select id="pm-pasto-modo"><option value="troca">Troca / reforma</option>
        <option value="junto">Junto (sobressemeadura)</option></select></div>
    </div>
    <div class="pt-linha-botoes">
      <button type="button" class="secundario" id="pm-cancelar">Cancelar</button>
      <button type="button" id="pm-ok">✔ Aplicar</button>
    </div>`);
  ligarCampoSelect("pm-pasto");
  ptEl("pm-grupo").onchange = () => ptEl("pm-grupo-novo").classList.toggle("escondido", ptEl("pm-grupo").value !== "__novo__");
  ptEl("pm-cancelar").onclick = ptFecharModal;
  ptEl("pm-ok").onclick = async (ev) => {
    const btn = ev.currentTarget;   // ler antes de qualquer await (depois vira null)
    const g = ptEl("pm-grupo").value;
    const dados = {
      ids: [...ptMassa.ids],
      uso: ptEl("pm-uso").value || null,
      descanso_meta_dias: ptEl("pm-descanso").value || null,
      ocupacao_max_dias: ptEl("pm-ocup").value || null,
      pasto: (await valorCampoSelect("pasto", "pm-pasto")) || null,
      pasto_inicio: ptEl("pm-pasto-inicio").value || null,
      pasto_substitui: ptEl("pm-pasto-modo").value === "troca",
    };
    if (g === "__sem__") dados.sem_grupo = true;
    else if (g === "__novo__") dados.area_nome = ptEl("pm-grupo-novo").value.trim() || null;
    else if (g) dados.area_nome = g;
    btn.disabled = true;
    try {
      const r = await api.post("/api/pastos/piquetes/massa", dados);
      ptFecharModal();
      await ptCarregar();
      ptToast(`✔ ${r.alterados} piquete(s) alterado(s).`);
    } catch (e) {
      alert(semSinal(e) ? "Precisa de sinal." : e.message);
      btn.disabled = false;
    }
  };
}

function ptMassaUnir() {
  const sel = ptMassaSelecionados();
  const ha = sel.reduce((s, p) => s + (p.hectares || 0), 0);
  const pastos = [...new Set(sel.map((p) => p.capim || "—"))];
  const diferentes = pastos.length > 1;
  ptModal(`
    <h2>🔗 Unir ${sel.length} piquetes</h2>
    <p>${sel.map((p) => `<b>${esc(p.nome)}</b> (${ptNum(p.hectares, 2)} ha · ${esc(p.capim || "sem pasto")})`).join("<br>")}</p>
    <p class="info">Os piquetes de hoje ficam no histórico com a área que tinham; o novo terá
      <b>${ptNum(ha, 2)} ha</b>. O gado que estiver em qualquer um deles passa para o novo.</p>
    <label>Nome do piquete unido</label>
    <input id="pu-nome" value="${esc(sel.map((p) => p.nome).join(" + ").slice(0, 80))}" />
    ${diferentes ? `<label>Pastagem do piquete unido <span class="info">(eram diferentes)</span></label>
      <div id="pu-pasto-box"></div>` : `<p class="info">Pastagem: ${esc(pastos[0])} (herdada).</p>`}
    <label>Data da união (cerca tirada)</label>
    <input type="date" id="pu-data" value="${ptHoje()}" max="${ptHoje()}" />
    <div class="pt-linha-botoes">
      <button type="button" class="secundario" id="pu-cancelar">Cancelar</button>
      <button type="button" id="pu-ok">✔ Unir</button>
    </div>`);
  if (diferentes) {
    campoSelectHTML("pasto", "pu-pasto", "", "— não informar —").then((html) => {
      if (!ptEl("pu-pasto-box")) return;
      ptEl("pu-pasto-box").innerHTML = html;
      ligarCampoSelect("pu-pasto");
    });
  }
  ptEl("pu-cancelar").onclick = ptFecharModal;
  ptEl("pu-ok").onclick = async (ev) => {
    const nome = ptEl("pu-nome").value.trim();
    if (!nome) { alert("Dê um nome para o piquete unido."); return; }
    if (!confirm(`Unir em "${nome}"? A união não pode ser desfeita pelo botão Desfazer.`)) return;
    const btn = ev.currentTarget;
    btn.disabled = true;
    try {
      const r = await api.post("/api/pastos/piquetes/unir", {
        ids: [...ptMassa.ids], nome, data: ptEl("pu-data").value || ptHoje(),
        pasto: diferentes && ptEl("pu-pasto") ? ((await valorCampoSelect("pasto", "pu-pasto")) || null) : null,
      });
      ptFecharModal();
      ptMassa.ids.clear();
      await ptCarregar();
      ptToast("✔ " + r.resumo);
    } catch (e) {
      alert(semSinal(e) ? "Unir precisa de sinal." : e.message);
      btn.disabled = false;
    }
  };
}

// ---------------------------------------------------------------- Mapa colorido por pastagem

const PT_CORES_PASTO = ["#7cb342", "#00897b", "#c0ca33", "#f9a825", "#8d6e63", "#26a69a", "#9ccc65",
  "#ffb300", "#5d4037", "#43a047", "#d4e157", "#6d4c41"];
let ptColorirPor = "situacao";

function ptCorPasto(nome) {
  if (!nome) return "#bdbdbd";
  let h = 0;
  for (const c of nome) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return PT_CORES_PASTO[h % PT_CORES_PASTO.length];
}

function ptLegendaMapa() {
  const box = document.querySelector(".pt-legenda");
  if (!box) return;
  if (ptColorirPor === "pasto") {
    const nomes = [...new Set((pt.dados.piquetes || []).map((p) => p.capim || ""))].sort();
    box.innerHTML = nomes.map((n) => `<span><i class="pt-cor" style="background:${ptCorPasto(n)}"></i>${esc(n || "Sem pastagem")}</span>`).join("");
  } else {
    box.innerHTML = `<span><i class="pt-cor ocupado"></i>Ocupado</span><span><i class="pt-cor descansando"></i>Descansando</span>
      <span><i class="pt-cor pronto"></i>Pronto</span><span><i class="pt-cor sem_registro"></i>Sem registro</span>`;
  }
}
