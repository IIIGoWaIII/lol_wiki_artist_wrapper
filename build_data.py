#!/usr/bin/env python3
"""
Builds data/skins.json for the LoL wiki reference wrapper.

1. Fetches Module:SkinData/data (Lua table) from the League of Legends wiki.
2. Parses the Lua dialect into plain data structures.
3. Derives splash-art filenames for every skin and verifies them in batches
   against the MediaWiki API (redirects + imageinfo), falling back to the
   base skin image for variant skins that share splash art.
4. Writes a compact JSON file consumed by the web app.

Usage: python build_data.py
"""

import json
import re
import sys
import time
import urllib.parse
import urllib.request

LUA_URL = "https://wiki.leagueoflegends.com/en-us/Module:SkinData/data?action=raw"
API_URL = "https://wiki.leagueoflegends.com/en-us/api.php"
USER_AGENT = "lol-wiki-reference-wrapper/1.0 (local artist tool)"

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
            # long string  [==[ ... ]==]
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
    entries = []  # (key_or_None, value, explicit_bool)
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


# ---------------------------------------------------------------------------
# Filename derivation + verification
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


def skin_variants(base: str) -> list[str]:
    """Candidate filenames for one splash base, best quality first.

    The wiki stores several suffixes per splash art - "_HD" for the high-res
    render, "_old"/"_old2" for pre-rework artwork, and "_Unused" for
    cancelled/concept artwork. Return them ordered so the first existing
    file is the current, best-quality version.
    """
    return [
        base + "_HD.jpg",
        base + "_old_HD.jpg",
        base + "_old2_HD.jpg",
        base + "_Unused_HD.jpg",
        base + "_Unused2_HD.jpg",
        base + ".jpg",
        base + "_old.jpg",
        base + "_old2.jpg",
        base + "_Unused.jpg",
        base + "_Unused2.jpg",
    ]


def version_rank(fn: str) -> int:
    """Recency rank of a version filename: current=0, old=1, old2=2, unused=3/4."""
    stem = fn[:-4]
    if "_old2" in stem:
        return 2
    if "_old" in stem:
        return 1
    if "_Unused2" in stem:
        return 4
    if "_Unused" in stem:
        return 3
    return 0


def version_label(fn: str) -> str:
    """Human label for a version filename, e.g. "Old HD", "Standard"."""
    stem = fn[:-4]
    tags = []
    if "_HD" in stem:
        tags.append("HD")
    if "_old2" in stem:
        tags.append("Old 2")
    elif "_old" in stem:
        tags.append("Old")
    elif "_Unused2" in stem:
        tags.append("Unused 2")
    elif "_Unused" in stem:
        tags.append("Unused")
    return " ".join(tags) if tags else "Standard"


