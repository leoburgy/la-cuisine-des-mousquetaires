from la_cuisine_des_mousquetaires.core.ina import (parse_list_page, parse_notice_page, search_url, split_items,
                                                   with_param, Field)

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
