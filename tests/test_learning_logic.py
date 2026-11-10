"""What learning decides from text: corrections, spacing, word lists and the journal."""

import numpy as np
import pytest

from cotorreando import learning
from cotorreando.config import Settings
from cotorreando.learning import (
    Learner,
    Pending,
    _plain,
    _sound,
    custom_word_ok,
    find_corrections,
    fit_start,
    phrase_alpha,
    sound_alike,
)
from cotorreando.vault import WrongPassword

# -- pure text helpers --------------------------------------------------------------


def test_plain_drops_accents_case_and_punctuation():
    assert _plain("Canción, ÑU!") == "cancion nu"


def test_sound_ignores_spelling_differences():
    assert _sound("Vaca") == _sound("baca")
    assert _sound("hola") == "ola"
    assert _sound("quiero") == "kiero" and _sound("zapato") == "sapato"


def test_sound_alike():
    assert sound_alike("vaca", "baca")
    assert not sound_alike("perro", "gato")


def test_phrase_alpha_grows_and_caps():
    assert phrase_alpha(1) == 1.0
    assert phrase_alpha(2) == 2.0
    assert phrase_alpha(4) == learning.MAX_PHRASE_ALPHA == 3.0
    assert phrase_alpha(1000) == learning.MAX_PHRASE_ALPHA


@pytest.mark.parametrize(
    "phrase,ok",
    [
        ("ab", True),
        ("a", False),
        ("", False),
        ("a1", False),
        ("hola mundo", True),
        ("...", False),
        ("¿¿", False),
        ("ñu", True),
        ("x y", True),
        ("route66", False),
    ],
)
def test_custom_word_ok(phrase, ok):
    assert custom_word_ok(phrase) is ok


@pytest.mark.parametrize(
    "text,before,expected",
    [
        ("Hola", None, "Hola"),
        ("", "", ""),
        ("hola", "", "Hola"),
        ("hola", "  ", "Hola"),
        ("hola", "Fin.", " Hola"),
        ("hola", "Fin. ", "Hola"),
        ("hola", "Fin.\n", "Hola"),
        ("hola", "fin?", " Hola"),
        ("Hola", "x", " hola"),
        ("Hola", "hola mundo", " hola"),
        ("Hola", "hola mundo ", "hola"),
        ("NASA", "hola", " NASA"),  # acronyms keep their capitals
        ("Nasa", "hola", " nasa"),
        ("hola", "(", "hola"),
        ("hola", "¿", "hola"),
    ],
)
def test_fit_start(text, before, expected):
    assert fit_start(text, before) == expected


# -- find_corrections ---------------------------------------------------------------------


def test_identical_text_has_no_pairs():
    assert find_corrections("hola mundo", "hola mundo") == ("hola mundo", [])


def test_sound_alike_replacement_is_a_correction():
    text, pairs = find_corrections("tengo vaca hoy", "tengo baca hoy")
    assert pairs == [("vaca", "baca")] and text == "tengo baca hoy"


def test_accent_is_a_correction():
    _, pairs = find_corrections("voy a comprar un comic", "voy a comprar un cómic")
    assert pairs == [("comic", "cómic")]


def test_more_than_three_words_changed_is_ignored():
    typed = "uno dos tres cuatro cinco seis siete ocho nueve diez once doce"
    field = "uno dos tres aaaa bbbb cccc dddd ocho nueve diez once doce"
    assert find_corrections(typed, field) == (typed, [])


def test_not_sound_alike_is_ignored():
    assert find_corrections("perro grande casa", "gato grande casa") == ("perro grande casa", [])


def test_inserted_or_deleted_words_are_ignored():
    assert find_corrections("el gato negro come", "el gato come")[1] == []
    assert find_corrections("el gato", "el gato negro")[1] == []


def test_rewritten_text_gives_none():
    assert find_corrections("uno dos tres cuatro", "xx yy") is None


def test_single_word_cannot_be_corrected():
    # one word replaced keeps 0% of the words, under MIN_KEPT
    assert find_corrections("valla", "vaya") is None


def test_empty_typed_gives_none():
    assert find_corrections("", "algo") is None
    assert find_corrections("...", "algo") is None


