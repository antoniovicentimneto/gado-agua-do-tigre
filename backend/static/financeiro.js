// Aba Financeiro (só dono): lançar despesas/receitas, resultado por mês com clique nos
// lançamentos, conferência, recorrentes. Notas fiscais, cadastros e extrato ficam em
// financeiro-notas.js. Substitui a planilha CONSIPA.
//
// Os dados vêm em poucas chamadas (/api/fin/cadastros e /api/fin/lancamentos) e os
// filtros rodam no aparelho — o banco fica em SP e o servidor nos EUA.

const fin = {
  modo: "lancar",
  cad: null,            // { fazendas, contas, plano, fornecedores }
  lancs: null,          // lista completa de lançamentos (cache)
  ultimoSalvo: null,    // pro "repetir último"
  pilhaModal: [],       // fechar o modal volta pra tela anterior (padrão do Antonio)
  aberto: new Set(["despesa", "receita"]), // nós abertos da árvore do Resultado
  filtrosResultado: null,
  filtrosLanc: { busca: "", tipo: "", fazenda: "", setor: "", categoria: "", por: "", origem: "",
    de: "", ate: "", revisar: false, excluidos: false },
  ordem: {},            // ordem por tabela: id -> [{col, dir}]
};

const FIN_MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
const finBRL = (v) => (v == null ? "—" : Number(v).toLocaleString("pt-BR", { style: "currency", currency: "BRL" }));
const finData = (s) => (s ? s.slice(0, 10).split("-").reverse().join("/") : "—");
const finMes = (m) => `${FIN_MESES[Number(m.slice(5, 7)) - 1]}/${m.slice(2, 4)}`;
// Data/hora gravada pelo servidor vem em UTC (termina em Z): mostra na hora do aparelho.
const finLocal = (s) => {
  const d = new Date(s);
  const p = (n) => String(n).padStart(2, "0");
  return { data: `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`, hora: `${p(d.getHours())}:${p(d.getMinutes())}` };
};
const finDataHora = (s) => (s ? `${finData(finLocal(s).data)} ${finLocal(s).hora}` : "—");
const finDiaLocal = (s) => (s ? finLocal(s).data : "");

function finMsg(texto, erro = false) {
  let el = document.getElementById("fin-toast");
  if (!el) {
    el = document.createElement("div");
    el.id = "fin-toast";
    el.className = "fin-toast";
    document.body.appendChild(el);
  }
  el.textContent = texto;
  el.classList.toggle("erro", erro);
  el.classList.add("visivel");
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.remove("visivel"), erro ? 6000 : 3000);
}

// Botão fica cinza com "salvando..." até a resposta (ninguém fica sem saber se travou).
async function finOcupado(botao, texto, funcao) {
  const original = botao ? botao.textContent : "";
  if (botao) { botao.disabled = true; botao.textContent = texto; }
  try {
    return await funcao();
  } catch (e) {
    finMsg("⚠ " + e.message, true);
    return undefined;
  } finally {
    if (botao) { botao.disabled = false; botao.textContent = original; }
  }
}

async function finUpload(url, formData) {
  const r = await fetch(url, { method: "POST", headers: cabecalhos(), body: formData });
  return _resposta(r);
}

// ----------------------------------------------------------------- modal com "voltar"
function finModal(html, aoMontar) {
  const corpo = document.getElementById("fin-modal-corpo");
  if (!document.getElementById("fin-modal").classList.contains("escondido") && corpo.dataset.tela) {
    fin.pilhaModal.push({ html: corpo.innerHTML, montar: corpo._montar, scroll: corpo.parentElement.scrollTop });
  }
  corpo.innerHTML = html;
  corpo.dataset.tela = "1";
  corpo._montar = aoMontar;
  document.getElementById("fin-modal").classList.remove("escondido");
  corpo.parentElement.scrollTop = 0;
  if (aoMontar) aoMontar(corpo);
}

function finFecharModal() {
  const corpo = document.getElementById("fin-modal-corpo");
  const anterior = fin.pilhaModal.pop();
  if (anterior) {
    corpo.innerHTML = anterior.html;
    corpo._montar = anterior.montar;
    if (anterior.montar) anterior.montar(corpo, true);
    corpo.parentElement.scrollTop = anterior.scroll;
    return;
  }
  corpo.dataset.tela = "";
  document.getElementById("fin-modal").classList.add("escondido");
}

function finFecharTudo() {
  fin.pilhaModal = [];
  finFecharModal();
}

// ----------------------------------------------------------------- tabela ordenável
// colunas: [{id, rotulo, valor(l), html(l), num:true, classe}] · ordem em cascata
// (clicar em outra coluna mantém a anterior como 2º critério, mostrado com ↑¹ ↑²).
function finCompara(a, b, num) {
  const va = a == null || a === "" ? null : a;
  const vb = b == null || b === "" ? null : b;
  if (va === null && vb === null) return 0;
  if (va === null) return 1;
  if (vb === null) return -1;
  if (num) return va - vb;
  return String(va).localeCompare(String(vb), "pt-BR", { numeric: true, sensitivity: "base" });
}

function finOrdenar(id, colunas, linhas, padrao) {
  const ordem = fin.ordem[id] || padrao || [];
  const out = linhas.slice();
  out.sort((a, b) => {
    for (const o of ordem) {
      const col = colunas.find((c) => c.id === o.col);
      if (!col) continue;
      const r = finCompara(col.valor(a), col.valor(b), col.num) * o.dir;
      if (r) return r;
    }
    return 0;
  });
  return out;
}

function finTabela(alvo, id, colunas, linhas, opcoes = {}) {
  const ordem = fin.ordem[id] || opcoes.padrao || [];
  const ordenadas = finOrdenar(id, colunas, linhas, opcoes.padrao);
  const seta = (c) => {
    const i = ordem.findIndex((o) => o.col === c.id);
    if (i < 0) return "";
    return `<span class="fin-seta">${ordem[i].dir > 0 ? "▲" : "▼"}${ordem.length > 1 ? "¹²³"[i] || "" : ""}</span>`;
  };
  const limite = opcoes.limite || ordenadas.length;
  const visiveis = ordenadas.slice(0, limite);
  alvo.innerHTML = `
    <div class="fin-tabela"><table>
      <thead><tr>${colunas.map((c) => `<th data-col="${c.id}" class="${c.num ? "num" : ""}">${c.rotulo}${seta(c)}</th>`).join("")}</tr></thead>
      <tbody>${visiveis.map((l, i) => `<tr data-i="${i}" class="${opcoes.classeLinha ? opcoes.classeLinha(l) : ""}">${
        colunas.map((c) => `<td class="${c.num ? "num" : ""} ${c.classe || ""}">${c.html ? c.html(l) : esc(c.valor(l) ?? "")}</td>`).join("")}</tr>`).join("")}
      </tbody>
      ${opcoes.rodape ? `<tfoot>${opcoes.rodape}</tfoot>` : ""}
    </table></div>
    ${ordenadas.length > limite ? `<button type="button" class="secundario fin-mais">Mostrar todos (${ordenadas.length})</button>` : ""}
    ${!ordenadas.length ? `<div class="info">${opcoes.vazio || "Nada aqui."}</div>` : ""}`;
  alvo.querySelectorAll("th[data-col]").forEach((th) => {
    th.onclick = () => {
      const col = colunas.find((c) => c.id === th.dataset.col);
      let atual = (fin.ordem[id] || opcoes.padrao || []).slice();
      if (atual[0] && atual[0].col === col.id) {
        atual[0] = { col: col.id, dir: -atual[0].dir };
      } else {
        // texto começa A→Z; número/data começa do maior/mais recente
        atual = [{ col: col.id, dir: col.num || col.data ? -1 : 1 }, ...atual.filter((o) => o.col !== col.id)].slice(0, 3);
      }
      fin.ordem[id] = atual;
      finTabela(alvo, id, colunas, linhas, opcoes);
    };
  });
  const mais = alvo.querySelector(".fin-mais");
  if (mais) mais.onclick = () => finTabela(alvo, id, colunas, linhas, { ...opcoes, limite: ordenadas.length });
  if (opcoes.aoClicar) {
    alvo.querySelectorAll("tbody tr").forEach((tr) => {
      tr.onclick = (ev) => {
        if (ev.target.closest("button, input, select, a")) return;
        opcoes.aoClicar(visiveis[Number(tr.dataset.i)], tr);
      };
    });
  }
  if (opcoes.aoMontar) opcoes.aoMontar(alvo, visiveis);
}

