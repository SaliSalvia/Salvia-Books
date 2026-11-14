# -*- coding: utf-8 -*-
"""تست‌های خلاصه‌سازیِ درصدی و صفحه‌آراییِ نسخهٔ دوزبانه — بدونِ شبکه."""

import json
import re

import pytest

import illustrate
import render
import summarize
from conftest import ScriptedClient, text_response


class FakeError(Exception):
    pass


# ---------------------------------------------------------------------------
# خلاصه‌سازی
# ---------------------------------------------------------------------------

def test_clamp_percent():
    assert summarize.clamp_percent(0) == 0
    assert summarize.clamp_percent(-5) == 0
    assert summarize.clamp_percent(40) == 40
    assert summarize.clamp_percent("40") == 40
    assert summarize.clamp_percent(100) == 95
    assert summarize.clamp_percent(999) == 95
    assert summarize.clamp_percent("نامعتبر") == 0
    assert summarize.clamp_percent(None) == 0


def test_percent_zero_returns_text_untouched():
    client = ScriptedClient(lambda c, cfg: pytest.fail("نباید مدل صدا زده شود"))
    original = "متنِ کاملِ کتاب.\n\nپاراگرافِ دوم."
    assert summarize.summarize_text(client, original, 0, "fa") == original


def test_summarize_sends_percentage_and_target_length():
    seen = []

    def handler(contents, config):
        seen.append(contents)
        return text_response("متنِ فشرده‌شده‌ی آزمایشی.")

    client = ScriptedClient(handler)
    text = "\n\n".join(["پاراگرافِ طولانیِ کتاب " * 20] * 4)
    out = summarize.summarize_text(client, text, 30, "fa")
    assert out == "متنِ فشرده‌شده‌ی آزمایشی."
    assert seen and "30 درصد" in seen[0]
    assert "فارسی" in seen[0]


def test_summarize_falls_back_to_original_on_error():
    def boom(contents, config):
        raise FakeError("quota")

    client = ScriptedClient(boom)
    text = "\n\n".join([f"پاراگراف {i} " * 30 for i in range(6)])
    out = summarize.summarize_text(client, text, 50, "fa")
    # شکستِ مدل نباید متن را حذف کند
    assert out.split() == text.split()


# ---------------------------------------------------------------------------
# صفحه‌آراییِ دوزبانه
# ---------------------------------------------------------------------------

def test_bilingual_pages_render_between_text_and_plate(tmp_path):
    sections = [
        {"paragraphs": ["متن فارسی بخش یک."], "alt_lang": "en",
         "alt_paragraphs": ["The English text of section one."],
         "chapter_title": "بخش یک", "chapter_kicker": "PLATE 1",
         "caption": "کپشن یک", "image_path": None},
        {"paragraphs": ["متن فارسی بخش دو."], "alt_lang": "en",
         "alt_paragraphs": ["The English text of section two."],
         "chapter_title": "بخش دو", "chapter_kicker": "PLATE 2",
         "caption": "کپشن دو", "image_path": None},
    ]
    out = tmp_path / "book.html"
    layout = render.render_book_html(
        lang="fa", title="کتاب نمونه", author="نویسنده", blurb="معرفی",
        sections=sections, logo_uri="", github_url="", out_html_path=out,
        alt_title="The Sample Book")
    html = out.read_text(encoding="utf-8")

    assert html.count('class="page text-page alt-page"') == 2
    assert "The English text of section one." in html
    assert "The Sample Book" in html                     # زیرِ نامِ فارسی روی جلد
    # ترتیب: متن، ترجمه، تصویر
    kinds = re.findall(
        r'class="page (cover|contents-page|text-page alt-page|text-page|'
        r'image-page|backcover)"', html)
    body = [k for k in kinds if k in ("text-page", "text-page alt-page",
                                      "image-page")]
    assert body[:3] == ["text-page", "text-page alt-page", "image-page"]
    # فهرست نباید ردیفِ اضافه برای ترجمه بسازد
    assert len(re.findall(r'<div class="row">', html)) == len(sections)
    # جلد + فهرست + ۲×(متن+ترجمه+تصویر) + پشت‌جلد
    assert layout["page_count"] == 9


def test_monolingual_book_has_no_alt_pages(tmp_path):
    sections = [{"paragraphs": ["متن."], "chapter_title": "بخش",
                 "chapter_kicker": "P", "caption": "ک", "image_path": None}]
    out = tmp_path / "book.html"
    render.render_book_html(
        lang="fa", title="کتاب", author="", blurb="", sections=sections,
        logo_uri="", github_url="", out_html_path=out)
    html = out.read_text(encoding="utf-8")
    assert 'class="page text-page alt-page"' not in html


def test_bilingual_layout_paginates_alt_with_its_own_width():
    # متنِ انگلیسی طولانی باید با عرضِ خطِ لاتین صفحه‌بندی شود، نه فارسی
    english = "This is a reasonably long English paragraph number %d."
    sections = [{
        "paragraphs": ["متن فارسی."],
        "alt_lang": "en",
        "alt_paragraphs": [(english % i) * 3 for i in range(30)],
        "chapter_title": "بخش", "chapter_kicker": "P", "caption": "ک",
        "image_path": None,
    }]
    pages = render._layout_pages(
        sections, line_cap=render.line_cap_for("fa", 0),
        chars_per_line=render.CHARS_PER_LINE["fa"])
    alt_pages = [p for p in pages if p.get("alt")]
    assert alt_pages and all(p["first"] is False for p in alt_pages)
    # صفحه‌ای که از کادر بیرون بزند نباید پیش بیاید
    assert pages[-1]["kind"] == "plate"
