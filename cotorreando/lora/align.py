"""Follow someone reading a known text from the words the recognizer has heard."""

from __future__ import annotations

import difflib
import re
import unicodedata

WINDOW = 8   # how far ahead a heard word may jump (the reader skipped or it was misheard)


def normalize(word: str) -> str:
    word = unicodedata.normalize("NFD", word.lower())
    return "".join(c for c in word if c.isalnum())


def split_words(text: str) -> list[str]:
    return text.split()


def _matches(heard: str, target: str) -> bool:
    if len(target) < 3:
        return heard == target
    return difflib.SequenceMatcher(None, heard, target).ratio() >= 0.7


class Follower:
    """``position`` is how many words of the text have been read so far."""

    def __init__(self, text: str):
        self.targets = [normalize(w) for w in split_words(text)]
        self.position = 0

    def hear(self, text: str) -> int:
        for heard in map(normalize, re.split(r"\s+", text.strip())):
            if not heard:
                continue
            stop = min(self.position + WINDOW, len(self.targets))
            for i in range(self.position, stop):
                if _matches(heard, self.targets[i]):
                    self.position = i + 1
                    break
        return self.position


def word_errors(reference: str, heard: str) -> tuple[int, int]:
    """Edit distance in words, and the number of reference words."""
    a = [w for w in map(normalize, reference.split()) if w]
    b = [w for w in map(normalize, heard.split()) if w]
    row = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        prev, row[0] = row[0], i
        for j, y in enumerate(b, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (x != y))
    return row[-1], len(a)
