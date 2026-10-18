import pytest

from la_cuisine_des_mousquetaires.core.matching import (check_overrides, confidence, core_title, match, tokens,
                                                        video_text, with_override)
from la_cuisine_des_mousquetaires.core.models import Notice, Override, Video


def video(vid, title, date=None, description="", show=True):
    return Video(vid, title, description, show, date)


def notice(path, title, date="1992-06-19", **kw):
    return Notice(path, date, title, kw.get("resume"), None, None, kw.get("descripteurs"))


def test_tokens_drop_stopwords_accents_and_plurals():
    assert tokens("Les Cèpes de la forêt, recettes") == {"cepe", "foret"}


def test_core_title_strips_show_prefix_and_ina_suffix():
    assert core_title("La cuisine des mousquetaires (1992) : Cou de canard | INA Les Recettes") == "canard cou"


def test_video_text_stops_at_boilerplate_and_skips_date_line():
    description = "Cou farci\nLa Cuisine Des Mousquetaires | FR3 | 19/06/1992\nAbonnez-vous\nignored"
    assert video_text(description) == "Cou farci"


@pytest.mark.parametrize("score, delta, expected", [
    (0.5, 0, "high"), (0.5, 1, "high"), (0.5, 2, "medium"), (0.3, 0, "medium"), (0.29, 0, "low")])
def test_confidence(score, delta, expected):
    assert confidence(score, delta) == expected


def test_match_pairs_same_recipe_on_same_day():
    result = match([video("v1", "Cou de canard farci", "1992-06-19")],
                   [notice("n1", "Cou de canard farci"), notice("n2", "Tarte aux pommes")])
    assert [(m.video_id, m.notice_path, m.delta) for m in result.matches] == [("v1", "n1", 0)]


def test_match_ignores_notices_beyond_max_days():
    result = match([video("v1", "Cou de canard", "1992-06-19")], [notice("n1", "Cou de canard", date="1992-07-19")])
    assert result.matches == []


def test_match_is_one_to_one_best_score_first():
    videos = [video("v1", "Cou de canard farci", "1992-06-19"), video("v2", "Cou de canard", "1992-06-19")]
    result = match(videos, [notice("n1", "Cou de canard farci")])
    assert [(m.video_id, m.notice_path) for m in result.matches] == [("v1", "n1")]


def test_match_skips_videos_that_are_not_the_show():
    result = match([video("v1", "Cou de canard", "1992-06-19", show=False)], [notice("n1", "Cou de canard")])
    assert result.matches == []


def test_undated_video_needs_a_clear_text_match():
    notices = [notice("n1", "Cou de canard farci")]
    assert match([video("v1", "Cou de canard farci")], notices).matches[0].confidence == "low"
    assert match([video("v1", "Tarte")], notices).matches == []


def test_manual_override_forces_pair_and_excludes_both_from_automatic_matching():
    videos = [video("v1", "Cou de canard", "1992-06-19"), video("v2", "Tarte", "1992-06-19")]
    notices = [notice("n1", "Cou de canard"), notice("n2", "Tarte")]
    result = match(videos, notices, {"v1": Override("n2")})
    assert {(m.video_id, m.notice_path, m.confidence) for m in result.matches} == {("v1", "n2", "manual")}


def test_rejected_video_is_not_matched():
    result = match([video("v1", "Cou de canard", "1992-06-19")], [notice("n1", "Cou de canard")],
                   {"v1": Override(None)})
    assert result.matches == []


def test_override_to_unknown_notice_is_reported():
    result = match([video("v1", "Cou", "1992-06-19")], [], {"v1": Override("missing")})
    assert result.matches == [] and "unknown notice" in result.warnings[0]


def test_with_override_replaces_and_does_not_mutate():
    before = {"v1": Override("n1")}
    after = with_override(before, "v1", "n2", "note")
    assert before["v1"].notice_path == "n1" and after["v1"] == Override("n2", "note")


def test_with_override_refuses_a_notice_already_taken():
    with pytest.raises(ValueError, match="already assigned to video v1"):
        with_override({"v1": Override("n1")}, "v2", "n1", "")


def test_check_overrides_refuses_duplicate_notice():
    with pytest.raises(ValueError):
        check_overrides({"v1": Override("n1"), "v2": Override("n1")})
