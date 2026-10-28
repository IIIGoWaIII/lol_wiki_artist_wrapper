"""Distribution run: cross-game correlation metric over all same-skin WR pairs.

For every WR skin with a LoL twin, computes:
- best Pearson correlation of the WR art vs the LoL canonical current revision
- best Pearson correlation vs the LoL HD file (what the LoL tab displays)
- the raw dHash distance the build currently uses (vs canonical)
Saves results to data/wr_dupe_analysis.json for threshold picking.
"""
import io
import json
import sys
import time

import numpy as np
from PIL import Image, ImageFilter

sys.path.insert(0, ".")
import build_data as bd

SCALES = (0.86, 0.90, 0.92, 0.94, 0.96, 0.98, 1.0, 1.02, 1.04, 1.06, 1.08, 1.10, 1.14)
STEP = 2
RANGE_FRAC = 0.14

THUMBS = {}  # url -> PIL image


def thumb_img(url):
    img = THUMBS.get(url)
    if img is None:
        data = bd.http_get(bd.thumb_url(url, 240))
        img = Image.open(io.BytesIO(data)).convert("L").filter(ImageFilter.GaussianBlur(2))
        THUMBS[url] = img
    return img


def _corr(a, b):
    a = a.ravel()
    b = b.ravel()
    a = a - a.mean()
    b = b - b.mean()
    denom = np.sqrt((a * a).sum() * (b * b).sum())
    if denom == 0:
        return 0.0
    return float((a * b).sum() / denom)


def best_corr(wr, lol):
    arr_w = np.asarray(wr, dtype=np.float32)
    best = -1.0
    wh, ww = arr_w.shape
    for f in SCALES:
        h = round(wh * f)
        ls = lol.resize((max(8, round(lol.size[0] * h / lol.size[1])), h), Image.Resampling.LANCZOS)
        arr_l = np.asarray(ls, dtype=np.float32)
        lh, lw = arr_l.shape
        ys = range(0, max(1, abs(wh - lh) + int(wh * RANGE_FRAC)), STEP)
        dys = (0,) if wh == lh else [v for y in ys for v in (y, -y)]
        span_x = abs(ww - lw) // 2 + int(ww * RANGE_FRAC)
        xs = range(0, span_x + 1, STEP)
        dxs = (0,) if ww == lw else [v for x in xs for v in (x, -x)]
        for dy in dys:
            oy = (wh - lh) // 2 + dy
            if lh <= wh:
                if oy < 0 or oy + lh > wh:
                    continue
                wa = arr_w[oy : oy + lh]
                la = arr_l
            else:
                cy = (-oy) if oy < 0 else 0
                if cy + wh > lh:
                    continue
                wa = arr_w
                la = arr_l[cy : cy + wh]
            for dx in dxs:
                ox = (ww - lw) // 2 + dx
                if lw <= ww:
                    if ox < 0 or ox + lw > ww:
                        continue
                    c = _corr(wa[:, ox : ox + lw], la)
                else:
                    cx = (-ox) if ox < 0 else 0
                    if cx + ww > lw:
                        continue
                    c = _corr(wa, la[:, cx : cx + ww])
                if c > best:
                    best = c
    return best


def dhash_of(img):
    px = img.resize((9, 8), Image.Resampling.LANCZOS).load()
    bits = []
    for y in range(8):
        for x in range(8):
            bits.append("1" if px[x, y] >= px[x + 1, y] else "0")
    return int("".join(bits), 2)


def main():
    lol = json.load(open("data/skins.json", encoding="utf-8"))
    wr = json.load(open("data/skins-wr.json", encoding="utf-8"))

    lol_skins_by_base = {}
    for s in lol["skins"]:
        lol_skins_by_base[f"{bd.champ_prefix(s['ch'])}_{bd.skin_asset(s['s'])}Skin"] = s

    indexes = {}  # champion prefix -> {filename: rec}
    out = []
    t0 = time.time()
    todo = [s for s in wr["skins"] if s["img"]]
    for n, s in enumerate(todo):
        prefix = bd.champ_prefix(s["ch"])
        if prefix not in indexes:
            base = f"{prefix}_{bd.skin_asset(s['s'])}Skin"
            lol_skin = lol_skins_by_base.get(base)
            if not lol_skin:
                continue
        if prefix not in indexes:
            indexes[prefix] = bd.discover_prefix(prefix)
        files = indexes[prefix]
        base = f"{prefix}_{bd.skin_asset(s['s'])}Skin"
        recs = {}
        for fn in (f"{base}.jpg", f"{base}_HD.jpg"):
            if fn in files:
                recs[fn] = files[fn]
        wr_img = thumb_img(s["img"])
        wr_h = dhash_of(wr_img)
        row = {"ch": s["ch"], "s": s["s"], "wr": s["img"]}
        for name, fn in (("canon", f"{base}.jpg"), ("hd", f"{base}_HD.jpg")):
            rec = recs.get(fn)
            if not rec:
                row[f"r_{name}"] = None
                row[f"d_{name}"] = None
                continue
            img = thumb_img(rec["url"])
            row[f"r_{name}"] = round(best_corr(wr_img, img), 4)
            row[f"d_{name}"] = bd.hamming(wr_h, dhash_of(img))
            row[f"lol_{name}"] = rec["url"]
        out.append(row)
        if (n + 1) % 25 == 0 or n == 0:
            print(f"{n + 1}/{len(todo)} ({time.time() - t0:.0f}s)", flush=True)

    with open("data/wr_dupe_analysis.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"done: {len(out)} pairs in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
