"""Scrape the YouTube channel INA Les Recettes Vintage into the `youtube_video` table.

Every video of the channel is stored (so it is only fetched once). Videos whose description mentions
"La Cuisine des mousquetaires" get their broadcast date and channel parsed from the description line,
e.g. "La Cuisine Des Mousquetaires | FR3 | 19/06/1992". The view `v_youtube_episode` lists those videos with
an ISO `date_iso`, ready to join on `v_notice.date_iso`.
"""
from __future__ import annotations

import logging
import re
import sqlite3
import time
from pathlib import Path

import yt_dlp

from ..core.youtube import WATCH_URL, video_record
from .db import YOUTUBE_SCHEMA, connect, utcnow

CHANNEL_URL = "https://www.youtube.com/@InaLesRecettesVintage/videos"

UNAVAILABLE_RE = re.compile(r"non disponible|unavailable", re.I)

log = logging.getLogger("youtube")


def list_video_ids(url: str, limit: int | None) -> list[str]:
    opts = {"extract_flat": True, "quiet": True, "skip_download": True}
    if limit:
        opts["playlistend"] = limit
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return [e["id"] for e in info.get("entries", []) if e and e.get("id")]


def extract_with_retry(ydl: yt_dlp.YoutubeDL, vid: str, delay: float, retries: int = 3) -> dict:
    """extract_info, trying again after delay*4 seconds per attempt when YouTube says the video is unavailable
    (often transient on a channel crawl, as with the INA requests)."""
    for attempt in range(1, retries + 1):
        try:
            return ydl.extract_info(WATCH_URL + vid, download=False)
        except yt_dlp.utils.DownloadError as e:
            msg = str(e).splitlines()[-1]
            if attempt == retries or not UNAVAILABLE_RE.search(msg):
                raise
            log.debug("%s: %s, retry %d in %.0fs", vid, msg, attempt, delay * 4)
            time.sleep(delay * 4)
    raise RuntimeError("unreachable")


def store_video(conn: sqlite3.Connection, info: dict) -> None:
    v = video_record(info)
    conn.execute(
        "INSERT OR REPLACE INTO youtube_video(video_id,url,title,description,duration_s,upload_date,view_count,"
        "fetched_at,is_mousquetaires,broadcast_date,broadcast_channel) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (v.video_id, v.url, v.title, v.description, v.duration_s, v.upload_date, v.view_count, utcnow(),
         int(v.is_mousquetaires), v.broadcast_date, v.broadcast_channel))
    conn.commit()


def scrape(db: str | Path, channel: str = CHANNEL_URL, delay: float = 1.0, limit: int | None = None,
           refresh: bool = False) -> None:
    conn = connect(db)
    conn.executescript(YOUTUBE_SCHEMA)

    ids = list_video_ids(channel, limit)
    known = {r[0] for r in conn.execute("SELECT video_id FROM youtube_video")}
    todo = [i for i in ids if refresh or i not in known]
    log.info("%d videos on the channel, %d to fetch", len(ids), len(todo))

    opts = {"quiet": True, "no_warnings": True, "skip_download": True,
            "extractor_args": {"youtube": {"lang": ["fr"]}}}
    failed = 0
    with yt_dlp.YoutubeDL(opts) as ydl:
        for n, vid in enumerate(todo, 1):
            try:
                info = extract_with_retry(ydl, vid, delay)
            except yt_dlp.utils.DownloadError as e:
                log.warning("%s: %s", vid, str(e).splitlines()[-1])
                failed += 1
                continue
            store_video(conn, info)
            log.debug("%d/%d %s %s", n, len(todo), vid, info.get("title"))
            if n % 50 == 0:
                log.info("%d/%d", n, len(todo))
            time.sleep(delay)

    shows, dated = conn.execute(
        "SELECT COUNT(*), COUNT(broadcast_date) FROM youtube_video WHERE is_mousquetaires = 1").fetchone()
    log.info("done: %d failed; %d show videos stored, %d with a broadcast date", failed, shows, dated)
