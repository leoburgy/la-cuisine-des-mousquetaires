"""SQLite access: schemas, connection and the clock."""
from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path


def utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def connect(path: str | Path, *, read_only: bool = False) -> sqlite3.Connection:
    """Open the database (created with its parent directory unless read_only), rows accessible by name."""
    if read_only:
        if not Path(path).exists():
            raise FileNotFoundError(f"database not found: {path}")
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    else:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


INA_SCHEMA = """
PRAGMA foreign_keys = ON;

-- One row per execution of a search URL.
CREATE TABLE IF NOT EXISTS search_run (
    run_id          INTEGER PRIMARY KEY,
    label           TEXT,
    url             TEXT NOT NULL,          -- URL as given
    fetched_url     TEXT NOT NULL,          -- URL actually requested (nbLignes changed)
    run_at          TEXT NOT NULL,          -- UTC ISO timestamp
    total_reported  INTEGER,                -- "Enregistrements 1 à N sur TOTAL"
    rows_parsed     INTEGER
);

-- One row per line of the result table, exactly as displayed.
CREATE TABLE IF NOT EXISTS search_result (
    run_id            INTEGER NOT NULL REFERENCES search_run(run_id),
    rang              INTEGER NOT NULL,     -- first column of the table
    notice_path       TEXT,                 -- e.g. RE_RBC07022460
    chaine            TEXT,                 -- "Chaîne de diffusion"
    date_diffusion    TEXT,                 -- "Date de diffusion" (dd/mm/yyyy, raw)
    heure_diffusion   TEXT,                 -- "Heure de diffusion" (raw)
    duree             TEXT,                 -- "Durée" (raw)
    titre_propre      TEXT,                 -- "Titre propre"
    titre_collection  TEXT,                 -- "Titre collection"
    titre_programme   TEXT,                 -- "Titre programme"
    genre             TEXT,                 -- "Genre"
    href              TEXT,                 -- link as found (with ?rang=)
    PRIMARY KEY (run_id, rang)
);

-- One row per notice page.
CREATE TABLE IF NOT EXISTS notice (
    notice_path   TEXT PRIMARY KEY,         -- e.g. RE_RBC07022460, RG_7033612.001
    notice_id     TEXT,                     -- value of field NO ("ID Notice")
    url           TEXT NOT NULL,
    fetched_at    TEXT NOT NULL,
    http_status   INTEGER,
    html_sha256   TEXT,
    html_zlib     BLOB,                     -- raw page, zlib-compressed (optional)
    duree_s       INTEGER                   -- field DUREE in seconds, NULL if unknown (the raw text stays in notice_field)
);

-- One row per field of a notice, in page order.
CREATE TABLE IF NOT EXISTS notice_field (
    notice_path   TEXT NOT NULL REFERENCES notice(notice_path) ON DELETE CASCADE,
    position      INTEGER NOT NULL,         -- order on the page (1-based)
    code          TEXT,                     -- id of the value cell (TI, DATDIF, GEN...)
    label         TEXT NOT NULL,            -- label cell text ("Titre propre"...)
    value_text    TEXT,                     -- text, <br> kept as newlines
    value_html    TEXT,                     -- inner HTML of the value cell
    PRIMARY KEY (notice_path, position)
);

-- List-valued fields split on " ; " (Générique, Descripteurs, Genre...).
-- For Générique (GEN) the part before the first comma is the role code
-- shown by the site (REA, PRE, JOU...), the rest is the name.
CREATE TABLE IF NOT EXISTS notice_field_item (
    notice_path   TEXT NOT NULL,
    position      INTEGER NOT NULL,         -- position of the field
    item_index    INTEGER NOT NULL,         -- order inside the field (1-based)
    value         TEXT NOT NULL,
    role_code     TEXT,                     -- GEN only
    name          TEXT,                     -- GEN only
    PRIMARY KEY (notice_path, position, item_index),
    FOREIGN KEY (notice_path, position) REFERENCES notice_field(notice_path, position) ON DELETE CASCADE
);

-- A notice can be found by several searches: search_result keeps every hit, notice keeps one copy.
-- Search results <-> notices.
CREATE INDEX IF NOT EXISTS ix_result_notice ON search_result(notice_path);
CREATE INDEX IF NOT EXISTS ix_field_code ON notice_field(code);

CREATE TABLE IF NOT EXISTS fetch_log (
    fetched_at   TEXT NOT NULL,
    url          TEXT NOT NULL,
    http_status  INTEGER,
    bytes        INTEGER,
    error        TEXT,
    run_id       INTEGER REFERENCES search_run(run_id)   -- search that triggered the request
);

-- Convenience view: one row per notice with the most common fields.
-- Derived only by pivoting notice_field; dates converted to ISO.
DROP VIEW IF EXISTS v_notice;
CREATE VIEW v_notice AS
SELECT
    n.notice_path,
    n.notice_id,
    n.url,
    MAX(CASE WHEN f.code = 'TI'       THEN f.value_text END) AS titre_propre,
    MAX(CASE WHEN f.code = 'TICOL'    THEN f.value_text END) AS titre_collection,
    MAX(CASE WHEN f.label = 'Titre programme' THEN f.value_text END) AS titre_programme,
    MAX(CASE WHEN f.code = 'CH'       THEN f.value_text END) AS chaine,
    MAX(CASE WHEN f.code = 'DATDIF'   THEN f.value_text END) AS date_diffusion,
    MAX(CASE WHEN f.code = 'DATDIF'   THEN substr(f.value_text,7,4)||'-'||substr(f.value_text,4,2)||'-'||substr(f.value_text,1,2) END) AS date_iso,
    MAX(CASE WHEN f.code = 'JOUR'     THEN f.value_text END) AS jour,
    MAX(CASE WHEN f.code = 'STADIF'   THEN f.value_text END) AS statut_diffusion,
    MAX(CASE WHEN f.code = 'HEURE'    THEN f.value_text END) AS heure_diffusion,
    MAX(CASE WHEN f.code = 'HEUREFIN' THEN f.value_text END) AS heure_fin,
    MAX(CASE WHEN f.code = 'DUREE'    THEN f.value_text END) AS duree,
    n.duree_s,
    MAX(CASE WHEN f.code = 'GENRE'    THEN f.value_text END) AS genre,
    MAX(CASE WHEN f.code = 'TYPDESCR' THEN f.value_text END) AS type_description,
    MAX(CASE WHEN f.code = 'GEN'      THEN f.value_text END) AS generique,
    MAX(CASE WHEN f.code = 'RES'      THEN f.value_text END) AS resume_documentaire,
    MAX(CASE WHEN f.label = 'Résumé producteur' THEN f.value_text END) AS resume_producteur,
    MAX(CASE WHEN f.code = 'SOM'      THEN f.value_text END) AS sommaire,
    MAX(CASE WHEN f.code = 'DE'       THEN f.value_text END) AS descripteurs,
    MAX(CASE WHEN f.code = 'DES'      THEN f.value_text END) AS descripteurs_secondaires,
    MAX(CASE WHEN f.code = 'PROD'     THEN f.value_text END) AS producteurs,
    MAX(CASE WHEN f.code = 'BASE'     THEN f.value_text END) AS base
FROM notice n
LEFT JOIN notice_field f ON f.notice_path = n.notice_path
GROUP BY n.notice_path;

-- Credits: one row per person and role.
DROP VIEW IF EXISTS v_generique;
CREATE VIEW v_generique AS
SELECT i.notice_path, i.item_index, i.role_code, i.name
FROM notice_field_item i
JOIN notice_field f ON f.notice_path = i.notice_path AND f.position = i.position
WHERE f.code = 'GEN';

-- Latest result list of each search, with ISO dates.
DROP VIEW IF EXISTS v_search_result_latest;
CREATE VIEW v_search_result_latest AS
SELECT r.*, s.label, s.url AS search_url,
       substr(r.date_diffusion,7,4)||'-'||substr(r.date_diffusion,4,2)||'-'||substr(r.date_diffusion,1,2) AS date_iso
FROM search_result r
JOIN search_run s ON s.run_id = r.run_id
WHERE s.run_id = (SELECT MAX(s2.run_id) FROM search_run s2 WHERE s2.url = s.url);
"""


