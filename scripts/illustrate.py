# -*- coding: utf-8 -*-
"""
illustrate.py
--------------
تقسیم متن به بخش‌های «دو صفحه متن، یک صفحه تصویر»، تحلیل هر بخش با Gemini
برای ساخت عنوان/کپشن/پرامپت تصویری، و تولید تصویر با مدل تصویرسازیِ همان API.

مقاومت‌ها:
* نتیجه‌ی هر تحلیل و تصویر در کنار فایل تصویر کش می‌شود؛ اجرای دوباره
  همان کتاب (مثلاً بعد از شکست در بخش ۳۰) همه‌چیز را از نو نمی‌سازد.
* خطای موقت مدل‌ها با backoff تکرار می‌شود (llm.py).
* بین درخواست‌های تصویر فاصله‌ی ایمن گذاشته می‌شود (سهمیه‌ی رایگان خیلی
  زود به 429 می‌خورد) و تصویرهای ناموفق در چند پاسِ بعدی دوباره تلاش
  می‌شوند تا کتاب با کمترین جای‌گذار کامل شود.
* شکستِ تحلیل/تصویر کل کتاب را نمی‌کُشد: بخش با پیش‌فرض ساخته می‌شود و
  PDF بدون آن تصویر (یا با صفحه‌ی جای‌گذار) تولید می‌گردد.
"""

import hashlib
import json
import os
import random
import re
import time
from pathlib import Path

import free_image
import llm
import render

TEXT_MODEL = os.getenv("GEMINI_TEXT_MODEL") or llm.DEFAULT_TEXT_MODELS[0]
IMAGE_MODEL = os.getenv("GEMINI_IMAGE_MODEL") or llm.DEFAULT_IMAGE_MODELS[0]

# با سقفِ نویسه‌ی صفحه‌بندیِ render.py یکی است تا نسبت واقعیِ «دو صفحه متن،
# یک صفحه تصویر» با واقعیت خروجی بخواند.
CHARS_PER_PAGE = render.DEFAULT_TEXT_CHARS


def _env_number(name: str, default: float) -> float:
    """عدد از متغیر محیطی، با مقدارِ پیش‌فرض در صورتِ نبود/خرابی."""
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        print(f"هشدار: {name}=«{raw}» عدد نیست؛ پیش‌فرض {default} استفاده می‌شود.")
        return default


def pages_per_image() -> int:
    """چند صفحه متن بین دو تصویر (پیش‌فرض ۲ → چیدمان متن/متن/تصویر)."""
    return max(1, int(_env_number("GEMINI_PAGES_PER_IMAGE", 2)))


def image_delay_s() -> float:
    """حداقل فاصله‌ی بین دو درخواست تصویر (پیش‌فرض ۱۲ ثانیه)."""
    return max(0.0, _env_number("GEMINI_IMAGE_DELAY_SECONDS", 12.0))


def image_retry_passes() -> int:
    """چند پاسِ اضافه برای تصویرهایی که ساخته نشدند (پیش‌فرض ۲)."""
    return max(0, int(_env_number("GEMINI_IMAGE_RETRY_PASSES", 2)))


def image_retry_cooldown_s() -> float:
    """مکث بین پاس‌های تکرارِ تصویر (پیش‌فرض ۹۰ ثانیه)."""
    return max(0.0, _env_number("GEMINI_IMAGE_RETRY_COOLDOWN_SECONDS", 90.0))


# صفحه‌بندیِ واقعیِ render تنها مرجعِ تقسیم است؛ این دو فقط برای سازگاری‌اند.
MIN_PAGES_PER_IMAGE = 2
MAX_PAGES_PER_IMAGE = 2


def _pace(last_ts: float, gap: float, reason: str) -> float:
    """تا رسیدنِ «gap» ثانیه از درخواستِ قبلی صبر می‌کند و زمانِ تازه را
    برمی‌گرداند؛ با jitterِ کوچک تا الگوی درخواست‌ها یکنواخت نباشد."""
    gap = max(0.0, float(gap or 0))
    if last_ts and gap:
        wait = gap - (time.monotonic() - last_ts)
        if wait > 0:
            print(f"    {reason}: {wait:.0f}s صبر ...")
            time.sleep(wait + random.uniform(0, min(2.0, gap * 0.2)))
    return time.monotonic()

