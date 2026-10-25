"""Pure selection of the final episode list from catalogue notices.

The catalogue has one notice per broadcast. Here they are reduced to one row per episode: other programmes
are dropped, and every broadcast of an episode (reruns, relays on other channels) is kept once, from the channel
closest to the show's origin.
"""
from __future__ import annotations

import difflib
import re
import unicodedata

from .ina import FIRST_RUN_END, TITLE
from .spelling import correct

SHOW = TITLE

# Credited with role PRE (presenter) or PAR (participant, used by the 1983 notices): Maïté and her co-presenter Micheline Banzet Lawton on the original run
# (to 1999), then the 2023+ revival.
PRESENTERS = {"Ordonez Maïté", "Banzet Lawton Micheline","Mignot Fabrice", "Estremo Caroline"}

# Lower is preferred; the Occitanie stations and anything else come last.
CHANNEL_RANK = {"France 3 Poitou Charente": 0, "France 3 Aquitaine": 1, "France 3": 2, "FR3": 2}
OTHER_RANK = 3
REGIONAL = {"France 3 Poitou Charente", "France 3 Aquitaine"}


def presenters(pre: str | None) -> list[str]:
    """Known presenters among the PRE credits (names separated by " ; ")."""
    return [n for n in (s.strip() for s in (pre or "").split(" ; ")) if n in PRESENTERS]


# "La cuisine des mousquetaires : [émission du 5 avril 1990]", "Les cuisines de France : émission du 17 mars 1992":
# the INA's wrapper around a whole magazine; it only lists the segments, which have their own notices.
WRAPPER = re.compile(r"émission du \d", re.I)


# Julien Courbet's FR3 programme (1991-92) aired inserts of the show, which the INA files under the show's collection
# like its own segments by other chefs: only those credited to the show's director or presenters are the show.
OTHER_PROGRAMME = "les cuisines de france"
DIRECTOR = "Bellot Patrice"


def _in_other_programme_without_the_show(row: dict) -> bool:
    return ((row.get("titre_programme") or "").casefold() == OTHER_PROGRAMME
            and not presenters(row.get("pre")) and DIRECTOR not in (row.get("generique") or ""))


# Long notices (25 to 40 minutes, the show lasts about 13) of Julien Courbet's programme "Les cuisines de France" or
# its specials, not episodes of the show: found by hand, nothing in the notices tells them apart.
EXCLUDED_NOTICES = {
    "RE_RBC07095970",   # 1991-05-07 "spéciale centième", 40 min, Courbet presenter
    "RE_RBC07095975",   # 1991-09-17 "spéciale centième", 25 min
    "DA_CPC92000335",   # 1992-01-07 "Spéciale centième", Courbet receives Maïté and Micheline
    "DA_CPC92000420",   # 1992-01-10 "Tourin blanc gascon", programme "Les cuisines de France", Courbet presenter
    "DA_CPC92012852",   # 1992-06-23 "Garbure et lapin aux girolles...", 26 min
}


def is_show(row: dict) -> bool:
    """The show's own collection, or a notice filed elsewhere but presented by a known presenter or titled
    "La cuisine des mousquetaires : ...". Notices that name no episode (wrappers, series descriptions, the bare show
    title) are not episodes."""
    if row["notice_path"] in EXCLUDED_NOTICES or _in_other_programme_without_the_show(row) or episode_key(row["titre_propre"]) == episode_key(SHOW) or WRAPPER.search(row["titre_propre"] or "") or (row.get("type_description") or "").startswith("Collection"):
        return False
    return row["titre_collection"] == SHOW or bool(presenters(row["pre"])) or bool(SHOW_PREFIX.match(row["titre_propre"] or ""))


# Words that differ between the INA's spellings of one title ("Les homards à la rionnaise" / "Homard à la Rionnaise").
STOPWORDS = {"le", "la", "les", "l", "un", "une", "de", "du", "des", "d", "a", "au", "aux", "en", "et"}


SHOW_PREFIX = re.compile(r"^\s*la cuisine des mousquetaires?\s*:\s*", re.I)


