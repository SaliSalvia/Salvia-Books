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
* متادیتای PDF (عنوان/نویسنده/زبان) و فهرستِ کنارِ PDF (bookmark) هم نوشته می‌شود.
* حاشیه‌آراییِ چاپی است: حاشیه‌ی شیرازه (inner) پهن‌تر است و بر اساسِ زوج/فرد
  بودنِ صفحه («verso»/«recto») آینه می‌شود؛ صفحه‌ی آغازِ هر بخش سرصفحه ندارد و
  سرصفحه‌ی بقیه‌ی صفحه‌ها نامِ کتاب (چپ) یا عنوانِ بخش (راست) است.
* شماره‌ی صفحه و فهرست در کتابِ فارسی با ارقامِ فارسی چاپ می‌شوند.
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
# نویسه‌ای است که در یک خطِ کاملِ چیدمانِ واقعیِ کرومیوم جا می‌شود (عرضِ
# ستونِ ۶۴۸px، قلمِ ۲۲٫۵/۲۳٫۵px). این اعداد تجربی‌اند: با بالاتر بردنشان
# صفحه‌ها پرتر می‌شوند ولی ریسکِ سرریز بالا می‌رود.
CHARS_PER_LINE = {"fa": 63, "en": 67}

# سقفِ خط در هر صفحه؛ صفحه‌ی آغازِ هر بخش (با عنوان و خطِ تزئینی) چهار خط کمتر.
LINE_CAPACITY = {"fa": 19, "en": 19}
FIRST_PAGE_LINES_OFFSET = 4

# اگر صفحه‌ای سرریز کرد، هر تلاشِ بعدی این‌قدر خط کمتر می‌گیرد.
LINE_STEP_DOWN = 1
MAX_ATTEMPTS = 5

# برای سازگاری با تست‌های صفحه‌بندی که هنوز بر حسبِ نویسه کار می‌کنند.
DEFAULT_CHARS_PER_LINE = CHARS_PER_LINE["fa"]
DEFAULT_TEXT_CHARS = LINE_CAPACITY["fa"] * DEFAULT_CHARS_PER_LINE


def line_cap_for(lang: str, attempt: int = 0) -> int:
    """سقفِ خط در هر صفحه برای تلاشِ شماره‌ی attempt."""
    base = LINE_CAPACITY.get(lang, LINE_CAPACITY["en"])
    return max(6, base - LINE_STEP_DOWN * attempt)

# چند ردیف فهرست در یک صفحه جا می‌شود. در کتاب‌های کم‌بخش (نسخه‌ی تصویری)
# هر ردیف کپشن هم دارد و بلندتر است؛ در کتاب‌های پربخش فهرست جمع‌وجور می‌شود.
CONTENTS_ROWS_PER_PAGE = 11
CONTENTS_ROWS_DESCRIBED = 5
CONTENTS_DESCRIBED_MAX_SECTIONS = 14

PAGE_W, PAGE_H = 794, 1123

