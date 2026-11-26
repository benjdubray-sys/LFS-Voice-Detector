"""Encodage du texte pour le chat de LFS.

LFS n'utilise pas Unicode dans le chat : chaque message est dans une page de code
Windows, que l'on sélectionne avec un code d'échappement en début de message
(^L latin, ^E Europe centrale, ^B balte, ^G grec, ^C cyrillique).
Les caractères non représentables sont translittérés (accent retiré) ou remplacés par '?'.
"""
import unicodedata

CP = {}


def _reg(codec, esc, langs):
    for lang in langs:
        CP[lang] = (codec, esc)


_reg("cp1252", "^L", "en fr es de it pt nl da sv fi ga".split())
_reg("cp1250", "^E", "cs hu pl sk sl hr ro mt".split())
_reg("cp1257", "^B", "et lt lv".split())
_reg("cp1253", "^G", ["el"])
_reg("cp1251", "^C", ["bg"])

TRANSLIT = {
    "ħ": "h", "Ħ": "H", "ġ": "g", "Ġ": "G", "ċ": "c", "Ċ": "C",   # maltais
    "ș": "ş", "Ș": "Ş", "ț": "ţ", "Ț": "Ţ",                       # roumain (virgule -> cédille)
    "’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-", "…": "...",
}


def uses_latin1(lang):
    return CP.get(lang, CP["en"])[0] == "cp1252"


def _enc_char(ch, codec):
    try:
        return ch.encode(codec)
    except UnicodeEncodeError:
        pass
    alt = TRANSLIT.get(ch)
    if alt:
        try:
            return alt.encode(codec)
        except UnicodeEncodeError:
            pass
    base = "".join(c for c in unicodedata.normalize("NFKD", ch) if not unicodedata.combining(c))
    if base:
        try:
            return base.encode(codec)
        except UnicodeEncodeError:
            pass
    return b"?"


def _enc(text, codec):
    return b"".join(_enc_char(ch, codec) for ch in text)


def sanitize(text):
    """Retire ce qui a un sens spécial dans le chat de LFS."""
    text = text.replace("^", "").replace("|", " ")
    text = " ".join(text.split())
    return text.lstrip("/ ")  # un "/" initial serait exécuté comme une commande


def chunks(text, lang, max_bytes=95):
    """Découpe le texte en messages (octets) <= max_bytes, chacun préfixé de la page de code."""
    codec, esc = CP.get(lang, CP["en"])
    prefix = esc.encode("ascii")
    budget = max_bytes - len(prefix)
    out, cur = [], b""
    for word in sanitize(text).split(" "):
        if not word:
            continue
        wb = _enc(word, codec)
        while len(wb) > budget:  # mot plus long qu'un message (pages de code à 1 octet/caractère)
            if cur:
                out.append(cur)
                cur = b""
            out.append(wb[:budget])
            wb = wb[budget:]
        if not wb:
            continue
        if not cur:
            cur = wb
        elif len(cur) + 1 + len(wb) <= budget:
            cur += b" " + wb
        else:
            out.append(cur)
            cur = wb
    if cur:
        out.append(cur)
    return [prefix + c for c in out]
