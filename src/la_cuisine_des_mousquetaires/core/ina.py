"""Pure knowledge about the INA catalogue: which searches to run, and how to read its HTML pages.

Nothing here touches the network or the database; the pages are passed in as strings.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup, NavigableString, Tag

BASE = "https://catalogue.ina.fr"
NOTICE_PREFIX = BASE + "/doc/TV-RADIO/"

SEARCH_BASE = ("https://catalogue.ina.fr/docListe/TV-RADIO?&base_label=TVNAT%2CRADIO%2CTVSAT%2CPUBTV%2CTVREG"
               "%2CCLIPTV%2CDLDON&sujets_filter=Sujet&bool_operator=AND&nbLignes=500")
TITLE = "La cuisine des mousquetaires"


def search_url(channel: str, exact_title: bool = True) -> str:
    """Result-list URL for the show on one channel (channel names as the catalogue spells them)."""
    q = {"ch": channel}
    if exact_title:
        q["itousti_exact"] = TITLE          # "Titres" field, exact match
    else:
        q["itoustext"] = f'"{TITLE.lower()}"'  # full-text, exact phrase
    return SEARCH_BASE + "&" + urlencode(q)


# Channel names used by the catalogue. "France 3 Occitanie" does not exist there:
# the 2023 version is indexed under the two former stations, Midi Pyrénées and
# Languedoc Roussillon. "France 3" is the national network (1990s reruns and 2020s).
CHANNELS = [
    "France 3 Aquitaine",
    "France 3 Poitou Charente",
    "France 3 Midi Pyrénées",
    "France 3 Languedoc Roussillon",
    "FR3",
    "France 3",
]

DEFAULT_SEARCHES = (
    # 1. Exact collection title, one search per channel: the programme notices themselves.
    [(f"titre exact - {c}", search_url(c)) for c in CHANNELS]
    # 2. Full-text phrase on three channels, for notices filed under another collection:
    #    the 1983 Poitou-Charentes broadcasts (collection "Magazine"), FR3 "Les Cuisines
    #    de France" (1991-1992) and news reports about the show on France 3 Aquitaine.
    #    Full text is not used for the Occitanie stations, where it mostly returns trailers.
    + [(f"texte - {c}", search_url(c, exact_title=False))
       for c in ("France 3 Poitou Charente", "FR3", "France 3 Aquitaine")]
)

# Fields whose value is a list separated by " ; " on the page.
LIST_FIELDS = {"GEN", "DE", "DES", "GENRE", "THEMAT", "DISP"}

LIST_COLUMNS = [
    "chaine", "date_diffusion", "heure_diffusion", "duree",
    "titre_propre", "titre_collection", "titre_programme", "genre",
]


def _text(node: Tag | None) -> str:
    """Text of a cell, with <br> as newlines and whitespace normalised per line."""
    if node is None:
        return ""
    parts: list[str] = []
    for el in node.descendants:
        if isinstance(el, NavigableString):
            parts.append(str(el))
        elif isinstance(el, Tag) and el.name == "br":
            parts.append("\n")
    lines = [re.sub(r"[ \t\r\f\v ]+", " ", l).strip() for l in "".join(parts).split("\n")]
    # drop leading/trailing empty lines, keep inner structure
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def notice_path_from_href(href: str) -> str | None:
    m = re.search(r"/doc/TV-RADIO/([^/?#]+)", href or "")
    return m.group(1) if m else None


@dataclass
class ListPage:
    total: int | None
    rows: list[dict]
    form_action: str | None = None   # pager form (name="documentSelection")
    form_fields: dict | None = None


def parse_list_page(html: str) -> ListPage:
    soup = BeautifulSoup(html, "html.parser")
    total = None
    m = re.search(r"Enregistrements\s+\d+\s+à\s+\d+\s+sur\s+(\d+)", soup.get_text(" "))
    if m:
        total = int(m.group(1))
    rows: list[dict] = []
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td", recursive=False)
        if len(tds) < 9 or "indice" not in (tds[0].get("class") or []):
            continue
        rang = _text(tds[0])
        if not rang.isdigit():
            continue
        a = tds[5].find("a", href=True)
        href = a["href"] if a else ""
        row = {"rang": int(rang), "href": href, "notice_path": notice_path_from_href(href)}
        for name, td in zip(LIST_COLUMNS, tds[1:9]):
            row[name] = _text(td) or None
        rows.append(row)
    form = soup.find("form", attrs={"name": "documentSelection"})
    action = fields = None
    if form is not None:
        action = form.get("action")
        fields = {str(i["name"]): str(i.get("value", "")) for i in form.find_all("input") if i.get("name")}
    return ListPage(total, rows, action, fields)


@dataclass
class Field:
    position: int
    code: str | None
    label: str
    value_text: str
    value_html: str


def parse_notice_page(html: str) -> list[Field]:
    soup = BeautifulSoup(html, "html.parser")
    container = soup.select_one("#result-tableau-1 table") or soup
    fields: list[Field] = []
    for tr in container.find_all("tr"):
        lab = tr.find("td", class_="label_champs_form")
        val = tr.find("td", class_="val_champs_form")
        if lab is None or val is None:
            continue
        fields.append(Field(
            position=len(fields) + 1,
            code=val.get("id"),
            label=_text(lab),
            value_text=_text(val),
            value_html=val.decode_contents().strip(),
        ))
    return fields


def split_items(field: Field) -> list[dict]:
    if field.code not in LIST_FIELDS:
        return []
    items = [x.strip() for x in re.split(r"\s+;\s+", field.value_text.replace("\n", " ")) if x.strip()]
    out = []
    for i, v in enumerate(items, 1):
        role = name = None
        if field.code == "GEN" and "," in v:
            role, name = (p.strip() for p in v.split(",", 1))
        out.append({"item_index": i, "value": v, "role_code": role, "name": name})
    return out


def with_param(url: str, **params) -> str:
    parts = urlsplit(url)
    q = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k not in params]
    q += [(k, str(v)) for k, v in params.items()]
    return urlunsplit(parts._replace(query=urlencode(q, safe=",")))
