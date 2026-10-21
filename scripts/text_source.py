# -*- coding: utf-8 -*-
"""
text_source.py
---------------
مسئول پیدا کردن متن کتاب از هر منبعی. زنجیره‌ی منابع (به ترتیب اولویت):

  ۱) فایل دستی کاربر در manuscripts/
  ۲) Project Gutenberg (gutendex) — کتاب‌های public domain
  ۳) Open Library + Internet Archive — متن کامل میلیون‌ها کتاب (بدون کلید)
  ۴) جست‌جوی آزاد در وب با اسکرپینگ — آخرین راه‌حل، که همیشه با «اعتبارسنجی
     هوشمند» بررسی می‌شود تا متنِ واقعاً همان کتاب باشد، نه فهرست سایت یا
     نقد یا صفحه‌ی تبلیغاتی.

هر متنِ غیرفارسی وقتی زبان هدف فارسی است، به‌صورت بخش‌به‌بخش با Gemini
ترجمه می‌شود. همه‌ی فراخوانی‌های مدل از طریق llm.py انجام می‌شوند تا در برابر
خطاهای موقت (429/5xx) و مدل‌های ناموجود مقاوم بمانند.
"""

import base64
import ipaddress
import json
import random
import re
import time
import unicodedata
import urllib.parse
from pathlib import Path

import requests
from bs4 import BeautifulSoup  # نیاز به نصب: beautifulsoup4

import llm

GUTENDEX_API = "https://gutendex.com/books"
OPENLIBRARY_API = "https://openlibrary.org/search.json"

# نشانی‌های داخلی/خصوصی را اسکرپ نکن (گارد ساده در برابر SSRF)
_PRIVATE_HOST_SUFFIXES = (".local", ".internal", ".lan", ".localhost", ".home", ".corp")
_BLOCKED_DOMAINS = (
    "google.com", "googleusercontent.com", "duckduckgo.com", "mojeek.com",
    "bing.com", "startpage.com", "marginalia.nu", "ecosia.org",
    "youtube.com", "youtu.be", "facebook.com", "twitter.com", "x.com",
    "instagram.com", "pinterest.", "linkedin.com", "tiktok.com", "reddit.com",
    "amazon.", "spotify.com", "netflix.com",
)
_BAD_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico", ".bmp",
    ".mp3", ".mp4", ".webm", ".avi", ".mov",
    ".zip", ".rar", ".7z", ".gz", ".exe", ".dmg", ".apk", ".deb",
    ".css", ".js", ".woff", ".woff2", ".ttf", ".otf", ".eot",
)

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
API_HEADERS = {"User-Agent": f"{BROWSER_UA} SalviaBooks/1.0"}
SEARCH_HEADERS = {"User-Agent": BROWSER_UA, "Accept-Language": "*"}

SESSION = requests.Session()
SESSION.headers.update(API_HEADERS)

# حداکثرِ زمانِ کلِ مرحله‌ی «جستجوی وب» تا اجرای CI ساعت‌ها گیر نکند
WEB_SEARCH_DEADLINE_S = 180


class ManualTextRequired(Exception):
    """وقتی هیچ متنی در هیچ منبعی پیدا نشود، این خطا بالا می‌رود."""
    pass


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip().lower()
    text = re.sub(r"[\s_]+", "-", text)
    return text or "book"


# ---------------------------------------------------------------------------
# پرامپت‌ها — همه‌ی پرامپت‌ها با «جایگزینی نشانه‌ای» ساخته می‌شوند تا متنِ
# کتاب (که ممکن است آکولاد یا قالب داشته باشد) هرگز پرامپت را نشکند.
# ---------------------------------------------------------------------------

TITLE_NORMALIZE_PROMPT = """
تو یک کتاب‌شناس هستی. ورودی زیر نام یک کتاب است (ممکن است فارسی، انگلیسی یا
هر زبان دیگری باشد، و ممکن است محاوره‌ای یا ناقص نوشته شده باشد).

فقط یک JSON خام با این ساختار برگردان (بدون توضیح اضافه):
{
  "title_en": "عنوان رسمی انگلیسی کتاب",
  "title_fa": "عنوان رایج فارسی کتاب (ترجمه‌ی مصطلح، نه لزوماً ترجمه‌ی لغوی)",
  "author": "نام نویسنده به انگلیسی",
  "gutenberg_query": "بهترین عبارت جست‌وجو برای پیدا کردن این کتاب در منابع رایگان (عنوان + نویسنده، به انگلیسی)"
}

نام کتاب: "<<RAW_TITLE>>"
"""

