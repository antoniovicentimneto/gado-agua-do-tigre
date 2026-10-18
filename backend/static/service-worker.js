// Service worker do app: guarda a casca do app (HTML/CSS/JS) pra abrir sem internet.
const CACHE = "gado-agua-do-tigre-v55";
const ARQUIVOS = [
  "/",
  "/static/style.css?v=63",
  "/static/app.js?v=63",
  "/static/fila-offline.js?v=63",
  "/static/mangueira.js?v=63",
  "/static/planilha.js?v=63",
  "/static/venda-gancho.js?v=63",
  "/static/cria.js?v=63",
  "/static/campo.js?v=63",
  "/static/pastos-historico.js?v=63",
  "/static/pastos.js?v=63",
  "/static/financeiro.js?v=63",
  "/static/financeiro-notas.js?v=63",
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

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((nomes) =>
      Promise.all(nomes.filter((n) => n !== CACHE).map((n) => caches.delete(n)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  // Chamadas à API: sempre tenta a rede, nunca serve cache (dados mudam o tempo todo).
  if (request.url.includes("/api/")) return;
  if (request.method !== "GET") return;

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
