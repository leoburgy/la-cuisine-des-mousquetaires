from la_cuisine_des_mousquetaires.core.episodes import SHOW, select_episodes


def row(path, chaine, date, title, collection=SHOW, pre=None, heure="11:00:00", programme=None):
    return {"notice_path": path, "chaine": chaine, "date_iso": date, "heure_diffusion": heure,
            "titre_propre": title, "titre_programme": programme, "titre_collection": collection, "pre": pre}


def test_other_programmes_are_dropped_unless_presented_by_a_known_presenter():
    rows = [row("a", "France 3 Aquitaine", "1995-01-01", "12-13", collection="Aquitaine actualités"),
            row("b", "France 3 Poitou Charente", "1983-10-27", "Magazine", collection="Magazine", pre="Ordonez Maïté"),
            row("c", "France 3", "1995-01-02", "Cassoulet")]
    assert [r["notice_path"] for r in select_episodes(rows)] == ["b", "c"]


def test_reruns_merge_into_the_first_run():
    rows = [row("nat", "France 3", "1995-02-09", "[Le pot au feu]"),
            row("aq", "France 3 Aquitaine", "1995-01-07", "LE POT AU FEU", pre="Ordonez Maïté"),
            row("pc", "France 3 Poitou Charente", "1996-02-01", "le pot au feu"),
            row("late", "France 3", "1999-07-02", "Le pot au feu")]
    [ep] = select_episodes(rows)
    assert (ep["notice_path"], ep["premiere_date"], ep["n_diffusions"]) == ("aq", "1995-01-07", 4)
    assert ep["presentateurs"] == "Ordonez Maïté"


def test_only_the_first_run_is_listed_and_the_other_series_is_dropped():
    rows = [row("revival", "France 3", "2023-05-05", "Poulet basquaise", pre="Mignot Fabrice"),
            row("rerun", "France 3", "1999-07-02", "Carré de boeuf"),
            row("ok", "FR3", "1992-03-18", "Tourte de lapin")]
    assert [r["notice_path"] for r in select_episodes(rows)] == ["ok"]


def test_titles_differing_by_articles_plurals_accents_or_punctuation_are_one_episode():
    rows = [row("a", "France 3 Aquitaine", "1989-12-12", "Les homards à la rionnaise"),
            row("b", "FR3", "1992-04-10", "Homard à la Rionnaise"),
            row("c", "France 3", "1994-01-21", "[Lotte aux anchois - lotte en ratatouille]"),
            row("d", "France 3 Aquitaine", "1995-10-18", "Lotte aux anchois, lotte en ratatouille")]
    assert [(r["notice_path"], r["n_diffusions"]) for r in select_episodes(rows)] == [("a", 2), ("c", 2)]


def test_the_episode_gets_the_best_youtube_match_of_any_of_its_broadcasts():
    rows = [{**row("aq", "France 3 Aquitaine", "1995-01-07", "Pot au feu"), "youtube_url": None},
            {**row("nat", "France 3", "1995-02-09", "Pot au feu"), "youtube_url": "u1", "youtube_duree_s": 720,
             "match_confidence": "low", "match_score": 0.5},
            {**row("nat2", "France 3", "1995-03-09", "Pot au feu"), "youtube_url": "u2", "youtube_duree_s": 780,
             "match_confidence": "high", "match_score": 0.9}]
    [ep] = select_episodes(rows)
    assert (ep["notice_path"], ep["youtube_url"], ep["match_confidence"]) == ("aq", "u2", "high")


def test_an_episode_without_a_match_has_empty_youtube_fields():
    [ep] = select_episodes([row("a", "FR3", "1995-01-07", "Pot au feu")])
    assert ep["youtube_url"] is None


def test_a_placeholder_date_follows_the_dated_notice_it_abbreviates():
    rows = [row("ph", "FR3", "1984-01-01", "[le sanglier]", heure="00:00:00:00"),
            row("rerun", "France 3", "1988-11-08", "Le sanglier"),
            row("real", "France 3 Aquitaine", "1984-09-17", "Les gibiers et leurs terrines : le sanglier")]
    [ep] = select_episodes(rows)
    assert (ep["notice_path"], ep["premiere_date"], ep["date_incertaine"], ep["n_diffusions"]) == ("real", "1984-09-17", "", 3)


