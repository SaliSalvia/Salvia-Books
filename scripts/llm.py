# -*- coding: utf-8 -*-
"""
llm.py
------
لایه‌ی مشترک فراخوانی مدل‌های Gemini برای کل خط تولید:

* تلاش مجدد با backoff نمایی و jitter برای خطاهای موقت (شبکه، 429، 5xx)
* زنجیره‌ی مدل‌های جایگزین وقتی مدلی برای این حساب در دسترس نیست (404)
* پارس امن JSON از خروجی مدل‌ها (حتی وقتی داخل markdown یا متن اضافه باشد)

هیچ وابستگی جدیدی لازم ندارد؛ فقط google-genai.
"""

import json
import os
import random
import re
import time

from google.genai import errors as genai_errors
from google.genai import types

# زنجیره‌ی پیشنهادی مدل‌های متنی/تصویری. اگر مدل اول در دسترس نباشد
# (تغییر نام، سهمیه، دسترسی حساب) به مدل بعدی سقوط می‌کنیم تا اجرای CI
# به‌خاطر نام مدل نُمیرد. با GEMINI_TEXT_MODEL / GEMINI_IMAGE_MODEL قابل
# بازنویسی است.
DEFAULT_TEXT_MODELS = (
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-2.5-flash",
)
DEFAULT_IMAGE_MODELS = (
    "gemini-nano-banana-2.1",
    "gemini-3.1-flash-image",
    "gemini-2.5-flash-image",
)

JSON_CONFIG = types.GenerateContentConfig(response_mime_type="application/json")
IMAGE_CONFIG = types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"])

# خطاهایی که ارزش تلاش مجدد دارند
RETRYABLE_STATUSES = {408, 429, 500, 502, 503, 504, 529}


class ModelNotAvailable(Exception):
    """مدلِ انتخاب‌شده برای این کلید در دسترس نیست (معمولاً 404)."""


def text_models(hint=None):
    """زنجیره‌ی مدل‌های متنی؛ نامِ هینت (env یا کد) اول است."""
    hint = (hint or os.getenv("GEMINI_TEXT_MODEL") or "").strip()
    chain = ([hint] if hint else []) + list(DEFAULT_TEXT_MODELS)
    return list(dict.fromkeys(chain))


def image_models(hint=None):
    """زنجیره‌ی مدل‌های تصویری؛ نامِ هینت (env یا کد) اول است."""
    hint = (hint or os.getenv("GEMINI_IMAGE_MODEL") or "").strip()
    chain = ([hint] if hint else []) + list(DEFAULT_IMAGE_MODELS)
    return list(dict.fromkeys(chain))


def _http_status(exc):
    code = getattr(exc, "code", None)
    if isinstance(code, int):
        return code
    m = re.match(r"\s*(\d{3})\b", str(exc))
    return int(m.group(1)) if m else None


def _is_retryable(exc):
    status = _http_status(exc)
    if status is not None:
        return status in RETRYABLE_STATUSES
    # خطاهای اتصال/شبکه (httpx و غیره) بدون کد HTTP می‌آیند
    module = type(exc).__module__ or ""
    if module.startswith("httpx") or module.startswith("requests"):
        return True
    if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        return True
    if isinstance(exc, genai_errors.APIError):
        return True
    return False


def _is_model_missing(exc):
    status = _http_status(exc)
    if status == 404:
        return True
    if status == 400 and "model" in str(exc).lower():
        return True
    return False


def _generate_raw(client, models, contents, *, config=None,
                  max_attempts=5, budget_s=300.0):
    """فراخوانی با تلاش مجدد؛ فقط خطاهای مدلِ ناموجود زنجیره را جلو می‌برد."""
    last_missing = None
    for model in models:
        attempt, started = 0, time.monotonic()
        while True:
            attempt += 1
            try:
                return client.models.generate_content(
                    model=model, contents=contents, config=config
                )
            except Exception as exc:
                if _is_model_missing(exc):
                    last_missing = exc
                    print(f"مدل «{model}» در دسترس نیست؛ تلاش با مدل بعدی زنجیره ...")
                    break  # مدل بعدی
                delay = min(60.0, 2.0 ** attempt) + random.uniform(0, 1.0)
                if (attempt >= max_attempts
                        or time.monotonic() - started + delay > budget_s
                        or not _is_retryable(exc)):
                    raise
                print(f"    خطای موقت [{_http_status(exc) or type(exc).__name__}] "
                      f"روی «{model}»؛ تلاش {attempt}/{max_attempts}، "
                      f"تأخیر {delay:.1f}s")
                time.sleep(delay)
    raise ModelNotAvailable(
        f"هیچ‌کدام از مدل‌های زنجیره در دسترس نیستند: {list(models)}"
    ) from last_missing


