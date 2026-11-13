(() => {
  const STEP = 240;
  const DEFAULT_GAME = "lol";
  // Kept in step with the `out` filename of each game in build_data.py.
  const GAMES = {
    lol: "skins.json",
    wr: "skins-wr.json",
    lor: "skins-lor.json",
  };
  // The Reference tab is a board, not a game: its own catalogue, its own shape.
  const REF_FILE = "reference.json";
  // Panels every game has, before the tag groups the catalogue declares in
  // meta.tagGroups. `tiles` panels show artwork, `pills` panels are text.
  const BASE_PANELS = [
    { kind: "champs", label: "Champions", tiles: true, open: true },
    { kind: "themes", label: "Themes", tiles: true },
    { kind: "artists", label: "Artists", pills: true },
  ];
  // Filter panels of the reference board. Each value is an entry in a record's
  // `tags`, so the game panels' machinery (counts, search, only-selected) works
  // unchanged. Film records carry the film half, art records the art half.
  const REF_PANELS = [
    { kind: "director", label: "Directors", chips: true, open: true },
    { kind: "cinematographer", label: "Cinematographers", chips: true },
    { kind: "designer", label: "Production designers", chips: true },
    { kind: "genre", label: "Genres", chips: true },
    { kind: "country", label: "Countries", chips: true },
    { kind: "artist", label: "Artists", chips: true, open: true },
    { kind: "movement", label: "Movements", chips: true },
    { kind: "decade", label: "Decades", chips: true },
  ];
  // Reference rows are sized to the container, so they need the width the grid
  // actually has and a target row height rather than a fixed column count.
  const ROW_TARGET = 260;
  const ROW_TARGET_SMALL = 150;
  const ROW_GAP = 8;
  const cache = new Map();
  const state = {
    game: null,
    skins: [],
    filtered: [],
    shown: 0,
    lbIdx: -1,
    panels: BASE_PANELS,
    items: {},
    sel: {},
    onlySel: {},
    refFilms: [],
    refSrc: "",
    refQuery: "",
    refRows: [],
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

  // --- Reference board -------------------------------------------------------
  const refmode = () => state.game === "ref";

  async function fetchRef() {
    if (cache.has("ref")) return cache.get("ref");
    const p = fetch("data/" + REF_FILE)
      .then((r) => {
        if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
        return r.json();
      })
      .catch((e) => {
        cache.delete("ref");
        throw e;
      });
    cache.set("ref", p);
    return p;
  }

  // Film posters are wider than tall, paintings are all over the place. The
  // board needs one number per record to size its rows before the image loads.
  function ratioOf(text) {
    if (!text) return 0;
    const m = String(text).match(/^(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)$/);
    if (m) return parseFloat(m[1]) / parseFloat(m[2]);
    const n = parseFloat(text);
    return Number.isFinite(n) && n > 0.2 && n < 5 ? n : 0;
  }

  const yearOfText = (text) => {
    const m = String(text || "").match(/\d{4}/);
    return m ? parseInt(m[0], 10) : null;
  };

  // `tags` is what the sidebar filters on, so a film's crew and an art work's
  // movement become the same shape the game tabs already understand.
  function precomputeRef(item, i) {
    const film = item.src === "film" ? state.refFilms[item.f] || null : null;
    const clean = (arr) => [...new Set((arr || []).map((s) => String(s).trim()).filter(Boolean))];
    const tags = film
      ? {
          director: clean(film.dir),
          cinematographer: clean(film.dp),
          designer: clean(film.pd),
          genre: clean(film.gen),
          country: clean(film.cty),
        }
      : {
          artist: clean([item.cr]),
          movement: clean([item.tag]),
        };
    const year = film ? yearOfText(film.y) : yearOfText(item.y);
    if (year) tags.decade = [String(Math.floor(year / 10) * 10)];
    const title = (film ? film.t : item.t) || "Untitled";
    const creator = film ? tags.director[0] || "" : item.cr || "";
    const ar = film ? ratioOf(film.ar) : ratioOf(item.ar);
    return {
      _ref: true,
      _i: i,
      _key: `${item.src}:${item.id}`,
      _src: item.src,
      _ar: ar || 1.5,
      _label: title,
      _date: year ? String(year) : "",
      _year: year,
      _film: film,
      _item: item,
      _page: film ? film.u : item.p,
      ch: creator,
      s: title,
      img: item.u,
      t: item.u,
      tags,
      _hay: [
        title,
        creator,
        (tags.director || []).join(" "),
        (tags.cinematographer || []).join(" "),
        (tags.designer || []).join(" "),
        (tags.genre || []).join(" "),
        (tags.country || []).join(" "),
        (tags.artist || []).join(" "),
        (tags.movement || []).join(" "),
        year || "",
      ]
        .join(" ")
        .toLowerCase(),
    };
  }

  function setSortLabels(ref) {
    const opts = $("fSort").options;
    opts[2].textContent = ref ? "Title A\u2192Z" : "Champion A\u2192Z";
    opts[3].textContent = ref ? "Title Z\u2192A" : "Champion Z\u2192A";
  }

  async function loadRef() {
    const token = ++loadToken;
    const d = await fetchRef();
    if (token !== loadToken) return;
    state.game = "ref";
    state.refFilms = d.films || [];
    state.skins = (d.items || []).map(precomputeRef);
    document.title = d.meta && d.meta.label ? `${d.meta.label} Board` : "Reference Board";
    setTab("ref");
    setSortLabels(true);
    document.body.classList.add("refmode");
    $("refbar").hidden = false;
    $("fYear").hidden = true;
    $("fYear").value = "";
    buildRefSources(d.meta || {});
    buildPanels([], REF_PANELS);
    resetFilters();
    buildIndex();
    renderPanels();
    apply();
  }

  function setTab(key) {
    for (const tab of $("gametabs").children) {
      const on = tab.dataset.game === key;
      tab.classList.toggle("on", on);
      tab.setAttribute("aria-selected", on ? "true" : "false");
    }
  }

  function buildRefSources(meta) {
    const host = $("refsrc");
    host.innerHTML = "";
    const total = (meta.counts && Object.values(meta.counts).reduce((a, b) => a + b, 0)) || 0;
    const choices = [["", "All", total], ...(meta.sources || []).map(([id, label]) => [id, label, (meta.counts || {})[id] || 0])];
    for (const [id, label, count] of choices) {
      const b = document.createElement("button");
      b.type = "button";
      b.dataset.src = id;
      b.textContent = label;
      const n = document.createElement("span");
      n.className = "n";
      n.textContent = count.toLocaleString();
      b.append(n);
      b.addEventListener("click", () => {
        state.refSrc = id;
        state.shown = 0;
        syncRefSources();
        apply();
      });
      host.appendChild(b);
    }
    syncRefSources();
  }

  function syncRefSources() {
    for (const b of $("refsrc").children) {
      const on = b.dataset.src === state.refSrc;
      b.classList.toggle("on", on);
      b.setAttribute("aria-pressed", String(on));
    }
  }

  // Every selection belongs to the game it was made in: a champion chosen under
  // League means nothing in Runeterra, so a tab change starts from a clean slate.
  function resetFilters() {
    for (const k of Object.keys(state.sel)) state.sel[k].clear();
    for (const k of Object.keys(state.onlySel)) state.onlySel[k] = false;
    for (const p of state.panels) {
      const search = $(`ps${p.id}`);
      if (search) search.value = "";
      const sc = $(`sc${p.id}`);
      if (sc) sc.textContent = "";
    }
    $("fYear").value = "";
    $("refq").value = "";
    state.refQuery = "";
    state.refSrc = "";
    if (refmode()) {
      syncRefSources();
      $("grid").classList.add("refgrid");
    }
    closeLightbox();
  }

  let loadToken = 0;

  async function load(key) {
    if (key === "ref") return loadRef();
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
    document.body.classList.remove("refmode");
    $("refbar").hidden = true;
    $("fYear").hidden = false;
    $("grid").classList.remove("refgrid");
    setTab(key);
    setSortLabels(false);
    buildPanels(d.meta.tagGroups || []);
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

  // Panels are built from the catalogue, so a new tag group in build_data.py
  // needs no HTML here: meta.tagGroups names the groups and the sidebar renders
  // one panel each.
  function buildPanels(tagGroups, base = BASE_PANELS) {
    const host = $("panels");
    host.innerHTML = "";
    const panels = [...base, ...tagGroups.map(([kind, label]) => ({ kind, label, chips: true }))];
    state.panels = panels;
    state.sel = {};
    for (const p of panels) {
      p.id = cap(p.kind);
      state.sel[p.kind] = new Set();
      state.onlySel[p.kind] = false;

      const box = document.createElement("details");
      box.className = "fpanel";
      box.id = `fp${p.id}`;
      if (p.open) box.open = true;

      const summary = document.createElement("summary");
      summary.textContent = p.label;
      const sc = document.createElement("span");
      sc.className = "sc";
      sc.id = `sc${p.id}`;
      summary.append(sc);

      const ctl = document.createElement("div");
      ctl.className = "pctl";
      const search = document.createElement("input");
      search.className = "psearch";
      search.id = `ps${p.id}`;
      search.type = "search";
      search.placeholder = "Search names, comma separated";
      // Shown only once something is selected, so the panel can collapse to
      // just the chosen names without leaving a useless control in the row.
      const only = document.createElement("button");
      only.className = "ponly";
      only.id = `po${p.id}`;
      only.textContent = "Only selected";
      only.title = "Hide everything except the selected names";
      only.setAttribute("aria-pressed", "false");
      only.hidden = true;
      const all = document.createElement("button");
      all.className = "pall";
      all.textContent = "Select all";
      const none = document.createElement("button");
      none.className = "pnone";
      none.textContent = "Clear";
      ctl.append(search, only, all, none);

      const grid = document.createElement("div");
      grid.className = "pgrid" + (p.tiles ? " tiles" : " pills") + (p.chips ? " chips" : "");
      grid.id = `pg${p.id}`;

      box.append(summary, ctl, grid);
      host.appendChild(box);

      grid.addEventListener("change", () => updateSel(p.kind));
      search.addEventListener("input", () => renderPanel(p.kind));
      only.addEventListener("click", () => toggleOnlySelected(p.kind));
      all.addEventListener("click", () => panelAll(p.kind));
      none.addEventListener("click", () => panelNone(p.kind));
      // A collapsed panel builds its grid on first open: the board has thousands
      // of directors and artists, and rendering them all up front is wasted DOM.
      box.addEventListener("toggle", () => {
        if (box.open) renderPanel(p.kind);
      });
    }
  }

  const tagValues = (s, kind) => (s.tags && s.tags[kind]) || [];

  function buildIndex() {
    const tags = {};
    for (const p of state.panels) if (p.chips) tags[p.kind] = new Map();
    state.items = {};
    if (!refmode()) {
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
      const entries = (map) => [...map.entries()].map(([name, v]) => ({ name, ...v }));
      state.items = {
        champs: entries(champs).sort((a, b) => a.name.localeCompare(b.name)),
        themes: entries(themes).sort((a, b) => b.count - a.count || a.name.localeCompare(b.name)),
        artists: entries(artists).sort((a, b) => a.name.localeCompare(b.name)),
      };
    }
    for (const kind of Object.keys(tags)) {
      const bucket = tags[kind];
      for (const s of state.skins) {
        for (const v of tagValues(s, kind)) bucket.set(v, (bucket.get(v) || 0) + 1);
      }
    }
    const entries = (map) => [...map.entries()].map(([name, count]) => ({ name, count }));
    for (const p of state.panels) {
      if (!p.chips) continue;
      state.items[p.kind] = entries(tags[p.kind])
        .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
    }
  }

  function renderPanels() {
    for (const p of state.panels) {
      const box = $(`fp${p.id}`);
      if (!box || box.open) renderPanel(p.kind);
    }
  }

  // Panel searches accept several names at once, separated by commas:
  // "briar, lux" lists every champion matching either.
  const searchTokens = (kind) =>
    $(`ps${cap(kind)}`).value.split(",").map((t) => t.trim().toLowerCase()).filter(Boolean);

  // The reference board has thousands of directors and artists; a panel renders
  // the head of the list and leans on its search box instead of building 4k
  // checkboxes nobody scrolls to.
  const MAX_PANEL_ITEMS = 400;

  function renderPanel(kind) {
    const tokens = searchTokens(kind);
    const pgrid = $(`pg${cap(kind)}`);
    pgrid.innerHTML = "";
    const panel = state.panels.find((p) => p.kind === kind);
    const sel = state.sel[kind];
    // Deselecting the last name must fall back to the full list, so the empty
    // selection disables the toggle for this pass too.
    const only = state.onlySel[kind] && sel.size > 0;
    let shown = 0;
    let total = 0;
    for (const it of state.items[kind]) {
      if (only && !sel.has(it.name)) continue;
      if (tokens.length && !tokens.some((t) => it.name.toLowerCase().includes(t))) continue;
      total++;
      if (shown >= MAX_PANEL_ITEMS) continue;
      shown++;
      pgrid.appendChild(panel.tiles ? makeTile(it, sel) : makePill(it, sel));
    }
    if (total > shown) {
      const note = document.createElement("p");
      note.className = "pmore";
      note.textContent = `Showing ${shown} of ${total.toLocaleString()} — search above to narrow.`;
      pgrid.appendChild(note);
    }
    syncOnlySelected(kind);
    syncClear();
  }

  // The "Only selected" toggle keeps the panel to the chosen names. It is only
  // offered while something is selected, and turns itself off with the last
  // deselection so the panel never sticks in an empty state.
  function syncOnlySelected(kind) {
    if (!state.sel[kind].size) state.onlySel[kind] = false;
    const btn = $(`po${cap(kind)}`);
    if (!btn) return;
    const on = state.onlySel[kind];
    btn.hidden = state.sel[kind].size === 0;
    btn.classList.toggle("on", on);
    btn.setAttribute("aria-pressed", on ? "true" : "false");
  }

  function toggleOnlySelected(kind) {
    state.onlySel[kind] = !state.onlySel[kind];
    renderPanel(kind);
  }

  function makeTile(it, sel) {
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
    // While the panel is collapsed to the selection, a deselected name has to
    // leave immediately, so rebuild the grid instead of only updating counts.
    if (state.onlySel[kind]) renderPanel(kind);
    else syncOnlySelected(kind);
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
    for (const p of state.panels) {
      state.sel[p.kind] = new Set();
      state.onlySel[p.kind] = false;
      $(`sc${p.id}`).textContent = "";
    }
  }

  function hasActiveFilters() {
    const searched = state.panels.some(
      (p) => state.sel[p.kind].size > 0 || $(`ps${p.id}`).value.trim() !== ""
    );
    if (refmode()) {
      return searched || state.refQuery.trim() !== "" || state.refSrc !== "" || $("fSort").value !== "new";
    }
    return searched || $("fYear").value !== "" || $("fSort").value !== "new";
  }

  // The clear button only exists while something is actually filtered, so it
  // cannot be clicked when there is nothing to reset.
  function syncClear() {
    $("clearbtn").hidden = !hasActiveFilters();
  }

  function apply() {
    syncClear();
    if (refmode()) return applyRef();
    const year = $("fYear").value;
    const sort = $("fSort").value;

    // Within a panel the values are alternatives (OR); across panels every
    // chosen panel has to match (AND), so Kind=Monster + Vibe=Cute works.
    let list = state.skins.filter((s) => {
      for (const p of state.panels) {
        const sel = state.sel[p.kind];
        if (sel.size && !matches(s, p.kind, sel)) return false;
      }
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
    const ep = empty.querySelector("p");
    if (ep) ep.textContent = "No skins match your filters.";
    more.hidden = true;
    renderStep();
  }

  // The board filters like the game tabs (panels AND, values OR) plus one
  // free-text box over everything printed on the record, and a library chip.
  function applyRef() {
    const words = state.refQuery.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const sort = $("fSort").value;
    const list = state.skins.filter((s) => {
      if (state.refSrc && s._src !== state.refSrc) return false;
      for (const p of state.panels) {
        const sel = state.sel[p.kind];
        if (sel.size && !matches(s, p.kind, sel)) return false;
      }
      return !words.length || words.every((w) => s._hay.includes(w));
    });

    const year = (r) => (r._year == null ? -1 : r._year);
    switch (sort) {
      case "old": list.sort((a, b) => year(a) - year(b) || a._label.localeCompare(b._label)); break;
      case "az": list.sort((a, b) => a._label.localeCompare(b._label) || a.ch.localeCompare(b.ch)); break;
      case "za": list.sort((a, b) => b._label.localeCompare(a._label) || a.ch.localeCompare(b.ch)); break;
      default: list.sort((a, b) => year(b) - year(a) || a._label.localeCompare(b._label));
    }

    state.filtered = list;
    state.refRows = layoutRows(list);
    state.shown = 0;
    grid.innerHTML = "";
    empty.hidden = list.length !== 0;
    const ep = empty.querySelector("p");
    if (ep) ep.textContent = "Nothing on the board matches that.";
    more.hidden = true;
    $("refcount").textContent = `${list.length.toLocaleString()} reference${list.length === 1 ? "" : "s"}`;
    renderStep();
  }

  // Justified rows: each row is filled until the images would be shorter than
  // the target height, then scaled to exactly fill the width. That keeps the
  // artwork's own ratios (a 2.39:1 frame stays wide) and gives the board its
  // edge-to-edge look without leaving a ragged bottom.
  function layoutRows(list) {
    const cs = getComputedStyle(grid);
    const width =
      grid.clientWidth - parseFloat(cs.paddingLeft || 0) - parseFloat(cs.paddingRight || 0) || 1200;
    const target = width < 700 ? ROW_TARGET_SMALL : ROW_TARGET;
    const rows = [];
    let i = 0;
    while (i < list.length) {
      let sum = 0;
      let j = i;
      let h = target;
      while (j < list.length) {
        sum += list[j]._ar;
        j++;
        h = (width - ROW_GAP * (j - i - 1)) / sum;
        if (h <= target) break;
      }
      rows.push({ start: i, end: j, h: Math.max(80, Math.min(h, target * 1.6)) });
      i = j;
    }
    return rows;
  }

  function matches(rec, kind, sel) {
    if (kind === "champs") return sel.has(rec.ch);
    if (kind === "themes") return (rec.set || []).some((t) => sel.has(t));
    if (kind === "artists") return (rec.art || []).some((a) => sel.has(a));
    return tagValues(rec, kind).some((v) => sel.has(v));
  }

  function renderStep() {
    if (refmode()) return renderRefRows();
    const next = Math.min(state.filtered.length, state.shown + STEP);
    for (let i = state.shown; i < next; i++) grid.appendChild(makeCard(state.filtered[i], i));
    state.shown = next;
    more.hidden = state.shown >= state.filtered.length;
    sentinel().style.display = more.hidden ? "none" : "block";
  }

  function renderRefRows(max = state.shown + 12) {
    const rows = state.refRows;
    const next = Math.min(rows.length, max);
    for (let i = state.shown; i < next; i++) {
      const row = rows[i];
      const el = document.createElement("div");
      el.className = "rrow";
      el.style.height = row.h + "px";
      for (let k = row.start; k < row.end; k++) el.appendChild(makeCard(state.filtered[k], k));
      grid.appendChild(el);
    }
    state.shown = next;
    more.hidden = state.shown >= rows.length;
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
    if (rec._ref) return makeRefCard(rec, idx);
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

  // A board tile: no chrome, no caption until hovered.
  function makeRefCard(rec, idx) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "rcard";
    card.dataset.idx = idx;
    card.style.flex = `${rec._ar} 1 0`;
    card.setAttribute("aria-label", `${rec._label}${rec.ch ? " - " + rec.ch : ""}`);

    const img = document.createElement("img");
    img.loading = "lazy";
    img.src = rec.img;
    img.alt = rec._label;
    card.appendChild(img);

    const ov = document.createElement("span");
    ov.className = "rov";
    const t = document.createElement("span");
    t.className = "rt";
    t.textContent = rec._label;
    const sub = document.createElement("span");
    sub.className = "rs";
    const f = rec._film;
    sub.textContent = f
      ? [rec.tags.director[0], f.y].filter(Boolean).join(" · ")
      : [rec._item.cr, rec._item.y, rec._item.tag].filter(Boolean).join(" · ");
    ov.append(t, sub);
    card.appendChild(ov);

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

    if (rec._ref) return openRefLightbox(rec, idx, wasHidden);

    $("lbName").textContent = `${rec.ch} - ${label}`;
    $("lbChamp").textContent = rec.ch;
    $("lbPos").textContent = `${idx + 1} of ${state.filtered.length}`;

    const info = $("lbInfo");
    info.innerHTML = "";
    const t = rec.tags || {};
    const rows = [
      ["Vibes", (t.vibe || []).join(", ")],
      ["Kind", (t.kind || []).join(", ")],
      ["Species", (t.species || []).join(", ")],
      ["Gender", (t.gender || []).join(", ")],
      ["Region", (t.region || []).join(", ")],
      ["Class", (t.class || []).join(", ")],
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

  // The board's detail view reuses the splash lightbox: same zoom lens, same
  // arrow keys. Only the metadata block and the title differ.
  function openRefLightbox(rec, idx, wasHidden) {
    const f = rec._film;
    const tg = rec.tags || {};
    $("lbName").textContent = rec._label;
    $("lbChamp").textContent = (tg.director || []).join(", ") || (tg.artist || []).join(", ");
    $("lbPos").textContent = `${idx + 1} of ${state.filtered.length}`;

    const info = $("lbInfo");
    info.innerHTML = "";
    const rows = f
      ? [
          ["Director", (tg.director || []).join(", ")],
          ["Cinematography", (tg.cinematographer || []).join(", ")],
          ["Production design", (tg.designer || []).join(", ")],
          ["Genre", (tg.genre || []).join(", ")],
          ["Country", (tg.country || []).join(", ")],
          ["Year", f.y],
          ["Aspect ratio", f.ar],
        ]
      : [
          ["Artist", (tg.artist || []).join(", ")],
          ["Movement", (tg.movement || []).join(", ")],
          ["Year", rec._item.y],
        ];
    for (const [k, v] of rows) {
      if (!v) continue;
      const dt = document.createElement("dt");
      dt.textContent = k;
      const dd = document.createElement("dd");
      dd.textContent = v;
      info.append(dt, dd);
    }
    if (rec._page) {
      const dt = document.createElement("dt");
      dt.textContent = "Source";
      const dd = document.createElement("dd");
      const a = document.createElement("a");
      a.href = rec._page;
      a.target = "_blank";
      a.rel = "noopener";
      a.textContent = f ? "film-grab.com" : "imaginemore.art";
      dd.appendChild(a);
      info.append(dt, dd);
    }

    rec._curVer = 0;
    loadLbImage(rec);
    $("lbImgWrap").scrollTop = 0;
    $("lbStage").scrollTop = 0;
    renderVersions(rec);

    lb.hidden = false;
    document.body.style.overflow = "hidden";
    writeUrl(null, null);
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
  // The board shares a frame instead: ?game=ref&r=film:Bullet_Train_01.jpg
  function readUrl() {
    const p = new URLSearchParams(location.search);
    const game = p.get("game");
    const known = game === "ref" || (game && Object.hasOwn(GAMES, game));
    return {
      game: known ? game : null,
      champ: p.get("champ"),
      skin: p.get("skin"),
      ref: p.get("r"),
    };
  }

  function writeUrl(champ, skin) {
    const p = new URLSearchParams(location.search);
    p.set("game", state.game || DEFAULT_GAME);
    p.delete("champ");
    p.delete("skin");
    p.delete("r");
    if (champ && skin) {
      p.set("champ", champ);
      p.set("skin", skin);
    }
    if (state.game === "ref" && state.lbIdx >= 0) p.set("r", state.filtered[state.lbIdx]._key);
    history.replaceState(null, "", `${location.pathname}?${p}`);
  }

  function syncUrl() {
    const u = readUrl();
    if (u.game && u.game !== state.game) {
      load(u.game).catch((e) => toast("Failed to load data: " + e.message));
      return;
    }
    const idx = refmode()
      ? u.ref
        ? state.filtered.findIndex((s) => s._key === u.ref)
        : -1
      : u.champ && u.skin
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
    for (const p of state.panels) $(`ps${p.id}`).value = "";
    resetPanels();
    $("fYear").value = "";
    $("fSort").value = "new";
    if (refmode()) {
      $("refq").value = "";
      state.refQuery = "";
      state.refSrc = "";
      syncRefSources();
    }
    renderPanels();
    apply();
  });

  // The board's search is one text box over every printed field, so "rogers
  // night" finds a Deakins film and "monet" finds the paintings. Re-filtering
  // 40k records per keystroke is cheap; rebuilding the rows is not, hence the
  // frame throttle.
  let refSearchRaf = 0;
  $("refq").addEventListener("input", () => {
    state.refQuery = $("refq").value;
    if (refSearchRaf) return;
    refSearchRaf = requestAnimationFrame(() => {
      refSearchRaf = 0;
      apply();
    });
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

  // Row heights depend on the width, so a resize re-flows the board. The rows
  // already on screen are re-rendered to keep the reader roughly in place.
  let refResizeTimer = 0;
  window.addEventListener("resize", () => {
    if (!refmode()) return;
    clearTimeout(refResizeTimer);
    refResizeTimer = setTimeout(() => {
      const keep = state.shown;
      state.refRows = layoutRows(state.filtered);
      state.shown = 0;
      grid.innerHTML = "";
      renderRefRows(Math.min(keep, state.refRows.length));
    }, 200);
  });

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
