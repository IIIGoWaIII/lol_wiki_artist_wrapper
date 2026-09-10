#!/usr/bin/env python3
"""
Builds data/skins.json for the LoL wiki reference wrapper.

1. Fetches Module:SkinData/data (Lua table) from the League of Legends wiki.
2. Parses the Lua dialect into plain data structures.
3. Discovers splash-art files via the wiki image index (allimages prefix search)
   and pulls the full revision history of each canonical skin file.
4. Collapses "small iterations" of the same artwork using perceptual hashing
   (dHash) so only distinct repaints are shown, then upgrades every artwork to
   its best available resolution (_HD / _oldN_HD files), newest art first.
5. Writes a compact JSON file consumed by the web app.

Usage: python build_data.py       (requires Pillow)
"""

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from io import BytesIO

from PIL import Image

LUA_URL = "https://wiki.leagueoflegends.com/en-us/Module:SkinData/data?action=raw"
API_URL = "https://wiki.leagueoflegends.com/en-us/api.php"
USER_AGENT = "lol-wiki-reference-wrapper/1.0 (local artist tool)"
OVERRIDES_PATH = "data/artwork_overrides.json"

# Perceptual-hash settings (0-64 bits hamming distance).
# CLUSTER_THRESHOLD: revisions within this distance count as the same artwork.
# A sibling file (_oldN/_Unused/_HD) within the same distance of an artwork is
# treated as that art, so the highest-resolution copy can be picked.
CLUSTER_THRESHOLD = 13
MATCH_THRESHOLD = 7
HASH_THUMB_WIDTH = 120

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


def skin_bases(champ: str, skin: str) -> list[str]:
    """Candidate file-base prefixes for a skin, light form first."""
    prefix = champ_prefix(champ)
    c1 = f"{prefix}_{skin_asset(skin)}Skin"
    c2 = f"{prefix}_{skin_asset(skin, aggressive=True)}Skin"
    return [c1] if c1 == c2 else [c1, c2]


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
    return 1200 if (art.get("w") or 0) > 2000 or str(art.get("url", "")).endswith("_HD.jpg") else 420


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


# ---------------------------------------------------------------------------
# Artwork timeline assembly
# ---------------------------------------------------------------------------

_OLD_RE = re.compile(r"^_old(\d*)(_HD)?$")
_UNUSED_RE = re.compile(r"^_Unused(\d*)(_HD)?$")
_SKIP_MARK = ("_Ch", "_WR", "_TFT", "_Mobile", "_Chr")  # other-game / non-splash files

# Art-creation dates for sibling files (_old/_Unused) are looked up lazily;
# see _enqueue_siblings / _flush_sibling_histories.
SIB_HIST = {}
_SIB_QUEUE = []
_SIB_SEEN = set()
_SIB_FN_RE = re.compile(r"_(?:old\d*|Unused\d*)(?:_HD)?\.jpg$")


def _sib_needs_date(fn: str) -> bool:
    return bool(_SIB_FN_RE.search(fn))


def _enqueue_siblings(files: dict):
    for fn in files:
        if fn in _SIB_SEEN or not _sib_needs_date(fn):
            continue
        _SIB_SEEN.add(fn)
        _SIB_QUEUE.append(fn)
        if len(_SIB_QUEUE) >= 45:
            _flush_sibling_histories()


def _flush_sibling_histories():
    if not _SIB_QUEUE:
        return
    chunk = _SIB_QUEUE[:45]
    del _SIB_QUEUE[:45]
    SIB_HIST.update(fetch_histories(chunk))


def art_date(fn: str, rec: dict, histories: dict, canon_sha_dates: dict) -> str:
    """Creation date of a sibling file's art.

    Prefer a byte-identical match against the canonical file history (the file
    may be a community copy of an earlier revision, re-uploaded later), then
    fall back to the sibling's own earliest revision, then its latest upload.
    """
    sha = rec.get("sha1")
    d = canon_sha_dates.get(sha)
    if d:
        return d
    revs = histories.get(fn) or SIB_HIST.get(fn)
    if revs:
        dates = [r["ts"][:10] for r in revs if r.get("ts")]
        if dates:
            return min(dates)
    return (rec.get("ts") or "")[:10]


