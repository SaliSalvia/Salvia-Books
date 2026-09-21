#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_book.py
-----------------
اجرای کامل خط تولید: عنوان کتاب -> متن آزاد/دستی -> تحلیل و تصویرسازی ->
PDF نهایی. این فایل مستقیماً توسط وورکفلوهای GitHub Actions صدا زده می‌شود.

اجرا:
    python scripts/generate_book.py --lang fa --title "شازده کوچولو" \\
        --api-key $GEMINI_API_KEY --github-url "https://github.com/USER/REPO"
"""

import argparse
import sys
from pathlib import Path

from google import genai

from text_source import get_source_text, ManualTextRequired, slugify
from illustrate import TEXT_MODEL, build_sections, generate_blurb
from render import render_book_html, html_to_pdf

REPO_ROOT = Path(__file__).resolve().parent.parent


def _api_error_hint(exc: Exception) -> str:
    message = str(exc).lower()
    if any(token in message for token in ("api key", "api_key", "unauthenticated", "401", "403", "permission denied")):
        return "کلید Gemini نامعتبر است، منقضی شده، یا اجازه‌ی استفاده از مدل را ندارد."
    if any(token in message for token in ("quota", "resource_exhausted", "rate limit", "429", "billing")):
        return "سهمیه یا اعتبار Gemini تمام شده است؛ سهمیه‌ی متن و تصویر و وضعیت Billing را بررسی کنید."
    if any(token in message for token in ("not found", "404", "model")):
        return "مدل در حساب یا منطقه‌ی شما در دسترس نیست؛ دسترسی مدل‌های متنی و تصویری را بررسی کنید."
    if any(token in message for token in ("timeout", "connection", "network", "dns", "503", "unavailable")):
        return "ارتباط با سرویس برقرار نشد؛ وضعیت شبکه یا سرویس Gemini را بررسی و دوباره اجرا کنید."
    if any(token in message for token in ("safety", "blocked", "prohibited", "finish_reason")):
        return "درخواست توسط فیلترهای ایمنی مدل مسدود شده است؛ متن یا پرامپت تصویر را بررسی کنید."
    return "جزئیات فنی خطا را در ادامه‌ی لاگ همین مرحله بررسی کنید."


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lang", choices=["fa", "en"], required=True)
    parser.add_argument("--title", required=True, help="نام کتاب (هر زبانی)")
    parser.add_argument("--author", default="", help="نام نویسنده برای متن ورودی")
    parser.add_argument("--text-file", help="مسیر فایل UTF-8 حاوی متن آماده‌ی کتاب")
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--github-url", default="https://github.com/")
    parser.add_argument("--logo", default=str(REPO_ROOT / "assets" / "logo.png"))
    parser.add_argument("--output-dir", default=str(REPO_ROOT / "output"))
    args = parser.parse_args()

    client = genai.Client(api_key=args.api_key)

    workdir = REPO_ROOT / "_build" / slugify(args.title)
    img_dir = workdir / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    manuscripts_dir = REPO_ROOT / "manuscripts"
    manuscripts_dir.mkdir(exist_ok=True)

    if args.text_file:
        text_path = Path(args.text_file)
        text = text_path.read_text(encoding="utf-8").strip()
        if not text:
            parser.error("فایل متن خالی است")
        norm = {
            "title_en": args.title,
            "title_fa": args.title,
            "author": args.author,
            "gutenberg_query": args.title,
        }
        meta = {"source": "provided_text", "path": str(text_path)}
        print(f"== مرحله ۱: استفاده از متن آماده برای «{args.title}» (زبان خروجی: {args.lang}) ==")
    else:
        print(f"== مرحله ۱: پیدا کردن متن برای «{args.title}» (زبان خروجی: {args.lang}) ==")
        try:
            text, norm, meta = get_source_text(
                client, TEXT_MODEL, args.title, args.lang, manuscripts_dir
            )
        except ManualTextRequired as e:
            print("\n❌ " + str(e), file=sys.stderr)
            sys.exit(2)

    print(f"منبع متن: {meta}")

    title_display = norm["title_fa"] if args.lang == "fa" else norm["title_en"]
    author = norm.get("author", "")

    print("== مرحله ۲: نوشتن توضیح جلد ==")
    blurb = generate_blurb(client, title_display, author, text[:2000], args.lang)

    print("== مرحله ۳: تحلیل بخش‌ها و تولید تصاویر ==")
    sections = build_sections(client, text, args.lang, img_dir)
    print(f"تعداد بخش‌ها/تصاویر: {len(sections)}")

    print("== مرحله ۴: ساخت HTML و PDF ==")
    logo_uri = Path(args.logo).resolve().as_uri()
    html_path = workdir / "book.html"
    render_book_html(
        lang=args.lang, title=title_display, author=author, blurb=blurb,
        sections=sections, logo_uri=logo_uri, github_url=args.github_url,
        out_html_path=html_path,
    )

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = slugify(norm["title_en"] or args.title)
    pdf_path = out_dir / f"{slug}-{args.lang}.pdf"
    html_to_pdf(html_path, pdf_path)

    print(f"\n✅ تمام شد: {pdf_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        hint = _api_error_hint(exc)
        print(f"DIAGNOSTIC: {hint}", file=sys.stderr)
        print(f"TECHNICAL_ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
