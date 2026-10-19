// Indicadores de rotação (aba Pastos › 📊 Indicadores): lotação média (UA/ha), ocupação e
// descanso médios, uso da área — no período, por época, por piquete e por pastagem.

const ptInd = { periodo: "safra", dados: null, ordem: { col: "nome", dir: 1 } };

function ptPeriodoIndicadores() {
  const hoje = new Date(ptHoje() + "T00:00");
  const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  const menos = (dias) => { const d = new Date(hoje); d.setDate(d.getDate() - dias); return iso(d); };
  const ano = hoje.getMonth() >= 6 ? hoje.getFullYear() : hoje.getFullYear() - 1;
  switch (ptInd.periodo) {
    case "30": return { inicio: menos(29), fim: ptHoje() };
    case "90": return { inicio: menos(89), fim: ptHoje() };
    case "365": return { inicio: menos(364), fim: ptHoje() };
    case "safra_anterior": return { inicio: `${ano - 1}-07-01`, fim: `${ano}-06-30` };
    default: return { inicio: `${ano}-07-01`, fim: `${ano + 1}-06-30` };
  }
}

async function ptRenderIndicadores() {
  const box = ptEl("pt-indicadores");
  const { inicio, fim } = ptPeriodoIndicadores();
  box.innerHTML = '<p class="info">Calculando…</p>';
  try {
    ptInd.dados = await api.get(`/api/pastos/indicadores?inicio=${inicio}&fim=${fim}&hoje=${ptHoje()}`, 20000);
  } catch (e) {
    box.innerHTML = `<p>${esc(semSinal(e) ? "Os indicadores precisam de sinal." : e.message)}</p>`;
    return;
  }
  ptDesenharIndicadores();
}

