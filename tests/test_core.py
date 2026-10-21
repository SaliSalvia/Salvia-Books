# -*- coding: utf-8 -*-
"""
تست‌های آفلاینِ منطقِ خالص خط تولید — بدون شبکه و بدون کلید API.
"""

import json
import re
from types import SimpleNamespace

import pytest

import illustrate
import llm
import render
import text_source as ts
from conftest import (PNG_BYTES, ScriptedClient, image_response,
                      text_response)


class FakeError(Exception):
    def __init__(self, code, msg="boom"):
        self.code = code
        super().__init__(f"{code} {msg}")


# ---------------------------------------------------------------------------
# slugify / پاک‌سازی / تشخیص زبان
# ---------------------------------------------------------------------------

def test_slugify():
    assert ts.slugify("The Little Prince!") == "the-little-prince"
    assert ts.slugify("شازده کوچولو") == "شازده-کوچولو"
    assert ts.slugify("") == "book"


def test_clean_gutenberg_text():
    raw = (
        "*** START OF THE PROJECT GUTENBERG EBOOK X ***\n\n"
        "First paragraph.\n\n\n\n\nSecond paragraph.\n\n"
        "*** END OF THE PROJECT GUTENBERG EBOOK X ***\n\ntrailing junk"
    )
    out = ts.clean_gutenberg_text(raw)
    assert "First paragraph." in out
    assert "Second paragraph." in out
    assert "trailing junk" not in out
    # باگ قدیمی: خطوط خالیِ اضافه حذف نمی‌شدند
    assert "\n\n\n" not in out
    # و نباید پاراگراف‌ها را به هم بچسباند
    assert "First paragraph.\n\nSecond paragraph." in out


def test_guess_lang():
    assert ts.guess_lang("شازده کوچولو") == "fa"
    assert ts.guess_lang("Pride and Prejudice") == "en"
    assert ts.guess_lang("") == "en"
    assert ts.guess_lang("The Little Prince") == "en"


def test_normalize_strips_markdown_artifacts():
    raw = (
        "# فصل اول\n\n"
        "متنِ اولِ کتاب است.\n\n"
        "---\n\n"
        "**متنِ پررّهنگ** و *مورب* و `کد`.\n\n"
        "> نقل‌قول\n\n"
        "- بولت اول\n- بولت دوم\n\n"
        "[لینک](https://example.com/x)\n\n\n\n"
        "### عنوانِ سه\n"
    )
    out = ts.normalize_text(raw)
    assert "#" not in out and ">" not in out
    assert "---" not in out
    assert "**" not in out and "`" not in out
    assert "متنِ پررّهنگ" in out and "مورب" in out and "کد" in out
    assert "فصل اول" in out and "عنوانِ سه" in out
    assert "لینک" in out and "https://" not in out
    assert "بولت اول" in out and "بولت دوم" in out
    assert "\n\n\n" not in out


def test_looks_persian():
    fa = "این یک متن کاملاً فارسی است و جمله‌های پیاپی دارد. " * 30
    en = "This is a long English text with many sentences. " * 60
    assert ts.looks_persian(fa)
    assert not ts.looks_persian(en)
    # پیش‌گفتارِ فارسیِ کوتاه نباید متنِ انگلیسی را فارسی جلوه دهد (باگ قدیمی: [:200])
    mixed = "پیش‌گفتارِ مترجم به فارسی است و چند جمله دارد. " * 8 + " " + en
    assert not ts.looks_persian(mixed)
    # و بالعکس: متنِ فارسیِ اصلی با پانویسِ کوتاهِ انگلیسی
    mixed2 = fa + " See the English footnote for details. "
    assert ts.looks_persian(mixed2)


# ---------------------------------------------------------------------------
# llm.py: JSON، retry، زنجیره‌ی مدل
# ---------------------------------------------------------------------------

