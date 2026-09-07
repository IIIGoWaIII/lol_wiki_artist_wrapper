# LoL Splash Reference

Local reference-gallery wrapper for the [League of Legends Wiki](https://wiki.leagueoflegends.com/en-us/) splash arts, built for quickly pulling full-HD splash references into [PureRef](https://www.pureref.com/).

## Features

- Browse all **2130 skins / 173 champions** as a filterable gallery.
- Multi-select filter panels with inline search and **Select all / Clear**:
  - **Champions** — grid of 173 champion avatars (alphabetical).
  - **Themes** — grid of 225 theme-representative splashes.
  - **Artists** — 142 splash artists.
- Free-text search across champion, skin, theme and artist names.
- Sort by release date, champion or price.
- High-definition splashes (up to 6000x3500+) with resolution shown on every card and in the detail view.
- **Other versions** listed in the side panel for reworked/older splashes (e.g. pre-rework `_old`/`_Unused` art) — click one to load it into the main view.

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

Skins data is generated from the wiki's `Module:SkinData/data` Lua table (single request). Filenames are derived from skin keys and verified against the wiki API.

```powershell
python build_data.py        # rewrites data/skins.json
```

## Layout

```
build_data.py   fetch + parse + verify -> data/skins.json
server.py       static server (local browsing)
web/            index.html, style.css, app.js (no build step, vanilla JS)
data/skins.json generated catalog (2130 skins, 225 themes)
.github/        GitHub Actions workflow that deploys web/ + data/ to Pages
```

## Notes

- Splash file resolution: `Champion_<Skin>Skin.jpg` with spaces/colons/slashes stripped but other punctuation kept (e.g. `Kog'Maw Bee'MawSkin.jpg`, `Gragas Gragas,Esq.Skin.jpg`). The `_HD` variant (e.g. `Tahm_Kench_OriginalSkin_HD.jpg`) is preferred when the wiki has one.
- Variant/prestige skins reuse their base skin's art.
- Images are hot-linked from the wiki; HD originals are up to 6000px+ wide, grid thumbs are 1200px HD.