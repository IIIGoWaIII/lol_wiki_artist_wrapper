(() => {
  const STEP = 240;
  const state = {
    skins: [],
    filtered: [],
    shown: 0,
    lbIdx: -1,
    champs: [],
    themes: [],
    artists: [],
    sel: { champs: new Set(), themes: new Set(), artists: new Set() },
  };

  const $ = (id) => document.getElementById(id);
  const grid = $("grid");
  const elSearch = $("search") || { value: "" };
  const empty = $("empty");
  const more = $("more");
  const lb = $("lb");
  const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);

  const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

  const skinLabel = (rec) => {
    if (rec.fmt) {
      const l = rec.fmt.replace(new RegExp("\\s*" + esc(rec.ch) + "\\s*$"), "").trim();
      if (l) return l;
    }
    return rec.s;
  };

  const yearOf = (rec) => (rec.r && /^\d{4}/.test(rec.r) ? parseInt(rec.r.slice(0, 4), 10) : null);

  function precompute(rec, i) {
    const set = rec.set || [];
    rec._i = i;
    rec._label = skinLabel(rec);
    rec._year = yearOf(rec);
    rec._search = [rec.ch, rec.s, rec.fmt, rec._label, set.join(" "), (rec.art || []).join(" ")]
      .filter(Boolean).join(" ").toLowerCase();
    return rec;
  }

  async function load() {
    const d = await (await fetch("data/skins.json")).json();
    state.skins = d.skins.map(precompute);
    buildIndex();
    buildSelects();
    renderPanels();
    apply();
  }

  function buildIndex() {
    const champs = new Map();
    const themes = new Map();
    const artists = new Map();
    for (const s of state.skins) {
      const c = champs.get(s.ch);
      if (c) c.count++; else champs.set(s.ch, { count: 1, rec: s });
      for (const t of s.set || []) {
        const th = themes.get(t);
        if (th) th.count++; else themes.set(t, { count: 1, rec: s });
      }
      for (const a of s.art || []) {
        const ar = artists.get(a);
        if (ar) ar.count++; else artists.set(a, { count: 1 });
      }
    }
    state.champs = [...champs.entries()].map(([name, v]) => ({ name, count: v.count, rec: v.rec }))
      .sort((a, b) => a.name.localeCompare(b.name));
    state.themes = [...themes.entries()].map(([name, v]) => ({ name, count: v.count, rec: v.rec }))
      .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
    state.artists = [...artists.entries()].map(([name, v]) => ({ name, count: v.count }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }

  function buildSelects() {
    const years = [...new Set(state.skins.map((s) => s._year).filter((y) => y != null))].sort((a, b) => b - a);
    const ys = $("fYear");
    for (const y of years) {
      const o = document.createElement("option");
      o.value = String(y);
      o.textContent = String(y);
      ys.appendChild(o);
    }
  }

  function renderPanels() {
    renderPanel("champs");
    renderPanel("themes");
    renderPanel("artists");
  }

  function renderPanel(kind) {
    const q = $(`ps${cap(kind)}`).value.trim().toLowerCase();
    const pgrid = $(`pg${cap(kind)}`);
    pgrid.innerHTML = "";
    const items = state[kind];
    const sel = state.sel[kind];
    for (const it of items) {
      if (q && !it.name.toLowerCase().includes(q)) continue;
      pgrid.appendChild(kind === "artists" ? makePill(it, sel) : makeTile(it, kind, sel));
    }
  }

  function makeTile(it, kind, sel) {
    const label = document.createElement("label");
    label.className = "tile";
    label.title = `${it.name} (${it.count})`;
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.value = it.name;
    cb.checked = sel.has(it.name);
    const img = document.createElement("img");
    img.loading = "lazy";
    img.src = it.rec.t || it.rec.img;
    img.alt = it.name;
    const name = document.createElement("span");
    name.className = "tn";
    name.textContent = it.name;
    const tick = document.createElement("span");
    tick.className = "tk";
    tick.textContent = "\u2713";
    label.append(cb, img, name, tick);
    return label;
  }

  function makePill(it, sel) {
    const label = document.createElement("label");
    label.className = "pill";
    label.title = it.name;
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.value = it.name;
    cb.checked = sel.has(it.name);
    const name = document.createElement("span");
    name.textContent = it.name;
    const cnt = document.createElement("b");
    cnt.textContent = it.count;
    label.append(cb, name, cnt);
    return label;
  }

  function updateSel(kind) {
    const pgrid = $(`pg${cap(kind)}`);
    const prev = state.sel[kind];
    if (prev) {
      const next = new Set(prev);
      pgrid.querySelectorAll("input").forEach((i) => {
        if (i.checked) next.add(i.value);
        else next.delete(i.value);
      });
      state.sel[kind] = next;
    } else {
      const sel = new Set();
      pgrid.querySelectorAll("input:checked").forEach((i) => sel.add(i.value));
      state.sel[kind] = sel;
    }
    $(`sc${cap(kind)}`).textContent = state.sel[kind].size ? `(${state.sel[kind].size})` : "";
    apply();
  }

  function panelAll(kind) {
    $(`pg${cap(kind)}`).querySelectorAll("input").forEach((i) => { i.checked = true; });
    updateSel(kind);
  }

  function panelNone(kind) {
    $(`pg${cap(kind)}`).querySelectorAll("input").forEach((i) => { i.checked = false; });
    updateSel(kind);
  }

  function resetPanels() {
    for (const kind of ["champs", "themes", "artists"]) {
      state.sel[kind] = new Set();
      $(`sc${cap(kind)}`).textContent = "";
    }
  }

  for (const kind of ["champs", "themes", "artists"]) {
    const pgrid = $(`pg${cap(kind)}`);
    pgrid.addEventListener("change", () => updateSel(kind));
    $(`ps${cap(kind)}`).addEventListener("input", () => renderPanel(kind));
  }
  document.querySelectorAll(".pall").forEach((b) => b.addEventListener("click", () => panelAll(b.dataset.kind)));
  document.querySelectorAll(".pnone").forEach((b) => b.addEventListener("click", () => panelNone(b.dataset.kind)));

  function apply() {
    const q = elSearch.value.trim().toLowerCase();
    const year = $("fYear").value;
    const sort = $("fSort").value;
    const sel = state.sel;

    let list = state.skins.filter((s) => {
      if (q && !s._search.includes(q)) return false;
      if (sel.champs.size && !sel.champs.has(s.ch)) return false;
      if (sel.themes.size && !(s.set || []).some((t) => sel.themes.has(t))) return false;
      if (sel.artists.size && !(s.art || []).some((a) => sel.artists.has(a))) return false;
      if (year && s._year != null && String(s._year) !== year) return false;
      return true;
    });

    const byDate = (rev) => (a, b) => {
      const da = a._year ?? (rev ? Infinity : -Infinity);
      const db = b._year ?? (rev ? Infinity : -Infinity);
      if (da !== db) return rev ? da - db : db - da;
      return a._label.localeCompare(b._label);
    };
    switch (sort) {
      case "old": list.sort(byDate(true)); break;
      case "new": list.sort(byDate(false)); break;
      case "az": list.sort((a, b) => a.ch.localeCompare(b.ch) || a._label.localeCompare(b._label)); break;
      case "za": list.sort((a, b) => b.ch.localeCompare(a.ch) || a._label.localeCompare(b._label)); break;
    }

    state.filtered = list;
    state.shown = 0;
    grid.innerHTML = "";
    empty.hidden = list.length !== 0;
    more.hidden = true;
    renderStep();
  }

  function renderStep() {
    const next = Math.min(state.filtered.length, state.shown + STEP);
    for (let i = state.shown; i < next; i++) grid.appendChild(makeCard(state.filtered[i], i));
    state.shown = next;
    more.hidden = state.shown >= state.filtered.length;
    sentinel().style.display = more.hidden ? "none" : "block";
  }

  let sentinelEl = null;
  function sentinel() {
    if (!sentinelEl) {
      sentinelEl = document.createElement("div");
      sentinelEl.id = "sentinel";
      grid.appendChild(sentinelEl);
      new IntersectionObserver((es) => { if (es[0].isIntersecting && !more.hidden) renderStep(); }, { rootMargin: "900px" })
        .observe(sentinelEl);
    }
    return sentinelEl;
  }

  function resText(rec) {
    return rec.w && rec.h ? `${rec.w}\u00d7${rec.h}` : "";
  }

  function makeCard(rec, idx) {
    const card = document.createElement("div");
    card.className = "card";
    card.dataset.idx = idx;

    const imgWrap = document.createElement("div");
    imgWrap.className = "imgwrap";
    if (resText(rec)) {
      const res = document.createElement("div");
      res.className = "res";
      res.textContent = resText(rec);
      imgWrap.appendChild(res);
    }
    const img = document.createElement("img");
    img.loading = "lazy";
    img.src = rec.t || rec.img;
    img.alt = `${rec._label} — ${rec.ch} splash art`;
    imgWrap.appendChild(img);
    card.appendChild(imgWrap);

    const meta = document.createElement("div");
    meta.className = "meta";
    const name = document.createElement("div");
    name.className = "name";
    name.textContent = rec._label;
    const sub = document.createElement("div");
    sub.className = "sub";
    sub.textContent = [rec.ch, (rec.set || []).join(", ") || "", (rec.art || [])[0] || ""].filter(Boolean).join(" · ");
    meta.append(name, sub);
    card.appendChild(meta);

    card.addEventListener("click", () => openLightbox(idx));
    return card;
  }

  function loadLbImage(rec) {
    const img = $("lbImg");
    const bar = $("lbLoadBar");
    bar.classList.remove("done");

    img.onload = null;
    img.onerror = null;

    const full = document.createElement("img");
    full.src = rec.img;
    full.onload = () => {
      bar.classList.add("done");
      setTimeout(() => bar.classList.remove("active", "done"), 2000);
      img.src = full.src;
    };
    full.onerror = () => bar.classList.remove("active");

    img.src = rec.t || rec.img;
    bar.classList.add("active");
  }

  function openLightbox(idx) {
    state.lbIdx = idx;
    const rec = state.filtered[idx];
    const label = rec._label;

    $("lbName").textContent = label;
    $("lbChamp").textContent = rec.ch;
    $("lbPos").textContent = `${idx + 1} of ${state.filtered.length}`;

    const info = $("lbInfo");
    info.innerHTML = "";
    const rows = [
      ["Themes", (rec.set || []).join(", ")],
      ["Artists", (rec.art || []).join(", ")],
      ["Release date", rec.r],
      ["Chromas", rec.cr > 0 ? `${rec.cr} chromas` : "None"],
      ["Resolution", resText(rec) ? `${resText(rec)} px` : ""],
    ];
    for (const [k, v] of rows) {
      if (!v) continue;
      const dt = document.createElement("dt"); dt.textContent = k;
      const dd = document.createElement("dd"); dd.textContent = v;
      if (k === "Resolution") dd.id = "lbRes";
      info.append(dt, dd);
    }

    loadLbImage(rec);
    $("lbImgWrap").scrollTop = 0;
    $("lbStage").scrollTop = 0;

    renderVersions(rec);

    lb.hidden = false;
    document.body.style.overflow = "hidden";
  }

  function renderVersions(rec) {
    const box = $("lbVersGrid");
    box.innerHTML = "";
    const vers = [{ l: "Newest", img: rec.img, t: rec.t, w: rec.w, h: rec.h }, ...(rec.v || [])];
    $("lbVers").hidden = vers.length <= 1;
    if (vers.length <= 1) return;
    vers.forEach((v, i) => {
      const b = document.createElement("button");
      b.className = "vbtn";
      if (i === (rec._curVer || 0)) b.classList.add("on");
      b.title = v.l;
      const im = document.createElement("img");
      im.loading = "lazy";
      im.src = v.t || v.img;
      im.alt = v.l;
      const sp = document.createElement("span");
      sp.textContent = v.l;
      b.append(im, sp);
      b.addEventListener("click", () => setVersion(rec, i, b));
      box.appendChild(b);
    });
  }

  function setVersion(rec, i, el) {
    const vers = [{ l: "Newest", img: rec.img, t: rec.t, w: rec.w, h: rec.h }, ...(rec.v || [])];
    const v = vers[i];
    if (!v) return;
    rec._curVer = i;
    loadLbImage(v);
    $("lbImgWrap").scrollTop = 0;
    $("lbStage").scrollTop = 0;
    const res = $("lbRes");
    if (res) res.textContent = v.w && v.h ? `${v.w}\u00d7${v.h} px` : "";
    $("lbVersGrid").querySelectorAll(".vbtn").forEach((b) => b.classList.remove("on"));
    el.classList.add("on");
  }

  function closeLightbox() {
    lb.hidden = true;
    document.body.style.overflow = "";
    state.lbIdx = -1;
  }

  function step(delta) {
    const nxt = (state.lbIdx + delta + state.filtered.length) % state.filtered.length;
    openLightbox(nxt);
  }

  let toastTimer = null;
  function toast(msg) {
    const t = $("toast");
    t.textContent = msg;
    t.hidden = false;
    requestAnimationFrame(() => t.classList.add("show"));
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { t.classList.remove("show"); }, 2600);
  }

  $("lbClose").addEventListener("click", closeLightbox);
  $("lbPrev").addEventListener("click", () => step(-1));
  $("lbNext").addEventListener("click", () => step(1));
  lb.addEventListener("click", (e) => { if (e.target === lb) closeLightbox(); });

  document.addEventListener("keydown", (e) => {
    if (lb.hidden) return;
    if (e.key === "Escape") closeLightbox();
    else if (e.key === "ArrowLeft") step(-1);
    else if (e.key === "ArrowRight") step(1);
  });

  $("clearbtn").addEventListener("click", () => {
    elSearch.value = "";
    for (const kind of ["champs", "themes", "artists"]) {
      $(`ps${cap(kind)}`).value = "";
    }
    resetPanels();
    $("fYear").value = "";
    $("fSort").value = "new";
    renderPanels();
    apply();
  });

  let debounce = null;
  $("fYear").addEventListener("change", apply);
  $("fSort").addEventListener("change", apply);
  more.addEventListener("click", renderStep);

  load().catch((e) => { toast("Failed to load data: " + e.message); });
})();