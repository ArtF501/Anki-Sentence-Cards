try:
    from aqt import mw
    from aqt.qt import QAction
except ImportError:  # running outside Anki (tests)
    mw = None

if mw is not None:
    from .ui.settings_dialog import open_settings

    menu = mw.form.menuTools.addMenu("Anki Sentence Cards")  # task 11 adds its item here
    _action = QAction("Настройки", mw)
    _action.triggered.connect(lambda: open_settings(mw))
    menu.addAction(_action)
