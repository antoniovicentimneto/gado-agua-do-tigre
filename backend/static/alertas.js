// Sininho 🔔 no topo: alertas do campo (mudar lote, piquete pronto, salgar, pesar...).
// Os alertas são calculados no servidor; "✓ Visto" esconde o alerta só neste aparelho e
// só até amanhã (se continuar valendo, volta).

const CHAVE_ALERTAS_OFFLINE = "gat_cache_alertas";
const CHAVE_ALERTAS_VISTOS = "gat_alertas_vistos";
const al = { lista: [] };

function alVistos() {
  const v = lerOffline(CHAVE_ALERTAS_VISTOS) || {};
  const hoje = hojeLocal();
  for (const k of Object.keys(v)) if (v[k] !== hoje) delete v[k];  // "visto" vale só no dia
  return v;
}

function alPendentes() {
  const vistos = alVistos();
  return al.lista.filter((a) => !vistos[a.id]);
}

async function alCarregar() {
  if (!estaLogado()) return;
  try {
    const r = await api.get(`/api/pastos/alertas?hoje=${hojeLocal()}`, 20000);
    al.lista = r.alertas;
    salvarOffline(CHAVE_ALERTAS_OFFLINE, r.alertas);
  } catch (e) {
    al.lista = lerOffline(CHAVE_ALERTAS_OFFLINE) || [];
  }
  alAtualizarSino();
}
window.alCarregar = alCarregar;

function alAtualizarSino() {
  const b = document.getElementById("btn-sino");
  if (!b) return;
  const pend = alPendentes();
  b.querySelector("span").textContent = pend.length || "";
  b.classList.toggle("tem", pend.length > 0);
  b.classList.toggle("urgente", pend.some((a) => a.nivel === "vermelho"));
  if (window.inAtualizarAtencao) window.inAtualizarAtencao();   // a tela inicial mostra o mesmo total
}

const AL_ICONE = { vermelho: "🔴", amarelo: "🟡", verde: "🟢" };

function alAbrir() {
  const pend = alPendentes();
  const vistos = al.lista.length - pend.length;
  ptModal(`
    <h2>🔔 Alertas</h2>
    ${pend.length ? pend.map((a) => `
      <div class="al-item al-${a.nivel}">
        <div class="al-texto">${AL_ICONE[a.nivel] || "•"} <b>${esc(a.titulo)}</b><br><small>${esc(a.detalhe)}</small></div>
        <div class="al-botoes">
          <button type="button" class="secundario" data-abrir="${esc(a.id)}">Abrir</button>
          <button type="button" class="secundario" data-visto="${esc(a.id)}">✓ Visto</button>
        </div>
      </div>`).join("") : '<p>Nada pendente hoje. 👍</p>'}
    ${vistos ? `<p class="info">${vistos} alerta(s) marcado(s) como visto hoje. <a href="#" id="al-mostrar">Mostrar de novo</a></p>` : ""}`);
  document.querySelectorAll("[data-visto]").forEach((b) => {
    b.onclick = () => {
      const v = alVistos();
      v[b.dataset.visto] = hojeLocal();
      salvarOffline(CHAVE_ALERTAS_VISTOS, v);
      alAtualizarSino();
      alAbrir();
    };
  });
  document.querySelectorAll("[data-abrir]").forEach((b) => {
    b.onclick = () => alIrPara(al.lista.find((a) => a.id === b.dataset.abrir));
  });
  const mostrar = document.getElementById("al-mostrar");
  if (mostrar) mostrar.onclick = (e) => { e.preventDefault(); salvarOffline(CHAVE_ALERTAS_VISTOS, {}); alAtualizarSino(); alAbrir(); };
}

// Leva até o que o alerta fala: ficha do lote (Pastos) ou histórico do piquete.
async function alIrPara(a) {
  if (!a) return;
  ptFecharModal();
  document.querySelector('.abas button[data-aba="pastos"]').click();
  if (!pt.dados) await ptCarregar();
  if (pt.modo === "indicadores") ptMudarModo("lista");
  if (a.alvo.tipo === "lote") ptFichaLote(a.alvo.id);
  else if (a.alvo.tipo === "piquete") ptHistoricoPiquete(a.alvo.id);
}

document.getElementById("btn-sino").onclick = alAbrir;
setInterval(alCarregar, 10 * 60 * 1000);

// ---------------------------------------------------------------- Limites (Config)

async function alConfigLimites(boxId) {
  const box = document.getElementById(boxId);
  if (!box) return;
  let lim;
  try { lim = (await api.get(`/api/pastos/alertas?hoje=${hojeLocal()}`)).limites; } catch (e) { box.textContent = e.message; return; }
  box.innerHTML = `
    <div class="grid-2">
      <div><label>Máximo de dias do lote no piquete</label><input id="al-ocup" inputmode="numeric" value="${lim.ocupacao_max_dias}" /></div>
      <div><label>Avisar salga depois de (dias)</label><input id="al-sal" inputmode="numeric" value="${lim.sal_dias}" /></div>
      <div><label>Mortalidade aceitável (% no período)</label><input id="al-mort" inputmode="numeric" value="${lim.mortalidade_max_pct}" /></div>
      <div><label>Rebanho pesado em dia, mínimo (%)</label><input id="al-pesados" inputmode="numeric" value="${lim.pesados_min_pct}" /></div>
    </div>
    <p class="info">O máximo de dias pode ser diferente em cada piquete (⚙ do piquete). O aviso de salga só
      aparece para lotes que já tiveram salga registrada.</p>
    <button type="button" id="al-salvar" class="secundario" style="width:100%">Salvar modificações</button>
    <div class="info" id="al-msg"></div>`;
  document.getElementById("al-salvar").onclick = async (ev) => {
    const btn = ev.currentTarget;
    btn.disabled = true;
    try {
      await api.put("/api/pastos/alertas/limites", {
        ocupacao_max_dias: document.getElementById("al-ocup").value,
        sal_dias: document.getElementById("al-sal").value,
        mortalidade_max_pct: document.getElementById("al-mort").value,
        pesados_min_pct: document.getElementById("al-pesados").value,
      });
      document.getElementById("al-msg").textContent = "✓ Salvo.";
      alCarregar();
    } catch (e) {
      document.getElementById("al-msg").textContent = e.message;
    } finally {
      btn.disabled = false;
    }
  };
}
window.alConfigLimites = alConfigLimites;