VALIDATE_PROMPT = """
تو یک داور دقیق هستی. نمونه‌ای از متنِ یک منبع را می‌بینی و باید بگویی آیا
این واقعاً «متن خودِ کتاب» است یا چیز دیگری (فهرست/منوی سایت، نقد یا معرفی
کتاب، تبلیغات، صفحه‌ی دانلود، خلاصه‌ی چند خطی، متن کتابِ دیگری، و ...).

عنوان کتاب: <<TITLE>>
نویسنده: <<AUTHOR>>
نمونه‌ی متن:
---
<<SAMPLE>>
---

فقط یک JSON خام برگردان:
{"verdict": "yes" یا "no" یا "uncertain", "reason": "توضیح کوتاه"}

راهنمای verdict:
- "yes": نمونه به‌وضوح بخشی از همان کتاب است (ادامه‌ی روایت/مقاله با همان حال‌وهوای اثر).
- "no": نمونه به‌وضوح چیز دیگری است (منو، نقد، تبلیغ، فهرست مطالب سایت، ...).
- "uncertain": ابهام هست ولی چیز خلافی دیده نمی‌شود.
"""

TRANSLATE_PROMPT = """
متن زیر بخشی از یک کتاب ادبی است. آن را به فارسیِ روان، ادبی و طبیعی ترجمه کن.
فقط ترجمه را برگردان، بدون توضیح اضافه، بدون شماره‌گذاری، و ساختار
پاراگراف‌بندی را حفظ کن.

متن:
---
<<CHUNK>>
---
"""


def _fill(prompt: str, **values) -> str:
    """جایگزینی نشانه‌های <<KEY>> بدون هیچ خطر شکستن قالب."""
    for key, value in values.items():
        prompt = prompt.replace(f"<<{key.upper()}>>", str(value))
    return prompt


# ---------------------------------------------------------------------------
# مرحله‌ی ۱: شناخت عنوان (هر زبانی که کاربر وارد کرده) با Gemini
# ---------------------------------------------------------------------------

def normalize_title(client, models, raw_title: str) -> dict:
    prompt = _fill(TITLE_NORMALIZE_PROMPT, raw_title=raw_title)
    data = llm.generate_json(client, models, prompt)
    if not isinstance(data, dict):
        data = {}
    out = {
        "title_en": str(data.get("title_en") or raw_title),
        "title_fa": str(data.get("title_fa") or raw_title),
        "author": str(data.get("author") or ""),
        "gutenberg_query": str(data.get("gutenberg_query") or raw_title),
    }
    return out


# ---------------------------------------------------------------------------
# تشخیص زبان با نسبت‌گیری روی نمونه‌ی بلند (نه ۲۰۰ کاراکتر اول!)
# ---------------------------------------------------------------------------

def guess_lang(text: str) -> str:
    """زبانِ ورودی/متن را حدس می‌زند: 'fa' اگر حروف فارسی-عربی داشته باشد."""
    sample = (text or "")[:6000]
    for ch in sample:
        o = ord(ch)
        if 0x0600 <= o <= 0x06FF or 0xFB50 <= o <= 0xFDFF or 0xFE70 <= o <= 0xFEFF:
            return "fa"
    return "en"


def looks_persian(text: str) -> bool:
    """آیا متن عملاً فارسی است؟ با نسبت حروف فارسی به کل حروف، روی ۶۰۰۰
    کاراکتر اول — تا پیش‌گفتار لاتین یا پانویس انگلیسی تصمیم را خراب نکند."""
    sample = (text or "")[:6000]
    fa = latin = 0
    for ch in sample:
        o = ord(ch)
        if 0x0600 <= o <= 0x06FF or 0xFB50 <= o <= 0xFDFF or 0xFE70 <= o <= 0xFEFF:
            fa += 1
        elif ch.isalpha() and (o < 0x0400):
            latin += 1
    total = fa + latin
    if total == 0:
        return False
    return fa / total >= 0.25


# ---------------------------------------------------------------------------
# مرحله‌ی ۲: Project Gutenberg (آثار public domain)
# ---------------------------------------------------------------------------

def gutendex_search(query: str, language: str = None, retries: int = 3):
    params = {"search": query}
    if language:
        params["languages"] = language
    # gutendex گاهی کند/ناپایدار است؛ چند تلاش کوتاه قبل از تسلیم‌شدن.
    for attempt in range(retries):
        try:
            r = SESSION.get(GUTENDEX_API, params=params, timeout=30)
            r.raise_for_status()
            return r.json().get("results", [])
        except (requests.RequestException, ValueError):
            if attempt < retries - 1:
                time.sleep(1.0 + attempt)
    return []


