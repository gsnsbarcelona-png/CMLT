// Service worker minimo: hace la app instalable (PWA) y permite abrir la
// interfaz sin conexion. Red primero para la interfaz (asi siempre se ve la
// version mas nueva); si la red tarda mas de 3 s (servidor de Render
// durmiendo) se abre YA la copia cacheada mientras la red actualiza la cache
// para la proxima vez. La API (/api/...) nunca se cachea: los datos y la
// publicacion siempre van en vivo al servidor.
const CACHE = "tweet-automation-v7";
const NETWORK_TIMEOUT_MS = 3000;
const SHELL = ["/", "/static/app.js", "/static/styles.css", "/static/manifest.webmanifest"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(SHELL))
      .catch(() => {}) // sin sesión "/" redirige a /login: no bloquea la instalación
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== self.location.origin || url.pathname.startsWith("/api/")) {
    return;
  }
  event.respondWith(networkFirst(event.request));
});

function networkFirst(request) {
  // cache: "no-cache" evita que la cache HTTP del navegador sirva un app.js viejo.
  const network = fetch(request, { cache: "no-cache" }).then((res) => {
    if (res.ok && !res.redirected) {
      const copy = res.clone();
      caches.open(CACHE).then((cache) => cache.put(request, copy));
    }
    return res;
  });
  return caches.match(request).then((cached) => {
    if (!cached) return network.catch(() => Response.error());
    const timeout = new Promise((resolve) => setTimeout(() => resolve(cached), NETWORK_TIMEOUT_MS));
    return Promise.race([network.catch(() => cached), timeout]);
  });
}
