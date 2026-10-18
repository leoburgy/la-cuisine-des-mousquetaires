"""Pure reading of YouTube video metadata (the dict returned by yt-dlp)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

WATCH_URL = "https://www.youtube.com/watch?v="

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


def iso_upload_date(s: str | None) -> str | None:
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if s and len(s) == 8 else None


@dataclass(frozen=True)
class VideoRecord:
    video_id: str
    url: str
    title: str | None
    description: str
    duration_s: int | None
    upload_date: str | None
    view_count: int | None
    is_mousquetaires: bool
    broadcast_date: str | None
    broadcast_channel: str | None


def video_record(info: dict) -> VideoRecord:
    description = info.get("description") or ""
    is_show = bool(SHOW_RE.search(description) or SHOW_RE.search(info.get("title") or ""))
    date, channel = parse_broadcast(description) if is_show else (None, None)
    return VideoRecord(
        video_id=info["id"], url=WATCH_URL + info["id"], title=info.get("title"), description=description,
        duration_s=int(info["duration"]) if info.get("duration") is not None else None,
        upload_date=iso_upload_date(info.get("upload_date")), view_count=info.get("view_count"),
        is_mousquetaires=is_show, broadcast_date=date, broadcast_channel=channel)