// ----------------------------------------------------------------- dados
async function finCarregarCadastros(forcar = false) {
  if (!fin.cad || forcar) fin.cad = await api.get("/api/fin/cadastros");
  return fin.cad;
}

async function finCarregarLancamentos(forcar = false) {
  if (!fin.lancs || forcar) fin.lancs = await api.get("/api/fin/lancamentos");
  return fin.lancs;
}

function finInvalidar() {
  fin.lancs = null;
}

const finAtivos = (lista) => lista.filter((x) => x.ativo !== false);

function finOpcoes(lista, valor, vazio = "—") {
  const itens = [...new Set(lista.filter((x) => x != null && x !== ""))];
  if (valor && !itens.includes(valor)) itens.unshift(valor);
  return `<option value="">${vazio}</option>` +
    itens.map((x) => `<option ${x === valor ? "selected" : ""}>${esc(x)}</option>`).join("");
}

function finCaminho(l) {
  if (!l.categoria) return `<span class="fin-sem-cat">sem categoria</span> <span class="info">${esc([l.setor, l.grupo].filter(Boolean).join(" › "))}</span>`;
  return `${esc(l.categoria)} <span class="info">${esc([l.setor, l.grupo].filter(Boolean).join(" › "))}</span>`;
}

// ----------------------------------------------------------------- classificação (selects dependentes)
// Setor › Grupo › Categoria vêm do plano de contas; "+ nova" cria na hora.
function finHtmlClasse(prefixo, v = {}) {
  const cad = fin.cad;
  return `
    <div class="fin-grid">
      <div><label>Fazenda</label><select id="${prefixo}-fazenda">${finOpcoes(finAtivos(cad.fazendas).map((f) => f.nome), v.fazenda || (prefixo === "fl" && !v.id ? "Água do Tigre" : v.fazenda))}</select></div>
      <div><label>Setor</label><select id="${prefixo}-setor"></select></div>
      <div><label>Grupo</label><select id="${prefixo}-grupo"></select></div>
      <div><label>Categoria</label><select id="${prefixo}-categoria"></select></div>
    </div>`;
}

function finLigarClasse(raiz, prefixo, tipoAtual, v = {}) {
  const $ = (s) => raiz.querySelector(`#${prefixo}-${s}`);
  const NOVO = "__novo__";
  const plano = () => fin.cad.plano.filter((p) => p.tipo === tipoAtual() && p.ativo !== false);
  const preencher = (sel, lista, valor) => {
    sel.innerHTML = finOpcoes(lista, valor) + `<option value="${NOVO}">+ nova…</option>`;
    sel.value = valor || "";
  };
  const setores = () => preencher($("setor"), plano().map((p) => p.setor).sort((a, b) => a.localeCompare(b, "pt-BR")), $("setor").value || v.setor);
  const grupos = (valor) => preencher($("grupo"), plano().filter((p) => p.setor === $("setor").value).map((p) => p.grupo), valor);
  const cats = (valor) => preencher($("categoria"), plano().filter((p) => p.setor === $("setor").value && p.grupo === $("grupo").value).map((p) => p.categoria), valor);
  const novo = (sel, rotulo, depois) => {
    if (sel.value !== NOVO) return depois();
    const nome = (window.prompt(`Nome do novo ${rotulo}:`) || "").trim();
    if (!nome) { sel.value = ""; return depois(); }
    sel.querySelector(`option[value="${NOVO}"]`).insertAdjacentHTML("beforebegin", `<option>${esc(nome)}</option>`);
    sel.value = nome;
    depois();
  };
  $("setor").onchange = () => novo($("setor"), "setor", () => { grupos(""); cats(""); });
  $("grupo").onchange = () => novo($("grupo"), "grupo", () => cats(""));
  $("categoria").onchange = () => novo($("categoria"), "categoria", () => {});
  const aplicar = (c) => {
    $("setor").innerHTML = "";
    preencher($("setor"), plano().map((p) => p.setor).sort((a, b) => a.localeCompare(b, "pt-BR")), c.setor);
    grupos(c.grupo);
    cats(c.categoria);
    if (c.fazenda && $("fazenda")) $("fazenda").value = c.fazenda;
  };
  aplicar(v);
  return {
    valores: () => ({
      fazenda: $("fazenda") ? $("fazenda").value || null : undefined,
      setor: $("setor").value === NOVO ? null : $("setor").value || null,
      grupo: $("grupo").value === NOVO ? null : $("grupo").value || null,
      categoria: $("categoria").value === NOVO ? null : $("categoria").value || null,
    }),
    aplicar,
    recarregar: () => aplicar({ setor: $("setor").value, grupo: $("grupo").value, categoria: $("categoria").value }),
    setores,
  };
}

