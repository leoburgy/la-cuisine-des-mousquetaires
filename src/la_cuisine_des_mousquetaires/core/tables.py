"""Pure table formatting: rows of strings to TSV and MediaWiki text."""
from __future__ import annotations

import csv
import io

from .ina import NOTICE_PREFIX


def select_columns(available: list[str], wanted: list[str] | None) -> list[int]:
    """Indexes in `available` of the wanted columns (all of them if wanted is empty)."""
    wanted = wanted or available
    missing = [c for c in wanted if c not in available]
    if missing:
        raise ValueError(f"unknown column(s): {', '.join(missing)} (available: {', '.join(available)})")
    return [available.index(c) for c in wanted]


def keep_filled(header: list[str], rows: list[list[str]], column: str) -> list[list[str]]:
    k = header.index(column)
    return [r for r in rows if r[k]]


def tsv_text(header: list[str], rows: list[list[str]]) -> str:
    out = io.StringIO(newline="")
    w = csv.writer(out, delimiter="\t", lineterminator="\n")
    w.writerow(header)
    # tabs and newlines would break the format
    w.writerows([[" ".join(c.split()) for c in r] for r in rows])
    return out.getvalue()


def wiki_cell(header: str, value: str) -> str:
    value = " ".join(value.split()).replace("|", "{{!}}")
    if header == "youtube_url" and value:
        return f"[{value} ▶]"
    if header == "notice_path" and value:
        return f"[{NOTICE_PREFIX}{value} {value}]"
    return value


def wiki_text(header: list[str], rows: list[list[str]]) -> str:
    lines = ['{| class="wikitable sortable"', "! " + " !! ".join(header)]
    for r in rows:
        lines.append("|-")
        lines.append("| " + " || ".join(wiki_cell(h, c) for h, c in zip(header, r)))
    lines.append("|}")
    return "\n".join(lines) + "\n"
