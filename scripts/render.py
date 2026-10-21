# -*- coding: utf-8 -*-
"""
render.py
---------
ساخت HTML (صفحات عمودی A4، جلد + فهرست + پشت‌جلد + فوتر استاندارد) و تبدیل
آن به PDF با Playwright (کرومیوم headless).

نکات کیفیت و مقاومت:
* فونت‌ها محلی‌اند (`assets/fonts`) تا خروجی به شبکه وابسته نباشد و بی‌سروصدا
  با فونت پیش‌فرض ساخته نشود.
* صفحه‌بندی روی مرز کلمه انجام می‌شود تا کلمات (مخصوصاً فارسی) وسطِ صفحه
  بریده نشوند و هیچ متنی از دست نرود.
* بعد از ساختِ HTML، ارتفاعِ محتوای هر صفحه اندازه‌گیری می‌شود؛ اگر صفحه‌ای
  سرریز کرده باشد گزارش می‌شود تا صفحه‌بندی با سقفِ کمتر دوباره انجام شود
  (به‌جای بریده‌شدنِ بی‌صدای متن).
* متادیتای PDF (عنوان/نویسنده) و فهرستِ کنارِ PDF (bookmark) هم نوشته می‌شود.
"""

import base64
import re
from functools import lru_cache
from html import escape
from pathlib import Path

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
_FONT_FACE_RE = re.compile(r"@font-face\s*\{(.*?)\}", re.S)

GOOGLE_FONTS_URL = (
    "https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;500;600;"
    "700;800&family=EB+Garamond:ital,wght@0,400;0,600;1,400&display=swap"
)

# صفحه‌بندی بر اساسِ «خط» است، نه نویسه: متنِ پرگفت‌وگو (پاراگراف‌های کوتاه)
# در همان تعداد نویسه چند خط بیشتر می‌گیرد. این اعداد از اندازه‌گیریِ واقعیِ
# چیدمان در کرومیوم به‌دست آمده‌اند (ارتفاعِ ۱۱۲۳px، حاشیه‌ی ۶۸/۱۰۴، سرصفحه).
CHARS_PER_LINE = {"fa": 61, "en": 69}

# سقفِ خط در هر صفحه؛ صفحه‌ی آغازِ هر بخش (با عنوان و خطِ تزئینی) سه خط کمتر.
LINE_CAPACITY = {"fa": 19, "en": 17}
FIRST_PAGE_LINES_OFFSET = 3

# اگر صفحه‌ای سرریز کرد، هر تلاشِ بعدی این‌قدر خط کمتر می‌گیرد.
LINE_STEP_DOWN = 2
MAX_ATTEMPTS = 5

# برای سازگاری با تست‌های صفحه‌بندی که هنوز بر حسبِ نویسه کار می‌کنند.
DEFAULT_CHARS_PER_LINE = CHARS_PER_LINE["fa"]
DEFAULT_TEXT_CHARS = LINE_CAPACITY["fa"] * DEFAULT_CHARS_PER_LINE


def line_cap_for(lang: str, attempt: int = 0) -> int:
    """سقفِ خط در هر صفحه برای تلاشِ شماره‌ی attempt."""
    base = LINE_CAPACITY.get(lang, LINE_CAPACITY["en"])
    return max(6, base - LINE_STEP_DOWN * attempt)

# چند ردیف فهرست در یک صفحه جا می‌شود (برای کتاب‌های چندبخشی→ چند صفحه فهرست)
CONTENTS_ROWS_PER_PAGE = 13

PAGE_W, PAGE_H = 794, 1123