def gutenberg_html_search(query: str, limit: int = 8):
    """جست‌وجوی HTML خودِ gutenberg.org — پشتیبان وقتی gutendex در دسترس نیست.

    خروجی با شکل نتایج gutendex تا همان کد امتیازدهی روی آن کار کند:
    [{id, title, authors: [{name}], languages, _html_fallback}]
    """
    url = ("https://www.gutenberg.org/ebooks/search/?query="
           + urllib.parse.quote(query))
    try:
        resp = SESSION.get(url, headers=SEARCH_HEADERS, timeout=30)
        if resp.status_code != 200:
            return []
    except requests.RequestException:
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    out, seen = [], set()
    for anchor in soup.find_all("a", href=True):
        m = re.search(r"/ebooks/(\d+)", anchor.get("href", ""))
        if not m or m.group(1) in seen:
            continue
        seen.add(m.group(1))
        title_el = anchor.find("span", class_="title")
        author_el = anchor.find("span", class_="author")
        title = title_el.get_text(" ", strip=True) if title_el else ""
        author = author_el.get_text(" ", strip=True) if author_el else ""
        author = re.sub(r"^by\s+", "", author, flags=re.IGNORECASE)
        out.append({
            "id": int(m.group(1)),
            "title": title,
            "authors": [{"name": author}] if author else [],
            "languages": [],
            "_html_fallback": True,
        })
        if len(out) >= limit:
            break
    return out


def _pick_txt_url(book: dict):
    for key, url in (book.get("formats") or {}).items():
        if str(key).startswith("text/plain"):
            return url
    return None


def _norm_words(text: str):
    text = (text or "").lower()
    text = re.sub(r"[\"'’“”«»:,.!?;()\[\]{}\-–—]+", " ", text)
    text = re.sub(r"^\W+|\W+$", "", text)
    return [w for w in text.split() if w and w not in ("the", "a", "an", "of")]


def _jaccard(a_words, b_words) -> float:
    a, b = set(a_words), set(b_words)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _author_matches(authors, want_author: str) -> bool:
    if not want_author:
        return False
    want = set(_norm_words(want_author))
    last_names = {w for w in want}
    for name in authors or []:
        have = set(_norm_words(name))
        if have and (have & last_names):
            return True
    return False


def _book_score(book: dict, want_title: str, want_author: str, prefer_lang=None) -> float:
    score = _jaccard(_norm_words(want_title), _norm_words(book.get("title") or ""))
    if _author_matches([a.get("name") for a in book.get("authors") or []], want_author):
        score += 1.5
    if prefer_lang and prefer_lang in (book.get("languages") or []):
        score += 0.5
    return score


def _gutenberg_txt_urls(ebook_id) -> list:
    """نشانی‌های متنِ خامِ یک شماره‌ی گوتنبرگ (ساختارهای رسمی و پایدار)."""
    eid = str(ebook_id or "").strip()
    if not eid.isdigit():
        return []
    return [
        f"https://www.gutenberg.org/cache/epub/{eid}/pg{eid}.txt",
        f"https://www.gutenberg.org/files/{eid}/{eid}-0.txt",
        f"https://www.gutenberg.org/files/{eid}/{eid}.txt",
    ]


def _download_book_text(book: dict):
    """دانلود اولین نشانیِ متنِ در دسترسِ یک کتاب. خروجی: (متن, url) یا (None, None)."""
    if book.get("_html_fallback"):
        urls = _gutenberg_txt_urls(book.get("id"))
    else:
        picked = _pick_txt_url(book)
        urls = [picked] if picked else []
    for url in urls:
        try:
            resp = SESSION.get(url, timeout=60)
            if resp.status_code != 200:
                continue
            if "charset" not in resp.headers.get("content-type", "").lower():
                resp.encoding = resp.apparent_encoding or "utf-8"
            return resp.text, url
        except requests.RequestException:
            continue
    return None, None


def find_public_domain_text(query, preferred_lang=None, *, want_title=None,
                            want_author=None, validate=None, max_candidates=3):
    """
    جست‌وجو در gutendex با امتیازدهی (عنوان/نویسنده/زبان) و اعتبارسنجی
    اختیاری روی هر کاندیدایی که دانلود می‌شود. اگر gutendex در دسترس نباشد
    یا نتیجه‌ای ندهد، جست‌وجوی HTML خودِ gutenberg.org امتحان می‌شود.
    خروجی: (متن، متا) یا (None, None).
    """
    want_title = want_title or query
    results = gutendex_search(query, preferred_lang)
    if not results and preferred_lang:
        results = gutendex_search(query, None)  # بدون فیلتر زبان دوباره

    def rank(items):
        ordered = sorted(
            items,
            key=lambda b: _book_score(b, want_title, want_author, preferred_lang),
            reverse=True,
        )
        strong = [b for b in ordered
                  if _jaccard(_norm_words(want_title),
                              _norm_words(b.get("title") or "")) >= 0.3]
        return strong or ordered[:3]

    pool = rank(results) if results else []
    if not pool:
        # gutendex قطع یا کند بود → جست‌وجوی مستقیم خودِ گوتنبرگ
        pool = rank(gutenberg_html_search(query))

    tried = 0
    for book in pool:
        if tried >= max_candidates:
            break
        text, url = _download_book_text(book)
        if text is None:
            continue
        tried += 1
        if not looks_like_book_text(text, min_chars=800, min_words=120):
            continue
        if validate is not None and not validate(text):
            continue
        return text, {
            "title": book.get("title"),
            "authors": [a.get("name") for a in book.get("authors") or []],
            "gutenberg_id": book.get("id"),
            "source_url": url,
            "language": (book.get("languages") or [None])[0],
        }
    return None, None


