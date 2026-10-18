// Histórico dos piquetes: ocupações com a "foto" de cada uma, pasto por período, dividir
// piquete e o GMD de referência por época (peso estimado entre pesagens).
//
// Regra de ouro: o passado não muda. Dividir encerra o piquete original com a área que
// ele tinha; trocar o pasto encerra o período anterior.

// ---------------------------------------------------------------- Histórico do piquete

const ptHist = { ordem: { col: "entrada", dir: -1 } };

async function ptHistoricoPiquete(piqueteId) {
  ptModal(`<h2>📜 Histórico</h2><p class="info">Carregando…</p>`);
  let h;
  try {
    h = await api.get(`/api/pastos/piquetes/${piqueteId}/historico?hoje=${ptHoje()}`, 15000);
  } catch (e) {
    ptModal(`<h2>📜 Histórico</h2><p>${esc(e instanceof TypeError ? "Precisa de sinal para ver o histórico." : e.message)}</p>`);
    return;
  }
  ptRenderHistorico(h);
}

function ptRenderHistorico(h) {
  const p = h.piquete;
  const est = (v, estimado) => (v == null ? "—" : (estimado ? "~" : "") + ptNum(v));
  const colunas = [
    ["entrada", "Entrada"], ["lote", "Lote"], ["dias", "Dias"], ["cabecas", "Cab."],
    ["ua_ha_entrada", "UA/ha"], ["gmd_periodo", "GMD"], ["pasto", "Pasto"], ["saida", "Saída"],
  ];
  const { col, dir } = ptHist.ordem;
  const linhas = h.ocupacoes.slice().sort((a, b) => {
    const va = a[col] ?? "", vb = b[col] ?? "";
    if (typeof va === "number" && typeof vb === "number") return (va - vb) * dir;
    return String(va).localeCompare(String(vb), "pt-BR", { numeric: true }) * dir;
  });
  const seta = (c) => (c === col ? (dir > 0 ? " ▲" : " ▼") : "");
  ptModal(`
    <h2>📜 ${esc(p.nome)}</h2>
    <p class="info">${p.hectares ? ptNum(p.hectares, 2) + " ha" : "área não informada"}${p.encerrado_em
      ? ` · encerrado em ${ptDataBR(p.encerrado_em)}` : ""}
      ${h.origem ? `<br>Veio da divisão de <a href="#" data-hist="${h.origem.id}">${esc(h.origem.nome)}</a>` : ""}
      ${h.partes.length ? `<br>Dividido em ${h.partes.map((x) => `<a href="#" data-hist="${x.id}">${esc(x.nome)}</a>`).join(", ")}` : ""}</p>

    <h3>Pasto</h3>
    ${h.pastos.length ? `<ul class="pt-pastos">${h.pastos.map((x) => `
      <li><b>${esc(x.especie)}</b> · desde ${ptDataBR(x.inicio)}${x.fim ? ` até ${ptDataBR(x.fim)}` : " <span class='tag'>atual</span>"}
        ${x.observacao ? `<small class="info"> — ${esc(x.observacao)}</small>` : ""}</li>`).join("")}</ul>`
      : '<p class="info">Nenhum pasto registrado.</p>'}

    <h3>Ocupações (${h.ocupacoes.length})</h3>
    <p class="info">UA/ha na entrada usa a área do piquete <b>naquela data</b>. "~" = peso estimado
      (último peso + GMD). GMD = ganho do lote no período, quando o lote não mudou de tamanho.</p>
    ${h.ocupacoes.length ? `<div class="sn-tabela-box"><table class="sn-tabela" id="pt-h-tabela">
      <tr>${colunas.map(([c, t]) => `<th data-col="${c}">${t}${seta(c)}</th>`).join("")}</tr>
      ${linhas.map((o) => `<tr>
        <td>${ptDataBR(o.entrada)}</td><td>${esc(o.lote || "")}</td><td>${o.dias}</td>
        <td>${o.cabecas ?? "—"}${o.cabecas_saida != null && o.cabecas_saida !== o.cabecas ? ` → ${o.cabecas_saida}` : ""}</td>
        <td>${est(o.ua_ha_entrada, o.entrada_estimada)}</td>
        <td>${o.gmd_periodo != null ? ptNum(o.gmd_periodo, 3) : "—"}</td>
        <td>${esc(o.pasto || "—")}</td><td>${o.saida ? ptDataBR(o.saida) : "<b>no piquete</b>"}</td></tr>`).join("")}
    </table></div>` : '<p class="info">Nenhum lote passou por aqui ainda.</p>'}`);
  document.querySelectorAll("#pt-h-tabela th[data-col]").forEach((th) => {
    th.onclick = () => {
      const c = th.dataset.col;
      ptHist.ordem = ptHist.ordem.col === c ? { col: c, dir: -ptHist.ordem.dir }
        : { col: c, dir: ["lote", "pasto"].includes(c) ? 1 : -1 };
      ptRenderHistorico(h);
    };
  });
  document.querySelectorAll("[data-hist]").forEach((a) => {
    a.onclick = (e) => { e.preventDefault(); ptHistoricoPiquete(Number(a.dataset.hist)); };
  });
}

