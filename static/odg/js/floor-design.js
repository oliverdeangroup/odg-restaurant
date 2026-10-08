/* Floor designer: drag, resize, rotate tables and sections; save as JSON. */
(function () {
  "use strict";
  const F = window.FLOOR, T = F.t;
  const D = JSON.parse(document.getElementById("floor-data").textContent);
  const floor = document.getElementById("fd-floor"), props = document.getElementById("fd-props");
  const grid = D.grid || 20;
  let zoom = 1, sel = null, dirty = false, seq = 1;
  const tables = D.tables, sections = D.sections;

  floor.style.width = D.width + "px"; floor.style.height = D.height + "px";
  floor.style.backgroundSize = grid + "px " + grid + "px";
  const snap = (v) => Math.round(v / grid) * grid;
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  function setZoom(z) {
    zoom = Math.max(0.4, Math.min(1.6, z));
    floor.style.transform = "scale(" + zoom + ")"; floor.style.transformOrigin = "0 0";
    floor.parentElement.style.height = Math.min(D.height * zoom + 4, window.innerHeight - 200) + "px";
    document.getElementById("fd-zoom").textContent = Math.round(zoom * 100) + "%";
  }
  function fit() { const w = floor.parentElement.clientWidth - 4; setZoom(Math.min(1, w / D.width)); }

  function render() {
    floor.innerHTML = "";
    sections.forEach((s) => {
      const el = document.createElement("div");
      el.className = "zone" + (sel === s ? " sel" : "");
      Object.assign(el.style, { left: s.x + "px", top: s.y + "px", width: s.w + "px", height: s.h + "px", background: s.color });
      el.innerHTML = "<span>" + esc(s.name) + "</span><i class='rs'></i>";
      bind(el, s, "section");
      floor.appendChild(el);
    });
    tables.forEach((t) => {
      const el = document.createElement("div");
      el.className = "ftable st-free " + t.shape + (sel === t ? " sel" : "");
      Object.assign(el.style, { left: t.x + "px", top: t.y + "px", width: t.w + "px", height: t.h + "px", transform: t.rotation ? "rotate(" + t.rotation + "deg)" : "" });
      el.innerHTML = "<b>" + esc(t.number) + "</b><small>" + esc(t.seats) + " " + esc(T.seatsShort) + "</small><i class='rs'></i>";
      bind(el, t, "table");
      floor.appendChild(el);
    });
  }

  function bind(el, obj, kind) {
    el.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      const resize = e.target.classList.contains("rs");
      const sx = e.clientX, sy = e.clientY, ox = obj.x, oy = obj.y, ow = obj.w, oh = obj.h;
      let moved = false;
      select(obj, kind);
      const target = floor.querySelectorAll(kind === "table" ? ".ftable" : ".zone")[(kind === "table" ? tables : sections).indexOf(obj)];
      function move(ev) {
        const dx = (ev.clientX - sx) / zoom, dy = (ev.clientY - sy) / zoom;
        if (Math.abs(dx) + Math.abs(dy) > 2) moved = true;
        if (resize) {
          obj.w = Math.max(40, snap(ow + dx)); obj.h = Math.max(40, snap(oh + dy));
          if (kind === "table" && obj.shape === "round") obj.h = obj.w;
        } else {
          obj.x = Math.max(0, Math.min(D.width - obj.w, snap(ox + dx)));
          obj.y = Math.max(0, Math.min(D.height - obj.h, snap(oy + dy)));
        }
        Object.assign(target.style, { left: obj.x + "px", top: obj.y + "px", width: obj.w + "px", height: obj.h + "px" });
      }
      function up() {
        window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up);
        if (moved) { dirty = true; if (kind === "table") autoSection(obj); showProps(); }
      }
      window.addEventListener("pointermove", move); window.addEventListener("pointerup", up);
    });
  }
  function autoSection(t) {
    const cx = t.x + t.w / 2, cy = t.y + t.h / 2;
    const s = sections.find((z) => cx >= z.x && cx <= z.x + z.w && cy >= z.y && cy <= z.y + z.h);
    if (s) t.section = s.id;
  }
  function select(obj, kind) {
    sel = obj; sel._kind = kind;
    floor.querySelectorAll(".sel").forEach((x) => x.classList.remove("sel"));
    const list = kind === "table" ? tables : sections;
    const el = floor.querySelectorAll(kind === "table" ? ".ftable" : ".zone")[list.indexOf(obj)];
    if (el) el.classList.add("sel");
    showProps();
  }

  function field(label, html) { return "<div class='field'><label>" + esc(label) + "</label>" + html + "</div>"; }
  function showProps() {
    if (!sel) return;
    const o = sel;
    let h = "";
    if (o._kind === "table") {
      document.getElementById("fd-title").textContent = T.table + " " + o.number;
      h += "<div class='grid g2' style='gap:10px'>" + field(T.number, "<input class='inp' type='number' min='1' data-k='number' value='" + esc(o.number) + "'>")
        + field(T.seats, "<input class='inp' type='number' min='1' max='99' data-k='seats' value='" + esc(o.seats) + "'>") + "</div>";
      h += field(T.label, "<input class='inp' data-k='label' maxlength='30' value='" + esc(o.label) + "'>");
      h += field(T.shape, "<select class='inp' data-k='shape'><option value='rect'" + (o.shape === "rect" ? " selected" : "") + ">" + esc(T.rect) + "</option><option value='round'" + (o.shape === "round" ? " selected" : "") + ">" + esc(T.round) + "</option></select>");
      h += field(T.section, "<select class='inp' data-k='section'><option value=''>" + esc(T.none) + "</option>" + sections.map((s) => "<option value='" + esc(s.id) + "'" + (String(o.section) === String(s.id) ? " selected" : "") + ">" + esc(s.name) + "</option>").join("") + "</select>");
      h += "<div class='grid g3' style='gap:10px'>" + field(T.width, "<input class='inp' type='number' data-k='w' value='" + o.w + "'>") + field(T.height, "<input class='inp' type='number' data-k='h' value='" + o.h + "'>")
        + field(T.rotation, "<input class='inp' type='number' step='15' data-k='rotation' value='" + o.rotation + "'>") + "</div>";
      h += "<label class='field check'><input class='chk' type='checkbox' data-k='online'" + (o.online ? " checked" : "") + "> <span>" + esc(T.online) + "</span></label>";
    } else {
      document.getElementById("fd-title").textContent = T.section;
      h += field(T.name, "<input class='inp' data-k='name' maxlength='60' value='" + esc(o.name) + "'>");
      h += field(T.color, "<input class='inp' type='color' data-k='color' value='" + esc(o.color) + "'>");
      h += "<div class='grid g2' style='gap:10px'>" + field(T.width, "<input class='inp' type='number' data-k='w' value='" + o.w + "'>") + field(T.height, "<input class='inp' type='number' data-k='h' value='" + o.h + "'>") + "</div>";
    }
    h += "<button class='btn danger' type='button' id='fd-del'>" + esc(T.del) + "</button>";
    props.innerHTML = h;
    props.querySelectorAll("[data-k]").forEach((inp) => inp.addEventListener("input", () => {
      const k = inp.dataset.k;
      let v = inp.type === "checkbox" ? inp.checked : inp.value;
      if (["number", "seats", "w", "h", "rotation"].includes(k)) v = Number(v) || 0;
      o[k] = v;
      if (k === "shape" && v === "round") o.h = o.w;
      dirty = true; render();
      if (o._kind === "table") document.getElementById("fd-title").textContent = T.table + " " + o.number;
    }));
    document.getElementById("fd-del").addEventListener("click", () => {
      if (o._kind === "table") {
        if (o.busy) { window.odgToast(T.busy, "", null, "err"); return; }
        tables.splice(tables.indexOf(o), 1);
      } else {
        sections.splice(sections.indexOf(o), 1);
        tables.forEach((t) => { if (String(t.section) === String(o.id)) t.section = ""; });
      }
      sel = null; props.innerHTML = ""; dirty = true; render();
    });
  }

  document.querySelectorAll("[data-add]").forEach((b) => b.addEventListener("click", () => {
    const kind = b.dataset.add;
    const cx = snap((floor.parentElement.scrollLeft + 80) / zoom), cy = snap((floor.parentElement.scrollTop + 80) / zoom);
    if (kind === "section") {
      const s = { id: "n" + seq++, name: T.section + " " + (sections.length + 1), color: "#eef2f8", x: cx, y: cy, w: 400, h: 300 };
      sections.push(s); render(); select(s, "section");
    } else {
      const n = Math.max(0, ...tables.map((t) => Number(t.number) || 0)) + 1;
      const t = { id: "", number: n, label: "", section: "", shape: kind, seats: kind === "round" ? 2 : 4, x: cx, y: cy, w: 100, h: kind === "round" ? 100 : 90, rotation: 0, online: true };
      autoSection(t); tables.push(t); render(); select(t, "table");
    }
    dirty = true;
  }));
  document.querySelectorAll("[data-zoom]").forEach((b) => b.addEventListener("click", () => setZoom(zoom + Number(b.dataset.zoom) * 0.1)));

  document.getElementById("fd-save").addEventListener("click", async () => {
    const body = JSON.stringify({
      tables: tables.map(({ _kind, busy, ...t }) => t),
      sections: sections.map(({ _kind, ...s }) => s),
    });
    const r = await fetch(F.save, { method: "POST", body, credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": window.ODG.csrf } });
    const d = await r.json().catch(() => ({}));
    if (!r.ok || !d.ok) { window.odgToast(d.error || "Error", "", null, "err"); return; }
    dirty = false;
    window.location = F.back;
  });
  window.addEventListener("beforeunload", (e) => { if (dirty) { e.preventDefault(); e.returnValue = T.unsaved; } });

  render(); fit();
})();
