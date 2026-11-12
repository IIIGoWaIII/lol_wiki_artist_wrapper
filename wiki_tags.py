"""Filter tags that the wiki does not ship.

Splash files on the wiki are only categorised by champion, skin line and release
season: there is no "cute", "female" or "monster" category anywhere. Those have
to be derived, from two places:

* **Champion lore.** ``Universe:<Champion>`` carries a ``{{Champion bio}}``
  template with ``species``, ``pronoun`` and ``region``, and the gameplay module
  ``Module:ChampionData/data`` carries the class. All of it is champion-level,
  so every skin of a champion inherits it.
* **Skin line.** ``VIBES`` below maps each skin line ("Coven", "Cafe Cuties",
  ...) to art-direction vibes. This is editorial, not wiki data, and is the
  place to tune the gallery's taste.

Champions whose lore page is thin or whose skin lines carry no theme fall back
to the ``CHAMP_VIBES`` baselines at the bottom.
"""

from __future__ import annotations

import re


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------

# (key, label) in sidebar order. build_data.py copies this into each catalogue's
# meta so the frontend does not have to know the tag vocabulary.
GROUPS = [
    ("vibe", "Vibes"),
    ("kind", "Kind"),
    ("species", "Species"),
    ("gender", "Gender"),
    ("region", "Region"),
    ("class", "Class"),
]

# LoR lists a cosmetic under the card's name, which is sometimes the champion
# plus the theme ("Spirit Blossom Ahri"). Map those back to the champion they
# borrow their lore from.
ALIASES = {
    "Lux: Illuminated": "Lux",
    "Spirit Blossom Ahri": "Ahri",
    "Spirit Blossom Evelynn": "Evelynn",
    "Spirit Blossom Master Yi": "Master Yi",
    "Spirit Blossom Teemo": "Teemo",
    "Spirit Blossom Yasuo": "Yasuo",
    "Nunu & Willump": "Nunu",
}

# Lore pages that omit the field or describe it in prose instead.
OVERRIDES = {
    "Aurora": {"gender": "Female"},
    "Jinx": {"gender": "Female"},
    "Nunu & Willump": {"gender": "Male", "species": ["Human", "Yeti"]},
    "Zyra": {"species": ["Plant"]},
    "Shaco": {"species": []},
    "Warwick": {"species": ["Chemical Beast"]},
    "Viktor": {"species": ["Evolved"]},
}

# Wiki species label -> the coarse kind an artist would sort by.
KINDS = {
    "Human": "Human",
    "Iceborn": "Human",
    "Vastayan": "Human",
    "Evolved": "Human",
    "Yordle": "Yordle",
    "Vesani": "Humanoid",
    "Oovi-Kat": "Humanoid",
    "Marai": "Humanoid",
    "Lhotlan": "Humanoid",
    "Shimon": "Humanoid",
    "Plant": "Monster",
    "Troll": "Monster",
    "Minotaur": "Monster",
    "Yeti": "Monster",
    "Sand-Troll": "Monster",
    "Drakalops": "Monster",
    "Baccai": "Monster",
    "Brackern": "Monster",
    "Plague Rat": "Monster",
    "Voidborn": "Monster",
    "Demon": "Monster",
    "Darkin": "Monster",
    "Xer'Sai": "Monster",
    "Chemical Beast": "Monster",
    "Kiilash": "Monster",
    "Cat": "Beast",
    "Dog": "Beast",
    "Dune Hound": "Beast",
    "Dragon": "Beast",
    "Terrestrial Dragon": "Beast",
    "Celestial Dragon": "Beast",
    "Bryni": "Spirit",
    "Fae Fawn": "Spirit",
    "Treant": "Spirit",
    "Spirit Tree": "Spirit",
    "Spirit God": "Spirit",
    "Celestial": "Spirit",
    "Aspect Host": "Spirit",
    "Ascended": "Spirit",
    "God-Warrior": "Spirit",
    "Wraith": "Spirit",
    "Revenant": "Spirit",
    "Golem": "Construct",
}

