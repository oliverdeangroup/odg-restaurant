/* ODG-RESTAURANT live sync.
 *
 * Polls /dashboard/pos/live/ every few seconds. When the change counter goes
 * up, every element with data-live-src="url" is re-loaded from the server.
 * New notifications (e.g. "Table 4: ready to pick up") appear as a toast with
 * a short sound. Elements with data-since="<ms>" show a running timer.
 */
(function () {
  "use strict";
  const cfg = window.ODG || {};
  if (!cfg.live) return;
  let version = null, lastNote = null, fails = 0, timer = null, busy = false;
  const dot = document.getElementById("live-dot");
  const badge = document.getElementById("bell-badge");
  let soundOn = cfg.sound;
  try { if (localStorage.getItem("odgSound")) soundOn = localStorage.getItem("odgSound") === "on"; } catch (_) { /* private mode */ }

  // ---------------------------------------------------------------- sound
  let ctx = null;
  function beep(kind) {
    if (!soundOn) return;
    try {
      ctx = ctx || new (window.AudioContext || window.webkitAudioContext)();
      const notes = kind === "pickup" ? [880, 1175] : [660, 880];
      notes.forEach((f, i) => {
        const o = ctx.createOscillator(), g = ctx.createGain();
        o.type = "sine"; o.frequency.value = f;
        g.gain.setValueAtTime(0.0001, ctx.currentTime + i * 0.18);
        g.gain.exponentialRampToValueAtTime(0.25, ctx.currentTime + i * 0.18 + 0.02);
        g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + i * 0.18 + 0.16);
        o.connect(g).connect(ctx.destination);
        o.start(ctx.currentTime + i * 0.18); o.stop(ctx.currentTime + i * 0.18 + 0.2);
      });
    } catch (_) { /* no audio */ }
  }
  document.querySelectorAll("[data-sound-toggle]").forEach((a) => {
    const label = a.querySelector("[data-sound-label]");
    const show = () => { if (label) label.textContent = soundOn ? cfg.t.soundOn : cfg.t.soundOff; };
    show();
    a.addEventListener("click", (e) => {
      e.preventDefault(); soundOn = !soundOn;
      try { localStorage.setItem("odgSound", soundOn ? "on" : "off"); } catch (_) { /* ignore */ }
      show(); if (soundOn) beep();
    });
  });

  // ---------------------------------------------------------------- toasts
  window.odgToast = function (title, message, link, kind) {
    const box = document.getElementById("toasts");
    if (!box) return;
    const el = document.createElement(link ? "a" : "div");
    el.className = "toast " + (kind || "");
    if (link) el.href = link;
    const strong = document.createElement("strong"); strong.textContent = title; el.appendChild(strong);
    if (message) { const s = document.createElement("span"); s.textContent = message; el.appendChild(s); }
    box.appendChild(el);
    setTimeout(() => el.classList.add("show"), 10);
    setTimeout(() => { el.classList.remove("show"); setTimeout(() => el.remove(), 400); }, kind === "pickup" ? 12000 : 6000);
  };

  // ---------------------------------------------------------------- parts
  function holding(el) {
    if (el.dataset.dirty === "1") return true;
    const a = document.activeElement;
    return a && el.contains(a) && /^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName);
  }
  async function refreshParts(force) {
    const parts = document.querySelectorAll("[data-live-src]");
    for (const el of parts) {
      if (!force && holding(el)) continue;
      try {
        const r = await fetch(el.dataset.liveSrc, { headers: { "x-requested-with": "fetch" }, credentials: "same-origin" });
        if (!r.ok) continue;
        const html = await r.text();
        if (html !== el.dataset.lastHtml) {
          el.dataset.lastHtml = html;
          el.innerHTML = html;
          el.dispatchEvent(new CustomEvent("live:updated", { bubbles: true }));
        }
      } catch (_) { /* next round */ }
    }
    tick();
  }
  window.odgLive = { refresh: () => refreshParts(true) };

  // ---------------------------------------------------------------- polling
  async function poll() {
    if (busy) return schedule();
    busy = true;
    try {
      const r = await fetch(cfg.live + "?n=" + (lastNote || 0), { headers: { "x-requested-with": "fetch" }, credentials: "same-origin" });
      if (r.redirected || r.status === 403 || r.status === 302) { location.reload(); return; }
      const d = await r.json();
      if (version !== null && d.v !== version) await refreshParts(false);
      version = d.v;
      if (lastNote !== null) {
        (d.notes || []).forEach((n) => { window.odgToast(n.title, n.message, n.link, n.category); beep(n.category); });
      }
      lastNote = d.last;
      if (badge) { badge.textContent = d.unread; badge.hidden = !d.unread; }
      fails = 0;
      if (dot) { dot.classList.remove("off"); dot.title = ""; }
    } catch (_) {
      fails += 1;
      if (dot && fails > 1) { dot.classList.add("off"); dot.title = cfg.t.offline; }
    } finally {
      busy = false;
      schedule();
    }
  }
  function schedule() {
    clearTimeout(timer);
    const base = Math.max(2, cfg.every || 3) * 1000;
    timer = setTimeout(poll, document.hidden ? base * 4 : base * Math.min(1 + fails, 5));
  }
  document.addEventListener("visibilitychange", () => { if (!document.hidden) poll(); });
  poll();

  // ---------------------------------------------------------------- timers
  function tick() {
    const now = Date.now();
    document.querySelectorAll("[data-since]").forEach((el) => {
      const secs = Math.max(0, Math.floor((now - Number(el.dataset.since)) / 1000));
      const m = Math.floor(secs / 60), s = secs % 60;
      el.textContent = m >= 60 ? Math.floor(m / 60) + "h " + String(m % 60).padStart(2, "0") + "m" : m + ":" + String(s).padStart(2, "0");
      if (el.dataset.due) {
        const late = now - Number(el.dataset.due);
        const card = el.closest("[data-ticket]") || el;
        card.classList.toggle("is-due", late > 0 && late <= Number(el.dataset.grace || 300000));
        card.classList.toggle("is-late", late > Number(el.dataset.grace || 300000));
      }
    });
  }
  setInterval(tick, 1000);
  tick();

  // ---------------------------------------------------------------- AJAX forms inside live parts
  // <form data-ajax> posts in the background and refreshes the live parts.
  document.addEventListener("submit", async (e) => {
    const f = e.target.closest("form[data-ajax]");
    if (!f || e.defaultPrevented) return;
    e.preventDefault();
    const fd = new FormData(f);
    if (e.submitter && e.submitter.name) fd.append(e.submitter.name, e.submitter.value);
    f.classList.add("sending");
    try {
      // f.action would return a field named "action" (our buttons are), so read the attribute.
      const r = await fetch(f.getAttribute("action") || location.href, { method: "POST", body: fd, headers: { "x-requested-with": "fetch" }, credentials: "same-origin" });
      if (!r.ok) {
        let msg = r.statusText;
        try { msg = (await r.json()).error || msg; } catch (_) { /* not json */ }
        window.odgToast(msg, "", null, "err");
      }
    } catch (_) { window.odgToast(cfg.t.offline, "", null, "err"); }
    f.classList.remove("sending");
    await refreshParts(true);
  });
})();
