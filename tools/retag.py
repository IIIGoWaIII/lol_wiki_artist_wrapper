#!/usr/bin/env python3
"""Re-apply the filter tags to the existing catalogues, without touching art.

Vibes in wiki_tags.py are hand-curated, so tuning them should not cost a full
image rebuild. This rewrites only each record's ``tags`` and the catalogue's
``meta.tagGroups``: same output as build_data.py for those fields, seconds
instead of minutes.

Usage: python tools/retag.py [game ...]     (default: all three)
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import build_data
import wiki_tags

build_data.DATA_DIR = os.path.join(ROOT, build_data.DATA_DIR)


def main():
    keys = sys.argv[1:] or build_data.GAME_ORDER
    tags = wiki_tags.TagSource(build_data.WIKI)
    for key in keys:
        game = build_data.get_game(key)
        path = os.path.join(build_data.DATA_DIR, game.out)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        owners = sorted({rec["ch"] for rec in data["skins"]})
        tags.ensure(owners)
        for rec in data["skins"]:
            rec["tags"] = tags.for_skin(rec["ch"], rec.get("set"))
        data["meta"]["tagGroups"] = [list(group) for group in wiki_tags.GROUPS]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        print(f"retagged {path}: {len(data['skins'])} entries")
    wiki_tags.report_unmapped()


if __name__ == "__main__":
    main()
