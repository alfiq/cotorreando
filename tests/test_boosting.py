"""The phrase-boosting tree: scores follow NeMo's formula, and leaving a phrase gives its bonus back."""

import math

import numpy as np
import pytest

from cotorreando.boosting import BoostingTree, PhraseTokenizer

DEPTH2 = 2.0 + math.log(2)      # bonus of the second piece of a phrase
DEPTH3 = 2.0 + math.log(3)


@pytest.fixture
def tree():
    # "1 2 3" and "1 2 4" share a prefix; "5" is a one-piece phrase with alpha 2
    return BoostingTree([[1, 2, 3], [1, 2, 4], [5]], [1.0, 1.0, 2.0], 8)


def test_root_scores_reward_first_pieces_only(tree):
    scores = tree.scores(0)
    assert scores[1] == pytest.approx(1.0) and scores[5] == pytest.approx(2.0)
    assert scores[[0, 2, 3, 4, 6, 7]].tolist() == [0.0] * 6


def test_scores_dtype_shape_and_cache(tree):
    scores = tree.scores(0)
    assert scores.dtype == np.float32 and scores.shape == (8,)
    assert tree.scores(0) is scores


def test_walking_a_phrase_increases_the_bonus(tree):
    s1 = tree.next(0, 1)
    assert tree.scores(s1)[2] == pytest.approx(DEPTH2)
    s2 = tree.next(s1, 2)
    assert tree.scores(s2)[3] == pytest.approx(DEPTH3)
    assert tree.scores(s2)[4] == pytest.approx(DEPTH3)      # the shared prefix serves both phrases


def test_leaving_a_phrase_gives_the_bonus_back(tree):
    s1 = tree.next(0, 1)
    # a piece that matches nothing costs the earned bonus (the backoff arc) plus unk_score
    assert tree.scores(s1)[7] == pytest.approx(-1.0)
    s2 = tree.next(s1, 2)
    assert tree.scores(s2)[7] == pytest.approx(-(1.0 + DEPTH2))
    # a piece that starts another phrase: back off, then earn its first-piece bonus
    assert tree.scores(s2)[5] == pytest.approx(-(1.0 + DEPTH2) + 2.0)


def test_finishing_a_phrase_keeps_it(tree):
    s = tree.next(0, 5)
    assert np.array_equal(tree.scores(s), tree.scores(0))


def test_next_transitions_and_backoff(tree):
    s1 = tree.next(0, 1)
    s2 = tree.next(s1, 2)
    assert s1 != 0 and s2 != s1
    assert tree.next(s2, 3) != 0 and tree.next(s2, 3) != tree.next(s2, 4)
    assert tree.next(s2, 7) == 0           # unrelated piece: back to the root
    assert tree.next(0, 7) == 0
    assert tree.next(s1, 5) == tree.next(0, 5)      # leaves the phrase and starts the other one


def test_empty_tree_scores_zero():
    empty = BoostingTree([], [], 4)
    assert empty.scores(0).tolist() == [0.0] * 4 and empty.next(0, 1) == 0


def test_shared_prefix_takes_the_largest_alpha():
    low = BoostingTree([[1, 2]], [1.0], 4).scores(0)[1]
    mixed = BoostingTree([[1, 2], [1, 3]], [1.0, 3.0], 4).scores(0)[1]
    assert low == pytest.approx(1.0) and mixed == pytest.approx(3.0)


def test_cache_is_bounded(tree, monkeypatch):
    monkeypatch.setattr("cotorreando.boosting.MAX_CACHED", 2)
    for state in range(5):
        tree.scores(state)
    assert len(tree._scores) <= 2


def test_phrase_tokenizer(tmp_path):
    from tokenizers import Tokenizer
    from tokenizers.models import WordLevel
    from tokenizers.pre_tokenizers import Whitespace
    base = Tokenizer(WordLevel({"[UNK]": 0, "hola": 1, "mundo": 2}, unk_token="[UNK]"))
    base.pre_tokenizer = Whitespace()
    path = tmp_path / "tokenizer.json"
    base.save(str(path))
    tokenize = PhraseTokenizer(path)
    assert tokenize("hola mundo") == [1, 2]
    assert tokenize("hola desconocido") == [1, 0]
    assert tokenize("") == []
