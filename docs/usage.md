# Usage reference

```shell
python -m la_cuisine_des_mousquetaires [global options] <command> [command options]
```

The package is installed by `poetry install`, so this works from any directory. The same text is available with
`--help` (`... <command> --help`); this page adds what each command reads, writes and assumes.

The pipeline has four steps, each its own command, and `all` chains them:

| Command | Reads | Writes |
|---|---|---|
| `scrape-ina` | catalogue.ina.fr | `search_run`, `search_result`, `notice`, `notice_field`, `notice_field_item`, `fetch_log` |
| `scrape-youtube` | the YouTube channel | `youtube_video` |
| `match` | `youtube_video`, `v_notice`, overrides CSV | `youtube_match`, overrides CSV (only with `--confirm` / `--reject`) |
| `export` | the database (read-only) | `.tsv` / `.wiki` files |

## Global options

They go **before** the command: `python -m la_cuisine_des_mousquetaires -v --db other.sqlite match`.

| Option | Default | Meaning |
|---|---|---|
| `-v`, `--verbose` | off | Debug logging (per-notice and per-video progress). |
| `--db PATH` | `data/ina_catalogue.sqlite` | The SQLite file. The default is relative to the project root, not to the current directory. Every command except `export` creates the file and its folder if missing; `export` opens it read-only and fails if it does not exist. |

Errors in the arguments' values (unknown column, missing database, conflicting override) print `error: ...` and exit
with status 1.

## `scrape-ina`

Runs search queries on the INA catalogue, records every result list, then fetches each notice page found. Searches
are always re-run and recorded as new `search_run` rows; notices already stored with HTTP 200 are skipped unless
`--refresh` is given. Requests are throttled and retried on HTTP 429/5xx.

With no `--search`, the built-in searches run: the exact title "La cuisine des mousquetaires" on each of six channels
(France 3 Aquitaine, Poitou Charente, Midi Pyrénées, Languedoc Roussillon, FR3, France 3), then a full-text phrase
search on three of them.

| Option | Default | Meaning |
|---|---|---|
| `--search URL` | built-in searches | A catalogue result-list URL to run instead of the built-in ones. Repeatable. |
| `--label TEXT` | the URL | Name stored in `search_run.label` for each `--search`, matched by position. Fewer labels than searches is fine: the remaining searches are labelled with their URL. |
| `--page-size N` | `500` | Rows requested per result page (`nbLignes`). The site caps it at 500; further pages are fetched automatically. |
| `--delay SECONDS` | `1.0` | Minimum pause between two requests. Keep it polite; failed requests wait 4x this per attempt before retrying. |
| `--refresh` | off | Fetch again the notices already stored, replacing their fields. |
| `--searches-only` | off | Record the result lists but do not fetch any notice page. |
| `--no-html` | off | Do not keep the raw notice HTML (`notice.html_zlib` stays empty). Saves space, but the parsed fields can no longer be re-derived without re-fetching. |
| `--contact TEXT` | none | E-mail or URL put in the User-Agent so the site can reach you. |

```shell
python -m la_cuisine_des_mousquetaires scrape-ina --contact me@example.org
python -m la_cuisine_des_mousquetaires scrape-ina --search "https://catalogue.ina.fr/docListe/TV-RADIO?..." --label "my search" --searches-only
```

## `scrape-youtube`

Lists the videos of the channel, then fetches the metadata of each video not yet stored (title, description,
duration, upload date, views). A video whose title or description mentions "La Cuisine des mousquetaires" is flagged
`is_mousquetaires`, and its broadcast date and TV channel are parsed from a description line such as
`La Cuisine Des Mousquetaires | FR3 | 19/06/1992`. Videos that fail to download are logged and skipped; the count is
reported at the end.

| Option | Default | Meaning |
|---|---|---|
| `--channel URL` | INA Les Recettes Vintage, `/videos` | The channel videos page to list. |
| `--delay SECONDS` | `1.0` | Pause between two video requests. |
| `--limit N` | all | Only list the N most recent videos. Useful for a quick test. |
| `--refresh` | off | Fetch again the videos already stored. |

## `match`

Pairs each show video with an INA notice and stores the result in `youtube_match` (emptied and rewritten on every
run). Matching is one-to-one, best scores first.

How a pair is scored:
- a video is only compared with notices broadcast within `--max-days` of its broadcast date;
- the score is 0.5 x similarity of the recipe titles + 0.5 x word overlap between the video text and the notice text
  (title, summaries, table of contents, descriptors), minus 0.04 per day of date difference;
- confidence is `high` (score >= 0.45 and at most 1 day apart), `medium` (score >= 0.3), otherwise `low`;
- a video with no usable date is matched on text alone, only with a score >= 0.6, and is always `low`;
- a pair forced by a human decision has confidence `manual`.

| Option | Default | Meaning |
|---|---|---|
| `--max-days N` | `3` | Largest difference, in days, between the video's broadcast date and the notice date. |
| `--min-score X` | `0.15` | Pairs scoring below this are dropped. |
| `--overrides PATH` | `data/youtube_match_overrides.csv` | The CSV of human decisions (`video_id,notice_path,note`). Read on every run; rewritten only by `--confirm` / `--reject`. |
| `--confirm VIDEO_ID NOTICE_PATH` | none | Record that this video is this notice, then match. Fails if the notice is already assigned to another video. |
| `--reject VIDEO_ID` | none | Record that this video has no notice, then match. |
| `--note TEXT` | empty | Comment stored with the `--confirm` / `--reject` decision. |
| `--report` | off | After matching, print the matched pairs (lowest score first) and the videos left without a notice. |

Overridden videos and notices are excluded from the automatic matching. An override naming a video or notice that is
not in the database is skipped with a warning. To undo a decision, delete its line from the CSV. See the README
section "Correct a match by hand" for the workflow.

```shell
python -m la_cuisine_des_mousquetaires match --report
python -m la_cuisine_des_mousquetaires match --confirm dQw4w9WgXcQ RE_RBC07022460 --note "same recipe, title differs"
python -m la_cuisine_des_mousquetaires match --reject dQw4w9WgXcQ
```

## `export`

Writes one table as TSV and/or MediaWiki, to `<out>/<table>.tsv` and `<out>/<table>.wiki`. In TSV, tabs and newlines
inside cells are flattened to spaces. In the wiki table, `|` is escaped, `youtube_url` becomes a link and
`notice_path` links to the catalogue.

| Option | Default | Meaning |
|---|---|---|
| `--table NAME` | `episodes` | `episodes`: one row per notice. `credits`: one row per person and role. `episodes_youtube`: every notice with its matched YouTube video, if any (run `match` first). |
| `--format F` | `both` | `tsv`, `wiki` or `both`. |
| `--only-matched` | off | `episodes_youtube` only: keep only notices that have a YouTube link. Has no effect on the other tables. |
| `--columns A,B,C` | a set per table | Comma-separated column names, in the order wanted. An unknown name fails and lists the available columns. |
| `--out DIR` | `out/` at the project root | Output folder, created if missing. |

```shell
python -m la_cuisine_des_mousquetaires export --table episodes_youtube --only-matched --format wiki
python -m la_cuisine_des_mousquetaires export --format tsv --columns date_iso,chaine,titre_propre
```

## `all`

Runs `scrape-ina`, `scrape-youtube`, `match` and `export` in this order, each with its default options. It takes no
options of its own, only the global `-v` and `--db`, which it passes to every step. It stops at the first step that
fails. Because it scrapes both sites, it takes a while; run the steps separately when you only need one.
