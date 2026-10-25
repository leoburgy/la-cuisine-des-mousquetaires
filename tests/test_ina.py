from la_cuisine_des_mousquetaires.core.ina import (DEFAULT_SEARCHES, Field, keep_result_row, parse_list_page,
                                                   parse_notice_page, search_url, split_items, with_param)

LIST_HTML = """
<p>Enregistrements 1 à 1 sur 2</p>
<table><tr>
  <td class="indice">1</td><td>France 3</td><td>19/06/1992</td><td>19:00</td><td>00:26:00</td>
  <td><a href="/doc/TV-RADIO/RE_RBC07022460?rang=1">Cou farci</a></td>
  <td>La cuisine des mousquetaires</td><td>Prog</td><td>Magazine</td>
</tr></table>
<form name="documentSelection" action="/next"><input name="page" value="1"><input name="x" value="y"></form>
"""

NOTICE_HTML = """
<div id="result-tableau-1"><table>
  <tr><td class="label_champs_form">ID Notice</td><td class="val_champs_form" id="NO">RBC1</td></tr>
  <tr><td class="label_champs_form">Générique</td>
      <td class="val_champs_form" id="GEN">REA, Jean Dupont ; PRE, Maïté</td></tr>
  <tr><td class="label_champs_form">Résumé</td><td class="val_champs_form" id="RES">Ligne 1<br>Ligne 2</td></tr>
</table></div>
"""


def test_parse_list_page():
    page = parse_list_page(LIST_HTML)
    assert page.total == 2
    assert page.rows == [{"rang": 1, "href": "/doc/TV-RADIO/RE_RBC07022460?rang=1", "notice_path": "RE_RBC07022460",
                          "chaine": "France 3", "date_diffusion": "19/06/1992", "heure_diffusion": "19:00",
                          "duree": "00:26:00", "titre_propre": "Cou farci",
                          "titre_collection": "La cuisine des mousquetaires", "titre_programme": "Prog",
                          "genre": "Magazine"}]
    assert page.form_action == "/next" and page.form_fields == {"page": "1", "x": "y"}


def test_parse_notice_page_keeps_page_order_and_br_as_newlines():
    fields = parse_notice_page(NOTICE_HTML)
    assert [(f.position, f.code, f.label) for f in fields] == [(1, "NO", "ID Notice"), (2, "GEN", "Générique"),
                                                               (3, "RES", "Résumé")]
    assert fields[2].value_text == "Ligne 1\nLigne 2"


def test_split_items_splits_credits_into_role_and_name():
    gen = parse_notice_page(NOTICE_HTML)[1]
    assert [(i["role_code"], i["name"]) for i in split_items(gen)] == [("REA", "Jean Dupont"), ("PRE", "Maïté")]


def test_split_items_ignores_non_list_fields():
    assert split_items(Field(1, "TI", "Titre", "a ; b", "a ; b")) == []


def test_with_param_replaces_existing_value():
    assert with_param("https://x/y?a=1&nbLignes=50", nbLignes=500) == "https://x/y?a=1&nbLignes=500"


def test_search_url_exact_and_full_text():
    assert "itousti_exact" in search_url("FR3") and "itoustext" in search_url("FR3", exact_title=False)


def test_search_url_limits_the_broadcast_date():
    assert "datdif=%5B%2A+TO+31%2F12%2F1997%5D" in search_url("FR3")
    assert "datdif" not in search_url("FR3", until=None)


def test_default_searches_skip_the_regional_relays():
    labels = [label for label, _ in DEFAULT_SEARCHES]
    assert not any("Midi" in l or "Languedoc" in l for l in labels) and len(labels) == 4


def row(date="19/06/1992", collection="La cuisine des mousquetaires", programme=None):
    return {"date_diffusion": date, "titre_collection": collection, "titre_programme": programme}


def test_keep_result_row_is_permissive():
    assert keep_result_row(row())
    assert keep_result_row(row(collection=None))          # judged later, on its credits
    assert keep_result_row(row(collection="Magazine"))
    assert not keep_result_row(row(date="07/01/2023"))
    assert not keep_result_row(row(collection="Aquitaine actualités"))
    assert keep_result_row(row(programme="Les cuisines de France"))      # same show, filed under another programme


def test_parse_duration_gives_seconds_and_none_for_unknown():
    from la_cuisine_des_mousquetaires.core.ina import parse_duration
    assert [parse_duration(t) for t in ("00:13:06", "00:12:56:00", "0:40:12", "00:00:00:00", "24:00:00", "", None, "13 min")] \
        == [786, 776, 2412, None, None, None, None, None]