def test_an_unresolved_placeholder_year_beats_a_later_rerun_and_is_flagged():
    rows = [row("ph", "FR3", "1983-01-01", "Les confits", heure="00:00:00:00"),
            row("rerun", "France 3 Aquitaine", "1986-08-01", "Les confits")]
    [ep] = select_episodes(rows)
    assert (ep["premiere_date"], ep["date_incertaine"]) == ("1983-01-01", "oui")


def test_a_first_of_january_with_a_real_time_is_not_a_placeholder():
    [ep] = select_episodes([row("a", "France 3", "1993-01-01", "Salade landaise", heure="11:42:53")])
    assert (ep["premiere_date"], ep["date_incertaine"]) == ("1993-01-01", "")


def test_the_wrapper_notice_of_a_whole_magazine_is_dropped():
    rows = [row("wrap", "FR3", "1984-01-01", "La cuisine des mousquetaires : [émission du 1 janvier 1984]"),
            row("seg", "France 3 Aquitaine", "1984-09-17", "Le sanglier")]
    assert [r["notice_path"] for r in select_episodes(rows)] == ["seg"]


def test_blank_fields_of_the_preferred_notice_are_completed_from_the_other_broadcasts():
    aq = {**row("aq", "France 3 Aquitaine", "1986-08-11", "La cuisine des mousquetaires : les foies en sauce",
                heure="00:00:00"), "duree_s": 825, "resume_documentaire": None}
    fr3 = {**row("fr3", "FR3", "1986-08-11", "[les foies en sauce]", heure="17:32:35"), "duree_s": 825,
           "resume_documentaire": "Un foie aux raisins"}
    other_day = {**row("late", "France 3", "1990-01-01", "[les foies en sauce]", heure="12:00:00"), "duree_s": None,
                 "resume_documentaire": None}
    [ep] = select_episodes([aq, fr3, other_day])
    assert (ep["notice_path"], ep["heure_diffusion"], ep["resume_documentaire"], ep["n_diffusions"]) == \
           ("aq", "17:32:35", "Un foie aux raisins", 3)
    [ep] = select_episodes([aq, other_day])
    assert ep["heure_diffusion"] == "00:00:00"


def test_the_bare_show_title_names_no_episode():
    rows = [row("a", "France 3 Aquitaine", "1989-09-01", "La cuisine des mousquetaires"),
            row("b", "France 3", "1989-09-02", "La cuisine des mousquetaires : Pot au feu")]
    assert [r["notice_path"] for r in select_episodes(rows)] == ["b"]


def test_a_series_description_is_not_an_episode():
    series = {**row("series", "France 3 Aquitaine", "1984-09-17", "Présentation de la série"),
              "type_description": "Collection d'émissions simples"}
    ep = {**row("ep", "France 3 Aquitaine", "1989-09-01", "Pot au feu"),
          "type_description": "Emission simple"}
    assert [r["notice_path"] for r in select_episodes([series, ep])] == ["ep"]


def test_one_title_contained_in_the_other_with_the_same_duration_is_a_rerun():
    rows = [{**row("da", "France 3", "1994-10-03", "La queue de boeuf aux lentilles"), "duree_s": 786},
            {**row("re", "France 3 Aquitaine", "1997-04-05",
                   "Queue de boeuf aux lentilles, sauté de queue de boeuf aux pois chiches"), "duree_s": 786},
            {**row("other", "France 3", "1995-01-01", "Queue de boeuf aux lentilles et riz"), "duree_s": 720}]
    eps = select_episodes(rows)
    assert [(r["premiere_date"], r["n_diffusions"]) for r in eps] == [("1994-10-03", 2), ("1995-01-01", 1)]


def test_a_contained_title_with_another_duration_stays_separate():
    rows = [{**row("a", "France 3", "1994-10-03", "Canard farci"), "duree_s": 786},
            {**row("b", "France 3", "1997-04-05", "Canard farci au madère"), "duree_s": 725}]
    assert len(select_episodes(rows)) == 2


