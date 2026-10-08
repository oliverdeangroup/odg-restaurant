/* ODG-RESTAURANT public website: mobile menu and the online reservation widget. */
(function () {
  "use strict";
  document.querySelectorAll("[data-nav-toggle]").forEach(function (b) {
    b.addEventListener("click", function () {
      document.body.classList.toggle("nav-open");
      b.setAttribute("aria-expanded", document.body.classList.contains("nav-open"));
    });
  });

  // Online reservation: pick date + guests → free 30-minute slots → details → book.
  document.querySelectorAll("[data-booking]").forEach(function (box) {
    const form = box.querySelector("form");
    const T = JSON.parse(box.querySelector(".bk-t").textContent);
    const slots = box.querySelector("[data-slots-box]");
    const details = box.querySelector(".bk-details");
    const msg = box.querySelector(".bk-msg");
    const timeInp = form.querySelector("[name=time]");
    async function load() {
      timeInp.value = ""; details.hidden = true; msg.textContent = ""; msg.className = "bk-msg";
      const url = form.dataset.slots + "?date=" + encodeURIComponent(form.date.value) + "&guests=" + encodeURIComponent(form.guests.value);
      slots.innerHTML = "<span class='muted'>…</span>";
      try {
        const d = await (await fetch(url, { headers: { "x-requested-with": "fetch" } })).json();
        slots.innerHTML = "";
        if (d.closed) { slots.innerHTML = "<span class='muted'>" + T.closed + "</span>"; return; }
        const free = (d.slots || []).filter(function (s) { return s.free; });
        if (!free.length) { slots.innerHTML = "<span class='muted'>" + T.none + "</span>"; return; }
        d.slots.forEach(function (s) {
          const b = document.createElement("button");
          b.type = "button"; b.textContent = s.time; b.disabled = !s.free;
          b.addEventListener("click", function () {
            slots.querySelectorAll("button").forEach(function (x) { x.classList.remove("on"); });
            b.classList.add("on"); timeInp.value = s.time; details.hidden = false;
            const first = details.querySelector("input"); if (first) first.focus();
          });
          slots.appendChild(b);
        });
      } catch (e) { slots.innerHTML = "<span class='muted'>" + T.error + "</span>"; }
    }
    form.date.addEventListener("change", load);
    form.guests.addEventListener("change", load);
    form.addEventListener("submit", async function (e) {
      e.preventDefault();
      const btn = form.querySelector(".bk-submit");
      btn.disabled = true; msg.className = "bk-msg"; msg.textContent = T.sending;
      try {
        const r = await fetch(form.getAttribute("action"), { method: "POST", body: new FormData(form), headers: { "x-requested-with": "fetch" } });
        const d = await r.json();
        if (d.ok) {
          msg.className = "bk-msg ok"; msg.textContent = d.message;
          form.querySelectorAll(".bk-step").forEach(function (s) { s.hidden = true; });
        } else { msg.className = "bk-msg err"; msg.textContent = d.error || T.error; btn.disabled = false; }
      } catch (err) { msg.className = "bk-msg err"; msg.textContent = T.error; btn.disabled = false; }
    });
    load();
  });
})();
