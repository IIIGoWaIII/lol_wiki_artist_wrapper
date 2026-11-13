# Splash Reference

Local reference-gallery wrapper for the [League of Legends Wiki](https://wiki.leagueoflegends.com/en-us/) splash arts, built for quickly pulling full-HD splash references into [PureRef](https://www.pureref.com/).

Covers three games, one tab each: **League of Legends**, **Wild Rift** and **Legends of Runeterra**, plus a fourth **Reference** tab with a general visual reference board for non-League study. TFT is excluded because it reuses League artwork, and 2XKO has no cosmetics on the wiki yet.

## Features

- Browse each game's splash arts as a filterable gallery.
- **Reference** tab: a searchable board of ~32k film stills and paintings, styled like [imaginemore.art](https://imaginemore.art): justified rows, captions on hover, one search box, and filters for director, cinematographer, production designer, genre, country, artist, movement and decade.
- Multi-select filter panels with inline search and **Select all / Clear**:
  - **Champions** — grid of champion avatars (alphabetical).
  - **Themes** — grid of theme-representative splashes.
  - **Artists** — splash artists.
  - **Vibes, Kind, Species, Gender, Region, Class** — see [Tags](#tags) below. Panels combine as AND, values inside a panel as OR, so *Kind: Monster* + *Vibes: Cute* finds the cute monsters.
- Sort by release date or champion, newest or oldest first.
- High-definition splashes (up to 6000x3500+) with resolution shown on every card and in the detail view.
- **Other versions** listed in the side panel for reworked/older splashes (e.g. pre-rework `_old`/`_Unused` art) — click one to load it into the main view.
- Shareable links: `?game=wr&champ=Jinx&skin=Project` opens that skin directly, and `?game=ref&r=film:Discrete_Charm_01.jpg` opens a frame on the reference board. The lightbox also keeps the URL in sync as you browse.
- Keyboard: Tab to a card, Enter or Space opens it, arrow keys step through the gallery, Esc closes.
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

Each catalogue is generated from the wiki's Lua tables, the image index (`allimages`), each file's full revision history, and the champion lore pages behind the [tags](#tags). Distinct repaints are detected by perceptual hash (dHash): small iterations of the same artwork are collapsed, so the **other versions** panel shows one copy per real repaint, oldest first, each upgraded to its best available resolution.

Requires Python with Pillow:

```powershell
python build_data.py              # all three games
python build_data.py wr           # just Wild Rift (also: lol, lor)
```

Computed dHashes are kept in `.cache/hashes.json`, keyed by image URL, so a rebuild only hashes art it has not seen. Delete the file to force a full recompute. The CI workflow caches the same directory between daily runs. A catalogue's `meta.gen` date only moves when its content changes, so the daily job commits only when the wiki actually changed.

Outputs one file per game, each with its own `meta.aspect` used by the frontend:

| Game | Wiki source | Output |
| --- | --- | --- |
| League of Legends | `Module:SkinData/data` | `data/skins.json` |
| Wild Rift | `Module:SkinDataWR/data` | `data/skins-wr.json` |
| Legends of Runeterra | `Module:LoRCosmetics/skins` + `Module:LoRData/data` | `data/skins-lor.json` |

### Reference board

`python build_reference.py` builds `data/reference.json` from two open libraries:

| Library | Source | What it gives |
| --- | --- | --- |
| Cinematic | [film-grab.com](https://film-grab.com) WordPress REST API | film stills with director, director of photography, production designer, genre, country, year and aspect ratio |
| Classic Art | [imaginemore.art](https://imaginemore.art) `/api/assets` | paintings with artist, year and movement |

Imagine More's Cinematic, Game Art, Animated and Music libraries are paywalled past a 150-item preview, and their anonymous Classic Art window stops at roughly 3,500 unique images, so that is the ceiling for the art half. film-grab lists about 2,400 films with still galleries; `--stills` decides how many frames are kept per film (an even spread through the film, default 8). Every API response is cached in `.cache/reference/`, so a run that trips film-grab's rate limit resumes instead of starting over; `--refresh` ignores the cache.

```powershell
python build_reference.py                 # both libraries
python build_reference.py --only film     # just the cinematic half
python build_reference.py --stills 12     # more frames per film
```

### Scene tags

Search is substring matching over metadata, so `train station` only works if the
image is actually tagged as one. `tag_images.py` runs a vision pass over every
image and writes closed facets plus a one-line caption into `data/tags.json`:

| Facet | Values |
| --- | --- |
| `place` | train station, kitchen, throne room, battlefield, procession, … |
| `setting` | interior, exterior, both |
| `light` | daylight, dusk, night, neon, candlelit, warm lamp, low key, … |
| `weather` | rain, snow, fog, smoke, haze, … |
| `people` | none, single, few, crowd |
| `shot` | close-up, portrait, full body, wide, landscape, detail |
| `mood` | calm, tense, melancholic, ominous, awe, … |

Facets are a closed vocabulary on purpose: free-form keywords fragment into
"railway station" / "station platform" / "train platform" and make filtering
worse. The sidebar turns them into five panels — Scenes, Setting, Light &
weather, Framing, Mood — and the search box indexes the captions too.

```powershell
python tag_images.py reference            # every reference image
python tag_images.py skins --game lol     # one game's splashes
python tag_images.py reference --limit 40 --dry   # pilot
python tag_images.py reference --aggregate-only   # rebuild tags.json from cache
python tagmerge.py                        # merge tags.json into the catalogues
```

The vision engine is the local `opencode` CLI, not an API key: it reads the
attached images through the same OpenCode subscription the coding session uses.
Each image is cached in `.cache/tags/<key>.json`, so a run resumes where it
stopped and the weekly refresh only tags new files. `build_reference.py` and
`build_data.py` re-apply `data/tags.json` on every rebuild, so a fresh catalogue
never loses its tags.


### Wild Rift and League artwork overlap

Wild Rift ports many League skins, so 667 of the 1073 WR cosmetics share a champion and skin name with a League skin. All of them are kept, for two reasons measured against the wiki:

- The files are never identical. No WR/LoL pair shares a sha1, so each port is its own upload and usually a different crop or colour grade. A WR splash is a separate piece of work rather than a copy of the League one.
- For 18 skins the WR file is the widest image that exists. Nocturne Original is 10000px in Wild Rift against 6000px in League, Riven Valiant Sword 8000 against 4000, Jhin PROJECT 7000 against a 1215px League file. Dropping those loses the only high-resolution copy.

A previous build dropped them by comparing images, using a blurred-correlation threshold of 0.70. Measured over the pairs, the same-painting scores reached down to 0.71 and the different-painting scores reached up to 0.70, so the bands overlapped with no clean cut in between and the threshold was a judgment call. It also hid roughly 100 WR splashes that exist nowhere else, among them the 15 champions whose base artwork Wild Rift re-shot for itself: Jax, Leona, Mel, Nautilus, Nidalee, Norra, Rek'Sai, Shyvana, Soraka, Sylas, Teemo, Thresh, Viego, Xin Zhao and Yunara.

Optional per-skin override in `data/artwork_overrides.json` (keyed by canonical file base, e.g. `"Xin_Zhao_OriginalSkin"`) forces which revisions to keep by date, either a plain list or `{"keep": [...]}`.

## Tags

The wiki does not tag splash art by subject: a splash file is only categorised by champion, skin line, release season and copyright, and there is no "cute", "female" or "monster" category anywhere on it (`Category:Monsters` is jungle camps). The gallery therefore builds its own filter groups, stored per skin in `tags`:

| Group | Where it comes from | Values |
| --- | --- | --- |
| `kind` | coarse grouping of `species` | Human, Humanoid, Yordle, Beast, Monster, Spirit, Construct |
| `species` | `species` field of the champion's lore page, `Universe:<Champion>` (`{{Champion bio}}`) | Human, Yordle, Voidborn, Darkin, Demon, Aspect Host, ... |
| `gender` | the lore page's `pronoun` field | Male, Female, Other |
| `region` | the lore page's `region` field | Ionia, Noxus, Zaun, Demacia, ... |
| `class` | `Module:ChampionData/data` | Marksman, Mage, Fighter, Tank, Assassin, Support |
| `vibe` | curated map of skin lines (`VIBES` in `wiki_tags.py`) | Cute, Anime, Dark, Sci-Fi, Fantasy, Oriental, Western, Summer, Holiday, Modern, Music, Esports |

Species, gender, region and class are champion-level, so every skin of a champion inherits them. Vibes are skin-line-level, with a small per-champion fallback (`CHAMP_VIBES`) for Originals and pre-skin-line art. Skins are never silently left out: the build prints any skin line missing from `VIBES`, which is the list to extend when the wiki adds a line.

The bio pages are fetched in batches of 50 titles through the API (four requests for League), and the lore overrides live in `OVERRIDES` next to the tables.

## Layout

```
build_data.py   fetch + parse + verify -> data/skins{,-wr,-lor}.json
build_reference.py  crawl film-grab + Imagine More -> data/reference.json
wiki_tags.py    champion lore + skin-line vibes -> the filter tags
server.py       static server (local browsing), gzip + ETag
web/            index.html, style.css, app.js (no build step, vanilla JS)
data/           generated catalogues, one JSON per game, plus the reference board
tools/          one-off wiki analysis scripts (not part of the build)
.github/        CI: daily skin refresh, weekly reference refresh, Pages deploy
```

## Notes

- League splash file resolution: `Champion_<Skin>Skin.jpg` with spaces/colons/slashes stripped but other punctuation kept (e.g. `Kog'Maw Bee'MawSkin.jpg`, `Gragas Gragas,Esq.Skin.jpg`). The `_HD` variant (e.g. `Tahm_Kench_OriginalSkin_HD.jpg`) is preferred when the wiki has one. Newer HD uploads are `.png` (`Briar_OriginalSkin_HD.png`), so both extensions are probed.
- Wild Rift uses the same scheme with a `_WR` suffix, but uploaded its first champions as `.png` and later switched to `.jpg`, so both extensions are probed.
- Runeterra files are named by card code (`01DE012_Rugged-HD-full.jpg`). A card's files also cover its star levels (`T1`-`T8`) and its other cosmetics, so only the `-alt` family is treated as alternate art of the same cosmetic.
- Variant/prestige skins reuse their base skin's art.
- Images are hot-linked from the wiki; HD originals are up to 6000px+ wide. Grid and sidebar thumbnails request the 420px variant, the lightbox requests 1200px.
- The reference board hot-links its stills and paintings the same way, from `film-grab.com` and `inspiration.imaginemore.art`. The film stills are 1920px JPEGs at roughly 85 KB, so the lightbox loads the grid image rather than a second copy.
- Skins with no artwork on the wiki (mostly unreleased `Upcoming` entries) are kept in the catalogue but show a placeholder. League currently has none; Wild Rift has a handful. Each catalogue's `meta.missingImage` holds the current count.
