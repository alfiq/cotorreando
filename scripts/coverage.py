"""Check the phonetic coverage of the calibration panels.

    python scripts/coverage.py CMUDICT_PATH

Spanish uses letter-to-sound rules (seseante, as in Latin America). English uses
the CMU Pronouncing Dictionary; download cmudict.dict from
https://github.com/cmusphinx/cmudict and pass its path.
"""

import re
import sys
import unicodedata
from pathlib import Path

DATASETS = Path(__file__).parent.parent / "cotorreando" / "lora" / "datasets"
ES = set("a e i o u p b t d k g m n ɲ f s x ʝ tʃ l ɾ r w j".split())
EN = set("AA AE AH AO AW AY B CH D DH EH ER EY F G HH IH IY JH K L M N NG OW OY P R S SH T TH UH UW "
         "V W Y Z ZH".split())


def panels(name: str) -> list[str]:
    lines = (DATASETS / name).read_text(encoding="utf-8").splitlines()
    return [line for line in lines if line.strip() and not line.startswith("#")]


def es_phones(word: str) -> list[str]:
    w = word.lower()
    for a, b in (("ch", "C"), ("ll", "J"), ("rr", "R"), ("qu", "k"), ("gue", "ge"), ("gui", "gi"),
                 ("güe", "we"), ("güi", "wi"), ("ge", "xe"), ("gi", "xi"), ("gé", "xé"), ("gí", "xí"),
                 ("ce", "se"), ("ci", "si"), ("cé", "sé"), ("cí", "sí"), ("c", "k"), ("z", "s"),
                 ("h", ""), ("v", "b"), ("j", "x"), ("y", "J")):
        w = w.replace(a, b)
    w = re.sub(r"^x(?=[oi])", "s", w)   # Xochimilco, Ximena
    w = re.sub(r"(?<=[aeiouáéíóú])x(?=[aeiouáéíóú])", "ks", w) if "méxi" not in w else w
    out, table = [], {"C": "tʃ", "J": "ʝ", "R": "r", "ñ": "ɲ", "r": "ɾ"}
    for i, c in enumerate(w):
        c = unicodedata.normalize("NFD", c)[0] if c != "ñ" else c
        next_vowel = i + 1 < len(w) and w[i + 1] in "aeoáéó"
        if c == "r" and i == 0:
            out.append("r")
        elif c in "iu" and next_vowel:
            out.append("j" if c == "i" else "w")
        elif c.isalpha():
            out.append(table.get(c, c))
    return out


def report(label: str, words: list[list[str]], inventory: set[str]) -> None:
    seen, pairs = set(), set()
    for phones in words:
        seen.update(phones)
        pairs.update(zip(phones, phones[1:]))
    print(f"{label}: {len(seen & inventory)}/{len(inventory)} phones, {len(pairs)} distinct within-word "
          f"diphones. Missing: {sorted(inventory - seen) or 'none'}")


def main() -> None:
    es = [es_phones(w) for p in panels("es.txt") for w in re.findall(r"[^\W\d_]+", p)]
    report("es", es, ES)
    entries = {}
    for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
        word, *phones = line.split("#")[0].split()
        entries.setdefault(word, [re.sub(r"\d", "", ph) for ph in phones])
    en, unknown = [], set()
    for word in (w.lower() for p in panels("en.txt") for w in re.findall(r"[A-Za-z']+", p)):
        en.append(entries[word]) if word in entries else unknown.add(word)
    report("en", en, EN)
    if unknown:
        print("Not in CMUdict:", sorted(unknown))
    for name in ("es.txt", "en.txt"):
        counts = [len(p.split()) for p in panels(name)]
        print(f"{name}: {len(counts)} panels, {sum(counts)} words, ~{sum(counts) / 2.4 / 60:.1f} min aloud")


if __name__ == "__main__":
    main()