# Species labels that carry no information on their own, or repeat a neighbour.
SPECIES_ALIASES = {
    "Universe:Human": "Human",
    "Aspect Host Candidate": "Aspect Host",
    "Vastayan Ancestry": "Vastayan",
    "Reincarnated Spirit": "Spirit",
    "Blood Golem": "Golem",
    "Elemental Golem": "Golem",
    "Ooze Golem": "Golem",
    "Techmaturgical": "",
    "Petricite": "",
    "Olaf is an Iceborn": "",
    "Unknown": "",
}
DROP_SPECIES = {"", "Species", "Unknown"}


# ---------------------------------------------------------------------------
# Bio parsing
# ---------------------------------------------------------------------------

_STRUCK = re.compile(r"<s>.*?</s>", re.S | re.I)
_REF = re.compile(r"<ref[^>]*>.*?</ref>", re.S | re.I)
_REF_SELF = re.compile(r"<ref[^>]*/>", re.I)
_LINK = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
_FI = re.compile(r"\{\{fi\|([^}|]+)")
_PARAM = re.compile(r"\n\s*\|\s*([a-z_]+)\s*=\s*")


def _bio_param(text: str, name: str) -> str:
    """One top-level parameter of the page's {{Champion bio}} template."""
    start = text.find("{{Champion bio")
    if start < 0:
        return ""
    body = text[start:]
    marks = list(_PARAM.finditer(body))
    for i, m in enumerate(marks):
        if m.group(1) != name:
            continue
        end = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        value = body[m.end():end]
        return value.split("\n}}")[0].strip()
    return ""


def _strip_history(raw: str) -> str:
    text = _REF.sub("", _REF_SELF.sub("", raw))
    text = _STRUCK.sub("", text)
    # <s> spans the wiki writes without a closing tag on a couple of pages.
    return re.sub(r"<s>.*", "", text, flags=re.S | re.I)


def parse_species(raw: str) -> list[str]:
    text = _strip_history(raw)
    names = []
    for m in _LINK.finditer(text):
        label = (m.group(2) or m.group(1)).split(":")[-1].strip()
        if label:
            names.append(label)
    if not names:
        plain = re.sub(r"<[^>]+>", " ", text)
        plain = re.sub(r"\{\{[^}]*\}\}", " ", plain)
        plain = re.sub(r"\s+", " ", plain).strip(" *;,")
        if plain and plain.lower() not in {"unknown"}:
            names.append(plain)
    out = []
    for name in names:
        name = SPECIES_ALIASES.get(name, name)
        if name not in DROP_SPECIES and name not in out:
            out.append(name)
    return out


def parse_gender(raw: str) -> str:
    text = re.sub(r"\{\{tt\|([^|}]+)[^}]*\}\}", r"\1", raw or "")
    text = re.sub(r"<[^>]+>", " ", text)
    m = re.search(r"\b(He|She|They|It)\b", text, re.I)
    if not m:
        return ""
    return {"he": "Male", "she": "Female"}.get(m.group(1).lower(), "Other")


def parse_region(raw: str) -> list[str]:
    text = _strip_history(raw)
    out = []
    for val in _FI.findall(text):
        val = val.strip()
        if val and val not in out:
            out.append(val)
    return out


# ---------------------------------------------------------------------------
# Source
# ---------------------------------------------------------------------------


