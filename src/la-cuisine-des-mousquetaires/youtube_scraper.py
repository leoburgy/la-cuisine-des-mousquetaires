"""Scrape the YouTube channel INA Les Recettes Vintage into the SQLite database of ina_scraper.py.

Every video of the channel is stored in `youtube_video` (so it is only fetched once). Videos whose
description mentions "La Cuisine des mousquetaires" get their broadcast date and channel parsed from
the description line, e.g. "La Cuisine Des Mousquetaires | FR3 | 19/06/1992". The view
`v_youtube_episode` lists those videos with an ISO `date_iso`, ready to join on `v_notice.date_iso`.

Usage:
    python youtube_scraper.py --db ina_catalogue.sqlite
    python youtube_scraper.py --db ina_catalogue.sqlite --refresh     # re-fetch stored videos
    python youtube_scraper.py --db ina_catalogue.sqlite --limit 20    # quick test
"""
from __future__ import annotations

import argparse
import logging
import re
import sqlite3
import time
from datetime import datetime, timezone

import yt_dlp

CHANNEL_URL = "https://www.youtube.com/@InaLesRecettesVintage/videos"
WATCH_URL = "https://www.youtube.com/watch?v="

log = logging.getLogger("youtube")

SCHEMA = """
CREATE TABLE IF NOT EXISTS youtube_video (
    video_id           TEXT PRIMARY KEY,
    url                TEXT NOT NULL,
    title              TEXT,
    description        TEXT,
    duration_s         INTEGER,               -- video length in seconds
    upload_date        TEXT,                  -- ISO date the video was posted
    view_count         INTEGER,
    fetched_at         TEXT NOT NULL,
    is_mousquetaires   INTEGER NOT NULL,      -- description mentions the show
    broadcast_date     TEXT,                  -- ISO date parsed from the description
    broadcast_channel  TEXT                   -- TV channel parsed from the description (FR3...)
);
CREATE INDEX IF NOT EXISTS ix_youtube_broadcast ON youtube_video(broadcast_date);

-- Episodes of the show on YouTube; join with v_notice on date_iso.
DROP VIEW IF EXISTS v_youtube_episode;
CREATE VIEW v_youtube_episode AS
SELECT video_id, url, title, duration_s,
       printf('%d:%02d:%02d', duration_s / 3600, duration_s % 3600 / 60, duration_s % 60) AS duree,
       broadcast_date AS date_iso, broadcast_channel AS chaine, upload_date
FROM youtube_video
WHERE is_mousquetaires = 1;
"""

SHOW_RE = re.compile(r"cuisine\s+des\s+mousquetaires", re.I)
DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")


def parse_broadcast(description: str) -> tuple[str | None, str | None]:
    """Return (ISO date, channel) from the first description line that names the show and has a date."""
    for line in description.splitlines():
        if not SHOW_RE.search(line):
            continue
        m = DATE_RE.search(line)
        if not m:
            continue
        d, mo, y = map(int, m.groups())
        try:
            iso = datetime(y, mo, d).date().isoformat()
        except ValueError:
            continue
        parts = [p.strip() for p in line.split("|")]
        channel = next((p for p in parts if p and not SHOW_RE.search(p) and not DATE_RE.search(p)), None)
        return iso, channel
    # mentioned but no usable date on the same line: take the first date of the description
    m = DATE_RE.search(description)
    if m:
        d, mo, y = map(int, m.groups())
        try:
            return datetime(y, mo, d).date().isoformat(), None
        except ValueError:
            pass
    return None, None


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def iso_upload_date(s: str | None) -> str | None:
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if s and len(s) == 8 else None


def list_video_ids(url: str, limit: int | None) -> list[str]:
    opts = {"extract_flat": True, "quiet": True, "skip_download": True}
    if limit:
        opts["playlistend"] = limit
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return [e["id"] for e in info.get("entries", []) if e and e.get("id")]


def store_video(conn: sqlite3.Connection, info: dict) -> None:
    description = info.get("description") or ""
    is_show = int(bool(SHOW_RE.search(description) or SHOW_RE.search(info.get("title") or "")))
    date, channel = parse_broadcast(description) if is_show else (None, None)
    conn.execute(
        "INSERT OR REPLACE INTO youtube_video(video_id,url,title,description,duration_s,upload_date,view_count,"
        "fetched_at,is_mousquetaires,broadcast_date,broadcast_channel) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (info["id"], WATCH_URL + info["id"], info.get("title"), description,
         int(info["duration"]) if info.get("duration") is not None else None,
         iso_upload_date(info.get("upload_date")), info.get("view_count"), utcnow(), is_show, date, channel))
    conn.commit()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="ina_catalogue.sqlite", help="SQLite file (created if missing)")
    ap.add_argument("--channel", default=CHANNEL_URL, help="channel videos URL")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between video requests (default 1.0)")
    ap.add_argument("--limit", type=int, help="only look at the N most recent videos")
    ap.add_argument("--refresh", action="store_true", help="re-fetch videos already stored")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")

    conn = sqlite3.connect(args.db)
    conn.executescript(SCHEMA)

    ids = list_video_ids(args.channel, args.limit)
    known = {r[0] for r in conn.execute("SELECT video_id FROM youtube_video")}
    todo = [i for i in ids if args.refresh or i not in known]
    log.info("%d videos on the channel, %d to fetch", len(ids), len(todo))

    opts = {"quiet": True, "no_warnings": True, "skip_download": True,
            "extractor_args": {"youtube": {"lang": ["fr"]}}}
    failed = 0
    with yt_dlp.YoutubeDL(opts) as ydl:
        for n, vid in enumerate(todo, 1):
            try:
                info = ydl.extract_info(WATCH_URL + vid, download=False)
            except yt_dlp.utils.DownloadError as e:
                log.warning("%s: %s", vid, str(e).splitlines()[-1])
                failed += 1
                continue
            store_video(conn, info)
            log.debug("%d/%d %s %s", n, len(todo), vid, info.get("title"))
            if n % 50 == 0:
                log.info("%d/%d", n, len(todo))
            time.sleep(args.delay)

    shows, dated = conn.execute(
        "SELECT COUNT(*), COUNT(broadcast_date) FROM youtube_video WHERE is_mousquetaires = 1").fetchone()
    log.info("done: %d failed; %d show videos stored, %d with a broadcast date", failed, shows, dated)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
