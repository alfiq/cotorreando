"""Keeps the speech model in memory only while it is needed.

The model loads on demand (one load at a time, however many ask), is freed after a while
without use and is never closed while someone uses or pins it. No Qt here, so it can be tested.
"""

from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager

log = logging.getLogger(__name__)


class ModelHolder:
    def __init__(self, factory, idle_s: float, clock=time.monotonic, on_load_start=None, on_load_done=None):
        """``factory()`` builds the model; ``on_load_done(error, discarded)`` gets error None
        on success, and discarded True when the load was thrown away.
        Both callbacks run on the loading thread."""
        self.factory, self.idle_s, self.clock = factory, idle_s, clock
        self.on_load_start, self.on_load_done = on_load_start, on_load_done
        self._cond = threading.Condition()
        self._model = None
        self._users = self._pins = 0
        self._retired: dict[int, list] = {}  # id -> [model, users, pins]: replaced but still in use
        self._loading = False
        self._gen = self._load_gen = 0  # a load whose generation is old is thrown away
        self._restart = False
        self._suspended = False
        self._error: Exception | None = None
        self.last_used = clock()

    # -- state ------------------------------------------------------------------

    @property
    def loaded(self) -> bool:
        return self._model is not None

    @property
    def failed(self) -> bool:
        with self._cond:
            return self._error is not None and not self._loading

    @property
    def available(self) -> bool:
        """Loaded, or can be loaded when needed."""
        with self._cond:
            return not self._suspended and (self._model is not None or self._error is None or self._loading)

    def touch(self) -> None:
        with self._cond:
            self.last_used = self.clock()

    # -- loading ----------------------------------------------------------------

    def ensure_loading(self) -> None:
        """Start loading in the background if nothing is loaded; never blocks. Retries after a failure."""
        with self._cond:
            if self._suspended or self._model is not None:
                return
            if self._loading:
                if self._load_gen != self._gen:
                    self._restart = True
                return
            self._error = None
            self._start_locked()

    def _start_locked(self) -> None:
        self._loading, self._restart, self._load_gen = True, False, self._gen
        threading.Thread(target=self._load, args=(self._gen,), daemon=True, name="model-load").start()

    def _load(self, gen: int) -> None:
        if self.on_load_start:
            self.on_load_start()
        model, error = None, None
        try:
            model = self.factory()
        except Exception as err:
            error = err
        stale, restarted, discarded = None, False, False
        with self._cond:
            if gen != self._gen:  # unloaded or invalidated meanwhile
                stale, model, discarded = model, None, True
                self._loading = False
                if self._restart and not self._suspended:
                    self._start_locked()
                    restarted = True
            else:
                self._loading = False
                self._model, self._error = model, error
                self._users = self._pins = 0
                self.last_used = self.clock()
            self._cond.notify_all()
        if stale is not None:
            _close(stale)
        if self.on_load_done and not restarted:
            self.on_load_done(error, discarded=discarded)

    # -- use --------------------------------------------------------------------

    def acquire(self):
        """Block until the model is loaded (loading it if needed) and count one use.
        Raises the error of a failed load."""
        with self._cond:
            while self._model is None:
                if self._suspended:
                    raise RuntimeError("model suspended")
                if not self._loading:
                    if self._error is not None:
                        raise self._error
                    self._start_locked()
                self._cond.wait()
            self._users += 1
            return self._model

    def release(self, model) -> None:
        self._drop(model, users=1)

    @contextmanager
    def using(self):
        model = self.acquire()
        try:
            yield model
        finally:
            self.release(model)

    def pin(self):
        """Keep the loaded model from being freed; None if it is not loaded. Never blocks."""
        with self._cond:
            if self._model is not None:
                self._pins += 1
            return self._model

    def unpin(self, model) -> None:
        self._drop(model, pins=1)

    def _drop(self, model, users=0, pins=0) -> None:
        close = None
        with self._cond:
            self.last_used = self.clock()
            if model is self._model:
                self._users -= users
                self._pins -= pins
            elif id(model) in self._retired:
                entry = self._retired[id(model)]
                entry[1] -= users
                entry[2] -= pins
                if entry[1] <= 0 and entry[2] <= 0:
                    close = self._retired.pop(id(model))[0]
        if close is not None:
            _close(close)

    # -- freeing ----------------------------------------------------------------

    def collect(self) -> bool:
        """Free the model if it has gone unused for ``idle_s`` (0 = never). True if freed."""
        with self._cond:
            if (
                self.idle_s <= 0
                or self._model is None
                or self._users
                or self._pins
                or self.clock() - self.last_used < self.idle_s
            ):
                return False
            model = self._detach_locked()
        log.info("Model freed after %.0f s idle", self.idle_s)
        _close(model)
        return True

    def unload(self, force: bool = False) -> bool:
        """Free the model now. Without ``force`` only if nobody uses or pins it; with it, a model
        still in use is closed when its last user lets go, and a load in progress is thrown away."""
        with self._cond:
            if not force and (self._users or self._pins or self._loading):
                return False
            self._gen += 1
            self._restart = False
            model = self._detach_locked()
        if model is not None:
            _close(model)
        return True

    def invalidate(self) -> None:
        """The settings changed: throw away what is loaded or loading and load again."""
        with self._cond:
            self._gen += 1
            model = self._detach_locked()
            self._error = None
            if self._loading:
                self._restart = True
            elif not self._suspended:
                self._start_locked()
        if model is not None:
            _close(model)

    def suspend(self) -> None:
        """Free the model and keep it from loading until resume() (training needs the GPU)."""
        with self._cond:
            self._suspended = True
            self._cond.notify_all()
        self.unload(force=True)

    def resume(self) -> None:
        with self._cond:
            self._suspended = False

    def _detach_locked(self):
        """Take the model out; return it if it can be closed now, else retire it until released."""
        model, self._model = self._model, None
        if model is not None and (self._users or self._pins):
            self._retired[id(model)] = [model, self._users, self._pins]
            model = None
        self._users = self._pins = 0
        return model


def _close(model) -> None:
    close = getattr(model, "close", None)
    if close:
        try:
            close()
        except Exception:
            log.exception("Closing the model failed")