class TagSource:
    """Lazy, cached champion tags shared by every game's build."""

    def __init__(self, wiki: str):
        self.wiki = wiki
        self._bio: dict[str, str] = {}
        self._classes: dict[str, list[str]] = {}
        self._tags: dict[str, dict] = {}
        self._classes_loaded = False

    # -- fetching ----------------------------------------------------------

    def ensure(self, names) -> None:
        """Fetch bios for every champion not seen yet, 50 titles per request."""
        # Imported here because build_data imports this module.
        from build_data import api_query

        wanted = []
        for name in names:
            page = ALIASES.get(name, name)
            if page not in self._bio and page not in wanted:
                wanted.append(page)
        if not self._classes_loaded:
            self._load_classes()
        for i in range(0, len(wanted), 50):
            chunk = wanted[i:i + 50]
            params = {
                "action": "query",
                "prop": "revisions",
                "rvprop": "content",
                "rvslots": "main",
                "titles": "|".join(f"Universe:{name}" for name in chunk),
            }
            data = self._query(params)
            for page in data.get("query", {}).get("pages", {}).values():
                title = page.get("title", "")[len("Universe:"):]
                revs = page.get("revisions") or [{}]
                text = (revs[0].get("slots") or {}).get("main", {}).get("*", "")
                self._bio[title] = text
            for name in chunk:
                self._bio.setdefault(name, "")

    @staticmethod
    def _query(params: dict) -> dict:
        """One API call. A truncated or blocked body is retried once."""
        import json

        from build_data import api_query

        params.setdefault("format", "json")
        for attempt in (0, 1):
            try:
                return api_query(params)
            except json.JSONDecodeError:
                if attempt:
                    raise
        return {}

    def _load_classes(self) -> None:
        from build_data import http_get, parse_lua

        raw = http_get(f"{self.wiki}/Module:ChampionData/data?action=raw").decode("utf-8")
        for name, info in parse_lua(raw).items():
            if not isinstance(info, dict):
                continue
            classes = [info.get("herotype"), info.get("alttype")]
            self._classes[name] = [c for c in dict.fromkeys(classes) if isinstance(c, str) and c]
        self._classes_loaded = True

    # -- lookups -----------------------------------------------------------

    def champion(self, name: str) -> dict:
        page = ALIASES.get(name, name)
        if page in self._tags:
            return self._tags[page]
        text = self._bio.get(page, "")
        tags = {
            "kind": [],
            "species": parse_species(_bio_param(text, "species")) if text else [],
            "gender": [parse_gender(_bio_param(text, "pronoun"))] if text else [],
            "region": parse_region(_bio_param(text, "region")) if text else [],
            # ChampionData keys the champion by its in-game name, which is what
            # the skin data uses, not the lore page alias.
            "class": list(self._classes.get(name) or self._classes.get(page) or []),
        }
        for key, val in OVERRIDES.get(name, {}).items():
            tags[key] = val if isinstance(val, list) else [val]
        for species in tags["species"]:
            kind = KINDS.get(species)
            if kind and kind not in tags["kind"]:
                tags["kind"].append(kind)
        tags = {k: v for k, v in tags.items() if v}
        self._tags[page] = tags
        return tags

    def for_skin(self, owner: str, lines) -> dict:
        tags = {k: list(v) for k, v in self.champion(owner).items()}
        vibes = skin_vibes(lines, owner)
        if vibes:
            tags["vibe"] = vibes
        return tags


# ---------------------------------------------------------------------------
# Vibes
# ---------------------------------------------------------------------------
#
# Skin line -> art direction. Exact, case-insensitive names, because the names
# are the wiki's own and guessing from keywords misfires ("Star Guardian" vs
# "Guardian of the Sands"). A line absent here is reported by the build, so new
# wiki lines show up as work rather than as silently untagged art.

