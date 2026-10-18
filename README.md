# la-cuisine-des-mousquetaires
Collect data about the episodes of the show "La Cuisine des mousquetaires"

## Usage

Run the commands from `src/`, after `poetry install`. `all` runs the four steps below in order.
```shell
cd src
python -m la_cuisine_des_mousquetaires all
```

### Scrape the INA
The scraping is carried out politely, with one request per second.
```shell
python -m la_cuisine_des_mousquetaires scrape-ina
```

### Scrape the YouTube channel
```shell
python -m la_cuisine_des_mousquetaires scrape-youtube
```

### Check the score of the pairing:
```shell
python -m la_cuisine_des_mousquetaires match --report
```

### Export the tables
Writes TSV and wiki files to `out/`.
```shell
python -m la_cuisine_des_mousquetaires export --table episodes_youtube
```

Every argument is described in [docs/usage.md](docs/usage.md). Options common to all commands (`-v`, `--db`) go before the command.

### Tests
```shell
poetry run pytest
```

### Correct a match by hand
The matcher recomputes `youtube_match` on every run, so edits to that table are lost. Human decisions are kept in
`data/youtube_match_overrides.csv` (or set `--overrides`). The matcher reads
it but never rewrites it, so it survives re-runs and a rebuilt database. Commit it to git: it is the one file that
cannot be regenerated.

Find the `video_id` (YouTube) and `notice_path` (INA, e.g. `RE_RBC07022460`) from the `--report` output or the
`youtube_video` / `v_notice` tables, then:
```shell
# this video is this notice, whatever the score says
python -m la_cuisine_des_mousquetaires match --confirm VIDEO_ID NOTICE_PATH --note "same recipe, title differs"

# this video has no notice, stop proposing one
python -m la_cuisine_des_mousquetaires match --reject VIDEO_ID
```
Both commands update the CSV and re-run the matching. You can also edit the CSV directly
(`video_id,notice_path,note`; an empty `notice_path` means "no notice"); remove a line to undo a decision.

Overridden pairs appear in `youtube_match` with confidence `manual`. The video and the notice are taken out of
the automatic matching, and a notice can be assigned to only one video. An override naming a video or notice that
is not in the database is skipped with a warning.
