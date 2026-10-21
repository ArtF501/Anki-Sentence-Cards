"""Anki Sentence Cards add-on entry point."""
try:
    from aqt import mw
    from aqt.qt import QAction
except ImportError:  # running outside Anki (tests)
    mw = None

_menu = None

if mw is not None:
    from .ui.settings_dialog import open_settings

    _menu = mw.form.menuTools.addMenu("Anki Sentence Cards")
    _action = QAction("Настройки", mw)
    _action.triggered.connect(lambda: open_settings(mw))
    _menu.addAction(_action)


def get_menu():
    """The add-on's Tools submenu, or None outside Anki.

    From ui/* modules use a function-level import so no cycle appears at
    load time (the package __init__ imports ui.settings_dialog):

        def register(mw):
            from .. import get_menu
            menu = get_menu()
            if menu is not None:
                action = QAction("...", mw)
                action.triggered.connect(...)
                menu.addAction(action)
    """
    return _menu