IMAGE_STYLE_SUFFIX = (
    ", cinematic film still from a literary movie trailer, 16:9 widescreen "
    "composition, dramatic volumetric lighting, deep shadows, rich cinematic "
    "color grading, subtle 35mm film grain, epic and emotional atmosphere, "
    "photorealistic cinematic concept art, ultra detailed, sharp focus, "
    "professional color science, no text, no letters, no captions, "
    "no watermark, no logo, no border, no frame"
)

ANALYSIS_PROMPT = """
تو یک ویراستار هنری و فیلم‌نامه‌نویسِ بصری هستی. زبان خروجی متنی باید <<LANG>> باشد.
برای بخشی از یک کتاب که به تو داده می‌شود، فقط یک JSON خام با این ساختار
دقیق برگردان (بدون هیچ متن اضافه):

{
  "chapter_title": "عنوان کوتاه و ادبی این بخش، به زبان <<LANG>>",
  "chapter_kicker": "یک زیرعنوان کوتاه انگلیسی با حروف بزرگ، حداکثر ۵ کلمه",
  "caption": "یک پاراگراف کوتاه (۲ تا ۳ جمله)، اتمسفریک و ادبی به زبان <<LANG>>، که فضای این بخش را توصیف می‌کند (بازنویسی خلاقانه، نه رونویسی مستقیم از متن)",
  "image_prompt_en": "پرامپت تصویرسازی به انگلیسی — قواعدش پایین آمده"
}

قواعد «image_prompt_en» (خیلی مهم):
۱) فقط و فقط بر اساس همین متن نوشته شود؛ هیچ شخصیت، مکان یا شیئی که در این
   بخش نیست اضافه نکن.
۲) یک لحظه‌ی مشخص و قابلِ دیدن را انتخاب کن (نه خلاصه‌ی کل بخش): همان صحنه‌ای
   که در این متن اتفاق می‌افتد.
۳) این جزئیات را، هر کدام که در متن آمده، صریح بنویس: تعداد و نوعِ شخصیت‌ها
   (انسان/حیوان/موجود)، سن و لباس، حالتِ چهره و بدن، عملِ در حالِ انجام،
   مکانِ دقیق، زمانِ روز، هوا، و اشیای کلیدیِ صحنه.
۴) حس و اتمسفر را با واژه‌های بصری بنویس (نور، سایه، رنگ، بافت) — نه با
   تفسیر یا استعاره.
۵) اگر متن گفتگو یا روایتِ درونی است، آن را به یک تصویرِ عینی ترجمه کن
   (حالتِ چهره، فاصله‌ی آدم‌ها، محیطِ اطراف).
۶) هیچ حرف/کلمه/تابلو/کتابِ باز با متن در تصویر توصیف نکن؛ پرامپت باید
   بدونِ نوشتار کار کند.
۷) پرامپت را انگلیسی، ۲ تا ۴ جمله‌ی توصیفی و پرجزئیات بنویس (حدود ۶۰ تا
   ۱۵۰ کلمه) و با سبکِ یک فریمِ سینمایی از تریلرِ فیلم بیان کن.

متن بخش کتاب:
---
<<CHUNK>>
---
"""

BLURB_PROMPT = """
یک توضیحِ تک‌جمله‌ای، زیبا و ادبی (حداکثر ۲۵ کلمه) به زبان <<LANG>>
برای معرفی این کتاب روی جلد بنویس. فقط همان یک جمله را برگردان، بدون
گیومه و بدون توضیح اضافه.

عنوان کتاب: <<TITLE>>
نویسنده: <<AUTHOR>>
ابتدای متن کتاب (برای فهم فضا):
---
<<SAMPLE>>
---
"""


def split_into_paragraphs(text: str):
    return [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]


