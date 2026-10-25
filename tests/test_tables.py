import pytest

from la_cuisine_des_mousquetaires.core.ina import NOTICE_PREFIX
from la_cuisine_des_mousquetaires.core.tables import keep_filled, select_columns, tsv_text, wiki_cell, wiki_text


def test_select_columns_keeps_requested_order():
    assert select_columns(["a", "b", "c"], ["c", "a"]) == [2, 0]
    assert select_columns(["a", "b"], None) == [0, 1]


def test_select_columns_rejects_unknown():
    with pytest.raises(ValueError, match="unknown column"):
        select_columns(["a"], ["z"])


def test_keep_filled():
    assert keep_filled(["a", "b"], [["1", ""], ["2", "x"]], "b") == [["2", "x"]]


def test_tsv_flattens_tabs_and_newlines():
    assert tsv_text(["a", "b"], [["x\ty", "l1\nl2"]]) == "a\tb\nx y\tl1 l2\n"


def test_wiki_cells_escape_pipes_and_link_urls():
    assert wiki_cell("titre", "a | b") == "a {{!}} b"
    assert wiki_cell("youtube_url", "https://y/x") == "[https://y/x ▶]"
    assert wiki_cell("notice_path", "RE_1").startswith("[https://catalogue.ina.fr/doc/TV-RADIO/RE_1 RE_1]")


def test_wiki_text_layout():
    assert wiki_text(["a", "b"], [["1", "2"]]) == '{| class="wikitable sortable"\n! A !! B\n|-\n| 1 || 2\n|}\n'


def test_wiki_headers_are_readable_labels():
    from la_cuisine_des_mousquetaires.core.tables import wiki_header
    assert [wiki_header(c) for c in ("premiere_date", "duree", "n_diffusions")] == ["Première diffusion", "Durée", "N diffusions"]


def test_rebroadcasts_are_linked_by_date():
    assert wiki_cell("rediffusions", "1996-02-01 RE_A ; 1997 RE_B") == (
        f"[{NOTICE_PREFIX}RE_A 1996-02-01] ; [{NOTICE_PREFIX}RE_B 1997]")