def normalize_text(raw: str) -> str:
    """
    یکدست‌سازی متنِ خام: شکستن صفحه، فاصله‌های اضافه، حذف کنترل‌ها و
    تمیزکاریِ نشانه‌های مارک‌داون (متن‌های وب و فایل‌های دستی اغلب مارک‌داون‌اند).
    """
    raw = raw.replace("\x0c", "\n\n")
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    raw = re.sub(r"[\x00-\x08\x0b\x0e-\x1f]", "", raw)

    # لینک‌های مارک‌داون → متنِ خودِ لینک
    raw = re.sub(r"\[([^\]\n]{1,200})\]\([^)\n]{0,500}\)", r"\1", raw)
    # عنوان‌های #/##/### و نقل‌قول‌های > در ابتدای خط
    raw = re.sub(r"^\s{0,3}#{1,6}\s*", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"^\s{0,3}>\s?", "", raw, flags=re.MULTILINE)
    # خط‌های جداکننده‌ی افقی (---، ***، ___) به‌تنهایی
    raw = re.sub(r"^\s*([-*_]\s*){3,}$", "", raw, flags=re.MULTILINE)
    # تأکیدهای **پررهنگ** و *مورب* و `کد` (نشانه‌ها حذف، متن می‌ماند)
    raw = re.sub(r"\*\*([^*\n]{1,300})\*\*", r"\1", raw)
    raw = re.sub(r"(?<!\w)[*_]([^*_\n]{1,300})[*_](?!\w)", r"\1", raw)
    raw = re.sub(r"`([^`\n]{1,300})`", r"\1", raw)
    # بولت‌های ابتدای خط
    raw = re.sub(r"^\s*[-*•]\s+", "", raw, flags=re.MULTILINE)

    raw = re.sub(r"[ \t]+", " ", raw)
    raw = re.sub(r"\n[ \t]+", "\n", raw)
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    return raw.strip()


def clean_gutenberg_text(raw: str) -> str:
    """حذف مقدمه/موخره‌ی استاندارد Project Gutenberg + یکدست‌سازی."""
    start_pat = re.compile(
        r"\*\*\*\s*START OF (THE|THIS) PROJECT GUTENBERG.*?\*\*\*",
        re.IGNORECASE | re.DOTALL,
    )
    end_pat = re.compile(
        r"\*\*\*\s*END OF (THE|THIS) PROJECT GUTENBERG.*",
        re.IGNORECASE | re.DOTALL,
    )
    m = start_pat.search(raw)
    if m:
        raw = raw[m.end():]
    m = end_pat.search(raw)
    if m:
        raw = raw[:m.start()]
    return normalize_text(raw)


# ---------------------------------------------------------------------------
# مرحله‌ی ۳: Open Library + Internet Archive (متن کامل، بدون کلید)
# ---------------------------------------------------------------------------

def find_archive_text(want_title, want_author=None, preferred_lang=None,
                      validate=None, max_candidates=4):
    """
    جست‌جوی عنوان در Open Library، سپس دانلود متن OCRشده‌ی همان نسخه از
    Internet Archive (فایل {ia_id}_djvu.txt). خروجی: (متن، متا) یا (None, None).
    """
    query = " ".join(x for x in (want_title, want_author) if x).strip()
    try:
        r = SESSION.get(
            OPENLIBRARY_API,
            params={
                "q": query,
                "limit": 15,
                "fields": "title,author_name,ia,language,first_publish_year",
            },
            timeout=30,
        )
        r.raise_for_status()
        docs = r.json().get("docs", [])
    except (requests.RequestException, ValueError):
        return None, None

    def doc_score(doc):
        s = _jaccard(_norm_words(want_title), _norm_words(doc.get("title") or ""))
        if _author_matches(doc.get("author_name") or [], want_author or ""):
            s += 1.5
        if preferred_lang and preferred_lang in (doc.get("language") or []):
            s += 0.5
        return s

    ranked = sorted(docs, key=doc_score, reverse=True)
    strong = [d for d in ranked if doc_score(d) >= 0.3 and d.get("ia")]
    pool = strong or [d for d in ranked if d.get("ia")][:3]

    tried = 0
    for doc in pool:
        for ia_id in (doc.get("ia") or [])[:3]:
            if tried >= max_candidates:
                return None, None
            url = (f"https://archive.org/download/"
                   f"{urllib.parse.quote(ia_id)}/{urllib.parse.quote(ia_id)}_djvu.txt")
            try:
                resp = SESSION.get(url, timeout=60)
                if resp.status_code != 200:
                    continue
                if "charset" not in resp.headers.get("content-type", "").lower():
                    resp.encoding = resp.apparent_encoding or "utf-8"
                text = resp.text
            except requests.RequestException:
                continue
            tried += 1
            text = normalize_text(text)
            if not looks_like_book_text(text, min_chars=800, min_words=120):
                continue
            if validate is not None and not validate(text):
                continue
            return text, {
                "title": doc.get("title"),
                "authors": doc.get("author_name") or [],
                "ia_id": ia_id,
                "source_url": url,
                "language": (doc.get("language") or [None])[0],
            }
    return None, None