// ---------------------------------------------------------------- Pasto do piquete (dono)

async function ptSecaoPasto(p, boxId) {
  const box = document.getElementById(boxId);
  let pers = [];
  try {
    pers = (await api.get(`/api/pastos/piquetes/${p.id}/historico?hoje=${ptHoje()}`, 15000)).pastos;
  } catch {
    box.innerHTML = '<p class="info">Sem sinal para carregar o pasto.</p>';
    return;
  }
  if (!document.getElementById(boxId)) return;
  const atuais = pers.filter((x) => !x.fim);
  box.innerHTML = `
    <p>${atuais.length ? `Atual: <b>${atuais.map((x) => esc(x.especie)).join(" + ")}</b>` : "Nenhum pasto registrado."}</p>
    ${pers.length ? `<ul class="pt-pastos">${pers.map((x) => `<li>${esc(x.especie)} · ${ptDataBR(x.inicio)}${x.fim ? " → " + ptDataBR(x.fim) : " → hoje"}
        ${!x.fim ? `<button type="button" class="pt-mini" data-encerrar="${x.id}">encerrar</button>` : ""}
        <button type="button" class="pt-mini perigo-texto" data-apagar-pasto="${x.id}" title="lançado errado">🗑</button></li>`).join("")}</ul>` : ""}
    <label>Novo pasto</label>
    ${await campoSelectHTML("pasto", "pt-ps-especie", "", "— escolha —")}
    <div class="grid-2">
      <div><label>Desde</label><input type="date" id="pt-ps-inicio" value="${ptHoje()}" max="${ptHoje()}" /></div>
      <div><label>Como?</label><select id="pt-ps-modo">
        <option value="troca">Troca / reforma (substitui o atual)</option>
        <option value="junto">Junto com o atual (sobressemeadura)</option></select></div>
    </div>
    <button type="button" class="secundario" id="pt-ps-salvar" style="width:100%;margin-top:8px">🌱 Registrar pasto</button>`;
  ligarCampoSelect("pt-ps-especie");
  const recarregar = () => ptSecaoPasto(p, boxId);
  ptEl("pt-ps-salvar").onclick = async () => {
    const especie = await valorCampoSelect("pasto", "pt-ps-especie");
    if (!especie) { alert("Escolha o pasto."); return; }
    try {
      await api.post(`/api/pastos/piquetes/${p.id}/pasto`, {
        especie, inicio: ptEl("pt-ps-inicio").value || ptHoje(),
        substitui: ptEl("pt-ps-modo").value === "troca",
      });
      await ptCarregar();
      recarregar();
    } catch (e) { alert(e instanceof TypeError ? "Precisa de sinal." : e.message); }
  };
  box.querySelectorAll("[data-encerrar]").forEach((b) => {
    b.onclick = async () => {
      const fim = prompt("Encerrar este pasto em qual data? (dd/mm/aaaa)", ptDataBR(ptHoje()));
      if (!fim) return;
      const [d, m, a] = fim.split("/");
      try {
        await api.put(`/api/pastos/pasto/${b.dataset.encerrar}/encerrar`, { fim: `${a}-${m}-${d}` });
        await ptCarregar();
        recarregar();
      } catch (e) { alert(e.message); }
    };
  });
  box.querySelectorAll("[data-apagar-pasto]").forEach((b) => {
    b.onclick = async () => {
      if (!confirm("Apagar este registro de pasto (lançado errado)?")) return;
      try {
        await api.delete(`/api/pastos/pasto/${b.dataset.apagarPasto}`);
        await ptCarregar();
        recarregar();
      } catch (e) { alert(e.message); }
    };
  });
}

// ---------------------------------------------------------------- Dividir piquete (dono)

// Estado da divisão enquanto o dono desenha as partes no mapa.
const ptDiv = { piquete: null, partes: [], data: null, destinos: {} };

