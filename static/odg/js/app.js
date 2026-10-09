/* ODG-RESTAURANT as an app: service worker, "Install app" buttons, keep the screen on. */
(function () {
  "use strict";
  // 1. Service worker: makes the system installable and shows an offline screen.
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {}));
  }

  // 2. Install. The browser's install event is caught early in the page head
  //    (window.__odgInstall, see core/_app_head.html), so it is never missed.
  const standalone = window.matchMedia("(display-mode: standalone)").matches ||
    window.matchMedia("(display-mode: fullscreen)").matches || window.navigator.standalone === true;
  if (standalone) document.documentElement.classList.add("is-app");
  document.querySelectorAll("[data-install]").forEach((b) => { b.hidden = standalone; });
  const box = document.getElementById("install-box");
  if (box) box.hidden = standalone;

  function browser() {
    const ua = navigator.userAgent;
    if (/iPad|iPhone|iPod/.test(ua) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1)) return "ios";
    if (/Electron\/|Claude\//.test(ua)) return "other";  // built-in app browsers cannot install apps
    if (/SamsungBrowser/.test(ua)) return "samsung";
    if (/Android/.test(ua)) return "android";
    if (/Edg\//.test(ua)) return "edge";
    if (/Chrome\//.test(ua) && !/OPR\//.test(ua)) return "chrome";
    return "other";
  }
  function help(done) {
    const m = document.getElementById("install-help");
    if (!m) return;
    const b = browser();
    m.querySelectorAll("[data-ih]").forEach((p) => { p.hidden = p.dataset.ih !== b; });
    m.querySelector(".ih-done").hidden = !done;
    m.querySelector(".ih-steps").hidden = !!done;
    m.classList.add("open");
  }
  window.addEventListener("appinstalled", () => {
    window.__odgInstall = null;
    document.querySelectorAll("[data-install]").forEach((b) => { b.hidden = true; });
    if (box) box.hidden = true;
    help(true);
  });
  document.addEventListener("click", async (e) => {
    const b = e.target.closest("[data-install]");
    if (!b) return;
    e.preventDefault();
    const ev = window.__odgInstall;
    if (!ev) { help(false); return; }
    window.__odgInstall = null;  // the browser allows one prompt per event
    try {
      ev.prompt();
      const choice = await Promise.race([ev.userChoice, new Promise((ok) => setTimeout(() => ok({ outcome: "timeout" }), 60000))]);
      if (choice.outcome !== "accepted") help(false);
    } catch (_) {
      help(false);
    }
  });

  // Close the install help (pages without dashboard.js, e.g. /app/)
  document.addEventListener("click", (e) => {
    const m = e.target.closest("#install-help");
    if (m && (e.target === m || e.target.closest(".modal-close"))) m.classList.remove("open");
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
