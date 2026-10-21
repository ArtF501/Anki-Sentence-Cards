"""Main window: paste words, pick a sentence for each, build cards, report.

All decisions live in ..batch (tested). This file is only Qt glue and is
verified by hand (see the task 11 report).
"""
import os

from aqt.operations import QueryOp
from aqt.qt import (
    QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPlainTextEdit,
    QPushButton, QSize, QStackedWidget, Qt, QVBoxLayout, QWidget,
)
from aqt.utils import showWarning

from .. import batch
from ..book.library import load_book
from ..book.loaders import BookLoadError
from ..book.search import find_occurrences
from ..card import build_draft
from ..notes import add_note, find_duplicate
from ..settings import load_settings

PAGE_INPUT, PAGE_PICK, PAGE_REPORT = 0, 1, 2


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
        self._busy = False
        self.total = batch.BatchResult()
        self.skipped_all = []
        self._retrying = []

        root = QVBoxLayout(self)
        self.stack = QStackedWidget()
        root.addWidget(self.stack)
        self.stack.addWidget(self._make_input())
        self.stack.addWidget(self._make_pick())
        self.stack.addWidget(self._make_report())

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
        if (self.stack.currentIndex() == PAGE_PICK and not self.manual_edit.hasFocus()
                and e.text() in tuple("123456789")):
            self._select(int(e.text()) - 1)
            return
        super().keyPressEvent(e)

    # ---- build
    def _finish_picking(self):
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
                    self._busy = False
                    self.start_btn.setEnabled(True)
                    if self.mw.col is None:
                        return  # profile closed meanwhile: nothing to write to
                    fn(arg)
                return inner

            QueryOp(parent=self, op=lambda _c: work(), success=guarded(ok)).failure(
                guarded(fail)).with_progress("Сборка карточек...").run_in_background()

        def done(res):
            self.total = batch.merge_results(self.total, res, self._retrying)
            self._retrying = []
            self._show_report()

        batch.run_batch(
            picks, lambda w: find_duplicate(col, deck, w),
            lambda w, o: build_draft(w, o, settings),
            lambda d: add_note(self.mw.col, d, deck, notetype, fmap),
            result, run_bg, done, progress)

    def reject(self):
        if self._busy:
            return  # a batch is being built: closing would lose its report
        super().reject()

    def closeEvent(self, e):
        if self._busy:
            e.ignore()
            return
        super().closeEvent(e)

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

    def _retry(self):
        words = batch.retry_words(self.total.outcomes)
        if words:
            self._retrying = words
            self._open_state(words)


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
