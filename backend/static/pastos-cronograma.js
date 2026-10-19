// Cronograma de rotação (aba Pastos › 📅 Cronograma): a fila de próximos piquetes de cada
// lote, com as datas previstas, avisos de descanso e o botão de mover para o próximo.

async function ptRenderCronograma() {
  const box = ptEl("pt-cronograma");
  box.innerHTML = '<p class="info">Carregando…</p>';
  let lista;
  try {
    lista = await api.get(`/api/pastos/cronograma?hoje=${ptHoje()}`, 20000);
  } catch (e) {
    box.innerHTML = `<p>${esc(semSinal(e) ? "O cronograma precisa de sinal." : e.message)}</p>`;
    return;
  }
  const hoje = ptHoje();
  const diasAte = (iso) => Math.round((new Date(iso + "T00:00") - new Date(hoje + "T00:00")) / 86400000);
  box.innerHTML = `
    <p class="info">Ordem: quem precisa sair primeiro. Toque em ✏ para montar a fila de piquetes de cada lote.</p>
    ${lista.length ? lista.map((c) => {
      const l = c.lote;
      const a = c.atual;
      const falta = a ? diasAte(a.saida_prevista) : null;
      const quando = falta == null ? "" : falta < 0 ? `<b class="cr-vencido">saída atrasada ${-falta} dia(s)</b>`
        : falta === 0 ? "<b class=\"cr-vencido\">sai hoje</b>" : `sai em ${falta} dia(s) (${ptDataBR(a.saida_prevista)})`;
      return `
      <div class="cr-lote">
        <div class="cr-topo">
          <div>${ptMarcaLote(l)} <b>${esc(l.nome)}</b> <small class="info">${l.cabecas} cab.</small><br>
            <small>📍 ${a ? `${esc(a.piquete)} · ${quando}` : "sem piquete"}</small></div>
          <button type="button" class="pt-mini" data-cr-editar="${l.id}">✏</button>
        </div>
        ${c.itens.length ? `<ol class="cr-fila">${c.itens.map((it) => `
          <li>${esc(it.piquete)} · ${it.dias} d <small class="info">(entra ${ptDataBR(it.entrada_prevista)})</small>
            ${it.aviso ? `<br><small class="cr-aviso">⚠ ${esc(it.aviso)}</small>` : ""}</li>`).join("")}</ol>
          <button type="button" class="cr-avancar" data-cr-avancar="${l.id}">➜ Mover agora para o ${esc(c.itens[0].piquete)}</button>`
          : '<p class="info">Sem próximos piquetes na fila.</p>'}
      </div>`;
    }).join("") : '<p class="info">Nenhum lote em piquete.</p>'}`;
  box.querySelectorAll("[data-cr-editar]").forEach((b) => { b.onclick = () => ptEditarCronograma(Number(b.dataset.crEditar)); });
  box.querySelectorAll("[data-cr-avancar]").forEach((b) => { b.onclick = () => ptAvancarCronograma(Number(b.dataset.crAvancar), b); });
}

async function ptAvancarCronograma(loteId, btn) {
  if (!redeBoa()) { alert("Sem sinal: use o ➜ Levar para cá na Lista (funciona offline)."); return; }
  if (!confirm(btn.textContent.replace("➜ ", "") + "?")) return;
  btn.disabled = true;
  try {
    const r = await api.post(`/api/pastos/lotes/${loteId}/cronograma/avancar`, { data: ptHoje(), chave: novaChave() }, PRAZO_LANCAMENTO_MS);
    await ptCarregar();
    ptToast("✔ " + r.movimentacao.resumo, () => ptDesfazer(r.movimentacao.id));
    if (pt.modo === "cronograma") ptRenderCronograma();
  } catch (e) {
    alert(semSinal(e) ? "Sem sinal agora." : e.message);
    btn.disabled = false;
  }
}

