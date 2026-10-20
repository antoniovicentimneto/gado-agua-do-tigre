// Fechamento de venda/compra de gado no Financeiro (só dono).
// Abre do manejo (Rebanho › Manejos): traz cabeças, @ e valor bruto da mangueira; a pessoa
// completa com a nota (comprador, vencimento, descontos) e o app lança a receita bruta +
// cada desconto como despesa (venda) ou a compra + custos extras (compra).

async function abrirFechamentoFinanceiro(sessaoId, voltar = null) {
  let d, cad;
  try {
    [d, cad] = await Promise.all([api.get(`/api/fin/fechamento/${sessaoId}`), api.get("/api/fin/cadastros")]);
  } catch (e) {
    alert("Erro ao abrir o fechamento: " + e.message);
    return;
  }
  modalVoltar = voltar;
  ffRender(sessaoId, d, cad, voltar);
  modal.classList.remove("escondido");
}

function ffRender(sessaoId, d, cad, voltar) {
  const m = d.manejo;
  const f = d.fechamento;
  const venda = m.tipo === "venda";
  // linhas de desconto: as salvas ou as sugeridas
  const linhas = (f ? f.descontos : d.descontos_padrao).map((x) => ({ ...x }));
  const cats = cad.plano.filter((p) => p.tipo === (venda ? "receita" : "despesa") && p.setor === "Pecuária"
    && p.grupo === m.grupo && p.ativo !== false).map((p) => p.categoria);
  // o lançamento principal é o "Venda de…"/"Compra de…"; os outros são os descontos/custos
  const principal = f && f.lancamentos.find((l) => /^(Venda|Compra) de /.test(l.descricao || ""));
  const catAtual = (principal && principal.categoria) || m.categoria;
  const contas = cad.contas.filter((c) => c.ativo !== false).map((c) => c.nome);
  const fazendas = cad.fazendas.filter((x) => x.ativo !== false).map((x) => x.nome);

  const ficha = document.getElementById("ficha");
  ficha.innerHTML = `
    <h2>💰 ${venda ? "Fechar venda" : "Fechar compra"} no Financeiro</h2>
    <div class="sub">Manejo de ${fmt.data(d.sessao.data)} · ${m.cabecas} cabeças · ${fmt.peso(m.peso_total)} no total
      ${m.arrobas != null ? ` · ${m.arrobas.toLocaleString("pt-BR", { maximumFractionDigits: 2 })} @` : ""}
      ${m.preco ? ` · ${fmt.real(m.preco)}/${m.unidade}` : ""}</div>
    ${f ? `<div class="fin-alerta" style="background:var(--verde-claro);color:var(--verde)">✔ Já lançado no Financeiro por ${esc(f.criado_por || "—")}.
      Salvar de novo refaz os lançamentos (os antigos ficam excluídos, com motivo).</div>` : ""}
    ${m.pendentes ? `<div class="fin-alerta">⚠ ${m.pendentes} animal(is) ainda sem os dados do frigorífico — o valor bruto
      da mangueira está incompleto. Use o valor da nota.</div>` : ""}

    <div class="fin-grid">
      <div class="fin-largo"><label>${venda ? "Comprador" : "Vendedor"}</label>
        <input id="ff-contra" list="ff-dl" value="${esc((f && f.contraparte) || (venda ? "" : d.sessao.vendedor || ""))}" placeholder="frigorífico, produtor...">
        <datalist id="ff-dl">${cad.fornecedores.filter((x) => x.ativo !== false).map((x) => `<option value="${esc(x.nome)}">`).join("")}</datalist></div>
      <div><label>Data da nota</label><input id="ff-data" type="date" value="${(f && f.data) || d.sessao.data}"></div>
      <div><label>Nº da nota</label><input id="ff-nf" value="${esc((f && f.nf_numero) || "")}"></div>
      <div><label>Valor bruto da nota (R$)</label><input id="ff-bruto" inputmode="decimal"
        value="${String((f ? f.valor_bruto : m.valor_bruto) || "").replace(".", ",")}">
        <div class="info">Mangueira calculou ${fmt.real(m.valor_bruto)}</div></div>
      <div><label>Categoria</label><select id="ff-cat">${finOpcoes(cats, catAtual)}</select></div>
      <div><label>Fazenda</label><select id="ff-faz">${finOpcoes(fazendas, "Água do Tigre")}</select></div>
      <div><label>Conta</label><select id="ff-conta">${finOpcoes(contas, "")}</select></div>
      <div><label>${venda ? "Recebimento" : "Pagamento"} (1º vencimento)</label><input id="ff-venc" type="date" value="${(f && f.data) || d.sessao.data}"></div>
      <div><label>Parcelas</label><input id="ff-n" type="number" min="1" max="60" value="1"></div>
    </div>

    <h3 style="margin-top:14px">${venda ? "Descontos da nota" : "Custos extras da compra"}</h3>
    <div class="info">${venda
      ? "Cada desconto vira uma despesa (Funrural/SENAR em Impostos, frete e comissão em Comercialização). Percentual é só sugestão — vale o da nota. Desmarque “descontado” se o imposto não saiu da nota e vocês recolhem depois."
      : "Frete, comissão, GTA... entram como despesas separadas e somam no custo da compra."}</div>
    <div id="ff-desc"></div>
    <button type="button" id="ff-mais" class="secundario">+ ${venda ? "desconto" : "custo"}</button>

    <div class="sn-cards" style="margin-top:12px" id="ff-totais"></div>
    <label>Observação</label><input id="ff-obs" value="${esc((f && f.observacao) || "")}">

    <div class="fin-form-topo" style="margin-top:12px">
      ${f ? `<button type="button" id="ff-desfazer" class="perigo">Tirar do Financeiro</button>` : "<span></span>"}
      <button type="button" id="ff-salvar">💾 ${f ? "Salvar de novo" : "Lançar no Financeiro"}</button>
    </div>
    <div id="ff-msg" class="info"></div>`;

  const $ = (s) => ficha.querySelector(s);
  const bruto = () => finNum($("#ff-bruto").value);
  const desenharDescontos = () => {
    $("#ff-desc").innerHTML = linhas.map((x, i) => `
      <div class="fin-parcela" data-i="${i}">
        <input data-c="nome" value="${esc(x.nome || "")}" placeholder="nome">
        <input data-c="percentual" inputmode="decimal" style="max-width:70px" placeholder="%"
          value="${x.percentual != null && x.percentual !== "" ? String(x.percentual).replace(".", ",") : ""}">
        <input data-c="valor" inputmode="decimal" placeholder="R$" value="${x.valor ? String(x.valor).replace(".", ",") : ""}">
        ${venda ? `<label class="check" title="saiu do valor da nota"><input type="checkbox" data-c="descontado" ${x.descontado !== false ? "checked" : ""}> descontado</label>` : ""}
      </div>`).join("");
    $("#ff-desc").querySelectorAll("input").forEach((inp) => {
      inp.oninput = inp.onchange = () => {
        const x = linhas[Number(inp.closest("[data-i]").dataset.i)];
        const c = inp.dataset.c;
        if (c === "descontado") x.descontado = inp.checked;
        else if (c === "nome") x.nome = inp.value;
        else if (c === "percentual") {
          x.percentual = inp.value === "" ? null : finNum(inp.value);
          if (x.percentual != null) {
            x.valor = Math.round(bruto() * x.percentual) / 100;
            inp.closest("[data-i]").querySelector('[data-c="valor"]').value = String(x.valor).replace(".", ",");
          }
        } else x.valor = finNum(inp.value);
        totais();
      };
    });
  };
  // percentuais sugeridos viram valor quando ainda não há valor
  const aplicarPercentuais = () => linhas.forEach((x) => {
    if (x.percentual != null && x.percentual !== "" && !f) x.valor = Math.round(bruto() * x.percentual) / 100;
  });
  const totais = () => {
    const desc = linhas.filter((x) => !venda || x.descontado !== false).reduce((s, x) => s + (Number(x.valor) || 0), 0);
    const extra = linhas.reduce((s, x) => s + (Number(x.valor) || 0), 0);
    const b = bruto();
    $("#ff-totais").innerHTML = venda
      ? `<div class="sn-card"><b>${fmt.real(b)}</b><span>bruto (receita)</span></div>
         <div class="sn-card"><b>${fmt.real(desc)}</b><span>descontos (despesas)</span></div>
         <div class="sn-card"><b>${fmt.real(b - desc)}</b><span>líquido a receber</span></div>`
      : `<div class="sn-card"><b>${fmt.real(b)}</b><span>compra</span></div>
         <div class="sn-card"><b>${fmt.real(extra)}</b><span>custos extras</span></div>
         <div class="sn-card"><b>${fmt.real(b + extra)}</b><span>custo total${m.cabecas ? ` · ${fmt.real((b + extra) / m.cabecas)}/cab.` : ""}</span></div>`;
  };
  aplicarPercentuais();
  desenharDescontos();
  totais();
  $("#ff-bruto").oninput = () => {
    // recalcula os que estão por percentual
    linhas.forEach((x) => { if (x.percentual != null && x.percentual !== "") x.valor = Math.round(bruto() * x.percentual) / 100; });
    desenharDescontos();
    totais();
  };
  $("#ff-mais").onclick = () => { linhas.push({ chave: "outro", nome: "", valor: 0, descontado: true }); desenharDescontos(); };

  $("#ff-salvar").onclick = (ev) => {
    const btn = ev.currentTarget;
    finOcupado(btn, "Lançando…", async () => {
      const dados = {
        contraparte: $("#ff-contra").value, data: $("#ff-data").value, nf_numero: $("#ff-nf").value,
        valor_bruto: bruto(), categoria: $("#ff-cat").value, fazenda: $("#ff-faz").value,
        conta: $("#ff-conta").value || null, vencimento: $("#ff-venc").value, n_parcelas: Number($("#ff-n").value) || 1,
        observacao: $("#ff-obs").value,
        descontos: linhas.map((x) => ({ ...x, vencimento: $("#ff-venc").value })),
      };
      try {
        await api.put(`/api/fin/fechamento/${sessaoId}`, dados);
      } catch (e) {
        $("#ff-msg").innerHTML = `<span class="fin-sem-cat">⚠ ${esc(e.message)}</span>`;
        return;
      }
      if (typeof finInvalidar === "function") finInvalidar();
      alert("✔ Lançado no Financeiro.");
      abrirFechamentoFinanceiro(sessaoId, voltar);
    });
  };
  const desf = $("#ff-desfazer");
  if (desf) desf.onclick = async () => {
    if (!confirm("Tirar esta venda/compra do Financeiro? Os lançamentos ficam excluídos (com motivo), nada é apagado.")) return;
    try {
      await api.delete(`/api/fin/fechamento/${sessaoId}`);
      if (typeof finInvalidar === "function") finInvalidar();
      abrirFechamentoFinanceiro(sessaoId, voltar);
    } catch (e) { alert("Erro: " + e.message); }
  };
}