CSS = """
@page { size: 794px 1123px; margin: 0; }
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
/* ---------------- توکن‌های طراحی ---------------- */
:root {
  --ink: #241d0e; --ink-soft: #4a3c1e; --paper: #f7f0de;
  --gold: #b3893c; --gold-line: rgba(179,137,60,.24);
  --outer: 62px; --inner: 84px;
}
body {
  font-family: var(--font); color: var(--ink); background: var(--paper);
  font-kerning: normal; font-variant-ligatures: common-ligatures;
  text-rendering: optimizeLegibility;
}
/* ایتالیک فقط برای متنِ لاتین؛ فونتِ فارسی صورتِ موربِ واقعی ندارد و
   موربِ مصنوعیِ مرورگر زشت است. */
em { font-style: normal; }
[dir="ltr"] em { font-style: italic; }
.page {
  width: 794px; height: 1123px; position: relative; overflow: hidden;
  background: var(--paper);
  page-break-after: always; break-after: page;
}
/* صفحه‌ی آخر نباید شکستِ اضافه بسازد (وگرنه PDF یک صفحه‌ی سفید می‌گیرد) */
.page:last-child { page-break-after: auto; break-after: auto; }
[dir="rtl"] .page { direction: rtl; }
[dir="ltr"] .page { direction: ltr; }

/* ---------------- جلد و پشت‌جلد ---------------- */
.cover, .backcover {
  background: radial-gradient(ellipse at 50% 36%, #2c255c 0%, #1a1739 58%, #100e26 100%);
  color: #ece0c0; text-align: center;
}
.cover {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 108px 86px 208px;
}
.backcover {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 118px 86px 180px;
}
.frame { position: absolute; inset: 28px; border: 1px solid rgba(196,158,74,.42); }
.frame::after { content: ""; position: absolute; inset: 6px; border: 1px solid rgba(196,158,74,.16); }
/* نگین (الماسِ کوچک) — با CSS ساخته می‌شود، نه گلیفِ فونت */
.ornament {
  width: 6px; height: 6px; background: var(--gold); transform: rotate(45deg);
  opacity: .85; margin: 0 auto 28px;
}
.ornament.tight { margin: 30px auto 0; opacity: .55; }
.cover .kicker, .backcover .kicker {
  font-size: 11px; letter-spacing: 4.4px; text-transform: uppercase;
  color: #b99c58; margin: 0 0 30px;
}
[dir="rtl"] .cover .kicker, [dir="rtl"] .backcover .kicker {
  letter-spacing: .8px; font-size: 12px;
}
.cover h1 {
  font-size: 55px; line-height: 1.28; margin: 0 0 22px; max-width: 590px;
  font-weight: 800; text-wrap: balance; color: #f2e6c6;
}
[dir="ltr"] .cover h1, .cover h1.latin { font-weight: 600; font-size: 60px; }
/* عنوان/نویسنده‌ی لاتین در کتابِ فارسی با فونتِ لاتین چیده می‌شود */
.cover h1.latin, .cover .author.latin, .runhead.latin {
  font-family: 'EB Garamond', 'Vazirmatn', serif;
}
.cover .author { font-size: 17px; letter-spacing: 2.4px; color: #cbb878; }
.cover .author.latin { font-size: 19px; letter-spacing: 2px; }
[dir="rtl"] .cover .author { letter-spacing: .4px; }
.cover .rule, .backcover .rule {
  width: 104px; height: 1px; margin: 32px auto;
  background: linear-gradient(90deg, rgba(196,158,74,0), #c8a24a, rgba(196,158,74,0));
}
.cover .blurb {
  font-size: 19px; line-height: 1.95; color: #d9caa0;
  max-width: 468px; font-style: italic; margin: 0;
}
/* فارسی مورب (شکسته‌نویس مصنوعی) زشت می‌شود */
[dir="rtl"] .cover .blurb { font-style: normal; line-height: 2.05; }
.cover .credit, .backcover .credit {
  position: absolute; bottom: 86px; left: 0; right: 0;
  display: flex; flex-direction: column; align-items: center; gap: 14px;
  font-size: 12.5px; color: #c2a86a;
}
.cover .credit img, .backcover .credit img {
  width: 54px; height: 54px; object-fit: contain;
}
.backcover .note {
  font-size: 17px; line-height: 2.05; max-width: 496px; color: #d9caa0;
  margin: 0; text-wrap: balance;
}
.backcover .github {
  font-size: 12.5px; color: #9fb3d9; margin-top: 2px; direction: ltr;
  letter-spacing: .2px;
}

/* ---------------- صفحه‌ی فهرست ---------------- */
.contents-page { display: flex; flex-direction: column; }
.contents-page h2 {
  font-size: 28px; margin: 0; text-align: center; font-weight: 700;
  letter-spacing: -.1px;
}
[dir="ltr"] .contents-page h2 { font-weight: 600; font-size: 30px; }
.contents-page .rule { width: 64px; height: 2px; background: var(--gold); margin: 18px auto 0; }
.contents-page .rows { margin-top: 42px; display: flex; flex-direction: column; }
.contents-page .row {
  display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 30px;
  align-items: start; padding: 18px 0 17px;
  border-bottom: 1px solid var(--gold-line, rgba(179,137,60,.24));
}
.contents-page .row:first-child {
  border-top: 1px solid var(--gold-line, rgba(179,137,60,.24));
}
.contents-page .row .kicker { font-size: 10.5px; letter-spacing: 2.4px; color: #a3823a; }
[dir="rtl"] .contents-page .row .kicker { letter-spacing: .4px; font-size: 11.5px; }
.contents-page .row .name {
  font-size: 21px; line-height: 1.5; font-weight: 700; margin-top: 8px;
}
[dir="ltr"] .contents-page .row .name { font-weight: 600; font-size: 22px; }
.contents-page .row .caption {
  font-size: 15px; line-height: 1.8; color: #5f4e27; margin-top: 8px;
  max-width: 480px;
  /* ارتفاعِ ردیف باید قابلِ پیش‌بینی بماند، وگرنه فهرست از کادر می‌زند */
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden;
}
.contents-page .row .nums { text-align: end; white-space: nowrap; }
.contents-page .row .num { display: block; font-size: 17px; color: #6d5a2c; }
.contents-page .row .plate-num {
  display: block; font-size: 11px; color: #96794a; margin-top: 9px;
  letter-spacing: .2px;
}
.contents-page .edition-line {
  margin-top: auto; padding-top: 28px; text-align: center;
  font-size: 11.5px; color: #8a7444; letter-spacing: .3px;
}
/* کتابِ پربخش: فهرستِ جمع‌وجور (بدونِ کپشن، ردیف‌های کم‌ارتفاع) */
.contents-page[data-compact] .row { padding: 12px 0 11px; }
.contents-page[data-compact] .row .kicker { font-size: 10px; letter-spacing: 1.8px; }
.contents-page[data-compact] .row .name { font-size: 19px; margin-top: 4px; }
.contents-page[data-compact] .row .num { font-size: 15px; }
.contents-page[data-compact] .row .plate-num { margin-top: 5px; }

/* ---------------- صفحات متن ---------------- */
.text-page { display: flex; flex-direction: column; }
.runhead {
  font-size: 10.5px; line-height: 14px; letter-spacing: 2.5px;
  text-transform: uppercase; color: #a8905f; text-align: center;
  padding-bottom: 12px; border-bottom: 1px solid var(--gold-line, rgba(179,137,60,.26));
  margin-bottom: 28px;
}
[dir="rtl"] .runhead { letter-spacing: .3px; font-size: 11px; }
.runhead.latin { font-family: 'EB Garamond', 'Vazirmatn', serif; letter-spacing: 2.6px; }
/* صفحه‌ی آغازِ بخش سرصفحه نمی‌گیرد (عنوان بزرگ خودش آن‌جاست) */
.runhead.blank { visibility: hidden; }
.text-page .title-wrap { text-align: center; margin: 14px 0 32px; }
.text-page .title-wrap .kicker {
  font-size: 11.5px; letter-spacing: 2.8px; color: #a3823a; margin-bottom: 13px;
}
[dir="rtl"] .text-page .title-wrap .kicker { letter-spacing: .4px; font-size: 12px; }
.text-page h2 { font-size: 32px; line-height: 1.45; margin: 0; font-weight: 700; }
[dir="ltr"] .text-page h2 { font-weight: 600; font-size: 34px; }
.text-page .title-wrap .rule {
  width: 72px; height: 2px; background: var(--gold); margin: 17px auto 0;
}
.text-page p {
  font-size: 22.5px; line-height: 45px; margin: 0; text-align: justify;
  hyphens: auto; -webkit-hyphens: auto;
}
[dir="ltr"] .text-page p { font-size: 23.5px; line-height: 46px; }
.text-page p + p { text-indent: 1.8em; }
/* بدونِ این، فلکس‌باکس متنِ سرریز را به‌جای بیرون‌زدن، مچاله می‌کند
   (ارتفاعِ پاراگراف‌ها ۰ می‌شود و شناساگرِ سرریز هیچ‌وقت هشدار نمی‌دهد) */
.text-page > *:not(.footer) { flex: 0 0 auto; }

/* ---------------- صفحات تصویری ---------------- */
.image-page { display: flex; flex-direction: column; }
.image-page .img-half { width: 100%; height: 588px; object-fit: cover; display: block; }
.image-page .img-half.placeholder {
  background: radial-gradient(ellipse at center, #2c255c 0%, #100e26 78%);
  box-shadow: inset 0 0 0 20px var(--paper, #f7f0de), inset 0 0 0 22px #c8a24a;
}
.image-page .caption-half {
  flex: 1; padding: 56px 92px 104px; text-align: center;
  display: flex; flex-direction: column; justify-content: center; align-items: center;
  border-top: 1px solid var(--gold-line, rgba(179,137,60,.24));
}
.image-page .caption-half .kicker {
  font-size: 11px; letter-spacing: 3px; color: #a3823a; margin-bottom: 16px;
}
[dir="rtl"] .image-page .caption-half .kicker { letter-spacing: .4px; font-size: 12px; }
.image-page .caption-half h3 {
  font-size: 27px; line-height: 1.5; margin: 0; font-weight: 700; max-width: 520px;
}
[dir="ltr"] .image-page .caption-half h3 { font-weight: 600; font-size: 29px; }
.image-page .caption-half .rule {
  width: 56px; height: 1px; background: var(--gold); margin: 20px auto 18px;
}
.image-page .caption-half p {
  font-size: 19px; line-height: 1.95; color: #42351a; margin: 0; max-width: 520px;
}

/* ---------------- فوتر ---------------- */
.footer {
  position: absolute; bottom: 30px; left: 0; right: 0; height: 30px;
  display: flex; align-items: center; justify-content: center;
  font-size: 11px; color: #8a7a4f;
}
.footer .page-num { font-size: 11.5px; color: #7c6a3f; letter-spacing: .5px; }
/* نشانِ برند در گوشه‌ی بیرونیِ پایین (متقابل با شیرازه) */
.footer .brand {
  position: absolute; top: 0; height: 30px;
  inset-inline-end: 44px; inset-inline-start: auto;
  direction: ltr; display: flex; align-items: center; gap: 8px;
}
.page[data-side="verso"] .footer .brand {
  inset-inline-start: 44px; inset-inline-end: auto;
}
.footer .brand img { width: 22px; height: 22px; object-fit: contain; }
.footer .brand span { font-size: 10px; letter-spacing: .3px; color: #9a875a; }

/* ---------------- حاشیه‌های چاپیِ آینه‌ای ---------------- */
/* سمتِ شیرازه (inner) پهن‌تر است و جای دوخت/بازشدنِ کتاب را می‌دهد؛
   سمتِ بیرونی (outer) بازتر می‌ماند. «recto» صفحه‌ی سمتِ راست و
   «verso» صفحه‌ی سمتِ چپِ دفتر است. */
.text-page, .contents-page {
  padding-top: 72px; padding-bottom: 100px;
  padding-inline-start: var(--outer, 62px);
  padding-inline-end: var(--inner, 84px);
}
.contents-page { padding-top: 82px; }
/* در هر دو جهتِ چیدمان، سمتِ شروعِ خواندن روی شیرازه است؛ پس قاعده
   مستقل از RTL/LTR است: recto شیرازه در start، verso شیرازه در end. */
.text-page[data-side="recto"], .contents-page[data-side="recto"] {
  padding-inline-start: var(--inner, 84px);
  padding-inline-end: var(--outer, 62px);
}
.text-page[data-side="verso"], .contents-page[data-side="verso"] {
  padding-inline-start: var(--outer, 62px);
  padding-inline-end: var(--inner, 84px);
}
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


def _wrap(piece: str, fill: int, cpl: int):
    """
    شبیه‌سازیِ شکستنِ خط برای یک قطعه‌ی متن: ``(خط‌های مصرفشده، پرشدگیِ خطِ
    آخر)``. برخلافِ تقسیمِ نویسه‌ای، این‌جا فضای هدررفته‌ی آخرِ هر خط (که
    آخرین کلمه جا نشده) حساب می‌شود — همان چیزی که صفحه را واقعاً پر می‌کند.
    """
    lines, fill = 0, max(0, fill)
    for word in piece.split():
        w = len(word)
        if fill == 0:
            fill = w
        elif fill + 1 + w <= cpl:
            fill += 1 + w
        else:
            lines += 1
            fill = w
        while fill > cpl:  # کلمه‌ای بلندتر از یک خط
            fill -= cpl
            lines += 1
    return lines, fill


def _paginate_paragraphs(paragraphs, max_chars=750, first_page_chars=None,
                         chars_per_line=None):
    """
    متن را به صفحه‌هایی با سقفِ خط می‌شکند، طوری که:
    * هیچ صفحه‌ای از کادر بیرون نزند،
    * هیچ صفحه‌ای بی‌دلیل نیمه‌خالی نماند (بسته‌بندی در سطحِ جمله)،
    * هیچ متنی گم نشود و هیچ کلمه‌ای وسطِ بریده نشود.
    """
    cpl = max(10, int(chars_per_line or DEFAULT_CHARS_PER_LINE))
    max_lines = max(3, int(max_chars) // cpl)
    first_lines = (max(3, int(first_page_chars) // cpl)
                   if first_page_chars else max_lines)

    pages, current = [], []
    # `breaks` = تعدادِ شکستنِ خط در صفحه؛ خطِ جاری جدا شمرده می‌شود، چون
    # نیمه‌پر است و هنوز به `breaks` اضافه نشده.
    breaks, fill, last_pid = 0, 0, None

    def close_page():
        nonlocal current, breaks, fill
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
        current, breaks, fill = [], 0, 0

    for pid, sid, sentence in _sentence_blocks(paragraphs):
        # قطعه‌ی تک‌نفره‌ای که از یک صفحه بلندتر است با فاصله می‌شکند؛
        # یک خط احتیاط می‌گذاریم تا خودِ قطعه از کادر بیرون نزند.
        chunk = max(3, max_lines - 1) * cpl
        for piece in _split_long_piece(sentence, chunk):
            limit = first_lines if not pages else max_lines
            if current and pid != last_pid and fill:
                # پاراگرافِ تازه از خطِ بعد شروع می‌شود.
                breaks += 1
                fill = 0
            added, end_fill = _wrap(piece, fill, cpl)
            used = breaks + added + (1 if end_fill else 0)
            if current and used > limit:
                close_page()
                limit = max_lines
                added, end_fill = _wrap(piece, 0, cpl)
            current.append((pid, sid, piece))
            breaks, fill = breaks + added, end_fill
            last_pid = pid
    close_page()
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


# قراردادِ Project Gutenberg برای ایتالیک: _متن_
_EMPH_RE = re.compile(r"(?<![\w_])_([^_\n]{1,400})_(?![\w_])")
# نشانه‌ی ایتالیکِ جفت‌نشده (تا در چاپ به‌شکلِ زیرخط دیده نشود)
# زیرخطِ چسبیده به مرزِ واژه (نه وسطِ واژه‌ای مثل snake_case)
_STRAY_MARK_RE = re.compile(r"(?:^|(?<![^\W_]))_+|_+(?![^\W_])")


def _plain(text: str) -> str:
    """متنِ امن برای HTML، بدونِ نشانه‌های جفت‌نشده‌ی ایتالیک."""
    return _STRAY_MARK_RE.sub("", escape(str(text or "")))


def _rich(text: str) -> str:
    """متنِ امن با ایتالیک: _متن_ → <em>متن</em> (قراردادِ گوتنبرگ)."""
    text = str(text or "")
    out, pos = [], 0
    for m in _EMPH_RE.finditer(text):
        out.append(_plain(text[pos:m.start()]))
        out.append(f"<em>{_plain(m.group(1))}</em>")
        pos = m.end()
    out.append(_plain(text[pos:]))
    return "".join(out)


_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def _num(value, lang: str) -> str:
    """شماره‌ها در کتابِ فارسی با ارقامِ فارسی چاپ می‌شوند."""
    text = str(value)
    return text.translate(_FA_DIGITS) if lang == "fa" else text


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
                     out_html_path: Path, line_cap: int = None,
                     contents_rows: int = None):
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
    runhead_text = str(title or "")
    title_class = "latin" if not _has_rtl(title) else ""

    cpl = CHARS_PER_LINE.get(lang, 60)
    line_cap = int(line_cap or line_cap_for(lang))
    max_chars = line_cap * cpl
    pages = _layout_pages(sections, line_cap=line_cap, chars_per_line=cpl)

    # ---- شماره‌ی صفحه‌ها: ۱ جلد، بعد صفحه(های) فهرست، بعد بدنه ----
    contents_rows_count = sum(1 for p in pages
                              if p["kind"] == "text" and p["first"])
    described = len(sections) <= CONTENTS_DESCRIBED_MAX_SECTIONS
    rows_per_page = (CONTENTS_ROWS_DESCRIBED if described
                     else CONTENTS_ROWS_PER_PAGE)
    if contents_rows:  # حلقه‌ی بازچاپ وقتی فهرست از کادر می‌زند
        rows_per_page = max(2, int(contents_rows))
    contents_page_count = ((contents_rows_count + rows_per_page - 1)
                           // rows_per_page) if sections else 0
    body_start = 2 + contents_page_count

    number_by_page = {}
    num = body_start
    for pos, page in enumerate(pages):
        number_by_page[pos] = num
        num += 1

    def side_of(page_number):
        """صفحه‌ی فرد = سمتِ راست (recto)، زوج = سمتِ چپ (verso)."""
        return "recto" if page_number % 2 else "verso"

    plate_number = {page["index"]: number_by_page[pos]
                    for pos, page in enumerate(pages) if page["kind"] == "plate"}

    contents, contents_rows = [], []
    for pos, page in enumerate(pages):
        if page["kind"] == "text" and page["first"]:
            sec_title, kicker = _section_labels(page["section"], page["index"], lang)
            number = number_by_page[pos]
            contents.append((kicker, sec_title, number))
            contents_rows.append((kicker, sec_title,
                                  str(page["section"].get("caption") or "").strip(),
                                  number, plate_number.get(page["index"])))

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
<div class="page cover" dir="{dir_attr}" data-side="recto">
  <div class="frame"></div>
  <div class="ornament"></div>
  <div class="kicker">{escape(kicker_top)}</div>
  <h1 class="{title_class}">{escape(str(title))}</h1>
  {author_html}
  <div class="rule"></div>          <p class="blurb">{_rich(blurb or "")}</p>
  <div class="ornament tight"></div>
  <div class="credit">
    {_logo_img(logo_attr)}
    <div>{escape(label_by)}: <span dir="ltr">@SaliSalvia</span></div>
  </div>
</div>
''')

    # ---------------- فهرست ----------------
    plate_label = "تصویر" if fa else "Plate"
    if fa:
        edition_line = (f"{_num(len(sections), lang)} بخش · "
                        f"{_num(len(plate_number), lang)} تصویر")
    else:
        edition_line = (f"{len(sections)} sections · "
                        f"{len(plate_number)} plates")

    def _contents_row(kicker, name, caption, number, plate):
        body = (f'<div class="kicker">{escape(str(kicker))}</div>'
                f'<div class="name">{escape(str(name))}</div>')
        if described and caption:
            body += f'<div class="caption">{_rich(caption)}</div>'
        nums = f'<span class="num">{_num(number, lang)}</span>'
        if plate:
            nums += (f'<span class="plate-num">{escape(plate_label)} '
                     f'{_num(plate, lang)}</span>')
        return (f'<div class="row"><div class="row-main">{body}</div>'
                f'<div class="nums">{nums}</div></div>')

    for i in range(contents_page_count):
        chunk = contents_rows[i * rows_per_page:(i + 1) * rows_per_page]
        rows = "".join(_contents_row(*row) for row in chunk)
        edition = ('<div class="edition-line">'
                   f'{escape(edition_line)}</div>'
                   if i == contents_page_count - 1 else "")
        num = 2 + i
        compact = "" if described else ' data-compact="1"'
        output.append(f'''
<div class="page contents-page" dir="{dir_attr}" data-side="{side_of(num)}"{compact}>
  <h2>{escape(contents_title)}</h2>
  <div class="rule"></div>
  <div class="rows">{rows}</div>
  {edition}
  {_footer_html(_num(num, lang), logo_attr)}
</div>
''')

    # ---------------- بدنه ----------------
    for pos, page in enumerate(pages):
        page_num = number_by_page[pos]
        side = side_of(page_num)
        sec = page["section"]
        sec_title, kicker = _section_labels(sec, page["index"], lang)
        if page["kind"] == "text":
            text_html = "".join(f"<p>{_rich(p)}</p>"
                               for p in page["paragraphs"])
            heading = ""
            if page["first"]:
                # صفحه‌ی آغازِ بخش: عنوانِ بزرگ، بی‌سرصفحه (تكرارِ عنوان لازم نیست)
                head = '<div class="runhead blank">&nbsp;</div>'
                heading = (
                    '<div class="title-wrap">'
                    f'<div class="kicker">{escape(kicker)}</div>'
                    f"<h2>{escape(sec_title)}</h2>"
                    '<div class="rule"></div>'
                    "</div>"
                )
            else:
                # سرصفحه‌ی کتاب: سمتِ چپ نامِ کتاب، سمتِ راست عنوانِ بخش
                label = runhead_text if side == "verso" else sec_title
                head_class = ("runhead" if _has_rtl(label)
                              else "runhead latin")
                head = f'<div class="{head_class}">{escape(str(label))}</div>'
            output.append(f'''
<div class="page text-page" dir="{dir_attr}" data-side="{side}">
  {head}
  {heading}
  {text_html}
  {_footer_html(_num(page_num, lang), logo_attr)}
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
<div class="page image-page" dir="{dir_attr}" data-side="{side}">
  {img_html}
  <div class="caption-half">
    <div class="kicker">{escape(kicker)}</div>
    <h3>{escape(sec_title)}</h3>
    <div class="rule"></div>
    <p>{_rich(caption)}</p>
  </div>
  {_footer_html(_num(page_num, lang), logo_attr)}
</div>
''')

    # ---------------- پشت‌جلد ----------------
    if sections:
        output.append(f'''
<div class="page backcover" dir="{dir_attr}" data-side="{side_of(page_count)}">
  <div class="frame"></div>
  <div class="ornament"></div>
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
    if contents_page_count:
        outline.append((contents_title, 1, 2))
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
        "contents_rows": rows_per_page,
        "contents_page_count": contents_page_count,
    }


# ---------------------------------------------------------------------------
# اندازه‌گیریِ سرریز + PDF
# ---------------------------------------------------------------------------

_OVERFLOW_JS = """
() => {
  // محتوا باید بالای نوار فوتر بماند (پایینِ صفحه ۱۰۰ پیکسل حاشیه دارد)
  const H = 1123, SAFE = 100;
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
        meta = {str(k): str(v) for k, v in (metadata or {}).items()}
        # /Lang کلیدِ اطلاعاتی نیست؛ روی catalog می‌نشیند (زبانِ سند برای
        # صفحه‌خوان‌ها و موتورهای جست‌وجو).
        lang = meta.pop("/Lang", "")
        if meta:
            writer.add_metadata(meta)
        try:
            from pypdf.generic import (BooleanObject, DictionaryObject,
                                       NameObject, TextStringObject)
            root = writer._root_object
            if lang:
                root[NameObject("/Lang")] = TextStringObject(lang)
            root[NameObject("/ViewerPreferences")] = DictionaryObject({
                NameObject("/DisplayDocTitle"): BooleanObject(True),
            })
        except Exception:
            pass  # نسخه‌ی قدیمیِ pypdf — متادیتای اصلی نوشته شده است
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