def recover_art_date(
    base: str,
    fn: str,
    rec: dict,
    histories: dict,
    cache: dict,
    rev_h: dict,
) -> str | None:
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
    canon = histories.get(base + ".jpg")
    if not canon or not rec.get("url"):
        return None
    sib = cache.get(rec["url"])
    if sib is None:
        sib = fetch_thumb_hash(rec["url"], cache)
    if sib is None:
        return None
    creation = None
    revs = histories.get(fn) or SIB_HIST.get(fn)
    if revs:
        dates = [r["ts"][:10] for r in revs if r.get("ts")]
        if dates:
            creation = min(dates)
    if creation is None:
        creation = (rec.get("ts") or "")[:10]
    if not creation:
        return None
    if base not in rev_h:
        hashes = []
        for r in canon:
            if not r.get("url"):
                hashes.append(None)
                continue
            h = cache.get(r["url"])
            if h is None:
                h = fetch_thumb_hash(r["url"], cache)
            hashes.append(h)
        rev_h[base] = list(zip(canon, hashes))
    oldest = None
    for r, h in rev_h[base]:
        if not r.get("ts") or r["ts"][:10] >= creation:
            continue
        ok = h is not None and bin(h ^ sib).count("1") <= CLUSTER_THRESHOLD
        if ok:
            oldest = r["ts"][:10]
    return oldest


def classify_siblings(
    files: dict,
    base: str,
    histories: dict,
    canon_sha_dates: dict,
    cache: dict,
    rev_h: dict,
) -> tuple[list, list]:
    """Split sibling files into old-art and unused-art candidates.

    Returns (old_list, unused_list); each item is {url, w, h, d, n}.
    """
    olds, unuseds = [], []
    for fn, rec in files.items():
        if not fn.endswith(".jpg"):
            continue
        if fn == base + ".jpg":
            continue  # canonical file, handled via history
        rest = fn[:-4][len(base):]
        if not rest.startswith("_"):
            continue
        if any(m in rest for m in _SKIP_MARK):
            continue
        m = _OLD_RE.match(rest)
        if m:
            d = art_date(fn, rec, histories, canon_sha_dates)
            rd = recover_art_date(base, fn, rec, histories, cache, rev_h)
            if rd and (not d or rd < d):
                d = rd
            olds.append(
                {
                    "fn": fn,
                    "url": rec["url"],
                    "w": rec["w"],
                    "h": rec["h"],
                    "d": d,
                    "n": int(m.group(1) or 1),
                }
            )
            continue
        m = _UNUSED_RE.match(rest)
        if m:
            d = art_date(fn, rec, histories, canon_sha_dates)
            rd = recover_art_date(base, fn, rec, histories, cache, rev_h)
            if rd and (not d or rd < d):
                d = rd
            unuseds.append(
                {
                    "fn": fn,
                    "url": rec["url"],
                    "w": rec["w"],
                    "h": rec["h"],
                    "d": d,
                    "n": int(m.group(1) or 1),
                }
            )

    for lst in (olds, unuseds):
        by_fn = {c["fn"]: c for c in lst}
        for c in lst:
            if not c["fn"].endswith("_HD.jpg") or not c.get("d"):
                continue
            partner = by_fn.get(c["fn"][:-7] + ".jpg")
            if not partner or not partner.get("d") or partner["d"] >= c["d"]:
                continue
            h1 = cache.get(c["url"])
            if h1 is None:
                h1 = fetch_thumb_hash(c["url"], cache)
            h2 = cache.get(partner["url"])
            if h2 is None:
                h2 = fetch_thumb_hash(partner["url"], cache)
            if h1 and h2 and bin(h1 ^ h2).count("1") <= CLUSTER_THRESHOLD:
                c["d"] = partner["d"]

    for c in olds:
        del c["fn"]
    for c in unuseds:
        del c["fn"]
    return olds, unuseds


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