// ----------------------------------------------------------------- formulário de lançamento
// Usado na sub-aba Lançar, na edição (modal) e pra lançar movimento do extrato.
function finHtmlFormulario(l, opcoes = {}) {
  const cad = fin.cad;
  const tipo = l.tipo || "despesa";
  const parcelas = l.parcelas && l.parcelas.length ? l.parcelas : null;
  return `
    <form id="fl-form" class="fin-form" autocomplete="off">
      <div class="fin-form-topo">
        <h3>${l.id ? `Lançamento #${l.id}` : "Novo lançamento"}</h3>
        <div class="fin-acoes">
          ${!l.id && fin.ultimoSalvo ? `<button type="button" id="fl-repetir" class="secundario">↻ Repetir último</button>` : ""}
          <button type="submit" id="fl-salvar">${l.id ? "Salvar modificações" : "Salvar lançamento"}</button>
        </div>
      </div>
      ${l.revisar ? `<div class="fin-alerta">⚠ A revisar: ${esc(l.revisar_motivo || "")}</div>` : ""}
      ${l.excluido ? `<div class="fin-alerta">Excluído: ${esc(l.excluido_motivo || "")}</div>` : ""}
      <div class="modo-toggle fin-tipo">
        <button type="button" data-tipo="despesa" class="${tipo === "despesa" ? "ativa" : ""}">Despesa</button>
        <button type="button" data-tipo="receita" class="${tipo === "receita" ? "ativa" : ""}">Receita</button>
      </div>
      <div class="fin-grid">
        <div class="fin-largo"><label>Fornecedor / cliente</label>
          <input id="fl-fornecedor" list="fl-dl-forn" value="${esc(l.fornecedor_nome || "")}" placeholder="Digite e escolha (ou um nome novo)">
          <datalist id="fl-dl-forn">${finAtivos(cad.fornecedores).map((f) => `<option value="${esc(f.nome)}">${f.documento ? esc(f.documento) : ""}</option>`).join("")}</datalist>
          <div id="fl-sugestao" class="info"></div></div>
        <div><label>Valor total (R$)</label><input id="fl-valor" inputmode="decimal" value="${l.valor_total != null ? String(l.valor_total).replace(".", ",") : ""}" placeholder="0,00" required></div>
        <div><label>Data da compra</label><input id="fl-data" type="date" value="${l.data || hojeLocal()}" required></div>
        <div class="fin-largo"><label>Descrição</label><input id="fl-descricao" value="${esc(l.descricao || "")}" placeholder="ex.: sal mineral, diesel, salário"></div>
      </div>
      ${finHtmlClasse("fl", l)}
      <div class="fin-grid">
        <div><label>Conta (banco/cartão)</label><select id="fl-conta">${finOpcoes(finAtivos(cad.contas).map((c) => c.nome), l.conta)}</select></div>
        <div><label>Forma de pagamento</label><select id="fl-forma">${finOpcoes(["Pix", "Boleto", "Cartão de crédito", "Cartão de débito", "Dinheiro", "Transferência", "Débito automático", "Cheque", "Outros"], l.forma_pagamento)}</select></div>
        <div><label>Nº da nota</label><input id="fl-nf" value="${esc(l.nf_numero || "")}"></div>
        <div><label>Parcelas</label><input id="fl-n" type="number" min="1" max="60" value="${parcelas ? parcelas.length : 1}"></div>
      </div>
      <label>Vencimentos</label>
      <div id="fl-parcelas" class="fin-parcelas"></div>
      <label>Observação</label><input id="fl-obs" value="${esc(l.observacao || "")}">
      ${l.id ? `<div class="info">Lançado por ${esc(l.criado_por || "—")} em ${finDataHora(l.criado_em)}${l.alterado_por ? ` · alterado por ${esc(l.alterado_por)} em ${finDataHora(l.alterado_em)}` : ""} · origem: ${esc(l.origem)}${l.nf_chave ? ` · chave ${esc(l.nf_chave)}` : ""}</div>` : ""}
      ${l.id && !opcoes.semExcluir ? `<div class="fin-perigo">
        ${l.excluido ? `<button type="button" id="fl-restaurar" class="secundario">Restaurar lançamento</button>`
          : `<input id="fl-motivo" placeholder="Motivo (ex.: lançado em dobro)"><button type="button" id="fl-excluir" class="perigo">Excluir</button>`}
      </div>` : ""}
    </form>`;
}

function finNum(txt) {
  const s = String(txt || "").trim().replace(/[R$\s]/g, "");
  if (!s) return 0;
  return Number(s.includes(",") ? s.replace(/\./g, "").replace(",", ".") : s) || 0;
}

function finSomarMeses(iso, n) {
  const [a, m, d] = iso.split("-").map(Number);
  const alvo = new Date(a, m - 1 + n, 1);
  const ultimo = new Date(alvo.getFullYear(), alvo.getMonth() + 1, 0).getDate();
  alvo.setDate(Math.min(d, ultimo));
  return `${alvo.getFullYear()}-${String(alvo.getMonth() + 1).padStart(2, "0")}-${String(alvo.getDate()).padStart(2, "0")}`;
}

// Liga o formulário. aoSalvar(lancamentoSalvo) é chamado depois de gravar.
function finLigarFormulario(raiz, l, aoSalvar) {
  const $ = (s) => raiz.querySelector(s);
  let tipo = l.tipo || "despesa";
  let parcelas = (l.parcelas || []).map((p) => ({ vencimento: p.vencimento, valor: p.valor, pago: p.pago }));
  let parcelasEditadas = !!l.id;
  const classe = finLigarClasse(raiz, "fl", () => tipo, l);

  raiz.querySelectorAll(".fin-tipo button").forEach((b) => {
    b.onclick = () => {
      tipo = b.dataset.tipo;
      raiz.querySelectorAll(".fin-tipo button").forEach((x) => x.classList.toggle("ativa", x === b));
      classe.aplicar({});
    };
  });

  const gerarParcelas = () => {
    const n = Math.max(1, Math.min(60, Number($("#fl-n").value) || 1));
    const total = finNum($("#fl-valor").value);
    const inicio = (parcelas[0] && parcelas[0].vencimento) || $("#fl-data").value || hojeLocal();
    const base = Math.round((total / n) * 100) / 100;
    parcelas = Array.from({ length: n }, (_, i) => ({ vencimento: finSomarMeses(inicio, i), valor: base }));
    if (n) parcelas[n - 1].valor = Math.round((total - base * (n - 1)) * 100) / 100;
    desenharParcelas();
  };
  const desenharParcelas = () => {
    const total = finNum($("#fl-valor").value);
    const soma = parcelas.reduce((s, p) => s + (Number(p.valor) || 0), 0);
    const difere = Math.abs(soma - total) > 0.05;
    $("#fl-parcelas").innerHTML = parcelas.map((p, i) => `
      <div class="fin-parcela">
        <span>${i + 1}ª</span>
        <input type="date" data-i="${i}" data-campo="vencimento" value="${p.vencimento}">
        <input inputmode="decimal" data-i="${i}" data-campo="valor" value="${String(p.valor).replace(".", ",")}">
        ${p.pago === false ? `<span class="fin-pill amarelo">a confirmar</span>` : ""}
      </div>`).join("") +
      (difere ? `<div class="fin-alerta">A soma das parcelas (${finBRL(soma)}) não bate com o total (${finBRL(total)}).
        <a href="#" id="fl-redividir">Dividir de novo</a></div>` : "");
    $("#fl-parcelas").querySelectorAll("input").forEach((inp) => {
      inp.onchange = () => {
        const p = parcelas[Number(inp.dataset.i)];
        if (inp.dataset.campo === "valor") p.valor = finNum(inp.value);
        else {
          p.vencimento = inp.value;
          // mudou o 1º vencimento: os outros acompanham (de mês em mês)
          if (Number(inp.dataset.i) === 0 && !parcelasEditadas) parcelas.forEach((x, i) => { if (i) x.vencimento = finSomarMeses(inp.value, i); });
        }
        parcelasEditadas = true;
        desenharParcelas();
      };
    });
    const red = $("#fl-redividir");
    if (red) red.onclick = (e) => { e.preventDefault(); gerarParcelas(); };
  };
  if (!parcelas.length) gerarParcelas(); else desenharParcelas();
  $("#fl-n").onchange = () => { parcelasEditadas = false; gerarParcelas(); };
  $("#fl-valor").onchange = () => { if (!parcelasEditadas || parcelas.length === 1) gerarParcelas(); else desenharParcelas(); };
  $("#fl-data").onchange = () => { if (!parcelasEditadas) { parcelas = []; gerarParcelas(); } };

  // Fornecedor conhecido: preenche a classificação que ele usou da última vez.
  $("#fl-fornecedor").onchange = () => {
    const nome = $("#fl-fornecedor").value.trim().toLowerCase();
    const f = fin.cad.fornecedores.find((x) => x.nome.toLowerCase() === nome ||
      (x.apelidos || "").toLowerCase().split(";").map((a) => a.trim()).includes(nome));
    const p = f && f.padrao;
    if (!p || !p.categoria) { $("#fl-sugestao").textContent = f ? "" : (nome ? "Fornecedor novo — será cadastrado." : ""); return; }
    const vazio = !classe.valores().categoria;
    if (vazio || l.id == null) {
      if (p.tipo && p.tipo !== tipo) raiz.querySelector(`.fin-tipo button[data-tipo="${p.tipo}"]`).click();
      classe.aplicar(p);
      if (p.conta) $("#fl-conta").value = p.conta;
      $("#fl-sugestao").innerHTML = `✨ Preenchido como da última vez: <b>${esc(p.categoria)}</b>`;
    }
  };

  const montarDados = () => ({
    tipo, data: $("#fl-data").value, ...classe.valores(),
    fornecedor_nome: $("#fl-fornecedor").value.trim() || null,
    descricao: $("#fl-descricao").value.trim(), valor_total: finNum($("#fl-valor").value),
    conta: $("#fl-conta").value || null, forma_pagamento: $("#fl-forma").value || null,
    nf_numero: $("#fl-nf").value.trim() || null, observacao: $("#fl-obs").value.trim() || null,
    parcelas: parcelas.map((p) => ({ vencimento: p.vencimento, valor: p.valor, pago: p.pago ?? null })),
    conferido: true,
  });

  $("#fl-form").onsubmit = async (ev) => {
    ev.preventDefault();
    const dados = montarDados();
    if (!dados.categoria && !window.confirm("Sem categoria: o lançamento vai pra fila 'Revisar'. Salvar assim mesmo?")) return;
    await finOcupado($("#fl-salvar"), "Salvando…", async () => {
      const salvo = l.id ? await api.put(`/api/fin/lancamentos/${l.id}`, dados) : await api.post("/api/fin/lancamentos", dados);
      finInvalidar();
      await finCarregarCadastros(true);
      if (!l.id) fin.ultimoSalvo = { ...dados, valor_total: null, parcelas: null, nf_numero: null, descricao: dados.descricao };
      finMsg(l.id ? "✔ Modificações salvas" : `✔ Lançado: ${finBRL(salvo.valor_total)}`);
      if (aoSalvar) aoSalvar(salvo);
    });
  };
  const rep = $("#fl-repetir");
  if (rep) {
    rep.onclick = () => {
      const u = fin.ultimoSalvo;
      $("#fl-fornecedor").value = u.fornecedor_nome || "";
      $("#fl-descricao").value = u.descricao || "";
      $("#fl-conta").value = u.conta || "";
      $("#fl-forma").value = u.forma_pagamento || "";
      if (u.tipo !== tipo) raiz.querySelector(`.fin-tipo button[data-tipo="${u.tipo}"]`).click();
      classe.aplicar(u);
      $("#fl-valor").focus();
    };
  }
  const exc = $("#fl-excluir");
  if (exc) {
    exc.onclick = async () => {
      const motivo = $("#fl-motivo").value.trim();
      if (!motivo) { finMsg("Escreva o motivo da exclusão", true); $("#fl-motivo").focus(); return; }
      await finOcupado(exc, "Excluindo…", async () => {
        await api.post(`/api/fin/lancamentos/${l.id}/excluir`, { motivo });
        finInvalidar();
        finMsg("Lançamento excluído (continua no histórico)");
        if (aoSalvar) aoSalvar(null);
      });
    };
  }
  const res = $("#fl-restaurar");
  if (res) {
    res.onclick = () => finOcupado(res, "Restaurando…", async () => {
      await api.post(`/api/fin/lancamentos/${l.id}/restaurar`, {});
      finInvalidar();
      finMsg("Lançamento restaurado");
      if (aoSalvar) aoSalvar(null);
    });
  }
}

// Abre um lançamento para editar (de qualquer lugar: resultado, lista, revisar...).
async function finAbrirLancamento(id, depois) {
  try {
    const l = await api.get(`/api/fin/lancamentos/${id}`);
    finModal(finHtmlFormulario(l), (corpo) => finLigarFormulario(corpo, l, () => {
      finFecharTudo();
      if (depois) return depois();
      finRender();
    }));
  } catch (e) {
    finMsg("⚠ " + e.message, true);
  }
}

// ----------------------------------------------------------------- sub-aba Lançar
async function finTelaLancar(alvo) {
  alvo.innerHTML = `<div id="fin-lancar-form"></div>
    <div class="fin-secao"><h3>Lançados hoje</h3><div id="fin-hoje"></div></div>`;
  const montar = () => {
    const box = alvo.querySelector("#fin-lancar-form");
    box.innerHTML = finHtmlFormulario({});
    finLigarFormulario(box, {}, () => { montar(); finMostrarHoje(); });
    box.querySelector("#fl-fornecedor").focus();
  };
  montar();
  finMostrarHoje();
}

async function finMostrarHoje() {
  const box = document.getElementById("fin-hoje");
  if (!box) return;
  const lancs = await finCarregarLancamentos();
  const hoje = hojeLocal();
  const meus = lancs.filter((l) => l.origem !== "consipa" && (finDiaLocal(l.criado_em) === hoje || finDiaLocal(l.alterado_em) === hoje));
  finTabela(box, "hoje", FIN_COLUNAS_LANC.filter((c) => ["data", "fornecedor", "descricao", "categoria", "valor", "por"].includes(c.id)),
    meus, { padrao: [{ col: "criado", dir: -1 }], aoClicar: (l) => finAbrirLancamento(l.id, () => finRender()),
      vazio: "Nada lançado hoje ainda. O que você salvar aparece aqui — assim dá pra conferir que gravou." });
}

// ----------------------------------------------------------------- sub-aba Lançamentos
const FIN_COLUNAS_LANC = [
  { id: "data", rotulo: "Data", valor: (l) => l.data, data: true, html: (l) => finData(l.data) },
  { id: "fornecedor", rotulo: "Fornecedor", valor: (l) => l.fornecedor_nome, html: (l) => esc(l.fornecedor_nome || "—") },
  { id: "descricao", rotulo: "Descrição", valor: (l) => l.descricao, html: (l) => esc(l.descricao || "") },
  { id: "categoria", rotulo: "Categoria", valor: (l) => l.categoria, html: (l) => finCaminho(l) },
  { id: "valor", rotulo: "Valor", valor: (l) => (l.tipo === "receita" ? 1 : -1) * l.valor_total, num: true,
    html: (l) => `<span class="${l.tipo === "receita" ? "fin-receita" : ""}">${finBRL(l.valor_total)}</span>` },
  { id: "parcelas", rotulo: "Parcelas", valor: (l) => l.parcelas.length, num: true,
    html: (l) => {
      const prox = l.parcelas.find((p) => !p.realizado);
      return `${l.parcelas.length}x${prox ? ` <span class="info">próx. ${finData(prox.vencimento)}</span>` : ""}`;
    } },
  { id: "fazenda", rotulo: "Fazenda", valor: (l) => l.fazenda, html: (l) => esc(l.fazenda || "—") },
  { id: "conta", rotulo: "Conta", valor: (l) => l.conta, html: (l) => esc(l.conta || "—") },
  { id: "nf", rotulo: "NF", valor: (l) => l.nf_numero, html: (l) => esc(l.nf_numero || "") },
  { id: "por", rotulo: "Lançado por", valor: (l) => l.criado_por, html: (l) => `${esc(l.criado_por || "—")} <span class="info">${finData(finDiaLocal(l.criado_em))}</span>` },
  { id: "criado", rotulo: "Lançado em", valor: (l) => l.criado_em, data: true, html: (l) => finDataHora(l.criado_em) },
  { id: "origem", rotulo: "Origem", valor: (l) => l.origem, html: (l) => esc(l.origem) },
];

async function finTelaLancamentos(alvo) {
  const f = fin.filtrosLanc;
  const lancs = f.excluidos ? await api.get("/api/fin/lancamentos?excluidos=true") : await finCarregarLancamentos();
  const cad = fin.cad;
  const uniq = (fn) => [...new Set(lancs.map(fn).filter(Boolean))].sort((a, b) => a.localeCompare(b, "pt-BR"));
  alvo.innerHTML = `
    <div class="fin-filtros ${fin.filtrosAbertos ? "" : "recolhido"}">
      <input id="ff-busca" class="fin-sempre" placeholder="Buscar fornecedor, descrição, nota, valor…" value="${esc(f.busca)}">
      <button type="button" class="secundario fin-sempre fin-so-celular" id="ff-mais">⚙ ${fin.filtrosAbertos ? "menos" : "mais"} filtros</button>
      <select id="ff-tipo">${finOpcoes(["despesa", "receita"], f.tipo, "Despesa e receita")}</select>
      <select id="ff-fazenda">${finOpcoes(cad.fazendas.map((x) => x.nome), f.fazenda, "Todas as fazendas")}</select>
      <select id="ff-setor">${finOpcoes(uniq((l) => l.setor), f.setor, "Todos os setores")}</select>
      <select id="ff-categoria">${finOpcoes(uniq((l) => l.categoria), f.categoria, "Todas as categorias")}</select>
      <select id="ff-por">${finOpcoes(uniq((l) => l.criado_por), f.por, "Lançado por qualquer um")}</select>
      <select id="ff-origem">${finOpcoes(uniq((l) => l.origem), f.origem, "Qualquer origem")}</select>
      <label class="fin-de">de <input type="date" id="ff-de" value="${f.de}"></label>
      <label class="fin-de">até <input type="date" id="ff-ate" value="${f.ate}"></label>
      <label class="check"><input type="checkbox" id="ff-revisar" ${f.revisar ? "checked" : ""}> só a revisar</label>
      <label class="check"><input type="checkbox" id="ff-excluidos" ${f.excluidos ? "checked" : ""}> ver excluídos</label>
    </div>
    <div id="ff-resumo" class="fin-resumo"></div>
    <div id="ff-tabela"></div>`;
  const desenhar = () => {
    const termo = f.busca.trim().toLowerCase();
    const lista = lancs.filter((l) =>
      (!f.tipo || l.tipo === f.tipo) && (!f.fazenda || l.fazenda === f.fazenda) && (!f.setor || l.setor === f.setor) &&
      (!f.categoria || l.categoria === f.categoria) && (!f.por || l.criado_por === f.por) &&
      (!f.origem || l.origem === f.origem) && (!f.de || l.data >= f.de) && (!f.ate || l.data <= f.ate) &&
      (!f.revisar || l.revisar) &&
      (!termo || [l.fornecedor_nome, l.descricao, l.nf_numero, l.categoria, l.observacao, String(l.valor_total).replace(".", ",")]
        .some((x) => (x || "").toLowerCase().includes(termo))));
    const desp = lista.filter((l) => l.tipo === "despesa").reduce((s, l) => s + l.valor_total, 0);
    const rec = lista.filter((l) => l.tipo === "receita").reduce((s, l) => s + l.valor_total, 0);
    alvo.querySelector("#ff-resumo").innerHTML = `<b>${lista.length}</b> lançamentos · despesas <b>${finBRL(desp)}</b> · receitas <b class="fin-receita">${finBRL(rec)}</b>`;
    finTabela(alvo.querySelector("#ff-tabela"), "lancamentos", FIN_COLUNAS_LANC, lista, {
      padrao: [{ col: "data", dir: -1 }], limite: 300,
      classeLinha: (l) => (l.revisar ? "fin-linha-revisar" : "") + (l.excluido ? " fin-linha-excluida" : ""),
      aoClicar: (l) => finAbrirLancamento(l.id, () => finRender()),
    });
  };
  const ligar = (id, campo, evento = "onchange", tipoValor = "value") => {
    alvo.querySelector(id)[evento] = (e) => {
      f[campo] = e.target[tipoValor];
      if (campo === "excluidos") return finRender();
      desenhar();
    };
  };
  alvo.querySelector("#ff-mais").onclick = () => { fin.filtrosAbertos = !fin.filtrosAbertos; finRender(); };
  ligar("#ff-busca", "busca", "oninput");
  ["tipo", "fazenda", "setor", "categoria", "por", "origem", "de", "ate"].forEach((c) => ligar(`#ff-${c}`, c));
  ligar("#ff-revisar", "revisar", "onchange", "checked");
  ligar("#ff-excluidos", "excluidos", "onchange", "checked");
  desenhar();
}

