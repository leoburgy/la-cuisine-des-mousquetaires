# Architecture of the pipeline

## Goal

- the goal of this project is to produce a curated list of all episodes of the TV show "la cuisine des mousquetaires".
- the aggregation must be reproducible and reliable so that one can include the content as a Wiki table under the article (TODO: when published) with no post editing.

## Workflow

### Scraping from the ina-thèque (`ina_scraper.py`)

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
dubious

#### **notice_field_item**
decompose information that is a list within a notice, like the presenter/realisator.

### Scraping from the ina channel of YouTube (`youtube_scraper.py`)

The results are written in the sqlite tables

### Joining the YouTube videos to the ina table

### Export the consolidated table to wiki format