function ptDesenharIndicadores() {
  const d = ptInd.dados;
  const box = ptEl("pt-indicadores");
  const periodos = [["safra", "Safra atual (jul–jun)"], ["safra_anterior", "Safra anterior"],
    ["30", "Últimos 30 dias"], ["90", "Últimos 90 dias"], ["365", "Últimos 12 meses"]];
  const sel = `<select id="pt-ind-periodo">${periodos.map(([v, t]) =>
    `<option value="${v}" ${v === ptInd.periodo ? "selected" : ""}>${t}</option>`).join("")}</select>`;
  if (d.vazio) { box.innerHTML = sel + '<p class="info">Período no futuro.</p>'; ptLigarIndicadores(); return; }

  const card = (valor, rotulo, dica) => `<div class="sn-card" title="${esc(dica)}"><b>${valor ?? "—"}</b><span>${rotulo}</span></div>`;
  const { col, dir } = ptInd.ordem;
  const linhas = d.por_piquete.slice().sort((a, b) => {
    const va = a[col] ?? (typeof b[col] === "number" ? -Infinity : ""), vb = b[col] ?? (typeof a[col] === "number" ? -Infinity : "");
    if (typeof va === "number" && typeof vb === "number") return (va - vb) * dir;
    return String(va).localeCompare(String(vb), "pt-BR", { numeric: true }) * dir;
  });
  const seta = (c) => (c === col ? (dir > 0 ? " ▲" : " ▼") : "");
  const colunas = [["nome", "Piquete"], ["pasto", "Pasto"], ["hectares", "ha"], ["ocupacoes", "Ocup."],
    ["dias_ocupado", "Dias c/ gado"], ["lotacao", "UA/ha"], ["descanso_medio", "Descanso méd."]];

  box.innerHTML = `
    <div class="pt-ind-topo">${sel}<span class="info">${ptDataBR(d.inicio)} a ${ptDataBR(d.fim)}</span></div>
    <div class="sn-cards pt-ind-cards">
      ${card(d.lotacao_media != null ? ptNum(d.lotacao_media, 2) : null, "lotação média (UA/ha)", "Σ(UA × dias) ÷ Σ(hectares × dias) das ocupações do período")}
      ${card(d.ocupacao_media_dias != null ? ptNum(d.ocupacao_media_dias, 1) + " d" : null, "ocupação média", "dias entre entrada e saída do lote, em média")}
      ${card(d.descanso_medio_dias != null ? ptNum(d.descanso_medio_dias, 1) + " d" : null, "descanso médio", "dias sem gado entre duas ocupações do mesmo piquete")}
      ${card(d.uso_area_pct != null ? ptNum(d.uso_area_pct, 1) + "%" : null, "uso da área", "hectares × dias com gado ÷ (hectares × dias do período)")}
    </div>
    ${d.ocupacoes_sem_foto ? `<p class="info">⚠ ${d.ocupacoes_sem_foto} ocupação(ões) lançada(s) antes do registro de peso na entrada não entram na lotação.</p>` : ""}

    <h3>Por época</h3>
    <div class="sn-tabela-box"><table class="sn-tabela"><tr><th>Época</th><th>Lotação (UA/ha)</th></tr>
      ${d.por_epoca.map((e) => `<tr><td>${esc(e.epoca)}</td><td>${e.lotacao != null ? ptNum(e.lotacao, 2) : "—"}</td></tr>`).join("") || '<tr><td colspan="2">Sem ocupações com peso no período.</td></tr>'}
    </table></div>

    <h3>Por pastagem</h3>
    <div class="sn-tabela-box"><table class="sn-tabela"><tr><th>Pastagem</th><th>Lotação (UA/ha)</th><th>GMD no pasto</th></tr>
      ${d.por_pasto.map((p) => `<tr><td>${esc(p.pasto)}</td><td>${p.lotacao != null ? ptNum(p.lotacao, 2) : "—"}</td>
        <td>${p.gmd != null ? ptNum(p.gmd, 3) + " kg/dia" : "—"}</td></tr>`).join("") || '<tr><td colspan="3">Sem dados.</td></tr>'}
    </table></div>
    <p class="info">GMD no pasto = ganho das ocupações em que o lote entrou e saiu com o mesmo número de cabeças.</p>

    <h3>Por piquete</h3>
    <div class="sn-tabela-box"><table class="sn-tabela" id="pt-ind-tabela">
      <tr>${colunas.map(([c, t]) => `<th data-col="${c}">${t}${seta(c)}</th>`).join("")}</tr>
      ${linhas.map((x) => `<tr class="${x.ativo ? "" : "pt-ind-inativo"}">
        <td><a href="#" data-hist="${x.id}">${esc(x.nome)}</a></td><td>${esc(x.pasto || "")}</td>
        <td>${x.hectares != null ? ptNum(x.hectares, 2) : "—"}</td><td>${x.ocupacoes}</td><td>${x.dias_ocupado}</td>
        <td>${x.lotacao != null ? ptNum(x.lotacao, 2) : "—"}</td><td>${x.descanso_medio != null ? ptNum(x.descanso_medio, 1) : "—"}</td></tr>`).join("")}
    </table></div>`;
  ptLigarIndicadores();
  ptSoloResumoHTML().then((html) => {
    if (!html || pt.modo !== "indicadores") return;
    box.insertAdjacentHTML("beforeend", html);
    box.querySelectorAll("[data-solo]").forEach((a) => {
      a.onclick = (e) => { e.preventDefault(); ptSoloPiquete(Number(a.dataset.solo)); };
    });
  });
}

function ptLigarIndicadores() {
  const box = ptEl("pt-indicadores");
  ptEl("pt-ind-periodo").onchange = () => { ptInd.periodo = ptEl("pt-ind-periodo").value; ptRenderIndicadores(); };
  box.querySelectorAll("#pt-ind-tabela th[data-col]").forEach((th) => {
    th.onclick = () => {
      const c = th.dataset.col;
      ptInd.ordem = ptInd.ordem.col === c ? { col: c, dir: -ptInd.ordem.dir }
        : { col: c, dir: ["nome", "pasto"].includes(c) ? 1 : -1 };
      ptDesenharIndicadores();
    };
  });
  box.querySelectorAll("[data-hist]").forEach((a) => {
    a.onclick = (e) => { e.preventDefault(); ptHistoricoPiquete(Number(a.dataset.hist)); };
  });
}
