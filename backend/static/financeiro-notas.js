// Financeiro › Notas (caixa de entrada de NF-e), Extrato (OFX) e Cadastros
// (CPF/CNPJ com certificado digital, plano de contas, fornecedores, contas, fazendas,
// importar a planilha CONSIPA). Usa os ajudantes de financeiro.js (fin, finTabela...).

const finNotas = { situacao: "pendentes", contribuintes: null, buscouSefaz: false };
const finExt = { conta: "", soPendentes: true };
const finCadModo = { aba: "cpf" };

const finFmtDoc = (d) => {
  if (!d) return "—";
  if (d.length === 11) return d.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, "$1.$2.$3-$4");
  if (d.length === 14) return d.replace(/(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})/, "$1.$2.$3/$4-$5");
  return d;
};

// ----------------------------------------------------------------- Notas
async function finTelaNotas(alvo) {
  if (!finNotas.contribuintes) finNotas.contribuintes = await api.get("/api/fin/contribuintes");
  const comCert = finNotas.contribuintes.filter((c) => c.ativo && c.tem_certificado);
  alvo.innerHTML = `
    <div class="fin-acoes-topo">
      <label class="fin-botao-arquivo">📥 Enviar XML ou ZIP das notas<input type="file" id="fn-arquivos" accept=".xml,.zip" multiple hidden></label>
      <button type="button" id="fn-sefaz" class="secundario" ${comCert.length ? "" : "disabled"}>🔄 Buscar na SEFAZ</button>
      <select id="fn-situacao">
        <option value="pendentes">A lançar</option><option value="lancada">Lançadas</option>
        <option value="ignorada">Ignoradas</option><option value="">Todas</option>
      </select>
    </div>
    <div id="fn-status" class="info">${comCert.length
      ? comCert.map((c) => `${esc(c.nome)} (${finFmtDoc(c.documento)}): última busca ${c.ultima_consulta ? finDataHora(c.ultima_consulta) : "nunca"}${c.ultimo_retorno ? ` — ${esc(c.ultimo_retorno)}` : ""}`).join("<br>")
      : `Pra buscar as notas sozinho na SEFAZ, cadastre o CPF/CNPJ e o certificado digital em <a href="#" id="fn-ir-cad">Cadastros › CPF/CNPJ</a>. Enquanto isso, dá pra enviar o XML que o fornecedor manda por e-mail.`}</div>
    <div id="fn-lista"><div class="info">⏳ Carregando notas…</div></div>`;
  alvo.querySelector("#fn-situacao").value = finNotas.situacao;
  alvo.querySelector("#fn-situacao").onchange = (e) => { finNotas.situacao = e.target.value; finListarNotas(alvo); };
  const ir = alvo.querySelector("#fn-ir-cad");
  if (ir) ir.onclick = (e) => { e.preventDefault(); fin.modo = "cadastros"; finCadModo.aba = "cpf"; finRender(); };
  alvo.querySelector("#fn-arquivos").onchange = async (e) => {
    const fd = new FormData();
    [...e.target.files].forEach((f) => fd.append("arquivos", f));
    if (![...fd.keys()].length) return;
    alvo.querySelector("#fn-status").textContent = "⏳ Lendo as notas…";
    try {
      const r = await finUpload("/api/fin/notas/xml", fd);
      finMsg(`✔ ${r.importadas} nota(s) recebida(s)${r.erros.length ? ` · ${r.erros.length} com problema` : ""}`, !!r.erros.length);
      if (r.erros.length) alvo.querySelector("#fn-status").innerHTML = r.erros.map(esc).join("<br>");
      finListarNotas(alvo);
    } catch (err) {
      finMsg("⚠ " + err.message, true);
    }
    e.target.value = "";
  };
  alvo.querySelector("#fn-sefaz").onclick = (e) => finBuscarSefaz(alvo, e.target);
  await finListarNotas(alvo);
  // Ao abrir, busca sozinho (uma vez por visita) quem já pode — a SEFAZ limita 1x por hora.
  if (comCert.length && !finNotas.buscouSefaz) {
    finNotas.buscouSefaz = true;
    finBuscarSefaz(alvo, alvo.querySelector("#fn-sefaz"), true);
  }
}

async function finBuscarSefaz(alvo, botao, silencioso = false) {
  await finOcupado(botao, "Buscando…", async () => {
    const r = await api.post("/api/fin/notas/buscar-sefaz", {});
    finNotas.contribuintes = await api.get("/api/fin/contribuintes");
    const novas = r.reduce((s, x) => s + (x.novas || 0), 0);
    const erros = r.filter((x) => !x.ok);
    if (!silencioso || novas || erros.length) {
      finMsg(r.length ? `${novas} nota(s) nova(s)${erros.length ? " · " + erros.map((x) => x.mensagem).join("; ") : ""}`
        : "A SEFAZ só deixa consultar 1 vez por hora — tente mais tarde", !!erros.length);
    }
    if (document.getElementById("fn-lista")) {
      const status = alvo.querySelector("#fn-status");
      if (status) status.innerHTML = finNotas.contribuintes.filter((c) => c.tem_certificado).map((c) =>
        `${esc(c.nome)} (${finFmtDoc(c.documento)}): última busca ${c.ultima_consulta ? finDataHora(c.ultima_consulta) : "nunca"}${c.ultimo_retorno ? ` — ${esc(c.ultimo_retorno)}` : ""}`).join("<br>");
      finListarNotas(alvo);
    }
  });
}

