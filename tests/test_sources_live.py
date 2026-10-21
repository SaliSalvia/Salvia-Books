# -*- coding: utf-8 -*-
"""
تست‌های زنده: به شبکه‌ی عمومی وصل می‌شوند و با `pytest -m live` اجرا شوند
(به‌طور پیش‌فرض در `pytest` رد می‌شوند).

این‌ها زنجیره‌ی منابع را با کتاب‌های واقعی می‌سنجند: گوتنبرگ، آرشیو
اینترنت/Open Library، جست‌جوی وب، و استخراج متنِ فارسی.
"""

import pytest
import requests

import text_source as ts

pytestmark = pytest.mark.live


def test_gutenberg_finds_pride_and_prejudice():
    text, meta = ts.find_public_domain_text(
        "Pride and Prejudice Jane Austen", preferred_lang="en",
        want_title="Pride and Prejudice", want_author="Jane Austen")
    assert text, "گوتنبرگ باید Pride and Prejudice را پیدا کند"
    assert len(text) > 50000
    assert "Elizabeth" in text[:80000]


def test_archive_finds_sherlock():
    text, meta = ts.find_archive_text(
        "The Adventures of Sherlock Holmes", "Arthur Conan Doyle", "en")
    assert text, "Open Library / Archive باید شرلوک هلمز را پیدا کند"
    assert len(text) > 50000
    assert "Holmes" in text[:80000]


def test_persian_web_extraction():
    resp = requests.get(
        "https://fa.wikipedia.org/wiki/شاهنامه", timeout=30,
        headers={"User-Agent": ts.BROWSER_UA})
    assert resp.status_code == 200
    text = ts._extract_text_from_html(resp.text)
    assert len(text) > 1500
    assert ts.looks_persian(text)
    assert ts.looks_like_book_text(text)


def test_web_search_finds_full_text():
    text, meta = ts.fetch_from_any_source(
        "The Time Machine H G Wells full text", "en", deadline_s=90)
    assert text, "جست‌جوی وب باید دست‌کم یک متنِ کامل پیدا کند"
    assert meta and meta.get("source") == "web_scrape"
    assert len(text) > 5000
