"""Spelling of the dish titles, which the INA typed by hand over ten years: one rule per recurring mistake.

The corrections are data (WORDS, PHRASES), applied to the listed title only, so the same notices always give the same
titles and a new correction is a new line here. A word is replaced whole and in any case; it keeps its initial capital.
"""
from __future__ import annotations

import re

# Misspelling -> spelling (lower case). Typos, missing accents and the ligatures oe -> œ.
WORDS = {
    "aperges": "asperges", "aumonière": "aumônière", "aumonières": "aumônières", "capres": "câpres", "cepes": "cèpes", "cêpes": "cèpes", "ceps": "cèpes",
    "coeur": "cœur", "coeurs": "cœurs", "boeuf": "bœuf", "boeufs": "bœufs", "oeuf": "œuf", "oeufs": "œufs",
    "croute": "croûte", "dombres": "dombrés", "dombies": "dombrés", "echalotte": "échalote", "echalottes": "échalotes",
    "échalotte": "échalote", "échalottes": "échalotes", "ecossaise": "écossaise", "ecrevisses": "écrevisses",
    "emilion": "émilion", "fete": "fête", "grac": "gras", "huitres": "huîtres", "meusclade": "mouclade",
    "moëlle": "moelle", "ocean": "océan", "papillottes": "papillotes", "papillotte": "papillote", "pate": "pâté",
    "paté": "pâté", "pomes": "pommes", "ragout": "ragoût", "ravigotte": "ravigote", "roti": "rôti",
    "salardaises": "sarladaises", "sarladaises": "sarladaises", "sariette": "sarriette", "soupé": "soupe", "steacks": "steaks", "truuite": "truite",
    "vinaigré": "vinaigre", "baëkeoffe": "baeckeoffe", "betisier": "bêtisier",
}

# Words that are lower case wherever they stand in a title (the first letter of the title is capitalised afterwards).
LOWER = {"écossaise", "sarladaises"}

# Several words, replaced before the words.
PHRASES = [
    (r"\bsace cavigote\b", "sauce ravigote"),
    (r"\bfois gras\b", "foie gras"),
    (r"\bdetoulouse\b", "de Toulouse"),
    (r"\ba (?=la\b|l')", "à "),
    # the scallops are plural and always "coquilles Saint-Jacques"
    (r"\bau (?=(?:coquilles? )?saint-jacques\b)", "aux "),
    (r"(?<!coquilles )(?<!coquille )\bsaint-jacques\b", "coquilles Saint-Jacques"),
]

# After "à la" / "à l'" comes a common noun or an adjective ("à l'antillaise", "à la bordelaise", "à l'armagnac").
PROPER_AFTER_A = {"Christophe"}
AFTER_A = re.compile(r"\b(à la |à l')([A-ZÀ-Ý])(\w*)")


def _word(m: re.Match) -> str:
    word = m[0]
    fixed = WORDS.get(word.lower())
    if fixed is None:
        return word
    if word[0].isupper() and fixed not in LOWER:
        fixed = fixed[0].upper() + fixed[1:]
    return fixed


def _after_a(m: re.Match) -> str:
    return m[0] if m[2] + m[3] in PROPER_AFTER_A else m[1] + m[2].lower() + m[3]


def correct(title: str) -> str:
    """The title with the known misspellings corrected and a capital kept on its first letter."""
    for pattern, replacement in PHRASES:
        title = re.sub(pattern, replacement, title, flags=re.I)
    title = re.sub(r"[^\W\d_]+", _word, title)
    title = AFTER_A.sub(_after_a, title)
    i = next((i for i, c in enumerate(title) if c.isalpha()), None)
    return title if i is None else title[:i] + title[i].upper() + title[i + 1:]
