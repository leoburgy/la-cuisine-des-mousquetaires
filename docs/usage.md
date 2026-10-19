# Usage reference

```shell
python -m la_cuisine_des_mousquetaires [global options] <command> [command options]
```

The package is installed by `poetry install`, so this works from any directory. The same text is available with
`--help` (`... <command> --help`); this page adds what each command reads, writes and assumes.

`poetry install` also installs the shorter `cuisine` command, equivalent to `python -m la_cuisine_des_mousquetaires`
(see [Shell completion](#shell-completion)).

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
| `--db PATH` | `../data/_ina_catalogue.sqlite` | The SQLite file. The default is relative to the project root, not to the current directory. Every command except `export` creates the file and its folder if missing; `export` opens it read-only and fails if it does not exist. |

Errors in the arguments' values (unknown column, missing database, conflicting override) print `error: ...` and exit
with status 1.

## `scrape-ina`

Runs search queries on the INA catalogue, records every result list, then fetches each notice page found. Searches
are always re-run and recorded as new `search_run` rows; notices already stored with HTTP 200 are skipped unless
`--refresh` is given. Requests are throttled and retried on HTTP 429/5xx.

With no `--search`, the built-in searches run, all limited to broadcasts up to 1997-12-31 (the first version of the
show; the catalogue's `datdif` range filter): the exact title "La cuisine des mousquetaires" on France 3 Aquitaine,
FR3 and France 3, then a full-text phrase search on France 3 Poitou Charente (the 1983 broadcasts are filed under
another collection). Result rows that clearly belong to another programme (another collection, or dated after
1997) are recorded in `search_result` but their notice page is not fetched.

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
| `--table NAME` | `episodes` | `episodes`: one row per notice. `selection`: the final list, one row per episode, with its YouTube video if any (run `match` first; see [The `selection` table](#the-selection-table)). `credits`: one row per person and role. `episodes_youtube`: every notice with its matched YouTube video, if any (run `match` first). |
| `--format F` | `both` | `tsv`, `wiki` or `both`. |
| `--only-matched` | off | `episodes_youtube` and `selection`: keep only the rows that have a YouTube link. Has no effect on the other tables. |
| `--columns A,B,C` | a set per table | Comma-separated column names, in the order wanted. An unknown name fails and lists the available columns. |
| `--out DIR` | `out/` at the project root | Output folder, created if missing. |

```shell
python -m la_cuisine_des_mousquetaires export --table episodes_youtube --only-matched --format wiki
python -m la_cuisine_des_mousquetaires export --format tsv --columns date_iso,chaine,titre_propre
```

Each call writes one table; `all` only exports the default one, `episodes`. To refresh the others, call `export` for
each `--table`.

### The `selection` table

`episodes` keeps every notice, one per broadcast. `selection` reduces them to one row per episode of the first run
(to 1997), described by its first broadcast.

**Which notices count.** The show's own collection, a notice presented by Maïté, Micheline Banzet Lawton or a
revival presenter (credit `PRE` or `PAR`), or a title starting "La cuisine des mousquetaires :". Dropped: other
programmes, the wrappers around a whole magazine ("... : [émission du 5 avril 1990]"), the description of the series
itself (INA type "Collection d'émissions simples"), a notice titled only with the show's name, and anything whose
first broadcast is after 1997.

**Which notices are the same episode.** A rerun carries the INA's own title, which varies, so notices are grouped by
their significant words (no case, accents, punctuation, articles, plural `s`, nor the show-name prefix), then:

- titles with the same words are one episode;
- if the words of one title are all in the other (two at least, compared by their first five letters), they are the
  same episode when the durations agree: within 2 seconds for three words or more, identical for fewer;
- notices of the same day with a common word and an identical duration are the same broadcast (a relay);
- two notices titled "La cuisine des mousquetaires : ..." with a common word and durations within 2 seconds are the
  same episode (the summer 1986 rerun of the 1983 series is titled differently);
- a summary saying "Rediffusion du 20/01/1988" attaches the notice to the broadcast of that date, and "Rediffusion
  du 1er épisode" to the earliest episode.

The INA's "Statut de diffusion" is not used to tell a first run from a rerun: it is often wrong.

**What the row shows.** The first broadcast to air, whether on a regional or the national channel (on the same day the
regional one wins). Blank `duree`, `generique` and `resume_documentaire`, an unknown time (`00:00:00`, `24:00:..`) on
the same day, and a provisional title in brackets are completed from the other broadcasts. A placeholder date (1
January at midnight, the INA's "year only") never beats a real one; when only placeholders are known the date is kept
and `date_incertaine` says `oui`. The YouTube video is the best match among all the broadcasts of the episode, since a
video often shows a rerun.

The default columns are the ones for the wiki article: `premiere_date`, `titre_propre`, `presentateurs`, `chaine`,
`duree`, `youtube_url` and `notice_path`. All the columns below are available with `--columns`.

| Column | Meaning |
|---|---|
| `premiere_date` | Date of the first broadcast. |
| `date_incertaine` | `oui` if that date is a placeholder. |
| `heure_diffusion`, `chaine` | Time and channel of the first broadcast. |
| `statut_diffusion` | The INA label of the first-run notice, unchanged ("Première diffusion", "Rediffusé"...). |
| `titre_propre` | Title of the first broadcast (a plain one if it was bracketed), without the "La cuisine des mousquetaires :" prefix and starting with a capital. |
| `presentateurs` | Known presenters credited on any of its notices. |
| `type_premiere_diffusion` | `régionale` (Aquitaine, Poitou-Charentes) or `nationale` (France 3, FR3). |
| `n_diffusions` | Number of notices merged, the first broadcast included. |
| `derniere_diffusion` | Date of the latest broadcast known. |
| `chaines` | Channels of all the broadcasts, in order of first airing. |
| `autres_diffusions` | `notice_path` of the other broadcasts (links in the wiki table). |
| `duree` | Duration. |
| `youtube_url`, `youtube_duree`, `match_confidence`, `match_score` | The matched video (see `match`). |
| `generique`, `resume_documentaire` | Credits and summary. |
| `notice_path` | The INA notice of the first broadcast. |

## `all`

Runs `scrape-ina`, `scrape-youtube`, `match` and `export` in this order, each with its default options (so `export` writes only the `episodes` table). It takes no
options of its own, only the global `-v` and `--db`, which it passes to every step. It stops at the first step that
fails. Because it scrapes both sites, it takes a while; run the steps separately when you only need one.

## Shell completion

Tab completion (commands, options, and the choices of `--table` / `--format`) is provided by
[argcomplete](https://kislyuk.github.io/argcomplete/) and works for the `cuisine` command, not for
`python -m la_cuisine_des_mousquetaires`. Activate it once per shell, with the virtualenv active (`poetry shell`, or
use the full path to the venv's `register-python-argcomplete`).

bash, in `~/.bashrc`:
```shell
eval "$(register-python-argcomplete cuisine)"
```

zsh, in `~/.zshrc`:
```shell
autoload -U bashcompinit && bashcompinit
eval "$(register-python-argcomplete cuisine)"
```

Then `cuisine ma<TAB>` gives `match`, and `cuisine export --table <TAB>` lists the tables. Free-text values such as
`--confirm` ids are not completed.
