// Fila de ações lançadas sem internet (ou com rede fraca): guarda no localStorage e
// envia automaticamente quando a conexão voltar. Cobre tanto pesagens da mangueira
// (sessão) quanto ações genéricas (ex.: editar tipo/raça/observação offline).

const FILA_KEY = "gat_fila_pesagens";

function filaLer() {
  try {
    return JSON.parse(localStorage.getItem(FILA_KEY)) || [];
  } catch {
    return [];
  }
}

function filaSalvar(lista) {
  localStorage.setItem(FILA_KEY, JSON.stringify(lista));
  filaAtualizarContador();
}

// Aceita duas formas de item:
// - genérica: { metodo, url, corpo, rotulo } — qualquer chamada de escrita.
// - da mangueira (mantida por compatibilidade): { sessaoId, tipo: "pesar" |
//   "pesar-sem-brinco", dados } — vira a forma genérica na hora de guardar.
function filaAdicionar(item) {
  const lista = filaLer();
  const generico = item.url
    ? {
        metodo: item.metodo || "POST",
        url: item.url,
        corpo: item.corpo,
        rotulo: item.rotulo || item.url,
      }
    : {
        metodo: "POST",
        url: item.tipo === "pesar-sem-brinco"
          ? `/api/sessoes/${item.sessaoId}/pesar-sem-brinco`
          : `/api/sessoes/${item.sessaoId}/pesar`,
        corpo: item.dados,
        rotulo: `Brinco ${(item.dados && item.dados.brinco) || "(sem brinco)"}`,
      };
  lista.push({ id: Date.now() + "_" + Math.random().toString(36).slice(2), ...generico });
  filaSalvar(lista);
}

// ---- Ações recusadas -----------------------------------------------------------
// O que o servidor recusou de vez (ex.: brinco que não existe) NÃO some: fica
// guardado aqui até o usuário ver e resolver na mão.
const FILA_RECUSADAS_KEY = "gat_fila_recusadas";

function recusadasLer() {
  try {
    return JSON.parse(localStorage.getItem(FILA_RECUSADAS_KEY)) || [];
  } catch {
    return [];
  }
}

function recusadasSalvar(lista) {
  localStorage.setItem(FILA_RECUSADAS_KEY, JSON.stringify(lista));
  filaAtualizarContador();
}

// Texto curto do que era o lançamento (pra pessoa conseguir refazer).
function filaDescrever(item) {
  const c = item.corpo || {};
  return item.rotulo + (c.peso != null ? ` — ${c.peso} kg` : "");
}

function recusadasMostrar() {
  const lista = recusadasLer();
  if (!lista.length) return;
  const texto = lista.map((r) => `• ${r.descricao}: ${r.motivo}`).join("\n");
  if (confirm(
    "Estes lançamentos NÃO foram gravados (o servidor recusou):\n\n" + texto +
    "\n\nRefaça cada um na mão. Depois de refazer, toque em OK pra limpar esta lista " +
    "(Cancelar mantém o aviso)."
  )) recusadasSalvar([]);
}

function filaAtualizarContador() {
  const n = filaLer().length;
  const rec = recusadasLer().length;
  const partes = [];
  if (n) partes.push(n === 1 ? "📡 1 lançamento aguardando a rede" : `📡 ${n} lançamentos aguardando a rede`);
  if (rec) partes.push(`⚠ ${rec} não gravado${rec === 1 ? "" : "s"} — toque pra ver`);
  ["fila-status", "fila-status-global"].forEach((id) => {
    const box = document.getElementById(id);
    if (!box) return;
    box.classList.toggle("escondido", !partes.length);
    box.classList.toggle("fila-recusadas", rec > 0);
    box.textContent = partes.join(" · ");
    box.onclick = rec ? recusadasMostrar : null;
  });
}

const PRAZO_FILA_MS = 30000;   // por item (o servidor pode estar "acordando")
let filaSincronizando = false;

// Envia a fila em ordem. Regras pra NUNCA perder lançamento:
//  - sem resposta / prazo estourado / erro do servidor (5xx) / login vencido (401):
//    para e mantém tudo na fila pra tentar de novo depois;
//  - servidor respondeu que não dá (4xx, ou 200 com "alerta"): tira da fila e guarda
//    em "recusadas", com o motivo, pra pessoa refazer na mão.
async function filaSincronizar() {
  if (filaSincronizando || !navigator.onLine) return;
  let lista = filaLer();
  if (!lista.length) return;
  filaSincronizando = true;
  let enviou = false;
  try {
    for (const item of lista) {
      let r;
      try {
        r = await fetchComPrazo(item.url, {
          method: item.metodo,
          headers: cabecalhos({ "Content-Type": "application/json" }),
          body: JSON.stringify(item.corpo),
        }, PRAZO_FILA_MS);
      } catch {
        marcarRedeRuim();   // rede ainda ruim: tenta de novo mais tarde, na mesma ordem
        break;
      }
      // Servidor fora do ar/acordando, ou login vencido: não é culpa do lançamento.
      if (r.status >= 500 || r.status === 401 || r.status === 408 || r.status === 429) break;

      const corpo = await r.json().catch(() => ({}));
      let motivo = null;
      if (!r.ok) motivo = corpo.detail || "Erro ao enviar";
      else if (corpo && corpo.alerta) motivo = corpo.mensagem || "O servidor não aceitou o lançamento";
      if (motivo) {
        recusadasSalvar([...recusadasLer(), { descricao: filaDescrever(item), motivo }]);
      }
      // Gravado (ou recusado de vez): sai da fila.
      lista = lista.filter((x) => x.id !== item.id);
      filaSalvar(lista);
      enviou = true;
      marcarRedeBoa();
    }
    const naMangueira = typeof mg !== "undefined" && mg.sessaoId &&
      document.getElementById("mg-sessao") &&
      !document.getElementById("mg-sessao").classList.contains("escondido");
    if (enviou && naMangueira) {
      try {
        mgRenderEstado(await api.get(`/api/sessoes/${mg.sessaoId}`, PRAZO_FILA_MS));
        carregarCacheAnimais().catch(() => {});
      } catch { /* sem rede de novo: a tela continua com o que tem */ }
    }
  } finally {
    filaSincronizando = false;
    filaAtualizarContador();
  }
}

window.addEventListener("online", () => { marcarRedeBoa(); filaSincronizar(); });
setInterval(filaSincronizar, 20000);
document.addEventListener("DOMContentLoaded", filaAtualizarContador);