async function finListarNotas(alvo) {
  const box = alvo.querySelector("#fn-lista");
  const notas = await api.get(`/api/fin/notas?situacao=${encodeURIComponent(finNotas.situacao)}`);
  const rotulo = { nova: "aguardando XML", completa: "pronta pra lançar", lancada: "lançada", ignorada: "ignorada" };
  finTabela(box, "notas", [
    { id: "data", rotulo: "Emissão", valor: (n) => n.data_emissao, data: true, html: (n) => finData(n.data_emissao) },
    { id: "emitente", rotulo: "Fornecedor", valor: (n) => n.emitente_nome, html: (n) => `<b>${esc(n.emitente_nome || "—")}</b> <span class="info">${finFmtDoc(n.emitente_doc)}</span>` },
    { id: "numero", rotulo: "Nº", valor: (n) => n.numero, html: (n) => esc(n.numero || "") },
    { id: "valor", rotulo: "Valor", valor: (n) => n.valor, num: true, html: (n) => finBRL(n.valor) },
    { id: "situacao", rotulo: "Situação", valor: (n) => n.situacao,
      html: (n) => `<span class="fin-pill ${n.situacao === "completa" ? "verde" : n.situacao === "nova" ? "amarelo" : ""}">${rotulo[n.situacao] || n.situacao}</span>` },
    { id: "origem", rotulo: "Veio de", valor: (n) => n.origem, html: (n) => (n.origem === "sefaz" ? "SEFAZ" : "XML enviado") },
  ], notas, { padrao: [{ col: "data", dir: -1 }], aoClicar: (n) => finAbrirNota(n.id, alvo),
    vazio: finNotas.situacao === "pendentes" ? "Nenhuma nota esperando lançamento 👍" : "Nenhuma nota." });
}

async function finAbrirNota(id, alvoTela) {
  let n;
  try {
    n = await api.get(`/api/fin/notas/${id}`);
  } catch (e) {
    finMsg("⚠ " + e.message, true);
    return;
  }
  const sug = n.sugestao || {};
  const geral = sug.geral || {};
  const parcelas = n.duplicatas && n.duplicatas.length ? n.duplicatas.map((d) => ({ vencimento: d.vencimento, valor: d.valor }))
    : [{ vencimento: n.data_emissao || hojeLocal(), valor: n.valor }];
  const semDup = !(n.duplicatas && n.duplicatas.length);
  const podeDividir = n.itens && n.itens.length > 1;
  const contrib = (finNotas.contribuintes || []).find((c) => c.id === n.contribuinte_id);
  const base = { tipo: geral.tipo || "despesa", fazenda: geral.fazenda || (contrib && contrib.fazenda) || "Água do Tigre",
    setor: geral.setor, grupo: geral.grupo, categoria: geral.categoria };
  finModal(`
    <form id="nl-form" class="fin-form">
      <div class="fin-form-topo"><h3>${esc(n.emitente_nome || "Nota")} · ${finBRL(n.valor)}</h3>
        <div class="fin-acoes">${n.situacao === "lancada"
          ? `<button type="button" id="nl-ver" class="secundario">Ver lançamento</button>`
          : `<button type="button" id="nl-ignorar" class="secundario">${n.situacao === "ignorada" ? "Voltar pra caixa" : "Ignorar"}</button>
             <button type="submit" id="nl-lancar">Lançar</button>`}</div></div>
      <div class="info">Nota ${esc(n.numero || "—")} · emitida em ${finData(n.data_emissao)} · ${finFmtDoc(n.emitente_doc)} · chave ${esc(n.chave)}</div>
      ${!n.completa ? `<div class="fin-alerta">Chegou só o resumo desta nota. A ciência já foi enviada à SEFAZ e o XML completo (itens e vencimentos) chega na próxima busca. Dá pra lançar já pelo total, se preferir.</div>` : ""}
      ${geral.origem ? `<div class="fin-sugestao">✨ Sugestão: <b>${esc(geral.categoria)}</b> — ${esc(geral.origem)}</div>` : ""}
      ${podeDividir ? `<label class="check"><input type="checkbox" id="nl-dividir"> Dividir por produto (cada um numa categoria)</label>` : ""}
      <div id="nl-geral">${finHtmlClasse("nl", base)}</div>
      ${n.itens && n.itens.length ? `<div class="fin-secao"><h3>Produtos</h3><div class="fin-tabela"><table>
        <thead><tr><th>Produto</th><th class="num">Qtde</th><th class="num">Valor</th><th class="nl-col-cat escondido">Categoria</th></tr></thead>
        <tbody>${n.itens.map((it, i) => {
          const s = (sug.itens || [])[i];
          return `<tr><td>${esc(it.descricao || "")} <span class="info">NCM ${esc(it.ncm || "—")}</span></td>
            <td class="num">${(it.qtde || 0).toLocaleString("pt-BR")} ${esc(it.unidade || "")}</td><td class="num">${finBRL(it.valor)}</td>
            <td class="nl-col-cat escondido"><select class="nl-item-cat" data-n="${it.n}" data-sug="${esc(s ? JSON.stringify(s) : "")}"></select></td></tr>`;
        }).join("")}</tbody></table></div></div>` : ""}
      <div class="fin-grid">
        <div><label>Conta (banco/cartão)</label><select id="nl-conta">${finOpcoes(finAtivos(fin.cad.contas).map((c) => c.nome), geral.conta)}</select></div>
        <div><label>Forma de pagamento</label><select id="nl-forma">${finOpcoes(["Pix", "Boleto", "Cartão de crédito", "Cartão de débito", "Dinheiro", "Transferência", "Débito automático", "Cheque", "Outros"], n.forma_pagamento)}</select></div>
        <div class="fin-largo"><label>Descrição</label><input id="nl-desc" placeholder="(em branco = nomes dos produtos)"></div>
      </div>
      <label>Vencimentos ${semDup ? `<span class="fin-pill amarelo">a nota não traz — confira</span>` : `<span class="info">(vindos da nota)</span>`}</label>
      <div id="nl-parcelas" class="fin-parcelas"></div>
      <button type="button" id="nl-mais-parc" class="secundario">+ parcela</button>
    </form>`, (corpo) => {
    const $ = (s) => corpo.querySelector(s);
    const classe = finLigarClasse(corpo, "nl", () => base.tipo, base);
    let parc = parcelas.slice();
    const desenharParc = () => {
      const soma = parc.reduce((s, p) => s + (Number(p.valor) || 0), 0);
      $("#nl-parcelas").innerHTML = parc.map((p, i) => `<div class="fin-parcela"><span>${i + 1}ª</span>
        <input type="date" data-i="${i}" data-c="vencimento" value="${p.vencimento}" class="${semDup ? "fin-preencher" : ""}">
        <input inputmode="decimal" data-i="${i}" data-c="valor" value="${String(p.valor).replace(".", ",")}">
        ${parc.length > 1 ? `<button type="button" class="secundario" data-tirar="${i}">×</button>` : ""}</div>`).join("") +
        (Math.abs(soma - n.valor) > 0.05 ? `<div class="fin-alerta">Soma das parcelas ${finBRL(soma)} ≠ valor da nota ${finBRL(n.valor)}</div>` : "");
      $("#nl-parcelas").querySelectorAll("input").forEach((inp) => {
        inp.onchange = () => { parc[Number(inp.dataset.i)][inp.dataset.c] = inp.dataset.c === "valor" ? finNum(inp.value) : inp.value; desenharParc(); };
      });
      $("#nl-parcelas").querySelectorAll("[data-tirar]").forEach((b) => { b.onclick = () => { parc.splice(Number(b.dataset.tirar), 1); desenharParc(); }; });
    };
    desenharParc();
    $("#nl-mais-parc").onclick = () => {
      const ult = parc[parc.length - 1];
      parc.push({ vencimento: finSomarMeses(ult ? ult.vencimento : hojeLocal(), 1), valor: 0 });
      desenharParc();
    };
    // Selects de categoria por produto (dividir): "Setor › Grupo › Categoria" do plano.
    const opcoesPlano = fin.cad.plano.filter((p) => p.tipo === "despesa" && p.ativo !== false);
    const rotuloPlano = (p) => `${p.categoria} (${p.setor} › ${p.grupo})`;
    corpo.querySelectorAll(".nl-item-cat").forEach((sel) => {
      const s = sel.dataset.sug ? JSON.parse(sel.dataset.sug) : null;
      sel.innerHTML = `<option value="">— escolha —</option>` + opcoesPlano.map((p) =>
        `<option value="${p.id}" ${s && s.categoria === p.categoria && s.setor === p.setor && s.grupo === p.grupo ? "selected" : ""}>${esc(rotuloPlano(p))}</option>`).join("");
    });
    const div = $("#nl-dividir");
    if (div) {
      div.onchange = () => {
        corpo.querySelectorAll(".nl-col-cat").forEach((el) => el.classList.toggle("escondido", !div.checked));
        $("#nl-geral").querySelectorAll("#nl-setor, #nl-grupo, #nl-categoria").forEach((el) => { el.closest("div").classList.toggle("escondido", div.checked); });
      };
      // Produtos que já foram lançados em categorias diferentes: já abre dividido.
      const cats = new Set((sug.itens || []).filter(Boolean).map((s) => `${s.setor}|${s.grupo}|${s.categoria}`));
      if (cats.size > 1) { div.checked = true; div.onchange(); }
    }
    const ver = $("#nl-ver");
    if (ver) ver.onclick = () => finAbrirLancamento(n.lancamento_id);
    const ign = $("#nl-ignorar");
    if (ign) {
      ign.onclick = () => finOcupado(ign, "…", async () => {
        await api.post(`/api/fin/notas/${n.id}/ignorar`, { voltar: n.situacao === "ignorada" });
        finMsg(n.situacao === "ignorada" ? "Nota voltou pra caixa de entrada" : "Nota ignorada (dá pra ver em 'Ignoradas')");
        finFecharTudo();
        finListarNotas(alvoTela);
      });
    }
    $("#nl-form").onsubmit = (ev) => {
      ev.preventDefault();
      const v = classe.valores();
      let partes;
      if (div && div.checked) {
        const grupos = {};
        for (const sel of corpo.querySelectorAll(".nl-item-cat")) {
          const p = opcoesPlano.find((x) => String(x.id) === sel.value);
          if (!p) { finMsg("Escolha a categoria de todos os produtos", true); sel.focus(); return; }
          const k = p.id;
          (grupos[k] = grupos[k] || { tipo: "despesa", fazenda: v.fazenda, setor: p.setor, grupo: p.grupo, categoria: p.categoria, itens: [] }).itens.push(Number(sel.dataset.n));
        }
        partes = Object.values(grupos);
      } else {
        if (!v.categoria) { finMsg("Escolha a categoria", true); return; }
        partes = [{ tipo: base.tipo, ...v }];
      }
      const dados = { fazenda: v.fazenda, conta: $("#nl-conta").value || null, forma_pagamento: $("#nl-forma").value || null,
        descricao: $("#nl-desc").value.trim() || null, parcelas: parc, partes, fornecedor_nome: n.emitente_nome };
      finOcupado($("#nl-lancar"), "Lançando…", async () => {
        const r = await api.post(`/api/fin/notas/${n.id}/lancar`, dados);
        finInvalidar();
        await finCarregarCadastros(true);
        finMsg(`✔ Nota lançada${r.lancamentos.length > 1 ? ` em ${r.lancamentos.length} partes` : ""}`);
        finFecharTudo();
        finListarNotas(alvoTela);
      });
    };
  });
}

