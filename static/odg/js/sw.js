/* ODG-RESTAURANT service worker (version __VERSION__).
 *
 * - Pages and live data always come from the server (the POS must be live,
 *   and private pages are never stored on the device).
 * - Static files (CSS, JavaScript, icons, fonts) are cached so the app opens fast.
 * - Without a connection a friendly "offline" screen is shown, which retries by itself.
 */
const CACHE = "odg-static-__VERSION__";
const OFFLINE = "__OFFLINE__";

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll([OFFLINE])).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k.startsWith("odg-static-") && k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) {
    if (url.hostname === "fonts.gstatic.com" || url.hostname === "fonts.googleapis.com") {
      event.respondWith(caches.open(CACHE).then((c) => c.match(req).then((hit) => hit || fetch(req).then((r) => { c.put(req, r.clone()); return r; }))));
    }
    return;
  }
  if (url.pathname.startsWith("/static/")) {
    event.respondWith(caches.open(CACHE).then((c) => c.match(req).then((hit) => hit || fetch(req).then((r) => {
      if (r.ok && !url.pathname.endsWith(".webm")) c.put(req, r.clone());
      return r;
    }))));
    return;
  }
  if (req.mode === "navigate") {
    event.respondWith(fetch(req).catch(() => caches.match(OFFLINE)));
  }
});
