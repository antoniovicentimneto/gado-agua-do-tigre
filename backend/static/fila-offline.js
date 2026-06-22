// Fila de pesagens lançadas sem internet: guarda no localStorage e envia
// automaticamente quando a conexão voltar.

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

function filaAdicionar(item) {
  const lista = filaLer();
  lista.push({ id: Date.now() + "_" + Math.random().toString(36).slice(2), ...item });
  filaSalvar(lista);
}

function filaAtualizarContador() {
  const n = filaLer().length;
  const texto = n === 1 ? "📡 1 pesagem aguardando envio" : `📡 ${n} pesagens aguardando envio`;
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
      const url = item.tipo === "pesar-sem-brinco"
        ? `/api/sessoes/${item.sessaoId}/pesar-sem-brinco`
        : `/api/sessoes/${item.sessaoId}/pesar`;
      try {
        const r = await fetch(url, {
          method: "POST",
          headers: cabecalhos({ "Content-Type": "application/json" }),
          body: JSON.stringify(item.dados),
        });
        if (!r.ok) {
          // Rejeitado pelo servidor (ex.: sessão já finalizada) — não tenta de novo.
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
        "Algumas pesagens da fila offline não puderam ser enviadas:\n" +
        falhas.map((f) => `Brinco ${f.item.dados.brinco || "(sem brinco)"}: ${f.motivo}`).join("\n") +
        "\nLance esses pesos de novo manualmente."
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
