// Service worker do app: guarda a casca do app (HTML/CSS/JS) pra abrir sem internet.
const CACHE = "gado-agua-do-tigre-v20";
const ARQUIVOS = [
  "/",
  "/static/style.css?v=28",
  "/static/app.js?v=28",
  "/static/fila-offline.js?v=28",
  "/static/mangueira.js?v=28",
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
