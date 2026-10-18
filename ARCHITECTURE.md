# Architecture of the pipeline

## Goal

- the goal of this project is to produce a curated list of all episodes of the TV show "la cuisine des mousquetaires".
- the aggregation must be reproducible and reliable so that one can include the content as a Wiki table under the article (TODO: when published) with no post editing.

## Code structure: functional core, imperative shell

`src/la_cuisine_des_mousquetaires/`:
- `core/` is pure: functions on strings and plain dataclasses, with no database, network, file, clock or printing.
  `ina.py` (search URLs, HTML parsing), `youtube.py` (video metadata), `matching.py` (scoring and one-to-one pairing,
  human overrides), `tables.py` (TSV / wiki text), `models.py` (the dataclasses exchanged with the shell).
- `shell/` does all the I/O and calls the core: `db.py` (schemas, connection, clock), `ina.py` and `youtube.py`
  (fetch, call the parser, store), `match.py` (load rows and the overrides CSV, call the matcher, store the result),
  `export.py` (SQL queries, write files).
- `__main__.py` is the only place with `argparse`; it orchestrates the steps (`scrape-ina`, `scrape-youtube`,
  `match`, `export`, `all`).

The core is covered by `tests/` without any fixture database.

## Workflow

### Scraping from the ina-thèque (`shell/ina.py`, `core/ina.py`)

with the search parameters:
- Propre titre = "la cuisine des mousquetaires"
- Chaine = France 3 {Poitou Charentes, Aquitaine}, FR3

The results are written in the sqlite tables

#### **search_run**
This table records all search and the numbers of returned results.

#### **search_result**
The results returned by each search run (run_id).

#### **notice**
the integrity table for each notice

#### **notice_field**
records any field of notices

#### **fetch_log**
One row per HTTP request attempt (status, bytes, error text), including failures and retries that never reach `notice`/`search_result`. `run_id` links it to the `search_run` that triggered the request (notice fetches are attributed to the first run that returned them).

#### **notice_field_item**
decompose information that is a list within a notice, like the presenter/realisator.

### Scraping from the ina channel of YouTube (`shell/youtube.py`, `core/youtube.py`)

The script passes each search to the fetcher 

The results are written in the sqlite tables

### Joining the YouTube videos to the ina table

`core/matching.py` scores each video against the notices broadcast within a few days and writes the one-to-one result
to `youtube_match`, which is recomputed on every run. Human corrections are not stored in the database: they live in
`data/youtube_match_overrides.csv`, applied before the automatic matching (see README, "Correct a match by hand").

### Export the consolidated table to wiki format

## Development
2026-10-18: 
- the DB is disposable until the schema stabilises, thus delete the file when the schema changes.
- Human corrections about the matching are stored in a csv file until the schema gets a stable structure.
-  The PRAGMA user_version migration would also be worth adding at that point.