// Fechamento da venda peso morto (gancho): depois que o frigorífico/cooperativa manda
// o romaneio, lança-se por animal o peso de carcaça, o rendimento, o preço da @ e o
// acabamento de gordura — cada animal tem os seus, pela classificação.
// Abre a partir do manejo de venda (Rebanho › Manejos) ou do resumo ao finalizar.

const vgDinheiro = (v) =>
  v == null ? "—" : v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
const vgNum = (v, casas = 1) =>
  v == null ? "—" : v.toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
// Lê número de um campo aceitando vírgula ("52,5"); vazio/ inválido = null.
const vgLer = (input) => {
  const v = parseFloat(String(input.value).replace(",", "."));
  return isNaN(v) ? null : v;
};

let vgDados = null;   // última resposta do servidor (itens + totais)

async function abrirFechamentoVenda(sessaoId, voltar = null) {
  let d;
  try {
    d = await api.get(`/api/sessoes/${sessaoId}/venda-fechamento`);
  } catch (e) {
    alert("Erro ao abrir o fechamento da venda: " + e.message);
    return;
  }
  modalVoltar = voltar;
  vgRender(sessaoId, d);
  modal.classList.remove("escondido");
}

function vgRender(sessaoId, d) {
  vgDados = d;
  const opcoesAcab = (atual) => `<option value="">—</option>` + d.acabamentos
    .map((n) => `<option value="${esc(n)}" ${n === atual ? "selected" : ""}>${esc(n)}</option>`).join("");

  const opcoesDentes = (atual) => `<option value="">—</option>` + [0, 2, 4, 6, 8]
    .map((n) => `<option value="${n}" ${n === atual ? "selected" : ""}>${n}</option>`).join("");

  const linhas = d.itens.map((i) => `
    <tr data-animal="${i.animal_id}" data-vivo="${i.peso_vivo ?? ""}" data-dentes="${i.dentes ?? ""}" class="${i.pendente ? "vg-pendente" : ""}">
      <td class="vg-c-brinco"><b>${esc(i.brinco)}</b><div class="info">${esc(i.tipo || "")}${i.raca ? " · " + esc(i.raca) : ""}</div></td>
      <td data-rot="Peso fazenda">${i.peso_vivo == null ? "—" : vgNum(i.peso_vivo, 0) + " kg"}</td>
      <td data-rot="Carcaça (kg)"><input class="vg-carcaca" type="text" inputmode="decimal" value="${i.peso_carcaca ?? ""}" placeholder="kg"></td>
      <td data-rot="Rend. (%)"><input class="vg-rend" type="text" inputmode="decimal" value="${i.rendimento == null ? "" : +(i.rendimento * 100).toFixed(2)}" placeholder="%"></td>
      <td data-rot="Preço @"><input class="vg-preco" type="text" inputmode="decimal" value="${i.preco_arroba ?? ""}" placeholder="R$"></td>
      <td data-rot="Acabamento"><select class="vg-acab">${opcoesAcab(i.acabamento)}</select></td>
      <td data-rot="Dentes anotados" title="${i.data_dentes ? "anotado em " + fmt.data(i.data_dentes) : "sem dentição anotada"}">${i.dentes ?? "—"}</td>
      <td data-rot="Dentes frigorífico"><select class="vg-dentes">${opcoesDentes(i.dentes_frigorifico)}</select> <span class="vg-dif-aviso"></span></td>
      <td data-rot="Valor" class="vg-valor"></td>
    </tr>`).join("");

  const ficha = document.getElementById("ficha");
  ficha.innerHTML = `
    <h2>Fechar venda — peso morto</h2>
    <div class="sub">Manejo de ${fmt.data(d.sessao.data)} · lance os dados do romaneio do frigorífico, animal por animal.</div>

    <div class="ficha-secao">
      <label style="font-weight:600;font-size:0.85rem">Preço da @ padrão (R$)</label>
      <div class="linha-pesar">
        <input id="vg-preco-padrao" type="text" inputmode="decimal" value="${d.sessao.preco_arroba ?? ""}" placeholder="ex.: 330" />
        <button id="vg-aplicar-preco" class="secundario">Aplicar nos sem preço</button>
      </div>
      <div class="info">Preenche o preço dos animais que ainda estão em branco. Depois é só ajustar os que tiveram classificação diferente.</div>
    </div>

    <div class="ficha-secao">
      <div class="vg-tabela">
        <table>
          <thead><tr>
            <th>Brinco</th><th>Peso fazenda</th><th>Carcaça (kg)</th><th>Rend. (%)</th>
            <th>Preço @</th><th>Acabamento</th><th title="última dentição anotada na fazenda">Dentes anotados</th>
            <th title="dentes que o frigorífico considerou">Dentes frigorífico</th><th>Valor</th>
          </tr></thead>
          <tbody>${linhas || "<tr><td colspan=9>Nenhum animal nesta venda</td></tr>"}</tbody>
        </table>
      </div>
      <div class="info">Rendimento em branco = calculado sozinho (carcaça ÷ peso da fazenda). O animal fica <b>pendente</b> até ter carcaça e preço da @. Em <b>Dentes frigorífico</b>, lance o que o frigorífico considerou — quando for diferente do anotado na fazenda, a linha fica marcada.</div>
    </div>

    <div class="ficha-secao vg-totais" id="vg-totais"></div>

    <button id="vg-salvar" style="width:100%">Salvar</button>
    <div id="vg-msg" class="info"></div>`;

  ficha.querySelectorAll("tbody tr[data-animal]").forEach((tr) => {
    tr.querySelectorAll("input, select").forEach((c) => {
      c.oninput = () => { tr.dataset.mudou = "1"; vgRecalcular(); };
    });
  });

  document.getElementById("vg-aplicar-preco").onclick = () => {
    const padrao = vgLer(document.getElementById("vg-preco-padrao"));
    if (padrao == null || padrao <= 0) { alert("Informe o preço da @ padrão."); return; }
    ficha.querySelectorAll("tbody tr[data-animal]").forEach((tr) => {
      const campo = tr.querySelector(".vg-preco");
      if (campo.value.trim() === "") { campo.value = padrao; tr.dataset.mudou = "1"; }
    });
    vgRecalcular();
  };

  document.getElementById("vg-salvar").onclick = () => vgSalvar(sessaoId);
  vgRecalcular();
}

