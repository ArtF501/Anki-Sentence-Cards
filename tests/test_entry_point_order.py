"""get_menu must be defined before the block that calls register(mw).

`register` does a function-level `from .. import get_menu`, but it is called
while the package is still initialising, so the name has to be bound already.
Anki reported this as a circular ImportError on the user's first launch.
"""
import ast
import pathlib

SRC = pathlib.Path(__file__).resolve().parents[1] / "anki_sentence_cards" / "__init__.py"


def _tree():
    return ast.parse(SRC.read_text(encoding="utf-8"))


def test_get_menu_is_defined_before_the_mw_block():
    get_menu_line = None
    mw_block_line = None
    for node in _tree().body:
        if isinstance(node, ast.FunctionDef) and node.name == "get_menu":
            get_menu_line = node.lineno
        if isinstance(node, ast.If) and ast.unparse(node.test) == "mw is not None":
            mw_block_line = node.lineno
    assert get_menu_line is not None, "get_menu disappeared from the entry point"
    assert mw_block_line is not None, "the `if mw is not None` block disappeared"
    assert get_menu_line < mw_block_line, (
        "get_menu is defined after the block that calls register(mw); "
        "register imports it at call time and Anki fails with a circular ImportError"
    )
