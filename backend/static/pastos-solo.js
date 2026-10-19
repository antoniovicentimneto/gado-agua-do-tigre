// Solo e insumos do piquete (botão 🧪): análises de solo, calagem pela saturação por
// bases e aplicações (calcário, gesso, adubo, herbicida, semente).

const SOLO_TIPOS = { calcario: "Calcário", gesso: "Gesso", adubo: "Adubo / fertilizante",
  herbicida: "Herbicida", semente: "Semente", outro: "Outro" };

// V2 de referência pela pastagem (faixa usual; quem define é o técnico).
function soloV2Sugerido(capim) {
  const c = (capim || "").toLowerCase();
  if (/tifton|coast|estrela|jiggs|momba|tanz|zuri|panicum|azev|aveia/.test(c)) return 60;
  if (/braqui|marandu|piat|decumb|humid|xara|brizan/.test(c)) return 50;
  return 50;
}

async function ptSoloPiquete(piqueteId) {
  ptModal(`<h2>🧪 Solo</h2><p class="info">Carregando…</p>`);
  let s;
  try { s = await api.get(`/api/pastos/piquetes/${piqueteId}/solo`, 15000); } catch (e) {
    ptModal(`<h2>🧪 Solo</h2><p>${esc(semSinal(e) ? "Precisa de sinal." : e.message)}</p>`);
    return;
  }
  const p = s.piquete;
  const a = s.analises[0];
  const dono = ptEhDono();
  const v2 = soloV2Sugerido(p.capim);
  const fmt2 = (v) => (v == null ? "—" : ptNum(v, 2));
  ptModal(`
    <h2>🧪 ${esc(p.nome)}</h2>
    <p class="info">${p.hectares ? ptNum(p.hectares, 2) + " ha" : "sem área"} · ${esc(p.capim || "pastagem não informada")}</p>

    <h3>Última análise de solo</h3>
    ${a ? `<p class="info">${ptDataBR(a.data)}${a.laboratorio ? " · " + esc(a.laboratorio) : ""} · ${esc(a.profundidade || "")}</p>
      <div class="sn-cards solo-cards">
        <div class="sn-card"><b>${fmt2(a.v_pct)}%</b><span>V% (saturação por bases)</span></div>
        <div class="sn-card"><b>${fmt2(a.ph_cacl2)}</b><span>pH CaCl₂</span></div>
        <div class="sn-card"><b>${fmt2(a.p)}</b><span>P (mg/dm³)</span></div>
        <div class="sn-card"><b>${fmt2(a.k)}</b><span>K (cmolc/dm³)</span></div>
        <div class="sn-card"><b>${fmt2(a.ctc)}</b><span>CTC (cmolc/dm³)</span></div>
        <div class="sn-card"><b>${a.m_pct != null ? fmt2(a.m_pct) + "%" : "—"}</b><span>m% (alumínio)</span></div>
      </div>` : '<p class="info">Nenhuma análise lançada.</p>'}
    ${dono ? '<button type="button" class="secundario" id="solo-nova" style="width:100%">+ Lançar análise de solo</button>' : ""}

    ${a && a.v_pct != null && a.ctc ? `
      <h3>Calagem (saturação por bases)</h3>
      <div class="grid-2">
        <div><label>V2 desejado (%)</label><input id="solo-v2" inputmode="decimal" value="${v2}" /></div>
        <div><label>PRNT do calcário (%)</label><input id="solo-prnt" inputmode="decimal" value="80" /></div>
      </div>
      <p class="solo-resultado" id="solo-nc"></p>
      <p class="info">NC = (V2 − V1) × CTC ÷ PRNT, camada 0–20 cm. V2 sugerido pela pastagem
        (${v2}%) — confirme com o técnico. Adubação de P e K segue o manual da região.</p>` : ""}

    <h3>Aplicações (${s.aplicacoes.length})${s.custo_total ? ` · R$ ${ptNum(s.custo_total, 2)}` : ""}</h3>
    ${s.aplicacoes.length ? `<div class="sn-tabela-box"><table class="sn-tabela">
      <tr><th>Data</th><th>Insumo</th><th>Dose</th><th>Total</th><th>R$/ha</th><th></th></tr>
      ${s.aplicacoes.map((x) => `<tr><td>${ptDataBR(x.data)}</td>
        <td>${esc(x.tipo_nome)}<br><small class="info">${esc(x.produto)}</small></td>
        <td>${ptNum(x.dose, 2)} ${esc(x.unidade)}</td>
        <td>${ptNum(x.quantidade_total, 2)} ${esc(x.unidade.replace("/ha", ""))}</td>
        <td>${x.custo_ha != null ? ptNum(x.custo_ha, 2) : "—"}</td>
        <td>${dono ? `<button type="button" class="sn-apagar" data-apl="${x.id}">🗑</button>` : ""}</td></tr>`).join("")}
    </table></div>` : '<p class="info">Nenhuma aplicação registrada.</p>'}
    <button type="button" class="secundario" id="solo-aplicar" style="width:100%;margin-top:8px">+ Registrar aplicação</button>`);

  const calcular = async () => {
    const box = ptEl("solo-nc");
    if (!box) return;
    const v2v = ptEl("solo-v2").value.replace(",", "."), prnt = ptEl("solo-prnt").value.replace(",", ".");
    try {
      const r = await api.get(`/api/pastos/calagem?v1=${a.v_pct}&ctc=${a.ctc}&v2=${v2v}&prnt=${prnt}${p.hectares ? `&hectares=${p.hectares}` : ""}`);
      box.innerHTML = r.t_ha > 0
        ? `Calcário: <b>${ptNum(r.t_ha, 2)} t/ha</b>${r.total_t != null ? ` · <b>${ptNum(r.total_t, 2)} t</b> no piquete` : ""}`
        : "V% já está no alvo — não precisa de calcário.";
      box.dataset.tha = r.t_ha;
    } catch (e) { box.textContent = e.message; }
  };
  if (ptEl("solo-v2")) {
    ptEl("solo-v2").oninput = calcular;
    ptEl("solo-prnt").oninput = calcular;
    calcular();
  }
  if (ptEl("solo-nova")) ptEl("solo-nova").onclick = () => ptSoloFormAnalise(p);
  ptEl("solo-aplicar").onclick = () => {
    const tha = ptEl("solo-nc") && Number(ptEl("solo-nc").dataset.tha);
    ptSoloFormAplicacao(p, tha > 0 ? { tipo: "calcario", dose: tha, unidade: "t/ha" } : {});
  };
  document.querySelectorAll("[data-apl]").forEach((b) => {
    b.onclick = async () => {
      if (!confirm("Apagar esta aplicação?")) return;
      try { await api.delete(`/api/pastos/aplicacoes/${b.dataset.apl}`); ptSoloPiquete(p.id); } catch (e) { alert(e.message); }
    };
  });
}