def response_text(resp):
    """متن خروجی یک پاسخ، مقاوم در برابر پارت‌های چندتایه."""
    try:
        txt = getattr(resp, "text", None)
        if txt:
            return txt.strip()
    except Exception:
        pass
    parts = []
    for cand in getattr(resp, "candidates", None) or []:
        content = getattr(cand, "content", None)
        for p in getattr(content, "parts", None) or []:
            if getattr(p, "text", None):
                parts.append(p.text)
    return "\n".join(parts).strip()


def extract_json(text):
    """استخراج اولین شیء JSON معتبر از خروجی مدل (حتی داخل markdown)."""
    if not text:
        return None
    t = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE).strip()
    start, end = t.find("{"), t.rfind("}")
    candidates = [t[start:end + 1]] if start != -1 and end > start else []
    candidates.append(t)
    for cand in candidates:
        if not cand:
            continue
        try:
            obj = json.loads(cand)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(obj, dict):
            return obj
    return None


def generate_text(client, models, contents, *, max_attempts=5, budget_s=300.0):
    """متن ساده از مدل (ترجمه، کپشن و ...) با تلاش مجدد."""
    resp = _generate_raw(client, models, contents, config=None,
                         max_attempts=max_attempts, budget_s=budget_s)
    return response_text(resp)


def generate_json(client, models, contents, *, max_attempts=4, budget_s=300.0):
    """JSON از مدل؛ اگر با mime_type هم خروجی خراب بود، یک بار بدون آن می‌گیریم."""
    resp = _generate_raw(client, models, contents, config=JSON_CONFIG,
                         max_attempts=max_attempts, budget_s=budget_s)
    obj = extract_json(response_text(resp))
    if obj is not None:
        return obj
    resp = _generate_raw(client, models, contents, config=None,
                         max_attempts=max_attempts, budget_s=budget_s)
    return extract_json(response_text(resp))


def resp_parts(resp):
    """همه‌ی پارت‌های پاسخ (candidates یا خودِ resp)."""
    parts = []
    for cand in getattr(resp, "candidates", None) or []:
        content = getattr(cand, "content", None)
        for p in getattr(content, "parts", None) or []:
            parts.append(p)
    if not parts:
        for p in getattr(resp, "parts", None) or []:
            parts.append(p)
    return parts


def generate_image_bytes(client, prompt, models=None, *, max_attempts=4,
                         budget_s=300.0):
    """
    تولید تصویر با زنجیره‌ی مدل‌های تصویری. شکستِ تصویر هرگز نباید کل کتاب
    را بکُشد، پس: خطای مدلِ ناموجود → مدل بعدی؛ خطای نهایی → چاپ دلیل و None.
    """
    chain = list(models) if models else image_models()
    for model in chain:
        try:
            resp = _generate_raw(
                client, [model], prompt, config=IMAGE_CONFIG,
                max_attempts=max_attempts, budget_s=budget_s,
            )
        except ModelNotAvailable as exc:
            print(f"مدل تصویر «{model}» در دسترس نیست ({exc})")
            continue
        except Exception as exc:
            print(f"تولید تصویر با «{model}» شکست خورد: {type(exc).__name__}: {exc}")
            continue
        for part in resp_parts(resp):
            inline = getattr(part, "inline_data", None)
            if inline is not None and getattr(inline, "data", None):
                data = inline.data
                if isinstance(data, (bytearray, memoryview)):
                    data = bytes(data)
                if data:
                    return bytes(data)
        print(f"مدل «{model}» تصویری برنگرداند (فقط متن/خالی).")
    return None