// ----------------------------------------------------------------- Extrato (OFX)
async function finTelaExtrato(alvo) {
  const cad = fin.cad;
  const dados = await api.get(`/api/fin/extrato${finExt.conta ? `?conta=${encodeURIComponent(finExt.conta)}` : ""}`);
  alvo.innerHTML = `
    <div class="info">Baixe o extrato do banco ou do cartão em formato <b>OFX</b> (no internet banking: "Exportar extrato" → OFX/Money)
      e envie aqui. O app liga cada movimento ao lançamento de mesmo valor e data próxima. O que sobrar sem ligação saiu do banco e <b>não foi lançado</b>.</div>
    <div class="fin-acoes-topo">
      <select id="fe-conta">${finOpcoes(finAtivos(cad.contas).map((c) => c.nome), finExt.conta, "Escolha a conta do extrato")}</select>
      <label class="fin-botao-arquivo">📥 Enviar OFX<input type="file" id="fe-arquivo" accept=".ofx,.OFX" hidden></label>
      <label class="check"><input type="checkbox" id="fe-pend" ${finExt.soPendentes ? "checked" : ""}> só o que não foi lançado</label>
    </div>
    <div id="fe-resumo" class="fin-resumo"></div><div id="fe-tabela"></div>`;
  alvo.querySelector("#fe-conta").onchange = (e) => { finExt.conta = e.target.value; finRender(); };
  alvo.querySelector("#fe-pend").onchange = (e) => { finExt.soPendentes = e.target.checked; finRender(); };
  alvo.querySelector("#fe-arquivo").onchange = async (e) => {
    const arq = e.target.files[0];
    if (!arq) return;
    if (!finExt.conta) { finMsg("Escolha primeiro a conta do extrato", true); e.target.value = ""; return; }
    const fd = new FormData();
    fd.append("conta", finExt.conta);
    fd.append("arquivo", arq);
    try {
      const r = await finUpload("/api/fin/extrato", fd);
      finMsg(`✔ ${r.novos} movimento(s) novo(s) · ${r.conciliados_agora} ligado(s) a lançamentos`);
      finInvalidar();
      finRender();
    } catch (err) {
      finMsg("⚠ " + err.message, true);
    }
  };
  const movs = dados.movimentos.filter((m) => !finExt.soPendentes || (!m.parcela_id && !m.ignorado));
  const pend = dados.movimentos.filter((m) => !m.parcela_id && !m.ignorado);
  alvo.querySelector("#fe-resumo").innerHTML = `${dados.movimentos.length} movimentos · <b class="fin-negativo">${pend.length} sem lançamento</b> (${finBRL(pend.reduce((s, m) => s + m.valor, 0))})`;
  finTabela(alvo.querySelector("#fe-tabela"), "extrato", [
    { id: "data", rotulo: "Data", valor: (m) => m.data, data: true, html: (m) => finData(m.data) },
    { id: "descricao", rotulo: "No extrato", valor: (m) => m.descricao, html: (m) => esc(m.descricao || "") },
    { id: "valor", rotulo: "Valor", valor: (m) => m.valor, num: true, html: (m) => `<span class="${m.valor < 0 ? "fin-negativo" : "fin-receita"}">${finBRL(m.valor)}</span>` },
    { id: "conta", rotulo: "Conta", valor: (m) => m.conta, html: (m) => esc(m.conta) },
    { id: "lanc", rotulo: "Lançamento", valor: (m) => m.lancamento || (m.ignorado ? "ignorado" : ""),
      html: (m) => (m.parcela_id ? `<a href="#" data-lanc="${m.lancamento_id}">✔ ${esc(m.lancamento || "ver")}</a>`
        : m.ignorado ? `<span class="info">ignorado</span> <button type="button" class="secundario" data-desig="${m.id}">desfazer</button>`
          : `<button type="button" data-ligar="${m.id}">ligar</button> <button type="button" class="secundario" data-lancar="${m.id}">lançar</button> <button type="button" class="secundario" data-ignorar="${m.id}">ignorar</button>`) },
  ], movs, { padrao: [{ col: "data", dir: -1 }], limite: 300, vazio: dados.movimentos.length ? "Tudo do extrato já está lançado 👍" : "Nenhum extrato enviado ainda.",
    aoMontar: (box) => {
      box.querySelectorAll("[data-lanc]").forEach((a) => { a.onclick = (e) => { e.preventDefault(); finAbrirLancamento(Number(a.dataset.lanc)); }; });
      box.querySelectorAll("[data-ignorar]").forEach((b) => { b.onclick = () => finOcupado(b, "…", async () => { await api.put(`/api/fin/extrato/${b.dataset.ignorar}`, { ignorado: true }); finRender(); }); });
      box.querySelectorAll("[data-desig]").forEach((b) => { b.onclick = () => finOcupado(b, "…", async () => { await api.put(`/api/fin/extrato/${b.dataset.desig}`, { ignorado: false }); finRender(); }); });
      box.querySelectorAll("[data-ligar]").forEach((b) => { b.onclick = () => finLigarMovimento(dados.movimentos.find((m) => m.id === Number(b.dataset.ligar))); });
      box.querySelectorAll("[data-lancar]").forEach((b) => { b.onclick = () => finLancarMovimento(dados.movimentos.find((m) => m.id === Number(b.dataset.lancar))); });
    } });
}

