/* ODG-SCHOOL dashboard behaviour: menus, modals, small helpers. */
(function () {
  "use strict";
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));

  // Mobile side menu
  $$("[data-toggle-nav]").forEach((b) => b.addEventListener("click", () => document.body.classList.toggle("nav-open")));

  // Dropdowns
  document.addEventListener("click", (e) => {
    const trigger = e.target.closest("[data-dd]");
    $$(".dd.open").forEach((d) => { if (!trigger || d !== trigger.parentElement) d.classList.remove("open"); });
    if (trigger) trigger.parentElement.classList.toggle("open");
  });

  // Dismissable alerts
  $$("[data-dismiss]").forEach((b) => b.addEventListener("click", () => b.parentElement.remove()));

  // Modals: <button data-modal="id"> opens <div class="modal" id="id">
  window.odgOpenModal = function (id, data) {
    const m = document.getElementById(id);
    if (!m) return;
    if (data) {
      Object.entries(data).forEach(([k, v]) => {
        const el = m.querySelector(`[name="${k}"]`);
        if (!el) { const t = m.querySelector(`[data-fill="${k}"]`); if (t) t.textContent = v; return; }
        if (el.type === "checkbox") el.checked = !!v; else el.value = v ?? "";
      });
    }
    m.classList.add("open");
    const first = m.querySelector("input:not([type=hidden]),select,textarea");
    if (first) setTimeout(() => first.focus(), 30);
  };
  document.addEventListener("click", (e) => {
    const opener = e.target.closest("[data-modal]");
    if (opener) {
      e.preventDefault();
      let data = null;
      if (opener.dataset.fill) { try { data = JSON.parse(opener.dataset.fill); } catch (_) { data = null; } }
      window.odgOpenModal(opener.dataset.modal, data);
      return;
    }
    if (e.target.classList.contains("modal") || e.target.closest(".modal-close")) {
      const m = e.target.closest(".modal");
      if (m) m.classList.remove("open");
    }
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") $$(".modal.open").forEach((m) => m.classList.remove("open")); });

  // Confirm before submitting dangerous forms
  document.addEventListener("submit", (e) => {
    const msg = e.target.dataset.confirm || (e.submitter && e.submitter.dataset.confirm);
    if (msg && !window.confirm(msg)) e.preventDefault();
  });

  // Client-side table filter: <input data-filter="#tableId">
  $$("[data-filter]").forEach((inp) => {
    const target = $(inp.dataset.filter);
    if (!target) return;
    inp.addEventListener("input", () => {
      const q = inp.value.trim().toLowerCase();
      $$("[data-search]", target).forEach((row) => {
        row.style.display = row.dataset.search.toLowerCase().includes(q) ? "" : "none";
      });
    });
  });

  // Show/hide blocks depending on a select: <div data-show-when="name=value">
  function syncConditional() {
    $$("[data-show-when]").forEach((el) => {
      const [name, values] = el.dataset.showWhen.split("=");
      const form = el.closest("form") || document;
      const ctl = form.querySelector(`[name="${name}"]`);
      if (!ctl) return;
      const val = ctl.type === "checkbox" ? (ctl.checked ? "on" : "") : ctl.value;
      el.style.display = values.split("|").includes(val) ? "" : "none";
    });
  }
  document.addEventListener("change", syncConditional);
  syncConditional();
})();