CSS = """
@page { size: 794px 1123px; margin: 0; }
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body { font-family: var(--font); color: #2b2410; }
.page {
  width: 794px; height: 1123px; position: relative; overflow: hidden;
  page-break-after: always; break-after: page;
}
/* صفحه‌ی آخر نباید شکستِ اضافه بسازد (وگرنه PDF یک صفحه‌ی سفید می‌گیرد) */
.page:last-child { page-break-after: auto; break-after: auto; }
[dir="rtl"] .page { direction: rtl; }
[dir="ltr"] .page { direction: ltr; }

/* ---------------- جلد و پشت‌جلد ---------------- */
.cover, .backcover {
  background: radial-gradient(ellipse at center, #2a2359 0%, #14122e 72%);
  color: #e9dcb8; text-align: center;
}
.cover {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 96px 76px 170px;
}
.backcover {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 90px 76px;
}
.frame { position: absolute; inset: 26px; border: 1px solid rgba(200,162,74,.40); }
.frame::after { content: ""; position: absolute; inset: 7px; border: 1px solid rgba(200,162,74,.18); }
.cover .kicker, .backcover .kicker {
  font-size: 12.5px; letter-spacing: 4px; text-transform: uppercase;
  color: #b79a55; margin-bottom: 24px;
}
[dir="rtl"] .cover .kicker, [dir="rtl"] .backcover .kicker { letter-spacing: 1px; }
.cover h1 {
  font-size: 54px; line-height: 1.3; margin: 0 0 16px; max-width: 600px;
  font-weight: 800; text-wrap: balance;
}
[dir="ltr"] .cover h1, .cover h1.latin { font-weight: 600; }
/* عنوان/نویسنده‌ی لاتین در کتابِ فارسی با فونتِ لاتین چیده می‌شود */
.cover h1.latin, .cover .author.latin, .runhead.latin {
  font-family: 'EB Garamond', 'Vazirmatn', serif;
}
.cover .author { font-size: 19px; letter-spacing: 2.5px; color: #cbb878; }
.cover .author.latin { font-size: 21px; letter-spacing: 1.5px; }
[dir="rtl"] .cover .author { letter-spacing: .5px; }
.cover .rule, .backcover .rule {
  width: 120px; height: 1px; margin: 28px auto;
  background: linear-gradient(90deg, rgba(200,162,74,0), #c8a24a, rgba(200,162,74,0));
}
.cover .blurb {
  font-size: 20px; line-height: 1.95; color: #d8c99a;
  max-width: 520px; font-style: italic; margin: 0;
}
/* فارسی مورب (شکسته‌نویس مصنوعی) زشت می‌شود */
[dir="rtl"] .cover .blurb { font-style: normal; }
.cover .credit, .backcover .credit {
  position: absolute; bottom: 74px; left: 0; right: 0;
  display: flex; flex-direction: column; align-items: center; gap: 12px;
  font-size: 14px; color: #c8ae6a;
}
.cover .credit img, .backcover .credit img { width: 58px; height: 58px; object-fit: contain; }
.backcover .note {
  font-size: 18px; line-height: 1.95; max-width: 540px; color: #d8c99a; margin: 0;
}
.backcover .github { font-size: 14px; color: #9fb3d9; margin-top: 4px; direction: ltr; }

/* ---------------- صفحه‌ی فهرست ---------------- */
.contents-page { background: #f4ecd8; padding: 92px 76px 104px; display: flex; flex-direction: column; }
.contents-page h2 { font-size: 30px; margin: 0; text-align: center; font-weight: 700; }
[dir="ltr"] .contents-page h2 { font-weight: 600; }
.contents-page .rule { width: 84px; height: 2px; background: #c8a24a; margin: 20px auto 34px; }
.contents-page .rows { display: flex; flex-direction: column; }
.contents-page .row {
  display: flex; align-items: baseline; gap: 12px; padding: 13px 0 9px;
}
.contents-page .row .kicker {
  font-size: 11.5px; letter-spacing: 2.2px; color: #a5843a; white-space: nowrap;
}
[dir="rtl"] .contents-page .row .kicker { letter-spacing: .5px; }
.contents-page .row .name { font-size: 19px; line-height: 1.6; }
.contents-page .row .leader {
  flex: 1; min-width: 24px; border-bottom: 1px dotted rgba(139,116,58,.55);
  transform: translateY(-4px);
}
.contents-page .row .num { font-size: 16px; color: #6d5a2c; }

/* ---------------- صفحات متن ---------------- */
.text-page { background: #f4ecd8; padding: 68px 68px 104px; display: flex; flex-direction: column; }
.runhead {
  font-size: 11.5px; letter-spacing: 2.6px; text-transform: uppercase;
  color: #b09a68; text-align: center; padding-bottom: 13px;
  border-bottom: 1px solid rgba(200,162,74,.30); margin-bottom: 30px;
}
[dir="rtl"] .runhead { letter-spacing: .4px; }
.text-page .title-wrap { text-align: center; margin: 2px 0 32px; }
.text-page .title-wrap .kicker {
  font-size: 12.5px; letter-spacing: 3px; color: #a5843a; margin-bottom: 14px;
}
[dir="rtl"] .text-page .title-wrap .kicker { letter-spacing: .5px; }
.text-page h2 { font-size: 32px; line-height: 1.5; margin: 0; font-weight: 700; }
[dir="ltr"] .text-page h2 { font-weight: 600; }
.text-page .title-wrap .rule { width: 84px; height: 2px; background: #c8a24a; margin: 18px auto 0; }
.text-page p {
  font-size: 22.5px; line-height: 1.98; margin: 0; text-align: justify;
  hyphens: auto; -webkit-hyphens: auto;
}
[dir="ltr"] .text-page p { font-size: 24px; line-height: 1.9; }
.text-page p + p { text-indent: 1.7em; }
/* بدونِ این، فلکس‌باکس متنِ سرریز را به‌جای بیرون‌زدن، مچاله می‌کند
   (ارتفاعِ پاراگراف‌ها ۰ می‌شود و شناساگرِ سرریز هیچ‌وقت هشدار نمی‌دهد) */
.text-page > *:not(.footer) { flex: 0 0 auto; }

/* ---------------- صفحات تصویری ---------------- */
.image-page { background: #f4ecd8; display: flex; flex-direction: column; }
.image-page .img-half { width: 100%; height: 590px; object-fit: cover; display: block; }
.image-page .img-half.placeholder {
  background: radial-gradient(ellipse at center, #2a2359 0%, #14122e 72%);
  box-shadow: inset 0 0 0 18px #f4ecd8, inset 0 0 0 20px #c8a24a;
}
.image-page .caption-half {
  flex: 1; padding: 44px 74px 96px; text-align: center;
  display: flex; flex-direction: column; justify-content: center;
}
.image-page .caption-half .kicker {
  font-size: 12.5px; letter-spacing: 3px; color: #a5843a; margin-bottom: 16px;
}
[dir="rtl"] .image-page .caption-half .kicker { letter-spacing: .5px; }
.image-page .caption-half h3 { font-size: 27px; line-height: 1.55; margin: 0; font-weight: 700; }
[dir="ltr"] .image-page .caption-half h3 { font-weight: 600; }
.image-page .caption-half .rule { width: 64px; height: 1px; background: #c8a24a; margin: 18px auto 20px; }
.image-page .caption-half p { font-size: 20px; line-height: 1.9; color: #3a3018; margin: 0; }

/* ---------------- فوتر ---------------- */
.footer {
  position: absolute; bottom: 26px; left: 0; right: 0; height: 32px;
  display: flex; align-items: center; justify-content: center;
  font-size: 12px; color: #8a7a4f;
}
.footer .page-num { font-size: 12.5px; color: #7c6a3f; }
.footer .brand {
  position: absolute; left: 46px; top: 0; height: 32px;
  direction: ltr; display: flex; align-items: center; gap: 8px;
}
[dir="rtl"] .footer .brand { left: auto; right: 46px; }
.footer .brand img { width: 24px; height: 24px; object-fit: contain; }
.footer .brand span { font-size: 10.5px; letter-spacing: .3px; color: #9a875a; }
"""


