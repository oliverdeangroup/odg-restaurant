/* ODG-RESTAURANT drag & drop builder (Elementor style).
 * Layout: {sections: [{id, layout, style, columns: [{widgets: [{id, type, data}]}]}]}
 * The server checks and cleans everything again (website/builder.py).
 */
(function () {
  "use strict";
  const SPEC = JSON.parse(document.getElementById("builder-spec").textContent);
  let layout = JSON.parse(document.getElementById("builder-layout").textContent) || {};
  if (!Array.isArray(layout.sections)) layout = { sections: [] };
  const T = window.BUILDER_T;
  const LAYOUTS = Object.fromEntries(SPEC.layouts);
  const canvas = document.getElementById("b-canvas");
  const panel = document.getElementById("b-settings");
  const input = document.getElementById("layout-input");
  let sel = null; // a section or a widget object

  const uid = (p) => p + Math.random().toString(36).slice(2, 10);
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const clone = (o) => JSON.parse(JSON.stringify(o));
  function icon(name, size) { return `<svg class="ic" width="${size || 16}" height="${size || 16}" aria-hidden="true"><use href="#i-${name}"></use></svg>`; }

  const DEFAULTS = {
    heading: { text: "Heading", level: "h2", align: "left", sub: "" },
    text: { html: "<p>Write your text here.</p>", align: "left" },
    image: { src: "", alt: "", link: "", caption: "", rounded: true, width: "100" },
    button: { text: "Book a table", link: "/reservations/", style: "primary", align: "left", new_tab: false },
    hero: { title: "Welcome", subtitle: "", button_text: "Book a table", button_link: "/reservations/", button2_text: "", button2_link: "", image: "", overlay: 45, height: "md", align: "center" },
    spacer: { height: 40 }, divider: { style: "line" },
    icon_box: { icon: "star", title: "Title", text: "Short text", align: "center" },
    gallery: { images: [], columns: "3" }, video: { url: "", caption: "" }, map: { query: "", height: 320 },
    reviews: { items: [{ name: "Guest", rating: 5, text: "Great food and friendly service!", source: "Google" }], title: "", columns: "3" },
    menu: { categories: [], show_prices: true, show_images: true, show_descriptions: true, columns: "2", title: "" },
    reservation: { title: "Book a table", text: "" }, hours: { title: "Opening hours" },
    contact: { title: "Contact", show_social: true }, social: { align: "left" }, html: { code: "<div>\n  \n</div>" },
  };
  function newWidget(type) { return { id: uid("w"), type, data: clone(DEFAULTS[type] || {}) }; }
  function newSection(lay) {
    return { id: uid("s"), layout: lay, style: { bg: "", image: "", overlay: 0, padding: "md", width: "boxed", align: "left", dark: false, anchor: "" },
      columns: LAYOUTS[lay].map(() => ({ widgets: [] })) };
  }

  // ---------------------------------------------------------------- palette
  const pal = document.getElementById("b-palette");
  Object.entries(SPEC.widgets).forEach(([type, w]) => {
    const d = document.createElement("div");
    d.className = "b-wtile"; d.dataset.type = type;
    d.innerHTML = icon(w.icon, 20) + "<span>" + esc(w.label) + "</span>";
    d.addEventListener("click", () => {
      // Click = add to the selected section (first column) or a new section.
      let sec = sel && sel.columns ? sel : layout.sections.find((s) => s.columns.some((c) => c.widgets.includes(sel)));
      if (!sec) { sec = newSection("1"); layout.sections.push(sec); }
      const w2 = newWidget(type);
      const col = sec.columns.find((c) => c.widgets.includes(sel)) || sec.columns[0];
      col.widgets.push(w2); sel = w2; render(); settings();
    });
    pal.appendChild(d);
  });
  new Sortable(pal, { group: { name: "widgets", pull: "clone", put: false }, sort: false, animation: 120 });
  const lays = document.getElementById("b-layouts");
  SPEC.layouts.forEach(([key, spans]) => {
    const b = document.createElement("button");
    b.type = "button"; b.className = "b-lay"; b.title = key;
    b.innerHTML = spans.map((s) => `<i style="flex:${s}"></i>`).join("");
    b.addEventListener("click", () => { const s = newSection(key); layout.sections.push(s); sel = s; render(); settings(); s && canvas.lastElementChild.scrollIntoView({ behavior: "smooth", block: "center" }); });
    lays.appendChild(b);
  });

  // ---------------------------------------------------------------- previews
  function preview(w) {
    const d = w.data || {};
    switch (w.type) {
      case "heading": return `${d.sub ? `<div class="pv-sub" style="text-align:${d.align}">${esc(d.sub)}</div>` : ""}<${d.level} style="text-align:${d.align}">${esc(d.text)}</${d.level}>`;
      case "text": return `<div class="pv-text" style="text-align:${d.align}">${d.html || ""}</div>`;
      case "image": return d.src ? `<img class="pv-img" src="${esc(d.src)}" alt="" style="width:${d.width}%;${d.rounded ? "" : "border-radius:0"}">` : `<div class="pv-ph">${icon("image", 22)}</div>`;
      case "button": return `<div style="text-align:${d.align}"><span class="pv-btn ${esc(d.style)}">${esc(d.text)}</span></div>`;
      case "hero": return `<div class="pv-hero" style="${d.image ? `background-image:linear-gradient(rgba(0,0,0,${(d.overlay || 0) / 100}),rgba(0,0,0,${(d.overlay || 0) / 100})),url('${esc(d.image)}')` : ""};text-align:${d.align}"><h2>${esc(d.title)}</h2>${d.subtitle ? `<p>${esc(d.subtitle)}</p>` : ""}${d.button_text ? `<p><span class="pv-btn">${esc(d.button_text)}</span></p>` : ""}</div>`;
      case "spacer": return `<div style="height:${Math.min(d.height || 0, 200)}px;background:repeating-linear-gradient(90deg,transparent 0 6px,rgba(0,0,0,.06) 6px 12px);border-radius:4px"></div>`;
      case "divider": return `<hr style="border:0;border-top:2px ${d.style === "dots" ? "dotted" : "solid"} rgba(0,0,0,.18);margin:6px 0">`;
      case "icon_box": return `<div style="text-align:${d.align}">${icon(d.icon, 28)}<h4>${esc(d.title)}</h4><div class="pv-text">${esc(d.text)}</div></div>`;
      case "gallery": return d.images && d.images.length ? `<div class="pv-grid" style="grid-template-columns:repeat(${d.columns},1fr)">${d.images.slice(0, 8).map((i) => `<img class="pv-img" style="height:70px" src="${esc(i.src)}" alt="">`).join("")}</div>` : `<div class="pv-ph">${icon("grid", 22)} ${esc(T.image)}</div>`;
      case "video": return `<div class="pv-ph">${icon("play", 26)}&nbsp;${esc(d.url || "YouTube / Vimeo")}</div>`;
      case "map": return `<div class="pv-ph" style="height:${Math.min(d.height || 200, 220)}px">${icon("pin", 22)}&nbsp;${esc(d.query || T.map)}</div>`;
      case "reviews": return `${d.title ? `<h3>${esc(d.title)}</h3>` : ""}<div class="pv-grid" style="grid-template-columns:repeat(${Math.min(d.columns, (d.items || []).length || 1)},1fr)">${(d.items || []).map((r) => `<div class="pv-box"><div class="pv-stars">${"★".repeat(r.rating || 5)}</div>${esc((r.text || "").slice(0, 90))}<br><b>${esc(r.name)}</b></div>`).join("")}</div>`;
      case "menu": {
        const names = (d.categories || []).map((id) => (SPEC.categories.find((c) => c.id === id) || {}).name).filter(Boolean);
        return `${d.title ? `<h3>${esc(d.title)}</h3>` : ""}<div class="pv-box">${icon("list", 16)} ${esc(names.length ? names.join(", ") : T.menuAll)}</div>`;
      }
      case "reservation": return `<h3>${esc(d.title)}</h3><div class="pv-box">${icon("calendar", 16)} ${esc(T.reservation)}</div>`;
      case "hours": return `${d.title ? `<h4>${esc(d.title)}</h4>` : ""}<div class="pv-box">${icon("clock", 16)} ${esc(T.hours)}</div>`;
      case "contact": return `${d.title ? `<h4>${esc(d.title)}</h4>` : ""}<div class="pv-box">${icon("phone", 16)} ${esc(T.contact)}</div>`;
      case "social": return `<div class="pv-box" style="text-align:${d.align}">${icon("facebook", 16)} ${icon("instagram", 16)} ${esc(T.social)}</div>`;
      case "html": return `<div class="pv-box"><code style="white-space:pre-wrap;font-size:12px">${esc((d.code || "").slice(0, 160))}</code></div>`;
    }
    return "";
  }

  // ---------------------------------------------------------------- canvas
  function render() {
    canvas.innerHTML = "";
    if (!layout.sections.length) canvas.innerHTML = `<div class="b-empty muted">${esc(T.empty)}</div>`;
    layout.sections.forEach((s) => {
      const st = s.style || {};
      const el = document.createElement("div");
      el.className = `b-sec pad-${st.padding || "md"}${st.dark ? " dark" : ""}${sel === s ? " sel" : ""}`;
      el.dataset.sid = s.id;
      if (st.bg) el.style.backgroundColor = st.bg;
      if (st.image) el.style.backgroundImage = `url('${st.image.replace(/'/g, "")}')`;
      el.innerHTML = `<div class="b-sec-bar"><button type="button" class="b-handle" title="${esc(T.section)}">${icon("drag", 14)}</button>`
        + `<button type="button" data-act="up" title="${esc(T.up)}">${icon("up", 14)}</button><button type="button" data-act="down" title="${esc(T.down)}">${icon("down", 14)}</button>`
        + `<button type="button" data-act="edit" title="${esc(T.settings)}">${icon("settings", 14)}</button><button type="button" data-act="dup" title="${esc(T.dup)}">${icon("layers", 14)}</button>`
        + `<button type="button" data-act="del" title="${esc(T.del)}">${icon("trash", 14)}</button></div>`
        + (st.image && st.overlay ? `<div class="b-ov" style="opacity:${st.overlay / 100}"></div>` : "");
      const inner = document.createElement("div");
      inner.className = "b-sec-in";
      inner.style.gridTemplateColumns = LAYOUTS[s.layout].map((n) => n + "fr").join(" ");
      s.columns.forEach((c) => {
        const col = document.createElement("div");
        col.className = "b-col"; col.dataset.empty = T.drop;
        c.widgets.forEach((w) => {
          const we = document.createElement("div");
          we.className = "b-w" + (sel === w ? " sel" : ""); we.dataset.wid = w.id;
          we.innerHTML = `<div class="b-w-tag">${icon(SPEC.widgets[w.type].icon, 11)} ${esc(SPEC.widgets[w.type].label)}</div>${preview(w)}`
            + `<div class="b-w-bar"><button type="button" data-wact="dup" title="${esc(T.dup)}">${icon("layers", 13)}</button><button type="button" data-wact="del" title="${esc(T.del)}">${icon("trash", 13)}</button></div>`;
          we.addEventListener("click", (e) => {
            e.stopPropagation();
            const act = e.target.closest("[data-wact]");
            if (act && act.dataset.wact === "del") { c.widgets.splice(c.widgets.indexOf(w), 1); if (sel === w) sel = null; render(); settings(); return; }
            if (act && act.dataset.wact === "dup") { const copy = clone(w); copy.id = uid("w"); c.widgets.splice(c.widgets.indexOf(w) + 1, 0, copy); sel = copy; render(); settings(); return; }
            sel = w; render(); settings();
          });
          col.appendChild(we);
        });
        inner.appendChild(col);
        new Sortable(col, { group: "widgets", animation: 140, ghostClass: "b-sortghost", onEnd: sync, onAdd: (e) => {
          if (e.item.dataset.type) { e.item.dataset.newType = e.item.dataset.type; }
          sync();
        } });
      });
      el.appendChild(inner);
      el.addEventListener("click", (e) => {
        const act = e.target.closest("[data-act]");
        const i = layout.sections.indexOf(s);
        if (act) {
          e.stopPropagation();
          if (act.dataset.act === "del") { if (!confirm(T.confirmDel)) return; layout.sections.splice(i, 1); sel = null; }
          if (act.dataset.act === "dup") { const copy = clone(s); copy.id = uid("s"); copy.columns.forEach((c) => c.widgets.forEach((w) => { w.id = uid("w"); })); layout.sections.splice(i + 1, 0, copy); sel = copy; }
          if (act.dataset.act === "up" && i > 0) layout.sections.splice(i - 1, 0, layout.sections.splice(i, 1)[0]);
          if (act.dataset.act === "down" && i < layout.sections.length - 1) layout.sections.splice(i + 1, 0, layout.sections.splice(i, 1)[0]);
          if (act.dataset.act === "edit") sel = s;
          render(); settings(); return;
        }
        if (e.target === el || e.target === inner || e.target.classList.contains("b-col")) { sel = s; render(); settings(); }
      });
      canvas.appendChild(el);
    });
    new Sortable(canvas, { handle: ".b-handle", draggable: ".b-sec", animation: 160, onEnd: sync });
    input.value = JSON.stringify(layout);
  }

  // Rebuild the model from the DOM after a drag.
  function sync() {
    const widgets = {}, sections = {};
    layout.sections.forEach((s) => { sections[s.id] = s; s.columns.forEach((c) => c.widgets.forEach((w) => { widgets[w.id] = w; })); });
    const out = [];
    canvas.querySelectorAll(":scope > .b-sec").forEach((se) => {
      const s = sections[se.dataset.sid]; if (!s) return;
      se.querySelectorAll(":scope > .b-sec-in > .b-col").forEach((ce, i) => {
        s.columns[i].widgets = Array.from(ce.children).map((we) => {
          if (we.dataset.newType) { const w = newWidget(we.dataset.newType); sel = w; return w; }
          return widgets[we.dataset.wid];
        }).filter(Boolean);
      });
      out.push(s);
    });
    layout.sections = out;
    render(); settings();
  }
  canvas.addEventListener("click", (e) => { if (e.target === canvas) { sel = null; render(); settings(); } });

  // ---------------------------------------------------------------- settings panel
  function fieldWrap(label, inner) { return `<div class="field"><label>${esc(label)}</label>${inner}</div>`; }
  function choiceLabel(v) { return SPEC.choices[v] || T[v] || v; }

  function settings() {
    if (!sel) { panel.innerHTML = `<div class="b-empty muted small">${esc(panel.dataset.empty || "")}</div>`; return; }
    if (sel.columns) return sectionSettings(sel);
    const w = sel, spec = SPEC.widgets[w.type];
    panel.innerHTML = `<div class="b-set-head"><span>${icon(spec.icon, 16)} ${esc(spec.label)}</span></div><div class="b-set-body" id="b-form"></div>`;
    const form = panel.querySelector("#b-form");
    Object.entries(spec.fields).forEach(([name, kind]) => form.appendChild(control(w, name, kind)));
  }

  function control(w, name, kind) {
    const d = w.data;
    const label = SPEC.fields[name] || name;
    const box = document.createElement("div");
    const changed = () => { renderKeep(); };
    if (kind === "str" || kind === "url") {
      box.innerHTML = fieldWrap(label, `<input class="inp" value="${esc(d[name])}">`);
      box.querySelector("input").addEventListener("input", (e) => { d[name] = e.target.value; changed(); });
    } else if (kind === "long") {
      box.innerHTML = fieldWrap(label, `<textarea class="inp" rows="3">${esc(d[name])}</textarea>`);
      box.querySelector("textarea").addEventListener("input", (e) => { d[name] = e.target.value; changed(); });
    } else if (kind === "int") {
      box.innerHTML = fieldWrap(label, `<input class="inp" type="number" min="0" value="${esc(d[name])}">`);
      box.querySelector("input").addEventListener("input", (e) => { d[name] = Number(e.target.value) || 0; changed(); });
    } else if (kind === "bool") {
      box.innerHTML = `<label class="field check"><input class="chk" type="checkbox" ${d[name] ? "checked" : ""}> <span>${esc(label)}</span></label>`;
      box.querySelector("input").addEventListener("change", (e) => { d[name] = e.target.checked; changed(); });
    } else if (kind.startsWith("choice:")) {
      const opts = kind.slice(7).split("|");
      box.innerHTML = fieldWrap(label, `<select class="inp">${opts.map((o) => `<option value="${esc(o)}" ${String(d[name]) === o ? "selected" : ""}>${esc(name === "level" ? o.toUpperCase() : choiceLabel(o))}</option>`).join("")}</select>`);
      box.querySelector("select").addEventListener("change", (e) => { d[name] = e.target.value; changed(); });
    } else if (kind === "img") {
      box.innerHTML = fieldWrap(label, `<div class="b-img-pick">${d[name] ? `<img src="${esc(d[name])}" alt="">` : ""}<button type="button" class="btn sm">${esc(T.choose)}</button>${d[name] ? `<button type="button" class="btn sm ghost danger">${esc(T.remove)}</button>` : ""}</div>`);
      const btns = box.querySelectorAll("button");
      btns[0].addEventListener("click", () => pickImage((url) => { d[name] = url; render(); settings(); }));
      if (btns[1]) btns[1].addEventListener("click", () => { d[name] = ""; render(); settings(); });
    } else if (kind === "html") {
      if (w.type === "html") {
        box.innerHTML = fieldWrap(label, `<textarea class="inp code-area" style="min-height:220px" spellcheck="false">${esc(d[name])}</textarea>`);
        box.querySelector("textarea").addEventListener("input", (e) => { d[name] = e.target.value; changed(); });
      } else {
        box.innerHTML = fieldWrap(label, `<div class="b-rte"><div class="b-rte-bar"><button type="button" data-cmd="bold" title="${esc(T.bold)}">B</button><button type="button" data-cmd="italic" title="${esc(T.italic)}"><i>I</i></button><button type="button" data-cmd="h3" title="${esc(T.h3)}">H3</button><button type="button" data-cmd="insertUnorderedList" title="${esc(T.list)}">•</button><button type="button" data-cmd="createLink" title="${esc(T.link)}">🔗</button><button type="button" data-cmd="removeFormat">⨯</button></div><div class="b-rte-area" contenteditable="true">${d[name] || ""}</div></div>`);
        const area = box.querySelector(".b-rte-area");
        area.addEventListener("input", () => { d[name] = area.innerHTML; changed(); });
        box.querySelectorAll("[data-cmd]").forEach((b) => b.addEventListener("click", () => {
          area.focus();
          const c = b.dataset.cmd;
          if (c === "createLink") { const u = prompt(T.linkUrl, "https://"); if (u) document.execCommand("createLink", false, u); }
          else if (c === "h3") document.execCommand("formatBlock", false, "h3");
          else document.execCommand(c, false, null);
          d[name] = area.innerHTML; changed();
        }));
      }
    } else if (kind === "ids") {
      const cur = new Set(d[name] || []);
      box.innerHTML = fieldWrap(label, `<div style="max-height:200px;overflow:auto;border:1px solid var(--line);border-radius:8px;padding:6px 8px">${SPEC.categories.map((c) => `<label class="field check" style="margin:3px 0"><input class="chk" type="checkbox" value="${c.id}" ${cur.has(c.id) ? "checked" : ""}> <span class="small">${esc(c.name)}</span></label>`).join("")}</div>`);
      box.querySelectorAll("input").forEach((i) => i.addEventListener("change", () => {
        d[name] = Array.from(box.querySelectorAll("input:checked")).map((x) => Number(x.value)); changed();
      }));
    } else if (kind.startsWith("list:")) {
      const fields = kind.slice(5).split(",");
      d[name] = d[name] || [];
      const list = document.createElement("div"); list.className = "stack";
      const draw = () => {
        list.innerHTML = "";
        d[name].forEach((row, i) => {
          const it = document.createElement("div"); it.className = "b-list-item";
          it.innerHTML = `<button type="button" class="x" title="${esc(T.remove)}">${icon("x", 13)}</button>`;
          fields.forEach((f) => {
            if (f === "src") {
              it.insertAdjacentHTML("beforeend", `<div class="b-img-pick">${row.src ? `<img src="${esc(row.src)}" alt="">` : ""}<button type="button" class="btn sm" data-pick>${esc(T.choose)}</button></div>`);
            } else if (f === "rating") {
              it.insertAdjacentHTML("beforeend", `<select class="inp" data-f="rating">${[5, 4, 3, 2, 1].map((n) => `<option value="${n}" ${Number(row.rating) === n ? "selected" : ""}>${"★".repeat(n)}</option>`).join("")}</select>`);
            } else if (f === "text") {
              it.insertAdjacentHTML("beforeend", `<textarea class="inp" rows="3" data-f="text" placeholder="${esc(SPEC.fields.text || "Text")}">${esc(row.text)}</textarea>`);
            } else {
              it.insertAdjacentHTML("beforeend", `<input class="inp" data-f="${f}" placeholder="${esc(SPEC.fields[f] || f)}" value="${esc(row[f])}">`);
            }
          });
          it.querySelector(".x").addEventListener("click", () => { d[name].splice(i, 1); draw(); changed(); });
          it.querySelectorAll("[data-f]").forEach((el) => el.addEventListener("input", () => { row[el.dataset.f] = el.dataset.f === "rating" ? Number(el.value) : el.value; changed(); }));
          const pick = it.querySelector("[data-pick]");
          if (pick) pick.addEventListener("click", () => pickImage((url) => { row.src = url; draw(); changed(); }));
          list.appendChild(it);
        });
        const add = document.createElement("button");
        add.type = "button"; add.className = "btn sm"; add.innerHTML = icon("plus", 13) + " " + esc(T.add);
        add.addEventListener("click", () => {
          if (fields.includes("src")) { pickImage((url) => { d[name].push({ src: url, alt: "" }); draw(); changed(); }); return; }
          d[name].push(Object.fromEntries(fields.map((f) => [f, f === "rating" ? 5 : ""]))); draw(); changed();
        });
        list.appendChild(add);
      };
      draw();
      box.innerHTML = `<div class="field"><label>${esc(label)}</label></div>`;
      box.firstChild.appendChild(list);
    }
    return box;
  }

  function sectionSettings(s) {
    const st = s.style;
    panel.innerHTML = `<div class="b-set-head"><span>${icon("columns", 16)} ${esc(T.section)}</span></div><div class="b-set-body" id="b-form"></div>`;
    const f = panel.querySelector("#b-form");
    const add = (html, bindFn) => { const d = document.createElement("div"); d.innerHTML = html; f.appendChild(d); bindFn && bindFn(d); };
    add(fieldWrap(T.layout, `<div class="b-layouts" style="padding:0">${SPEC.layouts.map(([k, spans]) => `<button type="button" class="b-lay" data-lay="${k}" style="${s.layout === k ? "border-color:var(--navy)" : ""}">${spans.map((n) => `<i style="flex:${n}"></i>`).join("")}</button>`).join("")}</div>`), (d) => {
      d.querySelectorAll("[data-lay]").forEach((b) => b.addEventListener("click", () => {
        const n = LAYOUTS[b.dataset.lay].length;
        const all = s.columns.map((c) => c.widgets);
        const cols = Array.from({ length: n }, (_, i) => ({ widgets: all[i] || [] }));
        all.slice(n).forEach((ws) => cols[n - 1].widgets.push(...ws)); // keep widgets of removed columns
        s.layout = b.dataset.lay; s.columns = cols; render(); settings();
      }));
    });
    add(fieldWrap(T.bg, `<div class="row"><input type="color" class="inp" style="width:60px;padding:2px" value="${esc(st.bg || "#ffffff")}"><button type="button" class="btn sm ghost">${esc(T.remove)}</button></div>`), (d) => {
      d.querySelector("input").addEventListener("input", (e) => { st.bg = e.target.value; renderKeep(); });
      d.querySelector("button").addEventListener("click", () => { st.bg = ""; render(); settings(); });
    });
    add(fieldWrap(T.bgimg, `<div class="b-img-pick">${st.image ? `<img src="${esc(st.image)}" alt="">` : ""}<button type="button" class="btn sm">${esc(T.choose)}</button>${st.image ? `<button type="button" class="btn sm ghost danger">${esc(T.remove)}</button>` : ""}</div>`), (d) => {
      const b = d.querySelectorAll("button");
      b[0].addEventListener("click", () => pickImage((url) => { st.image = url; render(); settings(); }));
      if (b[1]) b[1].addEventListener("click", () => { st.image = ""; render(); settings(); });
    });
    add(fieldWrap(T.overlay, `<input type="range" class="inp" min="0" max="90" value="${st.overlay || 0}">`), (d) => d.querySelector("input").addEventListener("input", (e) => { st.overlay = Number(e.target.value); renderKeep(); }));
    const sel2 = (key, opts) => add(fieldWrap(T[key], `<select class="inp">${opts.map((o) => `<option value="${o}" ${st[key] === o ? "selected" : ""}>${esc(T[o] || o)}</option>`).join("")}</select>`), (d) => d.querySelector("select").addEventListener("change", (e) => { st[key] = e.target.value; renderKeep(); }));
    sel2("padding", ["none", "sm", "md", "lg", "xl"]);
    sel2("width", ["boxed", "narrow", "full"]);
    sel2("align", ["left", "center"]);
    add(`<label class="field check"><input class="chk" type="checkbox" ${st.dark ? "checked" : ""}> <span>${esc(T.dark)}</span></label>`, (d) => d.querySelector("input").addEventListener("change", (e) => { st.dark = e.target.checked; renderKeep(); }));
    add(fieldWrap(T.anchor, `<input class="inp" value="${esc(st.anchor)}" placeholder="book">`), (d) => d.querySelector("input").addEventListener("input", (e) => { st.anchor = e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""); renderKeep(); }));
  }

  // Re-render the canvas but keep focus in the settings panel.
  let rt;
  function renderKeep() { clearTimeout(rt); rt = setTimeout(render, 120); input.value = JSON.stringify(layout); }

  // ---------------------------------------------------------------- media picker
  let pickCb = null;
  function pickImage(cb) {
    pickCb = cb;
    const grid = document.getElementById("media-grid");
    grid.innerHTML = "";
    fetch(SPEC.media + "?format=json", { headers: { "x-requested-with": "fetch" } }).then((r) => r.json()).then((d) => {
      d.files.filter((f) => f.image).forEach((f) => {
        const b = document.createElement("button"); b.type = "button";
        b.innerHTML = `<img src="${esc(f.url)}" alt="${esc(f.alt)}" loading="lazy">`;
        b.addEventListener("click", () => done(f.url));
        grid.appendChild(b);
      });
    });
    window.odgOpenModal("media-modal");
  }
  function done(url) { document.getElementById("media-modal").classList.remove("open"); if (pickCb) pickCb(url); pickCb = null; }
  document.getElementById("media-use-url").addEventListener("click", () => { const u = document.getElementById("media-url").value.trim(); if (/^(https?:\/\/|\/)/.test(u)) done(u); });
  document.getElementById("media-upload").addEventListener("change", async (e) => {
    const file = e.target.files[0]; if (!file) return;
    const status = document.getElementById("media-status"); status.textContent = T.uploading;
    const fd = new FormData(); fd.append("file", file); fd.append("csrfmiddlewaretoken", window.ODG.csrf);
    const r = await fetch(SPEC.media, { method: "POST", body: fd, headers: { "x-requested-with": "fetch" } });
    const d = await r.json().catch(() => ({}));
    status.textContent = d.error || "";
    e.target.value = "";
    if (d.url) done(d.url);
  });

  panel.dataset.empty = panel.textContent.trim();
  window.odgBuilder = { get: () => layout, text: () => {
    const parts = [];
    layout.sections.forEach((s) => s.columns.forEach((c) => c.widgets.forEach((w) => {
      const d = w.data || {};
      ["text", "title", "subtitle", "sub", "caption"].forEach((k) => d[k] && parts.push(String(d[k])));
      if (d.html) { const t = document.createElement("div"); t.innerHTML = d.html; parts.push(t.textContent); }
      (d.items || []).forEach((i) => parts.push(i.text || ""));
    })));
    return parts.join("\n");
  }, headings: () => {
    const out = [];
    layout.sections.forEach((s) => s.columns.forEach((c) => c.widgets.forEach((w) => {
      if (w.type === "heading") out.push(w.data.text || "");
      if (w.type === "text" && w.data.html) { const t = document.createElement("div"); t.innerHTML = w.data.html; t.querySelectorAll("h2,h3,h4").forEach((h) => out.push(h.textContent)); }
    })));
    return out;
  }, images: () => {
    const out = [];
    layout.sections.forEach((s) => s.columns.forEach((c) => c.widgets.forEach((w) => { if (w.type === "image" && w.data.src) out.push(w.data.alt || ""); (w.data.images || []).forEach((i) => out.push(i.alt || "")); })));
    return out;
  } };
  const form = input.closest("form");
  if (form) form.addEventListener("submit", () => { input.value = JSON.stringify(layout); });
  render(); settings();
})();
