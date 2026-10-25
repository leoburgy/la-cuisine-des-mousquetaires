import pytest

from la_cuisine_des_mousquetaires.core.spelling import WORDS, correct


@pytest.mark.parametrize("raw, expected", [
    ("Tête de veau sace cavigote", "Tête de veau sauce ravigote"),
    ("Tête de veau sauce ravigotte", "Tête de veau sauce ravigote"),
    ("Langouste a l'Antillaise aux petits dombres", "Langouste à l'antillaise aux petits dombrés"),
    ("Poulet à la Bordelaise", "Poulet à la bordelaise"),
    ("Chapon à la Christophe", "Chapon à la Christophe"),
    ("Ecrevisses et echalotte", "Écrevisses et échalote"),
    ("Coquilles aux Cêpes et cepes", "Coquilles aux Cèpes et cèpes"),
    ("Pommes Sarladaises et pommes salardaises", "Pommes sarladaises et pommes sarladaises"),
    ("Ecossaise", "Écossaise"),
    ("Soles à l'Ecossaise", "Soles à l'écossaise"),
    ("Foies de canard grac, fois gras", "Foies de canard gras, foie gras"),
    ("Coeur de boeuf aux oeufs", "Cœur de bœuf aux œufs"),
    ("Saucisse deToulouse, steacks", "Saucisse de Toulouse, steaks"),
    ("Betisier", "Bêtisier"),
    ("Baëkeoffe et rognons", "Baeckeoffe et rognons"),
    ("Tarte aux pomes et capres sariette", "Tarte aux pommes et câpres sarriette"),
    ("Pâté à la grecque", "Pâté à la grecque"),
])
def test_known_misspellings_are_corrected(raw, expected):
    assert correct(raw) == expected


def test_a_correction_never_changes_a_corrected_word():
    assert all(correct(fixed) == fixed.capitalize() for fixed in set(WORDS.values()))