async function finLigarMovimento(m) {
  const cands = await api.get(`/api/fin/extrato/${m.id}/candidatas`);
  finModal(`<h3>Ligar ${finBRL(m.valor)} de ${finData(m.data)}</h3><div class="info">${esc(m.descricao || "")}</div>
    <div id="fl-cands"></div>`, (corpo) => {
    finTabela(corpo.querySelector("#fl-cands"), "candidatas", [
      { id: "venc", rotulo: "Vencimento", valor: (p) => p.vencimento, data: true, html: (p) => finData(p.vencimento) },
      { id: "fornecedor", rotulo: "Fornecedor", valor: (p) => p.fornecedor, html: (p) => esc(p.fornecedor || "—") },
      { id: "descricao", rotulo: "Descrição", valor: (p) => p.descricao, html: (p) => esc(p.descricao || "") },
      { id: "valor", rotulo: "Valor", valor: (p) => p.valor, num: true, html: (p) => finBRL(p.valor) },
      { id: "conta", rotulo: "Conta", valor: (p) => p.conta, html: (p) => esc(p.conta || "—") },
    ], cands, { aoClicar: (p) => finOcupado(null, "", async () => {
      await api.put(`/api/fin/extrato/${m.id}`, { parcela_id: p.parcela_id });
      finMsg("✔ Ligado");
      finFecharTudo();
      finRender();
    }), vazio: "Nenhum lançamento com valor e data parecidos. Use 'lançar' pra criar um." });
  });
}

function finLancarMovimento(m) {
  const l = { tipo: m.valor < 0 ? "despesa" : "receita", data: m.data, valor_total: Math.abs(m.valor), descricao: m.descricao,
    conta: m.conta, parcelas: [{ vencimento: m.data, valor: Math.abs(m.valor), pago: true }] };
  finModal(finHtmlFormulario(l), (corpo) => finLigarFormulario(corpo, l, async (salvo) => {
    if (salvo && salvo.parcelas[0]) await api.put(`/api/fin/extrato/${m.id}`, { parcela_id: salvo.parcelas[0].id });
    finFecharTudo();
    finRender();
  }));
}

