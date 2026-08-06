# -*- coding: utf-8 -*-
"""
text_source.py
---------------
مسئول پیدا کردن متن قانونیِ کتاب (فقط از منابع Public Domain مثل Project
Gutenberg) و در صورت نیاز، ترجمه‌ی تازه‌ی آن با Gemini.

این ماژول عمداً هرگز از مدل نمی‌خواهد متن کامل یک کتاب کپی‌رایت‌دار را از
حافظه بازتولید کند و هرگز از سایت‌های غیرقانونی/دانلود غیرمجاز استفاده
نمی‌کند. اگر متن آزاد پیدا نشود، پردازش متوقف می‌شود و از کاربر می‌خواهد
خودش فایل متن را در پوشه‌ی manuscripts/ قرار دهد.
"""

import json
import re
import unicodedata
from pathlib import Path

import requests

GUTENDEX_API = "https://gutendex.com/books"


class ManualTextRequired(Exception):
    """وقتی متنِ آزاد و قانونی پیدا نشود، این خطا بالا می‌رود."""
    pass


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip().lower()
    text = re.sub(r"[\s_]+", "-", text)
    return text or "book"


# ---------------------------------------------------------------------------
# مرحله‌ی ۱: شناخت عنوان (هر زبانی که کاربر وارد کرده) با Gemini
# ---------------------------------------------------------------------------

TITLE_NORMALIZE_PROMPT = """
تو یک کتاب‌شناس هستی. ورودی زیر نام یک کتاب است (ممکن است فارسی، انگلیسی یا
هر زبان دیگری باشد، و ممکن است محاوره‌ای یا ناقص نوشته شده باشد).

فقط یک JSON خام با این ساختار برگردان (بدون توضیح اضافه):
{
  "title_en": "عنوان رسمی انگلیسی کتاب",
  "title_fa": "عنوان رایج فارسی کتاب (ترجمه‌ی مصطلح، نه لزوماً ترجمه‌ی لغوی)",
  "author": "نام نویسنده به انگلیسی",
  "gutenberg_query": "بهترین عبارت جست‌وجو برای پیدا کردن این کتاب در Project Gutenberg (عنوان + نویسنده، به انگلیسی)"
}

نام کتاب: "{raw_title}"
"""


def normalize_title(client, model_name: str, raw_title: str) -> dict:
    prompt = TITLE_NORMALIZE_PROMPT.replace("{raw_title}", raw_title)
    resp = client.models.generate_content(model=model_name, contents=prompt)
    raw = re.sub(r"^```(json)?|```$", "", resp.text.strip(), flags=re.MULTILINE).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {
            "title_en": raw_title,
            "title_fa": raw_title,
            "author": "",
            "gutenberg_query": raw_title,
        }
    return data


# ---------------------------------------------------------------------------
# مرحله‌ی ۲: جست‌وجو در Project Gutenberg (فقط آثار Public Domain)
# ---------------------------------------------------------------------------

def gutendex_search(query: str, language: str = None):
    params = {"search": query}
    if language:
        params["languages"] = language
    r = requests.get(GUTENDEX_API, params=params, timeout=30)
    r.raise_for_status()
    results = r.json().get("results", [])
    return results


def _pick_txt_url(book: dict):
    formats = book.get("formats", {})
    for key, url in formats.items():
        if key.startswith("text/plain"):
            return url
    return None


def find_public_domain_text(gutenberg_query: str, preferred_lang: str = None):
    """
    اول با زبان ترجیحی جست‌وجو می‌کند؛ اگر نبود، بدون فیلتر زبان دوباره
    امتحان می‌کند (معمولاً متن انگلیسی/اصلی پیدا می‌شود).
    خروجی: (raw_text, meta_dict) یا (None, None)
    """
    for lang in filter(None, [preferred_lang, None]):
        try:
            results = gutendex_search(gutenberg_query, lang)
        except requests.RequestException:
            results = []
        for book in results:
            url = _pick_txt_url(book)
            if not url:
                continue
            try:
                resp = requests.get(url, timeout=60)
                resp.raise_for_status()
            except requests.RequestException:
                continue
            return resp.text, {
                "title": book.get("title"),
                "authors": [a.get("name") for a in book.get("authors", [])],
                "gutenberg_id": book.get("id"),
                "source_url": url,
            }
    return None, None


