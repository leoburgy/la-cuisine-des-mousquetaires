#!/usr/bin/env python3
"""
Scrape the INA "Catalogue des fonds" (catalogue.ina.fr) and store the results
in a SQLite database that mirrors the structure of the source pages.

Source-aligned means:
  * one table per kind of source page (search result lists, notice pages);
  * every notice field is stored as it appears on the page, in page order,
    with the field code used by the site (the id of the value cell: NO, TI,
    TICOL, CH, DATDIF, HEURE, DUREE, GENRE, GEN, RES, SOM...) and its label;
  * nothing is interpreted, merged or corrected. Convenience views add ISO
    dates and a one-row-per-notice layout, but the base tables stay raw.

Usage
-----
    pip install requests beautifulsoup4
    python ina_scraper.py --db ina.sqlite                 # default searches
    python ina_scraper.py --db ina.sqlite --search "URL" --label "my search"
    python ina_scraper.py --db ina.sqlite --refresh       # re-fetch notices

Run it again at any time: searches are re-recorded as new runs, and notices
already stored are skipped unless --refresh is given.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import logging
import re
import sqlite3
import sys
import time
import zlib
from dataclasses import dataclass
from typing import Callable, Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

BASE = "https://catalogue.ina.fr"
NOTICE_PREFIX = BASE + "/doc/TV-RADIO/"
USER_AGENT = "ina-catalogue-scraper/1.0 (research use; contact: set --contact)"

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

log = logging.getLogger("ina")

SCHEMA = """
PRAGMA foreign_keys = ON;

-- One row per execution of a search URL.
CREATE TABLE IF NOT EXISTS search_run (
    run_id          INTEGER PRIMARY KEY,
    label           TEXT,
    url             TEXT NOT NULL,          -- URL as given
    fetched_url     TEXT NOT NULL,          -- URL actually requested (nbLignes changed)
    run_at          TEXT NOT NULL,          -- UTC ISO timestamp
    total_reported  INTEGER,                -- "Enregistrements 1 à N sur TOTAL"
    rows_parsed     INTEGER
);

-- One row per line of the result table, exactly as displayed.
CREATE TABLE IF NOT EXISTS search_result (
    run_id            INTEGER NOT NULL REFERENCES search_run(run_id),
    rang              INTEGER NOT NULL,     -- first column of the table
    notice_path       TEXT,                 -- e.g. RE_RBC07022460
    chaine            TEXT,                 -- "Chaîne de diffusion"
    date_diffusion    TEXT,                 -- "Date de diffusion" (dd/mm/yyyy, raw)
    heure_diffusion   TEXT,                 -- "Heure de diffusion" (raw)
    duree             TEXT,                 -- "Durée" (raw)
    titre_propre      TEXT,                 -- "Titre propre"
    titre_collection  TEXT,                 -- "Titre collection"
    titre_programme   TEXT,                 -- "Titre programme"
    genre             TEXT,                 -- "Genre"
    href              TEXT,                 -- link as found (with ?rang=)
    PRIMARY KEY (run_id, rang)
);

-- One row per notice page.
CREATE TABLE IF NOT EXISTS notice (
    notice_path   TEXT PRIMARY KEY,         -- e.g. RE_RBC07022460, RG_7033612.001
    notice_id     TEXT,                     -- value of field NO ("ID Notice")
    url           TEXT NOT NULL,
    fetched_at    TEXT NOT NULL,
    http_status   INTEGER,
    html_sha256   TEXT,
    html_zlib     BLOB                      -- raw page, zlib-compressed (optional)
);

-- One row per field of a notice, in page order.
CREATE TABLE IF NOT EXISTS notice_field (
    notice_path   TEXT NOT NULL REFERENCES notice(notice_path) ON DELETE CASCADE,
    position      INTEGER NOT NULL,         -- order on the page (1-based)
    code          TEXT,                     -- id of the value cell (TI, DATDIF, GEN...)
    label         TEXT NOT NULL,            -- label cell text ("Titre propre"...)
    value_text    TEXT,                     -- text, <br> kept as newlines
    value_html    TEXT,                     -- inner HTML of the value cell
    PRIMARY KEY (notice_path, position)
);

-- List-valued fields split on " ; " (Générique, Descripteurs, Genre...).
-- For Générique (GEN) the part before the first comma is the role code
-- shown by the site (REA, PRE, JOU...), the rest is the name.
CREATE TABLE IF NOT EXISTS notice_field_item (
    notice_path   TEXT NOT NULL,
    position      INTEGER NOT NULL,         -- position of the field
    item_index    INTEGER NOT NULL,         -- order inside the field (1-based)
    value         TEXT NOT NULL,
    role_code     TEXT,                     -- GEN only
    name          TEXT,                     -- GEN only
    PRIMARY KEY (notice_path, position, item_index),
    FOREIGN KEY (notice_path, position) REFERENCES notice_field(notice_path, position) ON DELETE CASCADE
);