def test_a_two_word_title_needs_the_exact_duration_to_merge():
    rows = [{**row("a", "France 3 Aquitaine", "1990-06-19", "Les foies de veau"), "duree_s": 814},
            {**row("b", "France 3", "1995-05-16", "Filet de porc à la scandinave et foie de veau aux fruits"), "duree_s": 812}]
    assert len(select_episodes(rows)) == 2


def test_the_first_to_air_wins_whether_national_or_regional_and_the_reruns_are_referred_to():
    rows = [row("reg", "France 3 Aquitaine", "1994-05-04", "Cailles aux kiwis"),
            row("nat", "France 3", "1993-05-11", "[Cailles aux kiwis]"),
            row("nat2", "France 3", "1995-01-01", "Cailles aux kiwis")]
    [ep] = select_episodes(rows)
    assert (ep["notice_path"], ep["chaine"], ep["premiere_date"]) == ("nat", "France 3", "1993-05-11")
    assert ep["autres_diffusions"] == "reg ; nat2"
    assert ep["titre_propre"] == "Cailles aux kiwis"       # the first run's title was a bracketed provisional one


def test_a_regional_and_a_national_broadcast_of_the_same_day_go_to_the_regional_one():
    rows = [row("nat", "France 3", "1993-05-11", "Cailles aux kiwis"),
            row("reg", "France 3 Aquitaine", "1993-05-11", "Cailles aux kiwis")]
    [ep] = select_episodes(rows)
    assert ep["notice_path"] == "reg"


def test_the_episode_says_where_it_first_aired_and_on_which_channels_and_until_when():
    rows = [row("nat", "France 3", "1993-05-11", "Cailles aux kiwis"),
            row("reg", "France 3 Aquitaine", "1994-05-04", "Cailles aux kiwis"),
            row("nat2", "France 3", "1995-01-01", "Cailles aux kiwis", heure="11:00:00")]
    [ep] = select_episodes(rows)
    assert (ep["type_premiere_diffusion"], ep["chaines"], ep["derniere_diffusion"]) == \
           ("nationale", "France 3 ; France 3 Aquitaine", "1995-01-01")


def test_the_rerun_of_the_1983_series_merges_despite_other_titles():
    rows = [{**row("pc", "France 3 Poitou Charente", "1983-10-20", "La cuisine des mousquetaires : sanquette, magret et pommes de terre sautées"), "duree_s": 806},
            {**row("aq", "France 3 Aquitaine", "1986-08-08", "La cuisine des mousquetaires : les magrets"), "duree_s": 806},
            {**row("fr3", "FR3", "1986-08-08", "Les magrets et la sanguette"), "duree_s": 806},
            {**row("sauce", "France 3 Aquitaine", "1986-08-11", "La cuisine des mousquetaires : les foies en sauce"), "duree_s": 825},
            {**row("raisin", "France 3 Poitou Charente", "1983-11-24", "La cuisine des mousquetaires : foies de canard au raisin et au sauterne"), "duree_s": 823},
            {**row("other", "France 3", "1990-01-01", "Magret de canard grillé"), "duree_s": 806}]
    eps = select_episodes(rows)
    assert [(r["notice_path"], r["n_diffusions"]) for r in eps] == [("pc", 3), ("raisin", 2), ("other", 1)]


def test_a_one_word_title_does_not_merge_with_every_title_that_contains_it():
    rows = [{**row("a", "France 3", "1993-01-01", "Les foies", heure="11:00:00"), "duree_s": 786},
            {**row("b", "France 3", "1995-02-02", "Dodine de volaille au foie gras"), "duree_s": 786}]
    assert len(select_episodes(rows)) == 2


def test_spelling_variants_of_a_word_do_not_prevent_a_rerun_merge():
    rows = [{**row("a", "France 3 Aquitaine", "1985-10-04", "Cêpes Bordelais et magret de canard"), "duree_s": 804},
            {**row("b", "FR3", "1986-08-14", "Les cèpes à la Bordelaise et le magret de canard farci au foie gras et aux cèpes"), "duree_s": 804}]
    assert [(r["notice_path"], r["n_diffusions"]) for r in select_episodes(rows)] == [("a", 2)]