def test_empty_field_gives_none():
    assert find_corrections("hola mundo", "") is None


def test_punctuation_of_the_dictated_text_is_preserved():
    text, pairs = find_corrections("quiero vaca grande y roja, ahora.", "quiero baca grande y roja ahora")
    assert pairs == [("vaca", "baca")] and text == "quiero baca grande y roja, ahora."


def test_case_only_difference_is_not_a_change():
    assert find_corrections("hola mundo", "hola Mundo") == ("hola mundo", [])


# -- Learner ----------------------------------------------------------------------------------


class StubReader:
    def __init__(self):
        self.shot = None
        self.text = None

    def snapshot(self):
        return self.shot

    def read_if_focused(self, element):
        return self.text


@pytest.fixture
def learner(unlocked_vault, monkeypatch):
    monkeypatch.setattr(learning, "FieldReader", StubReader)
    monkeypatch.setattr(Learner, "_watch", lambda self: None)
    obj = Learner(Settings())
    obj.vault = unlocked_vault
    return obj


@pytest.fixture
def loaded(learner):
    learner.activate()
    return learner


def lock_and_unlock(vault):
    identity = vault._identity
    vault.lock()
    return lambda: setattr(vault, "_identity", identity)


def test_events_when_loaded_update_lists_and_save(loaded):
    loaded.count_correction("vaca", "baca")
    loaded.count_correction("vaca", "baca")
    loaded._note({"op": "word", "word": "cañón."})
    assert loaded.counts == {"vaca|baca": 2}
    assert loaded.hard["baca"]["count"] == 2
    assert loaded.hard["canon"] == {"word": "cañón", "count": 1, "read": 0}
    assert loaded.vault.load_private("corrections", None) == {"vaca|baca": 2}
    assert loaded.vault.journal_size() == 0


def test_short_words_are_not_hard_words(loaded):
    loaded.count_correction("el", "la")
    assert loaded.counts == {"el|la": 1} and loaded.hard == {}


def test_note_while_locked_goes_to_journal(learner):
    learner.activate()
    learner.loaded = False
    learner.vault.lock()
    learner.count_correction("vaca", "baca")
    assert learner.counts == {} and learner.vault.journal_size() == 1


def test_activate_merges_journal_once(learner):
    unlock = lock_and_unlock(learner.vault)
    learner.count_correction("vaca", "baca")
    learner._note({"op": "word", "word": "palabra"})
    unlock()
    learner.activate()
    assert learner.loaded and learner.counts == {"vaca|baca": 1}
    assert set(learner.hard) == {"baca", "palabra"}
    assert learner.vault.journal_size() == 0
    assert learner.vault.load_private("corrections", None) == {"vaca|baca": 1}
    learner.activate()  # idempotent
    assert learner.counts == {"vaca|baca": 1} and learner.hard["baca"]["count"] == 1


def test_activate_loads_saved_lists(unlocked_vault, learner):
    unlocked_vault.save_private("custom_words", ["cotorro"])
    unlocked_vault.save_private("corrections", {"a|b": 3})
    learner.activate()
    assert learner.custom == ["cotorro"] and learner.counts == {"a|b": 3}


def test_activate_with_malformed_event_can_be_retried(learner):
    unlock = lock_and_unlock(learner.vault)
    learner.vault.add_event({"op": "correction"})  # no 'old' / 'new'
    unlock()
    try:
        learner.activate()
    except KeyError:
        pass
    assert not (learner.loaded and learner.vault.journal_size() > 0)


def test_forget_correction(loaded):
    for _ in range(2):
        loaded.count_correction("Vaca", "baca")
    loaded.forget_correction("Vaca", "baca")
    assert loaded.counts == {"vaca|baca": 1}
    loaded.forget_correction("Vaca", "baca")
    assert loaded.counts == {}
    loaded.forget_correction("Vaca", "baca")  # unknown: no-op


def test_drop_correction(loaded):
    loaded.count_correction("vaca", "baca")
    loaded.drop_correction("vaca", "baca")
    assert loaded.counts == {} and loaded.vault.load_private("corrections", None) == {}
    loaded.drop_correction("vaca", "baca")