-- A notice can be found by several searches: search_result keeps every hit, notice keeps one copy.
-- Search results <-> notices.
CREATE INDEX IF NOT EXISTS ix_result_notice ON search_result(notice_path);
CREATE INDEX IF NOT EXISTS ix_field_code ON notice_field(code);

CREATE TABLE IF NOT EXISTS fetch_log (
    fetched_at   TEXT NOT NULL,
    url          TEXT NOT NULL,
    http_status  INTEGER,
    bytes        INTEGER,
    error        TEXT,
    run_id       INTEGER REFERENCES search_run(run_id)   -- search that triggered the request
);

-- Convenience view: one row per notice with the most common fields.
-- Derived only by pivoting notice_field; dates converted to ISO.
DROP VIEW IF EXISTS v_notice;
CREATE VIEW v_notice AS
SELECT
    n.notice_path,
    n.notice_id,
    n.url,
    MAX(CASE WHEN f.code = 'TI'       THEN f.value_text END) AS titre_propre,
    MAX(CASE WHEN f.code = 'TICOL'    THEN f.value_text END) AS titre_collection,
    MAX(CASE WHEN f.label = 'Titre programme' THEN f.value_text END) AS titre_programme,
    MAX(CASE WHEN f.code = 'CH'       THEN f.value_text END) AS chaine,
    MAX(CASE WHEN f.code = 'DATDIF'   THEN f.value_text END) AS date_diffusion,
    MAX(CASE WHEN f.code = 'DATDIF'   THEN substr(f.value_text,7,4)||'-'||substr(f.value_text,4,2)||'-'||substr(f.value_text,1,2) END) AS date_iso,
    MAX(CASE WHEN f.code = 'JOUR'     THEN f.value_text END) AS jour,
    MAX(CASE WHEN f.code = 'STADIF'   THEN f.value_text END) AS statut_diffusion,
    MAX(CASE WHEN f.code = 'HEURE'    THEN f.value_text END) AS heure_diffusion,
    MAX(CASE WHEN f.code = 'HEUREFIN' THEN f.value_text END) AS heure_fin,
    MAX(CASE WHEN f.code = 'DUREE'    THEN f.value_text END) AS duree,
    MAX(CASE WHEN f.code = 'GENRE'    THEN f.value_text END) AS genre,
    MAX(CASE WHEN f.code = 'TYPDESCR' THEN f.value_text END) AS type_description,
    MAX(CASE WHEN f.code = 'GEN'      THEN f.value_text END) AS generique,
    MAX(CASE WHEN f.code = 'RES'      THEN f.value_text END) AS resume_documentaire,
    MAX(CASE WHEN f.label = 'Résumé producteur' THEN f.value_text END) AS resume_producteur,
    MAX(CASE WHEN f.code = 'SOM'      THEN f.value_text END) AS sommaire,
    MAX(CASE WHEN f.code = 'DE'       THEN f.value_text END) AS descripteurs,
    MAX(CASE WHEN f.code = 'DES'      THEN f.value_text END) AS descripteurs_secondaires,
    MAX(CASE WHEN f.code = 'PROD'     THEN f.value_text END) AS producteurs,
    MAX(CASE WHEN f.code = 'BASE'     THEN f.value_text END) AS base
FROM notice n
LEFT JOIN notice_field f ON f.notice_path = n.notice_path
GROUP BY n.notice_path;

-- Credits: one row per person and role.
DROP VIEW IF EXISTS v_generique;
CREATE VIEW v_generique AS
SELECT i.notice_path, i.item_index, i.role_code, i.name
FROM notice_field_item i
JOIN notice_field f ON f.notice_path = i.notice_path AND f.position = i.position
WHERE f.code = 'GEN';

-- Latest result list of each search, with ISO dates.
DROP VIEW IF EXISTS v_search_result_latest;
CREATE VIEW v_search_result_latest AS
SELECT r.*, s.label, s.url AS search_url,
       substr(r.date_diffusion,7,4)||'-'||substr(r.date_diffusion,4,2)||'-'||substr(r.date_diffusion,1,2) AS date_iso