// ----------------------------------------------------------------- sub-aba Resultado (árvore × meses)
function finFiltrosResultadoPadrao() {
  const ano = hojeLocal().slice(0, 4);
  return { inicio: `${ano}-01`, fim: `${ano}-12`, visao: "caixa", status: "todos", fazenda: "", setor: "" };
}

async function finTelaResultado(alvo) {
  const f = fin.filtrosResultado || (fin.filtrosResultado = finFiltrosResultadoPadrao());
  const cad = fin.cad;
  const setores = [...new Set(cad.plano.map((p) => p.setor))].sort((a, b) => a.localeCompare(b, "pt-BR"));
  alvo.innerHTML = `
    <div class="fin-filtros">
      <label class="fin-de">de <input type="month" id="fr-inicio" value="${f.inicio}"></label>
      <label class="fin-de">até <input type="month" id="fr-fim" value="${f.fim}"></label>
      <select id="fr-visao">
        <option value="caixa" ${f.visao === "caixa" ? "selected" : ""}>Caixa (mês do pagamento)</option>
        <option value="competencia" ${f.visao === "competencia" ? "selected" : ""}>Competência (mês da compra)</option>
      </select>
      <select id="fr-status">
        <option value="todos" ${f.status === "todos" ? "selected" : ""}>Realizado + previsto</option>
        <option value="realizado" ${f.status === "realizado" ? "selected" : ""}>Só realizado</option>
        <option value="previsto" ${f.status === "previsto" ? "selected" : ""}>Só previsto</option>
      </select>
      <select id="fr-fazenda">${finOpcoes(cad.fazendas.map((x) => x.nome), f.fazenda, "Todas as fazendas")}</select>
      <select id="fr-setor">${finOpcoes(setores, f.setor, "Todos os setores")}</select>
      <button type="button" class="secundario" id="fr-abrir">Abrir tudo</button>
    </div>
    <div class="info">Toque em qualquer número para ver os lançamentos que formam ele. ▸ abre o nível de baixo.</div>
    <div id="fr-tabela"><div class="info">⏳ Calculando…</div></div>`;
  ["inicio", "fim", "visao", "status", "fazenda", "setor"].forEach((c) => {
    alvo.querySelector(`#fr-${c}`).onchange = (e) => { f[c] = e.target.value; finDesenharResultado(alvo); };
  });
  alvo.querySelector("#fr-abrir").onclick = (e) => {
    const abrir = e.target.textContent === "Abrir tudo";
    fin.abrirTudo = abrir;
    if (!abrir) fin.aberto = new Set(["despesa", "receita"]);
    e.target.textContent = abrir ? "Fechar tudo" : "Abrir tudo";
    finDesenharResultado(alvo, true);
  };
  finDesenharResultado(alvo);
}

