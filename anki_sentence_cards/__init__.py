try:
    from aqt import mw
    from aqt.qt import QAction
except ImportError:  # running outside Anki (tests)
    mw = None

if mw is not None:
    from .ui.settings_dialog import open_settings

    _action = QAction("Anki Sentence Cards: Настройки", mw)
    _action.triggered.connect(lambda: open_settings(mw))
    mw.form.menuTools.addAction(_action)
