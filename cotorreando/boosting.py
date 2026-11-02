"""Phrase boosting for the decoder: a port of NVIDIA NeMo's GPU-PB boosting tree.

Ported from NeMo (Apache 2.0), ``context_graph_universal.py`` (ContextGraph.build,
_fill_fail_output, _get_token_score) and ``boosting_graph_batched.py``
(BoostingTreeStorage, advance), in the "default" BPE mode with non-uniform weights.
Phrases are tokenised with the model's own tokenizer, so a phrase becomes the same
pieces the decoder emits.

Each piece of a phrase earns a bonus: ``context_score`` for the first one and
``context_score * depth_scaling + ln(depth + 1)`` for the next ones, all times the
phrase's alpha. Leaving a phrase half way gives the earned bonus back (the backoff
arc of Aho-Corasick); finishing it keeps it. Pieces that start no phrase get
``unk_score``.
"""

from __future__ import annotations

import math
from collections import deque
from pathlib import Path

import numpy as np

CONTEXT_SCORE = 1.0      # NeMo default
DEPTH_SCALING = 2.0      # NeMo's recommendation for CTC, RNN-T and TDT
UNK_SCORE = 0.0          # NeMo default
MAX_CACHED = 256         # score vectors kept, 32 KB each


class _Node:
    """ContextState of NeMo, with only what boosting needs."""

    def __init__(self, token: int, token_score: float, node_score: float, is_end: bool, level: int):
        self.token = token
        self.token_score = token_score
        self.node_score = node_score
        self.is_end = is_end
        self.level = level
        self.next: dict[int, _Node] = {}
        self.fail: _Node | None = None


def _token_score(depth: int, context_score: float) -> float:
    if depth > 0:
        return context_score * DEPTH_SCALING + math.log(depth + 1)
    return context_score


class BoostingTree:
    """The weighted acceptor the decoder walks along, one state per decoder hypothesis."""

    def __init__(self, phrases: list[list[int]], alphas: list[float], vocab_size: int):
        self.vocab_size = vocab_size
        root = _Node(-1, 0.0, 0.0, False, 0)
        for tokens, alpha in zip(phrases, alphas):
            node = root
            for i, token in enumerate(tokens):
                if token not in node.next:
                    token_score = _token_score(i, CONTEXT_SCORE) * alpha
                    is_end = i == len(tokens) - 1
                    node.next[token] = _Node(token, token_score, node.node_score + token_score, is_end, i + 1)
                else:
                    # shared state: the largest score among the phrases that share it
                    child = node.next[token]
                    child.token_score = max(alpha * CONTEXT_SCORE, child.token_score)
                    child.node_score = node.node_score + child.token_score
                    child.is_end = i == len(tokens) - 1 or child.is_end
                node = node.next[token]
        _fill_fail(root)

        # Flatten into states: arcs (token -> next state, weight) and one backoff arc each.
        ids = {id(root): 0}
        self.arcs: list[dict[int, tuple[int, float]]] = [{}]
        self.backoff_to: list[int] = [0]
        self.backoff_w: list[float] = [0.0]
        order = []
        queue = deque([root])
        while queue:
            node = queue.popleft()
            for child in node.next.values():
                ids[id(child)] = len(order) + 1
                order.append(child)
                queue.append(child)
        for child in order:
            self.arcs.append({})
            self.backoff_to.append(0)
            self.backoff_w.append(0.0)
        for parent in [root] + order:
            for token, child in parent.next.items():
                state = ids[id(child)]
                self.arcs[ids[id(parent)]][token] = (state, child.node_score - parent.node_score)
                self.backoff_to[state] = ids[id(child.fail)]
                # NeMo does not penalise leaving a finished phrase (non-uniform weights)
                self.backoff_w[state] = 0.0 if child.is_end else child.fail.node_score - child.node_score
        self._scores: dict[int, np.ndarray] = {}

    def scores(self, state: int) -> np.ndarray:
        """Bonus of every token from ``state`` (NeMo's ``advance``), cached per state."""
        cached = self._scores.get(state)
        if cached is not None:
            return cached
        chain, acc, s = [], 0.0, state
        while True:
            chain.append((s, acc))
            if s == 0:
                break
            acc += self.backoff_w[s]
            s = self.backoff_to[s]
        out = np.full(self.vocab_size, acc + UNK_SCORE, np.float32)   # tokens matching nothing
        for s, acc_s in reversed(chain):       # nearer states override farther ones
            for token, (_, weight) in self.arcs[s].items():
                out[token] = acc_s + weight
        if len(self._scores) >= MAX_CACHED:
            self._scores.clear()
        self._scores[state] = out
        return out

    def next(self, state: int, token: int) -> int:
        s = state
        while True:
            arc = self.arcs[s].get(token)
            if arc is not None:
                return arc[0]
            if s == 0:
                return 0
            s = self.backoff_to[s]


def _fill_fail(root: _Node) -> None:
    """Aho-Corasick fail arcs, breadth first (NeMo's _fill_fail_output)."""
    queue = deque()
    for node in root.next.values():
        node.fail = root
        queue.append(node)
    while queue:
        current = queue.popleft()
        for token, node in current.next.items():
            fail = current.fail
            if token in fail.next:
                fail = fail.next[token]
            else:
                fail = fail.fail
                while fail is not None and token not in fail.next:
                    fail = fail.fail
                fail = fail.next[token] if fail is not None and token in fail.next else root
            node.fail = fail
            queue.append(node)


class PhraseTokenizer:
    """The model's own tokenizer, to split phrases exactly like the decoder emits them."""

    def __init__(self, path: Path):
        from tokenizers import Tokenizer
        self.tokenizer = Tokenizer.from_file(str(path))

    def __call__(self, phrase: str) -> list[int]:
        return self.tokenizer.encode(phrase, add_special_tokens=False).ids