function ptIniciarDivisao(p) {
  ptDiv.piquete = p;
  ptDiv.partes = [];
  ptDiv.data = ptHoje();
  ptDiv.destinos = {};
  ptFormDivisao();
}

function ptFormDivisao() {
  const p = ptDiv.piquete;
  const soma = ptDiv.partes.reduce((s, x) => s + x.hectares, 0);
  const letras = "ABCDEFGH";
  ptModal(`
    <h2>✂ Dividir ${esc(p.nome)}</h2>
    <p class="info">O piquete atual (${p.hectares ? ptNum(p.hectares, 2) + " ha" : "sem área"}) fica no histórico com a área
      de hoje, e cada parte vira um piquete novo, com o mesmo pasto. Desenhe cada parte no mapa.</p>
    ${ptDiv.partes.map((x, i) => `
      <div class="pt-div-parte">
        <input data-parte-nome="${i}" value="${esc(x.nome)}" />
        <span>${ptNum(x.hectares, 2)} ha</span>
        <button type="button" class="pt-mini perigo-texto" data-parte-tirar="${i}">✖</button>
      </div>`).join("")}
    <button type="button" class="secundario" id="pt-div-desenhar" style="width:100%">✏ Desenhar parte ${letras[ptDiv.partes.length] || ""}</button>
    ${ptDiv.partes.length ? `<p class="info">Soma das partes: ${ptNum(soma, 2)} ha${p.hectares ? ` (o piquete tinha ${ptNum(p.hectares, 2)} ha)` : ""}.</p>` : ""}
    ${p.lotes.length && ptDiv.partes.length >= 2 ? `
      <label>Onde fica o gado que está no piquete?</label>
      ${p.lotes.map((l) => `<div class="pt-div-lote">${ptMarcaLote(l)} <b>${esc(l.nome)}</b> (${l.cabecas} cab.)
        <select data-destino-lote="${l.id}">${ptDiv.partes.map((x, i) =>
          `<option value="${i}" ${ptDiv.destinos[l.id] === i ? "selected" : ""}>${esc(x.nome)}</option>`).join("")}</select></div>`).join("")}` : ""}
    <label>Data da divisão (cerca nova)</label>
    <input type="date" id="pt-div-data" value="${ptDiv.data}" max="${ptHoje()}" />
    <div class="pt-linha-botoes">
      <button type="button" class="secundario" id="pt-div-cancelar">Cancelar</button>
      <button type="button" id="pt-div-ok" ${ptDiv.partes.length < 2 ? "disabled" : ""}>✔ Dividir</button>
    </div>`);
  const guardarCampos = () => {
    document.querySelectorAll("[data-parte-nome]").forEach((inp) => {
      ptDiv.partes[Number(inp.dataset.parteNome)].nome = inp.value.trim();
    });
    document.querySelectorAll("[data-destino-lote]").forEach((s) => {
      ptDiv.destinos[s.dataset.destinoLote] = Number(s.value);
    });
    ptDiv.data = ptEl("pt-div-data").value || ptHoje();
  };
  document.querySelectorAll("[data-parte-tirar]").forEach((b) => {
    b.onclick = () => { guardarCampos(); ptDiv.partes.splice(Number(b.dataset.parteTirar), 1); ptFormDivisao(); };
  });
  ptEl("pt-div-desenhar").onclick = () => {
    guardarCampos();
    ptFecharModal();
    ptIniciarDesenho(null);
    pt.desenho.divisao = true;
    ptAtualizarDesenho();
    // Mostra o contorno atual por baixo, pra desenhar as partes por cima dele.
    if (p.geometria) L.geoJSON(p.geometria, { style: { color: "#fff", weight: 3, dashArray: "6 6", fill: false } }).addTo(pt.desenho.camada);
  };
  ptEl("pt-div-cancelar").onclick = ptFecharModal;
  ptEl("pt-div-ok").onclick = async (ev) => {
    guardarCampos();
    if (ptDiv.partes.some((x) => !x.nome)) { alert("Dê um nome para cada parte."); return; }
    for (const l of p.lotes) if (ptDiv.destinos[l.id] == null) ptDiv.destinos[l.id] = 0;
    if (!confirm(`Dividir ${p.nome} em ${ptDiv.partes.map((x) => x.nome).join(", ")}? A divisão não pode ser desfeita pelo botão Desfazer.`)) return;
    const btn = ev.currentTarget;
    btn.disabled = true;
    btn.textContent = "Dividindo…";
    try {
      const r = await api.post(`/api/pastos/piquetes/${p.id}/dividir`, {
        partes: ptDiv.partes.map((x) => ({ nome: x.nome, geometria: x.geometria })),
        data: ptDiv.data, destinos: ptDiv.destinos,
      });
      ptFecharModal();
      await ptCarregar();
      ptToast("✔ " + r.resumo);
    } catch (e) {
      alert(e instanceof TypeError ? "Dividir precisa de sinal." : e.message);
      btn.disabled = false;
      btn.textContent = "✔ Dividir";
    }
  };
}

