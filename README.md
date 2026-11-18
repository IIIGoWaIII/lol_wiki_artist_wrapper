# Splash Reference

A local gallery of League of Legends splash art, Wild Rift ports and Runeterra card art, plus a separate board of film stills and paintings for general visual reference. Filter a few thousand images down to the ones you want, open the full-resolution original, then send the set to PureRef.

The hosted copy lives at https://IIIGoWaIII.github.io/lol_wiki_artist_wrapper/ and deploys from `main`.

## Run it

```powershell
python server.py
python server.py --port 9000
```

Windows users can double-click `start_server.bat`. The server listens on `0.0.0.0` and prints its local, LAN and Tailscale addresses on startup. JSON is gzipped and ETagged, and `/data/` serves only the catalogue files, so build inputs such as `artwork_overrides.json` stay off the web.

The frontend is plain HTML, CSS and JavaScript in `web/` with no build step.

## The libraries

| Library | Contents |
| --- | --- |
| League of Legends | About 2,150 splashes across 173 champions, with reworked and unused art kept as alternate versions. |
| Wild Rift | About 1,090 cosmetics across 143 champions. Most are ports, some are redrawn, and for a few the Wild Rift file is the widest copy on the wiki. |
| Legends of Runeterra | 272 card arts across 122 champions. |
| Reference | About 29,700 film stills from 3,716 films and 3,700 paintings. |

Counts come from the last data refresh and move as the wiki changes. The browse header shows the real number once a library loads.

TFT sits out because its sets reuse League artwork. Everything else the wiki lists is kept, including entries with no uploaded image, which show a placeholder instead of disappearing.

## Using it

The home screen is a library chooser. Pick one and the browse view loads its catalogue, sorted newest first.

The filter drawer is built from what each catalogue declares, so its panels change with the library. Game libraries get Champions, Themes and Artists, then Vibes, Kind, Species, Gender, Region, Class and five scene groups from the vision pass. The reference board swaps those for Directors, Cinematographers, Production designers, Genres, Countries, Artists, Movements, Decades and the same scene groups.

Every panel has its own search box. Commas work, so `briar, lux` lists both champions. Select all and Clear act on the whole panel, and Only selected hides everything except your picks. Panels combine as AND and values within a panel as OR, so Kind: Monster with Vibes: Cute finds the cute monsters. Game libraries also get a release year filter at the bottom of the drawer.

The search box covers every printed field: champion, skin, theme, artist, director, place, mood and the generated caption. Every word has to match, so more words mean fewer results.

The champion strip along the top of a game library is quicker than opening the panel when you already know the champion you want.

Sort by newest or oldest release, or A to Z and Z to A by name. On the reference board, release means the film's year, and undated films stay last in both directions.

Some skins ship the same file. The SKT T1 and DRX team skins are single paintings shared by five entries each, so the gallery shows one tile marked "Shared by N skins" and lists every skin in the viewer. Only byte-identical files collapse. Different crops of one painting stay separate.

The Board is a save list. Click the bookmark on a tile or press `s` in the viewer, and the entry appears in the right-hand panel. It survives reloads in `localStorage`. Copy links dumps every saved image URL on its own line, ready for a PureRef import or a downloader.

The viewer shows a 1200px copy first and swaps in the original when it loads. Scroll to zoom up to 800% around the cursor, drag to pan, double-click to switch between fit and 1:1. The readout shows the current percentage, and the Details button collapses the metadata panel for more room.

Below the metadata, Other versions lists real repaints of the same skin, oldest first, each upgraded to the best resolution available. Click one to load it into the main view. Nearby steps through the current result set. Middle-click opens the original in a new tab.

Reference stills sit in justified rows, one contact sheet per film, with a header showing year, director and still count. Hover a tile for its film and caption. Tile size S, M or L also rescales these rows, and the choice is remembered between visits.

| Key | Action |
| --- | --- |
| `/` | Focus search |
| `b` | Toggle the board |
| `s` | Save the open image to the board |
| `i` | Show or hide viewer details |
| `Left` / `Right` | Previous or next image in the viewer |
| `Esc` | Close the viewer, drawer or board |
| `Tab` | Move through controls; the viewer traps focus |

Links carry state. `?game=wr&champ=Jinx&skin=Project` opens a skin, `?game=ref&r=film:Bullet_Train_01.jpg` opens a still, and filters travel as `?game=lol&f=vibe:Cute|kind:Monster&q=star&y=2021`. The viewer rewrites the URL as you step, so the address bar is always shareable.

## Building the skin catalogues