def test_corrections_sorted_by_count(loaded):
    loaded.counts = {"a|b": 1, "c|d": 5, "e|f": 3}
    assert loaded.corrections() == [("c", "d", 5), ("e", "f", 3), ("a", "b", 1)]


def test_add_and_drop_custom_words(loaded):
    assert loaded.add_custom_word("  Cotorro   loco ")
    assert loaded.custom == ["Cotorro loco"]
    assert not loaded.add_custom_word("Cotorro loco")  # already there
    assert not loaded.add_custom_word("abc123") and not loaded.add_custom_word("x")
    assert loaded.vault.load_private("custom_words", None) == ["Cotorro loco"]
    loaded.drop_custom_word("Cotorro loco")
    loaded.drop_custom_word("never there")
    assert loaded.custom == []


def test_hard_words_practice(loaded):
    loaded.hard = {
        "alpha": {"word": "alpha", "count": 5, "read": 0},
        "beta": {"word": "beta", "count": 3, "read": 0},
        "gamma": {"word": "gamma", "count": 9, "read": 1},  # already practiced
        "delta": {"word": "delta", "count": 2, "read": 0},  # not often enough
    }
    assert [e["word"] for e in loaded.hard_words()][:2] == ["gamma", "alpha"]
    assert loaded.words_to_practice() == ["alpha", "beta"]
    assert loaded.words_to_practice(limit=1) == ["alpha"]
    loaded.mark_practiced("Alpha")
    loaded.mark_practiced("unknown")
    assert loaded.words_to_practice() == ["beta"]
    loaded.drop_hard_word("beta")
    loaded.drop_hard_word("beta")
    assert "beta" not in loaded.hard


def test_hard_words_are_capped(loaded):
    loaded.hard = {
        f"w{i:04d}": {"word": f"w{i:04d}", "count": i, "read": 0} for i in range(learning.MAX_HARD_WORDS + 20)
    }
    loaded._save_hard()
    assert len(loaded.hard) == learning.MAX_HARD_WORDS
    assert "w0000" not in loaded.hard and f"w{learning.MAX_HARD_WORDS + 19:04d}" in loaded.hard


def test_vocabulary_and_bias_words(loaded):
    loaded.custom = ["Cotorro"]
    loaded.counts = {"vaca|baca": 1, "x|cosas": 2, "y|ab": 5, "z|room42": 3}
    words = loaded.vocabulary()
    assert words["Cotorro"] == learning.CUSTOM_ALPHA
    assert words["baca"] == 1.0 and words["cosas"] == 2.0
    assert "ab" not in words and "room42" not in words  # too short / digits
    snapshot = learning.Snapshot(text="hola mundo grande cosas", password=False)
    bias = loaded.bias_words(snapshot)
    assert bias["mundo"] == 1.0 and bias["grande"] == 1.0 and "hola" in bias
    assert bias["cosas"] == 2.0  # corrections win over field words
    assert loaded.bias_words(learning.Snapshot(text="secreto", password=True)) == loaded.vocabulary()
    assert loaded.bias_words(None) == loaded.vocabulary()


def test_vocabulary_survives_a_zero_count(loaded):
    loaded.counts = {"x|cosas": 0}
    assert isinstance(loaded.vocabulary(), dict)


def test_begin_respects_learning_switch_and_vault(learner, monkeypatch):
    learner.reader.shot = learning.Snapshot(text="hi")
    assert learner.begin(1) is learner.reader.shot
    learner.s.learning = False
    assert learner.begin(1) is None
    learner.s.learning = True
    monkeypatch.setattr(type(learner.vault), "ready", property(lambda self: False))
    assert learner.begin(1) is None


def test_excluded_apps(learner, monkeypatch):
    monkeypatch.setattr(learning, "exe_name", lambda window: "keepass.exe")
    assert learner.allowed(1)
    learner.s.excluded_apps = " Notepad.exe , KeePass.EXE ,, "
    assert not learner.allowed(1)
    monkeypatch.setattr(learning, "exe_name", lambda window: "word.exe")
    assert learner.allowed(1)
    learner.reader.shot = learning.Snapshot(text="hi")
    learner.s.excluded_apps = "word.exe"
    assert learner.begin(1) is None


