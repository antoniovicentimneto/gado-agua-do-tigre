// Mapa de satélite sem sinal: baixa as imagens da área da fazenda (piquetes, divisa e
// outras áreas) em vários zooms e guarda no aparelho. O service worker serve essas
// imagens quando não há internet (cache "gado-mapa-tiles", que sobrevive às versões).

const MO_CACHE = "gado-mapa-tiles";
const MO_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile";
const MO_ZOOMS = [13, 14, 15, 16, 17];
const MO_MAX_TILES = 4000;      // trava de segurança (~45 MB)
const MO_KB_POR_TILE = 12;      // média das imagens de satélite (pra estimar o tamanho)
const MO_CHAVE_INFO = "gat_mapa_offline_info";

function moTile(lat, lng, z) {
  const n = 2 ** z;
  const x = Math.floor(((lng + 180) / 360) * n);
  const r = (lat * Math.PI) / 180;
  const y = Math.floor(((1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2) * n);
  return [x, y];
}

// Retângulo que cobre tudo o que está desenhado no mapa da fazenda (com uma folga).
function moLimitesFazenda() {
  const geos = [...(pt.dados.piquetes || []).map((p) => p.geometria), ...(pt.dados.camadas || []).map((c) => c.geometria)]
    .filter(Boolean);
  if (!geos.length) return null;
  const b = L.geoJSON({ type: "GeometryCollection", geometries: geos }).getBounds().pad(0.15);
  return b;
}

function moListaTiles(b) {
  const urls = [];
  for (const z of MO_ZOOMS) {
    const [x1, y1] = moTile(b.getNorth(), b.getWest(), z);
    const [x2, y2] = moTile(b.getSouth(), b.getEast(), z);
    for (let x = Math.min(x1, x2); x <= Math.max(x1, x2); x++) {
      for (let y = Math.min(y1, y2); y <= Math.max(y1, y2); y++) urls.push(`${MO_URL}/${z}/${y}/${x}`);
    }
  }
  return urls;
}

function moMB(n) {
  const mb = (n * MO_KB_POR_TILE) / 1024;
  return mb < 1 ? "menos de 1 MB" : `~${Math.round(mb)} MB`;
}

function moTextoInfo() {
  const info = lerOffline(MO_CHAVE_INFO);
  return info ? `Mapa salvo no aparelho em ${new Date(info.em).toLocaleString("pt-BR")} (${info.n} imagens, ${moMB(info.n)}).`
    : "O mapa ainda não foi salvo neste aparelho.";
}

async function moAbrir() {
  const b = moLimitesFazenda();
  if (!b) { alert("Cadastre ou importe os piquetes primeiro — o mapa salvo cobre a área deles."); return; }
  const urls = moListaTiles(b);
  ptModal(`
    <h2>⬇ Mapa para usar sem sinal</h2>
    <p>${esc(moTextoInfo())}</p>
    <p>Baixa as imagens de satélite da área da fazenda (zoom ${MO_ZOOMS[0]} a ${MO_ZOOMS[MO_ZOOMS.length - 1]}):
      <b>${urls.length} imagens</b>, <b>${moMB(urls.length)}</b>. Faça com Wi-Fi.</p>
    ${urls.length > MO_MAX_TILES ? `<p style="color:var(--vermelho)">A área é grande demais (${urls.length} imagens). Confira se não há algum piquete muito longe da fazenda.</p>` : ""}
    <div class="mo-barra escondido" id="mo-barra"><div id="mo-progresso"></div></div>
    <p class="info" id="mo-status"></p>
    <div class="pt-linha-botoes">
      <button type="button" class="secundario" id="mo-apagar">Apagar mapa salvo</button>
      <button type="button" id="mo-baixar" ${urls.length > MO_MAX_TILES ? "disabled" : ""}>⬇ Salvar mapa</button>
    </div>`);
  ptEl("mo-baixar").onclick = () => moBaixar(urls);
  ptEl("mo-apagar").onclick = async () => {
    if (!confirm("Apagar as imagens de satélite salvas neste aparelho?")) return;
    await caches.delete(MO_CACHE);
    localStorage.removeItem(MO_CHAVE_INFO);
    ptEl("mo-status").textContent = "Mapa salvo apagado.";
  };
}

async function moBaixar(urls) {
  if (!navigator.onLine) { alert("Precisa de internet para baixar o mapa."); return; }
  const btn = ptEl("mo-baixar");
  btn.disabled = true;
  ptEl("mo-barra").classList.remove("escondido");
  const cache = await caches.open(MO_CACHE);
  let feitos = 0, falhas = 0, i = 0;
  const atualizar = () => {
    if (!ptEl("mo-progresso")) return;
    ptEl("mo-progresso").style.width = `${Math.round((feitos / urls.length) * 100)}%`;
    ptEl("mo-status").textContent = `${feitos} de ${urls.length} imagens${falhas ? ` · ${falhas} falharam` : ""}…`;
  };
  // 6 downloads ao mesmo tempo (sem sobrecarregar o servidor de imagens)
  const trabalhador = async () => {
    while (i < urls.length) {
      const url = urls[i++];
      try {
        if (!(await cache.match(url))) {
          const r = await fetch(url, { mode: "cors" });
          if (r.ok) await cache.put(url, r); else falhas++;
        }
      } catch { falhas++; }
      feitos++;
      if (feitos % 10 === 0) atualizar();
    }
  };
  await Promise.all(Array.from({ length: 6 }, trabalhador));
  atualizar();
  salvarOffline(MO_CHAVE_INFO, { em: Date.now(), n: urls.length - falhas });
  if (ptEl("mo-status")) {
    ptEl("mo-status").textContent = falhas
      ? `Pronto, mas ${falhas} imagens falharam (sinal fraco?). Toque em Salvar de novo para completar.`
      : "✔ Mapa salvo! Agora ele aparece mesmo sem sinal.";
  }
  if (ptEl("mo-baixar")) ptEl("mo-baixar").disabled = false;
}
