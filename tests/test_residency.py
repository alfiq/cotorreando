"""ModelHolder: load on demand, free when idle, never close a model in use."""

import threading
import time

import pytest

from cotorreando.residency import ModelHolder


class FakeModel:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def make(idle_s=600, gate=None, fail=None):
    calls, clock = [], Clock()

    def factory():
        calls.append(1)
        if gate is not None:
            gate.wait(5)
        if fail:
            raise fail
        return FakeModel()
    return ModelHolder(factory, idle_s, clock=clock), calls, clock


def loaded(holder):
    with holder.using() as model:
        return model


def test_frees_after_idle_and_not_before():
    holder, _, clock = make(idle_s=600)
    model = loaded(holder)
    clock.now += 599
    assert not holder.collect() and holder.loaded
    clock.now += 2
    assert holder.collect() and not holder.loaded and model.closed


def test_never_frees_with_idle_zero():
    holder, _, clock = make(idle_s=0)
    loaded(holder)
    clock.now += 10 ** 9
    assert not holder.collect() and holder.loaded


def test_not_freed_while_used_or_pinned():
    holder, _, clock = make(idle_s=1)
    with holder.using() as model:
        clock.now += 100
        assert not holder.collect() and not model.closed
    pinned = holder.pin()
    clock.now += 100
    assert not holder.collect() and not pinned.closed
    holder.unpin(pinned)
    clock.now += 100
    assert holder.collect() and pinned.closed


def test_reload_after_free_is_a_single_load():
    holder, calls, clock = make(idle_s=1)
    loaded(holder)
    clock.now += 10
    assert holder.collect()
    barrier, got = threading.Barrier(8), []

    def worker():
        barrier.wait()
        with holder.using() as model:
            got.append(model)
    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5)
    assert len(calls) == 2 and len(got) == 8 and len({id(m) for m in got}) == 1


def test_acquire_blocks_until_loaded():
    gate = threading.Event()
    holder, _, _ = make(gate=gate)
    holder.ensure_loading()
    got = []
    t = threading.Thread(target=lambda: got.append(loaded(holder)))
    t.start()
    time.sleep(0.1)
    assert not got
    gate.set()
    t.join(5)
    assert got and holder.loaded


def test_failure_propagates_and_leaves_clean_state():
    holder, calls, _ = make(fail=OSError("broken"))
    with pytest.raises(OSError):
        holder.acquire()
    assert holder.failed and not holder.loaded and not holder.available
    with pytest.raises(OSError):         # no retry loop on its own
        holder.acquire()
    assert len(calls) == 1
    holder.factory = FakeModel
    holder.ensure_loading()              # an explicit retry
    assert loaded(holder) and not holder.failed


def test_collect_racing_using_never_closes_a_model_in_use():
    holder, _, clock = make(idle_s=0.000001)
    loaded(holder)
    stop, bad = threading.Event(), []

    def user():
        while not stop.is_set():
            with holder.using() as model:
                if model.closed:
                    bad.append(model)

    def collector():
        while not stop.is_set():
            clock.now += 1
            holder.collect()
    threads = [threading.Thread(target=user) for _ in range(3)] + [threading.Thread(target=collector)]
    for t in threads:
        t.start()
    time.sleep(0.5)
    stop.set()
    for t in threads:
        t.join(5)
    assert not bad


def test_invalidate_waits_for_users_before_closing():
    holder, calls, _ = make()
    old = holder.acquire()
    holder.invalidate()
    new = loaded(holder)
    assert new is not old and not old.closed and len(calls) == 2
    holder.release(old)
    assert old.closed and not new.closed


def test_suspend_keeps_it_unloaded_until_resume():
    holder, _, _ = make()
    model = loaded(holder)
    holder.suspend()
    assert model.closed and not holder.available
    holder.ensure_loading()
    assert not holder.loaded
    with pytest.raises(RuntimeError):
        holder.acquire()
    holder.resume()
    assert loaded(holder)