def test_finish_queues_a_pending_check(loaded):
    audio = np.zeros(10, np.float32)
    snap = learning.Snapshot(element=object())
    loaded.finish("hola mundo", audio, [], snap)
    assert len(loaded.pending) == 1 and loaded.pending[0].typed == "hola mundo"
    for ignored in (learning.Snapshot(element=object(), password=True), None):
        loaded.finish("hola", audio, [], ignored)
    loaded.finish("   ", audio, [], snap)
    loaded.s.learning = False
    loaded.finish("hola", audio, [], snap)
    assert len(loaded.pending) == 1


def test_hesitation_is_noted_for_a_piece_without_leading_space(loaded):
    trace = [("mun", 0, 0.4, 0.9), ("dial", 0, 0.9, 0.9), (" yo", 0, 0.1, 0.9), (" firme", 0, 0.99, 0.99)]
    loaded._note_hesitations(trace)
    assert set(loaded.hard) == {"mundial"}  # "yo" is too short, "firme" was sure


def test_hesitation_is_noted_for_a_realistic_trace(loaded):
    trace = [(" hola", 0, 0.99, 0.9), (" mun", 0, 0.4, 0.9), ("dial", 0, 0.9, 0.9), (" yo", 0, 0.1, 0.9)]
    loaded._note_hesitations(trace)
    assert "mundial" in loaded.hard


def test_settle_keeps_the_correction(loaded):
    audio = np.ones(100, np.float32) * 0.1
    item = Pending(None, "tengo vaca hoy ", audio, 0.0, latest=("tengo baca hoy ", [("vaca", "baca")]))
    loaded._settle(item)
    (rid,) = loaded.vault.record_ids()
    meta, saved = loaded.vault.read_record(rid)
    assert (meta["kind"], meta["text"], meta["old"]) == ("correction", "tengo baca hoy", "tengo vaca hoy")
    assert len(saved) == 100 and loaded.counts == {"vaca|baca": 1}


def test_settle_without_corrections_saves_nothing(loaded):
    audio = np.zeros(10, np.float32)
    loaded._settle(Pending(None, "hola", audio, 0.0))
    loaded._settle(Pending(None, "hola", audio, 0.0, latest=("hola", [])))
    assert loaded.vault.record_ids() == [] and loaded.counts == {}


def test_look_follows_focus_and_text(loaded):
    item = Pending(object(), "tengo vaca hoy", np.zeros(1, np.float32), 0.0)
    loaded.reader.text = None  # not focused: nothing read, keep waiting
    assert loaded._look(item) is False and item.latest is None
    loaded.reader.text = "tengo baca hoy"
    assert loaded._look(item) is False and item.latest[1] == [("vaca", "baca")]
    loaded.reader.text = "something else entirely"  # sent or cleared: stop, keep the last version
    assert loaded._look(item) is True and item.latest[1] == [("vaca", "baca")]


# -- unlocking and old data --------------------------------------------------------------------


def test_unlock_with_wrong_password_stays_unloaded(learner):
    learner.vault.lock()
    with pytest.raises(WrongPassword):
        learner.unlock("definitely not it")
    assert not learner.loaded and learner.vault.locked


def test_unlock_loads(learner, unlocked_vault):
    learner.vault.lock()
    learner.unlock(unlocked_vault.password)
    assert learner.loaded and not learner.vault.locked


def test_finish_migration_paths(learner, monkeypatch, caplog):
    calls = []
    monkeypatch.setattr(learning.vault_legacy, "migrate", lambda vault: calls.append(vault))
    monkeypatch.setattr(learning.vault_legacy, "pending", lambda: False)
    learner._finish_migration()
    monkeypatch.setattr(learning.vault_legacy, "pending", lambda: True)
    monkeypatch.setattr(learning.vault_legacy, "needs_old_password", lambda: True)
    learner._finish_migration()
    assert calls == []  # nothing pending, or it needs the old password
    monkeypatch.setattr(learning.vault_legacy, "needs_old_password", lambda: False)
    learner._finish_migration()
    assert calls == [learner.vault]

    def boom(vault):
        raise OSError("disk full")

    monkeypatch.setattr(learning.vault_legacy, "migrate", boom)
    learner._finish_migration()  # logged, never fatal
    assert "Could not move the old data" in caplog.text
