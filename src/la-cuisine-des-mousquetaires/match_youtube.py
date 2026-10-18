"""Match YouTube videos (youtube_scraper.py) to INA notices (ina_scraper.py) and store the result.

A video is compared with every notice broadcast within --max-days of its broadcast date. The score
combines the similarity of the recipe titles with the overlap between the video's title/description and
the notice's title/summary/descriptors; each day of date difference costs a small penalty. Matching is
one-to-one (best scores first) and the result goes to `youtube_match`, with a `confidence` of
high / medium / low so doubtful pairs can be reviewed.

Usage:
    python match_youtube.py --db ina_catalogue.sqlite
    python match_youtube.py --db ina_catalogue.sqlite --report     # also print the pairs, unmatched videos and notices
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import unicodedata
from datetime import date
from difflib import SequenceMatcher

SCHEMA = """
CREATE TABLE IF NOT EXISTS youtube_match (
    notice_path  TEXT PRIMARY KEY,
    video_id     TEXT NOT NULL UNIQUE REFERENCES youtube_video(video_id),
    score        REAL NOT NULL,
    date_delta   INTEGER NOT NULL,          -- video broadcast date - notice date, in days
    confidence   TEXT NOT NULL              -- high / medium / low
);
"""

STOPWORDS = set("""
a au aux avec ce ces dans de des du en et la le les leur leurs mais ou par pour sa se ses son sur un une
facon recette recettes cuisine mousquetaires emission serie maite micheline ordonez banzet ina vintage
les recettes abonnez vous images archive institut national audiovisuel
""".split())

UNDATED_MIN_SCORE = 0.6

TITLE_PREFIX = re.compile(r"^\s*la\s+cuisine\s+des\s+mousquetaires\s*(\([^)]*\))?\s*[:\-]?\s*", re.I)
TITLE_SUFFIX = re.compile(r"\s*\|\s*ina.*$", re.I)


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def tokens(text: str) -> set[str]:
    text = re.sub(r"[^a-z0-9]+", " ", strip_accents(text.lower()))
    out = set()
    for w in text.split():
        if w in STOPWORDS or len(w) < 3:
            continue
        out.add(w.rstrip("sx") if len(w) > 4 else w)
    return out


def core_title(title: str) -> str:
    title = TITLE_SUFFIX.sub("", title or "")
    title = TITLE_PREFIX.sub("", title)
    return " ".join(sorted(tokens(title)))


def video_text(description: str) -> str:
    """The free-text part of a video description (before the boilerplate)."""
    lines = [l for l in description.splitlines() if l.strip()]
    keep = []
    for l in lines:
        if l.startswith(("Abonnez", "👉", "•", "Images d'archive", "******")):
            break
        if "|" in l and re.search(r"\d{1,2}/\d{1,2}/\d{4}", l):
            continue
        keep.append(l)
    return " ".join(keep)


def text_score(video: sqlite3.Row, notice: sqlite3.Row) -> float:
    vt, nt = core_title(video["title"]), core_title(notice["titre_propre"] or "")
    title_sim = SequenceMatcher(None, vt, nt).ratio() if vt and nt else 0.0
    vtok = tokens(TITLE_SUFFIX.sub("", video["title"] or "")) | tokens(video_text(video["description"] or ""))
    ntok = tokens(" ".join(filter(None, [notice["titre_propre"], notice["resume_documentaire"],
                                         notice["resume_producteur"], notice["sommaire"], notice["descripteurs"]])))
    overlap = len(vtok & ntok) / min(len(vtok), len(ntok)) if vtok and ntok else 0.0
    return 0.5 * title_sim + 0.5 * overlap


def confidence(score: float, delta: int) -> str:
    if score >= 0.45 and abs(delta) <= 1:
        return "high"
    if score >= 0.3:
        return "medium"
    return "low"


def match(conn: sqlite3.Connection, max_days: int, min_score: float) -> list[dict]:
    videos = conn.execute("SELECT * FROM youtube_video WHERE is_mousquetaires = 1 AND broadcast_date IS NOT NULL").fetchall()
    notices = conn.execute("SELECT * FROM v_notice WHERE date_iso IS NOT NULL").fetchall()
    pairs = []
    for v in videos:
        vd = date.fromisoformat(v["broadcast_date"])
        for n in notices:
            delta = (vd - date.fromisoformat(n["date_iso"])).days
            if abs(delta) > max_days:
                continue
            ts = text_score(v, n)
            score = ts - 0.04 * abs(delta)
            if score >= min_score:
                pairs.append({"video_id": v["video_id"], "notice_path": n["notice_path"], "score": score, "delta": delta})
    # videos without a usable date: text only, and only if the match is clear
    for v in conn.execute("SELECT * FROM youtube_video WHERE is_mousquetaires = 1 AND broadcast_date IS NULL").fetchall():
        scored = sorted(((text_score(v, n), n) for n in notices), key=lambda t: -t[0])
        if scored and scored[0][0] >= UNDATED_MIN_SCORE:
            pairs.append({"video_id": v["video_id"], "notice_path": scored[0][1]["notice_path"],
                          "score": scored[0][0], "delta": 0, "undated": True})
    pairs.sort(key=lambda p: -p["score"])
    used_v, used_n, result = set(), set(), []
    for p in pairs:
        if p["video_id"] in used_v or p["notice_path"] in used_n:
            continue
        used_v.add(p["video_id"])
        used_n.add(p["notice_path"])
        p["confidence"] = "low" if p.get("undated") else confidence(p["score"], p["delta"])
        result.append(p)
    return result


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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="ina_catalogue.sqlite")
    ap.add_argument("--max-days", type=int, default=3, help="largest date difference considered (default 3)")
    ap.add_argument("--min-score", type=float, default=0.15, help="lowest score kept (default 0.15)")
    ap.add_argument("--report", action="store_true", help="print pairs and unmatched videos")
    args = ap.parse_args(argv)

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    result = match(conn, args.max_days, args.min_score)
    conn.execute("DELETE FROM youtube_match")
    conn.executemany("INSERT INTO youtube_match VALUES (:notice_path,:video_id,:score,:delta,:confidence)", result)
    conn.commit()
    counts = {c: sum(r["confidence"] == c for r in result) for c in ("high", "medium", "low")}
    total = conn.execute("SELECT COUNT(*) FROM youtube_video WHERE is_mousquetaires = 1").fetchone()[0]
    print(f"{len(result)}/{total} videos matched {counts}")
    if args.report:
        report(conn)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