def verify_files(filenames):
    """Batch-verify File: titles; returns {filename: {full, thumb, w, h}}."""
    out = {}
    uniq = sorted(set(filenames))
    for start in range(0, len(uniq), 50):
        batch = uniq[start : start + 50]
        titles = "|".join("File:" + urllib.parse.quote(n, safe="'") for n in batch)
        url = (
            API_URL
            + "?action=query&format=json&formatversion=2&redirects=1"
            + "&prop=imageinfo&iiprop=url%7Csize&titles="
            + urllib.parse.quote(titles, safe="|'%")
        )
        raw = http_get(url)
        data = json.loads(raw)
        if "error" in data:
            print("API ERROR:", json.dumps(data["error"])[:300], file=sys.stderr)
            print("URL:", url[:400], file=sys.stderr)
            continue
        pages = data.get("query", {}).get("pages", [])
        if not pages:
            print("NO PAGES for batch:", url[:400], file=sys.stderr)
        for page in pages:
            if "missing" in page or "imageinfo" not in page:
                continue
            fn = page["title"].removeprefix("File:").replace(" ", "_")
            info = page["imageinfo"][0]
            url_full = info["url"]
            base = url_full.split("?")[0]
            if "/images/" in base:
                stem = urllib.parse.unquote(base.split("/images/", 1)[1])
            else:
                stem = urllib.parse.unquote(fn)
            is_hd = fn.endswith("_HD.jpg") or info.get("width", 0) > 2000
            thumb_w = 1200 if is_hd else 420
            thumb = (
                "https://wiki.leagueoflegends.com/en-us/images/thumb/"
                + urllib.parse.quote(stem, safe="_'() ")
                + f"/{thumb_w}px-"
                + urllib.parse.quote(stem, safe="_'() ")
            )
            out[fn] = {
                "full": url_full,
                "thumb": thumb,
                "w": info.get("width"),
                "h": info.get("height"),
            }
        time.sleep(0.15)
    return out


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

    candidates = {}  # (champ, skin) -> list of filenames to try
    lookup = {}  # skin_id -> (champ, skin_name)
    for name, ent in champs:
        prefix = champ_prefix(name)
        for sk, info in ent["skins"].items():
            if not isinstance(info, dict):
                continue
            skid = info.get("id")
            if isinstance(skid, (int, float)):
                lookup[int(skid)] = (name, sk)
            c1 = f"{prefix}_{skin_asset(sk)}Skin"
            c2 = f"{prefix}_{skin_asset(sk, aggressive=True)}Skin"
            lst = skin_variants(c1)
            if c2 != c1:
                lst += skin_variants(c2)
            candidates[(name, sk)] = lst

    all_filenames = [fn for _, l in candidates.items() for fn in l]
    print(f"candidate filenames: {len(all_filenames)}; verifying via API...")
    verified = verify_files(all_filenames)
    print(f"verified unique files: {len(verified)}")

    # map each candidate to the ordered list of verified version records
    res = {}
    for key, names in candidates.items():
        seen = set()
        lst = []
        for n in names:
            rec = verified.get(n)
            if rec and rec["full"] not in seen:
                seen.add(rec["full"])
                lst.append((n, rec))
        res[key] = lst

    # variant fallback
    def resolve(name, sk, info):
        lst = res.get((name, sk))
        if lst:
            return lst
        v = info.get("variant")
        if isinstance(v, (int, float)):
            base = lookup.get(int(v))
            if base:
                bname, bsk = base
                blst = res.get((bname, bsk))
                if blst:
                    return blst
        return None

    skins = []
    set_counts = {}
    missing_img = 0
    for name, ent in champs:
        ids = ent.get("id")
        for sk, info in ent["skins"].items():
            if not isinstance(info, dict):
                continue
            versions = resolve(name, sk, info)
            img = versions[0][1] if versions else None
            rec = {
                "ch": name,
                "s": sk,
                "fmt": info.get("formatname"),
                "set": info.get("set"),
                "avail": info.get("availability"),
                "cost": info.get("cost"),
                "r": info.get("release"),
                "art": info.get("splashartist") or [],
                "mu": info.get("music"),
                "cr": len(info.get("chromas") or {}) if isinstance(info.get("chromas"), dict) else 0,
                "mid": info.get("id"),
                "img": img["full"] if img else None,
                "t": img["thumb"] if img else None,
                "w": (img or {}).get("w"),
                "h": (img or {}).get("h"),
            }
            if versions:
                arts = {}
                for fn, r in versions:
                    art = fn[:-4].removesuffix("_HD")
                    arts.setdefault(art, (fn, r))
                primary_art = arts[next(iter(arts))][0][:-4].removesuffix("_HD")
                others = [(fn, r) for art, (fn, r) in arts.items() if art != primary_art]
                if others:
                    rec["v"] = [
                        {
                            "l": version_label(fn),
                            "img": r["full"],
                            "t": r["thumb"],
                            "w": r["w"],
                            "h": r["h"],
                        }
                        for fn, r in others
                    ]
            if not rec["img"]:
                missing_img += 1
            st = rec["set"]
            if isinstance(st, list):
                for s in st:
                    set_counts[s] = set_counts.get(s, 0) + 1
            skins.append(rec)

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
    import os

    os.makedirs("data", exist_ok=True)
    with open("data/skins.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))

    print(
        f"wrote data/skins.json: {len(skins)} skins, {len(sets)} sets, "
        f"{missing_img} skins without image"
    )


if __name__ == "__main__":
    main()