One wiki hosts all three games. `build_data.py` fetches each game's Lua module, parses it, finds art through the `allimages` index, pulls each canonical file's revision history, and writes one JSON catalogue per game.

| Game | Source modules | Output |
| --- | --- | --- |
| League of Legends | `Module:SkinData/data` | `data/skins.json` |
| Wild Rift | `Module:SkinDataWR/data` | `data/skins-wr.json` |
| Legends of Runeterra | `Module:LoRCosmetics/skins` and `Module:LoRData/data` | `data/skins-lor.json` |

Requires Python and Pillow.

```powershell
python build_data.py              # all three games
python build_data.py wr           # just Wild Rift (also: lol, lor)
```

The build uses dHash to collapse small iterations of the same painting. Distinct repaints survive, and each is upgraded to its highest-resolution copy. Every catalogue carries its native aspect ratio, so Wild Rift and Runeterra art is not cropped to League's 1215x717.

dHash values are cached in `.cache/hashes.json`, keyed by image URL, so a rebuild only hashes art it has not seen. Delete the file to force a full recompute. A catalogue's `meta.gen` date only moves when its content changes, which keeps the daily CI commit quiet when the wiki has not moved.

`python build_dupes.py` writes `data/dupes.json`, the map of byte-identical splashes. It downloads each canonical thumb once, caches its sha1 in `.cache/thumb-sha1.json`, and groups files that hash the same. Groups larger than `MAX_GROUP` are the wiki's fallback image for retired files, so they are ignored.

Optional per-skin overrides live in `data/artwork_overrides.json`, keyed by canonical file base such as `"Xin_Zhao_OriginalSkin"`. The value is either a list of dates to keep or `{"keep": [...]}`, which is how you force a revision when the hash matcher picks the wrong one.

### Automatic refreshes

Three GitHub Actions workflows keep the site current:

- `update-data.yml` runs daily at 06:00 UTC, rebuilds the three skin catalogues and the shared-splash map, and commits only if `data/` changed.
- `update-reference.yml` runs weekly on Monday at 07:00 UTC, recrawls the reference libraries with `--refresh`, and commits `reference.json` if it changed.
- `pages.yml` assembles `web/` and `data/` into the Pages site on every push to `main`.

## Reference board

`python build_reference.py` builds `data/reference.json` from two open libraries.