function ptSoloFormAnalise(p) {
  const campo = (id, rot, dica) => `<div><label>${rot}</label><input id="sa-${id}" inputmode="decimal" placeholder="${dica || ""}" /></div>`;
  ptModal(`
    <h2>🧪 Análise de solo — ${esc(p.nome)}</h2>
    <div class="grid-2">
      <div><label>Data da coleta</label><input type="date" id="sa-data" value="${ptHoje()}" max="${ptHoje()}" /></div>
      <div><label>Profundidade</label><input id="sa-prof" value="0-20 cm" /></div>
    </div>
    <label>Laboratório</label><input id="sa-lab" placeholder="Opcional" />
    <div class="grid-2">
      ${campo("ph_cacl2", "pH (CaCl₂)")}${campo("mo", "MO (g/dm³)")}
      ${campo("p", "P (mg/dm³)")}${campo("k", "K (cmolc/dm³)", "se vier em mg/dm³, ÷ 391")}
      ${campo("ca", "Ca (cmolc/dm³)")}${campo("mg", "Mg (cmolc/dm³)")}
      ${campo("al", "Al (cmolc/dm³)")}${campo("h_al", "H+Al (cmolc/dm³)")}
      ${campo("argila", "Argila (%)")}
    </div>
    <label>Observação</label><input id="sa-obs" />
    <div class="pt-linha-botoes">
      <button type="button" class="secundario" id="sa-cancelar">Cancelar</button>
      <button type="button" id="sa-ok">✔ Salvar</button>
    </div>`);
  ptEl("sa-cancelar").onclick = () => ptSoloPiquete(p.id);
  ptEl("sa-ok").onclick = async (ev) => {
    const btn = ev.currentTarget;
    const dados = { data: ptEl("sa-data").value, profundidade: ptEl("sa-prof").value, laboratorio: ptEl("sa-lab").value,
      observacao: ptEl("sa-obs").value };
    for (const c of ["ph_cacl2", "mo", "p", "k", "ca", "mg", "al", "h_al", "argila"]) dados[c] = ptEl("sa-" + c).value;
    btn.disabled = true;
    try {
      await api.post(`/api/pastos/piquetes/${p.id}/analises`, dados);
      ptSoloPiquete(p.id);
    } catch (e) {
      alert(semSinal(e) ? "Precisa de sinal." : e.message);
      btn.disabled = false;
    }
  };
}