// ----------------------------------------------------------------- Cadastros
async function finTelaCadastros(alvo) {
  alvo.innerHTML = `<div class="modo-toggle" id="fc-modos">
      <button data-c="cpf">CPF/CNPJ (notas)</button><button data-c="plano">Plano de contas</button>
      <button data-c="fornecedores">Fornecedores</button><button data-c="contas">Contas e fazendas</button>
      <button data-c="importar">Importar CONSIPA</button></div><div id="fc-corpo"></div>`;
  alvo.querySelectorAll("#fc-modos button").forEach((b) => {
    b.classList.toggle("ativa", b.dataset.c === finCadModo.aba);
    b.onclick = () => { finCadModo.aba = b.dataset.c; finTelaCadastros(alvo); };
  });
  const corpo = alvo.querySelector("#fc-corpo");
  await ({ cpf: finCadCpf, plano: finCadPlano, fornecedores: finCadFornecedores, contas: finCadContas, importar: finCadImportar })[finCadModo.aba](corpo);
}

async function finCadCpf(box) {
  const lista = finNotas.contribuintes = await api.get("/api/fin/contribuintes");
  box.innerHTML = `
    <div class="fin-explica">
      <b>Como funciona:</b> digite o CPF (produtor rural) ou CNPJ de quem recebe as notas. O app pergunta pra SEFAZ todas as NF-e emitidas
      contra ele e elas aparecem em <b>Notas</b> já com fornecedor, produtos, valor e vencimentos.<br>
      <b>Precisa do certificado digital A1</b> (arquivo <code>.pfx</code> e senha) <b>do próprio CPF/CNPJ</b> — é exigência da Receita;
      sem ele a SEFAZ não entrega as notas. O e-CPF A1 custa em torno de R$ 150–250/ano em qualquer certificadora.
      O certificado fica guardado criptografado no servidor e só é usado pra essa consulta.<br>
      <b>Limites:</b> só NF-e (modelo 55) dos últimos ~90 dias; cupom de posto/mercado (NFC-e) e nota de serviço não vêm por aqui.
      A SEFAZ deixa consultar 1 vez por hora.</div>
    <form id="fcc-novo" class="fin-grid fin-form">
      <div><label>CPF ou CNPJ</label><input id="fcc-doc" inputmode="numeric" placeholder="000.000.000-00" required></div>
      <div class="fin-largo"><label>Nome</label><input id="fcc-nome" placeholder="ex.: Luiz Zanetti Jr" required></div>
      <div><label>UF</label><input id="fcc-uf" value="PR" maxlength="2"></div>
      <div><label>Fazenda das notas</label><select id="fcc-faz">${finOpcoes(fin.cad.fazendas.map((f) => f.nome), "Água do Tigre")}</select></div>
      <div><label>&nbsp;</label><button type="submit" id="fcc-add">+ Cadastrar</button></div>
    </form>
    <div id="fcc-lista">${lista.length ? "" : `<div class="info">Nenhum CPF/CNPJ cadastrado.</div>`}</div>`;
  box.querySelector("#fcc-novo").onsubmit = (ev) => {
    ev.preventDefault();
    finOcupado(box.querySelector("#fcc-add"), "Salvando…", async () => {
      await api.post("/api/fin/contribuintes", { documento: box.querySelector("#fcc-doc").value, nome: box.querySelector("#fcc-nome").value,
        uf: box.querySelector("#fcc-uf").value, fazenda: box.querySelector("#fcc-faz").value || null });
      finMsg("✔ Cadastrado. Agora envie o certificado digital.");
      finCadCpf(box);
    });
  };
  box.querySelector("#fcc-lista").innerHTML += lista.map((c) => {
    const venc = c.cert_validade ? new Date(c.cert_validade) : null;
    const diasVenc = venc ? Math.round((venc - new Date()) / 86400000) : null;
    return `<div class="fin-contrib ${c.ativo ? "" : "inativo"}" data-id="${c.id}">
      <div class="fin-contrib-topo"><div><b>${esc(c.nome)}</b> · ${finFmtDoc(c.documento)} · ${esc(c.uf)}${c.fazenda ? ` · ${esc(c.fazenda)}` : ""}${c.ativo ? "" : " · <i>inativo</i>"}</div>
        <label class="check"><input type="checkbox" data-ativo ${c.ativo ? "checked" : ""}> ativo</label></div>
      <div>${c.tem_certificado
        ? `🔐 Certificado de <b>${esc(c.cert_titular || "")}</b>, válido até ${finData(c.cert_validade)}${diasVenc != null && diasVenc < 30 ? ` <span class="fin-pill vermelho">vence em ${diasVenc} dias</span>` : ""}`
        : `<span class="fin-sem-cat">Sem certificado digital — não dá pra buscar as notas ainda</span>`}</div>
      <div class="info">Última busca: ${c.ultima_consulta ? finDataHora(c.ultima_consulta) : "nunca"}${c.ultimo_retorno ? ` · ${esc(c.ultimo_retorno)}` : ""}${c.pode_consultar_apos && new Date(c.pode_consultar_apos) > new Date() ? ` · próxima liberada às ${finLocal(c.pode_consultar_apos).hora}` : ""}</div>
      <div class="fin-acoes">
        <label class="fin-botao-arquivo secundario">${c.tem_certificado ? "Trocar certificado" : "Enviar certificado (.pfx)"}<input type="file" accept=".pfx,.p12" data-cert hidden></label>
        <input type="password" data-senha placeholder="senha do certificado" autocomplete="new-password">
        ${c.tem_certificado ? `<button type="button" data-buscar>🔄 Buscar notas agora</button><button type="button" class="secundario" data-tirar>Remover certificado</button>` : ""}
      </div></div>`;
  }).join("");
  box.querySelectorAll(".fin-contrib").forEach((el) => {
    const id = el.dataset.id;
    el.querySelector("[data-ativo]").onchange = (e) => finOcupado(null, "", async () => { await api.put(`/api/fin/contribuintes/${id}`, { ativo: e.target.checked }); finCadCpf(box); });
    el.querySelector("[data-cert]").onchange = async (e) => {
      const arq = e.target.files[0];
      const senha = el.querySelector("[data-senha]").value;
      if (!arq) return;
      if (!senha) { finMsg("Digite a senha do certificado antes de escolher o arquivo", true); e.target.value = ""; el.querySelector("[data-senha]").focus(); return; }
      const fd = new FormData();
      fd.append("arquivo", arq);
      fd.append("senha", senha);
      try {
        const r = await finUpload(`/api/fin/contribuintes/${id}/certificado`, fd);
        finMsg(`🔐 Certificado de ${r.titular} guardado (válido até ${finData(r.validade)})`);
        finCadCpf(box);
      } catch (err) {
        finMsg("⚠ " + err.message, true);
        e.target.value = "";
      }
    };
    const b = el.querySelector("[data-buscar]");
    if (b) {
      b.onclick = () => finOcupado(b, "Buscando…", async () => {
        const r = await api.post(`/api/fin/contribuintes/${id}/buscar`, {});
        finMsg(r.ok ? `✔ ${r.novas} nota(s) nova(s) — veja em Notas` : r.mensagem, !r.ok);
        finCadCpf(box);
      });
    }
    const t = el.querySelector("[data-tirar]");
    if (t) {
      t.onclick = () => {
        if (!window.confirm("Remover o certificado deste CPF/CNPJ? A busca automática para até enviar de novo.")) return;
        finOcupado(t, "…", async () => { await api.delete(`/api/fin/contribuintes/${id}/certificado`); finCadCpf(box); });
      };
    }
  });
}