# ---------------------------------------------------------------------------
# مرحله‌ی ۴: اعتبارسنجی هوشمند (آیا این واقعاً همان کتاب است؟)
# ---------------------------------------------------------------------------

def validate_candidate_text(client, models, title, author, text) -> (bool, str):
    """داوریِ LLM روی نمونه‌ی ابتدای متن. فقط «no» رد می‌کند (رویکرد مدارا)."""
    sample = (text or "")[:3000]
    prompt = _fill(VALIDATE_PROMPT, title=title or "-", author=author or "-",
                   sample=sample)
    try:
        data = llm.generate_json(client, models, prompt, max_attempts=3,
                                 budget_s=90.0)
    except Exception as exc:
        # اگر خودِ داور در دسترس نبود، متن را رد نکن؛ زنجیره‌ی منابع ادامه می‌یابد.
        return True, f"داوری در دسترس نبود ({type(exc).__name__})؛ پذیرش مشروط"
    if not isinstance(data, dict):
        return True, "خروجی داوری نامفهوم بود؛ پذیرش مشروط"
    verdict = str(data.get("verdict") or "").strip().lower()
    reason = str(data.get("reason") or "").strip()
    if verdict == "no":
        return False, reason or "متن، همان کتاب نیست"
    if verdict in ("yes", "uncertain"):
        return True, reason or "پذیرفته شد"
    # verdict ناشناخته: مدارا
    return True, f"verdict ناشناخته ({verdict})؛ پذیرش مشروط"


# ---------------------------------------------------------------------------
# مرحله‌ی ۵: جست‌جوی آزاد در کل وب (اسکرپینگ) با بودجه‌ی زمانی
# ---------------------------------------------------------------------------

def _extract_text_from_html(html: str) -> str:
    """استخراج متن اصلی با حذف المان‌های مزاحم و اولویت با تگ‌های محتوایی."""
    soup = BeautifulSoup(html, "html.parser")
    for element in soup(["script", "style", "nav", "header", "footer", "aside",
                         "form", "noscript", "iframe", "button"]):
        element.decompose()

    main_content = (
        soup.find("main")
        or soup.find("article")
        or soup.find(id=re.compile(r"content|text|main|body|post|entry", re.I))
        or soup.find("div", class_=re.compile(
            r"content|text|body|post|entry|chapter|book", re.I))
        or soup.body
        or soup
    )
    paragraphs = main_content.find_all("p")
    if not paragraphs:
        text = main_content.get_text(separator="\n", strip=True)
    else:
        text = "\n\n".join(
            p.get_text(strip=True) for p in paragraphs
            if len(p.get_text(strip=True)) > 20
        )
    return normalize_text(re.sub(r"\n\s*\n", "\n\n", text))


def looks_like_book_text(text: str, min_chars: int = 1500,
                          min_words: int = 250) -> bool:
    """فیلتر رایگان و بدون مدل: متنِ کتاب باید بلند و جمله‌محور باشد، نه منو.

    حدِ پیش‌فرض برای کاندیداهای وب است (۱۵۰۰ نویسه)؛ منابع ساختارمند
    (گوتنبرگ/آرشیو) با حد پایین‌تر صدا زده می‌شوند چون کتاب‌های کوتاه هم
    معتبرند.
    """
    if not text or len(text) < min_chars:
        return False
    words = text.split()
    if len(words) < min_words:
        return False
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return False
    avg_line = sum(len(line) for line in lines) / len(lines)
    return avg_line >= 40


def _is_fetchable_url(url: str) -> bool:
    try:
        parts = urllib.parse.urlparse(url)
    except ValueError:
        return False
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return False
    host = parts.hostname.lower()
    if host == "localhost" or host.endswith(_PRIVATE_HOST_SUFFIXES):
        return False
    try:
        if not ipaddress.ip_address(host).is_global:
            return False
    except ValueError:
        pass  # نام دامنه است
    low = url.lower()
    if any(low.split("?")[0].endswith(ext) for ext in _BAD_EXTENSIONS):
        return False
    if any(domain in host for domain in _BLOCKED_DOMAINS):
        return False
    return True