function ptSoloFormAplicacao(p, pre) {
  ptModal(`
    <h2>➕ Aplicação — ${esc(p.nome)}</h2>
    <label>Tipo</label>
    <select id="ap-tipo">${Object.entries(SOLO_TIPOS).map(([k, t]) => `<option value="${k}" ${pre.tipo === k ? "selected" : ""}>${t}</option>`).join("")}</select>
    <label>Produto</label><input id="ap-produto" placeholder="Ex.: Calcário dolomítico PRNT 80, Ureia, 20-00-20" />
    <div class="grid-2">
      <div><label>Dose por hectare</label><input id="ap-dose" inputmode="decimal" value="${pre.dose ? ptNum(pre.dose, 2) : ""}" /></div>
      <div><label>Unidade</label><select id="ap-unid">${["kg/ha", "t/ha", "L/ha"].map((u) => `<option ${u === (pre.unidade || "kg/ha") ? "selected" : ""}>${u}</option>`).join("")}</select></div>
      <div><label>Área aplicada (ha)</label><input id="ap-area" inputmode="decimal" value="${p.hectares ? ptNum(p.hectares, 2) : ""}" /></div>
      <div><label>Custo total (R$)</label><input id="ap-custo" inputmode="decimal" placeholder="Opcional" /></div>
    </div>
    <label>Data</label><input type="date" id="ap-data" value="${ptHoje()}" max="${ptHoje()}" />
    <label>Observação</label><input id="ap-obs" />
    <div class="pt-linha-botoes">
      <button type="button" class="secundario" id="ap-cancelar">Cancelar</button>
      <button type="button" id="ap-ok">✔ Salvar</button>
    </div>`);
  ptEl("ap-cancelar").onclick = () => ptSoloPiquete(p.id);
  ptEl("ap-ok").onclick = async (ev) => {
    const btn = ev.currentTarget;
    const num = (v) => String(v).trim().replace(/\./g, (m, i, t) => (t.includes(",") ? "" : ".")).replace(",", ".");
    btn.disabled = true;
    try {
      await api.post(`/api/pastos/piquetes/${p.id}/aplicacoes`, {
        tipo: ptEl("ap-tipo").value, produto: ptEl("ap-produto").value, dose: num(ptEl("ap-dose").value),
        unidade: ptEl("ap-unid").value, area_ha: num(ptEl("ap-area").value),
        custo_total: num(ptEl("ap-custo").value), data: ptEl("ap-data").value, observacao: ptEl("ap-obs").value,
      });
      ptSoloPiquete(p.id);
    } catch (e) {
      alert(semSinal(e) ? "Precisa de sinal." : e.message);
      btn.disabled = false;
    }
  };
}

// Tabela "Solo" nos Indicadores: última análise de cada piquete.
async function ptSoloResumoHTML() {
  let linhas;
  try { linhas = await api.get("/api/pastos/solo", 15000); } catch { return ""; }
  const com = linhas.filter((l) => l.data);
  return `
    <h3>Solo (última análise por piquete)</h3>
    ${com.length ? `<div class="sn-tabela-box"><table class="sn-tabela">
      <tr><th>Piquete</th><th>Data</th><th>V%</th><th>pH</th><th>P</th><th>K</th></tr>
      ${linhas.map((l) => `<tr><td><a href="#" data-solo="${l.piquete_id}">${esc(l.piquete)}</a></td>
        <td>${l.data ? ptDataBR(l.data) : "<span class='info'>sem análise</span>"}</td>
        <td>${l.v_pct != null ? ptNum(l.v_pct, 1) : "—"}</td><td>${l.ph_cacl2 != null ? ptNum(l.ph_cacl2, 1) : "—"}</td>
        <td>${l.p != null ? ptNum(l.p, 1) : "—"}</td><td>${l.k != null ? ptNum(l.k, 2) : "—"}</td></tr>`).join("")}
    </table></div>` : '<p class="info">Nenhuma análise de solo lançada ainda (botão 🧪 em cada piquete).</p>'}`;
}
