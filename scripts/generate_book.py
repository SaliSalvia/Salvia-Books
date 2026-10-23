#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_book.py
-----------------
اجرای کامل خط تولید: نام کتاب → متن آزاد/دستی → تحلیل و تصویرسازی → PDF نهایی.

ورودی فقط دو چیز است: **نام کتاب** و **کلید API**. زبانِ کتاب خودکار تشخیص
داده می‌شود (فارسی یا انگلیسی)؛ PNG/لوگو/مسیر خروجی هم پیش‌فرض دارند.

اجرا:
    python scripts/generate_book.py --title "شازده کوچولو" --api-key "..."
    GEMINI_API_KEY=... python scripts/generate_book.py --title "Pride and Prejudice"

کلید از آرگومان --api-key یا (ترجیحاً) متغیر محیطی GEMINI_API_KEY خوانده می‌شود.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

from google import genai

from text_source import (get_source_text, guess_lang, ManualTextRequired,
                         slugify)
from illustrate import build_sections, generate_blurb
import render

REPO_ROOT = Path(__file__).resolve().parent.parent


def _render_pdf(*, workdir, out_dir, slug, lang, title, author, blurb, sections,
                logo_uri, github_url):
    """
    HTML/PDF را می‌سازد و اگر صفحه‌ای سرریز کرده باشد، با سقفِ کمتری دوباره
    صفحه‌بندی می‌کند. خروجی: (مسیر PDF، نقشه‌ی صفحه‌ها، صفحه‌های سرریز).
    """
    html_path = workdir / "book.html"
    pdf_path = out_dir / f"{slug}-{lang}.pdf"
    metadata = {
        "/Title": title,
        "/Author": author or "",
        "/Subject": blurb or "",
        "/Keywords": ", ".join(k for k in (title, author, "visual edition") if k),
        "/Creator": "Salvia Visual Book Engine",
        "/Producer": "Salvia Visual Book Engine",
        "/Lang": lang,
    }

    layout, overflow = None, []
    line_cap = render.line_cap_for(lang, 0)
    contents_rows = None
    for attempt in range(render.MAX_ATTEMPTS):
        layout = render.render_book_html(
            lang=lang, title=title, author=author, blurb=blurb,
            sections=sections, logo_uri=logo_uri, github_url=github_url,
            out_html_path=html_path, line_cap=line_cap,
            contents_rows=contents_rows,
        )
        overflow = render.html_to_pdf(html_path, pdf_path,
                                      metadata=metadata,
                                      outline=layout.get("outline"))
        if not overflow:
            break
        # دو نوع سرریز داریم و درمانِ هرکدام فرق دارد: صفحه‌های مقدمه (فهرست)
        # با ردیفِ کمتر درست می‌شوند، صفحه‌های بدنه با خطِ کمتر. اگر فهرست را
        # با کم‌کردنِ خطِ بدنه «درمان» کنیم، فقط کاغذ هدر می‌رود.
        front_pages = layout.get("contents_page_count", 0) + 1
        front = [p for p in overflow if p <= front_pages]
        body = [p for p in overflow if p > front_pages]
        if front:
            contents_rows = max(3, int((contents_rows or
                                        layout.get("contents_rows", 5)) * 0.7))
            print(f"هشدار: {len(front)} صفحه‌ی فهرست سرریز کرد؛ "
                  f"فهرست با {contents_rows} ردیف در صفحه دوباره چیده می‌شود "
                  f"(تلاش {attempt + 1}/{render.MAX_ATTEMPTS}).")
        if body:
            line_cap = max(6, line_cap - render.LINE_STEP_DOWN)
            print(f"هشدار: {len(body)} صفحه‌ی متن سرریز کرد؛ "
                  f"صفحه‌بندی با {line_cap} خط دوباره انجام می‌شود "
                  f"(تلاش {attempt + 1}/{render.MAX_ATTEMPTS}).")
    if overflow:
        print(f"هشدار: هنوز {len(overflow)} صفحه سرریز دارد: {overflow}")
    return pdf_path, layout, overflow