def test_a_notice_titled_with_the_show_name_is_kept_even_without_collection_or_credits():
    [ep] = select_episodes([row("raisin", "France 3 Poitou Charente", "1983-11-24",
                                "La cuisine des mousquetaires : foies de canard au raisin", collection="Magazine")])
    assert ep["notice_path"] == "raisin"


def test_a_summary_naming_the_repeated_broadcast_attaches_the_notice_to_it():
    rows = [{**row("first", "France 3 Aquitaine", "1988-01-20", "Les soupes de notre région"), "resume_documentaire": "Maïté s'attaque aux soupes"},
            {**row("rerun", "France 3 Aquitaine", "1988-12-27", "Soupes de nos régions"), "resume_documentaire": "Rediffusino du 20/01/1988"}]
    [ep] = select_episodes(rows)
    assert (ep["notice_path"], ep["n_diffusions"], ep["autres_diffusions"]) == ("first", 2, "rerun")


def test_a_rerun_of_the_first_episode_goes_to_the_earliest_episode():
    rows = [{**row("one", "France 3 Poitou Charente", "1983-10-20", "La cuisine des mousquetaires : sanquette"), "resume_documentaire": None},
            {**row("two", "France 3 Poitou Charente", "1983-10-27", "La cuisine des mousquetaires : les foies de canard"), "resume_documentaire": None},
            {**row("rerun", "France 3 Aquitaine", "1988-12-20", "La cuisine des mousquetaires, 1er épisode"),
             "resume_documentaire": "Rediffusion du 1er épisode de l'émission (1983)."}]
    eps = select_episodes(rows)
    assert [(r["notice_path"], r["n_diffusions"]) for r in eps] == [("one", 2), ("two", 1)]
    assert eps[0]["resume_documentaire"] is None or "Rediffusion" not in eps[0]["resume_documentaire"]


def test_the_video_of_the_first_run_wins_unless_its_match_is_doubtful():
    def with_video(r, url, conf, score):
        return {**r, "youtube_url": url, "youtube_duree_s": 780, "match_confidence": conf, "match_score": score}
    first = with_video(row("pc", "France 3 Poitou Charente", "1983-10-20", "Sanquette"), "u1", "medium", 0.5)
    rerun = with_video(row("aq", "France 3 Aquitaine", "1986-08-08", "Sanquette"), "u2", "high", 0.74)
    assert select_episodes([first, rerun])[0]["youtube_url"] == "u1"
    assert select_episodes([{**first, "match_confidence": "low"}, rerun])[0]["youtube_url"] == "u2"


def test_the_listed_title_has_no_show_prefix_and_starts_with_a_capital():
    rows = [row("a", "France 3 Poitou Charente", "1983-10-20", "La cuisine des mousquetaires : sanquette, magret"),
            row("b", "France 3 Poitou Charente", "1983-11-10", "La cuisine des mousquetaire : le confit de canard"),
            row("c", "France 3", "1992-01-01", "[le sanglier]", heure="11:00:00")]
    assert [r["titre_propre"] for r in select_episodes(rows)] == ["Sanquette, magret", "Le confit de canard", "Le sanglier"]


def test_the_listed_title_loses_its_brackets_and_capitals_when_the_catalogue_shouted():
    rows = [row("a", "France 3", "1993-06-18", "[TOURIN BLANC GASCON - SOUPE AU VIN]", heure="11:00:00"),
            row("b", "France 3", "1993-06-19", "[Darnes d'esturgeon - darnes à la rionnaise]", heure="11:00:00"),
            row("c", "France 3", "1993-06-20", "Brochettes [de] porc", heure="11:00:00")]
    assert [r["titre_propre"] for r in select_episodes(rows)] == [
        "Tourin blanc gascon - soupe au vin", "Darnes d'esturgeon - darnes à la rionnaise", "Brochettes [de] porc"]


