# -*- coding: utf-8 -*-
"""
text_source.py
---------------
مسئول پیدا کردن متن کتاب از هر منبعی (بدون محدودیت کپی‌رایت).
ابتدا از پوشه‌ی manuscripts، سپس گوتنبرگ (برای کتاب‌های عمومی)، و در نهایت
جستجوی آزاد در کل وب با اسکرپینگ استفاده می‌کند.
"""

import json
import re
import unicodedata
import urllib.parse
import time
import random
from pathlib import Path

import requests
from bs4 import BeautifulSoup  # نیاز به نصب: beautifulsoup4

GUTENDEX_API = "https://gutendex.com/books"


class ManualTextRequired(Exception):
    """وقتی هیچ متنی در هیچ منبعی پیدا نشود، این خطا بالا می‌رود."""
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
    """حذف مقدمه/موخره‌ی استاندارد Project Gutenberg (و کلی تمیزکاری اولیه)."""
    start_pat = re.compile(r"\*\*\*\s*START OF (THE|THIS) PROJECT GUTENBERG.*?\*\*\*", re.IGNORECASE | re.DOTALL)
    end_pat = re.compile(r"\*\*\*\s*END OF (THE|THIS) PROJECT GUTENBERG.*", re.IGNORECASE | re.DOTALL)
    m = start_pat.search(raw)
    if m:
        raw = raw[m.end():]
    m = end_pat.search(raw)
    if m:
        raw = raw[:m.start()]
    # حذف خطوط خالی اضافی
    return "\n".join(line for line in raw.splitlines() if line.strip() or True)


# ---------------------------------------------------------------------------
# مرحله‌ی ۳: جستجوی آزاد در کل وب (اسکرپینگ) — نسخه‌ی قدرتمند
# ---------------------------------------------------------------------------

