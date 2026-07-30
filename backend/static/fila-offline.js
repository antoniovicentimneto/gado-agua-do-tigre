// Fila de ações lançadas sem internet: guarda no localStorage e envia
// automaticamente quando a conexão voltar. Cobre tanto pesagens da mangueira
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

function filaAtualizarContador() {
  const n = filaLer().length;
  const texto = n === 1 ? "📡 1 ação aguardando envio" : `📡 ${n} ações aguardando envio`;
  ["fila-status", "fila-status-global"].forEach((id) => {
    const box = document.getElementById(id);
    if (!box) return;
    box.classList.toggle("escondido", n === 0);
    box.textContent = texto;
  });
}

let filaSincronizando = false;

async function filaSincronizar() {
  if (filaSincronizando || !navigator.onLine) return;
  filaSincronizando = true;
  try {
    let lista = filaLer();
    const falhas = [];
    for (const item of lista) {
      try {
        const r = await fetch(item.url, {
          method: item.metodo,
          headers: cabecalhos({ "Content-Type": "application/json" }),
          body: JSON.stringify(item.corpo),
        });
        if (!r.ok) {
          // Rejeitado pelo servidor (ex.: sessão já finalizada, sem permissão) — não tenta de novo.
          const erro = await r.json().catch(() => ({}));
          falhas.push({ item, motivo: erro.detail || "Erro ao enviar" });
        }
        // Sucesso ou rejeição definitiva: remove da fila.
        lista = lista.filter((x) => x.id !== item.id);
        filaSalvar(lista);
      } catch {
        // Falha de rede: para aqui e tenta de novo mais tarde, preservando a ordem.
        break;
      }
    }
    if (falhas.length) {
      alert(
        "Algumas ações da fila offline não puderam ser enviadas:\n" +
        falhas.map((f) => `${f.item.rotulo}: ${f.motivo}`).join("\n") +
        "\nRefaça essas ações manualmente."
      );
    }
    if (mg.sessaoId && document.getElementById("mg-sessao") && !document.getElementById("mg-sessao").classList.contains("escondido")) {
      mgRenderEstado(await api.get(`/api/sessoes/${mg.sessaoId}`));
    }
  } finally {
    filaSincronizando = false;
  }
}

window.addEventListener("online", filaSincronizar);
setInterval(filaSincronizar, 20000);
document.addEventListener("DOMContentLoaded", filaAtualizarContador);
