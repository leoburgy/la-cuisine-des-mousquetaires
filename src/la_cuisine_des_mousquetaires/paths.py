"""Locations shared by the commands, resolved from the project root so they do not depend on the working directory."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "data" / "ina_catalogue.sqlite"
DEFAULT_OVERRIDES = ROOT / "data" / "youtube_match_overrides.csv"
DEFAULT_OUT = ROOT / "out"