def _extract_text_from_html(html: str) -> str:
    """
    استخراج متن اصلی از HTML با حذف المان‌های مزاحم (منو، فوتر، اسکریپت و ...)
    و اولویت با تگ‌های محتوایی مانند <main>, <article>, <div class="content">
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    # حذف المان‌های مزاحم
    for element in soup(['script', 'style', 'nav', 'header', 'footer', 'aside', 'form', 'noscript']):
        element.decompose()
    
    # اولویت با تگ‌های اصلی محتوا
    main_content = (soup.find('main') or soup.find('article') or 
                    soup.find('div', class_=re.compile(r'content|text|body|post|entry|chapter', re.I)) or 
                    soup.body or soup)
    
    # استخراج پاراگراف‌ها
    paragraphs = main_content.find_all('p')
    if not paragraphs:
        text = main_content.get_text(separator='\n', strip=True)
    else:
        text = '\n\n'.join(p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 20)
    
    # یکدست‌سازی فاصله‌ها
    text = re.sub(r'\n\s*\n', '\n\n', text)
    text = re.sub(r' +', ' ', text)
    return text.strip()


def fetch_from_any_source(query: str, target_lang: str = None) -> tuple:
    """
    با استفاده از موتورهای جستجو (DuckDuckGo و Google) و عبارت‌های کلیدی متنوع،
    لینک‌های حاوی متن کتاب را پیدا کرده و محتوای آن را دانلود می‌کند.
    از HTML، TXT و حتی PDF (در صورت نصب pypdf) متن استخراج می‌شود.
    خروجی: (متن_خام, دیکشنری_متا) یا (None, None)
    """
    headers = {
        "User-Agent": random.choice([
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        ])
    }

    # ساخت عبارت‌های جستجوی متنوع
    search_queries = [
        query,
        f'"{query}" book',
        f'"{query}" full text',
        f'"{query}" read online',
        f'"{query}" free ebook',
        f'"{query}" novel',
        f'"{query}" pdf',
    ]
    if target_lang == "fa":
        search_queries.extend([
            f'"{query}" متن کامل',
            f'"{query}" دانلود کتاب',
            f'site:ganjoor.net {query}',
            f'site:noorlib.ir {query}',
        ])

    # موتورهای جستجو
    search_engines = [
        "https://html.duckduckgo.com/html/?q={}",
        "https://www.google.com/search?q={}",
    ]

    visited_urls = set()

    for engine_template in search_engines:
        for q in search_queries:
            # تاخیر تصادفی برای جلوگیری از مسدود شدن
            time.sleep(random.uniform(1.0, 2.5))
            search_url = engine_template.format(urllib.parse.quote(q))
            try:
                resp = requests.get(search_url, headers=headers, timeout=20)
                if resp.status_code != 200:
                    continue
                soup = BeautifulSoup(resp.text, 'html.parser')
                links = soup.find_all('a', href=True)

                for link in links:
                    href = link['href']

                    # پردازش لینک‌های تغییرمسیر DuckDuckGo
                    if '//duckduckgo.com/l/' in href:
                        parsed = urllib.parse.urlparse(href)
                        params = urllib.parse.parse_qs(parsed.query)
                        if 'uddg' in params:
                            href = params['uddg'][0]
                        else:
                            continue

                    if not href.startswith(('http://', 'https://')):
                        continue
                    if any(domain in href for domain in ['google.com', 'duckduckgo.com', 'youtube.com']):
                        continue
                    if href in visited_urls:
                        continue

                    visited_urls.add(href)

                    try:
                        page_resp = requests.get(href, headers=headers, timeout=30)
                        if page_resp.status_code != 200:
                            continue

                        content_type = page_resp.headers.get('content-type', '').lower()
                        extracted_text = ""

                        if 'text/plain' in content_type:
                            extracted_text = page_resp.text
                        elif 'text/html' in content_type:
                            extracted_text = _extract_text_from_html(page_resp.text)
                        elif 'application/pdf' in content_type:
                            try:
                                import pypdf
                                from io import BytesIO
                                reader = pypdf.PdfReader(BytesIO(page_resp.content))
                                extracted_text = "\n".join(p.extract_text() or "" for p in reader.pages)
                            except ImportError:
                                pass  # pypdf نصب نیست

                        extracted_text = re.sub(r'\s+', ' ', extracted_text).strip()

                        if len(extracted_text) > 1500:
                            print(f"متن کتاب از آدرس زیر پیدا و استخراج شد: {href}")
                            return extracted_text, {"source": "web_scrape", "url": href}
                    except Exception:
                        continue
            except Exception:
                continue

    return None, None


# ---------------------------------------------------------------------------
# مرحله‌ی ۴: ترجمه‌ی تازه به فارسی (در صورت نیاز)
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
# نقطه‌ی ورود اصلی این ماژول (همان امضای قبلی)
# ---------------------------------------------------------------------------

def get_source_text(client, model_name: str, raw_title: str, target_lang: str, manuscripts_dir: Path):
    """
    target_lang: 'fa' یا 'en'
    اولویت با فایل دستی کاربر در manuscripts/ است؛ سپس گوتنبرگ؛ و در نهایت
    جستجوی آزاد در وب.
    """
    norm = normalize_title(client, model_name, raw_title)
    slug = slugify(norm.get("title_en") or raw_title)

    # ۱) فایل دستی کاربر
    for candidate in [
        manuscripts_dir / f"{slug}-{target_lang}.txt",
        manuscripts_dir / f"{slug}.txt",
    ]:
        if candidate.exists():
            print(f"استفاده از متن دستی: {candidate}")
            return candidate.read_text(encoding="utf-8"), norm, {"source": "manual", "path": str(candidate)}

    # ۲) جست‌وجوی گوتنبرگ (آثار عمومی)
    gutenberg_lang = "fa" if target_lang == "fa" else "en"
    raw_text, meta = find_public_domain_text(norm["gutenberg_query"], preferred_lang=gutenberg_lang)

    if raw_text is not None:
        text = clean_gutenberg_text(raw_text)
        meta["source"] = "gutenberg"
        # ۳) ترجمه در صورت نیاز
        if target_lang == "fa" and gutenberg_lang != "fa":
            print("متن انگلیسیِ آزاد پیدا شد؛ در حال تولید ترجمه‌ی تازه‌ی فارسی با Gemini ...")
            text = translate_to_persian(client, model_name, text)
            meta["translated"] = True
        return text, norm, meta

    # ۴) جستجوی آزاد در کل وب (اگر گوتنبرگ نداد)
    print("گوتنبرگ نتیجه‌ای نداشت؛ در حال جستجوی وب برای یافتن متن کتاب ...")
    raw_text, meta = fetch_from_any_source(norm["gutenberg_query"], target_lang)

    if raw_text is None:
        # اگر هیچ‌چیز پیدا نشد، خطا بده (اما نه به‌خاطر کپی‌رایت)
        raise ManualTextRequired(
            f"هیچ متنی برای «{raw_title}» در هیچ منبعی (گوتنبرگ یا وب) پیدا نشد.\n"
            f"می‌توانی خودت فایل متن را در این مسیر قرار دهی:\n"
            f"  manuscripts/{slug}-{target_lang}.txt\n"
            f"و دوباره اجرا کن."
        )

    text = clean_gutenberg_text(raw_text)  # پاک‌سازی اولیه
    meta["source"] = "web_scrape"

    # ۵) اگر متن به زبان فارسی نبود و زبان هدف فارسی است، ترجمه کن
    if target_lang == "fa":
        # تشخیص ساده: اگر کاراکتر فارسی در ۲۰۰ کاراکتر اول نبود، احتمالاً انگلیسی است
        if not any('\u0600' <= c <= '\u06FF' for c in text[:200]):
            print("متن انگلیسی از وب پیدا شد؛ در حال تولید ترجمه‌ی فارسی با Gemini ...")
            text = translate_to_persian(client, model_name, text)
            meta["translated"] = True

    return text, norm, meta