def test_a_wrapper_titled_without_brackets_is_dropped_too():
    rows = [row("wrap", "FR3", "1992-03-17", "Les cuisines de France : émission du 17 mars 1992"),
            row("seg", "FR3", "1992-03-17", "Pot au feu", heure="11:00:00")]
    assert [r["notice_path"] for r in select_episodes(rows)] == ["seg"]


def test_the_listed_title_loses_the_show_name_with_its_date_or_series_but_other_prefixes_stay():
    rows = [row("a", "France 3 Aquitaine", "1991-05-07", "La cuisine des mousquetaires du 7 mai 1991 : spéciale centième"),
            row("b", "France 3 Aquitaine", "1991-09-17", "La cuisine des mousquetaires du 17 septembre 1991 : spéciale centième"),
            row("c", "France 3 Aquitaine", "1988-04-20", "La cuisine des mousquetaires, série 2 : Perdrix et faisans"),
            row("d", "France 3 Aquitaine", "1993-06-25", "Spéciale Francis Garcia : truites en brochette"),
            row("e", "France 3 Aquitaine", "1990-05-22", "La cuisine des mousquetaires du 22 mai 1990")]
    assert [r["titre_propre"] for r in select_episodes(rows)] == [
        "Perdrix et faisans", "Émission du 22 mai 1990 (titre non renseigné)", "Spéciale centième", "Spéciale centième",
        "Spéciale Francis Garcia : truites en brochette"]


def test_the_long_notices_of_the_other_programme_are_not_episodes():
    rows = [row("DA_CPC92000335", "FR3", "1992-01-07", "Spéciale centième cuisine des Mousquetaires"),
            row("ok", "FR3", "1992-01-08", "Pot au feu", heure="11:00:00")]
    assert [r["notice_path"] for r in select_episodes(rows)] == ["ok"]


def test_a_notice_of_the_other_programme_is_kept_only_with_the_show_s_credits():
    def cdf(path, day, title, generique, pre=None):
        return {**row(path, "FR3", day, title, pre=pre, heure="11:00:00", programme="Les cuisines de France"), "generique": generique}
    rows = [cdf("show", "1992-04-21", "Carbonnade farcie", "REA,Bellot Patrice"),
            cdf("duo", "1992-04-22", "Araignée farcie", "REA,Autre ; PAR,Ordonez Maïté", pre="Ordonez Maïté"),
            cdf("chef", "1992-03-24", "Cuisinez avec Daniel Ancel", "REA,Hattet Alain ; PAR,Ancel Daniel", pre="Ancel Daniel")]
    assert [r["notice_path"] for r in select_episodes(rows)] == ["show", "duo"]


def test_notices_listed_by_hand_as_one_episode_are_merged(monkeypatch):
    from la_cuisine_des_mousquetaires.core import episodes
    monkeypatch.setattr(episodes, "SAME_EPISODE", [{"x", "y"}])
    rows = [row("x", "France 3", "1991-10-04", "Salmis au foie"), row("y", "FR3", "1992-03-17", "Palombes et grives")]
    [ep] = select_episodes(rows)
    assert (ep["notice_path"], ep["n_diffusions"]) == ("x", 2)


def test_alike_titles_with_close_durations_are_one_episode():
    rows = [{**row("a", "France 3", "1993-12-10", "Magrets au cidre, jambon au vinaigre framboise et petits oiseaux"), "duree_s": 751},
            {**row("b", "France 3", "1994-12-28", "Magrets au cidre, jambon chaud au vinaigré de framboise, oiseaux"), "duree_s": 752}]
    [ep] = select_episodes(rows)
    assert (ep["notice_path"], ep["n_diffusions"]) == ("a", 2)


def test_alike_titles_with_other_durations_stay_apart():
    rows = [{**row("a", "France 3", "1989-01-24", "Brochet au beurre blanc et pain de brochet"), "duree_s": 805},
            {**row("b", "France 3", "1994-11-25", "Brochet au beurre blanc et brochet farci"), "duree_s": 787}]
    assert len(select_episodes(rows)) == 2


