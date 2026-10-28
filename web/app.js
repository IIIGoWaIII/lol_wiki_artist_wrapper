(() => {
  const STEP = 240;
  const DEFAULT_GAME = "lol";
  // Kept in step with the `out` filename of each game in build_data.py.
  const GAMES = {
    lol: "skins.json",
    wr: "skins-wr.json",
    lor: "skins-lor.json",
  };
  const cache = new Map();
  const state = {
    game: null,
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
  const empty = $("empty");
  const more = $("more");
  const lb = $("lb");
  const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);

  const lbLens = $("lbLens");
  const lbLensImg = $("lbLensImg");
  let magZoom = 1.5;
  const MAG_SIZE = 600;
  let lbDown = false;
  let curFull = null;

  const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

  const skinLabel = (rec) => {
    if (rec.fmt) {
      const l = rec.fmt.replace(new RegExp("\\s*" + esc(rec.ch) + "\\s*$"), "").trim();
      if (l) return l;
    }
    return rec.s;
  };

  const yearOf = (rec) => (rec._date && /^\d{4}/.test(rec._date) ? parseInt(rec._date.slice(0, 4), 10) : null);

  function precompute(rec, i) {
    rec._i = i;
    rec._label = skinLabel(rec);
    const rOk = rec.r && /^\d{4}-\d{2}-\d{2}$/.test(rec.r);
    rec._date = rec.d || (rOk ? rec.r : null) || null;
    rec._year = yearOf(rec);
    return rec;
  }

  // The wiki renders any thumb width on demand. Grid cards and version buttons
  // are a few hundred pixels wide, so ask for the 420px variant rather than the
  // 1200px one the catalogue stores for the lightbox.
  const thumbAt = (url, width) => (url ? url.replace(/\/\d+px-/, `/${width}px-`) : null);

  async function fetchGame(key) {
    if (cache.has(key)) return cache.get(key);
    const p = fetch("data/" + GAMES[key])
      .then((r) => {
        if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
        return r.json();
      })
      .catch((e) => {
        cache.delete(key);
        throw e;
      });
    cache.set(key, p);
    return p;
  }

  // Every selection belongs to the game it was made in: a champion chosen under
  // League means nothing in Runeterra, so a tab change starts from a clean slate.
  function resetFilters() {
    for (const k of Object.keys(state.sel)) state.sel[k].clear();
    for (const id of ["psChamps", "psThemes", "psArtists"]) $(id).value = "";
    $("fYear").value = "";
    closeLightbox();
  }

  let loadToken = 0;

  async function load(key) {
    if (!Object.hasOwn(GAMES, key)) return;
    // Two quick tab clicks resolve out of order; only the last one may paint.
    const token = ++loadToken;
    const d = await fetchGame(key);
    if (token !== loadToken) return;
    state.game = key;
    state.skins = d.skins.map(precompute);
    // Each game crops artwork to its own native ratio; the CSS reads this.
    const [w, h] = d.meta.aspect || [1215, 717];
    document.documentElement.style.setProperty("--ar", `${w} / ${h}`);
    document.title = d.meta.label ? `${d.meta.label} Splash Reference` : "Splash Reference";
    for (const tab of $("gametabs").children) {
      const on = tab.dataset.game === key;
      tab.classList.toggle("on", on);
      tab.setAttribute("aria-selected", on ? "true" : "false");
    }
    resetFilters();
    buildIndex();
    buildSelects();
    renderPanels();
    apply();
  }

  function buildSelects() {
    const years = [...new Set(state.skins.map((s) => s._year).filter((y) => y != null))].sort((a, b) => b - a);
    const ys = $("fYear");
    // Drop last game's years but keep the "Any year" placeholder from index.html.
    while (ys.options.length > 1) ys.remove(1);
    for (const y of years) {
      const o = document.createElement("option");
      o.value = String(y);
      o.textContent = String(y);
      ys.appendChild(o);
    }
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
    const name = document.createElement("span");
    name.className = "tn";
    name.textContent = it.name;
    const tick = document.createElement("span");
    tick.className = "tk";
    tick.textContent = "\u2713";
    label.append(cb, name, tick);
    const src = thumbAt(it.rec.t || it.rec.img, 420);
    if (src) {
      const img = document.createElement("img");
      img.loading = "lazy";
      img.src = src;
      img.alt = it.name;
      label.insertBefore(img, name);
    }
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
    const next = new Set(state.sel[kind]);
    pgrid.querySelectorAll("input").forEach((i) => {
      if (i.checked) next.add(i.value);
      else next.delete(i.value);
    });
    state.sel[kind] = next;
    $(`sc${cap(kind)}`).textContent = next.size ? `(${next.size})` : "";
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
    const year = $("fYear").value;
    const sort = $("fSort").value;
    const sel = state.sel;

    let list = state.skins.filter((s) => {
      if (sel.champs.size && !sel.champs.has(s.ch)) return false;
      if (sel.themes.size && !(s.set || []).some((t) => sel.themes.has(t))) return false;
      if (sel.artists.size && !(s.art || []).some((a) => sel.artists.has(a))) return false;
      if (year && String(s._year) !== year) return false;
      return true;
    });

    const cmpDate = (a, b) => {
      if (a === b) return 0;
      if (a == null) return 1;
      if (b == null) return -1;
      return a < b ? -1 : 1;
    };
    const byDate = (rev) => (a, b) => {
      const c = rev ? cmpDate(a._date, b._date) : cmpDate(b._date, a._date);
      return c || a._label.localeCompare(b._label);
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
      // A sibling of the grid, not a grid item: inside the grid it would take a
      // cell and push the next batch of cards out of alignment.
      grid.after(sentinelEl);
      new IntersectionObserver((es) => { if (es[0].isIntersecting && !more.hidden) renderStep(); }, { rootMargin: "900px" })
        .observe(sentinelEl);
    }
    return sentinelEl;
  }

  function resText(rec) {
    return rec.w && rec.h ? `${rec.w}\u00d7${rec.h}` : "";
  }

  function makeCard(rec, idx) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "card";
    card.dataset.idx = idx;
    card.setAttribute("aria-label", `${rec.ch} - ${rec._label}`);

    const imgWrap = document.createElement("span");
    imgWrap.className = "imgwrap";
    if (resText(rec)) {
      const res = document.createElement("span");
      res.className = "res";
      res.textContent = resText(rec);
      imgWrap.appendChild(res);
    }
    if (rec.img) {
      const img = document.createElement("img");
      img.loading = "lazy";
      img.src = thumbAt(rec.t || rec.img, 420);
      img.alt = `${rec._label} — ${rec.ch} splash art`;
      imgWrap.appendChild(img);
    } else {
      const ph = document.createElement("span");
      ph.className = "noart";
      ph.textContent = "No artwork on the wiki";
      imgWrap.appendChild(ph);
    }
    card.appendChild(imgWrap);

    const meta = document.createElement("span");
    meta.className = "meta";
    const name = document.createElement("span");
    name.className = "name";
    name.textContent = `${rec.ch} - ${rec._label}`;
    const sub = document.createElement("span");
    sub.className = "sub";
    sub.textContent = [(rec.set || []).join(", ") || "", (rec.art || [])[0] || ""].filter(Boolean).join(" · ");
    meta.append(name, sub);
    card.appendChild(meta);

    card.addEventListener("click", () => openLightbox(idx));
    card.addEventListener("mousedown", (e) => {
      if (e.button !== 1) return;
      e.preventDefault();
    });
    card.addEventListener("auxclick", (e) => {
      if (e.button !== 1) return;
      e.preventDefault();
      window.open(rec.img, "_blank", "noopener");
    });
    return card;
  }

  function loadLbImage(rec) {
    const img = $("lbImg");
    const bar = $("lbLoadBar");
    const noArt = $("lbNoArt");
    bar.classList.remove("done");
    curFull = rec.img;

    img.onload = null;
    img.onerror = null;

    if (!rec.img) {
      bar.classList.remove("active");
      img.hidden = true;
      img.removeAttribute("src");
      lbLensImg.removeAttribute("src");
      noArt.hidden = false;
      return;
    }
    img.hidden = false;
    noArt.hidden = true;

    const full = document.createElement("img");
    full.src = rec.img;
    full.onload = () => {
      bar.classList.add("done");
      setTimeout(() => bar.classList.remove("active", "done"), 2000);
      img.src = full.src;
      lbLensImg.src = full.src;
    };
    full.onerror = () => bar.classList.remove("active");

    img.src = thumbAt(rec.t || rec.img, 1200);
    bar.classList.add("active");
  }

  // Images open in place and leave the URL alone; stepping keeps lightbox focus.
  let lastFocus = null;

  function openLightbox(idx) {
    state.lbIdx = idx;
    const rec = state.filtered[idx];
    const label = rec._label;
    const wasHidden = lb.hidden;
    if (wasHidden) lastFocus = document.activeElement;

    $("lbName").textContent = `${rec.ch} - ${label}`;
    $("lbChamp").textContent = rec.ch;
    $("lbPos").textContent = `${idx + 1} of ${state.filtered.length}`;

    const info = $("lbInfo");
    info.innerHTML = "";
    const rows = [
      ["Themes", (rec.set || []).join(", ")],
      ["Artists", (rec.art || []).join(", ")],
      ["Artwork date", rec.d],
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

    // The side panel always starts on the newest artwork, so the highlighted
    // version button and the loaded image cannot drift apart.
    rec._curVer = 0;
    loadLbImage(rec);
    $("lbImgWrap").scrollTop = 0;
    $("lbStage").scrollTop = 0;

    renderVersions(rec);

    lb.hidden = false;
    document.body.style.overflow = "hidden";
    writeUrl(rec.ch, rec.s);
    if (wasHidden) $("lbClose").focus();
  }

  function renderVersions(rec) {
    const box = $("lbVersGrid");
    box.innerHTML = "";
    const vers = versions(rec);
    $("lbVers").hidden = vers.length <= 1;
    if (vers.length <= 1) return;
    vers.forEach((v, i) => {
      const b = document.createElement("button");
      b.className = "vbtn";
      if (i === rec._curVer) b.classList.add("on");
      b.title = v.l;
      const src = thumbAt(v.t || v.img, 420);
      if (src) {
        const im = document.createElement("img");
        im.loading = "lazy";
        im.src = src;
        im.alt = v.l;
        b.append(im);
      }
      const sp = document.createElement("span");
      sp.textContent = v.l;
      const d = document.createElement("i");
      d.textContent = v.d || "";
      b.append(sp, d);
      b.addEventListener("click", () => setVersion(rec, i, b));
      box.appendChild(b);
    });
  }

  const versions = (rec) =>
    [{ l: "Newest", d: rec.d, img: rec.img, t: rec.t, w: rec.w, h: rec.h }, ...(rec.v || [])];

  function setVersion(rec, i, el) {
    const v = versions(rec)[i];
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
    if (state.lbIdx < 0) return;
    lb.hidden = true;
    document.body.style.overflow = "";
    state.lbIdx = -1;
    writeUrl(null);
    if (lastFocus && document.contains(lastFocus)) lastFocus.focus();
    lastFocus = null;
  }

  function step(delta) {
    const nxt = (state.lbIdx + delta + state.filtered.length) % state.filtered.length;
    openLightbox(nxt);
  }

  // --- URL state -------------------------------------------------------------
  // A shared link opens the same game and skin: ?game=lor&champ=Jinx&skin=Project
  function readUrl() {
    const p = new URLSearchParams(location.search);
    const game = p.get("game");
    return {
      game: game && Object.hasOwn(GAMES, game) ? game : null,
      champ: p.get("champ"),
      skin: p.get("skin"),
    };
  }

  function writeUrl(champ, skin) {
    const p = new URLSearchParams(location.search);
    p.set("game", state.game || DEFAULT_GAME);
    if (champ && skin) {
      p.set("champ", champ);
      p.set("skin", skin);
    } else {
      p.delete("champ");
      p.delete("skin");
    }
    history.replaceState(null, "", `${location.pathname}?${p}`);
  }

  function syncUrl() {
    const u = readUrl();
    if (u.game && u.game !== state.game) {
      load(u.game).catch((e) => toast("Failed to load data: " + e.message));
      return;
    }
    const idx = u.champ && u.skin
      ? state.filtered.findIndex((s) => s.ch === u.champ && s.s === u.skin)
      : -1;
    if (idx >= 0) openLightbox(idx);
    else closeLightbox();
  }

  window.addEventListener("popstate", syncUrl);

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

  function trapTab(e) {
    const items = [...lb.querySelectorAll("button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])")]
      .filter((el) => !el.disabled && el.offsetParent !== null);
    if (!items.length) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }

  document.addEventListener("keydown", (e) => {
    if (lb.hidden) return;
    if (e.key === "Escape") closeLightbox();
    else if (e.key === "ArrowLeft") step(-1);
    else if (e.key === "ArrowRight") step(1);
    else if (e.key === "Tab") trapTab(e);
  });

  $("clearbtn").addEventListener("click", () => {
    for (const kind of ["champs", "themes", "artists"]) {
      $(`ps${cap(kind)}`).value = "";
    }
    resetPanels();
    $("fYear").value = "";
    $("fSort").value = "new";
    renderPanels();
    apply();
  });

  const sb = $("sidebar");
  const sbToggle = $("sbToggle");
  const sbOverlay = $("sbOverlay");
  function setSb(open) {
    sb.classList.toggle("open", open);
    document.body.classList.toggle("sbdim", open);
    sbOverlay.hidden = !open;
    sbToggle.setAttribute("aria-expanded", String(open));
  }
  sbToggle.addEventListener("click", () => setSb(!sb.classList.contains("open")));
  sbOverlay.addEventListener("click", () => setSb(false));
  sbToggle.setAttribute("aria-expanded", "false");
  const onResize = () => { if (window.innerWidth > 980) setSb(false); };
  window.addEventListener("resize", onResize);
  onResize();

  $("fYear").addEventListener("change", apply);
  $("fSort").addEventListener("change", apply);
  more.addEventListener("click", renderStep);

  const lbImg = $("lbImg");
  function magUpdate(e) {
    if (!lbDown) return;
    const box = lbImg.getBoundingClientRect();
    const mx = e.clientX - box.left;
    const my = e.clientY - box.top;
    if (mx < 0 || mx > box.width || my < 0 || my > box.height) {
      lbDown = false;
      lbLens.classList.remove("on");
      return;
    }
    const offX = mx * magZoom;
    const offY = my * magZoom;
    lbLensImg.style.width = (box.width * magZoom) + "px";
    lbLensImg.style.height = (box.height * magZoom) + "px";
    lbLensImg.style.left = (MAG_SIZE / 2 - offX) + "px";
    lbLensImg.style.top = (MAG_SIZE / 2 - offY) + "px";
    lbLens.style.left = (e.clientX - MAG_SIZE / 2) + "px";
    lbLens.style.top = (e.clientY - MAG_SIZE / 2) + "px";
  }
  lbImg.addEventListener("mousedown", (e) => {
    if (lb.hidden) return;
    if (e.button === 1) {
      e.preventDefault();
      return;
    }
    if (e.button !== 0) return;
    const src = lbImg.getAttribute("src");
    if (!src) return;
    e.preventDefault();
    lbDown = true;
    lbLens.style.width = MAG_SIZE + "px";
    lbLens.style.height = MAG_SIZE + "px";
    lbLensImg.src = src;
    magUpdate(e);
    lbLens.classList.add("on");
  });
  document.addEventListener("mousemove", magUpdate);
  document.addEventListener("mouseup", () => {
    lbDown = false;
    lbLens.classList.remove("on");
  });
  document.addEventListener("wheel", (e) => {
    if (lb.hidden || !lbDown) return;
    const box = lbImg.getBoundingClientRect();
    if (e.clientX < box.left || e.clientX > box.right || e.clientY < box.top || e.clientY > box.bottom) return;
    e.preventDefault();
    magZoom = Math.max(1, magZoom + (e.deltaY > 0 ? -0.15 : 0.15));
    magUpdate(e);
  }, { passive: false });

  lbImg.addEventListener("auxclick", (e) => {
    if (e.button !== 1 || lb.hidden || !curFull) return;
    e.preventDefault();
    window.open(curFull, "_blank", "noopener");
  });

  $("gametabs").addEventListener("click", (e) => {
    const tab = e.target.closest(".gtab");
    if (!tab || tab.dataset.game === state.game) return;
    load(tab.dataset.game)
      .then(() => writeUrl(null))
      .catch((err) => toast("Failed to load data: " + err.message));
  });

  const startGame = readUrl().game || DEFAULT_GAME;
  load(startGame)
    .then(syncUrl)
    .catch((e) => { toast("Failed to load data: " + e.message); });
})();