VIBES = {
    "Legacy": [],
    "High Noon": ["Western", "Dark"],
    "Spirit Blossom": ["Fantasy", "Oriental"],
    "PROJECT": ["Sci-Fi"],
    "Day Job": ["Modern", "Cute"],
    "Coven": ["Dark", "Fantasy"],
    "Nightbringer and Dawnbringer": ["Fantasy", "Dark"],
    "Pool Party": ["Summer", "Cute"],
    "Dragonmancers": ["Fantasy"],
    "Infernal": ["Dark", "Fantasy"],
    "Immortal Journey": ["Oriental", "Fantasy"],
    "Soul Fighter": ["Anime", "Fantasy"],
    "K/DA": ["Music", "Anime", "Modern"],
    "Battle Academia": ["Anime", "Modern"],
    "Blood Moon": ["Oriental", "Dark"],
    "Crystal Rose": ["Fantasy"],
    "Lunar Revel": ["Oriental", "Holiday"],
    "Star Guardian Season 1": ["Anime"],
    "Star Guardian Season 2": ["Anime"],
    "Star Guardian Season 3": ["Anime"],
    "Star Guardian Season 4": ["Anime"],
    "Dark Star": ["Sci-Fi", "Dark", "Fantasy"],
    "Cosmic": ["Fantasy", "Sci-Fi"],
    "Rift Quest": ["Fantasy", "Cute"],
    "Anima Squad": ["Anime", "Sci-Fi", "Cute"],
    "Dragon World": ["Fantasy"],
    "Trick-or-Treat": ["Holiday", "Cute", "Dark"],
    "Pulsefire": ["Sci-Fi"],
    "Arcane": ["Modern"],
    "Lunar Revel: Firecracker": ["Oriental", "Holiday"],
    "Lunar Revel: Warring Kingdoms": ["Oriental", "Holiday", "Fantasy"],
    "Arcade: Heroes": ["Sci-Fi", "Anime"],
    "Hextech": ["Sci-Fi", "Fantasy"],
    "Snowdown Showdown": ["Holiday"],
    "Glorious": [],
    "Space Groove": ["Music", "Sci-Fi", "Cute"],
    "Winter Wonder": ["Holiday"],
    "Winterblessed": ["Holiday", "Fantasy"],
    "Bewitching": ["Holiday", "Dark", "Cute"],
    "Empyrean": ["Fantasy", "Anime"],
    "Porcelain": ["Oriental", "Fantasy"],
    "Victorious": ["Esports"],
    "Bilgewater: Burning Tides": ["Fantasy"],
    "Heartbreakers": ["Cute", "Holiday"],
    "Wonders of the World": ["Fantasy"],
    "Mecha": ["Sci-Fi"],
    "Toy Box": ["Cute"],
    "Arcade: Battle Bosses": ["Sci-Fi", "Anime"],
    "Battlecast": ["Sci-Fi", "Dark"],
    "Elderwood": ["Fantasy"],
    "True Damage": ["Music", "Modern"],
    "Cats Versus Dogs": ["Cute"],
    "Eclipse": ["Dark", "Fantasy"],
    "Fables": ["Fantasy", "Cute"],
    "HEARTSTEEL": ["Music", "Modern"],
    "Shan Hai Scrolls": ["Oriental", "Fantasy"],
    "Silver Age": ["Modern"],
    "Worldbreaker": ["Fantasy", "Dark"],
    "Cafe Cuties": ["Cute", "Anime"],
    "Sentinels of Light": ["Fantasy", "Dark"],
    "Bees!": ["Cute"],
    "Debonair": ["Modern"],
    "Mythmaker": ["Oriental", "Holiday"],
    "Odyssey": ["Sci-Fi"],
    "Ruined": ["Dark", "Fantasy"],
    "Astronauts": ["Cute", "Sci-Fi"],
    "Faerie Court": ["Cute", "Fantasy"],
    "Guardian of the Sands": ["Fantasy"],
    "Arcana": ["Fantasy", "Dark"],
    "Battle Queens": ["Anime", "Fantasy"],
    "Death Sworn": ["Dark"],
    "Lunar Beast": ["Oriental", "Sci-Fi", "Holiday"],
    "Soccer Cup": ["Modern"],
    "World Championship": ["Esports"],
    "Academy": ["Modern", "Anime"],
    "Arclight": ["Fantasy"],
    "Definitely Not": ["Cute"],
    "Petals of Spring": ["Cute", "Oriental"],
    "Calligraphia": ["Oriental", "Fantasy"],
    "Fright Night": ["Dark", "Holiday"],
    "High Society": ["Modern"],
    "Inkshadow": ["Oriental", "Dark"],
    "Marauder": ["Fantasy", "Dark"],
    "Medieval": ["Fantasy"],
    "Neon Daredevil": ["Sci-Fi", "Modern"],
    "Otherroads": ["Fantasy"],
    "Prehistoric Hunters": ["Fantasy"],
    "Stargazer": ["Fantasy", "Anime"],
    "Steel Valkyries": ["Sci-Fi"],
    "Summer Party": ["Summer"],
    "Super Galaxy": ["Sci-Fi", "Anime"],
    "Broken Covenant": ["Dark", "Fantasy"],
    "Chromacrash": ["Sci-Fi", "Modern"],
    "Crime City": ["Modern", "Dark"],
    "Crime City Nightmare": ["Dark", "Modern"],
    "Cryptic Depth": ["Fantasy", "Dark"],
    "Culinary Masters": ["Cute", "Modern"],
    "Heavenscale": ["Oriental", "Fantasy"],
    "Ocean Song": ["Summer", "Music"],
    "Zombies VS Slayers": ["Dark", "Holiday"],
    "Cops and Robbers": ["Modern"],
    "Omega Squad": ["Sci-Fi", "Modern"],
    "Program": ["Sci-Fi"],
    "Weather Entity": ["Fantasy"],
    "Ashen Knights": ["Fantasy", "Dark"],
    "Commando": ["Modern"],
    "Corrupted": ["Dark"],
    "Demonic": ["Dark"],
    "Freljord": ["Fantasy"],
    "Garden Party": ["Cute", "Fantasy"],
    "Love Confession": ["Cute"],
    "Mecha Kingdoms": ["Sci-Fi", "Fantasy"],
    "PsyOps": ["Sci-Fi", "Dark"],
    "Risen Legends": ["Fantasy", "Dark"],
    "Road Warrior": ["Sci-Fi", "Modern"],
    "Warden": ["Fantasy"],
    "Arcanists": ["Fantasy"],
    "Black Rose Group": ["Dark", "Fantasy"],
    "Blackfrost": ["Dark", "Fantasy"],
    "Cottontail": ["Cute", "Holiday"],
    "Forgotten Depths": ["Dark", "Fantasy"],
    "Omen of the Dark": ["Dark"],
    "Pentakill": ["Music", "Dark"],
    "Pentakill III: The Lost Chapter": ["Music", "Dark"],
    "Spirit Blossom Springs": ["Cute", "Oriental"],
    "Sugar Rush": ["Cute"],
    "Superheroes Versus Supervillains": ["Anime", "Modern"],
    "Winter Sports": ["Holiday"],
    "Bloodstone": ["Dark", "Fantasy"],
    "Celestial Embroidery": ["Oriental", "Fantasy"],
    "Dragon Lantern": ["Oriental", "Holiday"],
    "Fiend Queller": ["Oriental", "Fantasy"],
    "Food Spirits": ["Cute", "Oriental"],
    "Headhunter": ["Sci-Fi", "Dark"],
    "Heavy Metal": ["Music", "Dark"],
    "La Ilusión": ["Holiday", "Dark"],
    "Mad Scientists": ["Sci-Fi"],
    "Snow Day": ["Holiday", "Cute"],
    "Storybook": ["Cute", "Fantasy"],
    "Traditional": [],
    "Urf the Manatee": ["Cute"],
    "Vandal": ["Modern"],
    "Arcticops": ["Modern", "Sci-Fi"],
    "Arctic Ops": ["Modern"],
    "Battle of the God-Kings": ["Fantasy", "Dark"],
    "Chosen of the Wolf": ["Fantasy", "Dark"],
    "Chronicle": ["Fantasy"],
    "Conqueror": ["Esports"],
    "Dreamscapes": ["Fantasy"],
    "Dunkmaster": ["Cute", "Modern"],
    "Food Fight": ["Cute"],
    "Glacial": ["Fantasy"],
    "Grand Reckoning": ["Fantasy"],
    "Masque of the Black Rose": ["Dark", "Fantasy"],
    "Riot": [],
    "Snow Moon": ["Oriental", "Holiday"],
    "Splendor Opus": ["Fantasy", "Modern"],
    "Street Demons": ["Modern", "Dark"],
    "Supreme Cells": ["Sci-Fi", "Modern"],
    "Surprise Party": ["Cute", "Holiday"],
    "Albion": ["Fantasy"],
    "Collector's Edition": [],
    "Curse of the Void": ["Dark", "Sci-Fi"],
    "Gilded": ["Fantasy"],
    "Goth": ["Dark", "Modern"],
    "Hexplorer": ["Sci-Fi", "Modern", "Fantasy"],
    "Highstakes": ["Modern"],
    "Luchador": ["Modern"],
    "NOVA": ["Music", "Sci-Fi"],
    "PAX": [],
    "Phoenixmancers": ["Fantasy", "Oriental"],
    "Rain Shepherd": ["Cute", "Fantasy"],
    "Remix Rumble": ["Music", "Cute"],
    "Shockblade": ["Fantasy", "Dark"],
    "The Laws of Stone": ["Fantasy"],
    "Woad": ["Fantasy"],
    "Bilgewater: Curse of the Drowned": ["Dark", "Fantasy"],
    "Bilgewater: Mercs": ["Fantasy"],
    "Demacia Vice": ["Modern"],
    "Lancer": ["Fantasy"],
    "Lovestruck": ["Cute", "Holiday"],
    "Mystical Herald": ["Fantasy"],
    "Pandemonium": ["Dark", "Fantasy"],
    "Primal Ambush": ["Fantasy"],
    "Primordian": ["Fantasy", "Dark"],
    "Steel Legion": ["Sci-Fi"],
    "Superfans": ["Music", "Modern"],
    "The Eternal Aspects": ["Fantasy"],
    "Withered Rose": ["Dark", "Fantasy"],
    "Wondertown": ["Cute", "Fantasy"],
    "Crystalis Indomitus": ["Fantasy", "Sci-Fi"],
    "Crystalis Motus": ["Fantasy", "Sci-Fi"],
    "Cyber Pop": ["Sci-Fi", "Modern", "Cute"],
    "Death Blossom": ["Dark", "Fantasy"],
    "Dreadknights": ["Dark", "Fantasy"],
    "Dreadnova": ["Sci-Fi", "Dark"],
    "Dumpling Darlings": ["Cute", "Oriental"],
    "Eternum": ["Dark", "Sci-Fi"],
    "Fatemakers and Fatebreakers": ["Fantasy"],
    "Flora Fatalis": ["Dark", "Fantasy"],
    "Galactic": ["Sci-Fi"],
    "Heartthrobs and Heartaches": ["Cute", "Holiday"],
    "Justicar": ["Fantasy"],
    "Masked Justice": ["Anime", "Modern"],
    "Monster Tamers": ["Cute", "Fantasy"],
    "Order of the Lotus": ["Oriental", "Fantasy"],
    "Pharaoh": ["Fantasy"],
    "Piltover Customs": ["Sci-Fi", "Modern"],
    "Praetorian": ["Sci-Fi", "Dark"],
    "Rift Hospital": ["Modern", "Cute"],
    "Sinful Shores": ["Summer", "Dark"],
    "Soulstealer": ["Dark", "Fantasy"],
    "Three Honors": ["Fantasy"],
    "Thunder Lord": ["Fantasy"],
    "Visions of the Fallen": ["Dark", "Fantasy"],
    "Warhounds": ["Sci-Fi", "Dark"],
    "Zenith Games": ["Anime", "Modern"],
    "Aegis Frame": ["Sci-Fi"],
    "Challenger": ["Esports"],
    "Crimson Elite": [],
    "DJ": ["Music", "Modern"],
    "Elf Forest": ["Fantasy", "Cute"],
    "Invaders": ["Sci-Fi"],
    "KBG": ["Esports"],
    "Magma Chamber": ["Fantasy"],
    "Papercraft": ["Cute", "Fantasy"],
    "Popstar": ["Music", "Cute"],
    "Sunken Shadows": ["Dark", "Fantasy"],
    "Tales from the Rift": ["Fantasy"],
    "Beta": [],
    "Classic": [],
    "Elementalist": ["Fantasy"],
    "Fist Bumps and Festivities": ["Cute", "Holiday"],
    "Heartsong": ["Cute", "Music"],
    "Iconic": [],
    "Kaiju": ["Sci-Fi"],
    "Modern Mythos": ["Fantasy", "Modern"],
    "Revenant Reign": ["Dark"],
    "Ruination": ["Dark", "Fantasy"],
    "Spirit Guard": ["Fantasy"],
    "Triumphant": [],
    "World Champions": ["Esports"],
}

