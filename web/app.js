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
    { kind: "scene", label: "Scenes", chips: true, open: true },
    { kind: "setting", label: "Setting", chips: true },
    { kind: "atmosphere", label: "Light & weather", chips: true },
    { kind: "framing", label: "Framing", chips: true },
    { kind: "mood", label: "Mood", chips: true },
  ];
  // The scene facets every tagged image gets, whether it is a film still, a
  // painting or a splash. build_data.py writes the same names into a game's
  // meta.tagGroups, so both sides of the app read them the same way.
  const SCENE_GROUPS = [
    ["scene", "Scenes"],
    ["setting", "Setting"],
    ["atmosphere", "Light & weather"],
    ["framing", "Framing"],
    ["mood", "Mood"],
  ];
  // Reference rows are sized to the container, so they need the width the grid
  // actually has and a target row height rather than a fixed column count.
  const ROW_TARGET = 260;
  const ROW_TARGET_SMALL = 150;
  const ROW_GAP = 8;
  // Home shelves. Counts are the catalogue sizes at the last data refresh; the
  // browse header replaces them with the real number once a library loads.
  const LIBRARIES = [
    {
      id: "lol",
      name: "League of Legends",
      sub: "Splash art · every champion",
      count: 1944,
      cover: "https://wiki.leagueoflegends.com/en-us/images/thumb/Ahri_SpiritBlossomSkin_HD.jpg/1200px-Ahri_SpiritBlossomSkin_HD.jpg",
    },
    {
      id: "wr",
      name: "Wild Rift",
      sub: "Ports and originals",
      count: 1063,
      cover: "https://wiki.leagueoflegends.com/en-us/images/thumb/Lillia_CottontailSkin_WR_HD.jpg/1200px-Lillia_CottontailSkin_WR_HD.jpg",
    },
    {
      id: "lor",
      name: "Legends of Runeterra",
      sub: "Card art, full bleed",
      count: 272,
      cover: "https://wiki.leagueoflegends.com/en-us/images/thumb/02DE006_StarGuardian-HD-full.jpg/1200px-02DE006_StarGuardian-HD-full.jpg",
    },
    {
      id: "ref",
      name: "Reference",
      sub: "Film stills · paintings",
      count: 32363,
      cover: "https://film-grab.com/wp-content/uploads/photo-gallery/La_Bete_Humaine_010.jpg",
    },
  ];
  const cache = new Map();
  const BOARD_KEY = "splash.board";
  const DENSITY_KEY = "splash.density";

  function loadBoard() {
    try {
      const raw = JSON.parse(localStorage.getItem(BOARD_KEY) || "[]");
      return Array.isArray(raw) ? raw.filter((e) => e && e.key && e.img) : [];
    } catch {
      return [];
    }
  }

  const state = {
    game: null,
    view: "home",
    query: "",
    density: localStorage.getItem(DENSITY_KEY) || "m",
    board: loadBoard(),
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
  const BOOKMARK =
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7.2 4h9.6A1.2 1.2 0 0 1 18 5.2V20l-6-4.2L6 20V5.2A1.2 1.2 0 0 1 7.2 4z"/></svg>';

  // Zoom-and-pan viewer state: scale plus a screen-pixel offset.
  let zoom = 1;
  let panX = 0;
  let panY = 0;
  let panning = false;
  let panFromX = 0;
  let panFromY = 0;
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
    rec._key = `${state.game}:${rec.ch}:${rec.s}`;
    rec._label = skinLabel(rec);
    const rOk = rec.r && /^\d{4}-\d{2}-\d{2}$/.test(rec.r);
    rec._date = rec.d || (rOk ? rec.r : null) || null;
    rec._year = yearOf(rec);
    // One haystack per record so the search box stays a substring scan.
    rec._hay = [
      rec.ch,
      rec.s,
      rec._label,
      (rec.set || []).join(" "),
      (rec.art || []).join(" "),
      Object.values(rec.tags || {}).flat().join(" "),
      rec.cap || "",
    ]
      .join(" ")
      .toLowerCase();
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

  // Byte-identical splashes from build_dupes.py: some skins ship the same
  // painting (Cafe Cuties, True Damage, event art). Fetched once.
  async function fetchDupes() {
    if (cache.has("dupes")) return cache.get("dupes");
    const p = fetch("data/dupes.json")
      .then((r) => (r.ok ? r.json() : {}))
      .catch(() => ({}));
    cache.set("dupes", p);
    return p;
  }

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
    // Scene facets come from tag_images.py: closed lists, so a phrase like
    // "train station" is one exact filter value instead of three loose words.
    const sc = item.sc;
    if (sc) {
      if (sc.place && sc.place.length) tags.scene = sc.place;
      if (sc.setting && sc.setting !== "unknown") tags.setting = [sc.setting];
      const atmos = [...(sc.light || []), ...(sc.weather || [])];
      if (atmos.length) tags.atmosphere = atmos;
      const framing = [...(sc.people && sc.people !== "none" ? [sc.people] : []), ...(sc.shot ? [sc.shot] : [])];
      if (framing.length) tags.framing = framing;
      if (sc.mood && sc.mood.length) tags.mood = sc.mood;
    }
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
      _hay: [title, creator, Object.values(tags).flat().join(" "), item.cap || "", year || ""]
        .join(" ")
        .toLowerCase(),
    };
  }

  function setSortLabels(ref) {
    const opts = $("fSort").options;
    opts[2].textContent = ref ? "Title A\u2192Z" : "Champion A\u2192Z";
    opts[3].textContent = ref ? "Title Z\u2192A" : "Champion Z\u2192A";
  }

  // Variant and prestige skins reuse their base splash, so the raw catalogue
  // puts the same painting on the wall three times. Keep one card and list the
  // other skins on it instead.
  function collapseVariants(dupes = {}) {
    const byGroup = new Map();
    let unique = 0;
    for (const rec of state.skins) {
      rec._dup = false;
      rec._also = null;
      rec._dupCount = 0;
      const groupKey = dupes[rec._key] || rec._key;
      const group = byGroup.get(groupKey);
      if (group) {
        group.also.push(rec);
        rec._dup = true;
      } else {
        byGroup.set(groupKey, { primary: rec, also: [] });
        unique++;
      }
    }
    const byImg = byGroup;
    for (const { primary, also } of byImg.values()) {
      if (also.length) {
        primary._also = also;
        primary._dupCount = also.length;
      }
    }
    state.uniqueCount = unique;
  }

  // --- Board: save what you want to keep ------------------------------------
  const onBoard = (key) => state.board.some((e) => e.key === key);

  function persistBoard() {
    try {
      localStorage.setItem(BOARD_KEY, JSON.stringify(state.board));
    } catch {
      /* storage full or blocked: the board still works for this session */
    }
    syncBoard();
  }

  function toggleSave(rec, el) {
    const i = state.board.findIndex((e) => e.key === rec._key);
    if (i >= 0) {
      state.board.splice(i, 1);
    } else {
      state.board.unshift({
        key: rec._key,
        label: rec._label,
        ch: rec.ch || "",
        img: rec.img,
        t: rec.t || rec.img,
        game: state.game,
      });
      toast("Saved to board");
    }
    const on = i < 0;
    for (const btn of grid.querySelectorAll(".save")) {
      if (btn.dataset.key !== rec._key) continue;
      btn.classList.toggle("on", on);
      btn.setAttribute("aria-pressed", String(on));
      btn.title = on ? "Remove from board" : "Save to board";
    }
    persistBoard();
    if ($("board").classList.contains("open")) renderBoard();
  }

  function syncBoard() {
    const n = state.board.length;
    const badge = $("boardBadge");
    badge.textContent = n;
    badge.hidden = n === 0;
    $("boardBtn").classList.toggle("has-items", n > 0);
    $("boardCount").textContent = n ? `(${n})` : "";
    $("boardCopy").hidden = n === 0;
    $("boardClear").hidden = n === 0;
  }

  function renderBoard() {
    const host = $("boardBody");
    host.innerHTML = "";
    if (!state.board.length) {
      const p = document.createElement("p");
      p.className = "board-empty";
      p.textContent = "Nothing saved yet. Tap the bookmark on any tile, or press S in the viewer.";
      host.appendChild(p);
      return;
    }
    const list = document.createElement("div");
    list.className = "board-grid";
    for (const e of state.board) {
      const item = document.createElement("div");
      item.className = "board-item";
      const img = document.createElement("img");
      img.src = e.t || e.img;
      img.loading = "lazy";
      img.alt = e.label;
      const label = document.createElement("span");
      label.className = "board-label";
      label.textContent = e.ch ? `${e.ch} - ${e.label}` : e.label;
      const rm = document.createElement("button");
      rm.type = "button";
      rm.className = "board-rm";
      rm.textContent = "\u00d7";
      rm.title = "Remove from board";
      rm.setAttribute("aria-label", `Remove ${label.textContent}`);
      rm.addEventListener("click", (ev) => {
        ev.stopPropagation();
        state.board = state.board.filter((x) => x.key !== e.key);
        persistBoard();
        renderBoard();
      });
      item.append(img, label, rm);
      item.addEventListener("click", () => {
        const idx = state.filtered.findIndex((r) => r._key === e.key);
        if (idx >= 0) {
          closeBoard();
          openLightbox(idx);
        } else {
          window.open(e.img, "_blank", "noopener");
        }
      });
      list.appendChild(item);
    }
    host.appendChild(list);
  }

  function buildSaveButton(rec) {
    const save = document.createElement("span");
    const on = onBoard(rec._key);
    save.className = "save" + (on ? " on" : "");
    save.dataset.key = rec._key;
    save.setAttribute("role", "button");
    save.tabIndex = 0;
    save.title = on ? "Remove from board" : "Save to board";
    save.setAttribute("aria-pressed", String(on));
    save.innerHTML = BOOKMARK;
    save.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      toggleSave(rec, save);
      save.title = onBoard(rec._key) ? "Remove from board" : "Save to board";
    });
    save.addEventListener("keydown", (e) => {
      if (e.key !== "Enter" && e.key !== " ") return;
      e.preventDefault();
      e.stopPropagation();
      toggleSave(rec, save);
    });
    return save;
  }

  function applyDensity() {
    for (const b of $("density").children) b.classList.toggle("on", b.dataset.density === state.density);
    grid.classList.remove("d-s", "d-m", "d-l");
    grid.classList.add("d-" + state.density);
    try {
      localStorage.setItem(DENSITY_KEY, state.density);
    } catch {
      /* ignore */
    }
    apply();
  }

  async function loadRef() {
    const token = ++loadToken;
    const d = await fetchRef();
    if (token !== loadToken) return;
    state.game = "ref";
    state.refFilms = d.films || [];
    state.skins = (d.items || []).map(precomputeRef);
    state.uniqueCount = state.skins.length;
    document.title = d.meta && d.meta.label ? `${d.meta.label} Board` : "Reference Board";
    setSortLabels(true);
    showBrowse("ref", d.meta || {});
    $("subbar").hidden = false;
    $("fYear").hidden = true;
    $("fYear").value = "";
    $("champstrip").hidden = true;
    buildRefSources(d.meta || {});
    buildPanels([], REF_PANELS);
    resetFilters();
    buildIndex();
    renderPanels();
    restoreFilters();
    apply();
  }

  function showBrowse(key, meta) {
    state.view = "browse";
    $("home").hidden = true;
    $("browse").hidden = false;
    window.scrollTo(0, 0);
    const lib = LIBRARIES.find((l) => l.id === key);
    $("libName").textContent = (meta && meta.label) || (lib && lib.name) || "Reference";
    $("q").placeholder =
      key === "ref" ? "Search films, directors, artists, places\u2026" : "Search champions, skins, artists\u2026";
    updateHeaderCount();
    syncDrawerState();
  }

  function updateHeaderCount() {
    const n = state.uniqueCount || state.skins.length;
    const lib = LIBRARIES.find((l) => l.id === state.game);
    const noun = state.game === "ref" || state.game === "lor" ? "pieces" : state.game === "lol" ? "splashes" : "cosmetics";
    $("libCount").textContent = n
      ? `${n.toLocaleString()} ${noun}`
      : lib
        ? `${lib.count.toLocaleString()} ${noun}`
        : "";
  }

  function goHome() {
    closeLightbox();
    closeDrawer();
    state.view = "home";
    state.query = "";
    $("q").value = "";
    $("home").hidden = false;
    $("browse").hidden = true;
    $("grid").innerHTML = "";
    $("empty").hidden = true;
    $("more").hidden = true;
    document.title = "Splash Reference";
    history.replaceState(null, "", location.pathname);
    window.scrollTo(0, 0);
  }

  function openLibrary(key) {
    if (!key) return;
    state.query = "";
    $("q").value = "";
    // Show the library shell at once; a 13 MB reference file takes a moment.
    showBrowse(key, LIBRARIES.find((l) => l.id === key) || null);
    showSkeleton(key);
    load(key).then(() => writeUrl(null)).catch((e) => toast("Failed to load data: " + e.message));
  }

  function showSkeleton(key) {
    grid.classList.toggle("refgrid", key === "ref");
    grid.innerHTML = "";
    empty.hidden = true;
    more.hidden = true;
    const n = key === "ref" ? 8 : 6;
    for (let i = 0; i < n; i++) {
      const s = document.createElement("div");
      s.className = "skel";
      grid.appendChild(s);
    }
    $("libCount").textContent = "Loading…";
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

  // Every selection belongs to the library it was made in: a champion chosen
  // under League means nothing in Runeterra, so a switch starts clean.
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
    if (!restoringFilters) {
      state.query = "";
      state.refQuery = "";
      state.refSrc = "";
      $("q").value = "";
    }
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
    // Two quick clicks resolve out of order; only the last one may paint.
    const token = ++loadToken;
    const d = await fetchGame(key);
    if (token !== loadToken) return;
    state.game = key;
    state.skins = d.skins.map(precompute);
    const dupes = (await fetchDupes())[key] || {};
    collapseVariants(dupes);
    // Each game crops artwork to its own native ratio; the CSS reads this.
    const [w, h] = d.meta.aspect || [1215, 717];
    document.documentElement.style.setProperty("--ar", `${w} / ${h}`);
    document.title = d.meta.label ? `${d.meta.label} Splash Reference` : "Splash Reference";
    showBrowse(key, d.meta);
    $("subbar").hidden = true;
    $("champstrip").hidden = false;
    $("fYear").hidden = false;
    $("grid").classList.remove("refgrid");
    setSortLabels(false);
    buildPanels(d.meta.tagGroups || []);
    resetFilters();
    buildIndex();
    buildSelects();
    renderPanels();
    restoreFilters();
    buildChampStrip();
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

  // The champion strip is the fast lane: one row of avatars that scrolls
  // sideways, multi-select like the panel, so a whole lane is two clicks.
  function buildChampStrip() {
    const host = $("champstrip");
    host.innerHTML = "";
    const all = document.createElement("button");
    all.type = "button";
    all.className = "champchip all";
    all.dataset.champ = "";
    all.title = "All champions";
    const allImg = document.createElement("span");
    allImg.className = "cimg";
    const allName = document.createElement("span");
    allName.textContent = "All";
    all.append(allImg, allName);
    all.addEventListener("click", () => {
      state.sel.champs.clear();
      $(`scChamps`).textContent = "";
      syncChampStrip();
      if ($("fpChamps") && $("fpChamps").open) renderPanel("champs");
      apply();
    });
    host.appendChild(all);

    for (const it of state.items.champs || []) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "champchip";
      b.dataset.champ = it.name;
      b.title = `${it.name} (${it.count})`;
      const wrap = document.createElement("span");
      wrap.className = "cimg";
      const img = document.createElement("img");
      img.loading = "lazy";
      img.src = thumbAt(it.rec.t || it.rec.img, 120);
      img.alt = it.name;
      wrap.appendChild(img);
      const nm = document.createElement("span");
      nm.textContent = it.name;
      b.append(wrap, nm);
      b.addEventListener("click", () => toggleChamp(it.name));
      host.appendChild(b);
    }
    syncChampStrip();
  }

  function toggleChamp(name) {
    const sel = state.sel.champs;
    if (sel.has(name)) sel.delete(name);
    else sel.add(name);
    const badge = $("scChamps");
    if (badge) badge.textContent = sel.size ? `(${sel.size})` : "";
    syncChampStrip();
    if ($("fpChamps") && $("fpChamps").open) renderPanel("champs");
    apply();
  }

  function syncChampStrip() {
    for (const b of $("champstrip").querySelectorAll(".champchip")) {
      const on = b.dataset.champ ? state.sel.champs.has(b.dataset.champ) : state.sel.champs.size === 0;
      b.classList.toggle("on", on);
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
    if (kind === "champs") syncChampStrip();
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

  function activeFilterCount() {
    let n = 0;
    for (const p of state.panels) {
      if (state.sel[p.kind].size) n++;
      if ($(`ps${p.id}`) && $(`ps${p.id}`).value.trim()) n++;
    }
    if (state.query.trim()) n++;
    if (refmode() && state.refSrc) n++;
    if ($("fYear").value) n++;
    if ($("fSort").value !== "new") n++;
    return n;
  }

  function hasActiveFilters() {
    return activeFilterCount() > 0;
  }

  // The clear button only exists while something is actually filtered, so it
  // cannot be clicked when there is nothing to reset.
  function syncClear() {
    const n = activeFilterCount();
    const clear = $("clearbtn");
    if (clear) clear.hidden = n === 0;
    const badge = $("filterCount");
    if (badge) {
      badge.textContent = n;
      badge.hidden = n === 0;
    }
    $("filterBtn").classList.toggle("has-filters", n > 0);
    $("qClear").hidden = !state.query;
  }

  // Filters live in the URL too: ?game=lol&f=vibe:Cute|kind:Monster&q=star
  // so a filtered view can be bookmarked or sent to someone.
  let restoringFilters = false;

  function writeFilterUrl() {
    if (restoringFilters) return;
    const p = new URLSearchParams(location.search);
    const q = state.query.trim();
    if (q) p.set("q", q);
    else p.delete("q");
    if (refmode() && state.refSrc) p.set("src", state.refSrc);
    else p.delete("src");
    const sort = $("fSort").value;
    if (sort !== "new") p.set("sort", sort);
    else p.delete("sort");
    const year = $("fYear").value;
    if (year) p.set("y", year);
    else p.delete("y");
    const picked = [];
    for (const panel of state.panels) {
      for (const value of state.sel[panel.kind]) picked.push(`${panel.kind}:${value}`);
    }
    if (picked.length) p.set("f", picked.join("|"));
    else p.delete("f");
    history.replaceState(null, "", `${location.pathname}?${p}`);
  }

  function restoreFilters() {
    const p = new URLSearchParams(location.search);
    restoringFilters = true;
    const q = p.get("q");
    if (q) {
      state.query = q;
      $("q").value = q;
    }
    const src = p.get("src");
    if (src && refmode()) {
      state.refSrc = src;
      syncRefSources();
    }
    const sort = p.get("sort");
    if (sort && $("fSort").querySelector(`option[value="${sort}"]`)) $("fSort").value = sort;
    const year = p.get("y");
    if (year && $("fYear").querySelector(`option[value="${year}"]`)) $("fYear").value = year;
    const f = p.get("f");
    if (f) {
      for (const pair of f.split("|")) {
        const cut = pair.indexOf(":");
        if (cut < 0) continue;
        const kind = pair.slice(0, cut);
        const value = pair.slice(cut + 1);
        if (state.sel[kind]) state.sel[kind].add(value);
      }
    }
    restoringFilters = false;
  }

  function apply() {
    syncClear();
    if (refmode()) return applyRef();
    const year = $("fYear").value;
    const sort = $("fSort").value;
    const words = state.query.trim().toLowerCase().split(/\s+/).filter(Boolean);

    // Within a panel the values are alternatives (OR); across panels every
    // chosen panel has to match (AND), so Kind=Monster + Vibe=Cute works.
    let list = state.skins.filter((s) => {
      if (s._dup) return false;
      for (const p of state.panels) {
        const sel = state.sel[p.kind];
        if (sel.size && !matches(s, p.kind, sel)) return false;
      }
      if (year && String(s._year) !== year) return false;
      if (words.length && !words.every((w) => s._hay.includes(w))) return false;
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
    $("drawerApply").textContent = `Show ${list.length.toLocaleString()} ${list.length === 1 ? "result" : "results"}`;
    writeFilterUrl();
    renderStep();
  }

  // The board filters like the game libraries (panels AND, values OR) plus one
  // free-text box over everything printed on the record, and a library chip.
  // Film stills are grouped by film, so the wall reads as contact sheets and
  // "newest first" means newest *film*, not the item with the most stills.
  function applyRef() {
    const words = state.query.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const sort = $("fSort").value;
    const list = state.skins.filter((s) => {
      if (state.refSrc && s._src !== state.refSrc) return false;
      for (const p of state.panels) {
        const sel = state.sel[p.kind];
        if (sel.size && !matches(s, p.kind, sel)) return false;
      }
      return !words.length || words.every((w) => s._hay.includes(w));
    });

    const groups = new Map();
    for (const s of list) {
      const key = s._film || "paintings";
      let group = groups.get(key);
      if (!group) {
        group = { film: s._film || null, items: [] };
        groups.set(key, group);
      }
      group.items.push(s);
    }
    const films = [...groups.values()].filter((g) => g.film);
    const rest = [...groups.values()].filter((g) => !g.film);
    const fy = (g) => {
      const y = g.film ? yearOfText(g.film.y) : null;
      return y == null ? null : y;
    };
    // Undated films go last in both directions rather than sorting as year 0.
    const dated = films.filter((g) => fy(g) != null);
    const undated = films.filter((g) => fy(g) == null);
    switch (sort) {
      case "old":
        dated.sort((a, b) => fy(a) - fy(b) || a.film.t.localeCompare(b.film.t));
        films.splice(0, films.length, ...dated, ...undated);
        break;
      case "az":
        films.sort((a, b) => a.film.t.localeCompare(b.film.t));
        break;
      case "za":
        films.sort((a, b) => b.film.t.localeCompare(a.film.t));
        break;
      default:
        dated.sort((a, b) => fy(b) - fy(a) || a.film.t.localeCompare(b.film.t));
        films.splice(0, films.length, ...dated, ...undated);
    }
    if (sort === "az" || sort === "za") {
      rest.sort((a, b) => a.items[0]._label.localeCompare(b.items[0]._label) * (sort === "az" ? 1 : -1));
    }
    const ordered = [...films, ...rest];
    state.refGroups = ordered;
    const flat = ordered.flatMap((g) => g.items);

    state.filtered = flat;
    state.refRows = layoutRefRows(flat);
    state.shown = 0;
    grid.innerHTML = "";
    empty.hidden = list.length !== 0;
    const ep = empty.querySelector("p");
    if (ep) ep.textContent = "Nothing on the board matches that.";
    more.hidden = true;
    $("refcount").textContent = `${flat.length.toLocaleString()} reference${flat.length === 1 ? "" : "s"}`;
    $("refcount").hidden = !state.query.trim() && !state.refSrc;
    $("drawerApply").textContent = `Show ${flat.length.toLocaleString()} ${flat.length === 1 ? "result" : "results"}`;
    writeFilterUrl();
    renderStep();
  }

  // Justified rows: each row is filled until the images would be shorter than
  // the target height, then scaled to exactly fill the width. That keeps the
  // artwork's own ratios (a 2.39:1 frame stays wide) and gives the board its
  // edge-to-edge look without leaving a ragged bottom.
  function layoutRefRows(list) {
    const cs = getComputedStyle(grid);
    const width =
      grid.clientWidth - parseFloat(cs.paddingLeft || 0) - parseFloat(cs.paddingRight || 0) || 1200;
    const target =
      width < 700
        ? ROW_TARGET_SMALL
        : state.density === "s"
          ? 190
          : state.density === "l"
            ? 360
            : ROW_TARGET;
    const rows = [];
    let i = 0;
    while (i < list.length) {
      const film = list[i]._film;
      let count = 1;
      while (i + count < list.length && list[i + count]._film === film) count++;
      if (film) rows.push({ type: "head", rec: list[i], count });
      let k = i;
      while (k < i + count) {
        let sum = 0;
        let j = k;
        let h = target;
        while (j < i + count) {
          sum += list[j]._ar;
          j++;
          h = (width - ROW_GAP * (j - k - 1)) / sum;
          if (h <= target) break;
        }
        rows.push({ type: "row", start: k, end: j, h: Math.max(80, Math.min(h, target * 1.6)) });
        k = j;
      }
      i += count;
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
      if (row.type === "head") {
        grid.appendChild(makeRefHead(row));
        continue;
      }
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
    const bits = [(rec.set || []).join(", ") || "", (rec.art || [])[0] || ""].filter(Boolean);
    if (rec._dupCount) bits.push(`Shared by ${rec._dupCount + 1} skins`);
    sub.textContent = bits.join(" · ");
    meta.append(name, sub);
    card.appendChild(meta);
    card.appendChild(buildSaveButton(rec));

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

  function makeRefHead(row) {
    const f = row.rec._film;
    const el = document.createElement("div");
    el.className = "rgroup";
    const title = document.createElement("h3");
    title.textContent = f.t;
    const meta = document.createElement("span");
    meta.textContent = [f.y, (f.dir || [])[0], `${row.count} still${row.count === 1 ? "" : "s"}`]
      .filter(Boolean)
      .join("  ·  ");
    el.append(title, meta);
    return el;
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
    // Film stills need no per-tile caption: the group header above them already
    // names the film, the year and the director.
    if (!f) {
      ov.append(t, sub);
      card.appendChild(ov);
    }
    card.appendChild(buildSaveButton(rec));

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
      resetZoom();
      resetZoom();
    };
    full.onerror = () => bar.classList.remove("active");

    img.src = thumbAt(rec.t || rec.img, 1200);
    bar.classList.add("active");
  }

  // Images open in place and leave the URL alone; stepping keeps lightbox focus.
  let lastFocus = null;

  // Metadata is grouped so the eye can scan it: identity, artwork, dates.
  function renderInfo(info, groups) {
    info.innerHTML = "";
    for (const [title, rows] of groups) {
      const visible = rows.filter(([, v]) => v);
      if (!visible.length) continue;
      const head = document.createElement("dt");
      head.className = "lb-sec";
      head.textContent = title;
      info.appendChild(head);
      for (const [k, v] of visible) {
        const dd = document.createElement("dd");
        dd.textContent = v;
        if (!k) {
          dd.style.gridColumn = "1 / -1";
        } else {
          const dt = document.createElement("dt");
          dt.textContent = k;
          info.appendChild(dt);
        }
        if (k === "Resolution") dd.id = "lbRes";
        info.appendChild(dd);
      }
    }
  }

  function openLightbox(idx) {
    state.lbIdx = idx;
    const rec = state.filtered[idx];
    const label = rec._label;
    const wasHidden = lb.hidden;
    if (wasHidden) lastFocus = document.activeElement;

    if (rec._ref) return openRefLightbox(rec, idx, wasHidden);

    $("lbName").textContent = `${rec.ch} - ${label}`;
    $("lbChamp").textContent = rec.ch;
    $("lbPos").textContent = `${idx + 1} / ${state.filtered.length.toLocaleString()}`;

    const info = $("lbInfo");
    const t = rec.tags || {};
    renderInfo(info, [
      [
        "Champion",
        [
          ["Kind", (t.kind || []).join(", ")],
          ["Species", (t.species || []).join(", ")],
          ["Gender", (t.gender || []).join(", ")],
          ["Region", (t.region || []).join(", ")],
          ["Class", (t.class || []).join(", ")],
        ],
      ],
      [
        "Artwork",
        [
          ["Vibes", (t.vibe || []).join(", ")],
          ["Themes", (rec.set || []).join(", ")],
          ["Artists", (rec.art || []).join(", ")],
          ["Chromas", rec.cr > 0 ? `${rec.cr} chromas` : "None"],
          ["Also used by", rec._also ? rec._also.map((r) => `${r._label} (${r.ch})`).join(", ") : ""],
        ],
      ],
      [
        "Dates",
        [
          ["Artwork", rec.d],
          ["Release", rec.r],
          ["Resolution", resText(rec) ? `${resText(rec)} px` : ""],
        ],
      ],
    ]);

    // The side panel always starts on the newest artwork, so the highlighted
    // version button and the loaded image cannot drift apart.
    rec._curVer = 0;
    loadLbImage(rec);
    $("lbImgWrap").scrollTop = 0;
    $("lbStage").scrollTop = 0;

    renderVersions(rec);
    renderNearby(idx);
    syncLbSave(rec);

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
    $("lbPos").textContent = `${idx + 1} / ${state.filtered.length.toLocaleString()}`;

    const info = $("lbInfo");
    const groups = f
      ? [
          [
            "Film",
            [
              ["Director", (tg.director || []).join(", ")],
              ["Cinematography", (tg.cinematographer || []).join(", ")],
              ["Production design", (tg.designer || []).join(", ")],
              ["Genre", (tg.genre || []).join(", ")],
              ["Country", (tg.country || []).join(", ")],
              ["Year", f.y],
              ["Aspect", f.ar],
            ],
          ],
          [
            "Scene",
            [
              ["Place", (tg.scene || []).join(", ")],
              ["Light", (tg.atmosphere || []).join(", ")],
              ["Mood", (tg.mood || []).join(", ")],
            ],
          ],
        ]
      : [
          [
            "Artwork",
            [
              ["Artist", (tg.artist || []).join(", ")],
              ["Movement", (tg.movement || []).join(", ")],
              ["Year", rec._item.y],
            ],
          ],
          [
            "Scene",
            [
              ["Place", (tg.scene || []).join(", ")],
              ["Mood", (tg.mood || []).join(", ")],
            ],
          ],
        ];
    if (rec._item.cap) groups.push(["Caption", [["", rec._item.cap]]]);
    renderInfo(info, groups);
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
    renderNearby(idx);
    syncLbSave(rec);

    lb.hidden = false;
    document.body.style.overflow = "hidden";
    writeUrl(null, null);
    if (wasHidden) $("lbClose").focus();
  }

  function renderNearby(idx) {
    const host = $("lbNear");
    host.innerHTML = "";
    const total = state.filtered.length;
    if (total < 2) {
      $("lbNearSec").hidden = true;
      return;
    }
    $("lbNearSec").hidden = false;
    const start = Math.max(0, idx - 2);
    const end = Math.min(total, idx + 3);
    for (let i = start; i < end; i++) {
      const rec = state.filtered[i];
      const b = document.createElement("button");
      b.type = "button";
      b.className = "near" + (i === idx ? " on" : "");
      b.title = rec._label;
      const img = document.createElement("img");
      img.src = thumbAt(rec.t || rec.img, 300);
      img.alt = rec._label;
      b.appendChild(img);
      b.addEventListener("click", () => openLightbox(i));
      host.appendChild(b);
    }
  }

  function syncLbSave(rec) {
    const on = onBoard(rec._key);
    const btn = $("lbSave");
    btn.classList.toggle("on", on);
    btn.textContent = on ? "Saved" : "Save";
    btn.setAttribute("aria-pressed", String(on));
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
    resetZoom();
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
  $("lbOpen").addEventListener("click", () => {
    if (curFull) window.open(curFull, "_blank", "noopener");
  });
  $("lbSave").addEventListener("click", () => {
    const rec = state.filtered[state.lbIdx];
    if (!rec) return;
    toggleSave(rec, null);
    syncLbSave(rec);
  });
  $("lbCopy").addEventListener("click", async () => {
    if (!curFull) return;
    try {
      await navigator.clipboard.writeText(curFull);
      toast("Image link copied");
    } catch {
      toast("Could not copy the link");
    }
  });
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
    else if (e.key === "i" || e.key === "I") $("lbInfoBtn").click();
    else if (e.key === "s" || e.key === "S") {
      const rec = state.filtered[state.lbIdx];
      if (rec) {
        toggleSave(rec, null);
        syncLbSave(rec);
      }
    }
    else if (e.key === "Tab") trapTab(e);
  });

  $("clearbtn").addEventListener("click", () => {
    for (const p of state.panels) $(`ps${p.id}`).value = "";
    resetPanels();
    $("fYear").value = "";
    $("fSort").value = "new";
    state.query = "";
    $("q").value = "";
    state.refSrc = "";
    if (refmode()) syncRefSources();
    syncChampStrip();
    renderPanels();
    apply();
  });

  // One search box over every printed field: champion, skin, theme, artist,
  // crew, place, mood, caption. Re-filtering 35k records is cheap; rebuilding
  // the rows is not, hence the frame throttle.
  let searchRaf = 0;
  $("q").addEventListener("input", () => {
    state.query = $("q").value;
    if (searchRaf) return;
    searchRaf = requestAnimationFrame(() => {
      searchRaf = 0;
      syncClear();
      apply();
    });
  });
  $("qClear").addEventListener("click", () => {
    state.query = "";
    $("q").value = "";
    $("q").focus();
    syncClear();
    apply();
  });

  // --- Drawer -------------------------------------------------------------
  const drawer = $("drawer");
  const scrim = $("scrim");
  let drawerTimer = 0;

  function openDrawer() {
    clearTimeout(drawerTimer);
    drawer.classList.add("open");
    drawer.setAttribute("aria-hidden", "false");
    $("filterBtn").setAttribute("aria-expanded", "true");
    scrim.hidden = false;
    requestAnimationFrame(() => scrim.classList.add("on"));
    document.body.classList.add("locked");
  }

  function closeDrawer() {
    clearTimeout(drawerTimer);
    drawer.classList.remove("open");
    drawer.setAttribute("aria-hidden", "true");
    $("filterBtn").setAttribute("aria-expanded", "false");
    scrim.classList.remove("on");
    document.body.classList.remove("locked");
    drawerTimer = setTimeout(() => { scrim.hidden = true; }, 260);
  }

  function syncDrawerState() {
    if (state.view !== "browse") closeDrawer();
  }

  $("filterBtn").addEventListener("click", () => {
    if (drawer.classList.contains("open")) closeDrawer();
    else openDrawer();
  });
  $("drawerClose").addEventListener("click", closeDrawer);
  $("drawerApply").addEventListener("click", closeDrawer);
  scrim.addEventListener("click", () => {
    closeDrawer();
    closeBoard();
  });

  // --- Board panel ---------------------------------------------------------
  const board = $("board");

  function openBoard() {
    if (drawer.classList.contains("open")) closeDrawer();
    renderBoard();
    board.classList.add("open");
    board.setAttribute("aria-hidden", "false");
    $("boardBtn").setAttribute("aria-expanded", "true");
  }

  function closeBoard() {
    board.classList.remove("open");
    board.setAttribute("aria-hidden", "true");
    $("boardBtn").setAttribute("aria-expanded", "false");
  }

  // The board is not modal: you keep saving while it is open. Clicking the
  // library behind it closes it.
  document.addEventListener("pointerdown", (e) => {
    if (!board.classList.contains("open")) return;
    if (board.contains(e.target) || $("boardBtn").contains(e.target)) return;
    closeBoard();
  });

  $("boardBtn").addEventListener("click", () => {
    if (board.classList.contains("open")) closeBoard();
    else openBoard();
  });
  $("boardClose").addEventListener("click", closeBoard);
  $("boardClear").addEventListener("click", () => {
    if (!state.board.length) return;
    state.board = [];
    persistBoard();
    renderBoard();
  });
  $("boardCopy").addEventListener("click", async () => {
    if (!state.board.length) return;
    try {
      await navigator.clipboard.writeText(state.board.map((e) => e.img).join("\n"));
      toast(`${state.board.length} link${state.board.length === 1 ? "" : "s"} copied`);
    } catch {
      toast("Could not copy the links");
    }
  });

  $("density").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-density]");
    if (!b || b.dataset.density === state.density) return;
    state.density = b.dataset.density;
    applyDensity();
  });
  $("emptyClear").addEventListener("click", () => $("clearbtn").click());

  document.addEventListener("keydown", (e) => {
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName);
    if (e.key === "/" && !typing && state.view === "browse") {
      e.preventDefault();
      $("q").focus();
    }
    if ((e.key === "b" || e.key === "B") && !typing && state.view === "browse") {
      e.preventDefault();
      if (board.classList.contains("open")) closeBoard();
      else openBoard();
    }
    if (e.key === "Escape" && lb.hidden) {
      if (drawer.classList.contains("open")) closeDrawer();
      if (board.classList.contains("open")) closeBoard();
    }
  });

  // Tile density from the last session.
  for (const b of $("density").children) b.classList.toggle("on", b.dataset.density === state.density);
  grid.classList.add("d-" + state.density);
  syncBoard();

  // --- Home / browse ------------------------------------------------------
  const cards = $("libCards");
  for (const lib of LIBRARIES) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "libcard";
    b.dataset.lib = lib.id;
    const img = document.createElement("img");
    img.src = lib.cover.replace(/\/1200px-/, "/800px-");
    img.alt = "";
    img.loading = "lazy";
    const meta = document.createElement("span");
    meta.className = "libmeta";
    const left = document.createElement("span");
    const name = document.createElement("span");
    name.className = "libname";
    name.textContent = lib.name;
    left.append(name);
    const count = document.createElement("span");
    count.className = "libcount";
    count.textContent = lib.count.toLocaleString();
    meta.append(left, count);
    const go = document.createElement("span");
    go.className = "libgo";
    go.textContent = "\u2197";
    b.append(img, meta, go);
    cards.appendChild(b);
  }

  for (const b of document.querySelectorAll("[data-lib]")) {
    b.addEventListener("click", () => openLibrary(b.dataset.lib));
  }
  $("backHome").addEventListener("click", goHome);

  const lbInfoBtn = $("lbInfoBtn");
  lbInfoBtn.addEventListener("click", () => {
    const collapsed = $("lbMeta").classList.toggle("collapsed");
    lbInfoBtn.setAttribute("aria-pressed", String(!collapsed));
    lbInfoBtn.textContent = collapsed ? "Details" : "Hide details";
  });

  const onResize = () => {
    if (window.innerWidth > 860) closeDrawer();
  };
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
      state.refRows = layoutRefRows(state.filtered);
      state.shown = 0;
      grid.innerHTML = "";
      renderRefRows(Math.min(keep, state.refRows.length));
    }, 200);
  });

  $("fYear").addEventListener("change", apply);
  $("fSort").addEventListener("change", apply);
  more.addEventListener("click", renderStep);

  const lbImg = $("lbImg");
  const lbImgWrap = $("lbImgWrap");

  function clampPan() {
    const box = lbImgWrap.getBoundingClientRect();
    const mx = ((zoom - 1) * box.width) / 2;
    const my = ((zoom - 1) * box.height) / 2;
    panX = Math.max(-mx, Math.min(mx, panX));
    panY = Math.max(-my, Math.min(my, panY));
  }

  function applyZoom() {
    lbImg.style.transform = `translate(${panX}px, ${panY}px) scale(${zoom})`;
    lbImg.classList.toggle("zoomed", zoom > 1);
    lbImg.classList.toggle("dragging", panning);
    const readout = $("lbZoom");
    readout.hidden = !lbImg.getAttribute("src");
    readout.textContent = zoom > 1 ? `${Math.round(zoom * 100)}%  ·  drag to pan` : "100%  ·  scroll to zoom";
  }

  function resetZoom() {
    zoom = 1;
    panX = 0;
    panY = 0;
    panning = false;
    applyZoom();
  }

  function zoomAt(clientX, clientY, factor) {
    const box = lbImgWrap.getBoundingClientRect();
    const cx = clientX - (box.left + box.width / 2);
    const cy = clientY - (box.top + box.height / 2);
    const next = Math.min(8, Math.max(1, zoom * factor));
    if (next === zoom) return;
    panX = cx - (cx - panX) * (next / zoom);
    panY = cy - (cy - panY) * (next / zoom);
    zoom = next;
    if (zoom === 1) {
      panX = 0;
      panY = 0;
    }
    clampPan();
    applyZoom();
  }

  lbImgWrap.addEventListener(
    "wheel",
    (e) => {
      if (lb.hidden || !lbImg.getAttribute("src")) return;
      e.preventDefault();
      zoomAt(e.clientX, e.clientY, e.deltaY < 0 ? 1.18 : 1 / 1.18);
    },
    { passive: false },
  );

  lbImg.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    if (zoom <= 1) return;
    e.preventDefault();
    panning = true;
    panFromX = e.clientX;
    panFromY = e.clientY;
    lbImg.setPointerCapture(e.pointerId);
    applyZoom();
  });

  lbImg.addEventListener("pointermove", (e) => {
    if (!panning) return;
    panX += e.clientX - panFromX;
    panY += e.clientY - panFromY;
    panFromX = e.clientX;
    panFromY = e.clientY;
    clampPan();
    applyZoom();
  });

  const endPan = () => {
    if (!panning) return;
    panning = false;
    applyZoom();
  };
  lbImg.addEventListener("pointerup", endPan);
  lbImg.addEventListener("pointercancel", endPan);

  lbImg.addEventListener("dblclick", (e) => {
    if (lb.hidden || !lbImg.getAttribute("src")) return;
    if (zoom > 1) resetZoom();
    else zoomAt(e.clientX, e.clientY, 2.5);
  });

  lbImg.addEventListener("auxclick", (e) => {
    if (e.button !== 1 || lb.hidden || !curFull) return;
    e.preventDefault();
    window.open(curFull, "_blank", "noopener");
  });

  // Deep link: ?game=wr&champ=Jinx&skin=Project lands straight in that library.
  const start = readUrl().game;
  if (start) {
    load(start)
      .then(syncUrl)
      .catch((e) => { toast("Failed to load data: " + e.message); });
  } else {
    state.view = "home";
  }
})();
