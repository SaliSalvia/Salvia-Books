# -*- coding: utf-8 -*-
"""
free_image.py
--------------
تصویرسازیِ **رایگان** با Cloudflare Workers AI (مدلِ FLUX.1 [schnell]).

چرا این فایل وجود دارد: مدل‌های تصویریِ Gemini در پلنِ رایگانِ Google AI Studio
در دسترس نیستند (خودِ گوگل در صفحه‌ی قیمت‌گذاری، ستونِ Free Tier را برای آن‌ها
«Not available» زده است). Cloudflare Workers AI رویِ پلنِ رایگانش روزی
۱۰٬۰۰۰ neuron می‌دهد — با FLUX.1 schnell این تقریباً ۵۰ تا ۲۳۰ تصویر در روز
است، یعنی بیش از اندازه‌ی یک کتاب در روز.

کلیدها فقط از محیط خوانده می‌شوند و هیچ‌وقت چاپ/ذخیره نمی‌شوند:
    CLOUDFLARE_ACCOUNT_ID
    CLOUDFLARE_API_TOKEN
اختیاری:
    CLOUDFLARE_IMAGE_MODEL   (پیش‌فرض @cf/black-forest-labs/flux-1-schnell)
    CLOUDFLARE_IMAGE_STEPS   (۱ تا ۸، پیش‌فرض ۴ — بیشتر = کیفیت بالاتر و کندتر)
"""

import base64
import os
import random
import time

import requests

API_ROOT = ("https://api.cloudflare.com/client/v4/accounts/"
            "{account}/ai/run/{model}")
DEFAULT_MODEL = "@cf/black-forest-labs/flux-1-schnell"

# خطاهایی که ارزش تلاشِ دوباره دارند
RETRYABLE_STATUSES = {408, 425, 429, 500, 502, 503, 504}


_discovered_account = ""


def account_id() -> str:
    """
    شناسهٔ حساب: از محیط، و اگر نبود با همان توکن از `/accounts` کشف می‌شود
    (تا کاربر لازم نباشد برای گرفتنِ یک کتاب، دو مقدار را دستی وارد کند).
    """
    global _discovered_account
    raw = (os.getenv("CLOUDFLARE_ACCOUNT_ID") or "").strip()
    if raw:
        return raw
    if _discovered_account:
        return _discovered_account
    token = api_token()
    if not token:
        return ""
    try:
        resp = requests.get(
            "https://api.cloudflare.com/client/v4/accounts",
            headers={"Authorization": f"Bearer {token}"}, timeout=20)
        if resp.status_code == 200:
            accounts = (resp.json() or {}).get("result") or []
            for account in accounts:
                found = str((account or {}).get("id") or "").strip()
                if found:
                    _discovered_account = found
                    print(f"شناسهٔ حساب Cloudflare خودکار پیدا شد ({found[:6]}…).")
                    return found
    except (requests.RequestException, ValueError):
        pass
    return ""


def api_token() -> str:
    return (os.getenv("CLOUDFLARE_API_TOKEN") or "").strip()


def model_name() -> str:
    return ((os.getenv("CLOUDFLARE_IMAGE_MODEL") or "").strip()
            or DEFAULT_MODEL)


def steps() -> int:
    raw = (os.getenv("CLOUDFLARE_IMAGE_STEPS") or "").strip()
    try:
        return max(1, min(8, int(raw))) if raw else 4
    except ValueError:
        return 4


def _fit_prompt(prompt: str, limit: int = 2000) -> str:
    """
    پرامپت را در سقفِ مجازِ مدل نگه می‌دارد، ولی **انتها** را حفظ می‌کند:
    امضای سبکِ سینمایی در آخرِ پرامپت است و نباید قربانیِ برش شود.
    """
    prompt = (prompt or "").strip()
    if len(prompt) <= limit:
        return prompt
    tail = 600
    head = limit - tail
    return prompt[:head].rstrip(" ,;") + " " + prompt[-tail:].lstrip(" ,;")


def is_configured() -> bool:
    """آیا هر دو کلید لازم برای بک‌اندِ رایگان حاضرند؟"""
    return bool(account_id() and api_token())


def generate_image_bytes(prompt: str, *, max_attempts: int = 3,
                         budget_s: float = 240.0) -> bytes | None:
    """
    یک تصویر می‌سازد و بایت‌هایش را برمی‌گرداند؛ در هر شکستی `None`
    (شکستِ تصویر نباید کل کتاب را بکُشد).

    خطاهای موقت (429/5xx/شبکه) با backoff نمایی تکرار می‌شوند.
    """
    if not prompt:
        return None
    if not is_configured():
        return None

    url = API_ROOT.format(account=account_id(), model=model_name())
    payload = {"prompt": _fit_prompt(prompt), "steps": steps()}
    headers = {
        "Authorization": f"Bearer {api_token()}",
        "Content-Type": "application/json",
    }

    started = time.monotonic()
    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=120)
        except requests.RequestException as exc:
            if attempt >= max_attempts:
                print(f"هشدار: اتصال به Cloudflare برقرار نشد: {exc}")
                return None
            delay = min(30.0, 2.0 ** attempt) + random.uniform(0, 1.0)
            print(f"    خطای شبکه در تصویرسازی؛ تلاش {attempt + 1} پس از "
                  f"{delay:.0f}s ...")
            time.sleep(delay)
            continue

        if resp.status_code in RETRYABLE_STATUSES:
            delay = min(60.0, 2.0 ** attempt) + random.uniform(0, 1.0)
            if (attempt >= max_attempts
                    or time.monotonic() - started + delay > budget_s):
                print(f"هشدار: Cloudflare خطای {resp.status_code} داد؛ "
                      f"تصویر ساخته نشد.")
                return None
            print(f"    Cloudflare خطای {resp.status_code} داد؛ تلاش "
                  f"{attempt + 1} پس از {delay:.0f}s ...")
            time.sleep(delay)
            continue

        if resp.status_code >= 400:
            detail = ""
            try:
                errors = (resp.json() or {}).get("errors") or []
                if errors:
                    detail = str(errors[0].get("message") or "")[:200]
            except ValueError:
                pass
            print(f"هشدار: Cloudflare درخواست را رد کرد "
                  f"({resp.status_code}{(': ' + detail) if detail else ''}).")
            return None

        try:
            body = resp.json()
        except ValueError:
            print("هشدار: پاسخِ Cloudflare JSON نبود.")
            return None

        data = ((body or {}).get("result") or {}).get("image")
        if not data:
            print("هشدار: Cloudflare تصویری برنگرداند.")
            return None
        try:
            return base64.b64decode(data)
        except (ValueError, TypeError):
            print("هشدار: تصویرِ برگشتی از Cloudflare قابلِ خواندن نبود.")
            return None

    return None