def test_extract_json():
    assert llm.extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert llm.extract_json('متن اضافه {"a": 1} بعد از آن') == {"a": 1}
    assert llm.extract_json('{"nested": {"b": 2}}') == {"nested": {"b": 2}}
    assert llm.extract_json("not json at all") is None
    assert llm.extract_json("[1, 2]") is None  # فقط شیء پذیرفته می‌شود
    assert llm.extract_json("") is None


def test_retry_on_transient_errors(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    calls = []

    def generate_content(model=None, contents=None, config=None):
        calls.append(model)
        if len(calls) < 3:
            raise FakeError(429, "quota exceeded")
        return SimpleNamespace(text="ok")

    client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    out = llm.generate_text(client, ["m1"], "hi")
    assert out == "ok"
    assert len(calls) == 3


def test_model_fallback_chain(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    used = []

    def generate_content(model=None, contents=None, config=None):
        used.append(model)
        if model == "missing":
            raise FakeError(404, "model not found")
        return SimpleNamespace(text="final")

    client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    out = llm.generate_text(client, ["missing", "ok"], "x")
    assert out == "final"
    assert used == ["missing", "ok"]


def test_non_retryable_raises_immediately(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    calls = []

    def generate_content(model=None, contents=None, config=None):
        calls.append(model)
        raise FakeError(400, "bad request")

    client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    with pytest.raises(FakeError):
        llm.generate_text(client, ["m1"], "x")
    assert len(calls) == 1


def test_all_models_missing_raises(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)

    def generate_content(model=None, contents=None, config=None):
        raise FakeError(404, "model not found")

    client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    with pytest.raises(llm.ModelNotAvailable):
        llm.generate_text(client, ["a", "b"], "x")


def test_model_chains_from_env(monkeypatch):
    monkeypatch.setenv("GEMINI_TEXT_MODEL", "custom-text")
    monkeypatch.setenv("GEMINI_IMAGE_MODEL", "custom-image")
    assert llm.text_models()[0] == "custom-text"
    assert "gemini-2.5-flash" in llm.text_models()  # زنجیره‌ی جایگزین
    assert llm.image_models()[0] == "custom-image"
    assert "gemini-2.5-flash-image" in llm.image_models()
    # هینتِ صریح مقدم است
    assert llm.text_models("explicit")[0] == "explicit"


# ---------------------------------------------------------------------------
# صفحه‌بندیِ render: مرز کلمه، عدم اتلاف متن، سقف صفحه
# ---------------------------------------------------------------------------

def test_paginate_word_boundaries_and_no_loss():
    para = " ".join(f"word{i}" for i in range(600))
    pages = render._paginate_paragraphs([para], max_chars=750)
    assert len(pages) >= 6
    for page in pages:
        assert sum(len(p) for p in page) <= 750
    words = [w for page in pages for p in page for w in p.split()]
    assert words == para.split()  # نه حرفی کم شده، نه وسطِ کلمه بریده شده


def test_paginate_hard_cut_keeps_everything():
    para = "ب" * 2000 + "c" * 100  # بدون هیچ فاصله‌ای
    pages = render._paginate_paragraphs([para])
    joined = "".join(p for page in pages for p in page)
    assert joined == para
    assert all(sum(len(p) for p in page) <= 750 for page in pages)
    assert len(pages) >= 3


def test_paginate_edge_cases():
    assert render._paginate_paragraphs([]) == [[]]
    pages = render._paginate_paragraphs(["کوتاه", "دیگر"])
    assert len(pages) == 1 and len(pages[0]) == 2


def test_render_placeholder_and_escaping(tmp_path):
    img = tmp_path / "pic.png"
    img.write_bytes(PNG_BYTES)
    sections = [
        {"paragraphs": ["پاراگراف اول.", "پاراگراف دوم."],
         "chapter_title": "عنوان یک", "chapter_kicker": "PLATE 1",
         "caption": "کپشن <script>alert(1)</script>", "image_path": str(img)},
        {"paragraphs": ["متن بخش دوم."],
         "chapter_title": "عنوان دو", "chapter_kicker": "PLATE 2",
         "caption": "کپشن دوم", "image_path": None},
    ]
    out = tmp_path / "book.html"
    layout = render.render_book_html(
        lang="fa", title="کتاب نمونه", author="نویسنده‌ی نمونه",
        blurb="توضیح جلد", sections=sections, logo_uri="",
        github_url="https://github.com/test/repo", out_html_path=out,
    )
    html = out.read_text(encoding="utf-8")
    assert 'dir="rtl"' in html
    assert "کتاب نمونه" in html
    assert "نویسنده‌ی نمونه" in html          # نویسنده روی جلد
    assert "<script>" not in html and "&lt;script&gt;" in html  # escape
    assert 'class="img-half placeholder"' in html               # بخشِ بدون تصویر
    assert '<img class="img-half"' in html                      # بخشِ با تصویر
    assert html.count("<img") == 1                              # لوگو خالی است
    assert '<div class="brand"><span>' in html                  # فوتر بدون لوگو
    assert '<div class="runhead">کتاب نمونه</div>' in html      # سرصفحه‌ی هر صفحه
    # جلد + فهرست + ۲×(متن+تصویر) + پشت‌جلد
    assert layout["page_count"] == 7
    assert len(html.split('class="page ')) - 1 == 7
    # شماره‌ی صفحه‌ها: جلد بی‌شماره، فهرست ۲، بعد ۳…۶، پشت‌جلد بی‌شماره
    assert [int(n) for n in re.findall(
        r'<div class="page-num">(\d+)</div>', html)] == [2, 3, 4, 5, 6]
    # فهرست: بخش‌ها با شماره‌ی صفحه‌ی شروعشان
    assert 'class="page contents-page"' in html
    assert [row[2] for row in layout["contents"]] == [3, 5]
    assert 'class="page cover"' in html and 'class="page backcover"' in html
    # متادیتای HTML → عنوانِ PDF
    assert "<title>کتاب نمونه — نویسنده‌ی نمونه</title>" in html


def test_render_splits_contents_over_pages(tmp_path):
    # کتابِ چندبخشی: فهرست نباید از کادر بیرون بزند
    sections = [
        {"paragraphs": ["متن کوتاه."], "chapter_title": f"بخش {i}",
         "chapter_kicker": f"PLATE {i}", "caption": f"کپشن {i}",
         "image_path": None}
        for i in range(1, 31)
    ]
    out = tmp_path / "book.html"
    layout = render.render_book_html(
        lang="fa", title="کتاب پرحجم", author="نویسنده", blurb="",
        sections=sections, logo_uri="",
        github_url="https://github.com/test/repo", out_html_path=out,
    )
    html = out.read_text(encoding="utf-8")
    n_contents = html.count('class="page contents-page"')
    assert n_contents == -(-len(sections) // render.CONTENTS_ROWS_PER_PAGE)
    assert n_contents > 1
    rows = re.findall(r'<div class="row">', html)
    assert len(rows) == len(sections)          # هیچ بخشی از فهرست جا نمی‌افتد
    # شماره‌های فهرست پیوسته و درست‌اند (بعد از همه‌ی صفحه‌های فهرست)
    assert [row[2] for row in layout["contents"]] == [
        2 + n_contents + 2 * i for i in range(len(sections))]
    assert layout["page_count"] == 1 + n_contents + 2 * len(sections) + 1


def test_render_english_without_author(tmp_path):
    out = tmp_path / "book.html"
    render.render_book_html(
        lang="en", title="A Book", author="", blurb="", sections=[],
        logo_uri="", github_url="https://github.com/test/repo",
        out_html_path=out,
    )
    html = out.read_text(encoding="utf-8")
    assert 'dir="ltr"' in html
    assert 'class="author"' not in html
    assert "<img" not in html


# ---------------------------------------------------------------------------
# illustrate: تقسیم متن، مقاومت در برابر شکست API
# ---------------------------------------------------------------------------

def test_chunking_covers_all_text():
    paragraphs = [
        f"این پاراگراف شماره {i} است و کمی طول دارد. " + "متنِ تکراری برای بلند شدن. " * 8
        for i in range(90)
    ]
    chunks = illustrate.chunk_text_by_target_pages(paragraphs)
    assert len(chunks) >= 3
    assert all(c.strip() for c in chunks)
    # هیچ متنی نه گم می‌شود نه تکرار
    assert " ".join(chunks).split() == " ".join(paragraphs).split()


def test_chunking_deterministic_for_same_text():
    paragraphs = ["پاراگراف " + "واژه " * 30 + str(i) for i in range(40)]
    a = illustrate.chunk_text_by_target_pages(paragraphs)
    b = illustrate.chunk_text_by_target_pages(list(paragraphs))
    assert a == b  # بذر قطعی → کش در اجرای دوباره کار می‌کند


def test_chunking_giant_paragraph_and_page_limit():
    giant = ("جمله‌ی کوتاهی اینجا هست. " * 30 + "\n") * 60  # ~۴۵هزار نویسه، یک پاراگراف
    chunks = illustrate.chunk_text_by_target_pages([giant])
    assert len(chunks) >= 3
    max_len = illustrate.MAX_PAGES_PER_IMAGE * illustrate.CHARS_PER_PAGE
    for chunk in chunks:
        assert len(chunk) <= max_len  # هرگز بیش از سقفِ ۱۱ صفحه
        # و با صفحه‌بندیِ render هم سازگار است
        pages = render._paginate_paragraphs(
            illustrate.split_into_paragraphs(chunk))
        assert 1 <= len(pages) <= illustrate.MAX_PAGES_PER_IMAGE + 1


def test_analyze_chunk_bad_json_falls_back():
    client = ScriptedClient(lambda c, cfg: text_response("این json نیست"))
    meta = illustrate.analyze_chunk(client, "متن بخش آزمایشی", "fa")
    assert meta["caption"] == "متن بخش آزمایشی"[:200]
    assert meta["image_prompt_en"].startswith("An atmospheric")


def test_analyze_chunk_tolerates_braces_in_text():
    # متنِ کتابِ حاوی آکولاد نباید پرامپتِ .format را بشکند (باگ قدیمی)
    payload = json.dumps({
        "chapter_title": "عنوان", "chapter_kicker": "KICK",
        "caption": "کپشن", "image_prompt_en": "prompt",
    }, ensure_ascii=False)
    client = ScriptedClient(lambda c, cfg: text_response(
        f"```json\n{payload}\n```"))
    meta = illustrate.analyze_chunk(
        client, "متن با {آکولاد} و {و} نشانه", "fa")
    assert meta["chapter_title"] == "عنوان"
    assert meta["chapter_kicker"] == "KICK"


def test_generate_image_success_and_failure(tmp_path):
    ok_client = ScriptedClient()  # handler پیش‌فرض تصویر برمی‌گرداند
    path = tmp_path / "img.png"
    assert illustrate.generate_image(ok_client, "a scene", path) is True
    assert path.read_bytes() == PNG_BYTES

    text_only = ScriptedClient(lambda c, cfg: text_response("بدون تصویر"))
    path2 = tmp_path / "img2.png"
    assert illustrate.generate_image(text_only, "a scene", path2) is False
    assert not path2.exists()


def test_build_sections_survives_api_failure(tmp_path):
    # کلاینی که برای تحلیل و تصویر همیشه خطای 503 می‌دهد
    def boom(c, cfg):
        raise FakeError(503, "server error")

    client = ScriptedClient(boom)
    sections = illustrate.build_sections(
        client, "بند اول.\n\nبند دوم.\n\nبند سوم.", "fa", tmp_path)
    assert sections  # کتاب نباید به‌خاطر شکست API از بین برود
    for sec in sections:
        assert sec["paragraphs"]
        assert sec["image_path"] is None


# ---------------------------------------------------------------------------
# text_source: زنجیره‌ی منابع (بدون شبکه)
# ---------------------------------------------------------------------------

def test_get_source_text_manual(tmp_path):
    mdir = tmp_path / "manuscripts"
    mdir.mkdir()
    (mdir / "the-little-prince-fa.txt").write_text(
        "متنِ فارسیِ آزمایشیِ کتاب.", encoding="utf-8")
    client = ScriptedClient()
    text, norm, meta = ts.get_source_text(
        client, None, "The Little Prince", "fa", mdir)
    assert meta["source"] == "manual"
    assert text.startswith("متنِ فارسی")
    assert norm["title_en"] == "The Little Prince"


def test_get_source_text_gutenberg_then_translate(tmp_path, monkeypatch):
    mdir = tmp_path / "manuscripts"
    mdir.mkdir()
    fake_book = "Once upon a time in a very long English novel. " * 120
    monkeypatch.setattr(ts, "find_public_domain_text",
                        lambda *a, **k: (fake_book, {"title": "x"}))
    client = ScriptedClient()
    text, norm, meta = ts.get_source_text(
        client, None, "Some Unknown Novel", "fa", mdir)
    assert meta["source"] == "gutenberg"
    assert meta["translated"] is True
    assert "ترجمه‌شده" in text
    # و ترجمه بخش‌به‌بخش انجام شده (حداقل دو فراخوانی)
    assert len(client.contents_matching("ترجمه")) >= 1


def test_get_source_text_archive_fallback(tmp_path, monkeypatch):
    mdir = tmp_path / "manuscripts"
    mdir.mkdir()
    monkeypatch.setattr(ts, "find_public_domain_text",
                        lambda *a, **k: (None, None))
    fake_book = "An archive edition of a very long novel. " * 120
    monkeypatch.setattr(ts, "find_archive_text",
                        lambda *a, **k: (fake_book, {"title": "y"}))
    client = ScriptedClient()
    text, norm, meta = ts.get_source_text(
        client, None, "Another Book", "en", mdir)
    assert meta["source"] == "archive_org"
    assert meta.get("translated") is None
    assert "archive edition" in text


def test_get_source_text_all_sources_empty(tmp_path, monkeypatch):
    mdir = tmp_path / "manuscripts"
    mdir.mkdir()
    monkeypatch.setattr(ts, "find_public_domain_text",
                        lambda *a, **k: (None, None))
    monkeypatch.setattr(ts, "find_archive_text",
                        lambda *a, **k: (None, None))
    monkeypatch.setattr(ts, "fetch_from_any_source",
                        lambda *a, **k: (None, None))
    client = ScriptedClient()
    with pytest.raises(ts.ManualTextRequired) as exc:
        ts.get_source_text(client, None, "Unknown Book XYZ", "en", mdir)
    assert "manuscripts/unknown-book-xyz-en.txt" in str(exc.value)


def test_get_source_text_auto_adopts_found_language(tmp_path, monkeypatch):
    mdir = tmp_path / "manuscripts"
    mdir.mkdir()
    novel = ("It was a bright cold day in April and the clocks were "
             "striking thirteen. ") * 60
    monkeypatch.setattr(ts, "find_public_domain_text",
                        lambda *a, **k: (novel, {"title": "x"}))
    client = ScriptedClient()
    text, norm, meta = ts.get_source_text(client, None, "1984", "auto", mdir)
    assert meta["lang"] == "en"
    assert meta.get("translated") is None       # در حالت خودکار ترجمه نمی‌شود
    assert "clocks were striking" in text


def test_get_source_text_auto_uses_manual_manuscript(tmp_path, monkeypatch):
    mdir = tmp_path / "manuscripts"
    mdir.mkdir()
    (mdir / "the-little-prince-fa.txt").write_text(
        "متنِ فارسیِ دستیِ کتاب.", encoding="utf-8")

    def boom(*a, **k):
        raise AssertionError("با وجود فایل دستی نباید سراغ گوتنبرگ برود")

    monkeypatch.setattr(ts, "find_public_domain_text", boom)
    client = ScriptedClient()
    text, norm, meta = ts.get_source_text(
        client, None, "The Little Prince", "auto", mdir)
    assert meta["source"] == "manual"
    assert meta["lang"] == "fa"                 # زبان از خودِ فایل دستی


def test_get_source_text_explicit_en_with_persian_source(tmp_path, monkeypatch):
    mdir = tmp_path / "manuscripts"
    mdir.mkdir()
    persian = "این یک متنِ بلندِ فارسی از یک کتاب است که باید بماند. " * 40
    monkeypatch.setattr(ts, "find_public_domain_text",
                        lambda *a, **k: (persian, {"title": "x"}))
    client = ScriptedClient()
    text, norm, meta = ts.get_source_text(client, None, "Shahnameh", "en", mdir)
    assert meta["lang"] == "fa"  # صفحه‌آرایی با زبانِ واقعیِ متن هم‌خوان می‌شود
    assert "فارسی از یک کتاب" in text


def test_validate_candidate_accept_and_reject():
    yes = ScriptedClient(lambda c, cfg: text_response(
        '{"verdict": "yes", "reason": "درست"}'))
    ok, _ = ts.validate_candidate_text(yes, llm.text_models(), "T", "A", "متن")
    assert ok is True

    no = ScriptedClient(lambda c, cfg: text_response(
        '{"verdict": "no", "reason": "نقد کتاب است"}'))
    ok, reason = ts.validate_candidate_text(no, llm.text_models(), "T", "A", "متن")
    assert ok is False
    assert "نقد" in reason

    # اگر خودِ داور در دسترس نبود، متنِ دانلودشده نباید بی‌دلیل رد شود
    broken = ScriptedClient(lambda c, cfg: (_ for _ in ()).throw(
        RuntimeError("down")))
    ok, _ = ts.validate_candidate_text(broken, llm.text_models(), "T", "A", "متن")
    assert ok is True


# ---------------------------------------------------------------------------
# وب‌اسکرپ: استخراج، ریدایرکت‌ها، فیلترها
# ---------------------------------------------------------------------------

def test_extract_text_from_html():
    html = """
    <html><body>
      <nav><a href="/">خانه</a><a href="/about">درباره ما</a></nav>
      <script>var x = "بدون متن";</script>
      <article>
        <p>این یک پاراگراف کاملاً بلند از دلِ کتاب است که باید استخراج شود.</p>
        <p>کوتاه</p>
        <p>پاراگراف دومِ بلند که باید با فاصله از اولی جدا شود و در خروجی بماند.</p>
      </article>
      <footer>حقوق ناشر</footer>
    </body></html>
    """
    text = ts._extract_text_from_html(html)
    assert "پاراگراف کاملاً بلند" in text
    assert "پاراگراف دومِ بلند" in text
    assert "بدون متن" not in text
    assert "خانه" not in text
    assert "حقوق ناشر" not in text
    assert "\n\n" in text  # مرزِ پاراگراف حفظ شده


def test_iter_result_urls_ddg_and_google():
    ddg = '<a class="r" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.example.com%2Fbook&t=x">Book</a>'
    urls = ts.iter_result_urls("duckduckgo", ddg)
    assert urls == ["https://www.example.com/book"]

    google = (
        '<a href="/url?q=https%3A%2F%2Fwww.example.org%2Ftext&sa=U">result</a>'
        '<a href="/search?q=another">nav</a>'
        '<a href="https://www.youtube.com/watch?v=1">video</a>'
    )
    urls = ts.iter_result_urls("google", google)
    assert urls == ["https://www.example.org/text"]  # /url?q= باز می‌شود


def test_unwrap_bing_redirect():
    import base64 as _b64
    target = "https://www.example.com/the-time-machine"
    enc = "a1" + _b64.urlsafe_b64encode(target.encode()).decode().rstrip("=")
    assert ts._unwrap_result_url("bing", f"https://www.bing.com/ck/a?!&p=abc&u={enc}") == target
    assert ts._unwrap_result_url("bing", f"/ck/a?u={enc}") == target  # نسبی
    assert ts._unwrap_result_url("bing", "/ck/a?u=a1!!!!") == ""      # خراب
    # لینکِ عادیِ خارجی دست‌نخورده برمی‌گردد
    assert (ts._unwrap_result_url("bing", "https://other.example/x")
            == "https://other.example/x")


def test_gutenberg_html_search_parses(monkeypatch):
    html = """
    <html><body>
      <span class="booklink"><a class="link" href="/ebooks/1342">
        <span class="title">Pride and Prejudice</span>
        <span class="author">by Jane Austen</span></a></span>
      <span class="booklink"><a class="link" href="/ebooks/1661">
        <span class="title">Adventures of Sherlock Holmes</span>
        <span class="author">by Arthur Conan Doyle</span></a></span>
    </body></html>
    """

    class FakeResp:
        status_code = 200

        def __init__(self):
            self.text = html

    monkeypatch.setattr(ts, "SESSION", type("FakeSession", (), {
        "get": lambda self, *a, **k: FakeResp(),
    })())
    out = ts.gutenberg_html_search("pride and prejudice austen")
    assert [b["id"] for b in out] == [1342, 1661]
    assert out[0]["title"] == "Pride and Prejudice"
    assert out[0]["authors"][0]["name"] == "Jane Austen"  # «by» حذف شده
    assert out[0]["_html_fallback"] is True


def test_find_public_domain_text_falls_back_when_gutendex_down(monkeypatch):
    book_text = (
        "It is a truth universally acknowledged that a single man in possession "
        "of a good fortune must be in want of a wife. "
    ) * 40
    monkeypatch.setattr(ts, "gutendex_search", lambda *a, **k: [])
    monkeypatch.setattr(ts, "gutenberg_html_search", lambda q, limit=8: [{
        "id": 1342, "title": "Pride and Prejudice",
        "authors": [{"name": "Jane Austen"}], "languages": [],
        "_html_fallback": True,
    }])

    class FakeResp:
        status_code = 200
        headers = {"content-type": "text/plain; charset=utf-8"}

        def __init__(self):
            self.text = book_text

    monkeypatch.setattr(ts, "SESSION", type("FakeSession", (), {
        "get": lambda self, *a, **k: FakeResp(),
    })())
    text, meta = ts.find_public_domain_text(
        "Pride and Prejudice Jane Austen", "en",
        want_title="Pride and Prejudice", want_author="Jane Austen")
    assert text and len(text) > 800
    assert meta["gutenberg_id"] == 1342
    assert meta["source_url"].endswith("/pg1342.txt")
    assert meta["title"] == "Pride and Prejudice"


def test_fetchable_url_guards():
    assert ts._is_fetchable_url("https://example.com/chapter-1")
    assert not ts._is_fetchable_url("http://127.0.0.1:8080/x")
    assert not ts._is_fetchable_url("http://10.0.0.5/x")
    assert not ts._is_fetchable_url("http://169.254.169.254/latest/meta")
    assert not ts._is_fetchable_url("http://localhost/x")
    assert not ts._is_fetchable_url("https://example.com/image.jpg")
    assert not ts._is_fetchable_url("https://www.youtube.com/watch?v=1")
    assert not ts._is_fetchable_url("file:///etc/passwd")


def test_looks_like_book_text():
    prose = "\n".join("این جمله‌ی بلندی است از یک کتاب واقعی و ادامه دارد. " * 4
                      for _ in range(30))
    assert ts.looks_like_book_text(prose)
    nav = "\n".join(["خانه", "درباره ما", "تماس", "ورود"] * 30)
    assert not ts.looks_like_book_text(nav)
    assert not ts.looks_like_book_text("کوتاه")


# ---------------------------------------------------------------------------
# ترجمه: بخش‌بندی و مقاومت در برابر آکولادِ متن
# ---------------------------------------------------------------------------

def test_translate_chunks_without_breaking_on_braces():
    big = ("پاراگرافِ نسبتاً بلندِ کتاب با {آکولاد} و {قالب} است. " * 10 + "\n\n") * 8
    client = ScriptedClient()
    out = ts.translate_to_persian(client, llm.text_models(), big)
    assert "ترجمه‌شده" in out
    # متنِ ورودی بلندتر از یک بخش است → بیش از یک فراخوانی
    assert len(client.contents_matching("ترجمه")) >= 2