async function finCadPlano(box) {
  const cad = await finCarregarCadastros(true);
  const lancs = await finCarregarLancamentos();
  const uso = {};
  lancs.forEach((l) => { const k = [l.tipo, l.setor, l.grupo, l.categoria].join("|"); uso[k] = (uso[k] || 0) + 1; });
  box.innerHTML = `<div class="fin-form-topo"><input id="fcp-busca" placeholder="Buscar categoria, grupo ou setor"><label class="check"><input type="checkbox" id="fcp-inativos"> mostrar inativas</label>
    <button type="button" id="fcp-nova">+ Categoria</button></div>
    <div class="info">Tocar numa linha edita. Renomear atualiza os lançamentos que já usam o nome. Inativar tira dos seletores, mas mantém o histórico.</div>
    <div id="fcp-tabela"></div>`;
  const desenhar = () => {
    const termo = box.querySelector("#fcp-busca").value.toLowerCase();
    const inat = box.querySelector("#fcp-inativos").checked;
    const lista = cad.plano.filter((p) => (inat || p.ativo) && (!termo || [p.setor, p.grupo, p.categoria].join(" ").toLowerCase().includes(termo)));
    finTabela(box.querySelector("#fcp-tabela"), "plano", [
      { id: "tipo", rotulo: "Tipo", valor: (p) => p.tipo, html: (p) => esc(p.tipo) },
      { id: "setor", rotulo: "Setor", valor: (p) => p.setor, html: (p) => esc(p.setor) },
      { id: "grupo", rotulo: "Grupo", valor: (p) => `${p.codigo || ""} ${p.grupo}`, html: (p) => esc(p.grupo) },
      { id: "categoria", rotulo: "Categoria", valor: (p) => p.categoria, html: (p) => `<b>${esc(p.categoria)}</b> <span class="info">${esc(p.codigo || "")}</span>` },
      { id: "uso", rotulo: "Lançamentos", valor: (p) => uso[[p.tipo, p.setor, p.grupo, p.categoria].join("|")] || 0, num: true,
        html: (p) => { const n = uso[[p.tipo, p.setor, p.grupo, p.categoria].join("|")] || 0; return n <= 2 ? `<span class="fin-pill">${n}</span>` : String(n); } },
      { id: "ativo", rotulo: "Situação", valor: (p) => (p.ativo ? "ativa" : "inativa"), html: (p) => (p.ativo ? "ativa" : `<span class="info">inativa</span>`) },
    ], lista, { padrao: [{ col: "tipo", dir: 1 }, { col: "setor", dir: 1 }, { col: "grupo", dir: 1 }], aoClicar: (p) => finEditarPlano(p, () => finCadPlano(box)) });
  };
  box.querySelector("#fcp-busca").oninput = desenhar;
  box.querySelector("#fcp-inativos").onchange = desenhar;
  box.querySelector("#fcp-nova").onclick = () => finEditarPlano({ tipo: "despesa", ativo: true }, () => finCadPlano(box));
  desenhar();
}

function finEditarPlano(p, depois) {
  finModal(`<form id="fep-form" class="fin-form"><div class="fin-form-topo"><h3>${p.id ? "Editar categoria" : "Nova categoria"}</h3><button type="submit" id="fep-salvar">Salvar</button></div>
    <div class="fin-grid">
      <div><label>Tipo</label><select id="fep-tipo"><option value="despesa">Despesa</option><option value="receita" ${p.tipo === "receita" ? "selected" : ""}>Receita</option></select></div>
      <div><label>Setor</label><input id="fep-setor" list="fep-dl-setor" value="${esc(p.setor || "")}" required></div>
      <div><label>Grupo</label><input id="fep-grupo" list="fep-dl-grupo" value="${esc(p.grupo || "")}" required></div>
      <div><label>Categoria</label><input id="fep-cat" value="${esc(p.categoria || "")}" required></div>
      <div><label>Código (opcional)</label><input id="fep-cod" value="${esc(p.codigo || "")}"></div>
    </div>
    <datalist id="fep-dl-setor">${[...new Set(fin.cad.plano.map((x) => x.setor))].map((s) => `<option value="${esc(s)}">`).join("")}</datalist>
    <datalist id="fep-dl-grupo">${[...new Set(fin.cad.plano.map((x) => x.grupo))].map((s) => `<option value="${esc(s)}">`).join("")}</datalist>
    ${p.id ? `<label class="check"><input type="checkbox" id="fep-ativo" ${p.ativo ? "checked" : ""}> ativa</label>` : ""}</form>`, (corpo) => {
    corpo.querySelector("#fep-form").onsubmit = (ev) => {
      ev.preventDefault();
      const q = (s) => corpo.querySelector(s).value.trim();
      const dados = { tipo: q("#fep-tipo"), setor: q("#fep-setor"), grupo: q("#fep-grupo"), categoria: q("#fep-cat"), codigo: q("#fep-cod") || null };
      if (p.id) dados.ativo = corpo.querySelector("#fep-ativo").checked;
      finOcupado(corpo.querySelector("#fep-salvar"), "Salvando…", async () => {
        if (p.id) await api.put(`/api/fin/plano/${p.id}`, dados); else await api.post("/api/fin/plano", dados);
        finInvalidar();
        await finCarregarCadastros(true);
        finMsg("✔ Plano de contas salvo");
        finFecharTudo();
        depois();
      });
    };
  });
}

