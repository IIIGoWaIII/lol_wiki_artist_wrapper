#!/usr/bin/env python3
"""
Tags catalogue images with scene facets and a caption.

Uses the local `opencode run` agent as the vision engine instead of an API key:
it reads the attached images through the same OpenCode subscription the session
runs on, so there is no separate credential to buy or leak.

Every image is cached under .cache/tags/<key>.json, so a run resumes where it
stopped and new catalogue entries are the only work next time. The aggregate is
written to data/tags.json; build_reference.py and build_data.py merge it into
their catalogues, and --merge patches the existing JSON in place for an
immediate result without a rebuild.

  python tag_images.py reference                     # every reference image
  python tag_images.py skins --game lol              # one game's splashes
  python tag_images.py reference --limit 40 --dry    # pilot, prints labels
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import html
import io
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from PIL import Image

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
CACHE_DIR = os.path.join(ROOT, ".cache", "tags")
IMG_DIR = os.path.join(ROOT, ".cache", "tag-img")
TAGS_PATH = os.path.join(DATA_DIR, "tags.json")
DATA_FILES = {
    "lol": "skins.json",
    "wr": "skins-wr.json",
    "lor": "skins-lor.json",
}
REFERENCE_PATH = os.path.join(DATA_DIR, "reference.json")
USER_AGENT = "lol-wiki-reference-wrapper/1.0 (local artist tool)"
DEFAULT_MODEL = "opencode-go/deepseek-v4.1-flash"

# Facets are closed lists on purpose: free-form tags fragment into "railway
# station" / "station platform" / "train platform" and make search worse.
VOCAB = {
    "place": [
        "train station", "subway", "airport", "train interior", "car interior", "bus",
        "boat", "kitchen", "bedroom", "living room", "bathroom", "office", "classroom",
        "hospital", "laboratory", "library", "museum", "church", "temple", "throne room",
        "tavern", "ballroom", "corridor", "staircase", "elevator", "factory", "warehouse",
        "prison", "courtroom", "theatre", "stage", "shop", "restaurant", "street", "alley",
        "rooftop", "balcony", "garden", "park", "forest", "jungle", "desert", "field",
        "mountain", "cliff", "beach", "ocean", "river", "lake", "swamp", "road", "highway",
        "bridge", "battlefield", "ruins", "castle", "village", "city", "industrial yard",
        "snow", "space", "procession", "execution ground", "circus", "stadium", "market",
        "crossing", "graveyard", "cave", "bridge deck", "ship deck", "window",
    ],
    "setting": ["interior", "exterior", "both", "unknown"],
    "light": [
        "daylight", "overcast", "dusk", "night", "moonlight", "neon", "candlelit",
        "firelight", "warm lamp", "fluorescent", "backlit", "silhouette", "high contrast",
        "low key", "fog", "harsh sun", "soft light", "colored light",
    ],
    "weather": ["clear", "rain", "snow", "fog", "storm", "dust", "smoke", "haze"],
    "people": ["none", "single", "few", "crowd"],
    "shot": ["close-up", "portrait", "full body", "wide", "landscape", "detail", "overhead"],
    "mood": [
        "calm", "tense", "melancholic", "romantic", "violent", "awe", "eerie", "joyful",
        "lonely", "ominous", "playful", "epic", "solemn", "grief", "ecstatic", "weary",
    ],
}

SCHEMA = """Return ONLY a JSON array with one object per attached image, in the same order.
Each object has exactly these keys:
  "place": array of 0-3 short lowercase phrases, preferably from the vocabulary
  "setting": "interior" | "exterior" | "both" | "unknown"
  "light": array of 1-3 short lowercase phrases
  "weather": array of 0-2 short lowercase phrases
  "people": "none" | "single" | "few" | "crowd"
  "shot": "close-up" | "portrait" | "full body" | "wide" | "landscape" | "detail" | "overhead"
  "mood": array of 1-3 short lowercase words
  "caption": one factual sentence, max 18 words, no proper nouns, no camera or film jargon

Vocabulary (prefer these exact words; a close equivalent only when nothing fits):
__VOCAB__