| Library | Source | What it gives |
| --- | --- | --- |
| Cinematic | [film-grab.com](https://film-grab.com) WordPress REST API | Film stills with director, director of photography, production designer, genre, country, year and aspect ratio. |
| Classic Art | [imaginemore.art](https://imaginemore.art) `/api/assets` | Paintings with artist, year and movement. |

film-grab lists around 3,700 films with full still galleries. Keeping every frame would be half a million files, so the build takes an even spread through each film, 8 by default.

Imagine More's Cinematic, Game Art, Animated and Music libraries stop at a 150-item preview without a subscription. Classic Art works without an account up to roughly 3,500 images, which is why the art half is the smaller one.

```powershell
python build_reference.py                 # both libraries
python build_reference.py --only film     # just the cinematic half
python build_reference.py --stills 12     # more frames per film
python build_reference.py --films 800     # cap the crawl
python build_reference.py --refresh       # ignore the response cache
```

API responses are cached in `.cache/reference/`, so a run that hits a rate limit resumes instead of starting over.

## Tags

The wiki does not tag splash art by subject. A file is categorised by champion, skin line, release season and copyright, so there is no cute, female or monster category to filter on. The gallery builds those groups itself from champion lore and a curated skin-line map, and stores them per skin in `tags`.

| Group | Where it comes from | Values |
| --- | --- | --- |
| `kind` | Coarse grouping of `species` | Human, Humanoid, Yordle, Beast, Monster, Spirit, Construct |
| `species` | `species` field on the champion lore page, `Universe:<Champion>` | Human, Yordle, Voidborn, Darkin, Demon, Aspect Host, ... |
| `gender` | The lore page's `pronoun` field | Male, Female, Other |
| `region` | The lore page's `region` field | Ionia, Noxus, Zaun, Demacia, ... |
| `class` | `Module:ChampionData/data` | Marksman, Mage, Fighter, Tank, Assassin, Support |
| `vibe` | Curated skin-line map, `VIBES` in `wiki_tags.py` | Cute, Anime, Dark, Sci-Fi, Fantasy, Oriental, Western, Summer, Holiday, Modern, Music, Esports |

Species, gender, region and class are champion-level, so every skin of a champion inherits them. The lore pages come from `{{Champion bio}}` templates, fetched in batches of 50 titles through the wiki API.

Vibes are editorial, not wiki data. `VIBES` maps each skin line to a look, with `CHAMP_VIBES` as the fallback for Originals and art that predates skin lines. Any skin line missing from `VIBES` is printed during the build, so the gap shows up instead of the skin quietly losing its tags.

Scene facets come from a vision pass over the images themselves. `tag_images.py` sends batches to the local `opencode` CLI and asks for a closed vocabulary of `place`, `setting`, `light`, `weather`, `people`, `shot` and `mood`, plus a one-line caption. The closed list matters: free-form keywords split into "railway station", "station platform" and "train platform", and the filters stop agreeing with each other.

`tagmerge.py` flattens the raw facets into the five sidebar groups. Place becomes Scenes, light and weather become Light & weather, people and shot become Framing, and mood stays Mood. The raw facets and caption stay on each record for the detail view, and the caption is searchable.

```powershell
python tag_images.py reference            # every reference image
python tag_images.py skins --game lol     # one game's splashes
python tag_images.py reference --limit 40 --dry   # pilot
python tag_images.py all --aggregate-only  # rebuild tags.json from cache
python tagmerge.py                        # merge tags.json into the catalogues
```

Each image's tags are cached in `.cache/tags/<key>.json`, so an interrupted run resumes. `run_all.sh` runs the reference pass, the skins pass, the aggregate and the merge in one job. The catalogue builds call `tagmerge` too, so a rebuild re-applies `tags.json` without another vision pass.

CI has no agent, so the daily and weekly refreshes only re-apply the tags that are already committed. After a large catalogue change, run `tag_images.py` locally and commit the updated `tags.json`.

## Why Wild Rift keeps its own copies

669 of the 1,091 Wild Rift entries share a champion and skin name with a League skin. All of them stay.

The WR file is a separate upload with its own crop and colour grade, and for 41 pairs it is the wider copy. Nocturne Original is 10,000px in Wild Rift against 6,000 in League. Talon Dragonblade is 10,000 against 4,800. Jhin PROJECT is 7,000 against a 1,215px League file. Dropping the ports would lose the best version of those paintings.

An earlier build did drop them by comparing images with a blurred-correlation threshold of 0.70. Same-painting pairs scored as low as 0.71 and different-painting pairs as high as 0.70, so the bands overlapped and there was no clean cut. The threshold was a guess, and it removed WR art the League catalogue does not contain.

## Repository layout

| Path | Purpose |
| --- | --- |
| `build_data.py` | Fetch, parse and verify the three skin catalogues. |
| `build_dupes.py` | Find byte-identical splashes. |
| `build_reference.py` | Crawl film-grab and Imagine More into `reference.json`. |
| `wiki_tags.py` | Champion lore and skin-line vibes. |
| `tag_images.py` | Vision pass over reference images and splashes. |
| `tagmerge.py` | Merge the vision tags into the catalogues. |
| `server.py` | Local static server with gzip and ETag. |
| `run_all.sh` | Full tagging run: reference, skins, aggregate, merge. |
| `web/` | `index.html`, `style.css`, `app.js`. |
| `data/` | Generated catalogues, the reference board and the merged tags. |
| `tools/` | One-off wiki analysis scripts, not part of the build. |
| `.github/` | Daily skin refresh, weekly reference refresh, Pages deploy. |

## Notes on wiki files

- League splashes are named `Champion_<Skin>Skin.jpg` with spaces, colons and slashes stripped but other punctuation kept, so Kog'Maw Bee'Maw is `Kog'Maw_Bee'MawSkin.jpg` and Gragas, Esq. is `Gragas_Gragas,Esq.Skin.jpg`. The `_HD` variant is preferred when it exists. Newer HD uploads are `.png`, so both extensions are probed.
- Wild Rift uses the same scheme with a `_WR` suffix. Early champions were uploaded as `.png` and later ones as `.jpg`, so both are probed.
- Runeterra files are named by card code, for example `01DE012_Rugged-HD-full.jpg`. A card's files also cover its star levels `T1` through `T8` and its other cosmetics, so only the `-alt` family counts as alternate art of the same cosmetic.
- Variant and prestige skins reuse the base skin's art.
- Images are hot-linked, never mirrored. Splash thumbnails in the grid and panels request the 420px variant, the viewer starts at 1200px and swaps in the original, and HD originals reach 10,000px wide. The galleries need network access.
- Reference stills are hot-linked from film-grab and paintings from `inspiration.imaginemore.art`, so the lightbox uses the full-size image there instead of a second copy.
- Skins with no artwork on the wiki stay in the catalogue with a placeholder. League currently has none and Wild Rift has one. `meta.missingImage` in each catalogue holds the count.