async function finCadFornecedores(box) {
  const cad = await finCarregarCadastros(true);
  const marcados = new Set();
  box.innerHTML = `<div class="fin-form-topo"><input id="fcf-busca" placeholder="Buscar por nome, apelido ou CNPJ/CPF">
      <label class="check"><input type="checkbox" id="fcf-inativos"> mostrar inativos</label>
      <button type="button" id="fcf-juntar" class="secundario" disabled>Juntar marcados</button><button type="button" id="fcf-novo">+ Fornecedor</button></div>
    <div class="info">Marque dois ou mais nomes que são o mesmo fornecedor (ex.: "Frísia" e "Frisia") e toque em Juntar: os lançamentos passam pra um só e o outro nome vira apelido.</div>
    <div id="fcf-tabela"></div>`;
  const desenhar = () => {
    const termo = box.querySelector("#fcf-busca").value.toLowerCase().replace(/\D/g, "") || box.querySelector("#fcf-busca").value.toLowerCase();
    const inat = box.querySelector("#fcf-inativos").checked;
    const t = box.querySelector("#fcf-busca").value.toLowerCase();
    const lista = cad.fornecedores.filter((f) => (inat || f.ativo) && (!t || [f.nome, f.apelidos, f.documento].join(" ").toLowerCase().includes(t) || (termo && (f.documento || "").includes(termo))));
    finTabela(box.querySelector("#fcf-tabela"), "fornecedores", [
      { id: "marca", rotulo: "", valor: () => 0, html: (f) => `<input type="checkbox" data-marca="${f.id}" ${marcados.has(f.id) ? "checked" : ""}>` },
      { id: "nome", rotulo: "Fornecedor", valor: (f) => f.nome, html: (f) => `<b>${esc(f.nome)}</b>${f.apelidos ? ` <span class="info">também: ${esc(f.apelidos.replace(/;/g, ", "))}</span>` : ""}` },
      { id: "doc", rotulo: "CNPJ/CPF", valor: (f) => f.documento, html: (f) => finFmtDoc(f.documento) },
      { id: "padrao", rotulo: "Classificação que usa", valor: (f) => f.padrao.categoria, html: (f) => (f.padrao.categoria ? finCaminho(f.padrao) : `<span class="info">—</span>`) },
      { id: "n", rotulo: "Lançamentos", valor: (f) => f.lancamentos, num: true, html: (f) => String(f.lancamentos) },
    ], lista, { padrao: [{ col: "nome", dir: 1 }], limite: 300, aoClicar: (f) => finEditarFornecedor(f, () => finCadFornecedores(box)),
      aoMontar: (alvo) => alvo.querySelectorAll("[data-marca]").forEach((c) => {
        c.onchange = () => {
          if (c.checked) marcados.add(Number(c.dataset.marca)); else marcados.delete(Number(c.dataset.marca));
          box.querySelector("#fcf-juntar").disabled = marcados.size < 2;
        };
      }) });
  };
  box.querySelector("#fcf-busca").oninput = desenhar;
  box.querySelector("#fcf-inativos").onchange = desenhar;
  box.querySelector("#fcf-novo").onclick = () => finEditarFornecedor({ ativo: true }, () => finCadFornecedores(box));
  box.querySelector("#fcf-juntar").onclick = () => {
    const lista = cad.fornecedores.filter((f) => marcados.has(f.id));
    finModal(`<h3>Juntar ${lista.length} fornecedores</h3><div class="info">Qual nome fica? Os outros viram apelido.</div>
      ${lista.map((f) => `<label class="check"><input type="radio" name="fj" value="${f.id}" ${f === lista[0] ? "checked" : ""}> <b>${esc(f.nome)}</b> ${finFmtDoc(f.documento)} · ${f.lancamentos} lançamentos</label>`).join("")}
      <button type="button" id="fj-ok" style="width:100%;margin-top:10px">Juntar</button>`, (corpo) => {
      corpo.querySelector("#fj-ok").onclick = (e) => finOcupado(e.target, "Juntando…", async () => {
        const manter = Number(corpo.querySelector("input[name=fj]:checked").value);
        await api.post(`/api/fin/fornecedores/${manter}/juntar`, { ids: lista.map((f) => f.id).filter((i) => i !== manter) });
        finInvalidar();
        finMsg("✔ Fornecedores juntados");
        finFecharTudo();
        finCadFornecedores(box);
      });
    });
  };
  desenhar();
}

function finEditarFornecedor(f, depois) {
  finModal(`<form id="fef-form" class="fin-form"><div class="fin-form-topo"><h3>${f.id ? "Editar fornecedor" : "Novo fornecedor"}</h3><button type="submit" id="fef-salvar">Salvar</button></div>
    <div class="fin-grid">
      <div class="fin-largo"><label>Nome</label><input id="fef-nome" value="${esc(f.nome || "")}" required></div>
      <div><label>CNPJ/CPF</label><input id="fef-doc" inputmode="numeric" value="${esc(f.documento || "")}"></div>
      <div class="fin-largo"><label>Outras grafias (separe com ;)</label><input id="fef-apel" value="${esc(f.apelidos || "")}"></div>
    </div>${f.id ? `<label class="check"><input type="checkbox" id="fef-ativo" ${f.ativo ? "checked" : ""}> ativo</label>` : ""}</form>`, (corpo) => {
    corpo.querySelector("#fef-form").onsubmit = (ev) => {
      ev.preventDefault();
      const dados = { nome: corpo.querySelector("#fef-nome").value, documento: corpo.querySelector("#fef-doc").value, apelidos: corpo.querySelector("#fef-apel").value };
      if (f.id) dados.ativo = corpo.querySelector("#fef-ativo").checked;
      finOcupado(corpo.querySelector("#fef-salvar"), "Salvando…", async () => {
        if (f.id) await api.put(`/api/fin/fornecedores/${f.id}`, dados); else await api.post("/api/fin/fornecedores", dados);
        await finCarregarCadastros(true);
        finMsg("✔ Fornecedor salvo");
        finFecharTudo();
        depois();
      });
    };
  });
}

