from la_cuisine_des_mousquetaires.core.youtube import iso_upload_date, parse_broadcast, video_record

LINE = "La Cuisine Des Mousquetaires | FR3 | 19/06/1992"


def test_parse_broadcast_reads_date_and_channel_from_the_show_line():
    assert parse_broadcast(f"Intro\n{LINE}\nautre 01/01/2000") == ("1992-06-19", "FR3")


def test_parse_broadcast_falls_back_to_first_date():
    assert parse_broadcast("La cuisine des mousquetaires\nle 03/04/1990") == ("1990-04-03", None)


def test_parse_broadcast_ignores_impossible_dates():
    assert parse_broadcast("La cuisine des mousquetaires 31/02/1990") == (None, None)


def test_iso_upload_date():
    assert iso_upload_date("20240131") == "2024-01-31"
    assert iso_upload_date(None) is None


def test_video_record_for_a_show_video():
    v = video_record({"id": "abc", "title": "Cou", "description": LINE, "duration": 61.0, "upload_date": "20240131"})
    assert (v.url, v.is_mousquetaires, v.broadcast_date, v.broadcast_channel, v.duration_s) == \
           ("https://www.youtube.com/watch?v=abc", True, "1992-06-19", "FR3", 61)


def test_video_record_for_another_video_has_no_broadcast():
    v = video_record({"id": "abc", "title": "Autre", "description": "01/01/2000"})
    assert (v.is_mousquetaires, v.broadcast_date, v.duration_s) == (False, None, None)