def episode_key(title: str | None) -> str:
    """Title reduced to its significant words: no show prefix, case, accents, punctuation, articles or plural s/x,
    and the misspellings and "St" / "Saint" variants of the listed title (so "sace cavigote" is "sauce ravigote")."""
    plain = unicodedata.normalize("NFKD", correct(_typography(SHOW_PREFIX.sub("", title or ""))).lower()).encode("ascii", "ignore").decode()
    words = [w for w in re.findall(r"[a-z0-9]+", plain) if w not in STOPWORDS]
    return " ".join(w[:-1] if len(w) > 3 and w[-1] in "sx" else w for w in words)


# The show name, with its date or series number, before a colon: "La cuisine des mousquetaires du 7 mai 1991 : ...",
# "La cuisine des mousquetaires, série 2 : ...". Not used to compare titles: two such notices of other dates differ.
DISPLAY_PREFIX = re.compile(r"^\s*la cuisine des mousquetaires?(?:\s+du\s[^:]*|,[^:]*)?\s*:\s*", re.I)


UNNAMED = re.compile(r"^\s*la cuisine des mousquetaires?\s+(du\s+\d[^:-]*?)\s*(-\s*incomplet)?\s*$", re.I)


# "Saint Jacques", "St Jacques", "st jacques", "SAINT HUBERT": the saint's name is hyphenated and capitalised.
SAINT = re.compile(r"\b(saint|sainte|st|ste)\.?[ -]+([^\W\d_]{2,})", re.I)
CAPITALS = re.compile(r"\b(?![IVXLC]+\b)[A-ZÀ-ÖØ-Þ]{2,}\b")       # not the Roman numerals ("Henri IV")


def _typography(title: str) -> str:
    """Words in capitals are capitalised ("MAZERE" -> "Mazere"); "St", "Saint" and "Ste" are written out and joined
    by a hyphen to the capitalised name that follows."""
    title = CAPITALS.sub(lambda m: m[0].capitalize(), title)

    def saint(m: re.Match) -> str:
        if m[2].lower() in STOPWORDS:        # "saint et ...": not a name
            return m[0]
        return ("Sainte-" if m[1].lower() in ("sainte", "ste") else "Saint-") + m[2][0].upper() + m[2][1:]
    return SAINT.sub(saint, title)


# "Spécial Jean BARDET : rognons", "Spéciale avec A. DAGUIN : brochettes", "Spécial Didier Oudill: papillotes": the
# episodes with a guest chef, written every which way. Listed as "Spéciale Jean Bardet : rognons".
SPECIAL = re.compile(r"^Sp[ée]cial(?:e)?(?:\s+avec)?\s+(?P<chef>.+?)(?:\s*:\s*|\s+-\s+|$)(?P<dishes>.*)$", re.I)
PARTICLES = {"de", "du", "des", "d'", "von"}
# Chefs the INA gives by initial or without accent, spelled out where the same notices or a second spelling settle it.
CHEFS = {"R. Verge": "Roger Vergé", "Roger Verge": "Roger Vergé", "A. Daguin": "André Daguin"}


def _chef(name: str) -> str:
    """The chef's name with a capital on each word ("Jean BARDET" -> "Jean Bardet"), particles kept in lower case."""
    words = [w if w.lower() in PARTICLES else "-".join(p[:1].upper() + p[1:].lower() if p.isupper() or p.islower() else p
                                                       for p in w.split("-")) for w in name.split()]
    name = " ".join(words)
    return CHEFS.get(name, name)


def _special(title: str) -> str:
    m = SPECIAL.match(title)
    if not m or not all(w.lower() in PARTICLES or w[0].isupper() for w in m["chef"].split()):     # "Spéciale centième"
        return title
    dishes = m["dishes"].strip()
    return f"Spéciale {_chef(m['chef'].strip())}" + (f" : {dishes}" if dishes else "")


def display_title(title: str) -> str:
    """The title as listed: without the INA's provisional brackets or the show-name prefix, in sentence case when
    the INA wrote it in capitals, and starting with a capital. A notice that only gives the show and its date
    names no dish: "La cuisine des mousquetaires du 22 mai 1990" is listed "Émission du 22 mai 1990 (titre non renseigné)"."""
    title = title.strip()
    if m := UNNAMED.match(title):
        return f"Émission {m[1]} ({'incomplète, ' if m[2] else ''}titre non renseigné)"
    if title.startswith("[") and title.endswith("]"):
        title = title[1:-1].strip()
    title = DISPLAY_PREFIX.sub("", title).strip()
    if title.isupper():
        title = title.lower()
    i = next((i for i, c in enumerate(title) if c.isalpha()), None)
    title = title if i is None else title[:i] + title[i].upper() + title[i + 1:]
    return _special(correct(_typography(title)))


