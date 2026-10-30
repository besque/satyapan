"""Text normalisation for matching institution names written in many ways.

Complainants write "Kesarveni Inst. of Tech", "KIT Indore", "केसरवेणी इंजीनियरिंग कॉलेज" or "kesarvani
engg clg". Three forms make these comparable:
  * plain:    lower-case ASCII words, abbreviations expanded, Hindi generic words translated,
              other Devanagari transliterated (ITRANS) and vowel lengths folded;
  * distinct: plain minus generic words (college, engineering, institute, ...);
  * skeleton: consonant outline of each distinctive word ("neelkamal" and "nIlakamala" -> "nlkml"),
              which survives spelling and transliteration differences.
"""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

from indic_transliteration import sanscript

DEVANAGARI = re.compile(r"[ऀ-ॿ]+")

# Hindi words that carry the institution *type*, translated so they compare with English names.
HINDI_GENERIC = {
    "इंजीनियरिंग": "engineering", "अभियांत्रिकी": "engineering", "कॉलेज": "college", "कालेज": "college",
    "महाविद्यालय": "college", "संस्थान": "institute", "प्रौद्योगिकी": "technology", "तकनीकी": "technology",
    "टेक्नोलॉजी": "technology", "इंस्टीट्यूट": "institute", "प्रबंधन": "management", "फार्मेसी": "pharmacy",
    "विश्वविद्यालय": "university", "पॉलिटेक्निक": "polytechnic", "एवं": "and", "और": "and", "का": "of",
    "की": "of", "के": "of", "श्री": "sri", "विज्ञान": "science", "अनुसंधान": "research", "महिला": "women",
}

ABBREV = {
    "engg": "engineering", "engin": "engineering", "eng": "engineering", "clg": "college", "coll": "college",
    "colg": "college", "inst": "institute", "instt": "institute", "insti": "institute", "tech": "technology",
    "techn": "technology", "technol": "technology", "mgmt": "management", "mngmt": "management", "univ": "university",
    "polytech": "polytechnic", "pharm": "pharmacy", "sci": "science", "res": "research", "shri": "sri",
    "shree": "sri", "sree": "sri", "sr": "sri",
}

GENERIC = {
    "college", "engineering", "institute", "institution", "institutions", "of", "and", "the", "technology",
    "technological", "management", "science", "sciences", "research", "polytechnic", "pharmacy", "pharmaceutical",
    "studies", "school", "academy", "group", "university", "centre", "center", "education", "educational",
    "society", "trust", "private", "pvt", "ltd", "for", "in", "at", "campus", "applied", "professional",
    "advanced", "information", "computer", "architecture", "near", "road", "dist", "district", "my", "our",
}

# Place names in Devanagari (gazetteer), so "इंदौर" compares with "Indore".
PLACE_HI = {
    "इंदौर": "indore", "भोपाल": "bhopal", "जबलपुर": "jabalpur", "ग्वालियर": "gwalior", "रायपुर": "raipur",
    "बिलासपुर": "bilaspur", "लखनऊ": "lucknow", "कानपुर": "kanpur", "वाराणसी": "varanasi", "गाज़ियाबाद": "ghaziabad",
    "गाजियाबाद": "ghaziabad", "प्रयागराज": "prayagraj", "रांची": "ranchi", "पटना": "patna", "देहरादून": "dehradun",
    "जयपुर": "jaipur", "नोएडा": "noida", "मेरठ": "meerut", "आगरा": "agra",
}

TYPE_WORDS = {"engineering": "Engineering", "pharmacy": "Pharmacy", "management": "Management",
              "polytechnic": "Polytechnic", "architecture": "Architecture"}


@lru_cache(maxsize=8192)
def _translit(word: str) -> str:
    if word in HINDI_GENERIC:
        return HINDI_GENERIC[word]
    if word in PLACE_HI:
        return PLACE_HI[word]
    t = sanscript.transliterate(word, sanscript.DEVANAGARI, sanscript.ITRANS)
    t = t.replace("M", "n").replace("~N", "n").replace(".N", "n").replace(".h", "")
    return t


def fold(s: str) -> str:
    """Lower-case ASCII with vowel lengths folded ('ee'/'ii'/'I' -> 'i', 'aa'/'A' -> 'a', ...)."""
    s = s.replace("A", "a").replace("I", "i").replace("U", "u").replace("RRi", "ri")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    for a, b in (("aa", "a"), ("ee", "i"), ("ii", "i"), ("oo", "u"), ("uu", "u"), ("w", "v"), ("ph", "f"),
                 ("ksh", "ks"), ("x", "ks"), ("z", "j"), ("q", "k"), ("y", "i")):
        s = s.replace(a, b)
    return s


def plain_words(text: str) -> list[str]:
    text = DEVANAGARI.sub(lambda m: " " + _translit(m.group(0)) + " ", text or "")
    text = text.replace("&", " and ")
    words = re.findall(r"[A-Za-z0-9]+", text)
    out = []
    for w in words:
        lw = w.lower()
        if lw in ABBREV:
            out.append(ABBREV[lw])
        elif lw in GENERIC or lw.isdigit():
            out.append(lw)
        else:
            out.append(fold(lw if w.isupper() else w))
    return out


def distinct(words: list[str]) -> list[str]:
    return [w for w in words if w not in GENERIC and not w.isdigit() and len(w) > 1]


def skeleton(word: str) -> str:
    w = word
    for a, b in (("sh", "s"), ("ch", "c"), ("kh", "k"), ("gh", "g"), ("th", "t"), ("dh", "d"), ("bh", "b"),
                 ("jh", "j"), ("h", "")):
        w = w.replace(a, b)
    if not w:
        return ""
    head, rest = w[0], re.sub(r"[aeiou]", "", w[1:])
    out = head + rest
    return re.sub(r"(.)\1+", r"\1", out)


def initials(name: str) -> str:
    """Acronym the way colleges write it: 'B.M.S. College of Engineering' -> 'bmsce'."""
    parts = re.findall(r"[A-Za-z]+", name)
    return "".join(p[0] for p in parts if p.lower() not in {"of", "and", "the", "for", "in", "at"}).lower()


def type_words(words: list[str]) -> set[str]:
    return {TYPE_WORDS[w] for w in words if w in TYPE_WORDS}