async function finDesenharResultado(alvo, soRedesenhar = false) {
  const f = fin.filtrosResultado;
  const box = alvo.querySelector("#fr-tabela");
  if (!soRedesenhar || !fin.resultado) {
    const q = new URLSearchParams(f);
    try {
      fin.resultado = await api.get(`/api/fin/resultado?${q}`);
    } catch (e) {
      box.innerHTML = `<div class="info">⚠ ${esc(e.message)}</div>`;
      return;
    }
  }
  const r = fin.resultado;
  if (!r.meses.length) { box.innerHTML = `<div class="info">Nenhum lançamento nesse período.</div>`; return; }
  const linhas = [];
  const rotTipo = { despesa: "Despesas", receita: "Receitas" };
  const andar = (no, nivel, caminho) => {
    const chave = caminho.join("›");
    const temFilhos = no.filhos && no.filhos.length;
    const aberto = fin.abrirTudo || fin.aberto.has(chave);
    linhas.push({ no, nivel, caminho, chave, temFilhos, aberto });
    if (temFilhos && aberto) no.filhos.forEach((fl) => andar(fl, nivel + 1, [...caminho, fl.nome]));
  };
  r.arvore.forEach((t) => andar(t, 0, [t.nome]));
  const celula = (valor, caminho, mes, extra = "") =>
    valor ? `<td class="num fin-cel ${extra}" data-caminho="${esc(JSON.stringify(caminho))}" data-mes="${mes || ""}">${finBRL(valor)}</td>` : `<td class="num fin-zero">—</td>`;
  box.innerHTML = `<div class="fin-tabela fin-arvore"><table>
    <thead><tr><th class="fin-col-nome">Conta</th>${r.meses.map((m) => `<th class="num">${finMes(m)}</th>`).join("")}<th class="num">Total</th></tr></thead>
    <tbody>${linhas.map((ln) => `
      <tr class="fin-nivel-${ln.nivel} ${ln.no.nome === "(sem categoria)" ? "fin-linha-revisar" : ""}">
        <td class="fin-col-nome" style="padding-left:${6 + ln.nivel * 14}px">
          ${ln.temFilhos ? `<button type="button" class="fin-abre" data-chave="${esc(ln.chave)}">${ln.aberto ? "▾" : "▸"}</button>` : `<span class="fin-abre-vazio"></span>`}
          ${ln.nivel === 0 ? `<b>${rotTipo[ln.no.nome] || esc(ln.no.nome)}</b>` : esc(ln.no.nome)}
          <span class="info">${ln.no.n}</span></td>
        ${r.meses.map((m) => celula(ln.no.meses[m], ln.caminho, m)).join("")}
        ${celula(ln.no.total, ln.caminho, "", "fin-total")}
      </tr>`).join("")}
      <tr class="fin-saldo"><td class="fin-col-nome"><b>Resultado (receitas − despesas)</b></td>
        ${r.meses.map((m) => `<td class="num ${r.saldo[m] < 0 ? "fin-negativo" : "fin-receita"}">${finBRL(r.saldo[m])}</td>`).join("")}
        <td class="num ${r.saldo_total < 0 ? "fin-negativo" : "fin-receita"}"><b>${finBRL(r.saldo_total)}</b></td></tr>
    </tbody></table></div>`;
  box.querySelectorAll(".fin-abre").forEach((b) => {
    b.onclick = () => {
      fin.abrirTudo = false;
      if (fin.aberto.has(b.dataset.chave)) fin.aberto.delete(b.dataset.chave);
      else fin.aberto.add(b.dataset.chave);
      finDesenharResultado(alvo, true);
    };
  });
  box.querySelectorAll(".fin-cel").forEach((td) => {
    td.onclick = () => finDetalheResultado(JSON.parse(td.dataset.caminho), td.dataset.mes || null);
  });
}