def main():
    parser = argparse.ArgumentParser(
        description="ساخت کتاب تصویریِ PDF از نامِ کتاب و کلید Gemini.")
    parser.add_argument("--title", required=True, help="نام کتاب (هر زبانی)")
    parser.add_argument("--api-key", default="",
                        help="کلید Gemini؛ اگر خالی بماند از GEMINI_API_KEY خوانده می‌شود")
    parser.add_argument("--lang", choices=["auto", "fa", "en"], default="auto",
                        help="زبان خروجی؛ پیش‌فرض auto (از خودِ متن تشخیص داده می‌شود)")
    parser.add_argument("--github-url", default="https://github.com/")
    parser.add_argument("--logo", default=str(REPO_ROOT / "assets" / "logo.png"))
    parser.add_argument("--output-dir", default=str(REPO_ROOT / "output"))
    args = parser.parse_args()

    api_key = (args.api_key or "").strip() or os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        parser.error("--api-key خالی است و متغیر محیطی GEMINI_API_KEY هم تنظیم نشده.")
    if not args.title.strip():
        parser.error("--title نمی‌تواند خالی باشد.")

    started = time.monotonic()
    client = genai.Client(api_key=api_key)

    workdir = REPO_ROOT / "_build" / slugify(args.title)
    img_dir = workdir / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    manuscripts_dir = REPO_ROOT / "manuscripts"
    manuscripts_dir.mkdir(exist_ok=True)

    lang_hint = "تشخیص خودکار" if args.lang == "auto" else args.lang
    print(f"== مرحله ۱: پیدا کردن متن برای «{args.title.strip()}» (زبان: {lang_hint}) ==")
    try:
        text, norm, meta = get_source_text(
            client, None, args.title.strip(), args.lang, manuscripts_dir
        )
    except ManualTextRequired as e:
        print("\n❌ " + str(e), file=sys.stderr)
        sys.exit(2)

    lang = meta.get("lang") or (args.lang if args.lang in ("fa", "en")
                                else guess_lang(text))
    print(f"منبع متن: {meta}")
    print(f"زبانِ نهاییِ کتاب: {lang} | طولِ متن: {len(text):,} نویسه")

    title_display = (norm.get("title_fa") if lang == "fa" else norm.get("title_en")) \
        or args.title.strip()
    author = norm.get("author", "")

    print("== مرحله ۲: نوشتن توضیح جلد ==")
    blurb = generate_blurb(client, title_display, author, text[:2000], lang)

    print("== مرحله ۳: تحلیل بخش‌ها و تولید تصاویر ==")
    sections = build_sections(client, text, lang, img_dir)
    n_images = sum(1 for s in sections if s.get("image_path"))
    print(f"تعداد بخش‌ها: {len(sections)} | تصاویر تولیدشده: {n_images}")
    if sections and n_images < len(sections):
        print(f"هشدار: {len(sections) - n_images} بخش بدون تصویر ماند "
              f"(صفحه‌ی جای‌گذار با همان کپشن چاپ می‌شود).")

    print("== مرحله ۴: ساخت HTML و PDF ==")
    logo_path = Path(args.logo)
    if logo_path.is_file():
        logo_uri = logo_path.resolve().as_uri()
    else:
        print(f"هشدار: لوگو پیدا نشد ({logo_path})؛ کتاب بدون لوگو ساخته می‌شود.")
        logo_uri = ""

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = slugify(norm.get("title_en") or args.title)

    pdf_path, layout, overflow = _render_pdf(
        workdir=workdir, out_dir=out_dir, slug=slug, lang=lang,
        title=title_display, author=author, blurb=blurb, sections=sections,
        logo_uri=logo_uri, github_url=args.github_url,
    )

    report = {
        "title": title_display,
        "author": author,
        "lang": lang,
        "source": meta.get("source"),
        "translated": bool(meta.get("translated")),
        "characters": len(text),
        "sections": len(sections),
        "images": n_images,
        "pages": layout.get("page_count"),
        "line_cap": layout.get("line_cap"),
        "max_chars": layout.get("max_chars"),
        "overflow_pages": overflow,
        "pdf": str(pdf_path),
        "elapsed_s": int(time.monotonic() - started),
    }
    (workdir / "layout.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n✅ تمام شد ({report['elapsed_s']}s): {pdf_path}")
    print(f"   {report['pages']} صفحه | {report['sections']} بخش | "
          f"{report['images']} تصویر")


if __name__ == "__main__":
    main()
