"""Export the database as TSV and/or MediaWiki tables.

Usage through the CLI:
    python -m la_cuisine_des_mousquetaires export                       # episodes, TSV + wiki in ./out
    python -m la_cuisine_des_mousquetaires export --format wiki --table credits --out tables
    python -m la_cuisine_des_mousquetaires export --format tsv --columns date_iso,chaine,titre_propre
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from ..core.episodes import select_episodes
from ..core.tables import keep_filled, select_columns, tsv_text, wiki_text
from .db import connect

TABLES = {
    "episodes": {
        "query": "SELECT * FROM v_notice ORDER BY date_iso, heure_diffusion, notice_path",
        "columns": ["date_iso", "heure_diffusion", "chaine", "titre_propre", "titre_collection",
                    "duree", "genre", "generique", "resume_documentaire", "descripteurs", "notice_path"],
    },
    # one row per episode: the show only, repeats on several channels merged (see core/episodes.py)
    "selection": {
        "query": """SELECT v.*, (SELECT group_concat(name, ' ; ') FROM v_generique g
                                 WHERE g.notice_path = v.notice_path AND g.role_code IN ('PRE', 'PAR')) AS pre,
                           yv.url AS youtube_url,
                           yv.duration_s AS youtube_duree_s,
                           m.confidence AS match_confidence, round(m.score, 2) AS match_score
                    FROM v_notice v
                    LEFT JOIN youtube_match m ON m.notice_path = v.notice_path
                    LEFT JOIN youtube_video yv ON yv.video_id = m.video_id""",
        # what goes on the wiki; every other column of the row is available with --columns
        "columns": ["premiere_date", "titre_propre", "chaine", "duree", "youtube_url", "notice_path"],
        "select": select_episodes,
        "matched_only": "youtube_url",
    },
    "credits": {
        "query": """SELECT n.date_iso, n.titre_propre, g.role_code, g.name, g.notice_path
                    FROM v_generique g JOIN v_notice n USING (notice_path)
                    ORDER BY n.date_iso, g.notice_path, g.item_index""",
        "columns": None,
    },
    # every notice, with the matched YouTube video if any (see the match command)
    "episodes_youtube": {
        "query": """SELECT n.date_iso, n.heure_diffusion, n.chaine, n.titre_propre, n.duree,
                           v.url AS youtube_url,
                           printf('%d:%02d:%02d', v.duration_s / 3600, v.duration_s % 3600 / 60, v.duration_s % 60) AS youtube_duree,
                           m.confidence AS match_confidence, round(m.score, 2) AS match_score, n.notice_path
                    FROM v_notice n
                    LEFT JOIN youtube_match m ON m.notice_path = n.notice_path
                    LEFT JOIN youtube_video v ON v.video_id = m.video_id
                    ORDER BY n.date_iso, n.heure_diffusion, n.notice_path""",
        "columns": None,
        "matched_only": "youtube_url",
    },
}


def fetch(conn: sqlite3.Connection, table: str, columns: list[str] | None) -> tuple[list[str], list[list[str]]]:
    spec = TABLES[table]
    cur = conn.execute(spec["query"])
    available = [d[0] for d in cur.description]
    if "select" in spec:        # row-level logic lives in the core, on plain dicts
        recs = spec["select"]([dict(r) for r in cur])
        available += [k for k in recs[0] if k not in available] if recs else []
        idx = select_columns(available, columns or spec["columns"])
        return [available[i] for i in idx], [["" if r[available[i]] is None else str(r[available[i]]) for i in idx] for r in recs]
    idx = select_columns(available, columns or spec["columns"])
    return [available[i] for i in idx], [["" if r[i] is None else str(r[i]) for i in idx] for r in cur]


def run(db: str | Path, table: str = "episodes", fmt: str = "both", only_matched: bool = False,
        columns: list[str] | None = None, out: str | Path = "out") -> None:
    conn = connect(db, read_only=True)
    header, rows = fetch(conn, table, columns)
    key = TABLES[table].get("matched_only")
    if only_matched and key:
        rows = keep_filled(header, rows, key)

    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    if fmt in ("tsv", "both"):
        (out / f"{table}.tsv").write_text(tsv_text(header, rows), encoding="utf-8", newline="")
    if fmt in ("wiki", "both"):
        (out / f"{table}.wiki").write_text(wiki_text(header, rows), encoding="utf-8")
    print(f"{len(rows)} rows -> {out}/")