YOUTUBE_SCHEMA = """
CREATE TABLE IF NOT EXISTS youtube_video (
    video_id           TEXT PRIMARY KEY,
    url                TEXT NOT NULL,
    title              TEXT,
    description        TEXT,
    duration_s         INTEGER,               -- video length in seconds
    upload_date        TEXT,                  -- ISO date the video was posted
    view_count         INTEGER,
    fetched_at         TEXT NOT NULL,
    is_mousquetaires   INTEGER NOT NULL,      -- description mentions the show
    broadcast_date     TEXT,                  -- ISO date parsed from the description
    broadcast_channel  TEXT                   -- TV channel parsed from the description (FR3...)
);
CREATE INDEX IF NOT EXISTS ix_youtube_broadcast ON youtube_video(broadcast_date);

-- Episodes of the show on YouTube; join with v_notice on date_iso.
DROP VIEW IF EXISTS v_youtube_episode;
CREATE VIEW v_youtube_episode AS
SELECT video_id, url, title, duration_s,
       printf('%d:%02d:%02d', duration_s / 3600, duration_s % 3600 / 60, duration_s % 60) AS duree,
       broadcast_date AS date_iso, broadcast_channel AS chaine, upload_date
FROM youtube_video
WHERE is_mousquetaires = 1;
"""


MATCH_SCHEMA = """
CREATE TABLE IF NOT EXISTS youtube_match (
    notice_path  TEXT PRIMARY KEY,
    video_id     TEXT NOT NULL UNIQUE REFERENCES youtube_video(video_id),
    score        REAL NOT NULL,
    date_delta   INTEGER NOT NULL,          -- video broadcast date - notice date, in days
    confidence   TEXT NOT NULL              -- high / medium / low / manual
);
"""
