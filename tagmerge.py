#!/usr/bin/env python3
"""
Merges the scene tags produced by tag_images.py into the catalogues.

Kept separate so build_reference.py, build_data.py and `tag_images.py --merge`
all apply the same mapping: raw facets live in `sc` (for the detail view), the
sidebar groups are flattened into `tags` (for filtering).
"""

from __future__ import annotations

import json
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
TAGS_PATH = os.path.join(DATA_DIR, "tags.json")

# One panel per line of thinking, not per facet: light and weather belong
# together, people and shot describe the same thing (how much and how close).
GROUPS = [
    ["scene", "Scenes"],
    ["setting", "Setting"],
    ["atmosphere", "Light & weather"],
    ["framing", "Framing"],
    ["mood", "Mood"],
]


def load() -> dict:
    try:
        with open(TAGS_PATH, encoding="utf-8") as f:
            return json.load(f).get("items") or {}
    except (OSError, json.JSONDecodeError):
        return {}


def groups(tags: dict) -> dict[str, list[str]]:
    light = list(tags.get("light") or [])
    weather = list(tags.get("weather") or [])
    people = tags.get("people")
    shot = tags.get("shot")
    out = {
        "scene": list(tags.get("place") or []),
        "setting": [tags["setting"]] if tags.get("setting") not in (None, "unknown") else [],
        "atmosphere": light + weather,
        "framing": ([people] if people and people != "none" else []) + ([shot] if shot else []),
        "mood": list(tags.get("mood") or []),
    }
    return {k: v for k, v in out.items() if v}


def for_reference(item: dict, tag: dict) -> None:
    item["sc"] = {k: v for k, v in tag.items() if k != "caption"}
    if tag.get("caption"):
        item["cap"] = tag["caption"]


def for_skin(rec: dict, tag: dict) -> None:
    rec["sc"] = {k: v for k, v in tag.items() if k != "caption"}
    if tag.get("caption"):
        rec["cap"] = tag["caption"]
    rec.setdefault("tags", {}).update(groups(tag))


def merge_reference(path: str, tags: dict | None = None) -> int:
    tags = load() if tags is None else tags
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    n = 0
    for item in data.get("items", []):
        tag = tags.get(f"ref:{item['src']}:{item['id']}")
        if tag:
            for_reference(item, tag)
            n += 1
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    return n


def merge_skins(path: str, game: str, tags: dict | None = None) -> int:
    tags = load() if tags is None else tags
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    n = 0
    for rec in data.get("skins", []):
        tag = tags.get(f"skin:{game}:{rec['ch']}:{rec['s']}")
        if tag:
            for_skin(rec, tag)
            n += 1
    if n:
        meta = data.setdefault("meta", {})
        existing = [g[0] for g in meta.get("tagGroups") or []]
        for group in GROUPS:
            if group[0] not in existing:
                meta.setdefault("tagGroups", []).append(list(group))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    return n


def merge_all(games: dict[str, str]) -> None:
    tags = load()
    if not tags:
        print("no data/tags.json yet")
        return
    ref = os.path.join(DATA_DIR, "reference.json")
    if os.path.exists(ref):
        print(f"reference.json: {merge_reference(ref, tags)} tagged")
    for game, name in games.items():
        path = os.path.join(DATA_DIR, name)
        if os.path.exists(path):
            print(f"{name}: {merge_skins(path, game, tags)} tagged")


if __name__ == "__main__":
    merge_all({"lol": "skins.json", "wr": "skins-wr.json", "lor": "skins-lor.json"})
