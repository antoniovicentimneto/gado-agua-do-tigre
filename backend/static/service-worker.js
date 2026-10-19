// Service worker do app: guarda a casca do app (HTML/CSS/JS) pra abrir sem internet.
const CACHE = "gado-agua-do-tigre-v59";
const ARQUIVOS = [
  "/",
  "/static/style.css?v=67",
  "/static/app.js?v=67",
  "/static/fila-offline.js?v=67",
  "/static/mangueira.js?v=67",
  "/static/planilha.js?v=67",
  "/static/venda-gancho.js?v=67",
  "/static/cria.js?v=67",
  "/static/campo.js?v=67",
  "/static/pastos-historico.js?v=67",
  "/static/pastos-indicadores.js?v=67",
  "/static/alertas.js?v=67",
  "/static/mapa-offline.js?v=67",
  "/static/pastos.js?v=67",
  "/static/financeiro.js?v=67",
  "/static/financeiro-notas.js?v=67",
  "/static/vendor/leaflet/leaflet.js",
  "/static/vendor/leaflet/leaflet.css",
  "/static/manifest.json",
  "/static/icon.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(ARQUIVOS)).then(() => self.skipWaiting())
  );
});

// Imagens de satélite do mapa ficam num cache próprio, que NÃO é apagado quando sai versão
// nova do app (o "mapa salvo pra usar sem sinal" sobrevive às atualizações).
const CACHE_MAPA = "gado-mapa-tiles";
const SERVIDOR_TILES = "server.arcgisonline.com";

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((nomes) =>
      Promise.all(nomes.filter((n) => n !== CACHE && n !== CACHE_MAPA).map((n) => caches.delete(n)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  // Chamadas à API: sempre tenta a rede, nunca serve cache (dados mudam o tempo todo).
  if (request.url.includes("/api/")) return;
  if (request.method !== "GET") return;

  // Mapa de satélite: usa o que está salvo no aparelho (rápido e funciona sem sinal);
  // o que ainda não está salvo vem da internet e fica guardado pra próxima vez.
  if (request.url.includes(SERVIDOR_TILES)) {
    event.respondWith(
      caches.open(CACHE_MAPA).then((cache) =>
        cache.match(request.url).then((salvo) => salvo || fetch(request).then((resposta) => {
          if (resposta.ok && resposta.type === "cors") cache.put(request.url, resposta.clone());
          return resposta;
        }))
      )
    );
    return;
  }
  // Outros sites (fontes, etc.): não passa pelo cache do app.
  if (new URL(request.url).origin !== self.location.origin) return;

  // Casca do app: tenta a rede primeiro (pra pegar atualizações), cai pro cache se offline.
  event.respondWith(
    fetch(request)
      .then((resposta) => {
        const copia = resposta.clone();
        caches.open(CACHE).then((cache) => cache.put(request, copia));
        return resposta;
      })
      .catch(() => caches.match(request).then((r) => r || caches.match("/")))
  );
});
