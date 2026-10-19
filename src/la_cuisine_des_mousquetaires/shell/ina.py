"""Scrape the INA "Catalogue des fonds" (catalogue.ina.fr) into SQLite, with tables that mirror the source pages.

Source-aligned means:
  * one table per kind of source page (search result lists, notice pages);
  * every notice field is stored as it appears on the page, in page order,
    with the field code used by the site (the id of the value cell: NO, TI,
    TICOL, CH, DATDIF, HEURE, DUREE, GENRE, GEN, RES, SOM...) and its label;
  * nothing is interpreted, merged or corrected. Convenience views add ISO
    dates and a one-row-per-notice layout, but the base tables stay raw.

Run it again at any time: searches are re-recorded as new runs, and notices
already stored are skipped unless refresh is set.
"""
from __future__ import annotations

import hashlib
import logging
import sqlite3
import time
import zlib
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import requests

from ..core.ina import (DEFAULT_SEARCHES, NOTICE_PREFIX, keep_result_row, parse_list_page, parse_notice_page,
                        split_items, with_param)
from .db import INA_SCHEMA, connect, utcnow

USER_AGENT = "ina-catalogue-scraper/1.0 (research use; contact: set --contact)"

log = logging.getLogger("ina")


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
    wanted = [r["notice_path"] for r in rows if r["notice_path"] and keep_result_row(r)]
    log.info("search %r: %s rows (site reports %s), %d to fetch", label, len(rows), page.total, len(wanted))
    return run_id, wanted


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


def scrape(db: str | Path, searches: list[tuple[str | None, str]] | None = None, page_size: int = 500,
           delay: float = 1.0, refresh: bool = False, searches_only: bool = False, keep_html: bool = True,
           contact: str | None = None) -> None:
    conn = connect(db)
    conn.executescript(INA_SCHEMA)
    fetcher = Fetcher(conn, delay, contact)
    paths: dict[str, int] = {}
    for label, url in searches or DEFAULT_SEARCHES:
        run_id, found = run_search(conn, fetcher, label or url, url, page_size)
        for p in found:
            paths.setdefault(p, run_id)
    if not searches_only:
        fetch_notices(conn, fetcher, paths, refresh, keep_html)
    n = conn.execute("SELECT COUNT(*) FROM notice WHERE http_status=200").fetchone()[0]
    f = conn.execute("SELECT COUNT(*) FROM notice_field").fetchone()[0]
    log.info("done: %d notices, %d fields in %s", n, f, db)