def _rank(row: dict) -> tuple:
    """Earliest broadcast first (a placeholder date counts last); on the same day the channel decides, whichever
    it is: a national and a regional broadcast of one episode are equal, the first to air is the first run."""
    return is_placeholder(row), row["date_iso"] or "", CHANNEL_RANK.get(row["chaine"], OTHER_RANK), row["heure_diffusion"] or ""


CONFIDENCE_RANK = {"manual": 0, "high": 1, "medium": 2, "low": 3}
VIDEO_FIELDS = ("youtube_url", "match_confidence", "match_score")


def _video(group: list[dict], first: dict) -> dict:
    """The YouTube fields of the episode (empty if none matched): the video of the first run, unless that match is
    a doubtful one, else the best match among the other broadcasts (a video often shows a rerun)."""
    matched = [r for r in group if r.get("youtube_url")]
    if not matched:
        return {}
    best = min(matched, key=lambda r: (CONFIDENCE_RANK.get(r["match_confidence"], 9), -(r["match_score"] or 0)))
    if first.get("youtube_url") and first["match_confidence"] != "low":
        best = first
    return {**{k: best[k] for k in VIDEO_FIELDS}, "youtube_duree": _mmss(best["youtube_duree_s"])}


def is_placeholder(row: dict) -> bool:
    """A 1 January at midnight: the catalogue's stand-in for "year known, date unknown"."""
    return (row["date_iso"] or "")[5:] == "01-01" and (row["heure_diffusion"] or "00:00").startswith(("00:00", "24:00"))


def _placeholder_aliases(shows: list[dict]) -> dict[str, str]:
    """Episode key of each placeholder-dated notice -> key of the one dated notice of the same year it abbreviates.

    "[le sanglier]" (1984-01-01) is "Les gibiers et leurs terrines : le sanglier" (1984-09-17): the placeholder's
    words are all in the other title. Only an unambiguous candidate counts.
    """
    dated = {}
    for r in shows:
        if r["date_iso"] and not is_placeholder(r):
            dated.setdefault(r["date_iso"][:4], set()).add(episode_key(r["titre_propre"]))
    aliases = {}
    for r in shows:
        if not (r["date_iso"] and is_placeholder(r)):
            continue
        key = episode_key(r["titre_propre"])
        words = set(key.split())
        found = {k for k in dated.get(r["date_iso"][:4], ()) if k != key and words <= set(k.split())}
        if len(found) == 1 and words:
            aliases[key] = found.pop()
    return aliases


def _premiere(group: list[dict]) -> tuple[str, bool]:
    """Earliest real date, unless a placeholder dates from an earlier year (then that placeholder, as uncertain)."""
    real = [r["date_iso"] for r in group if r["date_iso"] and not is_placeholder(r)]
    fake = [r["date_iso"] for r in group if r["date_iso"] and is_placeholder(r)]
    if real and (not fake or min(fake)[:4] >= min(real)[:4]):
        return min(real), False
    return (min(fake), True) if fake else ("", False)


# Fields of the preferred notice that are completed from the other broadcasts of the episode when blank.
FILLED = ("duree_s", "generique", "resume_documentaire")


def _blank(value: str | None) -> bool:
    """Empty, or a zero / 24:00 time standing in for "unknown" (a duration is blank when None or 0)."""
    return not value or (isinstance(value, str) and (bool(re.fullmatch(r"[0:]+", value)) or value.startswith("24:00")))


def _says_rerun(text: str) -> bool:
    return bool(RERUN_OF_DATE.search(text) or RERUN_OF_FIRST.search(text))