async function finDetalheResultado(caminho, mes) {
  const f = fin.filtrosResultado;
  let linhas;
  try {
    linhas = await api.post("/api/fin/resultado/detalhe", { filtros: f, caminho, mes });
  } catch (e) {
    finMsg("⚠ " + e.message, true);
    return;
  }
  const total = linhas.reduce((s, l) => s + l.valor, 0);
  const titulo = caminho.map((c, i) => (i === 0 ? (c === "despesa" ? "Despesas" : "Receitas") : c)).join(" › ");
  const colunas = [
    { id: "venc", rotulo: f.visao === "caixa" ? "Vencimento" : "Data", valor: (l) => l.vencimento || l.data, data: true, html: (l) => finData(l.vencimento || l.data) },
    { id: "fornecedor", rotulo: "Fornecedor", valor: (l) => l.fornecedor, html: (l) => esc(l.fornecedor || "—") },
    { id: "descricao", rotulo: "Descrição", valor: (l) => l.descricao, html: (l) => esc(l.descricao || "") },
    { id: "categoria", rotulo: "Categoria", valor: (l) => l.categoria, html: (l) => finCaminho(l) },
    { id: "valor", rotulo: "Valor", valor: (l) => l.valor, num: true, html: (l) => finBRL(l.valor) },
    { id: "parcela", rotulo: "Parc.", valor: (l) => l.parcela, html: (l) => esc(l.parcela || "") },
    { id: "conta", rotulo: "Conta", valor: (l) => l.conta, html: (l) => esc(l.conta || "—") },
    { id: "nf", rotulo: "NF", valor: (l) => l.nf_numero, html: (l) => esc(l.nf_numero || "") },
    { id: "por", rotulo: "Lançado por", valor: (l) => l.criado_por, html: (l) => esc(l.criado_por || "") },
  ];
  finModal(`<h3>${esc(titulo)}${mes ? ` · ${finMes(mes)}` : ""}</h3>
    <div class="fin-resumo"><b>${linhas.length}</b> lançamentos · total <b>${finBRL(total)}</b></div>
    <div id="fd-tabela"></div>`, (corpo) => {
    finTabela(corpo.querySelector("#fd-tabela"), "detalhe", colunas, linhas, {
      padrao: [{ col: "valor", dir: -1 }],
      classeLinha: (l) => (l.revisar ? "fin-linha-revisar" : ""),
      aoClicar: (l) => finAbrirLancamento(l.lancamento_id, async () => {
        // corrigiu: atualiza a árvore e volta pra mesma lista, já atualizada
        fin.resultado = null;
        finFecharTudo();
        await finRender();
        finDetalheResultado(caminho, mes);
      }),
    });
  });
}

