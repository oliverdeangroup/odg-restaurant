/* Waiter order screen: browse the menu, add items per guest, submit to bar & kitchen. */
(function () {
  "use strict";
  const O = window.ORDER, T = O.t;
  const data = JSON.parse(document.getElementById("menu-data").textContent);
  const cats = data.cats, prods = data.prods;
  const byId = Object.fromEntries(cats.map((c) => [c.id, c]));
  const $ = (id) => document.getElementById(id);
  const money = (v) => (window.ODG.money || "") + " " + Number(v).toFixed(2);
  const fmt = (s, ...a) => s.replace(/\{(\d)\}/g, (_, i) => a[i]);
  const KEY = "odg-cart-" + O.id;

  let cart = [];
  try { cart = JSON.parse(localStorage.getItem(KEY) || "[]"); } catch (_) { cart = []; }
  let guests = Math.max(O.guests, ...cart.map((l) => l.guest), 1);
  let guest = 1, current = null, query = "";

  function save() { try { localStorage.setItem(KEY, JSON.stringify(cart)); } catch (_) { /* full */ } }
  function station(cid) {
    let c = byId[cid];
    while (c) { if (c.station) return c.station; c = byId[c.parent_id]; }
    return "kitchen";
  }
  function el(tag, cls, text) { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
  function icon(name, size) {
    const s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    s.setAttribute("class", "ic"); s.setAttribute("width", size || 18); s.setAttribute("height", size || 18);
    const u = document.createElementNS("http://www.w3.org/2000/svg", "use"); u.setAttribute("href", "#i-" + name); s.appendChild(u);
    return s;
  }
  function descendants(cid) {
    const out = new Set([cid]); let grew = true;
    while (grew) { grew = false; cats.forEach((c) => { if (out.has(c.parent_id) && !out.has(c.id)) { out.add(c.id); grew = true; } }); }
    return out;
  }

  // ---------------------------------------------------------------- menu
  function renderMenu() {
    const crumbs = $("crumbs"); crumbs.innerHTML = "";
    const root = el("button", "", T.all); root.type = "button"; root.onclick = () => { current = null; renderMenu(); };
    crumbs.appendChild(root);
    const path = []; let c = byId[current];
    while (c) { path.unshift(c); c = byId[c.parent_id]; }
    path.forEach((p) => {
      crumbs.appendChild(document.createTextNode("›"));
      const b = el("button", "", p.name); b.type = "button"; b.onclick = () => { current = p.id; renderMenu(); };
      crumbs.appendChild(b);
    });
    const tiles = $("cat-tiles"); tiles.innerHTML = "";
    const pt = $("prod-tiles"); pt.innerHTML = "";
    let list;
    if (query) {
      const q = query.toLowerCase();
      list = prods.filter((p) => p.n.toLowerCase().includes(q) || (p.code && p.code.toLowerCase() === q));
    } else {
      cats.filter((x) => (x.parent_id || null) === current).sort((a, b) => a.order - b.order || a.name.localeCompare(b.name)).forEach((x) => {
        const b = el("button", "cat-tile " + station(x.id)); b.type = "button";
        b.appendChild(icon(station(x.id) === "bar" ? "glass" : "chef", 20)); b.appendChild(el("span", "", x.name));
        b.onclick = () => { current = x.id; renderMenu(); };
        tiles.appendChild(b);
      });
      list = current == null ? [] : prods.filter((p) => p.c === current);
      if (current != null && !list.length && !tiles.children.length) list = prods.filter((p) => descendants(current).has(p.c));
    }
    tiles.classList.toggle("hide", !tiles.children.length);
    list.forEach((p) => {
      const b = el("button", "prod-tile " + p.st); b.type = "button";
      b.appendChild(el("strong", "", p.n));
      if (p.o && p.o.length) b.appendChild(el("span", "opt", p.o.map((g) => g.name).join(" · ")));
      b.appendChild(el("span", "price", money(p.p)));
      const n = cart.filter((l) => l.product === p.id && l.guest === guest).reduce((a, l) => a + l.qty, 0);
      if (!p.a) { b.disabled = true; b.appendChild(el("span", "sold", T.soldOut)); }
      else if (n) b.appendChild(el("span", "added", n));
      b.onclick = () => choose(p);
      pt.appendChild(b);
    });
    $("no-prod").classList.toggle("hide", !(query && !list.length));
  }
  $("prod-search").addEventListener("input", (e) => { query = e.target.value.trim(); renderMenu(); });

  // ---------------------------------------------------------------- options modal
  let pending = null, qty = 1;
  function choose(p) {
    if (!p.o || !p.o.length) return add(p, 1, {}, "");
    pending = p; qty = 1;
    $("opt-title").textContent = p.n + " · " + money(p.p);
    $("opt-desc").textContent = p.d || "";
    $("opt-note").value = ""; $("opt-qty").textContent = "1"; $("opt-err").classList.add("hide");
    $("opt-guest").textContent = T.forGuest + ": " + (guest ? T.guest + " #" + guest : T.shared);
    const box = $("opt-groups"); box.innerHTML = "";
    p.o.forEach((g, gi) => {
      const wrap = el("div", "opt-group"); wrap.appendChild(el("label", "", g.name + (g.required ? " *" : "")));
      const ch = el("div", "opt-choices");
      g.choices.forEach((c) => {
        const l = el("label"); const i = document.createElement("input");
        i.type = "radio"; i.name = "g" + gi; i.value = c;
        l.appendChild(i); l.appendChild(el("span", "", c)); ch.appendChild(l);
        l.addEventListener("dblclick", () => { i.checked = true; $("opt-add").click(); });
      });
      wrap.appendChild(ch); box.appendChild(wrap);
    });
    window.odgOpenModal("opt-modal");
  }
  document.querySelectorAll("[data-opt-step]").forEach((b) => b.addEventListener("click", () => {
    qty = Math.max(1, Math.min(99, qty + Number(b.dataset.optStep))); $("opt-qty").textContent = qty;
  }));
  $("opt-add").addEventListener("click", () => {
    const p = pending; if (!p) return;
    const opts = {}; const missing = [];
    p.o.forEach((g, gi) => {
      const sel = document.querySelector(`#opt-groups input[name="g${gi}"]:checked`);
      if (sel) opts[g.name] = sel.value; else if (g.required) missing.push(g.name);
    });
    if (missing.length) { const e = $("opt-err"); e.textContent = fmt(T.choose, missing.join(", ")); e.classList.remove("hide"); return; }
    add(p, qty, opts, $("opt-note").value.trim());
    document.getElementById("opt-modal").classList.remove("open");
  });

  // ---------------------------------------------------------------- cart
  function add(p, n, opts, notes) {
    const sig = JSON.stringify([p.id, guest, opts, notes]);
    const line = cart.find((l) => JSON.stringify([l.product, l.guest, l.options, l.notes]) === sig);
    if (line) line.qty += n; else cart.push({ product: p.id, qty: n, guest: guest, options: opts, notes: notes });
    save(); renderCart(); renderMenu();
  }
  function renderGuests() {
    const box = $("guest-tabs"); box.innerHTML = "";
    for (let g = 0; g <= guests; g++) {
      const b = el("button", g === guest ? "on" : "", g ? T.guest + " #" + g : T.table); b.type = "button";
      const n = cart.filter((l) => l.guest === g).reduce((a, l) => a + l.qty, 0);
      if (n) b.appendChild(el("span", "n", "(" + n + ")"));
      b.onclick = () => { guest = g; renderGuests(); renderMenu(); };
      box.appendChild(b);
    }
    const plus = el("button", "", "+"); plus.type = "button"; plus.title = T.addGuest;
    plus.onclick = () => { guests += 1; guest = guests; renderGuests(); renderMenu(); };
    box.appendChild(plus);
  }
  function renderCart() {
    const box = $("cart"); box.innerHTML = "";
    const pmap = Object.fromEntries(prods.map((p) => [p.id, p]));
    cart = cart.filter((l) => pmap[l.product]);
    const groups = {};
    cart.forEach((l, i) => { (groups[l.guest] = groups[l.guest] || []).push([l, i]); });
    let total = 0, count = 0;
    Object.keys(groups).map(Number).sort((a, b) => a - b).forEach((g) => {
      const wrap = el("div", "cart-group");
      wrap.appendChild(el("h4", "", g ? T.guest + " #" + g : T.shared));
      groups[g].forEach(([l, i]) => {
        const p = pmap[l.product]; total += p.p * l.qty; count += l.qty;
        const row = el("div", "cart-line");
        const q = el("div", "q");
        const minus = el("button", "", "−"); minus.type = "button";
        minus.onclick = () => { l.qty -= 1; if (l.qty < 1) cart.splice(i, 1); save(); renderCart(); renderMenu(); };
        const plus = el("button", "", "+"); plus.type = "button";
        plus.onclick = () => { l.qty += 1; save(); renderCart(); renderMenu(); };
        q.appendChild(minus); q.appendChild(el("b", "", l.qty)); q.appendChild(plus);
        const info = el("div", "info"); info.appendChild(el("strong", "", p.n));
        const optText = Object.entries(l.options || {}).map(([k, v]) => v).join(" · ");
        if (optText) info.appendChild(el("small", "", optText));
        const note = document.createElement("input");
        note.className = "inp note-inp"; note.placeholder = T.note; note.value = l.notes || ""; note.maxLength = 200;
        note.oninput = () => { l.notes = note.value; save(); };
        info.appendChild(note);
        const st = el("span", "pill " + p.st, p.st === "bar" ? T.bar : p.st === "kitchen" ? T.kitchen : "—");
        row.appendChild(q); row.appendChild(info);
        const right = el("div", ""); right.style.textAlign = "right";
        right.appendChild(el("div", "money small", money(p.p * l.qty))); right.appendChild(st);
        row.appendChild(right);
        wrap.appendChild(row);
      });
      box.appendChild(wrap);
    });
    if (!cart.length) box.appendChild(el("p", "muted small", T.empty));
    $("cart-count").textContent = count;
    $("cart-total").textContent = count ? money(total) : "";
    $("submit-btn").disabled = !count;
    renderGuests();
  }

  $("submit-btn").addEventListener("click", async () => {
    const btn = $("submit-btn"); btn.disabled = true;
    try {
      const r = await fetch(O.submit, {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRFToken": window.ODG.csrf, "x-requested-with": "fetch" },
        body: JSON.stringify({ lines: cart }),
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok || !d.ok) { window.odgToast(d.error || T.error, "", null, "err"); btn.disabled = false; return; }
      cart = []; save(); renderCart(); renderMenu();
      const parts = []; if (d.bar) parts.push(T.bar + " " + d.bar); if (d.kitchen) parts.push(T.kitchen + " " + d.kitchen);
      window.odgToast(fmt(T.sent, d.count), parts.join(" · "));
      if (window.odgLive) window.odgLive.refresh();
    } catch (_) { window.odgToast(T.error, "", null, "err"); btn.disabled = false; }
  });

  renderMenu(); renderCart();
})();