# ---------------------------------------------------------------------------
# فونت‌ها: نسخه‌ی محلی، و اگر نبود، Google Fonts
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _local_font_files() -> tuple:
    """
    فهرستِ فونت‌های محلی از روی `assets/fonts/fonts.css`.

    فونت‌ها به‌صورتِ `url('file://…')` داخلِ CSS در مرورگر لود **نمی‌شوند**
    (کرومیوم فونتِ صفحه‌ی `file://` را بلاک می‌کند و صورتِ فونت با وضعیتِ
    `error` می‌ماند)، پس در زمانِ چاپ با `FontFace` تزریق می‌شوند.
    """
    css_path = FONT_DIR / "fonts.css"
    if not css_path.is_file():
        return ()
    faces = []
    for block in _FONT_FACE_RE.findall(css_path.read_text(encoding="utf-8")):
        family = re.search(r"font-family:\s*['\"]?([^;'\"]+)['\"]?\s*;", block)
        src = re.search(r"url\(\s*['\"]?([^'\")]+)['\"]?\s*\)", block)
        if not family or not src:
            continue
        path = FONT_DIR / src.group(1).strip()
        if not path.is_file():
            continue
        style = re.search(r"font-style:\s*([\w-]+)\s*;", block)
        weight = re.search(r"font-weight:\s*(\d+)\s*;", block)
        faces.append({
            "family": family.group(1).strip(),
            "style": style.group(1).strip() if style else "normal",
            "weight": weight.group(1).strip() if weight else "400",
            "path": path,
        })
    return tuple(faces)


