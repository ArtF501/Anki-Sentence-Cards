"""Settings window: books, deck, note type, DeepL key, voice, field mapping."""
from aqt.qt import (
    QButtonGroup, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QRadioButton, QVBoxLayout, QWidget,
)

from aqt.utils import showWarning

from ..notes import plan_field_map, resolve_field_map
from ..settings import (
    add_book, load_settings, merge_for_save, normalize_active, remove_book,
)
from .field_map_dialog import open_field_map


def _addon(mw) -> str:
    return mw.addonManager.addonFromModule(__name__)


def _fill_combo(combo: QComboBox, names, current: str) -> None:
    combo.clear()
    items = list(names)
    if current and current not in items:
        items.insert(0, current)  # keep a value that left the collection visible
    for n in items:
        combo.addItem(n)
    if current:
        combo.setCurrentIndex(max(combo.findText(current), 0))


def _notetype_fields(mw, notetype: str):
    model = mw.col.models.by_name(notetype)
    return [f["name"] for f in model["flds"]] if model else None


class SettingsDialog(QDialog):
    def __init__(self, mw):
        super().__init__(mw)
        self.mw = mw
        self.setWindowTitle("Anki Sentence Cards: настройки")
        self.setMinimumWidth(520)
        self._raw = mw.addonManager.getConfig(_addon(mw)) or {}
        self.s = load_settings(self._raw)
        self.s.active_book = normalize_active(self.s.books, self.s.active_book)
        self._map_notetype = self.s.notetype  # note type the current field_map was built for

        root = QVBoxLayout(self)
        root.addWidget(QLabel("Книги (отметьте активную):"))
        self._books_box = QVBoxLayout()
        root.addLayout(self._books_box)
        self._group = QButtonGroup(self)
        add_btn = QPushButton("Добавить файл")
        add_btn.clicked.connect(self._add_book)
        root.addWidget(add_btn)

        form = QFormLayout()
        root.addLayout(form)
        self._deck = QComboBox()
        names = [d.name for d in mw.col.decks.all_names_and_ids(include_filtered=False)]
        _fill_combo(self._deck, names, self.s.deck)
        form.addRow("Колода", self._deck)
        self._notetype = QComboBox()
        _fill_combo(self._notetype, [m.name for m in mw.col.models.all_names_and_ids()], self.s.notetype)
        form.addRow("Тип заметки", self._notetype)
        self._key = QLineEdit(self.s.deepl_key)
        form.addRow("Ключ DeepL", self._key)
        self._lang = QComboBox()
        self._lang.addItems(["en-GB", "en-US"])
        self._lang.setCurrentIndex(max(self._lang.findText(self.s.tts_lang), 0))
        form.addRow("Озвучка", self._lang)

        map_btn = QPushButton("Сопоставить поля вручную")
        map_btn.clicked.connect(self._map_manually)
        root.addWidget(map_btn)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self._rebuild_books()

    # books
    def _rebuild_books(self) -> None:
        while self._books_box.count():
            w = self._books_box.takeAt(0).widget()
            if w is not None:
                self._group.removeButton(w.findChild(QRadioButton))
                w.deleteLater()
        for path in self.s.books:
            row = QWidget()
            lay = QHBoxLayout(row)
            lay.setContentsMargins(0, 0, 0, 0)
            radio = QRadioButton(path)
            radio.setChecked(path == self.s.active_book)
            radio.toggled.connect(lambda on, p=path: on and setattr(self.s, "active_book", p))
            self._group.addButton(radio)
            btn = QPushButton("Удалить")
            btn.clicked.connect(lambda _=False, p=path: self._remove_book(p))
            lay.addWidget(radio, 1)
            lay.addWidget(btn)
            self._books_box.addWidget(row)

    def _add_book(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Выберите книгу", "", "Книги (*.txt *.epub *.pdf);;Все файлы (*)"
        )
        if not path:
            return
        self.s.books = add_book(self.s.books, path)
        if not self.s.active_book:
            self.s.active_book = self.s.books[0]
        self._rebuild_books()

    def _remove_book(self, path: str) -> None:
        self.s.books, self.s.active_book = remove_book(self.s.books, self.s.active_book, path)
        self._rebuild_books()

    # field mapping
    def _map_manually(self) -> None:
        self._run_field_map(force=True)

    def _run_field_map(self, force: bool) -> None:
        notetype = self._notetype.currentText()
        fields = _notetype_fields(self.mw, notetype)
        if fields is None:
            return
        keep, unresolved = plan_field_map(fields, self.s.field_map, self._map_notetype, notetype)
        if unresolved or force:
            chosen = open_field_map(self.mw, fields, keep)
            if chosen is not None:
                keep = chosen
        self.s.field_map = keep
        self._map_notetype = notetype

    def _save(self) -> None:
        self._run_field_map(force=False)
        self.s.deck = self._deck.currentText()
        self.s.notetype = self._notetype.currentText()
        self.s.deepl_key = self._key.text().strip()
        self.s.tts_lang = self._lang.currentText()
        self.mw.addonManager.writeConfig(_addon(self.mw), merge_for_save(self._raw, self.s))
        fields = _notetype_fields(self.mw, self.s.notetype)
        if fields is not None and "front" in resolve_field_map(fields, self.s.field_map)[1]:
            showWarning("Поле front не сопоставлено: карточки создаваться не будут, пока вы его не выберете.")
        self.accept()


def open_settings(mw) -> None:
    if mw.col is None:
        return
    SettingsDialog(mw).exec()
