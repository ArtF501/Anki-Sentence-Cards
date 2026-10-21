# Anki Sentence Cards

Anki add-on (23.10+, Qt6): builds sentence cards from a book file for a list of English words.
Paste a column of words, click the right sentence from the e-book for each, get cards
(sentence with the word in bold, translation, part of speech, IPA, meaning, mp3).

## Install

Linux/macOS: copy or symlink the `anki_sentence_cards` folder into Anki's `addons21` folder
(Tools > Add-ons > View Files opens it), then restart Anki.

Windows: `addons21` is at `%APPDATA%\Anki2\addons21`. Copy the whole `anki_sentence_cards`
folder there (File Explorer, or `xcopy /E /I anki_sentence_cards "%APPDATA%\Anki2\addons21\anki_sentence_cards"`),
restart Anki. Alternatively zip the *contents* of the folder (`manifest.json` must be at the zip root)
and rename it to `.ankiaddon`, then Tools > Add-ons > Install from file.

## Tests

`./.venv/bin/pytest -q` from the repository root (create the venv with `python3 -m venv .venv`
and `.venv/bin/pip install pytest`). Anki is not needed: only pure logic is tested; the Qt
files in `ui/` are checked by hand.

## Module map (`anki_sentence_cards/`)

- `__init__.py` - add-on entry, menu item.
- `settings.py` - settings model, config loading, field-map helpers (pure).
- `batch.py` - word list parsing, sentence picking state, batch run, report (pure).
- `card.py` - assembles one card draft from the sentence and the sources.
- `notes.py` - writes a draft into the collection, field mapping, duplicate check.
- `book/loaders.py` - .txt/.epub/.pdf to raw text; `book/normalize.py` - cleanup;
  `book/sentences.py` - sentence split; `book/search.py` - word search with inflections;
  `book/library.py` - book cache.
- `sources/` - network sources: `translate.py` (DeepL, Google), `dictionary.py` (dictionaryapi.dev),
  `meaning.py` (Reverso + translation), `tts.py` (Google TTS), `http.py` (shared client).
- `ui/` - Qt dialogs (main window, settings, manual field mapping).
- `vendor/` - bundled pypdf and typing_extensions.

## When Reverso changes its layout

Meanings are scraped from Reverso. If they stop appearing (cards get the `auto-incomplete` tag with
a "значение слова" error), the markup changed. The fix lives in one function:
`_parse_reverso` in `anki_sentence_cards/sources/meaning.py`. Update it against a fresh page and refresh
the fixture `tests/fixtures/reverso_contemporary.html`.
