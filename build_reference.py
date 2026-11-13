#!/usr/bin/env python3
"""
Builds data/reference.json for the Reference tab -- a general-purpose visual
reference board next to the game splash catalogues.

Two open libraries, each with the metadata an artist filters by:

  film  film-grab.com    curated film stills, tagged by director, director of
                         photography, production designer, genre, country, year
                         and aspect ratio.
  art   imaginemore.art  the Classic Art library: paintings with artist, year
                         and movement. (Imagine More's Cinematic/Game/Animated
                         libraries are paywalled past a 150-item preview, so
                         Classic Art is the one that can be crawled in full.)

film-grab is WordPress: its REST API lists every film post, and each post holds
its whole still gallery. Every still from every film would be ~500k files, so a
spread of `--stills` frames per film is kept -- enough to read the look of a
film without shipping the site.

Usage: python build_reference.py [--only film] [--only art] [--films N]
                                 [--stills N] [--art N] [--refresh]
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import tagmerge

DATA_DIR = "data"
OUT_PATH = os.path.join(DATA_DIR, "reference.json")
# Every API response is cached: film-grab rate-limits a crawl that asks for 42
# pages of ~250 KB, and a rerun after a limit error should resume rather than
# start over. Delete the directory (or pass --refresh) to refetch.
CACHE_DIR = os.path.join(".cache", "reference")
USER_AGENT = "lol-wiki-reference-wrapper/1.0 (local artist tool)"
PAGE_DELAY = 1.0

FILM_API = "https://film-grab.com/wp-json/wp/v2"
IMAGINE_API = "https://imaginemore.art/api/assets"
IMAGINE_LIBRARY = "Classic Art"

# film-grab gallery markup: .../photo-gallery/thumb/<file>.jpg, the full-size
# copy sits in the parent directory. Older posts use "01 (1165).jpg" names, so
# the capture has to run to the closing quote rather than the first space.
THUMB_RE = re.compile(r"photo-gallery/thumb/([^\"']+)")
STILL_EXT = (".jpg", ".jpeg", ".png", ".webp")

# Category roots that carry the per-film metadata.
ROOT_FIELDS = {
    "!directors": "dir",
    "!dps": "dp",
    "!production designer": "pd",
    "!genre": "gen",
    "!country": "cty",
}
YEAR_RE = re.compile(r"^\d{4}$")
DECADE_RE = re.compile(r"^\d{4}s$")
ASPECT_RE = re.compile(r"^\d+(?:\.\d+)?\s*:\s*\d+(?:\.\d+)?$")


REFRESH = False


def cache_path(url: str) -> str:
    name = hashlib.sha1(url.encode("utf-8")).hexdigest()[:20]
    return os.path.join(CACHE_DIR, name + ".json")


def http_json(url: str, retries: int = 5):
    """GET JSON, through the on-disk cache, backing off when a host says 429."""
    cached = cache_path(url)
    if not REFRESH and os.path.exists(cached):
        with open(cached, encoding="utf-8") as f:
            return json.load(f), {}
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=90) as r:
                data = json.load(r)
                headers = dict(r.headers)
            os.makedirs(CACHE_DIR, exist_ok=True)
            with open(cached, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            return data, headers
        except urllib.error.HTTPError as e:
            if attempt == retries - 1:
                raise
            wait = 20 * (attempt + 1)
            if e.code == 429:
                try:
                    wait = max(wait, int(e.headers.get("Retry-After") or 0))
                except (TypeError, ValueError):
                    pass
                print(f"  429 from {urllib.parse.urlsplit(url).netloc}, waiting {wait}s", file=sys.stderr)
            time.sleep(wait)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            if attempt == retries - 1:
                raise
            print(f"  retry {attempt + 1}: {url} ({e})", file=sys.stderr)
            time.sleep(2 * (attempt + 1))


def paginate(url: str, fields: str, limit: int, per_page: int = 100):
    """Walks a WordPress list endpoint, yielding items until `limit` or the end.

    Stops on a short page rather than X-WP-TotalPages: cached responses have no
    headers, and a short page is just as definitive.
    """
    got = 0
    page = 1
    while got < limit:
        sep = "&" if "?" in url else "?"
        try:
            data, _ = http_json(f"{url}{sep}per_page={per_page}&page={page}&_fields={fields}")
        except urllib.error.HTTPError as e:
            if e.code == 400:  # past the last page
                return
            raise
        if not data:
            return
        for item in data:
            yield item
            got += 1
            if got >= limit:
                return
        if len(data) < per_page:
            return
        page += 1
        time.sleep(PAGE_DELAY)


def film_categories() -> dict[int, tuple[str, int]]:
    """id -> (name, parent). A few hundred requests otherwise, so page through."""
    cats: dict[int, tuple[str, int]] = {}
    page = 1
    while True:
        try:
            data, _ = http_json(f"{FILM_API}/categories?per_page=100&page={page}&_fields=id,name,parent")
        except urllib.error.HTTPError as e:
            if e.code == 400:
                break
            raise
        if not data:
            break
        for c in data:
            cats[c["id"]] = (c["name"], c["parent"])
        if len(data) < 100:
            break
        page += 1
        time.sleep(PAGE_DELAY)
    return cats


def category_root(cats: dict[int, tuple[str, int]], cid: int) -> str:
    """Walks up to the !Root taxonomy term (directors, DPs, ...)."""
    seen = 0
    while cid and seen < 6:
        name, parent = cats.get(cid, ("", 0))
        if name.lower() in ROOT_FIELDS:
            return name.lower()
        if not parent:
            return ""
        cid = parent
        seen += 1
    return ""


def film_group(cats: dict[int, tuple[str, int]], ids: list[int]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for cid in ids or []:
        name = cats.get(cid, (None, 0))[0]
        if not name or name.startswith("!"):
            continue
        root = category_root(cats, cid)
        if root:
            out.setdefault(ROOT_FIELDS[root], []).append(name)
        elif YEAR_RE.match(name):
            out["year"] = [name]
        elif DECADE_RE.match(name):
            out.setdefault("decade", []).append(name[:-1])
        elif ASPECT_RE.match(name):
            out.setdefault("aspect", []).append(name.replace(" ", ""))
    return out


def build_films(limit: int, stills: int) -> tuple[list[dict], list[dict]]:
    print("film-grab: reading category taxonomy")
    cats = film_categories()
    print(f"  {len(cats)} categories")

    # Imagine More's records carry a creator per item; film-grab splits director,
    # DP and designer out of the post's categories. The web app reads one shape.
    films: list[dict] = []
    items: list[dict] = []
    skipped = 0
    for post in paginate(f"{FILM_API}/posts", "id,title,date,categories,content,link", limit):
        title = html.unescape(re.sub(r"<[^>]+>", "", post.get("title", {}).get("rendered", ""))).strip()
        content = post.get("content", {}).get("rendered", "")
        files = []
        for m in THUMB_RE.finditer(content):
            raw = m.group(1).split("?")[0].strip().rstrip("\\")
            name = urllib.parse.unquote(raw)
            if name.lower().endswith(STILL_EXT) and name not in files:
                files.append(name)
        if not title or not files:
            skipped += 1
            continue

        groups = film_group(cats, post.get("categories") or [])
        year = (groups.get("year") or groups.get("decade") or [""])[0]
        idx = len(films)
        films.append(
            {
                "t": title,
                "y": year,
                "dir": groups.get("dir") or [],
                "dp": groups.get("dp") or [],
                "pd": groups.get("pd") or [],
                "gen": groups.get("gen") or [],
                "cty": groups.get("cty") or [],
                "ar": (groups.get("aspect") or [""])[0],
                "u": post.get("link", ""),
            }
        )

        # Frames run front to back through the film, so an even spread is more
        # useful than the first N (which are all one scene).
        if len(files) > stills:
            step = (len(files) - 1) / max(stills - 1, 1)
            files = [files[round(i * step)] for i in range(stills)]

        for name in files:
            items.append(
                {
                    "src": "film",
                    "f": idx,
                    "id": name,
                    "u": "https://film-grab.com/wp-content/uploads/photo-gallery/"
                    + urllib.parse.quote(name, safe="()"),
                }
            )
        if idx % 100 == 99:
            print(f"  {idx + 1} films, {len(items)} stills")

    print(f"film-grab: {len(films)} films, {len(items)} stills, {skipped} skipped")
    return films, items


def build_art(limit: int, page_size: int = 1000) -> list[dict]:
    print(f"imagine more: {IMAGINE_LIBRARY}, using {limit} images")
    items: list[dict] = []
    seen: set[str] = set()
    offset = 0
    empty_pages = 0
    while len(items) < limit:
        url = f"{IMAGINE_API}?" + urllib.parse.urlencode({"library": IMAGINE_LIBRARY, "offset": offset})
        data, _ = http_json(url)
        assets = data.get("assets") or []
        if not assets:
            break
        before = len(items)
        for a in assets:
            image = a.get("imageUrl")
            if not image or image in seen:
                continue
            seen.add(image)
            ar = a.get("aspect_ratio")
            items.append(
                {
                    "src": "art",
                    "id": a.get("id"),
                    "t": (a.get("name") or "").strip(),
                    "cr": (a.get("user") or "").strip(),
                    "y": (a.get("date") or "").strip(),
                    "tag": (a.get("tags") or "").strip(),
                    "ar": round(float(ar), 2) if ar else 0,
                    "u": image,
                    "p": a.get("path") or "",
                }
            )
            if len(items) >= limit:
                break
        print(f"  {len(items)} images")
        # The API's anonymous window is smaller than the library it advertises:
        # past a few thousand rows the ordering repeats, so pages stop adding
        # anything. Three empty pages in a row is the end of what is readable.
        empty_pages = 0 if len(items) > before else empty_pages + 1
        if empty_pages >= 3:
            break
        offset += page_size
        if len(items) < limit:
            time.sleep(PAGE_DELAY)

    print(f"imagine more: {len(items)} images")
    return items


def write(films: list[dict], items: list[dict]) -> None:
    counts: dict[str, int] = {}
    for it in items:
        counts[it["src"]] = counts.get(it["src"], 0) + 1
    meta = {
        "gen": time.strftime("%Y-%m-%d"),
        "label": "Reference",
        "counts": counts,
        "sources": [
            ["film", "Cinematic", "film stills, film-grab.com"],
            ["art", "Classic Art", "paintings, imaginemore.art"],
        ],
    }

    os.makedirs(DATA_DIR, exist_ok=True)
    # Keep the previous generation date when nothing but the date moved, so the
    # weekly job only commits when a library actually gained something.
    try:
        with open(OUT_PATH, encoding="utf-8") as f:
            old = json.load(f)
    except (OSError, json.JSONDecodeError):
        old = None
    if old and old.get("meta", {}).get("gen"):
        same = old.get("items") == items and old.get("films") == films and {
            k: v for k, v in old["meta"].items() if k != "gen"
        } == {k: v for k, v in meta.items() if k != "gen"}
        if same:
            meta["gen"] = old["meta"]["gen"]

    payload = {"meta": meta, "films": films, "items": items}
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    size = os.path.getsize(OUT_PATH) / 1e6
    print(f"wrote {OUT_PATH}: {len(items)} references ({size:.1f} MB)")


def main():
    global REFRESH
    ap = argparse.ArgumentParser(description="Build the reference board catalogue")
    ap.add_argument("--only", choices=["film", "art"], action="append",
                    help="crawl only this library (repeatable; default: both)")
    ap.add_argument("--films", type=int, default=5000, help="films to crawl (film-grab has ~4200)")
    ap.add_argument("--stills", type=int, default=8, help="stills kept per film")
    ap.add_argument("--art", type=int, default=4000, help="classic art images to keep (the free window is ~3.5k)")
    ap.add_argument("--refresh", action="store_true", help="ignore the response cache and refetch")
    args = ap.parse_args()
    REFRESH = args.refresh
    sources = args.only or ["film", "art"]

    # A single-source run keeps the other half from the previous file: the tab
    # filters across sources, so the two have to agree on the film indices.
    films: list[dict] = []
    items: list[dict] = []
    if set(sources) != {"film", "art"} and os.path.exists(OUT_PATH):
        with open(OUT_PATH, encoding="utf-8") as f:
            old = json.load(f)
        films = old.get("films") or []
        items = old.get("items") or []

    if "film" in sources:
        films, film_items = build_films(args.films, args.stills)
        items = [i for i in items if i["src"] != "film"] + film_items
    if "art" in sources:
        art_items = build_art(args.art)
        items = [i for i in items if i["src"] != "art"] + art_items

    # Scene tags from tag_images.py survive a rebuild: the tag pass is expensive,
    # this lookup is not.
    scene_tags = tagmerge.load()
    for it in items:
        tag = scene_tags.get(f"ref:{it['src']}:{it['id']}")
        if tag:
            tagmerge.for_reference(it, tag)

    write(films, items)


if __name__ == "__main__":
    main()
