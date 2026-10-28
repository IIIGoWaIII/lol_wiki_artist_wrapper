"""120px dHash measurement: WR art vs the exact LoL files the hybrid dedupe
compares (canonical + HD index recs), using build_data's own hash pipeline.

Complements data/wr_dupe_analysis.json (240px blurred correlations). Writes
data/wr_dupe_analysis120.json and prints per-threshold impact.
"""
import json
import sys
import time

sys.path.insert(0, ".")
import build_data as bd

OUT = "data/wr_dupe_analysis120.json"


def main():
    rows = json.load(open("data/wr_dupe_analysis.json", encoding="utf-8"))
    wr_cat = json.load(open("data/skins-wr.json", encoding="utf-8"))
    kept = {(s["ch"], s["s"]) for s in wr_cat["skins"]}

    todo = [r for r in rows if r.get("lol_canon") or r.get("lol_hd")]
    cache: dict = {}
    out = []
    t0 = time.time()
    for n, r in enumerate(todo):
        h = bd.fetch_thumb_hash(r["wr"], cache)
        row = {"ch": r["ch"], "s": r["s"], "kept": (r["ch"], r["s"]) in kept}
        for name, url in (("canon", r.get("lol_canon")), ("hd", r.get("lol_hd"))):
            if not url or h is None:
                row[f"d_{name}"] = None
                continue
            b = bd.fetch_thumb_hash(url, cache)
            row[f"d_{name}"] = None if b is None else bd.hamming(h, b)
        mins = [v for v in (row["d_canon"], row["d_hd"]) if v is not None]
        row["min"] = min(mins) if mins else None
        row["r_hd"] = r.get("r_hd")
        out.append(row)
        if (n + 1) % 25 == 0 or n == 0:
            print(f"{n + 1}/{len(todo)} ({time.time() - t0:.0f}s)", flush=True)

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"done: {len(out)} rows in {time.time() - t0:.0f}s -> {OUT}", flush=True)

    have = [r for r in out if r["min"] is not None]
    kept_have = [r for r in have if r["kept"]]
    print(f"\ncomparable pairs: {len(have)} ({len(kept_have)} currently kept)")
    for t in (10, 14, 16, 18, 20, 22, 24):
        drop = [r for r in kept_have if r["min"] <= t]
        fp = [r for r in drop if (r.get("r_hd") or 0) < 0.65]
        gray = [r for r in drop if 0.65 <= (r.get("r_hd") or 0) < 0.70]
        print(
            f"  min<= {t}: drops {len(drop)}/295 | r_hd<0.65 {len(fp)} | 0.65-0.70 {len(gray)}"
        )
    print("\nreported pairs at 120px:")
    for r in out:
        if (r["ch"], r["s"]) in {("Hwei", "Original"), ("Hwei", "Winterblessed"), ("Kayn", "Odyssey"), ("Sett", "Obsidian Dragon")}:
            print(f"  {r['ch']} - {r['s']}: d_canon={r['d_canon']} d_hd={r['d_hd']} min={r['min']} kept={r['kept']}")


if __name__ == "__main__":
    main()
