"""Manual mapping of logical card keys to note type fields."""
from typing import Dict, List, Optional

from aqt.qt import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QVBoxLayout,
)
from aqt.utils import showWarning

from ..notes import DEFAULT_FIELD_NAMES, mappable_fields, resolve_field_map
from ..settings import NOT_FILLED, build_field_map

NOT_FILLED_LABEL = "не заполнять"


class FieldMapDialog(QDialog):
    def __init__(self, parent, notetype_fields: List[str], saved: Dict[str, str]):
        super().__init__(parent)
        self.setWindowTitle("Сопоставление полей")
        fields = mappable_fields(notetype_fields)
        current, _unresolved = resolve_field_map(notetype_fields, saved)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Какое поле заметки заполнять для каждой части карточки.\n"
            "Лицевая сторона (front) обязательна, остальные можно не заполнять."
        ))
        form = QFormLayout()
        layout.addLayout(form)
        self._combos = {}  # type: Dict[str, QComboBox]
        for key in DEFAULT_FIELD_NAMES:
            combo = QComboBox()
            combo.addItem(NOT_FILLED_LABEL, NOT_FILLED)
            for name in fields:
                combo.addItem(name, name)
            idx = combo.findData(current.get(key, NOT_FILLED))
            combo.setCurrentIndex(max(idx, 0))
            self._combos[key] = combo
            form.addRow(key, combo)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.result_map = {}  # type: Dict[str, str]

    def _on_accept(self) -> None:
        choices = {k: c.currentData() for k, c in self._combos.items()}
        result, ok, collision = build_field_map(choices)
        if not ok:
            showWarning("Поле для front нужно выбрать: без него карточку не создать.")
            return
        if collision:
            showWarning("Одно поле выбрано для нескольких частей карточки: "
                        "значения затрут друг друга. Выберите разные поля.")
            return
        self.result_map = result
        self.accept()


def open_field_map(mw, notetype_fields: List[str], saved: Dict[str, str]) -> Optional[Dict[str, str]]:
    """Show the dialog; return the chosen map, or None if cancelled."""
    dlg = FieldMapDialog(mw, notetype_fields, saved)
    if dlg.exec():
        return dlg.result_map
    return None
