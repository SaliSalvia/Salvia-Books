# -*- coding: utf-8 -*-
"""
conftest.py — فیکسچرهای مشترک تست‌ها.

پوشه‌ی scripts/ به sys.path اضافه می‌شود تا ماژول‌ها همان‌طور import
شوند که workflow آن‌ها را با working-directory=scripts اجرا می‌کند.

کلاینِ جعلیِ اینجا کاملاً سازگار با google.genai است (models.generate_content)
و بر اساس محتوای پرامپت، پاسخِ مناسب هر مرحله را برمی‌گرداند — یعنی کل خط
تولید بدون هیچ کلید API و بدون شبکه قابل اجرا و تست است.
"""

import base64
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

# یک PNG کوچک (نگین‌جان) برای شبیه‌سازی خروجی مدل تصویری
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
    "AAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def text_response(text: str):
    return SimpleNamespace(text=text, candidates=[])


def image_response(data: bytes = PNG_BYTES):
    part = SimpleNamespace(text=None, inline_data=SimpleNamespace(data=data))
    cand = SimpleNamespace(content=SimpleNamespace(parts=[part]))
    return SimpleNamespace(text="", candidates=[cand])


def default_handler(contents: str, config):
    """بر اساس پرامپت، پاسخِ مناسب هر مرحله را می‌سازد."""
    if config is not None and getattr(config, "response_modalities", None):
        return image_response()
    if "gutenberg_query" in contents:  # نرمال‌سازی عنوان
        m = re.search(r'نام کتاب: "(.*?)"', contents)
        title = m.group(1) if m else "A Book"
        return text_response(json.dumps({
            "title_en": title, "title_fa": title, "author": "Test Author",
            "gutenberg_query": title,
        }, ensure_ascii=False))
    if '"verdict"' in contents:  # داوری متن
        return text_response(
            '{"verdict": "yes", "reason": "متن با کتاب مطابقت دارد"}')
    if "chapter_title" in contents:  # تحلیل بخش
        return text_response(json.dumps({
            "chapter_title": "عنوان آزمایشی بخش",
            "chapter_kicker": "TEST PLATE",
            "caption": "کپشن آزمایشی این بخش.",
            "image_prompt_en": "a test scene, painterly, no text",
        }, ensure_ascii=False))
    if "تک‌جمله" in contents or "جلد" in contents:  # توضیح جلد
        return text_response("توضیحِ جلدِ آزمایشی برای تست.")
    if "ترجمه" in contents:  # ترجمه
        return text_response("متنِ ترجمه‌شده‌ی آزمایشی این بخش.")
    return text_response("پاسخِ متنیِ آزمایشی.")


class ScriptedClient:
    """کلاینِ جعلیِ سازگار با google.genai؛ همه‌ی فراخوانی‌ها ثبت می‌شوند."""

    def __init__(self, handler=None):
        self.calls = []
        self._handler = handler or default_handler
        self.models = SimpleNamespace(generate_content=self._generate)

    def _generate(self, model=None, contents=None, config=None):
        self.calls.append({"model": model, "contents": contents or "",
                           "config": config})
        return self._handler(contents or "", config)

    def contents_matching(self, needle: str):
        return [c for c in self.calls if needle in c["contents"]]

    def image_calls(self):
        return [c for c in self.calls
                if c["config"] is not None
                and getattr(c["config"], "response_modalities", None)]


@pytest.fixture
def fake_client():
    return ScriptedClient()