_VIBES_CI = {k.lower(): v for k, v in VIBES.items()}


def _vibes_for(line: str) -> list[str] | None:
    """Vibes for one skin line, or None when the line is unknown to VIBES."""
    key = line.lower()
    if key in _VIBES_CI:
        return _VIBES_CI[key]
    # Annual lines are one wiki string per year ("World Champions: 2019").
    if key.startswith("world champions"):
        return VIBES["World Champions"]
    return None

# Champions whose own art carries a vibe before any skin line does; used only
# for skins with no themed line (Original and the pre-line days).
CHAMP_VIBES = {
    # Cute
    "Amumu": ["Cute"], "Annie": ["Cute"], "Corki": ["Cute"], "Fizz": ["Cute"],
    "Gnar": ["Cute"], "Gwen": ["Cute"], "Heimerdinger": ["Cute"], "Kennen": ["Cute"],
    "Kled": ["Cute"], "Lillia": ["Cute"], "Lulu": ["Cute"], "Milio": ["Cute"],
    "Neeko": ["Cute"], "Norra": ["Cute"], "Nunu & Willump": ["Cute", "Holiday"],
    "Poppy": ["Cute"], "Rumble": ["Cute"], "Seraphine": ["Cute"], "Smolder": ["Cute"],
    "Teemo": ["Cute"], "Tristana": ["Cute"], "Veigar": ["Cute"], "Yuumi": ["Cute"],
    "Ziggs": ["Cute"], "Zoe": ["Cute"],
    # Dark
    "Aatrox": ["Dark"], "Bel'Veth": ["Dark"], "Cho'Gath": ["Dark"], "Elise": ["Dark"],
    "Evelynn": ["Dark"], "Fiddlesticks": ["Dark"], "Hecarim": ["Dark"],
    "Kalista": ["Dark"], "Karthus": ["Dark"], "Kha'Zix": ["Dark"], "Kog'Maw": ["Dark"],
    "Mordekaiser": ["Dark"], "Naafiri": ["Dark"], "Nocturne": ["Dark"],
    "Rek'Sai": ["Dark"], "Shaco": ["Dark"], "Sion": ["Dark"], "Thresh": ["Dark"],
    "Urgot": ["Dark"], "Vel'Koz": ["Dark"], "Viego": ["Dark"], "Warwick": ["Dark"],
    "Yorick": ["Dark"],
}

REPORTED = []


def skin_vibes(lines, champion: str) -> list[str]:
    """Vibes for one cosmetic: its skin line, else its champion's baseline."""
    out = []
    listed = lines if isinstance(lines, list) else ([lines] if lines else [])
    for line in listed:
        if not isinstance(line, str):
            continue
        vibes = _vibes_for(line)
        if vibes is None:
            REPORTED.append(line)
            continue
        for vibe in vibes:
            if vibe not in out:
                out.append(vibe)
    if not out:
        out = list(CHAMP_VIBES.get(ALIASES.get(champion, champion), []))
    return out


def report_unmapped() -> None:
    """Print skin lines the vibe table does not know yet."""
    unknown = sorted(set(REPORTED))
    if unknown:
        print(f"skin lines without vibes ({len(unknown)}): {', '.join(unknown)}")
