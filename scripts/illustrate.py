# -*- coding: utf-8 -*-
"""
illustrate.py
--------------
تقسیم متن به بخش‌های متناسب با طول کتاب (هر ۶ تا ۱۱ صفحه یک تصویر)،
تحلیل هر بخش با Gemini برای ساخت عنوان/کپشن/پرامپت تصویری، و تولید
تصویر با مدل تصویرسازیِ همان API.

مقاومت‌ها:
* نتیجه‌ی هر تحلیل و تصویر در کنار فایل تصویر کش می‌شود؛ اجرای دوباره
  همان کتاب (مثلاً بعد از شکست در بخش ۳۰) همه‌چیز را از نو نمی‌سازد.
* خطای موقت مدل‌ها با backoff تکرار می‌شود (llm.py).
* شکستِ تحلیل/تصویر کل کتاب را نمی‌کُشد: بخش با پیش‌فرض ساخته می‌شود و
  PDF بدون آن تصویر (یا با صفحه‌ی جای‌گذار) تولید می‌گردد.
"""

import hashlib
import json
import os
import random
import re

import llm
import render

TEXT_MODEL = os.getenv("GEMINI_TEXT_MODEL") or llm.DEFAULT_TEXT_MODELS[0]
IMAGE_MODEL = os.getenv("GEMINI_IMAGE_MODEL") or llm.DEFAULT_IMAGE_MODELS[0]

# با سقفِ نویسه‌ی صفحه‌بندیِ render.py یکی است تا نسبت واقعی «هر ۶ تا ۱۱
# صفحه یک تصویر» با واقعیت خروجی بخواند.
CHARS_PER_PAGE = render.DEFAULT_TEXT_CHARS
MIN_PAGES_PER_IMAGE = 6
MAX_PAGES_PER_IMAGE = 11

IMAGE_STYLE_SUFFIX = (
    ", cinematic warm painterly illustration, soft golden lighting, "
    "dreamlike storybook atmosphere, highly detailed, wide landscape "
    "composition, no text, no watermark"
)

ANALYSIS_PROMPT = """
تو یک ویراستار هنری کتاب هستی. زبان خروجی متنی باید <<LANG>> باشد.
برای بخشی از یک کتاب که به تو داده می‌شود، فقط یک JSON خام با این ساختار
دقیق برگردان (بدون هیچ متن اضافه):

{
  "chapter_title": "عنوان کوتاه و ادبی این بخش، به زبان <<LANG>>",
  "chapter_kicker": "یک زیرعنوان کوتاه انگلیسی با حروف بزرگ، حداکثر ۵ کلمه",
  "caption": "یک پاراگراف کوتاه (۲ تا ۳ جمله)، اتمسفریک و ادبی به زبان <<LANG>>، که فضای این بخش را توصیف می‌کند (بازنویسی خلاقانه، نه رونویسی مستقیم از متن)",
  "image_prompt_en": "یک پرامپت تصویرسازی مفصل به انگلیسی برای مدل تولید تصویر، که مهم‌ترین و پرپتانسیل‌ترین صحنه‌ی این بخش را توصیف می‌کند"
}

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


def chunk_text_by_target_pages(paragraphs):
    # بذرِ تصادفیِ قطعی: همان متن همیشه به همان بخش‌ها تقسیم شود تا کشِ
    # تحلیل/تصویر در اجرای بعدی واقعاً به‌کار بیاید.
    seed = hashlib.sha1("\n\n".join(paragraphs).encode("utf-8", "ignore")).hexdigest()
    rng = random.Random(int(seed, 16))
    chunks = []
    current, current_len = [], 0
    target = rng.randint(MIN_PAGES_PER_IMAGE, MAX_PAGES_PER_IMAGE) * CHARS_PER_PAGE

    def flush():
        nonlocal current, current_len, target
        if current:
            chunks.append("\n\n".join(current))
        current, current_len = [], 0
        target = rng.randint(MIN_PAGES_PER_IMAGE, MAX_PAGES_PER_IMAGE) * CHARS_PER_PAGE

    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        for piece in _split_long_piece(paragraph, target):
            if current and current_len + len(piece) > target:
                flush()
            current.append(piece)
            current_len += len(piece)
            if current_len >= target:
                flush()
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
                               f"An atmospheric literary illustration inspired by: {chunk[:300]}"),
    }


def _cache_paths(img_dir, index: int, chunk: str):
    digest = hashlib.sha1(chunk.encode("utf-8")).hexdigest()[:10]
    return (img_dir / f"scene_{index:02d}_{digest}.png",
            img_dir / f"scene_{index:02d}_{digest}.json")


def generate_image(client, prompt: str, out_path) -> bool:
    if not prompt:
        return False
    data = llm.generate_image_bytes(client, prompt + IMAGE_STYLE_SUFFIX)
    if not data:
        return False
    out_path.write_bytes(data)
    return True


def build_sections(client, full_text: str, lang: str, img_dir):
    paragraphs = split_into_paragraphs(full_text)
    chunks = chunk_text_by_target_pages(paragraphs)
    sections = []
    total = len(chunks)
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
        })
    return sections