// Lê o que está digitado numa linha (rendimento vem em %, vira fração).
function vgLinha(tr) {
  const vivo = parseFloat(tr.dataset.vivo) || null;
  const carcaca = vgLer(tr.querySelector(".vg-carcaca"));
  const rendPct = vgLer(tr.querySelector(".vg-rend"));
  const preco = vgLer(tr.querySelector(".vg-preco"));
  return {
    animal_id: parseInt(tr.dataset.animal, 10), vivo, carcaca, preco,
    rendimento: rendPct != null ? rendPct / 100 : (carcaca && vivo ? carcaca / vivo : null),
    rendDigitado: rendPct != null,
    acabamento: tr.querySelector(".vg-acab").value,
    dentes: tr.dataset.dentes === "" ? null : parseInt(tr.dataset.dentes, 10),
    dentesFrig: tr.querySelector(".vg-dentes").value === "" ? null : parseInt(tr.querySelector(".vg-dentes").value, 10),
    valor: carcaca && preco ? (carcaca / 15) * preco : null,   // @ = 15 kg de carcaça
  };
}

// Recalcula o valor de cada linha e os totais com o que está na tela (antes de salvar).
function vgRecalcular() {
  let carcaca = 0, vivo = 0, valor = 0, fechados = 0, total = 0, dentesDif = 0, dentesLancados = 0;
  document.querySelectorAll("#ficha tbody tr[data-animal]").forEach((tr) => {
    const l = vgLinha(tr);
    total += 1;
    tr.querySelector(".vg-valor").textContent = vgDinheiro(l.valor);
    // Mostra o rendimento calculado como dica quando o campo está em branco.
    tr.querySelector(".vg-rend").placeholder =
      !l.rendDigitado && l.rendimento != null ? vgNum(l.rendimento * 100, 1) : "%";
    tr.classList.toggle("vg-pendente", l.valor == null);
    // Dentes: compara o anotado na fazenda com o que o frigorífico considerou.
    const dif = l.dentes != null && l.dentesFrig != null && l.dentes !== l.dentesFrig;
    if (l.dentesFrig != null) dentesLancados += 1;
    if (dif) dentesDif += 1;
    tr.classList.toggle("vg-dentes-dif", dif);
    tr.querySelector(".vg-dif-aviso").textContent =
      dif ? `⚠ ${l.dentesFrig > l.dentes ? "+" : "−"}${Math.abs(l.dentesFrig - l.dentes)}` : "";
    if (l.valor != null) {
      fechados += 1; carcaca += l.carcaca; vivo += l.vivo || 0; valor += l.valor;
    }
  });
  const arrobas = carcaca / 15;
  const caixa = (rotulo, texto) =>
    `<div class="destaque"><div class="rotulo">${rotulo}</div><div class="num" style="font-size:1.1rem">${texto}</div></div>`;
  document.getElementById("vg-totais").innerHTML =
    caixa("Fechados", `${fechados} de ${total}`) +
    caixa("Valor total", vgDinheiro(fechados ? valor : null)) +
    caixa("Arrobas (@)", fechados ? vgNum(arrobas, 2) : "—") +
    caixa("Preço médio da @", arrobas ? vgDinheiro(valor / arrobas) : "—") +
    caixa("Carcaça total", fechados ? vgNum(carcaca, 1) + " kg" : "—") +
    caixa("Rendimento médio", vivo ? vgNum((carcaca / vivo) * 100, 1) + " %" : "—") +
    caixa("Dentes diferentes do anotado", dentesLancados ? `${dentesDif} de ${dentesLancados}` : "—");
}