@lru_cache(maxsize=1)
def _font_payload() -> tuple:
    """همان فهرست، با بایت‌های base64 (یک‌بار خوانده می‌شود، نه در هر صفحه)."""
    return tuple({
        "family": f["family"], "style": f["style"], "weight": f["weight"],
        "b64": base64.b64encode(f["path"].read_bytes()).decode("ascii"),
    } for f in _local_font_files())


def _font_css() -> str:
    """
    CSSِ فونت. اگر فونتِ محلی داریم، این‌جا چیزی لازم نیست (تزریق در چاپ)؛
    وگرنه به Google Fonts تکیه می‌کنیم.
    """
    if _local_font_files():
        return ("/* فونت‌های محلی هنگامِ ساختِ PDF از assets/fonts "
                "تزریق می‌شوند. */")
    return f"@import url('{GOOGLE_FONTS_URL}');"


_FONT_SPECS = [
    "400 23px Vazirmatn", "700 23px Vazirmatn", "800 23px Vazirmatn",
    "400 23px 'EB Garamond'", "600 36px 'EB Garamond'",
    "italic 400 20px 'EB Garamond'",
]

# تزریقِ فونت‌ها داخلِ صفحه (بدونِ شبکه و بدونِ محدودیتِ file://)
_FONT_JS = """
async (defs) => {
  for (const d of defs) {
    const bin = atob(d.b64);
    const buf = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
    const face = new FontFace(d.family, buf.buffer,
                              {style: d.style, weight: d.weight, display: 'block'});
    await face.load();
    document.fonts.add(face);
  }
  await document.fonts.ready;
  return document.fonts.size;
}
"""


# ---------------------------------------------------------------------------
# صفحه‌بندی
# ---------------------------------------------------------------------------

def _split_long_piece(piece: str, max_chars: int):
    """برشِ نویسه‌ایِ یک پاراگرافِ بلند، ترجیحاً روی مرز فاصله (نه وسط کلمه)."""
    out = []
    rest = piece
    while len(rest) > max_chars:
        cut = rest.rfind(" ", 0, max_chars + 1)
        if cut <= 0:  # فاصله‌ای در برش نبود → مجبوریم
            cut = max_chars
        out.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    if rest:
        out.append(rest)
    return out


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?؟…:؛»\"])\s+")


def _sentence_blocks(paragraphs):
    """جریان جمله‌ها: (شماره‌ی پاراگراف, شماره‌ی جمله, متن).

    بسته‌بندی در سطحِ جمله انجام می‌شود تا پاراگرافِ بلند، صفحه‌های
    نیمه‌خالیِ پشتِ‌سرهم نسازد.
    """
    for pid, paragraph in enumerate(paragraphs):
        paragraph = str(paragraph).strip()
        if not paragraph:
            continue
        for sid, sentence in enumerate(
                s for s in _SENTENCE_SPLIT.split(paragraph) if s.strip()):
            yield pid, sid, sentence.strip()


