#!/usr/bin/env python3
"""
Builds one data/<game>.json catalogue per game for the wiki reference wrapper.

Games (see GAMES): League of Legends, Wild Rift, Legends of Runeterra. TFT is
deliberately absent -- its sets are League champion skins reusing the same art.

1. Fetches the game's skin/cosmetic data module (Lua table) from the
   League of Legends wiki. One wiki hosts all three games.
2. Parses the Lua dialect into plain data structures.
3. Discovers art files via the wiki image index (allimages prefix search)
   and pulls the full revision history of each canonical file.
4. Collapses "small iterations" of the same artwork using perceptual hashing
    (dHash) so only distinct repaints are shown, then upgrades every artwork to
    its best available resolution (HD / oldN_HD files), newest art first.
5. Writes a compact JSON file consumed by the web app.

Wild Rift additionally drops any entry whose artwork is the same picture as the
League of Legends original -- those carry no information the LoL tab lacks.

Usage: python build_data.py [game ...]     (requires Pillow)
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from io import BytesIO

from PIL import Image

WIKI = "https://wiki.leagueoflegends.com/en-us"
API_URL = WIKI + "/api.php"
USER_AGENT = "lol-wiki-reference-wrapper/1.0 (local artist tool)"
OVERRIDES_PATH = "data/artwork_overrides.json"
DATA_DIR = "data"

# Perceptual-hash settings (0-64 bits hamming distance).
# CLUSTER_THRESHOLD: revisions within this distance count as the same artwork.
# A sibling file (_oldN/_Unused/_HD) within the same distance of an artwork is
# treated as that art, so the highest-resolution copy can be picked.
CLUSTER_THRESHOLD = 13
MATCH_THRESHOLD = 7
HASH_THUMB_WIDTH = 120

# A Wild Rift splash this close to the League of Legends original is the same
# artwork and is dropped from the WR catalogue, since the League tab already
# holds it. The LoL tab displays the _HD file when the wiki has one, and that
# file is often a different crop of the canonical, so the WR splash is hashed
# against both and the closer match decides. 20 is measured, not guessed: over
# the 295 same-named WR pairs it catches the reported duplicates (Hwei Original
# 20, Hwei Winterblessed 5, Kayn Odyssey 9), puts 47 pairs at 0-10 with none of
# them scoring like a distinct painting, and no lower cut catches Hwei Original
# at all. Above 10 the distances decay smoothly with no natural gap, so the cut
# past 10 is a judgment call; 13 of the dropped pairs score like distinct
# paintings on a blurred correlation, all of them same-named re-shoots.
CROSS_GAME_DUPLICATE = 20

UNKNOWN_ARTIST = "Unknown artist"

# Values in splashartist that are not artist/studio names; a skin whose artist
# list contains only these (or nothing at all) is credited to UNKNOWN_ARTIST.
ART_PLACEHOLDERS = frozenset(
    {
        "unknown",
        "unknown artist",
        "n/a",
        "na",
        "none",
        "tba",
        "tbd",
        "not specified",
        "unspecified",
        "unlisted",
        "to be determined",
        "to be announced",
        "null",
        "-",
        "?",
    }
)


def normalize_artist(info: dict) -> list:
    arts = info.get("splashartist") or []
    if isinstance(arts, str):
        arts = [arts]
    names = []
    for a in arts or []:
        if not isinstance(a, str):
            continue
        t = " ".join(a.split()).lower()
        if not t or t in ART_PLACEHOLDERS:
            continue
        names.append(a)
    return names or [UNKNOWN_ARTIST]


# ---------------------------------------------------------------------------
# Lua subset parser (MediaWiki dump output)
# ---------------------------------------------------------------------------

TOKEN_RE = re.compile(
    r"""
    (?P<comment>--(?:\[=*\[[\s\S]*?\]\=*\]|[^\n]*))
  | (?P<space>\s+)
  | (?P<lstr>\[=*\[[\s\S]*?\]\=*\])
  | (?P<string>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')
  | (?P<number>-?\d+(?:\.\d+)?)
  | (?P<ident>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<lb>\[) | (?P<ob>\{) | (?P<rb>\]) | (?P<cb>\}) | (?P<eq>=) | (?P<comma>,)
    """,
    re.VERBOSE,
)

_ESCAPES = {"n": "\n", "r": "\r", "t": "\t", "\\": "\\", '"': '"', "'": "'", "0": "\0"}


def _unescape(s: str) -> str:
    out = []
    i = 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            nxt = s[i + 1]
            if nxt in _ESCAPES:
                out.append(_ESCAPES[nxt])
                i += 2
                continue
            if nxt == "u" and i + 5 < len(s):
                out.append(chr(int(s[i + 2 : i + 6], 16)))
                i += 6
                continue
            out.append(nxt)
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _tokenize(text: str):
    tokens = []
    for m in TOKEN_RE.finditer(text):
        kind = m.lastgroup
        val = m.group(kind)
        if kind in ("comment", "space"):
            continue
        if kind == "string":
            tokens.append((kind, _unescape(val[1:-1])))
        elif kind == "number":
            tokens.append(("number", float(val) if "." in val else int(val)))
        elif kind in ("ident", "lb", "ob", "rb", "cb", "eq", "comma"):
            tokens.append((kind, val))
        elif kind == "lstr":
            inner = re.sub(r"^\s*\[=*\[(.*)\]=\]\s*$", r"\1", val, flags=re.DOTALL)
            tokens.append(("string", inner))
    return tokens


def _parse_value(tokens, i):
    kind, val = tokens[i]
    if kind == "string":
        return val, i + 1
    if kind == "number":
        return val, i + 1
    if kind == "ident":
        return {"true": True, "false": False, "nil": None}.get(val, val), i + 1
    if kind == "ob":
        return _parse_table(tokens, i)
    raise ValueError(f"unexpected token {kind}={val!r} at {i}")


def _parse_table(tokens, i):
    i += 1  # consume {
    entries = []  # (key_or_None, value)
    idx = 0
    while True:
        kind, val = tokens[i]
        if kind == "cb":
            return _bake_table(entries), i + 1
        if kind == "comma":
            i += 1
            continue
        if kind == "lb":
            # [key] = value
            i += 1
            kkind, kval = tokens[i]
            assert kkind in ("string", "number"), tokens[i]
            key = kval
            i += 1
            kkind, kval = tokens[i]
            assert kkind == "rb", tokens[i]
            i += 1
            kkind, kval = tokens[i]
            assert kkind == "eq", tokens[i]
            i += 1
            value, i = _parse_value(tokens, i)
            entries.append((key, value))
            continue
        if kind == "ident":
            # maybe name = value
            if i + 1 < len(tokens) and tokens[i + 1][0] == "eq":
                name = val
                i += 2
                value, i = _parse_value(tokens, i)
                entries.append((name, value))
                continue
            # bare value -> implicit array index
            idx += 1
            value, i = _parse_value(tokens, i)
            entries.append((idx, value))
            continue
        # bare value -> implicit array index
        idx += 1
        value, i = _parse_value(tokens, i)
        entries.append((idx, value))


def _bake_table(entries):
    keys = [k for k, _ in entries]
    all_int = all(isinstance(k, int) for k in keys)
    if all_int and keys and keys == list(range(1, len(keys) + 1)):
        return [v for _, v in entries]
    if all_int:
        return {str(k): v for k, v in entries if v is not None}
    return {k: v for k, v in entries if v is not None}


def parse_lua(text: str):
    tokens = _tokenize(text)
    if tokens and tokens[0] == ("ident", "return"):
        return _parse_value(tokens, 1)[0]
    return _parse_value(tokens, 0)[0]


# ---------------------------------------------------------------------------
# Network helpers
# ---------------------------------------------------------------------------


def http_get(url: str, retries: int = 3) -> bytes:
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except Exception as e:  # noqa: BLE001
            if attempt == retries - 1:
                raise
            time.sleep(1.5 * (attempt + 1))


def api_query(params: dict) -> dict:
    url = API_URL + "?" + urllib.parse.urlencode(params)
    return json.loads(http_get(url))


# ---------------------------------------------------------------------------
# Filename derivation
# ---------------------------------------------------------------------------


def champ_prefix(name: str) -> str:
    if name.endswith(" & Willump"):
        name = name.replace(" & Willump", "")
    return name.replace(" ", "_")


_LIGHT_STRIP = re.compile(r"[ :/]")
_AGGRESSIVE_STRIP = re.compile(r"[ :/()&,.!?'\"~@#$%^&*+=\[\]{}|\\]")


def skin_asset(name: str, aggressive: bool = False) -> str:
    if aggressive:
        return _AGGRESSIVE_STRIP.sub("", name)
    return _LIGHT_STRIP.sub("", name)


def _bases_variants(make) -> list[str]:
    """Build a base from the light and the punctuation-stripped skin name."""
    c1 = make(False)
    c2 = make(True)
    return [c1] if c1 == c2 else [c1, c2]


# ---------------------------------------------------------------------------
# Game sources
# ---------------------------------------------------------------------------
#
# One wiki (wiki.leagueoflegends.com) hosts all three games, but each stores its
# cosmetics differently, so every game supplies its own data module, file-naming
# rules and output. Everything downstream of the per-game rules below -- image
# discovery, revision mining, dHash clustering -- is shared.


class Entry:
    """One cosmetic to resolve.

    prefix  file-discovery key (champion name, or a card code for LoR)
    owner   display name shown in the UI (the champion)
    skin    cosmetic key, e.g. "Blood Moon"
    info    the raw data module entry
    """

    __slots__ = ("prefix", "owner", "skin", "info")

    def __init__(self, prefix: str, owner: str, skin: str, info: dict):
        self.prefix = prefix
        self.owner = owner
        self.skin = skin
        self.info = info


class Game:
    key = ""
    label = ""
    module = ""
    aspect = (1215, 717)
    out = ""
    unit = "Champions"

    def entries(self, raw: str) -> list[Entry]:
        raise NotImplementedError

    def bases(self, e: Entry) -> list[str]:
        raise NotImplementedError

    def canons(self, base: str) -> list[str]:
        """File names holding the current artwork, most likely first."""
        raise NotImplementedError

    def hd(self, base: str) -> list[str]:
        raise NotImplementedError

    def hits(self, files: dict, base: str, e: Entry) -> dict:
        """The discovered files belonging to one cosmetic."""
        raise NotImplementedError

    def candidates(self, files: dict, base: str, ctx: Ctx) -> list[dict]:
        raise NotImplementedError


class SkinDataGame(Game):
    """Games stored as champion -> {id, skins: {key -> info}} (LoL, Wild Rift)."""

    suffix = ""
    skip_marks: tuple = ()
    # Art extension(s) the wiki uses for this game. Wild Rift uploaded its first
    # champions as .png and later switched to .jpg, so both have to be probed;
    # League is .jpg throughout.
    exts: tuple = (".jpg",)

    def entries(self, raw: str) -> list[Entry]:
        out = []
        for name, ent in parse_lua(raw).items():
            if name.startswith("["):
                continue
            if not isinstance(ent, dict) or not isinstance(ent.get("id"), (int, float)):
                continue
            skins = ent.get("skins")
            if not isinstance(skins, dict):
                continue
            for sk, info in skins.items():
                if isinstance(info, dict):
                    out.append(Entry(name, name, sk, info))
        return out

    def bases(self, e: Entry) -> list[str]:
        prefix = champ_prefix(e.prefix)
        return _bases_variants(
            lambda agg: f"{prefix}_{skin_asset(e.skin, agg)}Skin{self.suffix}"
        )

    def canons(self, base: str) -> list[str]:
        return [base + ext for ext in self.exts]

    def hd(self, base: str) -> list[str]:
        return [base + "_HD" + ext for ext in self.exts]

    def hits(self, files: dict, base: str, e: Entry) -> dict:
        own = set(self.canons(base)) | set(self.hd(base))
        return {fn: r for fn, r in files.items() if fn in own or fn.startswith(base + "_")}

    def candidates(self, files: dict, base: str, ctx: Ctx) -> list[dict]:
        return classify_siblings(files, base, self.skip_marks, self.canons(base), ctx)


class LoL(SkinDataGame):
    key = "lol"
    label = "League of Legends"
    module = "Module:SkinData/data"
    out = "skins.json"
    # Non-splash files that share a skin's base prefix: other games' art,
    # champion icons/portraits, chromas, loading screens, promo and concept art.
    skip_marks = (
        "_Ch", "_WR", "_TFT", "_Mobile", "_Chr",
        "Loading", "Square", "Circle", "Special_Edition",
        "_Promo", "_Concept", "Concept_", "_Model", "Baron", "Rift",
    )


class WildRift(SkinDataGame):
    key = "wr"
    label = "Wild Rift"
    module = "Module:SkinDataWR/data"
    out = "skins-wr.json"
    suffix = "_WR"
    aspect = (1024, 568)
    exts = (".jpg", ".png")
    # Same shapes as League, minus the League-only marks. `_WR` itself is the
    # canonical suffix here, so it must not be skipped.
    skip_marks = (
        "_Ch", "_TFT", "_Mobile", "_Chr",
        "Loading", "Square", "Circle", "Special_Edition",
        "_Promo", "_Concept", "Concept_", "_Model", "Baron", "Rift",
    )


# Suffixes that mark an alternate rendering of the same LoR cosmetic, as opposed
# to a star level (T1-...), a different cosmetic (_Coven-...) or a presentation
# crop (-display-full).
_LOR_ALT_RE = re.compile(r"-(?:alt)(?:-hd)?-full\.(?:png|jpg)", re.I)


class LegendsOfRuneterra(Game):
    key = "lor"
    label = "Legends of Runeterra"
    module = "Module:LoRCosmetics/skins"
    names_module = "Module:LoRData/data"
    out = "skins-lor.json"
    aspect = (2, 1)
    unit = "Champions"

    def __init__(self):
        self._names = {}

    def card_names(self) -> dict:
        """cardcode -> champion name, from the (much larger) card data module."""
        if not self._names:
            data = parse_lua(http_get(f"{WIKI}/{self.names_module}?action=raw").decode("utf-8"))
            self._names = {
                code: ent["name"]
                for code, ent in data.items()
                if isinstance(ent, dict) and isinstance(ent.get("name"), str)
            }
            print(f"    card names loaded: {len(self._names)}")
        return self._names

    def entries(self, raw: str) -> list[Entry]:
        names = self.card_names()
        out = []
        for code, cosmetics in parse_lua(raw).items():
            if not isinstance(cosmetics, dict) or code not in names:
                continue
            for sk, info in cosmetics.items():
                if isinstance(info, dict):
                    out.append(Entry(code, names[code], sk, info))
        return out

    def bases(self, e: Entry) -> list[str]:
        # The base card art carries no cosmetic name suffix: 01DE012-full.png.
        if e.skin == "Original":
            return [e.prefix]
        code = e.prefix
        return _bases_variants(lambda agg: f"{code}_{skin_asset(e.skin, agg)}")

    def canons(self, base: str) -> list[str]:
        return [base + "-full.png", base + "-full.jpg"]

    def hd(self, base: str) -> list[str]:
        # Cosmetic HD art is capitalised, base card art is not.
        return [base + "-HD-full.jpg", base + "-hd-full.jpg"]

    def hits(self, files: dict, base: str, e: Entry) -> dict:
        # Every cosmetic of a card shares the card's files, so the whole card
        # prefix is in scope; the per-cosmetic filter happens in candidates().
        return {fn: r for fn, r in files.items() if fn.startswith(e.prefix)}

    def candidates(self, files: dict, base: str, ctx: Ctx) -> list[dict]:
        """Alternate art for one cosmetic.

        A LoR card's files are a flat pile: the base card art, one set per
        cosmetic, and a variant per star level, all sharing the card code. Only
        the `-alt` family hangs off the cosmetic's own base, so everything else
        (other cosmetics, `T1`-`T8` star levels, `-display` presentation crops)
        is a different picture of a different thing and is left out here. What
        remains goes to the shared dHash matcher, which folds it onto the main
        artwork when it is the same painting and lists it otherwise.
        """
        skip = {*self.canons(base), *self.hd(base)}
        out = []
        for fn, rec in files.items():
            if fn in skip or not fn.startswith(base):
                continue
            if not _LOR_ALT_RE.fullmatch(fn[len(base):]):
                continue
            out.append(
                {
                    "url": rec["url"],
                    "w": rec["w"],
                    "h": rec["h"],
                    "d": (rec.get("ts") or "")[:10],
                    "n": 1,
                    "kind": "alt",
                }
            )
        return out


GAMES: dict[str, Game] = {g.key: g for g in (LoL(), WildRift(), LegendsOfRuneterra())}
GAME_ORDER = ["lol", "wr", "lor"]


def get_game(key: str) -> Game:
    if key not in GAMES:
        sys.exit(f"unknown game {key!r}; choose from {', '.join(GAME_ORDER)}")
    return GAMES[key]


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------


def thumb_url(full_url: str, width: int) -> str:
    """Build a MediaWiki thumb URL (current or archive revision) from the full URL."""
    base = full_url.split("?")[0]
    marker = "/images/"
    i = base.rindex(marker)
    origin = base[:i]
    rel = base[i + len(marker):]
    if "/" in rel:
        tail = rel.rsplit("/", 1)[-1]
        name = tail.split("%21")[-1].split("!")[-1]
        return f"{origin}{marker}thumb/{rel}/{width}px-{name}"
    return f"{origin}{marker}thumb/{rel}/{width}px-{rel}"


def thumb_width(art) -> int:
    """Thumb size to serve. Big art gets a 1200px thumb so the lightbox can show
    detail immediately; everything else gets 420px."""
    url = str(art.get("url", ""))
    return 1200 if (art.get("w") or 0) > 2000 or re.search(r"[-_]hd-full\.jpg$|_HD\.jpg$", url, re.I) else 420


# ---------------------------------------------------------------------------
# Image index discovery + canonical history
# ---------------------------------------------------------------------------


def _file_rec(im: dict) -> dict:
    return {
        "url": im["url"],
        "w": im.get("width"),
        "h": im.get("height"),
        "ts": im.get("timestamp", ""),
        "sha1": im.get("sha1", ""),
    }


def discover_prefix(prefix: str) -> dict:
    """allimages prefix search -> {filename: rec} (url/w/h/ts/sha1)."""
    out = {}
    cont = None
    while True:
        params = {
            "action": "query",
            "format": "json",
            "formatversion": "2",
            "list": "allimages",
            "aiprefix": prefix,
            "ailimit": "500",
            "aiprop": "timestamp|url|dimensions|sha1",
        }
        if cont:
            params.update(cont)
        data = api_query(params)
        for im in data.get("query", {}).get("allimages", []):
            out[im["name"]] = _file_rec(im)
        cont = data.get("continue")
        if not cont:
            break
        time.sleep(0.12)
    return out


def fetch_histories(filenames: list[str]) -> dict:
    """Batch imageinfo with iihistory for canonical (plain .jpg) files.

    Returns {filename: [revision, ...]}, newest revision first. Each revision
    has url/w/h/ts/sha1. Archive URLs point at the image archive.
    """
    out = {}
    uniq = sorted(set(f for f in filenames if f))
    nbatch = (len(uniq) + 44) // 45
    for start in range(0, len(uniq), 45):
        batch = uniq[start : start + 45]
        if nbatch > 1:
            print(f"    history {start // 45 + 1}/{nbatch} ({len(batch)} files)", flush=True)
        titles = "|".join("File:" + urllib.parse.quote(f, safe="_' ") for f in batch)
        params = {
            "action": "query",
            "format": "json",
            "formatversion": "2",
            "redirects": "1",
            "prop": "imageinfo",
            "iiprop": "url|size|timestamp|sha1",
            "iihistory": "1",
            "iilimit": "100",
            "titles": titles,
        }
        data = api_query(params)
        if "error" in data:
            print("API ERROR:", json.dumps(data["error"])[:300], file=sys.stderr)
            continue
        for page in data.get("query", {}).get("pages", []):
            if "imageinfo" not in page:
                continue
            fn = page["title"].removeprefix("File:").replace(" ", "_")
            infos = []
            for ii in page["imageinfo"]:
                infos.append(
                    {
                        "ts": ii.get("timestamp", ""),
                        "url": ii["url"],
                        "w": ii.get("width"),
                        "h": ii.get("height"),
                        "sha1": ii.get("sha1"),
                    }
                )
            out[fn] = infos
        time.sleep(0.12)
    return out


# ---------------------------------------------------------------------------
# Perceptual hashing
# ---------------------------------------------------------------------------


def fetch_thumb_hash(url: str, cache: dict) -> int | None:
    """64-bit horizontal dHash of a small thumbnail, cached by URL."""
    if url in cache:
        return cache[url]
    h = None
    try:
        data = http_get(thumb_url(url, HASH_THUMB_WIDTH))
        img = Image.open(BytesIO(data)).convert("L").resize((9, 8), Image.Resampling.LANCZOS)
        px = img.load()
        bits = []
        for y in range(8):
            for x in range(8):
                bits.append("1" if px[x, y] >= px[x + 1, y] else "0")
        h = int("".join(bits), 2)
    except Exception:  # noqa: BLE001
        h = None
    cache[url] = h
    return h


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


# Cross-game caches, keyed by wiki-visible names, so they are valid for every
# game and survive from one game's build into the next. League and Wild Rift
# files sit under the same champion prefix, so one image-index read serves both
# and the Wild Rift pass can reach the League originals it de-duplicates against.
INDEX: dict = {}  # discovery key -> {filename: rec}
HASHES: dict = {}  # url -> dHash
HISTORIES: dict = {}  # filename -> [revision, ...]
CANON_SHA_DATES: dict = {}  # sha1 -> earliest date it appears under
SIB: dict = {}  # sibling filename -> [revision, ...]
_SIB_QUEUE: list = []
_SIB_SEEN: set = set()


class Ctx:
    """Per-game build state. The expensive caches above are shared."""

    def __init__(self, overrides: dict):
        self.overrides = overrides
        self.report: list = []
        self.rev_h: dict = {}  # base -> [(revision, hash)] for art-date recovery

    @property
    def cache(self) -> dict:
        return HASHES

    @property
    def histories(self) -> dict:
        return HISTORIES

    @property
    def canon_sha_dates(self) -> dict:
        return CANON_SHA_DATES

    def revisions(self, fn: str) -> list:
        return HISTORIES.get(fn) or SIB.get(fn)

    def note_siblings(self, files: dict):
        """Queue sibling files whose art date needs its own revision history."""
        for fn in files:
            if fn in _SIB_SEEN or not _SIB_FN_RE.search(fn):
                continue
            _SIB_SEEN.add(fn)
            _SIB_QUEUE.append(fn)
            if len(_SIB_QUEUE) >= 45:
                self.flush_siblings()

    def flush_siblings(self):
        while _SIB_QUEUE:
            chunk = _SIB_QUEUE[:45]
            del _SIB_QUEUE[:45]
            SIB.update(fetch_histories(chunk))


# ---------------------------------------------------------------------------
# Artwork timeline assembly
# ---------------------------------------------------------------------------

_OLD_RE = re.compile(r"^_old(\d*)(_HD)?$")
_UNUSED_RE = re.compile(r"^_Unused(\d*)(_HD)?$")
_SIB_FN_RE = re.compile(r"_(?:old\d*|Unused\d*)(?:_HD)?\.(?:jpg|png)$", re.I)


def index_for(ctx: Ctx, key: str) -> dict:
    """allimages prefix search, cached. Returns {filename: rec}."""
    files = INDEX.get(key)
    if files is None:
        files = discover_prefix(key)
        INDEX[key] = files
        ctx.note_siblings(files)
        ctx.flush_siblings()
    return files


def art_date(fn: str, rec: dict, ctx: Ctx) -> str:
    """Creation date of a sibling file's art.

    Prefer a byte-identical match against the canonical file history (the file
    may be a community copy of an earlier revision, re-uploaded later), then
    fall back to the sibling's own earliest revision, then its latest upload.
    """
    sha = rec.get("sha1")
    d = CANON_SHA_DATES.get(sha)
    if d:
        return d
    revs = ctx.revisions(fn)
    if revs:
        dates = [r["ts"][:10] for r in revs if r.get("ts")]
        if dates:
            return min(dates)
    return (rec.get("ts") or "")[:10]


def recover_art_date(base: str, canon_names: list[str], fn: str, rec: dict, ctx: Ctx) -> str | None:
    """Art-creation date of a sibling that only appeared during a wiki migration
    sweep.

    Such files hold a re-encoded copy of the art that was current on the
    canonical file right before the sweep, so their true date lives in the
    canonical history, not in their own (post-migration) revisions. Match the
    sibling against canonical revisions older than the sibling's creation and
    take the oldest matching revision: same-art junk revisions repeat the
    original bytes, so the birth of the art is the oldest revision whose
    thumbnail matches within the repaint-noise threshold.
    """
    canon = next((ctx.histories.get(n) for n in canon_names if ctx.histories.get(n)), None)
    if not canon or not rec.get("url"):
        return None
    sib = ctx.cache.get(rec["url"])
    if sib is None:
        sib = fetch_thumb_hash(rec["url"], ctx.cache)
    if sib is None:
        return None
    creation = None
    revs = ctx.revisions(fn)
    if revs:
        dates = [r["ts"][:10] for r in revs if r.get("ts")]
        if dates:
            creation = min(dates)
    if creation is None:
        creation = (rec.get("ts") or "")[:10]
    if not creation:
        return None
    if base not in ctx.rev_h:
        hashes = []
        for r in canon:
            if not r.get("url"):
                hashes.append(None)
                continue
            h = ctx.cache.get(r["url"])
            if h is None:
                h = fetch_thumb_hash(r["url"], ctx.cache)
            hashes.append(h)
        ctx.rev_h[base] = list(zip(canon, hashes))
    oldest = None
    for r, h in ctx.rev_h[base]:
        if not r.get("ts") or r["ts"][:10] >= creation:
            continue
        ok = h is not None and hamming(h, sib) <= CLUSTER_THRESHOLD
        if ok:
            oldest = r["ts"][:10]
    return oldest


def classify_siblings(files: dict, base: str, skip_marks: tuple, canon_names: list[str], ctx: Ctx) -> list[dict]:
    """Sibling files of a League/Wild Rift skin, oldest-art and unused first.

    Each item is {url, w, h, d, n, kind} and carries no filename: the shared
    dHash matcher downstream works on pixels, not names.
    """
    olds, unuseds = [], []
    for fn, rec in files.items():
        if not fn.endswith((".jpg", ".png")):
            continue
        if fn in canon_names:
            continue  # canonical file, handled via history
        rest = fn.rsplit(".", 1)[0][len(base):]
        if not rest.startswith("_"):
            continue
        if any(m in rest for m in skip_marks):
            continue
        m = _OLD_RE.match(rest) or _UNUSED_RE.match(rest)
        if not m:
            continue
        d = art_date(fn, rec, ctx)
        rd = recover_art_date(base, canon_names, fn, rec, ctx)
        if rd and (not d or rd < d):
            d = rd
        cands = olds if _OLD_RE.match(rest) else unuseds
        cands.append(
            {
                "url": rec["url"],
                "w": rec["w"],
                "h": rec["h"],
                "d": d,
                "n": int(m.group(1) or 1),
            }
        )

    for lst in (olds, unuseds):
        by_url = {c["url"]: c for c in lst}
        for c in lst:
            stem, ext = os.path.splitext(c["url"])
            if not stem.endswith("_HD") or not c.get("d"):
                continue
            partner = by_url.get(stem[:-3] + ext)
            if not partner or not partner.get("d") or partner["d"] >= c["d"]:
                continue
            h1 = ctx.cache.get(c["url"])
            if h1 is None:
                h1 = fetch_thumb_hash(c["url"], ctx.cache)
            h2 = ctx.cache.get(partner["url"])
            if h2 is None:
                h2 = fetch_thumb_hash(partner["url"], ctx.cache)
            if h1 and h2 and hamming(h1, h2) <= CLUSTER_THRESHOLD:
                c["d"] = partner["d"]

    for c in olds:
        c["kind"] = "old"
    for c in unuseds:
        c["kind"] = "unused"
    return olds + unuseds


def dedupe_history(revs: list[dict]) -> list[dict]:
    """Drop exact-duplicate revisions (same sha1), keeping the original upload."""
    seen = set()
    out = []
    for r in reversed(revs):  # oldest first
        sha = r.get("sha1")
        if sha and sha in seen:
            continue
        if sha:
            seen.add(sha)
        out.append(r)
    out.reverse()
    return out


def pick_keep(cluster: list[dict], is_first: bool) -> dict:
    """Representative revision of a cluster.

    Newest cluster -> newest revision again (iterations of the current art are
    dropped in favour of the latest). Older clusters -> the original (oldest)
    repaint, since subsequent revisions are just smaller iterations of it.
    """
    return cluster[0] if is_first else cluster[-1]


def cluster_history(arts: list[dict], cache: dict) -> list[list[dict]]:
    """Merge consecutive revisions whose dHash is within CLUSTER_THRESHOLD.

    arts is newest-first. Returns a list of clusters (also newest-first).
    """
    clusters = []
    for a in arts:
        a["hash"] = fetch_thumb_hash(a["url"], cache)
        if not clusters:
            clusters.append([a])
            continue
        rep = pick_keep(clusters[-1], len(clusters) == 1)
        if (
            rep.get("hash") is not None
            and a["hash"] is not None
            and hamming(rep["hash"], a["hash"]) <= CLUSTER_THRESHOLD
        ):
            clusters[-1].append(a)
        else:
            clusters.append([a])
    return clusters


def build_timeline(base: str, revs: list[dict], force: list[str] | None, ctx: Ctx) -> list[dict]:
    """Produce the distinct-artwork timeline (newest first) for one skin.

    Each returned art has url/w/h/d/ts/sha1. `force` is an optional override
    list of dates (or full timestamps) to keep, oldest first.
    """
    arts = [
        {
            "url": r["url"],
            "w": r.get("w"),
            "h": r.get("h"),
            "d": r.get("ts", "")[:10],
            "ts": r.get("ts", ""),
            "sha1": r.get("sha1"),
        }
        for r in dedupe_history(revs)
    ]
    if force:
        sel = []
        for k in force:
            for a in arts:
                if a["ts"] == k or a["d"] == k[:10]:
                    sel.append(a)
                    break
        if sel:
            return sel
    if not arts:
        return []
    clusters = cluster_history(arts, ctx.cache)
    keeps = [pick_keep(cl, i == 0) for i, cl in enumerate(clusters)]
    # Backdate each artwork to when its family was first created: the oldest
    # revision in the cluster, so repaints/re-uploads don't masquerade as new
    # artworks. Image stays the newest revision; only the date moves.
    for cl, k in zip(clusters, keeps):
        k["d"] = cl[-1]["d"] or k["d"]
        k["ts"] = cl[-1]["ts"] or k["ts"]
    dropped = [a for a in arts if all(a is not k for k in keeps)]
    if dropped or len(keeps) > 1:
        ctx.report.append(
            f"{base}: kept {[k['d'] for k in keeps]} dropped {[a['d'] for a in dropped]}"
        )
    return keeps


def match_siblings(arts: list[dict], cands: list[dict], cache: dict) -> tuple[dict, list]:
    """Assign each sibling file to its nearest artwork (by dHash).

    Returns (upgrades, extras) where upgrades maps an art index to the best
    (highest-res) matched sibling and extras are siblings that match no artwork
    (genuinely different art, e.g. unused concept art).
    """
    for c in cands:
        c["hash"] = fetch_thumb_hash(c["url"], cache)
        c["best"], c["dist"] = None, None
        if c["hash"] is None:
            continue
        best, bd = None, 10**9
        for i, a in enumerate(arts):
            ah = a.get("hash")
            if ah is None:
                ah = fetch_thumb_hash(a["url"], cache)
                a["hash"] = ah
            if ah is None:
                continue
            d = hamming(ah, c["hash"])
            if d < bd:
                bd, best = d, i
        c["best"], c["dist"] = best, bd
    groups = {}
    for c in cands:
        if c["best"] is None or c["dist"] is None or c["dist"] > MATCH_THRESHOLD:
            continue
        groups.setdefault(c["best"], []).append(c)
    upgrade = {i: max(grp, key=lambda c: (c["w"] or 0) * (c["h"] or 0)) for i, grp in groups.items()}
    extras = [c for c in cands if c["best"] is None or c["dist"] is None or c["dist"] > MATCH_THRESHOLD]
    return upgrade, extras


def assemble(game: Game, base: str, files: dict, ctx: Ctx) -> dict | None:
    """Assemble the artwork payload for one skin base. Returns None if nothing found."""
    canon_fns = game.canons(base)
    canon_fn = next((fn for fn in canon_fns if fn in files), None)
    hd = next((files[fn] for fn in game.hd(base) if fn in files), None)

    force = None
    if base in ctx.overrides:
        ov = ctx.overrides[base]
        force = ov if isinstance(ov, list) else ov.get("keep")

    arts = []
    revs = ctx.histories.get(canon_fn) if canon_fn else None
    if revs:
        arts = build_timeline(base, revs, force, ctx)
    if not arts and not force:
        # No usable history (missing canonical file): synthesize from current art.
        cur = files.get(canon_fn) if canon_fn else None
        if cur is None:
            cur = hd
        if not cur:
            return None
        arts = [{"url": cur["url"], "w": cur["w"], "h": cur["h"], "d": (cur["ts"] or "")[:10]}]
    if not arts:
        return None

    if hd and len(arts) == 1:
        arts[0]["url"], arts[0]["w"], arts[0]["h"] = hd["url"], hd["w"], hd["h"]

    cands = game.candidates(files, base, ctx)
    upgrade, extras = match_siblings(arts, cands, ctx.cache)
    for i, c in upgrade.items():
        arts[i]["url"], arts[i]["w"], arts[i]["h"] = c["url"], c["w"], c["h"]

    # A hi-res sibling is a copy of the current art; always use it as the main
    # image (never a separate version), regardless of how far its downscaled
    # hash drifts from the base file.
    if hd and hd["url"] not in arts[0]["url"]:
        art_area = (arts[0].get("w") or 0) * (arts[0].get("h") or 0)
        hd_area = (hd.get("w") or 0) * (hd.get("h") or 0)
        if hd_area > art_area:
            arts[0]["url"], arts[0]["w"], arts[0]["h"] = hd["url"], hd["w"], hd["h"]

    main = arts[0]
    versions = []
    for a in arts[1:]:
        versions.append(
            {
                "l": "Old",
                "d": a["d"],
                "img": a["url"],
                "t": thumb_url(a["url"], thumb_width(a)),
                "w": a["w"],
                "h": a["h"],
            }
        )
    for c in extras:
        versions.append(
            {
                "l": c.get("kind", "unused").capitalize(),
                "d": c["d"],
                "img": c["url"],
                "t": thumb_url(c["url"], thumb_width(c)),
                "w": c["w"],
                "h": c["h"],
            }
        )
    versions.sort(key=lambda v: v["d"] or "9999-99-99")

    return {
        "img": main["url"],
        "t": thumb_url(main["url"], thumb_width(main)),
        "w": main["w"],
        "h": main["h"],
        "d": main.get("d"),
        "v": versions or None,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def load_overrides() -> dict:
    try:
        with open(OVERRIDES_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def is_lol_twin(game: Game, base: str) -> bool:
    """True when a Wild Rift base has a League of Legends counterpart.

    The two games use the same file layout, so the League file is the same base
    without the _WR suffix. Most Wild Rift skins are exclusive and have no
    counterpart at all, which is the common case.
    """
    return game.key == "wr" and base.endswith("_WR")


def build_game(game: Game, overrides: dict) -> dict:
    """Build one game's catalogue and write it to data/<out>."""
    ctx = Ctx(overrides)
    print(f"\n=== {game.label} ===")

    print("fetching lua data...")
    entries = game.entries(http_get(f"{WIKI}/{game.module}?action=raw").decode("utf-8"))
    owners = sorted({e.owner for e in entries})
    print(f"{game.unit.lower()} parsed: {len(owners)} ({len(entries)} cosmetics)")

    print("fetching file histories...")
    wanted = sorted({fn for e in entries for b in game.bases(e) for fn in game.canons(b)})
    HISTORIES.update(fetch_histories(wanted))
    for fn, revs in HISTORIES.items():
        for r in revs:
            sha, ts = r.get("sha1"), r.get("ts", "")[:10]
            if sha and ts:
                CANON_SHA_DATES[sha] = min(CANON_SHA_DATES.get(sha, ts), ts)

    print("discovering art files via image index...")

    def files_for(e: Entry, base: str) -> dict:
        key = e.prefix if isinstance(game, LegendsOfRuneterra) else champ_prefix(e.prefix)
        hits = game.hits(index_for(ctx, key), base, e)
        if not hits:
            hits = game.hits(index_for(ctx, base), base, e)
        return hits

    # variant: a chroma-style entry pointing at another skin of the same owner.
    lookup: dict[str, dict[int, str]] = {}
    by_skin: dict[str, dict[str, dict]] = {}
    if isinstance(game, SkinDataGame):
        for e in entries:
            skid = e.info.get("id")
            if isinstance(skid, (int, float)):
                lookup.setdefault(e.prefix, {})[int(skid)] = e.skin
            by_skin.setdefault(e.prefix, {})[e.skin] = e.info

    def resolve(e: Entry, depth: int = 0):
        for base in game.bases(e):
            files = files_for(e, base)
            if not files and base not in ctx.histories:
                continue
            payload = assemble(game, base, files, ctx)
            if payload:
                return base, payload
        if depth > 3:
            return None, None
        v = e.info.get("variant")
        if isinstance(v, (int, float)):
            other = lookup.get(e.prefix, {}).get(int(v))
            if other and other != e.skin:
                return resolve(Entry(e.prefix, e.owner, other, by_skin[e.prefix][other]), depth + 1)
        return None, None

    skins = []
    set_counts: dict[str, int] = {}
    missing_img = 0
    dupes = 0
    prev = None
    done = 0
    for e in entries:
        if e.owner != prev:
            prev = e.owner
            done += 1
            if done % 5 == 0 or done == 1:
                print(f"  {game.unit[:-1].lower()} {done}/{len(owners)}: {e.owner}", flush=True)
        base, art = resolve(e)
        if base and art and is_lol_twin(game, base):
            if drop_as_lol_duplicate(game, e, base, art, ctx):
                dupes += 1
                continue
        rec = {
            "ch": e.owner,
            "s": e.skin,
            "fmt": e.info.get("formatname"),
            "set": e.info.get("set"),
            "avail": e.info.get("availability"),
            "cost": e.info.get("cost"),
            "r": e.info.get("release"),
            "d": art["d"] if art else None,
            "art": normalize_artist(e.info),
            "mu": e.info.get("music"),
            "cr": len(e.info.get("chromas") or {}) if isinstance(e.info.get("chromas"), dict) else 0,
            "mid": e.info.get("id"),
            "img": art["img"] if art else None,
            "t": art["t"] if art else None,
            "w": art["w"] if art else None,
            "h": art["h"] if art else None,
        }
        if art and art.get("v"):
            rec["v"] = art["v"]
        if not rec["img"]:
            missing_img += 1
        for s in rec["set"] if isinstance(rec["set"], list) else []:
            set_counts[s] = set_counts.get(s, 0) + 1
        skins.append(rec)

    ctx.flush_siblings()

    sets = sorted(set_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    meta = {
        "gen": time.strftime("%Y-%m-%d"),
        "game": game.key,
        "label": game.label,
        "aspect": list(game.aspect),
        "unit": game.unit,
        "ownerCount": len(owners),
        "skinCount": len(skins),
        "missingImage": missing_img,
        "sets": sets,
    }
    if dupes:
        meta["droppedAsLoLDuplicate"] = dupes

    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, game.out)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "skins": skins}, f, ensure_ascii=False, separators=(",", ":"))

    extra = f", {dupes} dropped as League duplicates" if dupes else ""
    print(f"wrote {path}: {len(skins)} entries, {len(sets)} sets, {missing_img} without image{extra}")
    if ctx.report:
        print(f"multi-art cosmetics ({len(ctx.report)}):")
        for line in ctx.report:
            print("  " + line)
    return {"meta": meta, "skins": skins}


