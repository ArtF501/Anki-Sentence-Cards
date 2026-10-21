try:
    from aqt import mw
    from aqt.qt import QAction
    from aqt.utils import tooltip
except ImportError:  # running outside Anki (tests)
    mw = None

if mw is not None:
    _action = QAction("Sentence Cards", mw)
    _action.triggered.connect(lambda: tooltip("not implemented"))
    mw.form.menuTools.addAction(_action)