def _unwrap_result_url(engine: str, href: str) -> str:
    """بازکردن ریدایرکت‌های موتورهای جستجو (DDG، /url?q= گوگل، ck/a بینگ)."""
    if not href:
        return ""
    if "uddg=" in href:
        parsed = urllib.parse.urlparse(href)
        params = urllib.parse.parse_qs(parsed.query)
        if "uddg" in params:
            return params["uddg"][0]
        return ""
    if engine == "google":
        if href.startswith("/url?") or "google.com/url?" in href:
            parsed = urllib.parse.urlparse(href)
            params = urllib.parse.parse_qs(parsed.query)
            for key in ("q", "url"):
                if params.get(key):
                    return params[key][0]
        return ""
    if href.startswith("/ck/a") or "bing.com/ck/a" in href:
        # بینگ: نتایج داخل redirect با رمز base64-url هستند: u=a1<target>
        if href.startswith("/"):
            href = "https://www.bing.com" + href
        parsed = urllib.parse.urlparse(href)
        params = urllib.parse.parse_qs(parsed.query)
        u = (params.get("u") or [""])[0]
        if not u.startswith("a1"):
            return ""
        payload = u[2:]
        payload += "=" * (-len(payload) % 4)
        try:
            target = base64.urlsafe_b64decode(payload).decode("utf-8", "ignore")
        except (ValueError, TypeError):
            return ""
        return target if target.startswith(("http://", "https://")) else ""
    if href.startswith("//"):
        href = "https:" + href
    if href.startswith("/"):
        return ""  # لینک داخلیِ همان موتور جستجو
    return href


def iter_result_urls(engine: str, html: str, limit: int = 40):
    """لینک‌های نتیجه‌ی یک صفحه‌ی جستجو، به ترتیب، بدون تکرار."""
    soup = BeautifulSoup(html, "html.parser")
    urls, seen = [], set()
    for anchor in soup.find_all("a", href=True):
        url = _unwrap_result_url(engine, anchor["href"].strip())
        if not url or url in seen:
            continue
        if not _is_fetchable_url(url):
            continue
        seen.add(url)
        urls.append(url)
        if len(urls) >= limit:
            break
    return urls


def _download_and_extract(url: str):
    """دانلود یک صفحه/متن و استخراج متنِ خام از آن (یا None)."""
    try:
        resp = SESSION.get(url, headers=SEARCH_HEADERS, timeout=(10, 30),
                           allow_redirects=True)
    except requests.RequestException:
        return None
    if resp.status_code != 200:
        return None
    content_type = resp.headers.get("content-type", "").lower()
    try:
        if "pdf" in content_type:
            try:
                import pypdf
                from io import BytesIO
                reader = pypdf.PdfReader(BytesIO(resp.content))
                text = "\n".join(page.extract_text() or "" for page in reader.pages)
            except Exception:
                return None
        elif "html" in content_type or not content_type:
            if "charset" not in content_type:
                resp.encoding = resp.apparent_encoding or "utf-8"
            text = _extract_text_from_html(resp.text)
        elif "text/" in content_type:
            if "charset" not in content_type:
                resp.encoding = resp.apparent_encoding or "utf-8"
            text = resp.text
        else:
            return None
    except Exception:
        return None
    return normalize_text(text)


