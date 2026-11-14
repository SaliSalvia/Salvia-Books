# -*- coding: utf-8 -*-
"""
تست‌های بک‌اندِ تصویرسازیِ رایگان (Cloudflare Workers AI) و انتخابِ موتور
تصویرسازی — همه بدونِ شبکه و بدونِ کلید واقعی.
"""

import base64

import pytest

import free_image
import illustrate
import llm
from conftest import PNG_BYTES, ScriptedClient, text_response


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


@pytest.fixture
def cf_env(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acc-123")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok-456")
    monkeypatch.setattr(free_image.time, "sleep", lambda s: None)
    return monkeypatch


def test_not_configured_without_keys(monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    assert free_image.is_configured() is False
    # بدون کلید نباید هیچ درخواستی بفرستد
    monkeypatch.setattr(free_image.requests, "post",
                        lambda *a, **k: pytest.fail("نباید درخواست بفرستد"))
    assert free_image.generate_image_bytes("a scene") is None


def test_success_decodes_base64(cf_env):
    seen = {}

    def post(url, json=None, headers=None, timeout=None):
        seen.update(url=url, json=json, headers=headers)
        return FakeResponse(200, {"success": True,
                                  "result": {"image": base64.b64encode(
                                      PNG_BYTES).decode("ascii")}})

    cf_env.setattr(free_image.requests, "post", post)
    out = free_image.generate_image_bytes("a desert at dusk, cinematic")
    assert out == PNG_BYTES
    assert seen["url"].endswith(
        "/accounts/acc-123/ai/run/@cf/black-forest-labs/flux-1-schnell")
    assert seen["headers"]["Authorization"] == "Bearer tok-456"
    assert seen["json"]["steps"] == 4
    assert "cinematic" in seen["json"]["prompt"]


def test_retry_on_rate_limit_then_success(cf_env):
    calls = []

    def post(*a, **k):
        calls.append(1)
        if len(calls) == 1:
            return FakeResponse(429, {"errors": [{"message": "rate limited"}]})
        return FakeResponse(200, {"result": {"image": base64.b64encode(
            PNG_BYTES).decode("ascii")}})

    cf_env.setattr(free_image.requests, "post", post)
    assert free_image.generate_image_bytes("x") == PNG_BYTES
    assert len(calls) == 2


def test_hard_error_returns_none(cf_env):
    cf_env.setattr(free_image.requests, "post", lambda *a, **k: FakeResponse(
        400, {"errors": [{"message": "invalid prompt"}]}))
    assert free_image.generate_image_bytes("x") is None


def test_steps_env_is_clamped(cf_env):
    cf_env.setenv("CLOUDFLARE_IMAGE_STEPS", "99")
    assert free_image.steps() == 8
    cf_env.setenv("CLOUDFLARE_IMAGE_STEPS", "نامعتبر")
    assert free_image.steps() == 4


def test_generate_image_falls_back_to_free_backend(tmp_path, cf_env):
    # کلاینتِ Gemini فقط متن می‌دهد (سهمیه‌ی تصویرِ رایگان وجود ندارد) →
    # باید به Cloudflare سقوط کند و تصویر را بنویسد.
    client = ScriptedClient(lambda c, cfg: text_response("بدون تصویر"))
    cf_env.setattr(illustrate.free_image, "generate_image_bytes",
                   lambda prompt: PNG_BYTES)
    out = tmp_path / "scene.png"
    assert illustrate.generate_image(client, "the little prince in the desert",
                                     out) is True
    assert out.read_bytes() == PNG_BYTES


def test_generate_image_gemini_only_skips_free_backend(tmp_path, cf_env):
    cf_env.setenv("IMAGE_BACKEND", "gemini")
    called = []
    cf_env.setattr(illustrate.free_image, "generate_image_bytes",
                   lambda prompt: called.append(1) or PNG_BYTES)
    client = ScriptedClient(lambda c, cfg: text_response("بدون تصویر"))
    assert illustrate.generate_image(client, "x", tmp_path / "s.png") is False
    assert called == []


def test_style_suffix_requests_cinematic_trailer_without_text():
    suffix = illustrate.IMAGE_STYLE_SUFFIX.lower()
    assert "cinematic" in suffix
    assert "16:9" in suffix
    assert "no text" in suffix
    assert "no watermark" in suffix


def test_analysis_prompt_forces_text_fidelity():
    prompt = illustrate.ANALYSIS_PROMPT
    # پرامپتِ تصویر باید مقید به خودِ متن باشد، نه برداشتِ آزاد
    assert "فقط و فقط بر اساس همین متن" in prompt
    assert "image_prompt_en" in prompt
