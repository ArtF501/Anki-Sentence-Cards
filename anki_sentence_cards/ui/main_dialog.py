"""Main window: paste words, pick a sentence for each, build cards, report.

All decisions live in ..batch (tested). This file is only Qt glue and is
verified by hand (see the task 11 report).
"""
import logging
import os

from aqt.operations import QueryOp
from aqt.qt import (
    QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPlainTextEdit,
    QPushButton, QSize, QStackedWidget, Qt, QVBoxLayout, QWidget,
)
from aqt.utils import askUser, showText, showWarning

from .. import batch
from ..book.library import load_book
from ..book.loaders import BookLoadError
from ..book.search import find_occurrences
from ..card import build_draft
from ..notes import add_note, find_duplicate
from ..settings import load_settings

log = logging.getLogger(__name__)

PROFILE_CLOSED = "Профиль закрыт, партия не записана."
BREAK_CANCELLED = "Перерыв прерван, уже добытые карточки будут дописаны."

PAGE_INPUT, PAGE_PICK, PAGE_REPORT, PAGE_CHOOSE = 0, 1, 2, 3


def _addon(mw) -> str:
    return mw.addonManager.addonFromModule(__name__)


class MainDialog(QDialog):
    def __init__(self, mw):
        super().__init__(mw)
        self.mw = mw
        self.setWindowTitle("Anki Sentence Cards")
        self.setMinimumSize(640, 480)
        self.settings = load_settings(mw.addonManager.getConfig(_addon(mw)) or {})
        self.sentences = None
        self.state = None
        self.pf = None
        self.occs = []
        self.choice = None
        self._finish_batch = None
        self._busy = False
        self._cancelled = False
        self.total = batch.BatchResult()
        self.skipped_all = []
        self._retrying = []

        root = QVBoxLayout(self)
        self.stack = QStackedWidget()
        root.addWidget(self.stack)
        self.stack.addWidget(self._make_input())
        self.stack.addWidget(self._make_pick())
        self.stack.addWidget(self._make_report())
        self.stack.addWidget(self._make_choose())

    # ---- page 1: input
    def _make_input(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        name = os.path.basename(self.settings.active_book) or "не выбрана"
        lay.addWidget(QLabel("Книга: %s" % name))
        lay.addWidget(QLabel("Слова или фразы, по одному в строке:"))
        self.words_edit = QPlainTextEdit()
        lay.addWidget(self.words_edit, 1)
        self.start_btn = QPushButton("Начать")
        self.start_btn.clicked.connect(self._start)
        lay.addWidget(self.start_btn)
        return w

    def _start(self):
        if self._busy:
            return
        if self.mw.col is None:
            showWarning("Профиль закрыт: откройте профиль и окно аддона заново.")
            return
        words = batch.parse_words(self.words_edit.toPlainText())
        if not words:
            showWarning("Введите хотя бы одно слово.")
            return
        s = self.settings
        fields = None
        model = self.mw.col.models.by_name(s.notetype) if s.notetype else None
        if model is not None:
            fields = [f["name"] for f in model["flds"]]
        self.pf = batch.preflight(s, fields, bool(s.active_book) and os.path.isfile(s.active_book))
        if self.pf.fatal:
            showWarning(self.pf.fatal)
            return
        if self.pf.warnings:
            showWarning("\n".join(self.pf.warnings))
        self._begin_picking(words)

    def _begin_picking(self, words):
        if self.sentences is not None:
            self._open_state(words)
            return
        self._busy = True
        cache = os.path.join(self.mw.addonManager.addonsFolder(_addon(self.mw)), "user_files", "cache")
        path = self.settings.active_book

        def op(col):
            return load_book(path, cache).sentences

        def ok(sentences):
            self._busy = False
            self.sentences = sentences
            self._open_state(words)

        def fail(e):
            self._busy = False
            if isinstance(e, BookLoadError):
                showWarning("Не удалось прочитать книгу: %s" % e)
            else:
                showWarning("Ошибка при загрузке книги: %s" % e)

        QueryOp(parent=self, op=op, success=ok).failure(fail).with_progress("Загрузка книги...").run_in_background()

    def _open_state(self, words):
        self.state = batch.PickState(words)
        self.stack.setCurrentIndex(PAGE_PICK)
        self._show_word()

    # ---- page 2: pick
    def _make_pick(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        self.title = QLabel()
        self.title.setStyleSheet("font-size: 16pt; font-weight: bold;")
        lay.addWidget(self.title)
        self.info = QLabel()
        self.info.setWordWrap(True)
        lay.addWidget(self.info)
        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.list.itemClicked.connect(self._clicked)
        lay.addWidget(self.list, 1)
        self.manual_edit = QPlainTextEdit()
        self.manual_edit.setPlaceholderText("Предложение целиком")
        self.manual_edit.setFixedHeight(70)
        self.manual_edit.hide()
        lay.addWidget(self.manual_edit)
        row = QHBoxLayout()
        self.manual_btn = QPushButton("Вписать предложение вручную")
        self.manual_btn.clicked.connect(self._manual)
        skip = QPushButton("Пропустить")
        skip.clicked.connect(self._skip)
        row.addWidget(self.manual_btn)
        row.addStretch(1)
        row.addWidget(skip)
        lay.addLayout(row)
        return w

    def _show_word(self):
        st = self.state
        if st.done:
            self._finish_picking()
            return
        word = st.current
        self.title.setText("%s    %s" % (word, st.counter))
        self.occs, truncated = find_occurrences(self.sentences, word, self.settings.occurrence_limit)
        self.manual_edit.clear()
        self.manual_edit.hide()
        self.manual_btn.setText("Вписать предложение вручную")
        self.list.clear()
        if not self.occs:
            self.info.setText("В книге не найдено ни одного предложения. Впишите своё или пропустите слово.")
        else:
            self.info.setText(batch.limit_note(len(self.occs), truncated, self.settings.occurrence_limit)
                              or "Найдено предложений: %d. Клик или цифра выбирает." % len(self.occs))
        width = max(self.list.viewport().width() - 40, 300)
        for i, occ in enumerate(self.occs):
            label = QLabel("%s %s" % ("%d." % (i + 1) if i < 9 else "&nbsp;&nbsp;", batch.highlight_html(occ)))
            label.setTextFormat(Qt.TextFormat.RichText)
            label.setWordWrap(True)
            label.setFixedWidth(width)
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            item = QListWidgetItem()
            item.setSizeHint(QSize(width, label.heightForWidth(width) + 10))
            self.list.addItem(item)
            self.list.setItemWidget(item, label)

    def _clicked(self, item):
        self._select(self.list.row(item))

    def _select(self, row):
        if 0 <= row < len(self.occs):
            self.state.choose(self.occs[row])
            self._show_word()

    def _manual(self):
        if self.manual_edit.isHidden():
            self.manual_edit.show()
            self.manual_edit.setFocus()
            self.manual_btn.setText("Готово: использовать это предложение")
            return
        if not self.state.choose_manual(self.manual_edit.toPlainText()):
            showWarning("Впишите предложение.")
            return
        self._show_word()

    def _skip(self):
        self.state.skip()
        self._show_word()

    def keyPressEvent(self, e):
        digit = e.text() in tuple("123456789")
        page = self.stack.currentIndex()
        if page == PAGE_PICK and digit and not self.manual_edit.hasFocus():
            self._select(int(e.text()) - 1)
            return
        if page == PAGE_CHOOSE and digit:
            self._pick_meaning(int(e.text()) - 1)
            return
        super().keyPressEvent(e)

    # ---- build
    def _finish_picking(self):
        if self.mw.col is None:
            showWarning(PROFILE_CLOSED)
            return
        picks = self.state.picks
        self.skipped_all += self.state.skipped
        result = batch.BatchResult()
        col = self.mw.col
        settings, mw = self.settings, self.mw
        deck, notetype, fmap = settings.deck, settings.notetype, self.pf.field_map

        def progress(i, n, word):
            mw.taskman.run_on_main(
                lambda: mw.progress.update(label="%s (%d из %d)" % (word, i + 1, n), value=i, max=n))

        def run_bg(work, ok, fail):
            self._busy = True
            self.start_btn.setEnabled(False)
            self.stack.setCurrentIndex(PAGE_INPUT)

            def guarded(fn):
                def inner(arg):
                    profile_closed = self.mw.col is None
                    self._busy = False
                    try:
                        self.start_btn.setEnabled(True)
                    except RuntimeError:  # the dialog was destroyed meanwhile
                        pass
                    if profile_closed:
                        log.warning("profile closed during the batch: results dropped")
                        try:
                            showWarning(PROFILE_CLOSED)
                        except RuntimeError:
                            pass
                        return
                    try:
                        fn(arg)
                    except RuntimeError:  # widgets gone while showing the report
                        log.exception("dialog destroyed before the report was shown")
                    
                return inner

            QueryOp(parent=self, op=lambda _c: work(), success=guarded(ok)).failure(
                guarded(fail)).with_progress("Сборка карточек...").run_in_background()

        def done(res):
            self.total = batch.merge_results(self.total, res, self._retrying)
            self._retrying = []
            self._show_report()

        self._cancelled = False
        batch.run_batch(
            picks, lambda w: find_duplicate(col, deck, w),
            lambda w, o: build_draft(w, o, settings, bool(fmap.get("sound"))),
            lambda d: add_note(self.mw.col, d, deck, notetype, fmap),
            result, run_bg, done, progress,
            choose=self._begin_choosing,
            workers=settings.parallel,
            should_stop=self._should_stop)

    def _cancel_if_running(self) -> bool:
        """Closing never traps the user and never drops the work in silence.

        During the break: the fetch is told to stop, and whatever was already
        fetched is written. During the choice pass: writing the rest with the
        first variants is exactly what this feature exists to avoid, so it is
        asked for. False means the user changed their mind: stay open.
        """
        if self.choice is not None:
            left = len(self.choice.drafts) - self.choice.index
            if not askUser(
                    "Выбор не закончен: осталось слов — %d.\n\n"
                    "Записать их с первыми вариантами части речи и значения?\n"
                    "«Нет» — вернуться к выбору." % left,
                    title="Anki Sentence Cards", defaultno=True):
                return False
            self.choice.accept_all()
            self._end_choosing()
            return True
        if self._busy and not self._cancelled:
            self._cancelled = True
            showWarning(BREAK_CANCELLED)
        return True

    def reject(self):
        if self._cancel_if_running():
            super().reject()

    def closeEvent(self, e):
        if not self._cancel_if_running():
            e.ignore()
            return
        super().closeEvent(e)

    def _should_stop(self) -> bool:
        """Read from the fetching threads: the window or Anki asked to stop."""
        if self._cancelled:
            return True
        try:
            return bool(self.mw.progress.want_cancel())
        except Exception:  # no progress window at all
            return False

    # ---- page 3: report
    def _make_report(self):
        w = QWidget()
        self.report_lay = QVBoxLayout(w)
        self.report_label = QLabel()
        self.report_label.setWordWrap(True)
        self.report_label.setTextFormat(Qt.TextFormat.RichText)
        self.report_lay.addWidget(self.report_label, 1)
        row = QHBoxLayout()
        self.retry_btn = QPushButton("Повторить проблемные")
        self.retry_btn.clicked.connect(self._retry)
        close = QPushButton("Закрыть")
        close.clicked.connect(self.accept)
        row.addWidget(self.retry_btn)
        row.addStretch(1)
        row.addWidget(close)
        self.report_lay.addLayout(row)
        return w

    def _show_report(self):
        import html
        out = self.total.outcomes
        parts = ["<p><b>%s</b></p>" % html.escape(m) for m in self.total.warnings]
        if self.skipped_all:
            parts.append("<p>Пропущено вами: %s</p>" % html.escape(", ".join(self.skipped_all)))
        for title, lines in batch.report_text(out):
            parts.append("<h3>%s</h3><ul>%s</ul>" % (
                html.escape(title), "".join("<li>%s</li>" % html.escape(x) for x in lines)))
        if not out:
            parts.append("<p>Ничего не создано.</p>")
        self.report_label.setText("".join(parts))
        self.retry_btn.setVisible(bool(batch.retry_words(out)))
        self.stack.setCurrentIndex(PAGE_REPORT)
        if not self.isVisible():
            # the window was closed mid-batch: the page switch would be invisible
            showText(batch.report_plain(out, self.total.warnings, self.skipped_all),
                     title="Anki Sentence Cards: отчёт")

    def _retry(self):
        words = batch.retry_words(self.total.outcomes)
        if words:
            self._retrying = words
            self._open_state(words)


    # ---- page 4: choose the role and the meaning
    def _make_choose(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        self.ch_title = QLabel()
        self.ch_title.setStyleSheet("font-size: 16pt; font-weight: bold;")
        lay.addWidget(self.ch_title)
        self.ch_sentence = QLabel()
        self.ch_sentence.setWordWrap(True)
        self.ch_sentence.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(self.ch_sentence)
        self.ch_roles_host = QWidget()
        self.ch_roles = QHBoxLayout(self.ch_roles_host)
        self.ch_roles.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.ch_roles_host)
        self.ch_info = QLabel()
        self.ch_info.setWordWrap(True)
        lay.addWidget(self.ch_info)
        self.ch_list = QListWidget()
        self.ch_list.setWordWrap(True)
        self.ch_list.itemClicked.connect(self._clicked_meaning)
        lay.addWidget(self.ch_list, 1)
        row = QHBoxLayout()
        accept = QPushButton("Принять всё")
        accept.clicked.connect(self._accept_all)
        row.addStretch(1)
        row.addWidget(accept)
        lay.addLayout(row)
        return w

    def _begin_choosing(self, built, finish):
        """Second pass. ChoiceState edits the very drafts `built` holds, so
        finish() writes the notes with the user's choices already in them."""
        state = batch.ChoiceState([d for _, d, _ in built if d is not None])
        if self._cancelled or state.done:
            state.accept_all()
            finish()
            return
        self.choice = state
        self._finish_batch = finish
        self.stack.setCurrentIndex(PAGE_CHOOSE)
        self._show_choice()

    def _show_choice(self):
        st = self.choice
        if st is None:
            return
        if st.done:
            self._end_choosing()
            return
        d = st.current
        self.ch_title.setText("%s    %s" % (d.word, st.counter))
        self.ch_sentence.setText(d.values.get("front", ""))
        self._fill_roles(st)
        labels = st.meaning_labels()
        self.ch_list.clear()
        for i, text in enumerate(labels):
            self.ch_list.addItem(QListWidgetItem(
                "%s %s" % ("%d." % (i + 1) if i < 9 else "  ", text)))
        if labels:
            self.ch_info.setText("Значение: клик или цифра выбирает и ведёт к следующему слову.")
        else:
            self.ch_list.addItem(QListWidgetItem("значение не добыто — подтвердить и идти дальше"))
            self.ch_info.setText("Значение добыть не удалось: поле останется пустым.")

    def _fill_roles(self, st):
        while self.ch_roles.count():
            widget = self.ch_roles.takeAt(0).widget()
            if widget is not None:
                # deleteLater alone leaves the button painted at its old place
                # until the event loop spins: detach it from the row right now
                widget.setParent(None)
                widget.deleteLater()
        labels = st.role_labels() if st.needs_role() else []
        self.ch_roles_host.setVisible(bool(labels))
        if not labels:
            return
        chosen = st.current.role_index
        for i, text in enumerate(labels):
            button = QPushButton(text)
            button.setCheckable(True)
            button.setChecked(i == chosen)
            button.clicked.connect(lambda _=False, k=i: self._pick_role(k))
            self.ch_roles.addWidget(button)
        self.ch_roles.addStretch(1)

    def _pick_role(self, i):
        if self.choice is not None:
            self.choice.choose_role(i)   # the word stays, the meanings redraw
            self._show_choice()

    def _clicked_meaning(self, item):
        self._pick_meaning(self.ch_list.row(item))

    def _pick_meaning(self, row):
        if self.choice is not None and row >= 0:
            self.choice.choose_meaning(row)
            self._show_choice()

    def _accept_all(self):
        if self.choice is not None:
            self.choice.accept_all()
            self._end_choosing()

    def _end_choosing(self):
        self.choice = None
        finish, self._finish_batch = self._finish_batch, None
        if finish is not None:
            finish()


def register(mw):
    from .. import get_menu
    from aqt.qt import QAction
    menu = get_menu()
    if menu is None:
        return
    action = QAction("Добавить слова из книги", mw)
    action.triggered.connect(lambda: open_main(mw))
    menu.addAction(action)


def open_main(mw) -> None:
    if mw.col is None:
        return
    MainDialog(mw).exec()