Judge only what is visible. For abstracts, textures and skies use empty place,
"unknown" setting and "detail" shot instead of guessing. No markdown, no commentary,
no code fences: the array must parse as JSON."""


def prompt_for(n: int) -> str:
    vocab = "\n".join(f"{k}: {', '.join(v)}" for k, v in VOCAB.items())
    return f"The {n} attached images are in order, 1 to {n}.\n\n" + SCHEMA.replace("__VOCAB__", vocab)


# --- work lists -------------------------------------------------------------

def reference_items() -> list[dict]:
    with open(REFERENCE_PATH, encoding="utf-8") as f:
        data = json.load(f)
    out = []
    for it in data.get("items", []):
        key = f"ref:{it['src']}:{it['id']}"
        out.append({"key": key, "url": it["u"], "label": it.get("t") or it.get("id")})
    return out


def skin_items(games: list[str]) -> list[dict]:
    out = []
    for game in games:
        path = os.path.join(DATA_DIR, DATA_FILES[game])
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for rec in data.get("skins", []):
            if not rec.get("img"):
                continue
            out.append(
                {
                    "key": f"skin:{game}:{rec['ch']}:{rec['s']}",
                    "url": rec.get("t") or rec["img"],
                    "label": f"{rec['ch']} {rec['s']}",
                }
            )
    return out


# --- image cache ------------------------------------------------------------

def cache_name(key: str) -> str:
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:24]


def fetch_url(url: str) -> str:
    """Some catalogue paths were stored entity-escaped, and film-grab 404s on them."""
    if "&#" not in urllib.parse.unquote(url):
        return url
    return urllib.parse.quote(html.unescape(urllib.parse.unquote(url)), safe=":/?&=#")


def image_path(item: dict) -> str | None:
    os.makedirs(IMG_DIR, exist_ok=True)
    path = os.path.join(IMG_DIR, cache_name(item["key"]) + ".jpg")
    if os.path.exists(path):
        return path
    url = fetch_url(item["url"])
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=90) as r:
                raw = r.read()
            im = Image.open(io.BytesIO(raw)).convert("RGB")
            w, h = im.size
            scale = 640 / max(w, h)
            if scale < 1:
                im = im.resize((round(w * scale), round(h * scale)), Image.LANCZOS)
            im.save(path, "JPEG", quality=78)
            return path
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt == 2:
                return None
            time.sleep(1 + attempt)
    return None


# --- agent call -------------------------------------------------------------

def opencode_cmd() -> list[str]:
    """The CLI is a .cmd shim on Windows, which CreateProcess will not run directly."""
    if os.name == "nt":
        exe = os.path.join(os.environ.get("APPDATA", ""), "npm", "node_modules", "@opencode", "cli", "bin", "opencode.exe")
        if os.path.exists(exe):
            return [exe]
    exe = shutil.which("opencode")
    if not exe:
        raise SystemExit("opencode CLI not found on PATH")
    if os.name == "nt" and exe.lower().endswith((".cmd", ".bat")):
        return ["cmd", "/c", exe]
    return [exe]


def run_batch(batch: list[dict], model: str, timeout: int) -> tuple[list[dict], dict, list[dict]]:
    """Taggable items, their rows and usage. Unreadable images are dropped, not fatal."""
    kept, paths = [], []
    for it in batch:
        path = image_path(it)
        if path:
            kept.append(it)
            paths.append(path)
    if not kept:
        return [], {}, []
    cmd = opencode_cmd() + ["run", "--standalone", "--archived", "--format", "json", "-m", model]
    for p in paths:
        cmd += ["--file", p]
    cmd.append(prompt_for(len(kept)))

    # stdin must be closed: `opencode run` blocks until stdin hits EOF, and an
    # inherited ssh channel or terminal pipe never does. That alone made every
    # call hang until the timeout with zero tokens spent.
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        stdin=subprocess.DEVNULL,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"opencode exit {proc.returncode}: {(proc.stderr or proc.stdout)[-300:]}")

    texts, usage = [], {}
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "text" and isinstance(ev.get("part", {}).get("text"), str):
            texts.append(ev["part"]["text"])
        elif ev.get("type") == "step_finish":
            tokens = (ev.get("part") or {}).get("tokens") or {}
            for k in ("input", "output", "reasoning"):
                usage[k] = usage.get(k, 0) + int(tokens.get(k) or 0)

    text = "\n".join(texts)
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end <= start:
        raise ValueError("no JSON array in model output: " + text[:200])
    rows = json.loads(text[start : end + 1])
    if not isinstance(rows, list) or len(rows) != len(kept):
        raise ValueError(f"expected {len(kept)} objects, got {len(rows) if isinstance(rows, list) else type(rows)}")
    return rows, usage, kept


def clean_row(row: dict) -> dict:
    def arr(v, allowed=None, limit=3):
        vals = [str(x).strip().lower() for x in (v or []) if str(x).strip()][:limit]
        return [x for x in vals if allowed is None or x in allowed]

    out = {
        "place": arr(row.get("place"), VOCAB["place"]),
        "setting": str(row.get("setting", "unknown")).lower(),
        "light": arr(row.get("light"), VOCAB["light"]),
        "weather": arr(row.get("weather"), VOCAB["weather"], 2),
        "people": str(row.get("people", "none")).lower(),
        "shot": str(row.get("shot", "detail")).lower(),
        "mood": arr(row.get("mood"), VOCAB["mood"]),
        "caption": re.sub(r"\s+", " ", str(row.get("caption", ""))).strip(),
    }
    if out["setting"] not in VOCAB["setting"]:
        out["setting"] = "unknown"
    if out["people"] not in VOCAB["people"]:
        out["people"] = "none"
    if out["shot"] not in VOCAB["shot"]:
        out["shot"] = "detail"
    return out


# --- tagging ----------------------------------------------------------------

def tag_batch(items: list[dict], model: str, timeout: int, log=print) -> dict[str, dict]:
    """Tags one batch, halving it when the model returns the wrong shape."""
    try:
        rows, usage, kept = run_batch(items, model, timeout)
        kept_keys = {it["key"] for it in kept}
        for it in items:
            if it["key"] not in kept_keys:
                log(f"    SKIP {it['key']}: image download failed")
        return {it["key"]: clean_row(row) for it, row in zip(kept, rows)}, usage
    except (ValueError, RuntimeError, subprocess.TimeoutExpired) as e:
        if len(items) == 1:
            log(f"    FAIL {items[0]['key']}: {str(e)[:160]}")
            return {}, {}
        mid = len(items) // 2
        log(f"    split {len(items)} -> {mid}+{len(items) - mid} ({str(e)[:80]})")
        left, u1 = tag_batch(items[:mid], model, timeout, log)
        right, u2 = tag_batch(items[mid:], model, timeout, log)
        left.update(right)
        return left, {k: u1.get(k, 0) + u2.get(k, 0) for k in ("input", "output", "reasoning")}


def main():
    ap = argparse.ArgumentParser(description="Tag catalogue images with scene facets")
    ap.add_argument("what", choices=["reference", "skins", "all"], help="which catalogue to tag")
    ap.add_argument("--game", action="append", choices=sorted(DATA_FILES), help="skins: limit to these games")
    ap.add_argument("--limit", type=int, default=0, help="tag at most N new images (0 = all)")
    ap.add_argument("--batch", type=int, default=24, help="images per agent call")
    ap.add_argument("--workers", type=int, default=3, help="agent calls in flight")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--timeout", type=int, default=180, help="seconds per agent call")
    ap.add_argument("--force", action="store_true", help="re-tag cached keys")
    ap.add_argument("--dry", action="store_true", help="tag and print, write nothing to the catalogues")
    ap.add_argument("--aggregate-only", action="store_true", help="rebuild data/tags.json from the cache, no tagging")
    ap.add_argument("--sample", action="store_true", help="random spread instead of catalogue order")
    args = ap.parse_args()

    items: list[dict] = []
    if args.what in ("reference", "all"):
        items += reference_items()
    if args.what in ("skins", "all"):
        items += skin_items(args.game or sorted(DATA_FILES))

    os.makedirs(CACHE_DIR, exist_ok=True)
    if args.aggregate_only:
        aggregate(items, dry=False)
        return
    todo = [it for it in items if args.force or not os.path.exists(os.path.join(CACHE_DIR, cache_name(it["key"]) + ".json"))]
    if args.sample:
        random.Random(11).shuffle(todo)
    if args.limit:
        todo = todo[: args.limit]
    print(f"{len(items)} images in scope, {len(todo)} need tags ({args.batch}/call, {args.workers} workers)")

    batches = [todo[i : i + args.batch] for i in range(0, len(todo), args.batch)]
    done = {"images": 0, "input": 0, "output": 0}
    t0 = time.time()

    def work(batch):
        result, usage = tag_batch(batch, args.model, args.timeout)
        for key, row in result.items():
            with open(os.path.join(CACHE_DIR, cache_name(key) + ".json"), "w", encoding="utf-8") as f:
                json.dump({"key": key, **row}, f, ensure_ascii=False)
        return result, usage

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(work, b): b for b in batches}
        for fut in concurrent.futures.as_completed(futures):
            result, usage = fut.result()
            done["images"] += len(result)
            done["input"] += usage.get("input", 0)
            done["output"] += usage.get("output", 0)
            mins = (time.time() - t0) / 60
            rate = done["images"] / mins if mins else 0
            left = len(todo) - done["images"]
            eta = left / rate if rate else 0
            print(
                f"  {done['images']}/{len(todo)} images  {rate:.1f}/min  "
                f"eta {eta:.0f}min  in {done['input'] / 1e6:.1f}M out {done['output'] / 1e6:.2f}M tokens"
            )
            if args.dry:
                for key, row in list(result.items())[:3]:
                    print("   ", key, json.dumps(row, ensure_ascii=False))

    aggregate(items, args.dry)


def aggregate(items: list[dict], dry: bool) -> None:
    """Collects the per-key cache files into data/tags.json."""
    tags = {}
    for it in items:
        path = os.path.join(CACHE_DIR, cache_name(it["key"]) + ".json")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            row = json.load(f)
        tags[it["key"]] = {k: v for k, v in row.items() if k != "key"}
    if dry:
        print(f"dry run: {len(tags)} tagged in cache, data/tags.json untouched")
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    payload = {"gen": time.strftime("%Y-%m-%d"), "model": DEFAULT_MODEL, "items": tags}
    with open(TAGS_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {TAGS_PATH}: {len(tags)} tagged images")


if __name__ == "__main__":
    main()