def _filled(best: dict, group: list[dict], premiere: str) -> dict:
    """Values for the fields the first-run notice lacks, taken from the reruns (earliest first), and a plain title
    for a bracketed one ("[le sanglier]" is the INA's provisional title)."""
    ranked = sorted(group, key=_rank)
    out = {}
    if best["titre_propre"].startswith("["):
        plain = [r["titre_propre"] for r in ranked if not r["titre_propre"].startswith("[")]
        if plain:
            out["titre_propre"] = plain[0]
    for field in FILLED:
        if _blank(best.get(field)):
            donors = [r for r in ranked if not _blank(r.get(field)) and not _says_rerun(r.get(field))]
            if donors:
                out[field] = donors[0][field]
    if _blank(best["heure_diffusion"]):     # a time only from a broadcast of the same day
        same_day = [r for r in ranked if r["date_iso"] == premiere and not _blank(r["heure_diffusion"])]
        if same_day:
            out["heure_diffusion"] = same_day[0]["heure_diffusion"]
    return out


# A short title ("Les foies de veau") is contained in many others by chance, so it needs the exact same duration.
SHORT_TITLE_WORDS = 3
DURATION_TOLERANCE_S = 2
STEM = 5        # the INA spells one word several ways: "Bordelais" / "Bordelaise", "pibales" / "piballes"
# Titles worded differently but alike (typos, "St" / "Saint", a dish added or dropped) are the same episode when
# their durations are close too: the rerun of a recording lasts the same to the second, a recut a few seconds more.
FUZZY_TITLE = 0.8
FUZZY_DURATION_S = 5
# "La cuisine des mousquetaires du 4 mai 1993": a title that only gives the date names no dish to compare.
DATE_TITLE = re.compile(r"^\s*la cuisine des mousquetaires?\s+du\s+\d", re.I)


def _mmss(seconds: int | None) -> str:
    """Seconds as "mm:ss" (minutes past 59 kept: "40:12"), empty if unknown."""
    return "" if not seconds else f"{seconds // 60:02d}:{seconds % 60:02d}"


def _durations(group: list[dict]) -> list[int]:
    """Known durations of the group in seconds."""
    return [r["duree_s"] for r in group if r.get("duree_s")]


def _same_duration(a: list[int], b: list[int], tolerance: int) -> bool:
    return any(abs(x - y) <= tolerance for x in a for y in b)


