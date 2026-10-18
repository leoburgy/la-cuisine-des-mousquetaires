"""Run the matcher: load videos, notices and human overrides, store the result in `youtube_match`.

The overrides CSV (default data/youtube_match_overrides.csv) is only ever rewritten by --confirm / --reject,
never by the matcher, so decisions survive re-runs and a rebuilt database. A row `video_id,notice_path,note`
forces that pair (confidence `manual`); an empty notice_path says the video has no notice.
"""
from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from ..core.matching import DEFAULT_MAX_DAYS, DEFAULT_MIN_SCORE, check_overrides, match, with_override
from ..core.models import Match, Notice, Override, Video
from .db import MATCH_SCHEMA, connect

OVERRIDE_FIELDS = ["video_id", "notice_path", "note"]


def load_overrides(path: Path) -> dict[str, Override]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as f:
        overrides = {r["video_id"]: Override(r["notice_path"] or None, r["note"] or "")
                     for r in csv.DictReader(f) if r.get("video_id")}
    try:
        check_overrides(overrides)
    except ValueError as e:
        raise ValueError(f"{path}: {e}") from e
    return overrides


def save_overrides(path: Path, overrides: dict[str, Override]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, OVERRIDE_FIELDS)
        w.writeheader()
        for vid, o in sorted(overrides.items()):
            w.writerow({"video_id": vid, "notice_path": o.notice_path or "", "note": o.note})


def load_videos(conn: sqlite3.Connection) -> list[Video]:
    return [Video(r["video_id"], r["title"], r["description"], bool(r["is_mousquetaires"]), r["broadcast_date"])
            for r in conn.execute("SELECT * FROM youtube_video")]


def load_notices(conn: sqlite3.Connection) -> list[Notice]:
    return [Notice(r["notice_path"], r["date_iso"], r["titre_propre"], r["resume_documentaire"],
                   r["resume_producteur"], r["sommaire"], r["descripteurs"])
            for r in conn.execute("SELECT * FROM v_notice")]


def save_matches(conn: sqlite3.Connection, matches: list[Match]) -> None:
    conn.execute("DELETE FROM youtube_match")
    conn.executemany("INSERT INTO youtube_match VALUES (?,?,?,?,?)",
                     [(m.notice_path, m.video_id, m.score, m.delta, m.confidence) for m in matches])
    conn.commit()


def report(conn: sqlite3.Connection) -> None:
    print("== matched (lowest score first) ==")
    for r in conn.execute("""SELECT m.confidence, round(m.score,2) s, m.date_delta d, substr(v.title,1,45) yt,
                                    substr(n.titre_propre,1,45) ina, n.chaine
                             FROM youtube_match m JOIN youtube_video v USING(video_id)
                             JOIN v_notice n USING(notice_path) ORDER BY m.score"""):
        print(" | ".join(str(x) for x in r))
    print("\n== videos without a notice ==")
    for r in conn.execute("""SELECT v.broadcast_date, substr(v.title,1,60) FROM youtube_video v
                             WHERE v.is_mousquetaires = 1 AND v.video_id NOT IN (SELECT video_id FROM youtube_match)
                             ORDER BY 1"""):
        print(" | ".join(str(x) for x in r))


def run(db: str | Path, overrides_path: Path, max_days: int = DEFAULT_MAX_DAYS, min_score: float = DEFAULT_MIN_SCORE,
        confirm: tuple[str, str] | None = None, reject: str | None = None, note: str = "",
        show_report: bool = False) -> None:
    conn = connect(db)
    conn.executescript(MATCH_SCHEMA)
    overrides = load_overrides(overrides_path)
    try:
        if confirm:
            overrides = with_override(overrides, confirm[0], confirm[1], note)
            save_overrides(overrides_path, overrides)
        if reject:
            overrides = with_override(overrides, reject, None, note)
            save_overrides(overrides_path, overrides)
    except ValueError as e:
        raise ValueError(f"{e} in {overrides_path}") from e
    result = match(load_videos(conn), load_notices(conn), overrides, max_days, min_score)
    for w in result.warnings:
        print(f"warning: {w}")
    save_matches(conn, result.matches)
    counts = {c: sum(m.confidence == c for m in result.matches) for c in ("manual", "high", "medium", "low")}
    total = conn.execute("SELECT COUNT(*) FROM youtube_video WHERE is_mousquetaires = 1").fetchone()[0]
    print(f"{len(result.matches)}/{total} videos matched {counts}")
    if show_report:
        report(conn)