def fetch_from_any_source(query, target_lang=None, *, validate=None,
                          max_fetches=12, max_validations=5,
                          deadline_s=WEB_SEARCH_DEADLINE_S):
    """
    جست‌جو در چند موتور، دانلود کاندیداها، فیلتر رایگان، و در صورت وجود
    callback اعتبارسنجی، اولین متنِ پذیرفته‌شده را برمی‌گرداند.
    خروجی: (متن_خام, متا) یا (None, None).
    """
    search_queries = [
        query,
        f'"{query}" "full text"',
        f'"{query}" read online',
        f'"{query}" ebook',
    ]
    if target_lang == "fa":
        search_queries.extend([
            f'"{query}" متن کامل کتاب',
            f'site:ganjoor.net {query}',
        ])

    engines = [
        ("duckduckgo", "https://html.duckduckgo.com/html/?q={}"),
        ("bing", "https://www.bing.com/search?q={}"),
        ("google", "https://www.google.com/search?num=20&q={}"),
        ("mojeek", "https://www.mojeek.com/search?q={}"),
        ("marginalia", "https://search.marginalia.nu/search?query={}"),
    ]

    deadline = time.monotonic() + deadline_s
    expired = lambda: time.monotonic() > deadline

    # فاز ۱: جمع‌آوری لینک‌ها به‌صورتِ عرضی (هر موتور یک کوئری، بعد کوئری بعدی)
    # و با «مرگ تدریجی» موتور: موتورِ بلاک‌شده (202/403/429/5xx) یا دو کوئریِ
    # پیاپیِ بی‌نتیجه دیگر صدا زده نمی‌شود — این‌طوری یک موتورِ قطع، بقیه را
    # معطل نمی‌کند و بودجه‌ی زمانی صرفِ موتورهای سالم می‌شود.
    urls, seen = [], set()
    dead, zero_hits = set(), {}
    for q in search_queries:
        if expired() or len(urls) >= 24:
            break
        for engine, template in engines:
            if expired() or engine in dead:
                continue
            time.sleep(random.uniform(0.4, 1.0))
            try:
                resp = SESSION.get(template.format(urllib.parse.quote(q)),
                                   headers=SEARCH_HEADERS, timeout=15)
            except requests.RequestException:
                continue
            if resp.status_code != 200:
                if resp.status_code in (202, 403, 429, 451, 500, 503):
                    dead.add(engine)
                continue
            found = iter_result_urls(engine, resp.text)
            if not found:
                zero_hits[engine] = zero_hits.get(engine, 0) + 1
                if zero_hits[engine] >= 2:
                    dead.add(engine)  # صفحه‌ی 200ِ بدون نتیجه (پوسته‌ی JS)
                continue
            zero_hits[engine] = 0
            for url in found:
                if url not in seen:
                    seen.add(url)
                    urls.append(url)

    if not urls:
        return None, None

    # فاز ۲: دانلود + فیلتر رایگان + اعتبارسنجی
    # اولویت با نشانی‌هایی که کلماتِ عنوان در مسیرشان می‌آید (مثلاً
    # /the-time-machine/) تا صفحه‌های بی‌ربطِ اولِ نتایج آخر بررسی شوند.
    query_words = [w for w in _norm_words(query) if len(w) > 2]

    def _url_priority(u):
        parts = urllib.parse.urlparse(u)
        hay = (parts.path + "?" + parts.query).lower()
        return -sum(1 for w in query_words if w in hay)

    urls = sorted(urls, key=_url_priority)

    fetched = validated = 0
    for url in urls:
        if expired() or fetched >= max_fetches or validated >= max_validations:
            break
        fetched += 1
        text = _download_and_extract(url)
        # برای مرحله‌ی وب (آخرین راه‌حل) سخت‌گیرانه‌تر از منابع ساختارمند:
        # متنِ کاملِ یک کتاب معمولاً ده‌ها هزار نویسه است؛ صفحه‌ی کوتاهِ
        # بی‌ربط (ساعت، مقاله، معرفی) نباید پذیرفته شود.
        if not looks_like_book_text(text, min_chars=5000, min_words=400):
            continue
        meta = {"source": "web_scrape", "url": url}
        if validate is None:
            return text, meta
        validated += 1
        if validate(text):
            return text, meta
    return None, None


# ---------------------------------------------------------------------------
# مرحله‌ی ۶: ترجمه‌ی تازه به فارسی (در صورت نیاز)
# ---------------------------------------------------------------------------

def translate_to_persian(client, models, text: str, chunk_chars: int = 4000) -> str:
    paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    # پاراگرافِ بلندتر از سقف هم باید بشکند تا اندازه‌ی هر فراخوانی واقعاً
    # زیر chunk_chars بماند (وگرنه یک فراخوانیِ غول‌پیکر می‌شود).
    bounded = []
    for p in paragraphs:
        while len(p) > chunk_chars:
            cut = p.rfind(" ", 0, chunk_chars + 1)
            if cut <= 0:
                cut = chunk_chars
            bounded.append(p[:cut].rstrip())
            p = p[cut:].lstrip()
        if p:
            bounded.append(p)
    chunks, buf, buf_len = [], [], 0
    for p in bounded:
        # قبل از افزودن: اگر پاراگراف جا نمی‌شود، بسته‌ی فعلی را تمام کن؛
        # هرگز بیشتر از chunk_chars (مگر یک پاراگرافِ واحد).
        if buf and buf_len + len(p) > chunk_chars:
            chunks.append("\n\n".join(buf))
            buf, buf_len = [], 0
        buf.append(p)
        buf_len += len(p)
    if buf:
        chunks.append("\n\n".join(buf))
    if not chunks:
        return text

    translated_parts = []
    for i, chunk in enumerate(chunks, 1):
        prompt = _fill(TRANSLATE_PROMPT, chunk=chunk)
        translated = llm.generate_text(client, models, prompt, budget_s=240.0)
        translated_parts.append(translated)
        print(f"  ترجمه بخش {i}/{len(chunks)} انجام شد")
    return "\n\n".join(translated_parts)


# ---------------------------------------------------------------------------
# نقطه‌ی ورود اصلی این ماژول
# ---------------------------------------------------------------------------