def _split_long_piece(piece: str, limit: int):
    """برشِ یک پاراگرافِ خیلی بلند: اول روی مرز جمله، وگرنه روی مرز کلمه."""
    if len(piece) <= limit:
        return [piece]
    sentences = [s.strip() for s in re.split(r"(?<=[.!?؟…:])\s+", piece)
                 if s.strip()]
    if len(sentences) <= 1:
        sentences = [piece]
    out, buf = [], ""
    for sent in sentences:
        candidate = f"{buf} {sent}".strip() if buf else sent
        if len(candidate) <= limit:
            buf = candidate
            continue
        if buf:
            out.append(buf)
            buf = ""
        if len(sent) <= limit:
            buf = sent
            continue
        # حتی یک جمله هم از حد گذشت: روی مرز کلمه
        rest = sent
        while len(rest) > limit:
            cut = rest.rfind(" ", 0, limit + 1)
            if cut <= 0:
                cut = limit
            out.append(rest[:cut].rstrip())
            rest = rest[cut:].lstrip()
        buf = rest
    if buf:
        out.append(buf)
    return [p for p in out if p]


def _count_pages(paragraphs, lang: str) -> int:
    """تعداد صفحه‌ای که render از همین پاراگراف‌ها می‌سازد (همان سقفِ خطِ
    صفحه‌ی آغازِ بخش)، تا تقسیمِ بخش‌ها با چیدمانِ واقعیِ PDF یکی باشد."""
    cpl = render.CHARS_PER_LINE.get(lang, render.DEFAULT_CHARS_PER_LINE)
    line_cap = render.line_cap_for(lang, 0)
    pages = render._paginate_paragraphs(
        paragraphs, line_cap * cpl,
        first_page_chars=max(3, line_cap - render.FIRST_PAGE_LINES_OFFSET) * cpl,
        chars_per_line=cpl,
    )
    return len(pages) if pages and pages != [[]] else 0


def chunk_text_by_target_pages(paragraphs, target_pages=None, lang="fa"):
    """
    متن را به بخش‌هایی می‌شکند که هرکدام با صفحه‌بندیِ واقعیِ render دقیقاً
    «pages_per_image» صفحه‌ی متن داشته باشند (پیش‌فرض ۲). یعنی خروجی PDF
    این ریتم را می‌گیرد: دو صفحه متن، یک صفحه تصویر.

    تقسیم قطعی است (بدون تصادف) تا کشِ تحلیل/تصویر در اجرای بعدی به‌کار بیاید.
    هیچ متنی گم نمی‌شود: فقط مرزِ بین دو بخش، بین دو پاراگراف (یا برای
    پاراگرافِ بلندتر از یک صفحه، روی مرزِ جمله) می‌افتد.
    """
    target = max(1, int(target_pages or pages_per_image()))
    cpl = render.CHARS_PER_LINE.get(lang, render.DEFAULT_CHARS_PER_LINE)
    line_cap = render.line_cap_for(lang, 0)

    pieces = []
    for paragraph in paragraphs:
        paragraph = str(paragraph or "").strip()
        if not paragraph:
            continue
        # پاراگرافی که از یک صفحه بلندتر است، پیش از بسته‌بندی بریده می‌شود
        # تا هیچ بخشی بیشتر از سقفِ صفحه نداشته باشد.
        pieces.extend(_split_long_piece(paragraph, line_cap * cpl))

    chunks, current = [], []
    for piece in pieces:
        if current and _count_pages(current + [piece], lang) > target:
            chunks.append("\n\n".join(current))
            current = [piece]
        else:
            current.append(piece)
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def _lang_name(lang: str) -> str:
    return "فارسی" if lang == "fa" else "English"


def _fill(prompt: str, **values) -> str:
    for key, value in values.items():
        prompt = prompt.replace(f"<<{key.upper()}>>", str(value))
    return prompt


def generate_blurb(client, title: str, author: str, sample_text: str, lang: str) -> str:
    prompt = _fill(
        BLURB_PROMPT, lang=_lang_name(lang), title=title, author=author or "",
        sample=(sample_text or "")[:1500],
    )
    try:
        text = llm.generate_text(client, llm.text_models(TEXT_MODEL), prompt,
                                 budget_s=120.0)
    except Exception as exc:
        print(f"هشدار: توضیح جلد ساخته نشد: {type(exc).__name__}: {exc}")
        return ""
    return text.strip().strip('"').strip("«»")