// Chamado quando o dono conclui o desenho de uma parte.
function ptParteDesenhada(geometria) {
  const letras = "ABCDEFGH";
  const ha = ptAreaHa(geometria.coordinates[0].slice(0, -1).map(([lng, lat]) => ({ lng, lat })));
  ptDiv.partes.push({ nome: `${ptDiv.piquete.nome} ${letras[ptDiv.partes.length] || ptDiv.partes.length + 1}`,
    geometria, hectares: Math.round(ha * 100) / 100 });
  ptFormDivisao();
}

// ---------------------------------------------------------------- GMD de referência (Config)

const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

async function ptConfigGmd(boxId) {
  const box = document.getElementById(boxId);
  if (!box) return;
  let cfg;
  try { cfg = await api.get("/api/pastos/config-gmd"); } catch (e) { box.textContent = e.message; return; }
  const linha = (e, i) => `
    <div class="pt-gmd-linha" data-i="${i}">
      <input data-k="nome" value="${esc(e.nome)}" placeholder="Época" />
      <select data-k="inicio">${MESES.map((m, k) => `<option value="${k + 1}" ${e.inicio === k + 1 ? "selected" : ""}>${m}</option>`).join("")}</select>
      <span>a</span>
      <select data-k="fim">${MESES.map((m, k) => `<option value="${k + 1}" ${e.fim === k + 1 ? "selected" : ""}>${m}</option>`).join("")}</select>
      <input data-k="gmd" inputmode="decimal" value="${String(e.gmd).replace(".", ",")}" title="kg/dia" />
      <button type="button" class="pt-mini perigo-texto" data-tirar="${i}">✖</button>
    </div>`;
  const render = (epocas) => {
    box.innerHTML = `
      <p class="info">Usado quando o lote <b>ainda não tem GMD</b> (só uma pesagem, recém-comprado).
        Com GMD, vale o ganho do último período do próprio lote. A projeção vai até ${cfg.limite_dias} dias
        depois da última pesagem; passou disso, o app avisa que está na hora de pesar.</p>
      <div class="pt-gmd-cab"><span>Época</span><span>de</span><span></span><span>até</span><span>GMD kg/dia</span><span></span></div>
      ${epocas.map(linha).join("")}
      <div class="pt-linha-botoes">
        <button type="button" class="secundario" id="pt-gmd-add">+ época</button>
        <button type="button" id="pt-gmd-salvar">Salvar modificações</button>
      </div>
      <div class="info" id="pt-gmd-msg"></div>`;
    const ler = () => [...box.querySelectorAll(".pt-gmd-linha")].map((l) => ({
      nome: l.querySelector('[data-k="nome"]').value,
      inicio: Number(l.querySelector('[data-k="inicio"]').value),
      fim: Number(l.querySelector('[data-k="fim"]').value),
      gmd: l.querySelector('[data-k="gmd"]').value.replace(",", "."),
    }));
    box.querySelector("#pt-gmd-add").onclick = () => render([...ler(), { nome: "", inicio: 1, fim: 1, gmd: 0.3 }]);
    box.querySelectorAll("[data-tirar]").forEach((b) => {
      b.onclick = () => { const l = ler(); l.splice(Number(b.dataset.tirar), 1); render(l); };
    });
    box.querySelector("#pt-gmd-salvar").onclick = async (ev) => {
      const btn = ev.currentTarget;
      btn.disabled = true;
      btn.textContent = "Salvando…";
      try {
        cfg = await api.put("/api/pastos/config-gmd", { epocas: ler() });
        render(cfg.epocas);
        box.querySelector("#pt-gmd-msg").textContent = "✓ Salvo.";
      } catch (e) {
        box.querySelector("#pt-gmd-msg").textContent = e.message;
        btn.disabled = false;
        btn.textContent = "Salvar modificações";
      }
    };
  };
  render(cfg.epocas);
}
window.ptConfigGmd = ptConfigGmd;