// ----------------------------------------------------------------- sub-aba Revisar
async function finTelaRevisar(alvo) {
  alvo.innerHTML = `<div class="info">⏳ Conferindo…</div>`;
  const [lancs, conf] = await Promise.all([finCarregarLancamentos(), api.get("/api/fin/conferencia")]);
  const revisar = lancs.filter((l) => l.revisar);
  const porId = Object.fromEntries(lancs.map((l) => [l.id, l]));
  alvo.innerHTML = `
    <div class="fin-cards">
      <a href="#fr-revisar" class="fin-card vermelho"><span>${revisar.length}</span>a revisar (sem categoria ou importados com aviso)</a>
      <a href="#fr-confirmar" class="fin-card amarelo"><span>${conf.a_confirmar.length}</span>recorrentes a confirmar</a>
      <a href="#fr-dup" class="fin-card"><span>${conf.duplicados.length}</span>possíveis duplicados</a>
    </div>
    <div class="fin-secao" id="fr-confirmar"><h3>Recorrentes a confirmar</h3>
      <div class="info">Confira o valor real do mês e toque em ✔. Se não houve a despesa, abra e exclua.</div>
      <div id="frc-lista"></div></div>
    <div class="fin-secao" id="fr-dup"><h3>Possíveis duplicados</h3>
      <div class="info">Mesma nota, ou mesmo fornecedor, valor e descrição idêntica com até 3 dias de diferença
        (parcelas 1/2P e 2/2P não contam). Abra e exclua o repetido.</div>
      <div id="frd-lista"></div></div>
    <div class="fin-secao" id="fr-revisar"><h3>A revisar</h3><div id="frr-lista"></div></div>`;
  alvo.querySelectorAll(".fin-card").forEach((a) => {
    a.onclick = (e) => { e.preventDefault(); alvo.querySelector(a.getAttribute("href")).scrollIntoView({ behavior: "smooth" }); };
  });
  // a confirmar
  const boxC = alvo.querySelector("#frc-lista");
  boxC.innerHTML = conf.a_confirmar.length ? conf.a_confirmar.map((l) => {
    const p = l.parcelas.find((x) => x.pago === false);
    return `<div class="fin-item"><div><b>${esc(l.descricao)}</b> <span class="info">${finData(p.vencimento)} · ${esc(l.fornecedor_nome || "")} · ${esc(l.categoria || "sem categoria")}</span></div>
      <div class="fin-item-acoes"><input inputmode="decimal" value="${String(p.valor).replace(".", ",")}" data-p="${p.id}">
      <button type="button" data-ok="${p.id}">✔</button><button type="button" class="secundario" data-abrir="${l.id}">abrir</button></div></div>`;
  }).join("") : `<div class="info">Nada a confirmar.</div>`;
  boxC.querySelectorAll("[data-ok]").forEach((b) => {
    b.onclick = () => finOcupado(b, "…", async () => {
      const valor = finNum(boxC.querySelector(`input[data-p="${b.dataset.ok}"]`).value);
      await api.put(`/api/fin/parcelas/${b.dataset.ok}`, { pago: true, valor });
      finInvalidar();
      finMsg("✔ Confirmado");
      finRender();
    });
  });
  boxC.querySelectorAll("[data-abrir]").forEach((b) => { b.onclick = () => finAbrirLancamento(Number(b.dataset.abrir)); });
  // duplicados
  const boxD = alvo.querySelector("#frd-lista");
  boxD.innerHTML = conf.duplicados.length ? conf.duplicados.map((ids) => `<div class="fin-item fin-dup">${ids.map((id) => {
    const l = porId[id];
    return l ? `<a href="#" data-abrir="${id}">${finData(l.data)} · ${esc(l.fornecedor_nome || "—")} · ${finBRL(l.valor_total)} · ${esc(l.descricao || "")} <span class="info">(${esc(l.origem)})</span></a>` : "";
  }).join("")}<button type="button" class="secundario" data-dupok="${ids.join(",")}">Não é duplicado (compra repetida mesmo)</button></div>`).join("") : `<div class="info">Nenhum duplicado encontrado.</div>`;
  boxD.querySelectorAll("[data-dupok]").forEach((b) => {
    b.onclick = () => finOcupado(b, "…", async () => {
      await api.post("/api/fin/lancamentos/nao-duplicado", { ids: b.dataset.dupok.split(",").map(Number) });
      finMsg("Ok, não aparece mais como duplicado");
      finRender();
    });
  });
  boxD.querySelectorAll("[data-abrir]").forEach((a) => { a.onclick = (e) => { e.preventDefault(); finAbrirLancamento(Number(a.dataset.abrir)); }; });
  // a revisar
  finTabela(alvo.querySelector("#frr-lista"), "revisar",
    [...FIN_COLUNAS_LANC.filter((c) => ["data", "fornecedor", "descricao", "categoria", "valor"].includes(c.id)),
      { id: "motivo", rotulo: "Motivo", valor: (l) => l.revisar_motivo, html: (l) => `<span class="fin-sem-cat">${esc(l.revisar_motivo || "")}</span>` }],
    revisar, { padrao: [{ col: "data", dir: -1 }], limite: 200, classeLinha: () => "fin-linha-revisar",
      aoClicar: (l) => finAbrirLancamento(l.id, () => finRender()), vazio: "Tudo revisado 👍" });
}

