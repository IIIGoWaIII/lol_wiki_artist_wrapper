# Splash Reference

Local reference-gallery wrapper for the [League of Legends Wiki](https://wiki.leagueoflegends.com/en-us/) splash arts, built for quickly pulling full-HD splash references into [PureRef](https://www.pureref.com/).

Covers three games, one tab each: **League of Legends**, **Wild Rift** and **Legends of Runeterra**. TFT is excluded because it reuses League artwork, and 2XKO has no cosmetics on the wiki yet.

## Features

- Browse each game's splash arts as a filterable gallery.
- Multi-select filter panels with inline search and **Select all / Clear**:
  - **Champions** — grid of champion avatars (alphabetical).
  - **Themes** — grid of theme-representative splashes.
  - **Artists** — splash artists.
- Free-text search across champion, skin, theme and artist names.
- Sort by release date, champion or price.
- High-definition splashes (up to 6000x3500+) with resolution shown on every card and in the detail view.
- **Other versions** listed in the side panel for reworked/older splashes (e.g. pre-rework `_old`/`_Unused` art) — click one to load it into the main view.
- Each game is cropped to its own native artwork ratio, so Wild Rift and Runeterra card art are not cut to League's 1215x717.

## Run

Public copy hosted on GitHub Pages (auto-deployed from `main`):

- https://IIIGoWaIII.github.io/lol_wiki_artist_wrapper/

Run locally:

```powershell
python server.py            # http://localhost:8000
python server.py --port 9000
```

The server also binds 0.0.0.0, so LAN devices can use `http://<your-ip>:8000`, and a Tailscale node at `http://<tailscale-ip>:8000` when present.

## Regenerate data

Each catalogue is generated from the wiki's Lua tables, the image index (`allimages`), and each file's full revision history. Distinct repaints are detected by perceptual hash (dHash): small iterations of the same artwork are collapsed, so the **other versions** panel shows one copy per real repaint, oldest first, each upgraded to its best available resolution.

Requires Python with Pillow:

```powershell
python build_data.py              # all three games
python build_data.py wr           # just Wild Rift (also: lol, lor)
```

Outputs one file per game, each with its own `meta.aspect` used by the frontend:

| Game | Wiki source | Output |
| --- | --- | --- |
| League of Legends | `Module:SkinData/data` | `data/skins.json` |
| Wild Rift | `Module:SkinDataWR/data` | `data/skins-wr.json` |
| Legends of Runeterra | `Module:LoRCosmetics/skins` + `Module:LoRData/data` | `data/skins-lor.json` |

### Wild Rift deduplication

Wild Rift ports many League skins unchanged, which would show the same painting in two tabs. A WR splash is hashed against its same-named League original's canonical file *and* its `_HD` file — the one the LoL tab actually displays, and often a different crop of the canonical — and dropped when the closer match is within a dHash distance of 20 (`CROSS_GAME_DUPLICATE`). Hashing against only the canonical let re-cropped twins survive: of the reported duplicates, Hwei Original sits at distance 21 from the canonical but 20 from the HD file. 20 is the measured minimum that separates the reported duplicates (Hwei Winterblessed 5, Kayn Odyssey 9) and it puts 47 pairs at 0-10 with none of them scoring like a distinct painting; above 10 the distances decay smoothly with no natural gap, so the cut past 10 is a judgment call — 13 of the dropped pairs score like distinct paintings on a blurred correlation, all same-named re-shoots such as per-game `Original` art. Champion lists and every WR-exclusive skin (no same-named League counterpart) are unaffected.

Optional per-skin override in `data/artwork_overrides.json` (keyed by canonical file base, e.g. `"Xin_Zhao_OriginalSkin"`) forces which revisions to keep by date — either a plain list or `{"keep": [...]}`.

## Layout

```
build_data.py   fetch + parse + verify -> data/skins{,-wr,-lor}.json
server.py       static server (local browsing)
web/            index.html, style.css, app.js (no build step, vanilla JS)
data/           generated catalogues, one JSON per game
.github/        GitHub Actions workflow that deploys web/ + data/ to Pages
```

## Notes

- League splash file resolution: `Champion_<Skin>Skin.jpg` with spaces/colons/slashes stripped but other punctuation kept (e.g. `Kog'Maw Bee'MawSkin.jpg`, `Gragas Gragas,Esq.Skin.jpg`). The `_HD` variant (e.g. `Tahm_Kench_OriginalSkin_HD.jpg`) is preferred when the wiki has one.
- Wild Rift uses the same scheme with a `_WR` suffix, but uploaded its first champions as `.png` and later switched to `.jpg`, so both extensions are probed.
- Runeterra files are named by card code (`01DE012_Rugged-HD-full.jpg`). A card's files also cover its star levels (`T1`-`T8`) and its other cosmetics, so only the `-alt` family is treated as alternate art of the same cosmetic.
- Variant/prestige skins reuse their base skin's art.
- Images are hot-linked from the wiki; HD originals are up to 6000px+ wide, grid thumbs are 1200px HD.
- Skins with no artwork on the wiki (mostly unreleased `Upcoming` entries) are kept in the catalogue but show a placeholder. League currently has none; Wild Rift has a handful. Each catalogue's `meta.missingImage` holds the current count.
