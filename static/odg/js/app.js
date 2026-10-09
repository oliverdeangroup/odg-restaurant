/* ODG-RESTAURANT as an app: service worker, "Install app" buttons, keep the screen on. */
(function () {
  "use strict";
  // 1. Service worker: makes the system installable and shows an offline screen.
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {}));
  }

  // 2. Install buttons ([data-install]) and the install box (#install-box).
  let prompt = null;
  const standalone = window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone;
  if (standalone) document.documentElement.classList.add("is-app");
  function showInstall(show) {
    document.querySelectorAll("[data-install]").forEach((b) => { b.hidden = !show; const li = b.closest("[data-install-item]"); if (li) li.hidden = !show; });
    const box = document.getElementById("install-box");
    if (box) box.hidden = !show;
  }
  showInstall(false);
  window.addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); prompt = e; if (!standalone) showInstall(true); });
  window.addEventListener("appinstalled", () => { prompt = null; showInstall(false); });
  document.addEventListener("click", async (e) => {
    const b = e.target.closest("[data-install]");
    if (!b || !prompt) return;
    e.preventDefault();
    prompt.prompt();
    await prompt.userChoice;
    prompt = null;
    showInstall(false);
  });

  // 3. Keep the screen on while a live work screen is open (bar, kitchen, waiter, Cassa, overview).
  const live = /^\/dashboard\/pos\/(bar|kitchen|overview|cassa|order|floor)?\/?/.test(location.pathname) && !/design/.test(location.pathname);
  let lock = null;
  async function keepAwake() {
    if (!live || !("wakeLock" in navigator) || document.hidden) return;
    try { lock = await navigator.wakeLock.request("screen"); } catch (_) { /* not allowed, e.g. battery saver */ }
  }
  document.addEventListener("visibilitychange", () => { if (!document.hidden && (!lock || lock.released)) keepAwake(); });
  keepAwake();
})();