// ----------------------------------------------------------------- sub-aba Recorrentes
async function finTelaRecorrentes(alvo) {
  const lista = await api.get("/api/fin/recorrentes");
  alvo.innerHTML = `<div class="fin-form-topo"><div class="info">Despesas que se repetem todo mês (salário, Copel, tarifas, seguro).
    O app cria o lançamento do mês "a confirmar" — você confere o valor na aba Revisar.</div>
    <button type="button" id="frec-novo">+ Recorrente</button></div><div id="frec-tabela"></div>`;
  finTabela(alvo.querySelector("#frec-tabela"), "recorrentes", [
    { id: "descricao", rotulo: "Descrição", valor: (r) => r.descricao, html: (r) => `<b>${esc(r.descricao)}</b>` },
    { id: "fornecedor", rotulo: "Fornecedor", valor: (r) => r.fornecedor_nome, html: (r) => esc(r.fornecedor_nome || "—") },
    { id: "categoria", rotulo: "Categoria", valor: (r) => r.categoria, html: (r) => finCaminho(r) },
    { id: "valor", rotulo: "Valor", valor: (r) => r.valor, num: true, html: (r) => finBRL(r.valor) },
    { id: "dia", rotulo: "Dia", valor: (r) => r.dia, num: true, html: (r) => String(r.dia) },
    { id: "conta", rotulo: "Conta", valor: (r) => r.conta, html: (r) => esc(r.conta || "—") },
    { id: "ativo", rotulo: "Situação", valor: (r) => (r.ativo ? "ativo" : "inativo"), html: (r) => (r.ativo ? "ativo" : `<span class="info">inativo</span>`) },
  ], lista, { padrao: [{ col: "descricao", dir: 1 }], aoClicar: (r) => finEditarRecorrente(r),
    vazio: "Nenhum recorrente ainda. Cadastre salário, luz, internet…" });
  alvo.querySelector("#frec-novo").onclick = () => finEditarRecorrente({ tipo: "despesa", dia: 10, ativo: true });
}

function finEditarRecorrente(r) {
  const cad = fin.cad;
  finModal(`<form id="frec-form" class="fin-form">
      <div class="fin-form-topo"><h3>${r.id ? "Editar recorrente" : "Novo recorrente"}</h3><button type="submit" id="frec-salvar">Salvar</button></div>
      <div class="fin-grid">
        <div class="fin-largo"><label>Descrição</label><input id="frec-desc" value="${esc(r.descricao || "")}" required></div>
        <div><label>Tipo</label><select id="frec-tipo"><option value="despesa">Despesa</option><option value="receita" ${r.tipo === "receita" ? "selected" : ""}>Receita</option></select></div>
        <div class="fin-largo"><label>Fornecedor</label><input id="frec-forn" list="frec-dl" value="${esc(r.fornecedor_nome || "")}">
          <datalist id="frec-dl">${cad.fornecedores.map((f) => `<option value="${esc(f.nome)}">`).join("")}</datalist></div>
        <div><label>Valor (R$)</label><input id="frec-valor" inputmode="decimal" value="${r.valor != null ? String(r.valor).replace(".", ",") : ""}"></div>
        <div><label>Dia do vencimento</label><input id="frec-dia" type="number" min="1" max="31" value="${r.dia || 10}"></div>
        <div><label>A partir de</label><input id="frec-inicio" type="date" value="${r.inicio || hojeLocal().slice(0, 8) + "01"}"></div>
        <div><label>Conta</label><select id="frec-conta">${finOpcoes(finAtivos(cad.contas).map((c) => c.nome), r.conta)}</select></div>
      </div>
      ${finHtmlClasse("frec", r)}
      <label class="check"><input type="checkbox" id="frec-ativo" ${r.ativo !== false ? "checked" : ""}> ativo (desmarque pra parar de gerar)</label>
    </form>`, (corpo) => {
    const classe = finLigarClasse(corpo, "frec", () => corpo.querySelector("#frec-tipo").value, r);
    corpo.querySelector("#frec-tipo").onchange = () => classe.aplicar({});
    corpo.querySelector("#frec-form").onsubmit = (ev) => {
      ev.preventDefault();
      const dados = {
        descricao: corpo.querySelector("#frec-desc").value, tipo: corpo.querySelector("#frec-tipo").value,
        fornecedor_nome: corpo.querySelector("#frec-forn").value.trim() || null,
        valor: finNum(corpo.querySelector("#frec-valor").value), dia: Number(corpo.querySelector("#frec-dia").value),
        inicio: corpo.querySelector("#frec-inicio").value, conta: corpo.querySelector("#frec-conta").value || null,
        ativo: corpo.querySelector("#frec-ativo").checked, ...classe.valores(),
      };
      finOcupado(corpo.querySelector("#frec-salvar"), "Salvando…", async () => {
        if (r.id) await api.put(`/api/fin/recorrentes/${r.id}`, dados);
        else await api.post("/api/fin/recorrentes", dados);
        finInvalidar();
        await finCarregarCadastros(true);
        finMsg("✔ Recorrente salvo");
        finFecharTudo();
        finRender();
      });
    };
  });
}

// ----------------------------------------------------------------- navegação
const FIN_TELAS = {
  lancar: finTelaLancar,
  resultado: finTelaResultado,
  lancamentos: finTelaLancamentos,
  revisar: finTelaRevisar,
  recorrentes: finTelaRecorrentes,
  // as outras (notas, extrato, cadastros) são registradas por financeiro-notas.js
};

async function finRender() {
  const alvo = document.getElementById("fin-corpo");
  if (!alvo) return;
  document.querySelectorAll("#fin-modos button").forEach((b) => b.classList.toggle("ativa", b.dataset.fin === fin.modo));
  try {
    await finCarregarCadastros();
    if (fin.modo !== "resultado") fin.resultado = null;
    await FIN_TELAS[fin.modo](alvo);
  } catch (e) {
    alvo.innerHTML = `<div class="info">⚠ Erro ao carregar: ${esc(e.message)}. <a href="#" id="fin-retentar">Tentar de novo</a></div>`;
    const r = document.getElementById("fin-retentar");
    if (r) r.onclick = (ev) => { ev.preventDefault(); fin.cad = null; finRender(); };
  }
  finAtualizarContadores();
}

// Contador vermelho na sub-aba Revisar e na de Notas.
async function finAtualizarContadores() {
  try {
    const lancs = fin.lancs || (fin.modo === "lancar" ? null : await finCarregarLancamentos());
    const btn = document.querySelector('#fin-modos button[data-fin="revisar"]');
    if (lancs && btn) {
      const n = lancs.filter((l) => l.revisar).length;
      btn.innerHTML = `Revisar${n ? ` <span class="fin-badge">${n}</span>` : ""}`;
    }
  } catch { /* contador é só enfeite */ }
}

document.querySelectorAll("#fin-modos button").forEach((b) => {
  b.onclick = () => { fin.modo = b.dataset.fin; finFecharTudo(); finRender(); };
});
document.getElementById("fin-modal-fechar").onclick = finFecharModal;
document.getElementById("fin-modal").addEventListener("click", (e) => { if (e.target.id === "fin-modal") finFecharModal(); });

window.finAbrir = () => finRender();