def clean_gutenberg_text(raw: str) -> str:
    """حذف مقدمه/موخره‌ی استاندارد Project Gutenberg."""
    start_pat = re.compile(r"\*\*\*\s*START OF (THE|THIS) PROJECT GUTENBERG.*?\*\*\*", re.IGNORECASE | re.DOTALL)
    end_pat = re.compile(r"\*\*\*\s*END OF (THE|THIS) PROJECT GUTENBERG.*", re.IGNORECASE | re.DOTALL)
    m = start_pat.search(raw)
    if m:
        raw = raw[m.end():]
    m = end_pat.search(raw)
    if m:
        raw = raw[:m.start()]
    return raw.strip()


# ---------------------------------------------------------------------------
# مرحله‌ی ۳: ترجمه‌ی تازه به فارسی (در صورت نیاز) — یک ترجمه‌ی جدید و
# اختصاصی تولید می‌شود، نه بازتولید ترجمه‌ی موجود کسی دیگر.
# ---------------------------------------------------------------------------

TRANSLATE_PROMPT = """
متن زیر بخشی از یک کتاب ادبی به زبان انگلیسی است. آن را به فارسیِ روان،
ادبی و طبیعی ترجمه کن. فقط ترجمه را برگردان، بدون توضیح اضافه، بدون
شماره‌گذاری، و ساختار پاراگراف‌بندی را حفظ کن.

متن:
---
{chunk}
---
"""


def translate_to_persian(client, model_name: str, text: str, chunk_chars: int = 4000) -> str:
    paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, buf, buf_len = [], [], 0
    for p in paragraphs:
        buf.append(p)
        buf_len += len(p)
        if buf_len >= chunk_chars:
            chunks.append("\n\n".join(buf))
            buf, buf_len = [], 0
    if buf:
        chunks.append("\n\n".join(buf))

    translated_parts = []
    for i, chunk in enumerate(chunks, 1):
        prompt = TRANSLATE_PROMPT.replace("{chunk}", chunk)
        resp = client.models.generate_content(model=model_name, contents=prompt)
        translated_parts.append(resp.text.strip())
        print(f"  ترجمه بخش {i}/{len(chunks)} انجام شد")
    return "\n\n".join(translated_parts)


# ---------------------------------------------------------------------------
# نقطه‌ی ورود اصلی این ماژول
# ---------------------------------------------------------------------------

def get_source_text(client, model_name: str, raw_title: str, target_lang: str, manuscripts_dir: Path):
    """
    target_lang: 'fa' یا 'en'
    اولویت با فایل دستی کاربر در manuscripts/ است؛ سپس Project Gutenberg.
    """
    norm = normalize_title(client, model_name, raw_title)
    slug = slugify(norm.get("title_en") or raw_title)

    # ۱) آیا کاربر خودش متنی گذاشته؟
    for candidate in [
        manuscripts_dir / f"{slug}-{target_lang}.txt",
        manuscripts_dir / f"{slug}.txt",
    ]:
        if candidate.exists():
            print(f"استفاده از متن دستی: {candidate}")
            return candidate.read_text(encoding="utf-8"), norm, {"source": "manual", "path": str(candidate)}

    # ۲) جست‌وجوی Project Gutenberg (فقط آثار آزاد)
    gutenberg_lang = "fa" if target_lang == "fa" else "en"
    raw_text, meta = find_public_domain_text(norm["gutenberg_query"], preferred_lang=gutenberg_lang)

    if raw_text is None:
        raise ManualTextRequired(
            f"متن آزاد و قانونی (Public Domain) برای «{raw_title}» در Project Gutenberg پیدا نشد.\n"
            f"این کتاب احتمالاً هنوز کپی‌رایت دارد، پس این ابزار عمداً آن را دانلود نمی‌کند.\n"
            f"برای ادامه، متن خودتان را (که حق استفاده از آن را دارید) در این مسیر قرار دهید:\n"
            f"  manuscripts/{slug}-{target_lang}.txt\n"
            f"و دوباره اکشن را اجرا کنید."
        )

    text = clean_gutenberg_text(raw_text)
    meta["source"] = "gutenberg"

    # ۳) اگر زبان متن پیداشده با زبان هدف یکی نیست، ترجمه‌ی تازه انجام بده
    if target_lang == "fa" and gutenberg_lang != "fa":
        print("متن انگلیسیِ آزاد پیدا شد؛ در حال تولید ترجمه‌ی تازه‌ی فارسی با Gemini ...")
        text = translate_to_persian(client, model_name, text)
        meta["translated"] = True

    return text, norm, meta
