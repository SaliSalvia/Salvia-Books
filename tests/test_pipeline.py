# -*- coding: utf-8 -*-
"""
تستِ سرتاسری خط تولید: اجرای کاملِ CLI بدون هیچ کلید API، تا ساختن
PDF واقعی با Playwright — دقیقاً همان مسیری که workflow اجرا می‌کند.

نکته: ورودیِ پیش‌فرض فقط «نام کتاب» است؛ زبان خودکار تشخیص داده می‌شود.
"""

import json
import shutil
import sys
from pathlib import Path

import pytest
from pypdf import PdfReader

import generate_book
import render
from conftest import ROOT, ScriptedClient


def _prepare(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "manuscripts").mkdir()
    shutil.copy(ROOT / "manuscripts" / "the-little-prince-fa.txt",
                tmp_path / "manuscripts" / "the-little-prince-fa.txt")


def _run(tmp_path, monkeypatch, logo_path, lang="fa"):
    monkeypatch.setattr(generate_book, "REPO_ROOT", tmp_path)
    client = ScriptedClient()
    monkeypatch.setattr(generate_book.genai, "Client",
                        lambda api_key=None: client)
    argv = [
        "generate_book.py", "--title", "The Little Prince",
        "--api-key", "test-key",
        "--github-url", "https://github.com/test/repo",
        "--logo", str(logo_path),
    ]
    if lang:
        argv += ["--lang", lang]
    monkeypatch.setattr(sys, "argv", argv)
    generate_book.main()
    return client


def _report(tmp_path):
    return json.loads(
        (tmp_path / "_build" / "the-little-prince" / "layout.json")
        .read_text(encoding="utf-8"))


def test_full_run_builds_illustrated_pdf(tmp_path, monkeypatch):
    _prepare(tmp_path)
    logo = ROOT / "assets" / "logo.png"
    assert logo.is_file(), "لوگوی پیش‌فرض ریپو باید موجود باشد"
    client = _run(tmp_path, monkeypatch, logo)

    pdfs = list((tmp_path / "output").glob("*.pdf"))
    assert len(pdfs) == 1
    pdf = pdfs[0]
    assert pdf.name == "the-little-prince-fa.pdf"

    # ساختار HTML: همه‌ی بخش‌ها تصویر واقعی دارند (کلاین جعلی تصویر می‌دهد)
    html = next((tmp_path / "_build").rglob("book.html")).read_text(
        encoding="utf-8")
    n_sections = html.count('class="page image-page"')
    # متنِ کوتاه → بخش‌های کمتر ولی هر تصویر واقعی، نه جای‌گذار
    assert n_sections >= 2
    assert html.count('<img class="img-half"') == n_sections
    assert 'class="img-half placeholder"' not in html
    assert 'dir="rtl"' in html
    assert "Design by: @SaliSalvia" in html
    assert 'class="page contents-page"' in html   # فهرستِ تصاویر

    # فراخوانی‌های مدل: نرمال‌سازی + تحلیل + تصویر + جلد
    assert client.contents_matching("gutenberg_query")
    assert client.contents_matching("chapter_title")
    assert client.image_calls()

    # گزارش ساخت: صفحه‌بندی و تصاویر سالم‌اند
    report = _report(tmp_path)
    assert report["lang"] == "fa"
    assert report["source"] == "manual"
    assert report["overflow_pages"] == []              # هیچ متنی از کادر بیرون نزده
    assert report["line_cap"] in [render.line_cap_for("fa", i)
                                   for i in range(render.MAX_ATTEMPTS)]
    assert report["images"] == report["sections"] == n_sections

    # PDF واقعی با لایه‌ی متن
    reader = PdfReader(str(pdf))
    assert len(reader.pages) >= 10
    assert len(reader.pages) == report["pages"]        # نه صفحه‌ی سفید اضافه، نه گم‌شده
    assert pdf.stat().st_size > 30_000
    text = "\n".join((p.extract_text() or "") for p in reader.pages)
    if not text.strip():
        pytest.fail("لایه‌ی متنِ PDF خالی است (فونت/-render مشکل دارد)")
    assert "SaliSalvia" in text  # فوترِ برندشده در همه‌ی صفحات میانی

    # متادیتا و فهرستِ کنارِ PDF
    assert reader.metadata.title == "The Little Prince"
    assert reader.metadata.author == "Test Author"

    def flatten(items):
        for item in items:
            if isinstance(item, list):
                yield from flatten(item)
            else:
                yield getattr(item, "title", "")

    titles = list(flatten(reader.outline))
    assert titles[0] == "The Little Prince"          # سطح ۱: خود کتاب
    assert isinstance(reader.outline[1], list)       # سطح ۲: بخش‌ها زیر کتاب
    assert sum(1 for t in titles if "TEST PLATE" in t) == n_sections
    assert "درباره‌ی این نسخه" in titles             # پشت‌جلد


