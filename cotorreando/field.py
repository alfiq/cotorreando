"""Reads the focused text field through UI Automation, when the application allows it.

Everything here is best effort. Many applications expose nothing, and some hang
when asked, so all calls happen on one worker thread and callers wait with a short
timeout. Failing simply means there is no context.
"""

from __future__ import annotations

import logging
import queue
import threading
from concurrent.futures import Future, TimeoutError as FutureTimeout
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)
MAX_CHARS = 20000
ENDPOINT_START, ENDPOINT_END = 0, 1


@dataclass
class Snapshot:
    element: Any = None
    password: bool = False
    text: str = ""
    before: str | None = None    # text before the caret; None when the caret is unknown


class FieldReader:
    def __init__(self):
        self.jobs: queue.Queue = queue.Queue()
        self.busy = False
        threading.Thread(target=self._run, daemon=True, name="field").start()

    def _submit(self, work) -> Future | None:
        if self.busy or self.jobs.qsize():   # the application is not answering; never pile up
            return None
        future: Future = Future()
        self.jobs.put((work, future))
        return future

    @staticmethod
    def _wait(future: Future | None, timeout: float):
        if future is None:
            return None
        try:
            return future.result(timeout)
        except FutureTimeout:
            return None

    def snapshot(self, timeout: float = 0.1) -> Snapshot | None:
        return self._wait(self._submit(self._focused), timeout)

    def reread(self, element, timeout: float = 1.0) -> str | None:
        return self._wait(self._submit(lambda: self._read(element).text), timeout)

    def _run(self) -> None:
        try:
            import comtypes
            import comtypes.client
            comtypes.CoInitialize()
            comtypes.client.GetModule("UIAutomationCore.dll")
            from comtypes.gen import UIAutomationClient as uia
            self.uia = uia
            self.automation = comtypes.client.CreateObject(uia.CUIAutomation, interface=uia.IUIAutomation)
        except Exception:
            log.info("UI Automation is not available; dictating without field context", exc_info=True)
            while True:
                self.jobs.get()[1].set_result(None)
        while True:
            work, future = self.jobs.get()
            self.busy = True
            try:
                future.set_result(work())
            except Exception:      # a closed window, an application that exposes nothing...
                future.set_result(None)
            self.busy = False

    def _focused(self) -> Snapshot:
        return self._read(self.automation.GetFocusedElement())

    def _read(self, element) -> Snapshot:
        uia = self.uia
        if element.CurrentIsPassword:
            return Snapshot(element, password=True)
        pattern = element.GetCurrentPattern(uia.UIA_TextPatternId)
        if pattern:
            text_pattern = pattern.QueryInterface(uia.IUIAutomationTextPattern)
            document = text_pattern.DocumentRange
            text = document.GetText(MAX_CHARS)
            before = None
            selection = text_pattern.GetSelection()
            if selection and selection.Length:
                head = document.Clone()
                head.MoveEndpointByRange(ENDPOINT_END, selection.GetElement(0), ENDPOINT_START)
                before = head.GetText(MAX_CHARS)
            return Snapshot(element, text=text, before=before)
        pattern = element.GetCurrentPattern(uia.UIA_ValuePatternId)
        if pattern:
            value = pattern.QueryInterface(uia.IUIAutomationValuePattern).CurrentValue
            return Snapshot(element, text=value[:MAX_CHARS])
        return Snapshot(element)
