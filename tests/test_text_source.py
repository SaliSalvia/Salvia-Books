import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import text_source


class _Response:
    text = (
        '{"title_en":"Le Petit Prince",'
        '"title_fa":"شاهزاده کوچولو",'
        '"author":"Antoine de Saint-Exupery",'
        '"gutenberg_query":"Le Petit Prince"}'
    )


class _Models:
    def generate_content(self, model, contents):
        return _Response()


class _Client:
    models = _Models()


def test_get_source_text_uses_single_language_manual_fallback(tmp_path):
    manuscripts = tmp_path / "manuscripts"
    manuscripts.mkdir()
    manual = manuscripts / "the-little-prince-fa.txt"
    manual.write_text("متن دستی فارسی", encoding="utf-8")

    text, _norm, meta = text_source.get_source_text(
        _Client(), "fake-model", "شازده کوچولو", "fa", manuscripts
    )

    assert text == "متن دستی فارسی"
    assert meta == {"source": "manual", "path": str(manual)}


def test_get_source_text_checks_raw_title_before_gemini(tmp_path):
    manuscripts = tmp_path / "manuscripts"
    manuscripts.mkdir()
    manual = manuscripts / "the-little-prince-fa.txt"
    manual.write_text("متن دستی فارسی", encoding="utf-8")

    class FailIfCalled:
        @property
        def models(self):
            raise AssertionError("Gemini should not be called for exact manual matches")

    text, norm, meta = text_source.get_source_text(
        FailIfCalled(), "fake-model", "The Little Prince", "fa", manuscripts
    )

    assert text == "متن دستی فارسی"
    assert norm["title_en"] == "The Little Prince"
    assert meta == {"source": "manual", "path": str(manual)}
