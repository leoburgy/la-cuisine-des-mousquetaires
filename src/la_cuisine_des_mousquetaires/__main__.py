"""Command line of the pipeline: INA scrape, YouTube scrape, matching, export.

Each subcommand is a thin shell around the pure functions in `core`:
    python -m la_cuisine_des_mousquetaires scrape-ina
    python -m la_cuisine_des_mousquetaires scrape-youtube [--limit 20]
    python -m la_cuisine_des_mousquetaires match [--report] [--confirm VIDEO_ID NOTICE_PATH | --reject VIDEO_ID]
    python -m la_cuisine_des_mousquetaires export [--table episodes_youtube --format wiki]
    python -m la_cuisine_des_mousquetaires all        # the four steps in order, default options
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

if not __package__:     # run as a script (python __main__.py, IDE run button): make the package importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from la_cuisine_des_mousquetaires.core.matching import DEFAULT_MAX_DAYS, DEFAULT_MIN_SCORE
from la_cuisine_des_mousquetaires.paths import DEFAULT_DB, DEFAULT_OUT, DEFAULT_OVERRIDES
from la_cuisine_des_mousquetaires.shell import export, ina, youtube
from la_cuisine_des_mousquetaires.shell import match as matching
from la_cuisine_des_mousquetaires.shell.export import TABLES


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="la_cuisine_des_mousquetaires", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite file (default data/ina_catalogue.sqlite)")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("scrape-ina", help="scrape the INA catalogue")
    p.add_argument("--search", action="append", default=[], help="search result URL (repeatable)")
    p.add_argument("--label", action="append", default=[], help="label for each --search, in order")
    p.add_argument("--page-size", type=int, default=500, help="nbLignes used for result lists (default 500)")
    p.add_argument("--delay", type=float, default=1.0, help="seconds between requests (default 1.0)")
    p.add_argument("--refresh", action="store_true", help="re-fetch notices already stored")
    p.add_argument("--searches-only", action="store_true", help="record result lists, do not fetch notices")
    p.add_argument("--no-html", action="store_true", help="do not keep the raw notice HTML")
    p.add_argument("--contact", help="e-mail or URL added to the User-Agent")

    p = sub.add_parser("scrape-youtube", help="scrape the YouTube channel")
    p.add_argument("--channel", default=youtube.CHANNEL_URL, help="channel videos URL")
    p.add_argument("--delay", type=float, default=1.0, help="seconds between video requests (default 1.0)")
    p.add_argument("--limit", type=int, help="only look at the N most recent videos")
    p.add_argument("--refresh", action="store_true", help="re-fetch videos already stored")

    p = sub.add_parser("match", help="match YouTube videos to INA notices")
    p.add_argument("--max-days", type=int, default=DEFAULT_MAX_DAYS, help="largest date difference considered (default 3)")
    p.add_argument("--min-score", type=float, default=DEFAULT_MIN_SCORE, help="lowest score kept (default 0.15)")
    p.add_argument("--overrides", type=Path, default=DEFAULT_OVERRIDES,
                   help="CSV of human decisions (default data/youtube_match_overrides.csv)")
    p.add_argument("--confirm", nargs=2, metavar=("VIDEO_ID", "NOTICE_PATH"), help="record that this video is this notice")
    p.add_argument("--reject", metavar="VIDEO_ID", help="record that this video has no notice")
    p.add_argument("--note", default="", help="comment stored with --confirm / --reject")
    p.add_argument("--report", action="store_true", help="print pairs and unmatched videos")

    p = sub.add_parser("export", help="write TSV / MediaWiki tables")
    p.add_argument("--table", choices=TABLES, default="episodes")
    p.add_argument("--format", choices=["tsv", "wiki", "both"], default="both")
    p.add_argument("--only-matched", action="store_true", help="episodes_youtube: keep only notices with a YouTube link")
    p.add_argument("--columns", help="comma-separated column names (default: a sensible set per table)")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output directory (default: out/)")

    sub.add_parser("all", help="scrape-ina, scrape-youtube, match and export with default options")
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO, format="%(levelname)s %(message)s")

    try:
        match a.command:
            case "scrape-ina":
                searches = list(zip(a.label + [None] * len(a.search), a.search)) or None
                ina.scrape(a.db, searches, a.page_size, a.delay, a.refresh, a.searches_only, not a.no_html, a.contact)
            case "scrape-youtube":
                youtube.scrape(a.db, a.channel, a.delay, a.limit, a.refresh)
            case "match":
                matching.run(a.db, a.overrides, a.max_days, a.min_score, a.confirm, a.reject, a.note, a.report)
            case "export":
                export.run(a.db, a.table, a.format, a.only_matched, a.columns.split(",") if a.columns else None, a.out)
            case "all":
                for step in ("scrape-ina", "scrape-youtube", "match", "export"):
                    main(["--db", str(a.db), *(["-v"] if a.verbose else []), step])
    except (ValueError, FileNotFoundError) as e:
        ap.exit(1, f"error: {e}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