def _paginate_paragraphs(paragraphs, max_chars=750, first_page_chars=None,
                         chars_per_line=None):
    """
    متن را به صفحه‌هایی با سقفِ خط می‌شکند، طوری که:
    * هیچ صفحه‌ای از کادر بیرون نزند (شکستِ پاراگراف یک خطِ کامل هدر می‌دهد)،
    * هیچ صفحه‌ای بی‌دلیل نیمه‌خالی نماند (بسته‌بندی در سطحِ جمله)،
    * هیچ متنی گم نشود و هیچ کلمه‌ای وسطِ بریده نشود.
    """
    import math

    cpl = max(10, int(chars_per_line or DEFAULT_CHARS_PER_LINE))
    max_lines = max(3, int(max_chars) // cpl)
    first_lines = (max(3, int(first_page_chars) // cpl)
                   if first_page_chars else max_lines)

    pages, current, used, last_pid = [], [], 0.0, None

    def flush():
        nonlocal current, used
        if not current:
            return
        merged = []
        for pid, sid, text in current:
            if merged and merged[-1][0] == pid:
                if merged[-1][1] == sid:
                    merged[-1][2] += text           # ادامه‌ی همان جمله
                else:
                    merged[-1][2] += " " + text     # جمله‌ی بعدیِ همان پاراگراف
                merged[-1][1] = sid
            else:
                merged.append([pid, sid, text])
        pages.append([item[2] for item in merged])
        current, used = [], 0.0

    for pid, sid, sentence in _sentence_blocks(paragraphs):
        limit = first_lines if not pages else max_lines
        for piece in _split_long_piece(sentence, max(1, limit) * cpl):
            if current and pid != last_pid:
                # پاراگرافِ تازه از خطِ بعد شروع می‌شود؛ بقیه‌ی خط هدر می‌رود.
                used = math.ceil(used)
            if current and used + len(piece) / cpl > limit + 1e-9:
                flush()
                limit = max_lines
            if current and pid == last_pid and sid != current[-1][1]:
                used += 1 / cpl  # فاصله‌ی بینِ جمله‌های یک پاراگراف
            used += len(piece) / cpl
            current.append((pid, sid, piece))
            last_pid = pid
    flush()
    return pages or [[]]


def _layout_pages(sections, *, line_cap, chars_per_line):
    """فهرستِ صفحه‌های بدنه: برای هر بخش، صفحه‌های متن و سپس صفحه‌ی تصویر."""
    pages = []
    max_chars = line_cap * chars_per_line
    first_page_chars = max(3, line_cap - FIRST_PAGE_LINES_OFFSET) * chars_per_line
    for idx, sec in enumerate(sections, start=1):
        text_pages = _paginate_paragraphs(
            sec.get("paragraphs", []), max_chars,
            first_page_chars=first_page_chars,
            chars_per_line=chars_per_line)
        if text_pages == [[]]:
            text_pages = []
        for text_idx, paragraphs in enumerate(text_pages):
            pages.append({"kind": "text", "index": idx, "first": text_idx == 0,
                          "paragraphs": paragraphs, "section": sec})
        pages.append({"kind": "plate", "index": idx, "section": sec})
    return pages


# ---------------------------------------------------------------------------
# ساخت HTML
# ---------------------------------------------------------------------------

def _has_rtl(text: str) -> bool:
    """آیا متن حرفِ راست‌به‌چپ (فارسی/عربی) دارد؟"""
    return any(0x0590 <= ord(ch) <= 0x08FF for ch in str(text or ""))


def _logo_img(logo_uri: str):
    if not logo_uri:
        return ""
    return f'<img src="{escape(logo_uri, quote=True)}">'


def _footer_html(page_num, logo_uri):
    logo_html = _logo_img(logo_uri)
    brand_text = "Design by: @SaliSalvia"
    return (
        '<div class="footer">'
        f'<div class="brand">{logo_html}<span>{brand_text}</span></div>'
        f'<div class="page-num">{page_num}</div>'
        "</div>"
    )


def _section_labels(sec, idx, lang):
    if lang == "fa":
        fallback_title, fallback_kicker = f"بخش {idx}", f"تصویر {idx}"
    else:
        fallback_title, fallback_kicker = f"Plate {idx}", f"PLATE {idx}"
    title = str(sec.get("chapter_title") or "").strip() or fallback_title
    kicker = str(sec.get("chapter_kicker") or "").strip() or fallback_kicker
    return title, kicker


def render_book_html(*, lang: str, title: str, author: str, blurb: str,
                     sections: list, logo_uri: str, github_url: str,
                     out_html_path: Path, line_cap: int = None):
    """
    HTML کتاب را می‌سازد و نقشه‌ی صفحه‌ها را برمی‌گرداند:

        {"page_count": int, "line_cap": int, "max_chars": int,
         "outline": [(عنوان, ایندکسِ صفحه از صفر, سطح), ...],
         "contents": [(kicker, title, شماره‌ی صفحه), ...]}
    """
    fa = lang == "fa"
    font_var = ("'Vazirmatn', 'EB Garamond', serif" if fa
                else "'EB Garamond', 'Vazirmatn', serif")
    dir_attr = "rtl" if fa else "ltr"
    kicker_top = ("یک نسخه‌ی کیوریتوریِ تصویری" if fa
                  else "A CURATORIAL VISUAL EDITION")
    label_by = "طراحی و ساخت" if fa else "Designed & built by"
    contents_title = "فهرست" if fa else "Contents"
    colophon_title = "درباره‌ی این نسخه" if fa else "About this edition"
    colophon_body = (
        "این نسخه با کمک هوش مصنوعی (تحلیل متن، تصویرسازی و صفحه‌آرایی خودکار) "
        "به‌صورت غیرانتفاعی و صرفاً برای بازخوانیِ بصریِ اثر ساخته شده."
        if fa else
        "This edition was generated with the help of AI (automated text analysis, "
        "illustration, and layout) as a non-commercial visual companion to the "
        "original work."
    )
    logo_attr = escape(str(logo_uri or ""), quote=True)
    author_class = "author latin" if not _has_rtl(author) else "author"
    author_html = (f'<div class="{author_class}">{escape(str(author))}</div>'
                   if author else "")
    runhead_class = "runhead latin" if not _has_rtl(title) else "runhead"
    runhead_text = escape(str(title or ""))
    title_class = "latin" if not _has_rtl(title) else ""

    line_cap = int(line_cap or line_cap_for(lang))
    max_chars = line_cap * CHARS_PER_LINE.get(lang, 61)
    pages = _layout_pages(sections, line_cap=line_cap,
                          chars_per_line=CHARS_PER_LINE.get(lang, 61))

    # ---- شماره‌ی صفحه‌ها: ۱ جلد، بعد صفحه(های) فهرست، بعد بدنه ----
    contents_rows_count = sum(1 for p in pages
                              if p["kind"] == "text" and p["first"])
    contents_page_count = ((contents_rows_count + CONTENTS_ROWS_PER_PAGE - 1)
                           // CONTENTS_ROWS_PER_PAGE) if sections else 0
    body_start = 2 + contents_page_count

    number_by_page = {}
    num = body_start
    for pos, page in enumerate(pages):
        number_by_page[pos] = num
        num += 1

    contents = []
    for pos, page in enumerate(pages):
        if page["kind"] == "text" and page["first"]:
            sec_title, kicker = _section_labels(page["section"], page["index"], lang)
            contents.append((kicker, sec_title, number_by_page[pos]))

    page_count = body_start + len(pages) - 1 if pages else 1 + contents_page_count
    if sections:
        page_count += 1  # پشت‌جلد

    output = [f'''<!DOCTYPE html>
<html lang="{escape(lang, quote=True)}" dir="{dir_attr}">
<head>
<meta charset="UTF-8">
<title>{escape(str(title))}{(" — " + escape(str(author))) if author else ""}</title>
<meta name="author" content="{escape(str(author))}">
<meta name="description" content="{escape(str(blurb or ""), quote=True)}">
<meta name="generator" content="Salvia Visual Book Engine">
<style>
{_font_css()}
:root {{ --font: {font_var}; }}
{CSS}
</style></head><body>
''']

    # ---------------- جلد ----------------
    output.append(f'''
<div class="page cover" dir="{dir_attr}">
  <div class="frame"></div>
  <div class="kicker">{escape(kicker_top)}</div>
  <h1 class="{title_class}">{escape(str(title))}</h1>
  {author_html}
  <div class="rule"></div>
  <p class="blurb">{escape(str(blurb or ""))}</p>
  <div class="credit">
    {_logo_img(logo_attr)}
    <div>{escape(label_by)}: <span dir="ltr">@SaliSalvia</span></div>
  </div>
</div>
''')

    # ---------------- فهرست ----------------
    for i in range(contents_page_count):
        chunk = contents[i * CONTENTS_ROWS_PER_PAGE:
                         (i + 1) * CONTENTS_ROWS_PER_PAGE]
        rows = "".join(
            '<div class="row">'
            f'<div class="kicker">{escape(str(kicker))}</div>'
            f'<div class="name">{escape(str(name))}</div>'
            '<div class="leader"></div>'
            f'<div class="num">{number}</div>'
            "</div>"
            for kicker, name, number in chunk
        )
        output.append(f'''
<div class="page contents-page" dir="{dir_attr}">
  <h2>{escape(contents_title)}</h2>
  <div class="rule"></div>
  <div class="rows">{rows}</div>
  {_footer_html(2 + i, logo_attr)}
</div>
''')

    # ---------------- بدنه ----------------
    for pos, page in enumerate(pages):
        page_num = number_by_page[pos]
        sec = page["section"]
        sec_title, kicker = _section_labels(sec, page["index"], lang)
        if page["kind"] == "text":
            text_html = "".join(f"<p>{escape(str(p))}</p>"
                               for p in page["paragraphs"])
            heading = ""
            if page["first"]:
                heading = (
                    '<div class="title-wrap">'
                    f'<div class="kicker">{escape(kicker)}</div>'
                    f"<h2>{escape(sec_title)}</h2>"
                    '<div class="rule"></div>'
                    "</div>"
                )
            output.append(f'''
<div class="page text-page" dir="{dir_attr}">
  <div class="{runhead_class}">{runhead_text}</div>
  {heading}
  {text_html}
  {_footer_html(page_num, logo_attr)}
</div>
''')
        else:
            caption = str(sec.get("caption", "") or "")
            image_path = sec.get("image_path")
            if image_path and Path(image_path).is_file():
                img_html = (f'<img class="img-half" src="'
                            f'{escape(Path(image_path).resolve().as_uri(), quote=True)}">')
            else:
                # تصویر ساخته نشد: صفحه‌ی جای‌گذار با همان کپشن، تا طراحی و
                # شماره‌بندی کتاب بهم نریزد.
                img_html = '<div class="img-half placeholder"></div>'
            output.append(f'''
<div class="page image-page" dir="{dir_attr}">
  {img_html}
  <div class="caption-half">
    <div class="kicker">{escape(kicker)}</div>
    <h3>{escape(sec_title)}</h3>
    <div class="rule"></div>
    <p>{escape(caption)}</p>
  </div>
  {_footer_html(page_num, logo_attr)}
</div>
''')

    # ---------------- پشت‌جلد ----------------
    if sections:
        output.append(f'''
<div class="page backcover" dir="{dir_attr}">
  <div class="frame"></div>
  <div class="kicker">{escape(colophon_title)}</div>
  <div class="note">{escape(colophon_body)}</div>
  <div class="rule"></div>
  <div class="credit">
    {_logo_img(logo_attr)}
    <div>{escape(label_by)}: <span dir="ltr">@SaliSalvia</span></div>
    <div class="github">{escape(str(github_url))}</div>
  </div>
</div>
''')

    output.append("</body></html>")
    out_html_path.write_text("".join(output), encoding="utf-8")

    outline = [(str(title), 0, 1)]
    for idx, page in enumerate(pages):
        if page["kind"] == "text" and page["first"]:
            sec_title, kicker = _section_labels(page["section"], page["index"], lang)
            outline.append((f"{kicker} · {sec_title}", number_by_page[idx] - 1, 2))
    if sections:
        outline.append((colophon_title, page_count - 1, 1))

    return {
        "page_count": page_count,
        "line_cap": line_cap,
        "max_chars": max_chars,
        "outline": outline,
        "contents": contents,
    }


# ---------------------------------------------------------------------------
# اندازه‌گیریِ سرریز + PDF
# ---------------------------------------------------------------------------

_OVERFLOW_JS = """
() => {
  // محتوا باید بالای نوار فوتر بماند (پایینِ صفحه ۱۰۴ پیکسل حاشیه دارد)
  const H = 1123, SAFE = 104;
  const bad = [];
  document.querySelectorAll('.page').forEach((el, i) => {
    const pageRect = el.getBoundingClientRect();
    let bottom = -Infinity;
    el.querySelectorAll('.text-page > *:not(.footer), .caption-half > *, .contents-page > *:not(.footer)')
      .forEach(node => {
        const r = node.getBoundingClientRect();
        bottom = Math.max(bottom, r.bottom - pageRect.top);
      });
    if (isFinite(bottom) && bottom > H - SAFE) bad.push(i + 1);
  });
  return bad;
}
"""


def html_to_pdf(html_path: Path, pdf_path: Path, *, metadata=None, outline=None):
    """
    HTML را به PDF تبدیل می‌کند؛ خروجی: فهرستِ شماره‌ی صفحه‌هایی که محتوایشان
    از کادر بیرون زده است (خالی یعنی همه‌ی صفحه‌ها سالم‌اند).
    """
    from playwright.sync_api import sync_playwright

    overflow = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(Path(html_path).resolve().as_uri(), wait_until="load")
            # منتظر فونت‌ها می‌مانیم؛ اگر لود نشده باشند، هشدار چاپ می‌شود
            # تا بی‌صدا PDF با فونت پیش‌فرض ساخته نشود.
            try:
                # فونت‌های محلی را به‌صورتِ FontFace تزریق می‌کنیم؛ بارگذاریِ
                # `url(file://…)` از صفحه‌ی `file://` بلاک می‌شود.
                if _font_payload():
                    page.evaluate(_FONT_JS, list(_font_payload()))
                else:
                    page.evaluate(
                        """async (specs) => {
                            if (!document.fonts) return;
                            await Promise.all(specs.map(s =>
                                document.fonts.load(s).catch(() => null)));
                            await document.fonts.ready;
                        }""",
                        _FONT_SPECS,
                    )
                for spec in ("700 23px Vazirmatn", "400 23px 'EB Garamond'"):
                    if not page.evaluate("s => document.fonts.check(s)", spec):
                        print(f"هشدار: فونت «{spec}» لود نشد؛ "
                              f"خروجی با فونت جایگزین ساخته می‌شود.")
            except Exception as exc:
                print(f"هشدار: بررسی فونت‌ها ممکن نشد: {exc}")
            # دو فریم صبر تا چیدمان نهایی شود
            try:
                page.evaluate(
                    "() => new Promise(r => requestAnimationFrame("
                    "() => requestAnimationFrame(() => r())))")
            except Exception:
                page.wait_for_timeout(300)
            try:
                overflow = page.evaluate(_OVERFLOW_JS) or []
            except Exception:
                overflow = []
            page.pdf(
                path=str(pdf_path),
                width=f"{PAGE_W}px", height=f"{PAGE_H}px",
                print_background=True,
                margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
            )
        finally:
            browser.close()

    if metadata or outline:
        _stamp_pdf(pdf_path, metadata=metadata, outline=outline)
    return overflow


def _stamp_pdf(pdf_path: Path, *, metadata=None, outline=None):
    """متادیتا و فهرستِ PDF را با pypdf می‌نویسد؛ شکستش ساخت را متوقف نمی‌کند."""
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        print("هشدار: pypdf نصب نیست؛ متادیتا/فهرست PDF نوشته نشد.")
        return
    tmp_path = Path(str(pdf_path) + ".tmp")
    try:
        reader = PdfReader(str(pdf_path))
        writer = PdfWriter(clone_from=reader)
        if metadata:
            writer.add_metadata({str(k): str(v) for k, v in metadata.items()})
        if outline:
            stack = {}
            for title, page_index, level in outline:
                if not isinstance(page_index, int) or not (
                        0 <= page_index < len(writer.pages)):
                    continue
                parent = stack.get(level - 1)
                try:
                    item = writer.add_outline_item(title, page_index,
                                                   parent=parent)
                except Exception:
                    continue
                stack[level] = item
                for deeper in [k for k in stack if k > level]:
                    del stack[deeper]
        with open(tmp_path, "wb") as fh:
            writer.write(fh)
        tmp_path.replace(pdf_path)
    except Exception as exc:
        print(f"هشدار: نوشتن متادیتای PDF ناموفق بود ({type(exc).__name__}: {exc}).")
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
