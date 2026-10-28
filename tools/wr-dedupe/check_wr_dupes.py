"""Check WR skins whose art visually duplicates a LoL tab entry.

Feedback loop for the duplicate-skins bug: loads both built data files, and for
every WR skin computes the dHash distance to every LoL skin of the same
champion. Red = WR skins within visual-duplicate distance of a LoL entry.
"""
import json
import sys

sys.path.insert(0, ".")
import build_data as bd


def dist(a_url, b_url, cache):
    h1 = bd.fetch_thumb_hash(a_url, cache)
    h2 = bd.fetch_thumb_hash(b_url, cache)
    if h1 is None or h2 is None:
        return None
    return bd.hamming(h1, h2)


def main():
    lol = json.load(open("data/skins.json", encoding="utf-8"))
    wr = json.load(open("data/skins-wr.json", encoding="utf-8"))
    only = set(sys.argv[1:])  # optional champion filter

    by_champ = {}
    for s in lol["skins"]:
        by_champ.setdefault(s["ch"], []).append(s)

    cache = {}
    hits = []
    for s in wr["skins"]:
        if s["img"] is None or (only and s["ch"] not in only):
            continue
        best = (None, None, None)
        for ls in by_champ.get(s["ch"], []):
            if ls["img"] is None:
                continue
            d = dist(s["img"], ls["img"], cache)
            if d is not None and (best[0] is None or d < best[0]):
                best = (d, ls["s"], ls["img"])
        if best[0] is not None and best[0] <= 20:
            hits.append((best[0], s["ch"], s["s"], s["img"], best[1], best[2]))

    hits.sort()
    print(f"WR skins within distance 20 of a same-champion LoL skin: {len(hits)}")
    for d, ch, sk, wrimg, lsk, lolimg in hits:
        print(f"  d={d:2d}  {ch} - {sk}")
        print(f"        wr: {wrimg}")
        print(f"        lol({lsk}): {lolimg}")

    # The user's reported duplicates must be gone from the WR tab entirely;
    # these three pairs are the red signal when they reappear.
    reported = {("Hwei", "Original"), ("Hwei", "Winterblessed"), ("Kayn", "Odyssey")}
    present = {(s["ch"], s["s"]) for s in wr["skins"]}
    print("\nreported pairs still in the WR tab:", sorted(reported & present) or "none")


if __name__ == "__main__":
    main()
