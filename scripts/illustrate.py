# -*- coding: utf-8 -*-
"""
illustrate.py
--------------
تقسیم متن به بخش‌های متناسب با طول کتاب (هر ۶ تا ۱۱ صفحه یک تصویر)،
تحلیل هر بخش با Gemini برای ساخت عنوان/کپشن/پرامپت تصویری، و تولید
تصویر با مدل تصویرسازیِ همان API.
"""

import json
import random
import re

TEXT_MODEL = "gemini-2.5-flash"
IMAGE_MODEL = "gemini-2.5-flash-image"

CHARS_PER_PAGE = 950  # با فونت بزرگ‌شده و صفحه‌ی عمودی
MIN_PAGES_PER_IMAGE = 6
MAX_PAGES_PER_IMAGE = 11

IMAGE_STYLE_SUFFIX = (
    ", cinematic warm painterly illustration, soft golden lighting, "
    "dreamlike storybook atmosphere, highly detailed, no text, no watermark"
)

ANALYSIS_PROMPT = """
تو یک ویراستار هنری کتاب هستی. زبان خروجی متنی باید {lang_name} باشد.
برای بخشی از یک کتاب که به تو داده می‌شود، فقط یک JSON خام با این ساختار
دقیق برگردان (بدون هیچ متن اضافه):

{{
  "chapter_title": "عنوان کوتاه و ادبی این بخش، به زبان {lang_name}",
  "chapter_kicker": "یک زیرعنوان کوتاه انگلیسی با حروف بزرگ، حداکثر ۵ کلمه",
  "caption": "یک پاراگراف کوتاه (۲ تا ۳ جمله)، اتمسفریک و ادبی به زبان {lang_name}، که فضای این بخش را توصیف می‌کند (بازنویسی خلاقانه، نه رونویسی مستقیم از متن)",
  "image_prompt_en": "یک پرامپت تصویرسازی مفصل به انگلیسی برای مدل تولید تصویر، که مهم‌ترین و پرپتانسیل‌ترین صحنه‌ی این بخش را توصیف می‌کند"
}}

متن بخش کتاب:
---
{chunk}
---
"""

BLURB_PROMPT = """
یک توضیحِ تک‌جمله‌ای، زیبا و ادبی (حداکثر ۲۵ کلمه) به زبان {lang_name}
برای معرفی این کتاب روی جلد بنویس. فقط همان یک جمله را برگردان، بدون
گیومه و بدون توضیح اضافه.

عنوان کتاب: {title}
نویسنده: {author}
ابتدای متن کتاب (برای فهم فضا):
---
{sample}
---
"""


def split_into_paragraphs(text: str):
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def chunk_text_by_target_pages(paragraphs):
    chunks = []
    current, current_len = [], 0
    target = random.randint(MIN_PAGES_PER_IMAGE, MAX_PAGES_PER_IMAGE) * CHARS_PER_PAGE
    for p in paragraphs:
        current.append(p)
        current_len += len(p)
        if current_len >= target:
            chunks.append("\n\n".join(current))
            current, current_len = [], 0
            target = random.randint(MIN_PAGES_PER_IMAGE, MAX_PAGES_PER_IMAGE) * CHARS_PER_PAGE
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def _lang_name(lang: str) -> str:
    return "فارسی" if lang == "fa" else "English"


def generate_blurb(client, title: str, author: str, sample_text: str, lang: str) -> str:
    prompt = BLURB_PROMPT.format(
        lang_name=_lang_name(lang), title=title, author=author or "",
        sample=sample_text[:1500],
    )
    resp = client.models.generate_content(model=TEXT_MODEL, contents=prompt)
    return resp.text.strip().strip('"').strip("«»")


def analyze_chunk(client, chunk: str, lang: str) -> dict:
    prompt = ANALYSIS_PROMPT.format(lang_name=_lang_name(lang), chunk=chunk[:6000])
    resp = client.models.generate_content(model=TEXT_MODEL, contents=prompt)
    raw = re.sub(r"^```(json)?|```$", "", resp.text.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {
            "chapter_title": "",
            "chapter_kicker": "",
            "caption": chunk[:200],
            "image_prompt_en": f"An atmospheric literary illustration inspired by: {chunk[:300]}",
        }


def generate_image(client, prompt: str, out_path):
    full_prompt = prompt + IMAGE_STYLE_SUFFIX
    resp = client.models.generate_content(model=IMAGE_MODEL, contents=full_prompt)
    for part in resp.candidates[0].content.parts:
        if part.inline_data is not None:
            out_path.write_bytes(part.inline_data.data)
            return True
    return False


def build_sections(client, full_text: str, lang: str, img_dir):
    paragraphs = split_into_paragraphs(full_text)
    chunks = chunk_text_by_target_pages(paragraphs)
    sections = []
    for i, chunk in enumerate(chunks, start=1):
        print(f"[{i}/{len(chunks)}] تحلیل بخش با Gemini ...")
        meta = analyze_chunk(client, chunk, lang)

        img_path = img_dir / f"scene_{i:02d}.png"
        print(f"[{i}/{len(chunks)}] تولید تصویر ...")
        ok = generate_image(client, meta.get("image_prompt_en", ""), img_path)

        sections.append({
            "paragraphs": split_into_paragraphs(chunk),
            "chapter_title": meta.get("chapter_title", ""),
            "chapter_kicker": meta.get("chapter_kicker", f"PLATE {i}"),
            "caption": meta.get("caption", ""),
            "image_path": img_path if ok else None,
        })
    return sections