def test_titles_that_only_give_a_date_are_not_compared():
    rows = [{**row("a", "France 3", "1992-05-25", "La cuisine des mousquetaires du 25 mai 1992"), "duree_s": 780},
            {**row("b", "France 3", "1992-06-26", "La cuisine des mousquetaires du 26 juin 1992"), "duree_s": 780}]
    assert len(select_episodes(rows)) == 2


def test_durations_are_listed_as_minutes_and_seconds():
    rows = [{**row("a", "France 3", "1995-01-24", "Cassoulet"), "duree_s": 764},
            {**row("b", "France 3", "1991-05-07", "Poule au pot"), "duree_s": 2412},
            {**row("c", "France 3", "1992-05-22", "Garbure"), "duree_s": None},
            {**row("d", "France 3", "1992-06-22", "Tourin"), "duree_s": None, "youtube_url": "u", "youtube_duree_s": 786,
             "match_confidence": "high", "match_score": 1}]
    got = {r["notice_path"]: (r["duree"], r["youtube_duree"]) for r in select_episodes(rows)}
    assert got == {"a": ("12:44", None), "b": ("40:12", None), "c": ("", None), "d": ("", "13:06")}


def test_a_title_that_only_gives_the_date_is_listed_as_unnamed():
    [ep] = select_episodes([row("a", "France 3 Aquitaine", "1990-05-22", "La cuisine des mousquetaires du 22 mai 1990")])
    assert ep["titre_propre"] == "Émission du 22 mai 1990 (titre non renseigné)"
    [ep] = select_episodes([row("b", "France 3 Aquitaine", "1991-04-23", "La cuisine des mousquetaire du 23 avril 1991 -incomplet")])
    assert ep["titre_propre"] == "Émission du 23 avril 1991 (incomplète, titre non renseigné)"


def test_the_specials_with_a_chef_are_written_alike():
    titles = ["Spécial Jacques Le Divellec : salade", "Spéciale avec R. VERGE : fricassée", "Spécial Didier Oudill: papillotes",
              "Spéciale Jean BARDET : rognons", "Spéciale avec Didier OUDILL", "Spéciale Elisabeth de ROZIERES : langouste",
              "Spécial Roger VERGE - fricassée de moules", "Spéciale dix ans", "Spéciale centième"]
    from la_cuisine_des_mousquetaires.core.episodes import display_title
    assert [display_title(t) for t in titles] == [
        "Spéciale Jacques Le Divellec : salade", "Spéciale Roger Vergé : fricassée", "Spéciale Didier Oudill : papillotes",
        "Spéciale Jean Bardet : rognons", "Spéciale Didier Oudill", "Spéciale Elisabeth de Rozieres : langouste",
        "Spéciale Roger Vergé : fricassée de moules", "Spéciale dix ans", "Spéciale centième"]


def test_saints_are_hyphenated_and_capitals_are_lowered():
    from la_cuisine_des_mousquetaires.core.episodes import display_title
    titles = ["Coquilles Saint Jacques et st jacques", "Côtelettes SAINT HUBERT", "Tartines St-Jean", "Poires Sainte Anne",
              "Ste Foy", "Henri IV et saint et sauce", "Poulet à la CHRISTOPHE"]
    assert [display_title(t) for t in titles] == [
        "Coquilles Saint-Jacques et Saint-Jacques", "Côtelettes Saint-Hubert", "Tartines Saint-Jean", "Poires Sainte-Anne",
        "Sainte-Foy", "Henri IV et saint et sauce", "Poulet à la Christophe"]


def test_reruns_typed_with_other_misspellings_merge_whatever_their_durations():
    rows = [{**row("a", "France 3", "1989-09-26", "Coquilles St Jacques en papillottes et à l'oseille"), "duree_s": 885},
            {**row("b", "France 3", "1992-04-10", "Coquilles Saint Jacques en papillotes et à l'oseille"), "duree_s": 720}]
    [ep] = select_episodes(rows)
    assert (ep["notice_path"], ep["n_diffusions"]) == ("a", 2)