def drop_as_lol_duplicate(game: Game, e: Entry, base: str, art: dict, ctx: Ctx) -> bool:
    """True when this Wild Rift splash is the same picture as the League original.

    Wild Rift ports many League skins unchanged, and those files are already in
    the LoL catalogue at higher resolution, so keeping them would just show the
    same painting twice. The LoL tab displays the _HD file when the wiki has
    one, and HD is often a different crop of the canonical file, so both are
    compared and the closer match decides; hashing against only one of the two
    crops produced distances that let re-cropped twins survive.
    """
    lol_game = GAMES["lol"]
    lol_base = base[: -len(game.suffix)]
    lol_files = index_for(ctx, champ_prefix(e.prefix))
    recs = [
        lol_files[fn]
        for fn in lol_game.canons(lol_base) + lol_game.hd(lol_base)
        if fn in lol_files
    ]
    if not recs:
        return False
    a = fetch_thumb_hash(art["img"], ctx.cache)
    if a is None:
        return False
    for rec in recs:
        b = fetch_thumb_hash(rec["url"], ctx.cache)
        if b is not None and hamming(a, b) <= CROSS_GAME_DUPLICATE:
            return True
    return False


def main():
    keys = sys.argv[1:] or GAME_ORDER
    games = [get_game(k) for k in keys]
    overrides = load_overrides()
    print(f"overrides loaded: {len(overrides)}")
    for game in games:
        build_game(game, overrides)


if __name__ == "__main__":
    main()