async function vgSalvar(sessaoId) {
  const itens = [];
  let erro = null;
  document.querySelectorAll("#ficha tbody tr[data-animal]").forEach((tr) => {
    if (tr.dataset.mudou !== "1") return;
    const l = vgLinha(tr);
    const brinco = tr.querySelector("b").textContent;
    if (l.carcaca != null && l.vivo && l.carcaca >= l.vivo) erro = `Brinco ${brinco}: carcaça maior que o peso da fazenda.`;
    if (l.rendDigitado && (l.rendimento <= 0.3 || l.rendimento >= 0.75)) erro = `Brinco ${brinco}: rendimento fora do normal (digite em %, ex.: 52,5).`;
    itens.push({
      animal_id: l.animal_id, peso_carcaca: l.carcaca, preco_arroba: l.preco,
      rendimento: l.rendDigitado ? +l.rendimento.toFixed(4) : null,
      acabamento: l.acabamento,
      dentes_frigorifico: l.dentesFrig,
    });
  });
  const msg = document.getElementById("vg-msg");
  if (erro) { alert(erro); return; }
  if (!itens.length) { msg.textContent = "Nada foi alterado."; return; }

  const btn = document.getElementById("vg-salvar");
  btn.disabled = true; btn.textContent = "Salvando...";
  try {
    const r = await api.post(`/api/sessoes/${sessaoId}/venda-fechamento`, { itens });
    vgRender(sessaoId, r);
    const t = r.totais;
    document.getElementById("vg-msg").textContent = t.pendentes
      ? `✓ Salvo. Ainda faltam ${t.pendentes} animal(is) pra fechar.`
      : `✓ Salvo. Venda fechada: ${vgDinheiro(t.valor)}.`;
  } catch (e) {
    alert("Erro ao salvar: " + e.message);
    btn.disabled = false; btn.textContent = "Salvar";
  }
}