def get_source_text(client, model_name: str, raw_title: str, target_lang: str,
                    manuscripts_dir: Path):
    """
    target_lang: 'fa'، 'en' یا 'auto'.

    در حالت 'auto' (پیش‌فرضِ CLI) زبان از خودِ متنِ پیداشده گرفته می‌شود:
    نام کتاب به هر زبانی وارد شود، کتاب به همان زبانی ساخته می‌شود که متنش
    پیدا شده — بدون ترجمه‌ی غیرمنتظره. زبانِ نهایی در meta["lang"] برمی‌گردد.

    اولویت با فایل دستی کاربر است؛ سپس گوتنبرگ؛ سپس Open Library /
    Internet Archive؛ و در نهایت جست‌جوی آزاد در وب. هر متنِ غیر هدف
    نهایی با داوریِ LLM رد یا پذیرفته می‌شود.
    """
    requested = (target_lang or "auto").strip().lower()
    auto_lang = requested not in ("fa", "en")
    target_lang = requested if not auto_lang else guess_lang(raw_title)

    models = llm.text_models(model_name)
    norm = normalize_title(client, models, raw_title)
    slug = slugify(norm.get("title_en") or raw_title)
    raw_slug = slugify(raw_title)
    want_title = norm.get("title_en") or raw_title
    want_author = norm.get("author") or ""

    # ۱) فایل دستی کاربر. عنوانِ نرمال‌شده ممکن است نگارش را عوض کند، پس
    #    نام خام را هم امتحان می‌کنیم.
    candidate_slugs = list(dict.fromkeys([slug, raw_slug]))
    suffix_order = ([target_lang] + [x for x in ("fa", "en") if x != target_lang]
                    if auto_lang else [target_lang])
    for candidate_slug in candidate_slugs:
        for suffix in suffix_order + [None]:
            name = (f"{candidate_slug}-{suffix}.txt" if suffix
                    else f"{candidate_slug}.txt")
            candidate = manuscripts_dir / name
            if candidate.exists():
                content = normalize_text(
                    candidate.read_text(encoding="utf-8")).strip()
                if content:
                    print(f"استفاده از متن دستی: {candidate}")
                    meta = {"source": "manual", "path": str(candidate),
                            "lang": guess_lang(content)}
                    return content, norm, meta

    failures = []

    def make_validator():
        def validate(text):
            ok, reason = validate_candidate_text(client, models, want_title,
                                                 want_author, text)
            print(f"    داوری متن: {'✓ پذیرفته' if ok else '✗ رد شد'} — {reason}")
            if not ok:
                failures.append(reason)
            return ok
        return validate

    def finish(text, meta):
        text = normalize_text(text)
        found_lang = "fa" if looks_persian(text) else "en"
        meta["lang"] = target_lang
        if auto_lang:
            # زبان خروجی از خودِ متن پیروی می‌کند (بدون ترجمه‌ی غافلگیرکننده).
            if found_lang != target_lang:
                print("زبانِ متنِ پیدا‌شده با حدسِ اولیه فرق دارد؛ "
                      "کتاب به زبانِ خودِ متن ساخته می‌شود.")
            meta["lang"] = found_lang
        elif target_lang == "fa" and found_lang == "en":
            print("متنِ غیرفارسیِ پیدا شد؛ در حال تولید ترجمه‌ی تازه با Gemini ...")
            text = translate_to_persian(client, models, text)
            meta["translated"] = True
        elif target_lang == "en" and found_lang == "fa":
            print("هشدار: متنِ پیدا‌شده فارسی است ولی خروجی انگلیسی خواسته شده؛ "
                  "کتاب به فارسی ساخته می‌شود تا صفحه‌آرایی و فونت درست بماند.")
            meta["lang"] = "fa"
        return text, norm, meta

    # ۲) Project Gutenberg
    print("جست‌وجو در Project Gutenberg ...")
    raw_text, meta = find_public_domain_text(
        norm.get("gutenberg_query") or want_title,
        preferred_lang=("fa" if target_lang == "fa" else "en"),
        want_title=want_title, want_author=want_author,
        validate=make_validator(), max_candidates=3,
    )
    if raw_text:
        meta["source"] = "gutenberg"
        return finish(clean_gutenberg_text(raw_text), meta)

    # ۳) Open Library + Internet Archive
    print("جست‌وجو در Open Library / Internet Archive ...")
    raw_text, meta = find_archive_text(
        want_title, want_author,
        preferred_lang=("fa" if target_lang == "fa" else "en"),
        validate=make_validator(), max_candidates=4,
    )
    if raw_text:
        meta["source"] = "archive_org"
        return finish(raw_text, meta)

    # ۴) جست‌جوی آزاد در کل وب
    print("جست‌جوی وب برای یافتن متن کتاب (با داوری هوشمند) ...")
    raw_text, meta = fetch_from_any_source(
        norm.get("gutenberg_query") or want_title,
        target_lang, validate=make_validator(),
    )
    if raw_text:
        return finish(raw_text, meta)

    detail = ("\nدلایل رد شدن کاندیداها:\n  - " + "\n  - ".join(failures[-5:])
              if failures else "")
    raise ManualTextRequired(
        f"هیچ متنی برای «{raw_title}» در هیچ منبعی (گوتنبرگ، آرشیو اینترنت، وب) "
        f"پیدا نشد.{detail}\n"
        f"می‌توانی خودت فایل متن را در این مسیر قرار دهی:\n"
        f"  manuscripts/{slug}-{target_lang}.txt\n"
        f"و دوباره اجرا کن."
    )
