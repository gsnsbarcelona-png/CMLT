// Service worker minimo: hace la app instalable (PWA) y permite abrir la
// interfaz sin conexion. Red primero para la interfaz (asi siempre se ve la
// version mas nueva), cache solo como respaldo. La API (/api/...) nunca se
// cachea: los datos y la publicacion siempre van en vivo al servidor.
const CACHE = "tweet-automation-v1";
const SHELL = ["/", "/static/app.js", "/static/styles.css", "/static/manifest.webmanifest"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(SHELL))
      .catch(() => {}) // sin sesion "/" redirige a /login: no bloquea la instalacion
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
  event.respondWith(
    fetch(event.request)
      .then((res) => {
        if (res.ok && !res.redirected) {
          const copy = res.clone();
          caches.open(CACHE).then((cache) => cache.put(event.request, copy));
        }
        return res;
      })
      .catch(() => caches.match(event.request).then((cached) => cached || Response.error()))
  );
});
