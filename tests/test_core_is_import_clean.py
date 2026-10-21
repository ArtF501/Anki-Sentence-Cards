import re
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent / "anki_sentence_cards"
PATTERN = re.compile(r"^\s*(?:import|from)\s+(?:aqt|anki)\b", re.MULTILINE)


def _core_files():
    files = []
    for sub in ("book", "sources"):
        files += sorted((PKG / sub).glob("*.py"))
    files += [PKG / "card.py", PKG / "settings.py", PKG / "batch.py"]
    return [f for f in files if f.exists()]


def test_core_modules_never_import_anki():
    offenders = [str(f) for f in _core_files() if PATTERN.search(f.read_text(encoding="utf-8"))]
    assert offenders == []
