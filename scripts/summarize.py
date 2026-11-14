# -*- coding: utf-8 -*-
"""
summarize.py
------------
خلاصه‌سازیِ ادبیِ متن با همان مدلِ متنیِ Gemini و به نسبتِ درصدیِ دلخواه.

هدف، «خلاصهٔ فهرست‌وار» نیست: متن باید مثل یک روایتِ پیوسته خوانده شود،
صحنه‌های کلیدی و ترتیبِ رویدادها بمانند و فقط طول کم شود. هر بخش از متن
جداگانه بازنویسی می‌شود تا محدودیتِ پنجرهٔ مدل رعایت شود و اگر مدل جایی
شکست خورد، همان بخش با متنِ اصلی جایش پر شود (کتاب نباید نیمه‌کاره بماند).
"""

import re

import llm

PROMPT = """تو یک ویراستارِ ادبیِ حرفه‌ای هستی.
متنِ زیر بخشی از یک کتاب است. آن را به زبان <<LANG>> بازنویسی کن، به اندازهٔ
حدود <<PERCENT>> درصدِ طولِ فعلی (یعنی نزدیک به <<TARGET>> نویسه)، بی‌هیچ
مقدمه یا توضیح.

قواعد:
- خروجی باید روایتِ پیوسته و خوانا باشد، نه فهرستِ نکته‌ها و نه تحلیل.
- صحنه‌های کلیدی، شخصیت‌ها، گفت‌وگوهای مهم و ترتیبِ رویدادها حفظ شوند.
- جمله‌های ادبیِ درخشان را تا جای ممکن با کمترین تغییر نگه دار.
- چیزی از خودت اضافه نکن؛ تنها فشرده کن.
- بخش را طبیعی شروع و تمام کن (با «در این بخش…» یا «خلاصه اینکه…» شروع نکن).

متن:
---
<<CHUNK>>
---
"""


def _lang_name(lang: str) -> str:
    return "فارسی" if lang == "fa" else "English"


def clamp_percent(value) -> int:
    """درصد را در بازهٔ امنِ ۰ تا ۹۵ نگه می‌دارد (۱۰۰ = بدون خلاصه)."""
    try:
        percent = int(float(value))
    except (TypeError, ValueError):
        return 0
    if percent <= 0:
        return 0
    return min(95, percent)


def split_for_summary(text: str, limit: int = 9000):
    """متن را به تکه‌های حداکثر `limit` نویسه‌ای می‌شکند، روی مرز پاراگراف."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]
    chunks, buf, size = [], [], 0
    for paragraph in paragraphs:
        pieces = []
        rest = paragraph
        while len(rest) > limit:
            cut = rest.rfind(" ", 0, limit + 1)
            if cut <= 0:
                cut = limit
            pieces.append(rest[:cut].rstrip())
            rest = rest[cut:].lstrip()
        if rest:
            pieces.append(rest)
        for piece in pieces:
            if buf and size + len(piece) > limit:
                chunks.append("\n\n".join(buf))
                buf, size = [], 0
            buf.append(piece)
            size += len(piece)
    if buf:
        chunks.append("\n\n".join(buf))
    return chunks


def summarize_text(client, text: str, percent, lang: str, *,
                   model_name: str = "", budget_s: float = 240.0) -> str:
    """
    متن را به حدودِ `percent` درصدِ طولش فشرده می‌کند و برمی‌گرداند.

    percent ≤ 0 یا ≥ 100 → متن دست‌نخورده. خطا در هر تکه → همان تکه‌ی اصلی.
    """
    ratio = clamp_percent(percent)
    if ratio <= 0 or not (text or "").strip():
        return text

    chunks = split_for_summary(text)
    if not chunks:
        return text

    models = llm.text_models(model_name)
    out = []
    for index, chunk in enumerate(chunks, 1):
        target = max(200, int(len(chunk) * ratio / 100))
        prompt = (PROMPT.replace("<<LANG>>", _lang_name(lang))
                        .replace("<<PERCENT>>", str(ratio))
                        .replace("<<TARGET>>", str(target))
                        .replace("<<CHUNK>>", chunk))
        try:
            shortened = llm.generate_text(client, models, prompt,
                                          budget_s=budget_s).strip()
        except Exception as exc:
            print(f"هشدار: خلاصه‌سازیِ تکهٔ {index} ناموفق بود "
                  f"({type(exc).__name__}: {exc})؛ متنِ اصلی همین تکه استفاده می‌شود.")
            shortened = ""
        out.append(shortened or chunk)
        print(f"  خلاصه‌سازی تکه {index}/{len(chunks)} "
              f"({len(chunk):,} → {len(out[-1]):,} نویسه)")
    return "\n\n".join(out)