def build_timeline(base: str, revs: list[dict], force: list[str] | None, cache: dict, report: list) -> list[dict]:
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
    clusters = cluster_history(arts, cache)
    keeps = [pick_keep(cl, i == 0) for i, cl in enumerate(clusters)]
    # Backdate each artwork to when its family was first created: the oldest
    # revision in the cluster, so repaints/re-uploads don't masquerade as new
    # artworks. Image stays the newest revision; only the date moves.
    for cl, k in zip(clusters, keeps):
        k["d"] = cl[-1]["d"] or k["d"]
        k["ts"] = cl[-1]["ts"] or k["ts"]
    dropped = [a for a in arts if all(a is not k for k in keeps)]
    if dropped or len(keeps) > 1:
        report.append(
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


def assemble(
    base: str,
    files: dict,
    histories: dict,
    cache: dict,
    overrides: dict,
    report: list,
    canon_sha_dates: dict,
) -> dict | None:
    """Assemble the artwork payload for one skin base. Returns None if nothing found."""
    force = None
    if base in overrides:
        ov = overrides[base]
        force = ov if isinstance(ov, list) else ov.get("keep")

    arts = []
    revs = histories.get(base + ".jpg")
    if revs:
        arts = build_timeline(base, revs, force, cache, report)
    if not arts and not force:
        # No usable history (missing canonical file): synthesize from current art.
        cur = files.get(base + ".jpg") or files.get(base + "_HD.jpg")
        if not cur:
            return None
        arts = [{"url": cur["url"], "w": cur["w"], "h": cur["h"], "d": (cur["ts"] or "")[:10]}]
    if not arts:
        return None

    hd = files.get(base + "_HD.jpg")
    if hd and len(arts) == 1:
        arts[0]["url"], arts[0]["w"], arts[0]["h"] = hd["url"], hd["w"], hd["h"]

    rev_h = {}
    olds, unuseds = classify_siblings(files, base, histories, canon_sha_dates, cache, rev_h)
    cands = [dict(c, kind="old") for c in olds] + [dict(c, kind="unused") for c in unuseds]

    upgrade, extras = match_siblings(arts, cands, cache)
    for i, c in upgrade.items():
        arts[i]["url"], arts[i]["w"], arts[i]["h"] = c["url"], c["w"], c["h"]

    # A bare _HD file is a high-resolution copy of the current art; always use
    # it as the main image (never a separate version), regardless of how far its
    # downscaled hash drifts from the base file.
    if hd and "HD" not in arts[0]["url"]:
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
                "l": "Unused" if c["kind"] == "unused" else "Old",
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


def main():
    print("fetching lua data...")
    raw = http_get(LUA_URL).decode("utf-8")
    data = parse_lua(raw)
    if not isinstance(data, dict):
        sys.exit(f"parse produced {type(data)}, expected dict")

    champs = []
    for name, ent in data.items():
        if name.startswith("["):
            continue
        if not isinstance(ent, dict) or "skins" not in ent or not isinstance(ent["skins"], dict):
            continue
        if not isinstance(ent.get("id"), (int, float)):
            continue
        champs.append((name, ent))
    print(f"champions parsed: {len(champs)}")

    import os

    try:
        with open(OVERRIDES_PATH, encoding="utf-8") as f:
            overrides = json.load(f)
    except FileNotFoundError:
        overrides = {}
        try:
            os.makedirs("data", exist_ok=True)
        except OSError:
            pass
    print(f"overrides loaded: {len(overrides)}")

    # champion -> base prefixes -> skin records
    skin_info = []  # (champ_name, skin_key, skin_dict, bases, entry_id)
    champ_lookup = {}  # champ_name -> {skin_id: skin_key}
    champ_skins = {}  # champ_name -> {skin_key: skin_dict}
    canonical_files = []
    for name, ent in champs:
        csl = champ_lookup.setdefault(name, {})
        css = champ_skins.setdefault(name, {})
        for sk, info in ent["skins"].items():
            if not isinstance(info, dict):
                continue
            css[sk] = info
            skid = info.get("id")
            if isinstance(skid, (int, float)):
                csl[int(skid)] = sk
            bases = skin_bases(name, sk)
            skin_info.append((name, sk, info, bases))
            for b in bases:
                canonical_files.append(b + ".jpg")
    print(f"skins: {len(skin_info)}; fetching file histories...")
    histories = fetch_histories(canonical_files)

    canon_sha_dates = {}
    for fn, revs in histories.items():
        for r in revs:
            sha = r.get("sha1")
            ts = r.get("ts", "")[:10]
            if sha and ts:
                canon_sha_dates[sha] = min(canon_sha_dates.get(sha, ts), ts)

    print("discovering splash files via image index...")
    champ_cache = {}
    cache = {}  # thumb-hash cache {url: hash}

    def files_for_base(champ: str, base: str) -> dict:
        key = champ_prefix(champ)
        files = champ_cache.get(key)
        if files is None:
            files = discover_prefix(key)
            champ_cache[key] = files
            _enqueue_siblings(files)
            _flush_sibling_histories()
            histories.update(SIB_HIST)
        hits = {fn: r for fn, r in files.items() if fn == base + ".jpg" or fn.startswith(base + "_")}
        if not hits:
            files = discover_prefix(base)
            _enqueue_siblings(files)
            _flush_sibling_histories()
            histories.update(SIB_HIST)
            hits = {fn: r for fn, r in files.items() if fn == base + ".jpg" or fn.startswith(base + "_")}
        return hits

    def resolve(name, sk, info):
        for base in skin_bases(name, sk):
            files = files_for_base(name, base)
            if not files and base not in histories:
                continue
            payload = assemble(base, files, histories, cache, overrides, report, canon_sha_dates)
            if payload:
                return payload
        v = info.get("variant")
        if isinstance(v, (int, float)):
            bsk = champ_lookup.get(name, {}).get(int(v))
            if bsk:
                tinfo = champ_skins.get(name, {}).get(bsk) or {}
                return resolve(name, bsk, tinfo)
        return None

    report = []
    skins = []
    set_counts = {}
    missing_img = 0
    prev_champ = None
    done_champs = 0
    for name, sk, info, bases in skin_info:
        if name != prev_champ:
            prev_champ = name
            done_champs += 1
            if done_champs % 5 == 0 or done_champs == 1:
                print(f"  champion {done_champs}/{len(champs)}: {name}", flush=True)
        art = resolve(name, sk, info)
        rec = {
            "ch": name,
            "s": sk,
            "fmt": info.get("formatname"),
            "set": info.get("set"),
            "avail": info.get("availability"),
            "cost": info.get("cost"),
            "r": info.get("release"),
            "d": art["d"] if art else None,
            "art": info.get("splashartist") or [],
            "mu": info.get("music"),
            "cr": len(info.get("chromas") or {}) if isinstance(info.get("chromas"), dict) else 0,
            "mid": info.get("id"),
            "img": art["img"] if art else None,
            "t": art["t"] if art else None,
            "w": art["w"] if art else None,
            "h": art["h"] if art else None,
        }
        if art and art.get("v"):
            rec["v"] = art["v"]
        if not rec["img"]:
            missing_img += 1
        st = rec["set"]
        if isinstance(st, list):
            for s in st:
                set_counts[s] = set_counts.get(s, 0) + 1
        skins.append(rec)

    _flush_sibling_histories()
    histories.update(SIB_HIST)

    sets = sorted(set_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    meta = {
        "gen": time.strftime("%Y-%m-%d"),
        "championCount": len(champs),
        "skinCount": len(skins),
        "missingImage": missing_img,
        "champions": [c for c, _ in champs],
        "sets": sets,
    }
    payload = {"meta": meta, "skins": skins}
    os.makedirs("data", exist_ok=True)
    with open("data/skins.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))

    print(f"wrote data/skins.json: {len(skins)} skins, {len(sets)} sets, {missing_img} skins without image")
    if report:
        print(f"multi-art skins ({len(report)}):")
        for line in report:
            print("  " + line)


if __name__ == "__main__":
    main()