async function ptEditarCronograma(loteId) {
  ptModal(`<h2>📅 Cronograma</h2><p class="info">Carregando…</p>`);
  let c;
  try { c = await api.get(`/api/pastos/lotes/${loteId}/cronograma?hoje=${ptHoje()}`, 15000); } catch (e) {
    ptModal(`<h2>📅 Cronograma</h2><p>${esc(semSinal(e) ? "Precisa de sinal." : e.message)}</p>`);
    return;
  }
  const piquetes = (pt.dados.piquetes || []).slice().sort((a, b) => a.nome.localeCompare(b.nome, "pt-BR", { numeric: true }));
  let itens = c.itens.map((i) => ({ piquete_id: i.piquete_id, dias: i.dias, aviso: i.aviso, entrada: i.entrada_prevista }));
  const opcoesPiq = (sel) => piquetes.map((p) => `<option value="${p.id}" ${p.id === sel ? "selected" : ""}>${esc(p.nome)}${p.status === "ocupado" ? " (ocupado)" : ""}</option>`).join("");
  const desenhar = () => {
    ptModal(`
      <h2>📅 Cronograma — ${esc(c.lote.nome)}</h2>
      ${c.atual ? `<p>📍 Agora no <b>${esc(c.atual.piquete)}</b> desde ${ptDataBR(c.atual.entrada)}.</p>
        <label>Dias previstos no piquete atual</label>
        <input id="cr-dias-atual" inputmode="numeric" value="${c.atual.dias_previstos}" />` : '<p class="info">O lote está sem piquete.</p>'}
      <label>Próximos piquetes (na ordem)</label>
      <div id="cr-itens">${itens.map((it, i) => `
        <div class="cr-item">
          <span class="cr-n">${i + 1}</span>
          <select data-cr-piq="${i}">${opcoesPiq(it.piquete_id)}</select>
          <input data-cr-dias="${i}" inputmode="numeric" value="${it.dias}" title="dias" />
          <button type="button" class="pt-mini" data-cr-sobe="${i}" ${i === 0 ? "disabled" : ""}>↑</button>
          <button type="button" class="pt-mini perigo-texto" data-cr-tira="${i}">✖</button>
          ${it.aviso ? `<small class="cr-aviso">⚠ ${esc(it.aviso)}</small>` : ""}
        </div>`).join("") || '<p class="info">Nenhum ainda.</p>'}</div>
      <button type="button" class="secundario" id="cr-add" style="width:100%">+ adicionar piquete</button>
      <div class="pt-linha-botoes">
        <button type="button" class="secundario" id="cr-cancelar">Cancelar</button>
        <button type="button" id="cr-salvar">✔ Salvar</button>
      </div>`);
    const ler = () => {
      document.querySelectorAll("[data-cr-piq]").forEach((s) => { itens[Number(s.dataset.crPiq)].piquete_id = Number(s.value); });
      document.querySelectorAll("[data-cr-dias]").forEach((s) => { itens[Number(s.dataset.crDias)].dias = parseInt(s.value, 10) || 0; });
    };
    ptEl("cr-add").onclick = () => {
      ler();
      const usados = new Set(itens.map((i) => i.piquete_id));
      const livre = piquetes.find((p) => !usados.has(p.id) && p.id !== (c.atual && c.atual.piquete_id)) || piquetes[0];
      itens.push({ piquete_id: livre ? livre.id : null, dias: 7 });
      desenhar();
    };
    document.querySelectorAll("[data-cr-tira]").forEach((b) => { b.onclick = () => { ler(); itens.splice(Number(b.dataset.crTira), 1); desenhar(); }; });
    document.querySelectorAll("[data-cr-sobe]").forEach((b) => {
      b.onclick = () => { ler(); const i = Number(b.dataset.crSobe); [itens[i - 1], itens[i]] = [itens[i], itens[i - 1]]; desenhar(); };
    });
    ptEl("cr-cancelar").onclick = ptFecharModal;
    ptEl("cr-salvar").onclick = async (ev) => {
      ler();
      const btn = ev.currentTarget;
      btn.disabled = true;
      try {
        c = await api.put(`/api/pastos/lotes/${loteId}/cronograma`, {
          itens: itens.map((i) => ({ piquete_id: i.piquete_id, dias: i.dias })),
          dias_atual: ptEl("cr-dias-atual") ? parseInt(ptEl("cr-dias-atual").value, 10) || null : null,
        });
        itens = c.itens.map((i) => ({ piquete_id: i.piquete_id, dias: i.dias, aviso: i.aviso }));
        await ptCarregar();
        if (itens.some((i) => i.aviso)) { desenhar(); ptToast("Salvo — confira os avisos ⚠."); return; }
        ptFecharModal();
        ptToast("✔ Cronograma salvo.");
        if (pt.modo === "cronograma") ptRenderCronograma();
      } catch (e) {
        alert(semSinal(e) ? "Salvar o cronograma precisa de sinal." : e.message);
        btn.disabled = false;
      }
    };
  };
  desenhar();
}
