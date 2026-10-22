"""The shipped add-on must read PDFs with no pypdf installed anywhere.

pypdf's modules import each other absolutely, so importing the vendored copy
as `anki_sentence_cards.vendor.pypdf` leaves those inner imports looking for a
top-level `pypdf`. A development venv with pypdf installed hides this: the
inner imports silently resolve to the installed copy and every test passes
while the shipped add-on fails on the user's machine with
"No module named 'pypdf'". This test runs in a subprocess with site-packages
stripped, so an installed pypdf cannot mask the failure again.
"""
import subprocess
import sys
import textwrap
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _run_without_site_packages(body: str):
    script = textwrap.dedent(
        """
        import sys
        sys.path = [p for p in sys.path if 'site-packages' not in p]
        sys.path.insert(0, %r)
        """
        % str(ROOT)
    ) + textwrap.dedent(body)
    return subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, cwd=str(ROOT)
    )


def test_pypdf_imports_without_site_packages():
    r = _run_without_site_packages(
        """
        from anki_sentence_cards.book.loaders import _ensure_pypdf
        pypdf = _ensure_pypdf()
        assert hasattr(pypdf, "PdfReader"), "no PdfReader on the vendored module"
        print("OK")
        """
    )
    assert r.returncode == 0, r.stderr
    assert "OK" in r.stdout


def test_pdf_is_read_without_site_packages(tmp_path):
    # Build the PDF here, where pytest is importable; the subprocess has no
    # site-packages at all, so it only reads the file.
    from tests.test_loaders import _tiny_pdf

    pdf = tmp_path / "s.pdf"
    pdf.write_bytes(_tiny_pdf(["Hello there."]))
    r = _run_without_site_packages(
        """
        from anki_sentence_cards.book import loaders
        import pathlib
        text = loaders.load_text(pathlib.Path(%r))
        assert "Hello" in text, text
        print("OK")
        """
        % str(pdf)
    )
    assert r.returncode == 0, r.stderr
    assert "OK" in r.stdout
