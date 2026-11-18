#!/usr/bin/env python3
"""
Finds splashes that are literally the same file under different skins and
writes data/dupes.json.

Riot ships one illustration for some groups: the four Cafe Cuties champions
share a single splash, as do the True Damage "Know My Name" skins. Those are
separate catalogue entries pointing at byte-identical images.

Only identical bytes count. Different crops of the same painting (the K/DA
FIRESTARTER splashes, for example) are different artwork and stay separate.
A group larger than MAX_GROUP is not a shared splash but the wiki's fallback
image for retired files, so it is ignored.

  python build_dupes.py        # thumbs cached in .cache/thumb-sha1.json
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
CACHE_PATH = os.path.join(ROOT, ".cache", "thumb-sha1.json")
OUT_PATH = os.path.join(DATA_DIR, "dupes.json")
GAMES = {"lol": "skins.json", "wr": "skins-wr.json", "lor": "skins-lor.json"}
USER_AGENT = "lol-wiki-reference-wrapper/1.0 (local artist tool)"
MAX_GROUP = 8


def load_cache() -> dict:
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def save_cache(cache: dict) -> None:
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(dict(cache), f, separators=(",", ":"))


def fetch_sha(url: str, cache: dict) -> tuple[str, str | None]:
    if url in cache:
        return url, cache[url]
    # A truncated response raises http.client.IncompleteRead, which is not an
    # OSError, so an explicit exception list would let it escape and kill the
    # refresh. Catch broadly, like build_data.http_get, and leave the url out of
    # the cache so the next run retries it.
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=60) as r:
                digest = hashlib.sha1(r.read()).hexdigest()
            cache[url] = digest
            return url, digest
        except Exception:  # noqa: BLE001
            if attempt == 2:
                return url, None
            time.sleep(1.5 * (attempt + 1))
    return url, None


def main() -> None:
    cache = load_cache()
    out: dict[str, dict[str, str]] = {}
    for game, filename in GAMES.items():
        path = os.path.join(DATA_DIR, filename)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        recs = data.get("skins") or []
        missing = []
        for rec in recs:
            url = rec.get("t") or rec.get("img")
            if url and url not in cache and url not in missing:
                missing.append(url)
        print(f"{game}: {len(recs)} skins, {len(missing)} new thumbs")
        if missing:
            unhashed = 0
            with ThreadPoolExecutor(max_workers=8) as pool:
                for i, (_, digest) in enumerate(pool.map(lambda u: fetch_sha(u, cache), missing), 1):
                    if digest is None:
                        unhashed += 1
                    if i % 200 == 0:
                        print(f"  hashed {i}/{len(missing)}")
                        save_cache(cache)
            if unhashed:
                print(f"  {unhashed}/{len(missing)} thumbs could not be fetched, retrying next run")

        groups: dict[str, list[dict]] = {}
        for rec in recs:
            url = rec.get("t") or rec.get("img")
            h = cache.get(url)
            if not h:
                continue
            groups.setdefault(h, []).append(rec)

        dupes = {}
        for h, members in groups.items():
            if len(members) < 2 or len(members) > MAX_GROUP:
                continue
            primary = members[0]
            primary_key = f"{game}:{primary['ch']}:{primary['s']}"
            for rec in members[1:]:
                dupes[f"{game}:{rec['ch']}:{rec['s']}"] = primary_key
        out[game] = dupes
        shared = sum(1 for m in groups.values() if 2 <= len(m) <= MAX_GROUP)
        print(f"{game}: {len(dupes)} shared skins across {shared} paintings")

    save_cache(cache)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"wrote {OUT_PATH}: {sum(len(v) for v in out.values())} duplicates")


if __name__ == "__main__":
    main()