async function finCadContas(box) {
  const cad = await finCarregarCadastros(true);
  const lista = (titulo, itens, url, comTipo) => `<div class="fin-secao"><h3>${titulo}</h3>
    ${itens.map((x) => `<div class="fin-item ${x.ativo ? "" : "inativo"}"><div><b>${esc(x.nome)}</b>${comTipo ? ` <span class="info">${esc(x.tipo)}</span>` : ""}${x.ativo ? "" : " <i>inativo</i>"}</div>
      <div class="fin-item-acoes"><button type="button" class="secundario" data-ren="${url}/${x.id}" data-nome="${esc(x.nome)}">renomear</button>
      <button type="button" class="secundario" data-ativ="${url}/${x.id}" data-nome="${esc(x.nome)}" data-v="${x.ativo ? "0" : "1"}">${x.ativo ? "inativar" : "reativar"}</button></div></div>`).join("")}
    <form class="fin-item" data-novo="${url}"><input placeholder="Nova ${titulo === "Fazendas" ? "fazenda" : "conta"}" required>
      ${comTipo ? `<select><option value="banco">banco</option><option value="cartao">cartão</option><option value="outro">outro</option></select>` : ""}<button type="submit">+</button></form></div>`;
  box.innerHTML = lista("Contas (bancos e cartões)", cad.contas, "/api/fin/contas", true) + lista("Fazendas", cad.fazendas, "/api/fin/fazendas", false);
  box.querySelectorAll("[data-ren]").forEach((b) => {
    b.onclick = () => {
      const nome = (window.prompt("Novo nome:", b.dataset.nome) || "").trim();
      if (!nome) return;
      finOcupado(b, "…", async () => { await api.put(b.dataset.ren, { nome }); finCadContas(box); });
    };
  });
  box.querySelectorAll("[data-ativ]").forEach((b) => {
    b.onclick = () => finOcupado(b, "…", async () => { await api.put(b.dataset.ativ, { nome: b.dataset.nome, ativo: b.dataset.v === "1" }); finCadContas(box); });
  });
  box.querySelectorAll("[data-novo]").forEach((f) => {
    f.onsubmit = (ev) => {
      ev.preventDefault();
      const sel = f.querySelector("select");
      finOcupado(f.querySelector("button"), "…", async () => {
        await api.post(f.dataset.novo, { nome: f.querySelector("input").value, tipo: sel ? sel.value : undefined });
        finCadContas(box);
      });
    };
  });
}

async function finCadImportar(box) {
  box.innerHTML = `<div class="fin-explica">Envie a planilha <b>CONSIPA</b> (.xlsm). O app lê a aba CentralReal e junta as parcelas de cada compra num lançamento só.
    Aplica as decisões combinadas: "Pecuária de leite" vira <b>fazenda Castro</b>; Agricultura vai pra Sede; lançamentos sem categoria e os 3 que estavam no
    grupo errado vão pra aba <b>Revisar</b> em vermelho. Pode enviar de novo depois (planilha atualizada): o que já foi importado é pulado, nada é apagado.</div>
    <div class="fin-explica"><b>Anos anteriores:</b> se houver uma planilha mais antiga (ex.: a da Letícia, de 2024 pra trás),
      escolha também. Dela entra só o que é <b>antes</b> de a CONSIPA assumir (o primeiro mês que a CONSIPA tem completo) e o que
      não está repetido. Valor quebrado (#REF!) é recalculado pela fórmula da CONSIPA.</div>
    <label>1. Planilha CONSIPA (atual) <input type="file" id="fci-arq" accept=".xlsm,.xlsx"></label>
    <label>2. Planilha antiga (opcional) <input type="file" id="fci-antiga" accept=".xlsm,.xlsx"></label>
    <button type="button" id="fci-ok" class="fin-botao-arquivo">📥 Importar</button>
    <div id="fci-res" class="fin-secao"></div>`;
  box.querySelector("#fci-ok").onclick = async (e) => {
    const arq = box.querySelector("#fci-arq").files[0];
    const antiga = box.querySelector("#fci-antiga").files[0];
    if (!arq) { alert("Escolha a planilha CONSIPA."); return; }
    const res = box.querySelector("#fci-res");
    res.innerHTML = `<div class="info">⏳ Importando ${esc(arq.name)}${antiga ? " + " + esc(antiga.name) : ""} (pode levar alguns minutos)…</div>`;
    const fd = new FormData();
    fd.append("arquivo", arq);
    if (antiga) fd.append("antiga", antiga);
    try {
      const r = await finUpload("/api/fin/importar-consipa", fd);
      finInvalidar();
      await finCarregarCadastros(true);
      res.innerHTML = `<div class="destaque">✔ <b>${r.lancamentos}</b> lançamentos importados (${r.parcelas} parcelas).<br>
        ${r.ja_existiam ? `${r.ja_existiam} já existiam e foram pulados.<br>` : ""}
        <b class="fin-sem-cat">${r.a_revisar} a revisar</b> — veja na aba Revisar.<br>
        <span class="info">${r.linhas_ignoradas} linhas de inventário/configuração não entram (não são despesa nem receita).</span>
        ${r.planilha_antiga ? `<br><span class="info">Planilha antiga: ${r.planilha_antiga.antiga_incluidas} lançamentos de antes de
          ${fmt.data(r.planilha_antiga.corte)} incluídos; ${r.planilha_antiga.antiga_repetidas} repetidos ficaram de fora.</span>` : ""}</div>`;
    } catch (err) {
      res.innerHTML = `<div class="fin-alerta">⚠ ${esc(err.message)}</div>`;
    }
  };
}

Object.assign(FIN_TELAS, { notas: finTelaNotas, extrato: finTelaExtrato, cadastros: finTelaCadastros });
