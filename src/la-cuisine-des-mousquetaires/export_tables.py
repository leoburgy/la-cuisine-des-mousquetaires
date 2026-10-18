"""Export the INA SQLite database (see ina_scraper.py) as TSV and/or MediaWiki tables.

Usage:
    python export_tables.py --db ina_catalogue.sqlite                      # episodes, TSV + wiki in ./out
    python export_tables.py --format wiki --table credits --out tables
    python export_tables.py --format tsv --columns date_iso,chaine,titre_propre
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from pathlib import Path

TABLES = {
    "episodes": {
        "query": "SELECT * FROM v_notice ORDER BY date_iso, heure_diffusion, notice_path",
        "columns": ["date_iso", "heure_diffusion", "chaine", "titre_propre", "titre_collection",
                    "duree", "genre", "generique", "resume_documentaire", "descripteurs", "notice_path"],
    },
    "credits": {
        "query": """SELECT n.date_iso, n.titre_propre, g.role_code, g.name, g.notice_path
                    FROM v_generique g JOIN v_notice n USING (notice_path)
                    ORDER BY n.date_iso, g.notice_path, g.item_index""",
        "columns": None,
    },
    # every notice, with the matched YouTube video if any (see match_youtube.py)
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

NOTICE_URL = "https://catalogue.ina.fr/doc/TV-RADIO/"


def fetch(conn: sqlite3.Connection, table: str, columns: list[str] | None) -> tuple[list[str], list[list[str]]]:
    spec = TABLES[table]
    cur = conn.execute(spec["query"])
    available = [d[0] for d in cur.description]
    wanted = columns or spec["columns"] or available
    missing = [c for c in wanted if c not in available]
    if missing:
        sys.exit(f"unknown column(s): {', '.join(missing)} (available: {', '.join(available)})")
    idx = [available.index(c) for c in wanted]
    rows = [["" if r[i] is None else str(r[i]) for i in idx] for r in cur]
    return wanted, rows


def write_tsv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(header)
        # tabs and newlines would break the format
        w.writerows([[" ".join(c.split()) for c in r] for r in rows])


def wiki_cell(header: str, value: str) -> str:
    value = " ".join(value.split()).replace("|", "{{!}}")
    if header == "youtube_url" and value:
        return f"[{value} ▶]"
    if header == "notice_path" and value:
        return f"[{NOTICE_URL}{value} {value}]"
    return value


def write_wiki(path: Path, header: list[str], rows: list[list[str]]) -> None:
    lines = ['{| class="wikitable sortable"', "! " + " !! ".join(header)]
    for r in rows:
        lines.append("|-")
        lines.append("| " + " || ".join(wiki_cell(h, c) for h, c in zip(header, r)))
    lines.append("|}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="ina_catalogue.sqlite", help="SQLite file produced by ina_scraper.py")
    ap.add_argument("--table", choices=TABLES, default="episodes")
    ap.add_argument("--format", choices=["tsv", "wiki", "both"], default="both")
    ap.add_argument("--only-matched", action="store_true", help="episodes_youtube: keep only notices with a YouTube link")
    ap.add_argument("--columns", help="comma-separated column names (default: a sensible set per table)")
    ap.add_argument("--out", default="out", help="output directory (default: ./out)")
    args = ap.parse_args(argv)

    if not Path(args.db).exists():
        sys.exit(f"database not found: {args.db}")
    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    header, rows = fetch(conn, args.table, args.columns.split(",") if args.columns else None)

    key = TABLES[args.table].get("matched_only")
    if args.only_matched and key:
        k = header.index(key)
        rows = [r for r in rows if r[k]]

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.format in ("tsv", "both"):
        write_tsv(out / f"{args.table}.tsv", header, rows)
    if args.format in ("wiki", "both"):
        write_wiki(out / f"{args.table}.wiki", header, rows)
    print(f"{len(rows)} rows -> {out}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