def _merge_reruns(groups: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """Merge episodes that are the same broadcast under two titles. The INA titles one recipe "La queue de boeuf
    aux lentilles" and "Queue de boeuf aux lentilles, sauté de queue de boeuf aux pois chiches". Words are compared
    by their first letters (spellings vary: "Bordelais" / "Bordelaise"). Two episodes are the same when

    - their titles have the same words, or
    - the words of one are all in the other (at least two of them) and the durations agree: within 2 seconds for
      three words or more, identical for fewer, or
    - they were broadcast the same day, share a word, and have the same duration: the relay of one episode, or
    - their titles are alike (similarity of 0.8 or more once reduced to their key) and the durations are within 5
      seconds, unless the titles only give a date, or
    - both come from the 1983-86 series titled "La cuisine des mousquetaires : ...", share a word and have
      durations within 2 seconds: the summer 1986 rerun of the 1983 series carries other titles for its episodes
      ("les magrets" for "sanquette, magret et pommes de terre sautées").
    """
    keys = list(groups)
    words = {k: {w[:STEM] for w in k.split()} for k in keys}
    durations = {k: _durations(groups[k]) for k in keys}
    days = {k: {r["date_iso"] for r in groups[k]} for k in keys}
    series = {k: any(SHOW_PREFIX.match(r["titre_propre"] or "") for r in groups[k]) for k in keys}
    parent = {k: k for k in keys}

    def find(k: str) -> str:
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            small, big = sorted((words[a], words[b]), key=len)
            tolerance = DURATION_TOLERANCE_S if len(small) >= SHORT_TITLE_WORDS else 0
            merge = (
                (len(small) >= 2 and small == big)
                or (len(small) >= 2 and small <= big and _same_duration(durations[a], durations[b], tolerance))
                or (small & big and days[a] & days[b] and _same_duration(durations[a], durations[b], 0))
                or (small & big and series[a] and series[b] and _same_duration(durations[a], durations[b], DURATION_TOLERANCE_S)))
            if merge:
                parent[find(b)] = find(a)
    fuzzy = [k for k in keys if durations[k] and not all(DATE_TITLE.match(r["titre_propre"] or "") for r in groups[k])]
    for i, a in enumerate(fuzzy):
        for b in fuzzy[i + 1:]:
            if (difflib.SequenceMatcher(None, a, b).ratio() >= FUZZY_TITLE
                    and _same_duration(durations[a], durations[b], FUZZY_DURATION_S)):
                parent[find(b)] = find(a)
    merged: dict[str, list[dict]] = {}
    for k in keys:
        merged.setdefault(find(k), []).extend(groups[k])
    return merged


# Notices of one episode that no title or duration rule joins, found by hand; each set is one episode.
SAME_EPISODE = [
    # 1991 title cut at "au foie" and 4 s longer than 1992; the 1995 rerun has another long title but the 1992 summary
    {"RE_RBC07108722", "DA_CPC92002462", "TV_22783.001"},
    # same recipe, durations 4 s apart
    {"DA_CPC93010948", "RE_RBC08005770"},
    # the same 38-minute special under two titles, a week apart (38:15 both)
    {"RE_RBC07108923", "DA_CPC93001816"},
    # the 1991 title adds "et à la lotte" and the notice is 1 min 28 s shorter than the 1992 one
    {"DA_CPC10004993", "RE_RBC07108755"},
    # reruns reviewed by hand (candidates the title and duration rules left apart): the same dish under reworded titles
    {"DA_CPC93010412", "RE_RBC08005760"},                   # sarriette, 0 s
    {"TV_71350.001", "TV_657530.001"},                      # jambon au cidre, 0 s
    {"DA_CPC94008224", "RE_RBC08009680"},                   # jambonneau au maïs, 1 s
    {"RE_RBC07022460", "DA_CPC91014368"},                   # coq au vin sous la cendre
    {"RE_BOC8907030116", "DA_CPC93004442"},                 # dodine
    {"RE_RBC07036004", "DA_CPC91014509"},                   # crépinettes de foie gras et dinde
    {"RE_RBC07083745", "DA_CPC92002026"},                   # cochon de lait farci aux haricots landais
    {"RE_RBC07108737", "DA_CPC92003715", "DA_CPC92013808"}, # soupe de poissons de fête et filet de sole
    {"RE_RBC07095947", "TV_195357.001"},                    # escalope de saumon, purée de cèpes
    {"RE_BOC8907030119", "RE_RBC07035705", "DA_CPC92001437"},   # ris de veau et gratin de courgettes
    {"RE_RBC07083593", "DA_CPC92012426"},                   # cassoulet de Rion-des-Landes
    {"DA_CPC93006108", "RE_RBC08005644"},                   # esturgeon à la bordelaise
    {"RE_RBC07108756", "DA_CPC92004589"},                   # araignées farcies
    {"RE_BOC8907030125", "DA_CPC92011197"},                 # matelote d'anguille
    {"RE_RBC07108915", "DA_CPC92016916"},                   # soupe à l'oignon au champagne, cailles
    {"RE_RBC06068102", "DA_CPC93002567"},                   # canard et poireaux braisés
    {"DA_CPC92002967", "TV_54405.001"},                     # foie gras aux raisins, poivre vert, persillade
    {"RE_RBC07095858", "DA_CPC92014420"},                   # blanc de poulet au Sauterne et aux raisins
    {"RE_RBC07095983", "DA_CPC91010709", "DA_CPC92012912"}, # pâté de cèpes en croûte (1991-06-11 and 1992-10-12: 13:45 both)
    {"RE_BOC8908230340", "DA_CPC92000961"},                 # truite aux girolles, aux épices, aux amandes
    {"RE_BOC8908230339", "DA_CPC92001738"},                 # piballes et truite
    {"RE_BOC8907030115", "DA_CPC92001454"},                 # fricassée de poissons au Sauternes
    {"RE_RBC07034803", "DA_CPC92004292"},                   # faisan aux cèpes
    {"DA_CPC94004408", "RE_RBC07108741", "DA_CPC92011344"}, # cuissot / gigue de chevreuil, terrine
    {"RE_BOC8909260596", "DA_CPC10005123"},                 # lapin aux girolles et au sauterne
    {"RE_BOC8908230347", "DA_CPC93000379", "TV_15684.001"}, # cous farcis (au foie gras), cou de canard farci
    {"DA_CPC93011319", "RE_RBC08005729"},                   # spéciale Didier Oudill
]


def _merge_listed(groups: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """Join the episodes holding notices of one SAME_EPISODE set."""
    for notices in SAME_EPISODE:
        keys = [k for k, g in groups.items() if any(r["notice_path"] in notices for r in g)]
        for k in keys[1:]:
            groups[keys[0]].extend(groups.pop(k))
    return groups


# Some summaries say which broadcast they repeat: "Rediffusion du 20/01/1988" (sic, "Rediffusino"), or "Rediffusion
# du 1er épisode de l'émission (1983)".
RERUN_OF_DATE = re.compile(r"r[ée]diffus\w*\s+(?:de l'[ée]mission\s+)?du\s+(\d{1,2})/(\d{1,2})/(\d{4})", re.I)
RERUN_OF_FIRST = re.compile(r"r[ée]diffus\w*\s+du\s+(?:1er|premier)\s+[ée]pisode", re.I)


def _merge_declared_reruns(groups: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """Move the notices whose summary says which broadcast they repeat into the episode of that broadcast: the
    broadcast of the given date, or the first episode of the series (the earliest one we know)."""
    def group_of_date(date: str, own: str) -> str | None:
        found = {k for k, g in groups.items() if k != own and any(r["date_iso"] == date for r in g)}
        return found.pop() if len(found) == 1 else None

    first = min((k for k, g in groups.items() if _premiere(g)[0]), key=lambda k: _premiere(groups[k]), default=None)
    moves = []
    for key, g in groups.items():
        for r in g:
            text = r.get("resume_documentaire") or ""
            if m := RERUN_OF_DATE.search(text):
                target = group_of_date(f"{m[3]}-{int(m[2]):02d}-{int(m[1]):02d}", key)
            elif RERUN_OF_FIRST.search(text):
                target = first
            else:
                continue
            if target and target != key:
                moves.append((key, target, r))
    for key, target, r in moves:
        groups[key].remove(r)
        groups[target].append(r)
    return {k: g for k, g in groups.items() if g}


def select_episodes(rows: list[dict]) -> list[dict]:
    """One row per episode, by date, described by its first run (reruns fill what it lacks). Adds premiere_date
    (date_incertaine when it is a placeholder), n_diffusions, autres_diffusions (the other notices) and presentateurs."""
    shows = [r for r in rows if is_show(r)]
    aliases = _placeholder_aliases(shows)
    groups: dict[str, list[dict]] = {}
    for r in shows:
        key = episode_key(r["titre_propre"])
        groups.setdefault(aliases.get(key, key), []).append(r)
    out = []
    for g in _merge_declared_reruns(_merge_listed(_merge_reruns(groups))).values():
        premiere, uncertain = _premiere(g)
        if not premiere or premiere > FIRST_RUN_END:
            continue
        best = min((r for r in g if r["date_iso"] == premiere), key=_rank)      # the first run
        filled = {**best, **_filled(best, g, premiere)}
        out.append({**filled, "titre_propre": display_title(filled["titre_propre"]), "duree": _mmss(filled.get("duree_s")),
                    **{k: None for k in VIDEO_FIELDS}, "youtube_duree": None, **_video(g, best), "premiere_date": premiere,
                    "date_incertaine": "oui" if uncertain else "", "n_diffusions": len(g),
                    "type_premiere_diffusion": "régionale" if best["chaine"] in REGIONAL else "nationale",
                    "chaines": " ; ".join(dict.fromkeys(r["chaine"] for r in sorted(g, key=_rank) if r["chaine"])),
                    "derniere_diffusion": max((r["date_iso"] for r in g if r["date_iso"] and not is_placeholder(r)), default=""),
                    "autres_diffusions": " ; ".join(r["notice_path"] for r in sorted(g, key=_rank) if r is not best),
                    "presentateurs": " ; ".join(sorted({n for r in g for n in presenters(r["pre"])}))})
    return sorted(out, key=lambda r: (r["premiere_date"], r["heure_diffusion"] or "", r["notice_path"]))