def analyze_chunk(client, chunk: str, lang: str) -> dict:
    """تحلیل یک بخش؛ هم خطای API و هم JSONِ خراب → پیش‌فرضهای قابل قبول."""
    prompt = _fill(ANALYSIS_PROMPT, lang=_lang_name(lang),
                   chunk=chunk[:24000])
    data = {}
    try:
        data = llm.generate_json(client, llm.text_models(TEXT_MODEL), prompt,
                                 budget_s=180.0) or {}
    except Exception as exc:
        print(f"هشدار: تحلیل بخش ناموفق بود ({type(exc).__name__}: {exc})؛ "
              f"استفاده از پیش‌فرض‌ها")
    if not isinstance(data, dict):
        data = {}
    return {
        "chapter_title": str(data.get("chapter_title") or ""),
        "chapter_kicker": str(data.get("chapter_kicker") or ""),
        "caption": str(data.get("caption") or chunk[:200]),
        "image_prompt_en": str(data.get("image_prompt_en") or
                               "An atmospheric cinematic film still, strictly "
                               "following this passage of the book: "
                               f"{chunk[:300]}"),
    }


def _cache_paths(img_dir, index: int, chunk: str):
    digest = hashlib.sha1(chunk.encode("utf-8")).hexdigest()[:10]
    return (img_dir / f"scene_{index:02d}_{digest}.png",
            img_dir / f"scene_{index:02d}_{digest}.json")


