"""Plain data passed between the shell and the matching core."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Video:
    video_id: str
    title: str | None
    description: str | None
    is_mousquetaires: bool
    broadcast_date: str | None      # ISO


@dataclass(frozen=True)
class Notice:
    notice_path: str
    date_iso: str | None
    titre_propre: str | None
    resume_documentaire: str | None
    resume_producteur: str | None
    sommaire: str | None
    descripteurs: str | None


@dataclass(frozen=True)
class Match:
    video_id: str
    notice_path: str
    score: float
    delta: int                      # video broadcast date - notice date, in days
    confidence: str                 # manual / high / medium / low


@dataclass(frozen=True)
class Override:
    """A human decision about a video; notice_path None says the video has no notice."""
    notice_path: str | None
    note: str = ""
