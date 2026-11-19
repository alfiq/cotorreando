"""The dialog to review and delete what the app has learnt."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from .. import keyboard
from ..audio import RATE, Player
from ..i18n import tr
from ..learning import phrase_alpha
from .base import Prompt, Window, footer_bar, ghost_button, scroll_area

log = logging.getLogger(__name__)


class DataDialog(Window):
    """What has been kept, to read, listen to and delete. The vault must be unlocked.

    It closes by itself, so that whoever opened it locks the vault again, when Windows
    is locked or nobody has touched the computer for a while."""

    playback_ended = Signal(str)
    IDLE_LIMIT_MS = 5 * 60 * 1000

    def __init__(self, learner, parent=None):
        super().__init__(parent)
        self.learner = learner
        self.vault = learner.vault
        self.player = Player()
        self.playing = ""
        self.cards: dict[str, tuple[QFrame, QPushButton]] = {}
        self.setWindowTitle(tr("data_title"))
        self.resize(720, 560)
        self.playback_ended.connect(self._on_ended)
        self.guard = QTimer(self, interval=2000, timeout=self._check_away)
        self.guard.start()

        pages = QStackedWidget()
        pages.addWidget(scroll_area(self._dictations_page()))
        pages.addWidget(scroll_area(self._words_page()))
        tabs = QTabBar(drawBase=False, expanding=False)
        tabs.addTab(tr("data_tab_dictations"))
        tabs.addTab(tr("data_tab_words"))
        self.delete_all = ghost_button(tr("data_delete_all"), clicked=self._delete_all)
        self.delete_all.setEnabled(bool(self.cards))
        tabs.currentChanged.connect(pages.setCurrentIndex)
        tabs.currentChanged.connect(lambda i: self.delete_all.setVisible(i == 0))

        footer, bottom = footer_bar()
        bottom.addWidget(self.delete_all)
        bottom.addStretch()
        bottom.addWidget(QPushButton(tr("cal_finish"), clicked=self.accept, default=True))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._header(tabs))
        layout.addWidget(pages, 1)
        layout.addWidget(footer)

    @staticmethod
    def _header(tabs: QTabBar) -> QWidget:
        header = QWidget(objectName="content")
        top = QVBoxLayout(header)
        top.setContentsMargins(28, 24, 28, 0)
        top.setSpacing(8)
        top.addWidget(QLabel(tr("data_title"), objectName="pageTitle"))
        top.addWidget(tabs)
        return header

    @staticmethod
    def _column() -> tuple[QWidget, QVBoxLayout]:
        """A page of this dialog: a column of rows, inside a widget."""
        page = QWidget(objectName="content")
        rows = QVBoxLayout(page)
        rows.setContentsMargins(28, 16, 28, 24)
        rows.setSpacing(10)
        return page, rows

    def _dictations_page(self) -> QWidget:
        """One card per saved dictation, the latest first."""
        page, self.rows = self._column()
        for rid in reversed(self.vault.record_ids()):
            meta, samples = self.vault.read_record(rid)
            self.rows.addWidget(self._card(rid, meta, samples.size / RATE))
        self.empty = QLabel(tr("data_empty"), objectName="note")
        self.empty.setVisible(not self.cards)
        self.rows.addWidget(self.empty)
        self.rows.addStretch()
        return page

    def _words_page(self) -> QWidget:
        """What has been learnt word by word: replacements, corrections on their way, hard words."""
        page, rows = self._column()
        self._custom_words_section(rows)
        drop = self.learner.drop_correction
        self._learnt_section(
            rows,
            tr("words_boost"),
            tr("words_boost_note"),
            [
                (
                    f"{old}  →  {new}",
                    tr("words_boost_detail", n=n, alpha=phrase_alpha(n)),
                    lambda o=old, w=new: drop(o, w),
                )
                for old, new, n in self.learner.corrections()
            ],
        )
        self._learnt_section(
            rows,
            tr("words_hard"),
            tr("words_hard_note"),
            [
                (
                    e["word"],
                    tr("words_hard_times", n=e["count"], read=e["read"]),
                    lambda w=e["word"]: self.learner.drop_hard_word(w),
                )
                for e in self.learner.hard_words()
            ],
        )
        rows.addStretch()
        return page

    def _custom_words_section(self, rows: QVBoxLayout) -> None:
        """The words the user adds by hand: an entry to type one, then the ones already added."""
        rows.addWidget(QLabel(tr("words_custom"), objectName="groupTitle"))
        rows.addWidget(self._text(tr("words_custom_note"), "note"))
        entry = QLineEdit(placeholderText=tr("words_custom_hint"))
        add = QPushButton(tr("words_add"), enabled=False)
        error = QLabel(objectName="note", visible=False)
        line = QHBoxLayout()
        line.addWidget(entry, 1)
        line.addWidget(add)
        rows.addLayout(line)
        rows.addWidget(error)
        custom = QVBoxLayout()
        custom.setSpacing(10)
        rows.addLayout(custom)

        def show(word: str) -> None:
            custom.addWidget(self._word_row(word, "", lambda: self.learner.drop_custom_word(word)))

        def submit() -> None:
            word = " ".join(entry.text().split())
            if self.learner.add_custom_word(word):
                show(word)
                entry.clear()
                error.hide()
            else:
                error.setText(tr("words_custom_bad"))
                error.show()

        entry.textChanged.connect(lambda text: add.setEnabled(bool(text.strip())))
        entry.returnPressed.connect(submit)
        add.clicked.connect(submit)
        for word in self.learner.custom:
            show(word)

    def _learnt_section(self, rows: QVBoxLayout, title: str, note: str, items) -> None:
        """A titled list of ``(text, detail, forget)``, or a line saying there is nothing yet."""
        rows.addSpacing(6)
        rows.addWidget(QLabel(title, objectName="groupTitle"))
        rows.addWidget(self._text(note, "note"))
        if not items:
            rows.addWidget(self._text(tr("words_none"), "note"))
        for text, detail, forget in items:
            rows.addWidget(self._word_row(text, detail, forget))

    def _word_row(self, text: str, detail: str, forget) -> QFrame:
        row = QFrame(objectName="card")
        line = QHBoxLayout(row)
        line.setContentsMargins(16, 8, 10, 8)
        line.addWidget(self._text(text), 1)
        if detail:
            line.addWidget(QLabel(detail, objectName="caption"))

        def delete() -> None:
            forget()
            row.deleteLater()

        line.addWidget(ghost_button(tr("data_delete"), clicked=delete))
        return row

    def _card(self, rid: str, meta: dict, seconds: float) -> QFrame:
        date = f"{rid[6:8]}/{rid[4:6]}/{rid[:4]} {rid[9:11]}:{rid[11:13]}"
        card = QFrame(objectName="card")
        column = QVBoxLayout(card)
        column.setContentsMargins(16, 12, 16, 12)
        column.setSpacing(8)
        column.addWidget(QLabel(f"{tr('kind_' + meta['kind'])} · {date} · {seconds:.0f} s", objectName="caption"))
        label = self._text(meta["text"])
        editor = QPlainTextEdit(tabChangesFocus=True, visible=False)
        editor.setFixedHeight(96)
        column.addWidget(label)
        column.addWidget(editor)
        if meta.get("old"):
            column.addWidget(self._text(tr("data_old", text=meta["old"]), "note"))
        play = QPushButton(tr("data_play"), clicked=lambda: self._toggle(rid))
        column.addLayout(self._card_buttons(rid, play, label, editor))
        self.cards[rid] = (card, play)
        return card

    def _card_buttons(self, rid: str, play: QPushButton, label: QLabel, editor: QPlainTextEdit) -> QHBoxLayout:
        """Play, edit and delete; while editing, those give way to save and cancel."""
        edit = ghost_button(tr("data_edit"))
        delete = ghost_button(tr("data_delete"), clicked=lambda: self._delete(rid))
        save = QPushButton(tr("save"), visible=False)
        cancel = ghost_button(tr("cancel"), visible=False)

        def editing(on: bool) -> None:
            for widget in (editor, save, cancel):
                widget.setVisible(on)
            for widget in (label, edit, delete):
                widget.setVisible(not on)

        def begin() -> None:
            editor.setPlainText(label.text())
            editing(True)
            editor.setFocus()

        def finish() -> None:
            text = editor.toPlainText().strip()
            self._save_text(rid, text)
            label.setText(text)
            editing(False)

        edit.clicked.connect(begin)
        save.clicked.connect(finish)
        cancel.clicked.connect(lambda: editing(False))
        editor.textChanged.connect(lambda: save.setEnabled(bool(editor.toPlainText().strip())))
        line = QHBoxLayout()
        for widget in (play, edit, delete, save, cancel):
            line.addWidget(widget)
        line.addStretch()
        return line

    def _save_text(self, rid: str, text: str) -> None:
        # Your own word counts as verified: training must not throw it away. Untrained again, so it gets learnt.
        self.vault.update_record(rid, {"text": text, "verified": True})
        self.vault.set_trained_ids([i for i in self.vault.trained_ids() if i != rid])

    @staticmethod
    def _text(text: str, name: str = "") -> QLabel:
        label = QLabel(text, objectName=name, wordWrap=True, textFormat=Qt.PlainText)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        return label

    def _toggle(self, rid: str) -> None:
        same = rid == self.playing
        self._stop()
        if same:
            return
        _, samples = self.vault.read_record(rid)
        self.playing = rid
        self.cards[rid][1].setText(tr("data_stop"))
        self.player.play(samples, lambda: self.playback_ended.emit(rid))

    def _stop(self) -> None:
        self.player.stop()
        if self.playing in self.cards:
            self.cards[self.playing][1].setText(tr("data_play"))
        self.playing = ""

    def _on_ended(self, rid: str) -> None:
        if rid == self.playing:  # not one that was stopped to play another
            self._stop()

    def _delete(self, rid: str) -> None:
        if rid == self.playing:
            self._stop()
        self.vault.delete_record(rid)
        self.cards.pop(rid)[0].deleteLater()
        self.empty.setVisible(not self.cards)
        self.delete_all.setEnabled(bool(self.cards))

    def _delete_all(self):
        if Prompt(self, tr("data_confirm"), ok=tr("data_delete_all")).exec():
            self._stop()
            self.vault.delete_all_records()
            for card, _ in self.cards.values():
                card.deleteLater()
            self.cards.clear()
            self.empty.show()
            self.delete_all.setEnabled(False)

    def _check_away(self) -> None:
        if keyboard.session_locked() or (not self.playing and keyboard.idle_ms() > self.IDLE_LIMIT_MS):
            log.info("Closing the data window: the computer was left alone")
            self.reject()

    def done(self, result):
        self.guard.stop()
        self._stop()
        super().done(result)