def test_auto_language_without_lang_flag(tmp_path, monkeypatch):
    # ورودی فقط نام کتاب: زبان از خودِ متن (فایل دستیِ فارسی) گرفته می‌شود
    _prepare(tmp_path)
    _run(tmp_path, monkeypatch, tmp_path / "no-logo.png", lang=None)
    assert [p.name for p in (tmp_path / "output").glob("*.pdf")] == [
        "the-little-prince-fa.pdf"]
    report = _report(tmp_path)
    assert report["lang"] == "fa"
    assert report["overflow_pages"] == []


def test_overflow_detector_flags_clipped_page(tmp_path):
    # اگر متن از کادر بیرون بزند، باید شناسایی شود (وگرنه بی‌صدا بریده می‌شود)
    html = (f'<html dir="rtl"><head><meta charset="utf-8"><style>'
            f':root {{ --font: Vazirmatn; }}{render.CSS}</style></head><body>'
            '<div class="page text-page"><div class="runhead">h</div>'
            + "<p>یک خط متن برای پرکردن صفحه.</p>" * 40 +
            '</div>'
            '<div class="page text-page"><div class="runhead">h</div>'
            '<p>کوتاه</p></div></body></html>')
    html_path = tmp_path / "book.html"
    html_path.write_text(html, encoding="utf-8")
    overflow = render.html_to_pdf(html_path, tmp_path / "out.pdf")
    assert overflow == [1]


def test_pagination_retries_with_smaller_cap(tmp_path, monkeypatch):
    # اگر یک صفحه سرریز کند، با سقفِ کمتر دوباره چیده میشود (نه بریدهشدنِ متن)
    work = tmp_path / "_build" / "x"
    work.mkdir(parents=True)
    out = tmp_path / "output"
    out.mkdir()
    calls = []

    def fake_html_to_pdf(html_path, pdf_path, *, metadata=None, outline=None):
        calls.append(1)
        Path(pdf_path).write_bytes(b"%PDF-1.4\n")
        return [3] if len(calls) < 3 else []

    monkeypatch.setattr(render, "html_to_pdf", fake_html_to_pdf)
    sections = [{"paragraphs": ["یک پاراگراف کوتاه."], "chapter_title": "بخش",
                 "chapter_kicker": "PLATE 1", "caption": "کپشن",
                 "image_path": None}]
    _pdf, layout, overflow = generate_book._render_pdf(
        workdir=work, out_dir=out, slug="x", lang="fa", title="T",
        author="A", blurb="", sections=sections, logo_uri="",
        github_url="")
    assert len(calls) == 3
    assert overflow == []
    assert layout["line_cap"] == render.line_cap_for("fa", 2)
    assert (work / "book.html").is_file()


def test_second_run_uses_cache(tmp_path, monkeypatch):
    _prepare(tmp_path)
    logo = ROOT / "assets" / "logo.png"
    first = _run(tmp_path, monkeypatch, logo)
    assert first.contents_matching("chapter_title")
    assert first.image_calls()

    # اجرای دوباره با همان متن: نه تحلیل دوباره، نه تصویر دوباره
    second = ScriptedClient()
    monkeypatch.setattr(generate_book.genai, "Client",
                        lambda api_key=None: second)
    generate_book.main()
    assert second.contents_matching("chapter_title") == []
    assert second.image_calls() == []
    assert second.contents_matching("gutenberg_query")  # نرمال‌سازی همچنان هست
    assert (tmp_path / "output" / "the-little-prince-fa.pdf").is_file()


def test_missing_logo_warns_but_builds(tmp_path, monkeypatch, capsys):
    _prepare(tmp_path)
    _run(tmp_path, monkeypatch, tmp_path / "does-not-exist.png")
    out = capsys.readouterr().out
    assert "لوگو پیدا نشد" in out
    pdfs = list((tmp_path / "output").glob("*.pdf"))
    assert len(pdfs) == 1
    html = next((tmp_path / "_build").rglob("book.html")).read_text(
        encoding="utf-8")
    # بدون لوگو، هیچ <img> از لوگو در جلد/فوتر نیست
    assert '<div class="brand"><span>' in html