FROM search_result r
JOIN search_run s ON s.run_id = r.run_id
WHERE s.run_id = (SELECT MAX(s2.run_id) FROM search_run s2 WHERE s2.url = s.url);
"""

LIST_COLUMNS = [
    "chaine", "date_diffusion", "heure_diffusion", "duree",
    "titre_propre", "titre_collection", "titre_programme", "genre",
]


# --------------------------------------------------------------------------- parsing

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


# --------------------------------------------------------------------------- fetching

class Fetcher:
    def __init__(self, conn: sqlite3.Connection, delay: float, contact: str | None, timeout: float = 30):
        self.conn = conn
        self.delay = delay
        self.timeout = timeout
        self.session = requests.Session()
        ua = USER_AGENT.replace("set --contact", contact) if contact else USER_AGENT
        self.session.headers.update({"User-Agent": ua, "Accept-Language": "fr-FR,fr;q=0.9"})
        self._last = 0.0
        self.run_id: int | None = None      # set by the pipeline before each batch of requests

    def get(self, url: str, retries: int = 3) -> tuple[int, str]:
        return self.request("GET", url, None, retries)

    def post(self, url: str, data: dict, retries: int = 3) -> tuple[int, str]:
        return self.request("POST", url, data, retries)

    def request(self, method: str, url: str, data: dict | None, retries: int = 3) -> tuple[int, str]:
        for attempt in range(1, retries + 1):
            wait = self.delay - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            now = utcnow()
            try:
                r = self.session.request(method, url, data=data, timeout=self.timeout)
                r.encoding = r.encoding or "utf-8"
                logged = url if data is None else f"{url} [POST page={data.get('page')}]"
                self.conn.execute(
                    "INSERT INTO fetch_log(fetched_at,url,http_status,bytes,error,run_id) VALUES (?,?,?,?,NULL,?)",
                    (now, logged, r.status_code, len(r.content), self.run_id))
                if r.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                    log.warning("HTTP %s on %s, retrying", r.status_code, url)
                    time.sleep(self.delay * 4 * attempt)
                    continue
                return r.status_code, r.text
            except requests.RequestException as e:
                self.conn.execute(
                    "INSERT INTO fetch_log(fetched_at,url,http_status,bytes,error,run_id) VALUES (?,?,NULL,NULL,?,?)",
                    (now, url, str(e), self.run_id))
                if attempt == retries:
                    raise
                log.warning("%s on %s, retrying", e, url)
                time.sleep(self.delay * 4 * attempt)
        raise RuntimeError("unreachable")


def utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def with_param(url: str, **params) -> bytes:
    parts = urlsplit(url)
    q = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k not in params]
    q += [(k, str(v)) for k, v in params.items()]
    return urlunsplit(parts._replace(query=urlencode(q, safe=",")))


# --------------------------------------------------------------------------- pipeline

def run_search(conn, fetcher: Fetcher, label: str, url: str, page_size: int) -> tuple[int, list[str]]:
    fetched_url = with_param(url, nbLignes=page_size)
    # The run row is created first so that fetch_log rows (including failures) can reference it.
    run_id = conn.execute(
        "INSERT INTO search_run(label,url,fetched_url,run_at) VALUES (?,?,?,?)",
        (label, url, fetched_url, utcnow())).lastrowid
    fetcher.run_id = run_id
    status, html = fetcher.get(fetched_url)
    if status != 200:
        raise RuntimeError(f"search returned HTTP {status}: {fetched_url}")
    page = parse_list_page(html)
    rows = list(page.rows)
    # nbLignes is capped at 500 by the site. Further pages are obtained the way the
    # site does it: by POSTing its hidden pager form with page=2, 3...
    p = 2
    while page.total and len(rows) < page.total:
        if not page.form_fields:
            log.warning("search %r: no pager form, %d of %d rows", label, len(rows), page.total)
            break
        data = dict(page.form_fields, page=str(p), nbLignes=str(page_size))
        refine = dict(parse_qsl(urlsplit(fetched_url).query)).get("refine")
        if refine and not data.get("refine"):
            data["refine"] = refine
        st, h = fetcher.post(page.form_action or fetched_url, data)
        nxt = parse_list_page(h).rows if st == 200 else []
        new = [r for r in nxt if r["rang"] > rows[-1]["rang"]]
        if not new:
            log.warning("search %r: page %d returned nothing new; %d of %d rows", label, p, len(rows), page.total)
            break
        rows += new
        p += 1
    if page.total and len(rows) != page.total:
        log.warning("search %r: %d rows parsed, site reports %d", label, len(rows), page.total)
    conn.execute("UPDATE search_run SET total_reported=?, rows_parsed=? WHERE run_id=?",
                 (page.total, len(rows), run_id))
    conn.executemany(
        "INSERT INTO search_result(run_id,rang,notice_path,chaine,date_diffusion,heure_diffusion,duree,"
        "titre_propre,titre_collection,titre_programme,genre,href) VALUES "
        "(:run_id,:rang,:notice_path,:chaine,:date_diffusion,:heure_diffusion,:duree,"
        ":titre_propre,:titre_collection,:titre_programme,:genre,:href)",
        [dict(r, run_id=run_id) for r in rows])
    conn.commit()
    log.info("search %r: %s rows (site reports %s)", label, len(rows), page.total)
    return run_id, [r["notice_path"] for r in rows if r["notice_path"]]


def store_notice(conn, path: str, url: str, status: int, html: str, keep_html: bool) -> int:
    fields = parse_notice_page(html) if status == 200 else []
    notice_id = next((f.value_text for f in fields if f.code == "NO"), None)
    conn.execute("DELETE FROM notice WHERE notice_path = ?", (path,))
    conn.execute(
        "INSERT INTO notice(notice_path,notice_id,url,fetched_at,http_status,html_sha256,html_zlib) VALUES (?,?,?,?,?,?,?)",
        (path, notice_id, url, utcnow(), status, hashlib.sha256(html.encode()).hexdigest(),
         zlib.compress(html.encode()) if keep_html else None))
    for f in fields:
        conn.execute(
            "INSERT INTO notice_field(notice_path,position,code,label,value_text,value_html) VALUES (?,?,?,?,?,?)",
            (path, f.position, f.code, f.label, f.value_text, f.value_html))
        for it in split_items(f):
            conn.execute(
                "INSERT INTO notice_field_item(notice_path,position,item_index,value,role_code,name) VALUES (?,?,?,?,?,?)",
                (path, f.position, it["item_index"], it["value"], it["role_code"], it["name"]))
    return len(fields)


def fetch_notices(conn, fetcher: Fetcher, paths: dict[str, int], refresh: bool, keep_html: bool) -> None:
    """paths maps each notice_path to the run_id of the first search that returned it."""
    todo = list(paths)
    if not refresh:
        have = {r[0] for r in conn.execute("SELECT notice_path FROM notice WHERE http_status = 200")}
        todo = [p for p in todo if p not in have]
    log.info("%d notices to fetch", len(todo))
    for i, path in enumerate(todo, 1):
        url = NOTICE_PREFIX + path
        fetcher.run_id = paths[path]
        try:
            status, html = fetcher.get(url)
        except Exception as e:  # keep going, the failure is in fetch_log
            log.error("notice %s failed: %s", path, e)
            continue
        n = store_notice(conn, path, url, status, html, keep_html)
        if status != 200 or n == 0:
            log.warning("notice %s: HTTP %s, %d fields", path, status, n)
        if i % 25 == 0:
            conn.commit()
            log.info("%d/%d notices", i, len(todo))
    conn.commit()


def open_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="ina_catalogue.sqlite", help="SQLite file (created if missing)")
    ap.add_argument("--search", action="append", default=[], help="search result URL (repeatable)")
    ap.add_argument("--label", action="append", default=[], help="label for each --search, in order")
    ap.add_argument("--page-size", type=int, default=500, help="nbLignes used for result lists (default 500)")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between requests (default 1.0)")
    ap.add_argument("--refresh", action="store_true", help="re-fetch notices already stored")
    ap.add_argument("--searches-only", action="store_true", help="record result lists, do not fetch notices")
    ap.add_argument("--no-html", action="store_true", help="do not keep the raw notice HTML")
    ap.add_argument("--contact", help="e-mail or URL added to the User-Agent")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO, format="%(levelname)s %(message)s")

    searches = list(zip(a.label + [None] * len(a.search), a.search)) if a.search else DEFAULT_SEARCHES
    conn = open_db(a.db)
    fetcher = Fetcher(conn, a.delay, a.contact)
    paths: dict[str, int] = {}
    for label, url in searches:
        run_id, found = run_search(conn, fetcher, label or url, url, a.page_size)
        for p in found:
            paths.setdefault(p, run_id)
    if not a.searches_only:
        fetch_notices(conn, fetcher, paths, a.refresh, keep_html=not a.no_html)
    n = conn.execute("SELECT COUNT(*) FROM notice WHERE http_status=200").fetchone()[0]
    f = conn.execute("SELECT COUNT(*) FROM notice_field").fetchone()[0]
    log.info("done: %d notices, %d fields in %s", n, f, a.db)
    return 0


if __name__ == "__main__":
    sys.exit(main())