# سرصفحه‌ی فایل‌های تصویریِ قابلِ چاپ؛ پاسخِ HTML/JSON یا فایلِ خالی نباید
# به‌عنوانِ تصویر در PDF بنشیند (وگرنه آیکونِ «تصویر شکسته» چاپ می‌شود).
_IMAGE_MAGIC = (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF87a", b"GIF89a")


def _is_printable_image(data: bytes) -> bool:
    if not data or len(data) < 16:
        return False
    if data.startswith(_IMAGE_MAGIC):
        return True
    return data[:4] == b"RIFF" and data[8:12] == b"WEBP"


def image_backend() -> str:
    """کدام موتور تصویرسازی؟ auto (پیش‌فرض) | gemini | cloudflare."""
    backend = (os.getenv("IMAGE_BACKEND") or "auto").strip().lower()
    return backend if backend in ("auto", "gemini", "cloudflare") else "auto"


def generate_image(client, prompt: str, out_path) -> bool:
    """
    تصویرِ یک بخش را می‌سازد.

    ترتیب در حالتِ auto: اول Gemini (کیفیتِ بالاتر و وفاداریِ بهتر به متن)،
    و اگر کلیدِ Gemini سهمیه‌ی تصویر نداشت، Cloudflare Workers AI که در پلنِ
    رایگانش روزی ۱۰٬۰۰۰ neuron (حدود ۵۰ تا ۲۳۰ تصویر) می‌دهد.
    """
    if not prompt:
        return False
    text = prompt + IMAGE_STYLE_SUFFIX
    backend = image_backend()
    data = None

    if backend in ("auto", "gemini"):
        try:
            data = llm.generate_image_bytes(client, text)
        except Exception as exc:
            print(f"هشدار: تصویرسازی با Gemini شکست خورد: "
                  f"{type(exc).__name__}: {exc}")
            data = None

    if not data and backend in ("auto", "cloudflare"):
        if free_image.is_configured():
            print("    تصویر با Cloudflare Workers AI (رایگان) ...")
            data = free_image.generate_image_bytes(text)
        elif backend == "cloudflare":
            print("هشدار: CLOUDFLARE_ACCOUNT_ID/CLOUDFLARE_API_TOKEN تنظیم نشده‌اند.")

    if not data:
        return False
    if not _is_printable_image(data):
        print("هشدار: خروجیِ مدل تصویر نبود (یا ناقص بود)؛ دور انداخته شد.")
        return False
    out_path.write_bytes(data)
    return True


def build_sections(client, full_text: str, lang: str, img_dir):
    paragraphs = split_into_paragraphs(full_text)
    chunks = chunk_text_by_target_pages(paragraphs, lang=lang)
    sections = []
    total = len(chunks)
    image_ts = 0.0
    for i, chunk in enumerate(chunks, start=1):
        img_path, meta_path = _cache_paths(img_dir, i, chunk)

        # --- کشِ تحلیل (اجرای دوباره را ارزان می‌کند) ------------------
        meta = None
        if meta_path.is_file():
            try:
                cached = json.loads(meta_path.read_text(encoding="utf-8"))
                if isinstance(cached, dict) and cached.get("chunk_sha1") == \
                        hashlib.sha1(chunk.encode("utf-8")).hexdigest():
                    meta = cached.get("meta")
                    print(f"[{i}/{total}] تحلیل بخش از کش خوانده شد.")
            except (ValueError, OSError):
                meta = None

        if not isinstance(meta, dict):
            print(f"[{i}/{total}] تحلیل بخش با Gemini ...")
            meta = analyze_chunk(client, chunk, lang)
            try:
                meta_path.write_text(
                    json.dumps({"chunk_sha1":
                                hashlib.sha1(chunk.encode("utf-8")).hexdigest(),
                                "meta": meta}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except OSError:
                pass

        # --- تصویر (از کش، یا تولید تازه) -------------------------------
        image_ok = img_path.is_file() and img_path.stat().st_size > 0
        if image_ok:
            print(f"[{i}/{total}] تصویر از کش خوانده شد: {img_path.name}")
        else:
            print(f"[{i}/{total}] تولید تصویر ...")
            image_ts = _pace(image_ts, image_delay_s(),
                             "فاصله‌ی ایمن بین درخواست‌های تصویر")
            try:
                image_ok = generate_image(client, meta.get("image_prompt_en", ""),
                                          img_path)
            except Exception as exc:
                print(f"هشدار: تصویر بخش {i} ساخته نشد: {exc}")
                image_ok = False
            if not image_ok and img_path.is_file():
                try:
                    img_path.unlink()  # فایل خالی/خراب را نگه نداریم
                except OSError:
                    pass

        sections.append({
            "paragraphs": split_into_paragraphs(chunk),
            "chapter_title": meta.get("chapter_title", ""),
            "chapter_kicker": meta.get("chapter_kicker", "") or f"PLATE {i}",
            "caption": meta.get("caption", ""),
            "image_path": str(img_path) if image_ok else None,
            # برای پاس‌های تکرار: مسیر و پرامپتِ همان تصویر را نگه می‌داریم.
            "image_file": str(img_path),
            "image_prompt_en": meta.get("image_prompt_en", ""),
        })

    # --- پاس‌های تکرار: تصویرهایی که در دورِ اول ساخته نشدند ---------------
    # سهمیه‌ی رایگان معمولاً با یک مکث برمی‌گردد؛ به‌جای رهاکردنِ جای‌گذار،
    # چند بار دیگر تلاش می‌کنیم تا کتاب تا حدِ ممکن کامل شود.
    for pass_no in range(1, image_retry_passes() + 1):
        pending = [s for s in sections if not s.get("image_path")]
        if not pending:
            break
        cooldown = image_retry_cooldown_s()
        print(f"پاس تکرار {pass_no}: {len(pending)} تصویر ساخته نشده"
              + (f"؛ {cooldown:.0f}s صبر ..." if cooldown else ""))
        if cooldown:
            time.sleep(cooldown)
        for sec in pending:
            path = Path(sec["image_file"])
            image_ts = _pace(image_ts, image_delay_s(),
                             "فاصله‌ی ایمن بین درخواست‌های تصویر")
            try:
                ok = generate_image(client, sec.get("image_prompt_en", ""), path)
            except Exception as exc:
                print(f"هشدار: تلاش دوباره برای {path.name} شکست خورد: {exc}")
                ok = False
            if ok and path.is_file() and path.stat().st_size > 0:
                sec["image_path"] = str(path)
                print(f"    تصویر {path.name} در پاس تکرار ساخته شد.")
    return sections
