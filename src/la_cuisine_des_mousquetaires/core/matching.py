"""Match YouTube videos to INA notices: pure functions on plain data, no database, files or printing.

A video is compared with every notice broadcast within max_days of its broadcast date. The score
combines the similarity of the recipe titles with the overlap between the video's title/description and
the notice's title/summary/descriptors; each day of date difference costs a small penalty. Matching is
one-to-one (best scores first), with a `confidence` of high / medium / low so doubtful pairs can be reviewed.

Human decisions are `Override`s: they force a pair (confidence `manual`) or say that a video has no
notice, and the overridden videos and notices are excluded from the automatic matching.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher

from .models import Match, Notice, Override, Video

DEFAULT_MAX_DAYS = 3
DEFAULT_MIN_SCORE = 0.15

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


def text_score(video: Video, notice: Notice) -> float:
    vt, nt = core_title(video.title), core_title(notice.titre_propre or "")
    title_sim = SequenceMatcher(None, vt, nt).ratio() if vt and nt else 0.0
    vtok = tokens(TITLE_SUFFIX.sub("", video.title or "")) | tokens(video_text(video.description or ""))
    ntok = tokens(" ".join(filter(None, [notice.titre_propre, notice.resume_documentaire,
                                         notice.resume_producteur, notice.sommaire, notice.descripteurs])))
    overlap = len(vtok & ntok) / min(len(vtok), len(ntok)) if vtok and ntok else 0.0
    return 0.5 * title_sim + 0.5 * overlap


def confidence(score: float, delta: int) -> str:
    if score >= 0.45 and abs(delta) <= 1:
        return "high"
    if score >= 0.3:
        return "medium"
    return "low"


def check_overrides(overrides: dict[str, Override]) -> None:
    targets = [o.notice_path for o in overrides.values() if o.notice_path]
    if len(targets) != len(set(targets)):
        raise ValueError("a notice is assigned to several videos")


def with_override(overrides: dict[str, Override], video_id: str, notice_path: str | None, note: str) -> dict[str, Override]:
    """A copy of overrides with this decision added (replacing any earlier one for the video)."""
    clash = next((v for v, o in overrides.items() if notice_path and o.notice_path == notice_path and v != video_id), None)
    if clash:
        raise ValueError(f"{notice_path} is already assigned to video {clash}")
    return {**overrides, video_id: Override(notice_path, note)}


def _delta(video_date: str | None, notice_date: str | None) -> int:
    if not (video_date and notice_date):
        return 0
    return (date.fromisoformat(video_date) - date.fromisoformat(notice_date)).days


@dataclass(frozen=True)
class MatchResult:
    matches: list[Match]
    warnings: list[str]


def manual_matches(videos: dict[str, Video], notices: dict[str, Notice],
                   overrides: dict[str, Override]) -> tuple[list[Match], list[str]]:
    result, warnings = [], []
    for vid, o in overrides.items():
        if not o.notice_path:
            continue
        v, n = videos.get(vid), notices.get(o.notice_path)
        if v is None or n is None:
            warnings.append(f"override {vid} -> {o.notice_path} ignored, unknown {'video' if v is None else 'notice'}")
            continue
        result.append(Match(vid, o.notice_path, text_score(v, n), _delta(v.broadcast_date, n.date_iso), "manual"))
    return result, warnings


def match(videos: list[Video], notices: list[Notice], overrides: dict[str, Override] | None = None,
          max_days: int = DEFAULT_MAX_DAYS, min_score: float = DEFAULT_MIN_SCORE) -> MatchResult:
    overrides = overrides or {}
    manual, warnings = manual_matches({v.video_id: v for v in videos}, {n.notice_path: n for n in notices}, overrides)
    skip_n = {m.notice_path for m in manual}
    shows = [v for v in videos if v.is_mousquetaires and v.video_id not in overrides]
    candidates = [n for n in notices if n.date_iso and n.notice_path not in skip_n]

    pairs = []      # (score, video_id, notice_path, delta, undated)
    for v in shows:
        if not v.broadcast_date:
            continue
        for n in candidates:
            delta = _delta(v.broadcast_date, n.date_iso)
            if abs(delta) > max_days:
                continue
            score = text_score(v, n) - 0.04 * abs(delta)
            if score >= min_score:
                pairs.append((score, v.video_id, n.notice_path, delta, False))
    # videos without a usable date: text only, and only if the match is clear
    for v in shows:
        if v.broadcast_date:
            continue
        scored = sorted(((text_score(v, n), n) for n in candidates), key=lambda t: -t[0])
        if scored and scored[0][0] >= UNDATED_MIN_SCORE:
            pairs.append((scored[0][0], v.video_id, scored[0][1].notice_path, 0, True))
    pairs.sort(key=lambda p: -p[0])

    used_v, used_n, result = set(), set(), list(manual)
    for score, video_id, notice_path, delta, undated in pairs:
        if video_id in used_v or notice_path in used_n:
            continue
        used_v.add(video_id)
        used_n.add(notice_path)
        result.append(Match(video_id, notice_path, score, delta, "low" if undated else confidence(score, delta)))
    return MatchResult(result, warnings)
