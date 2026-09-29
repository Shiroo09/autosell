"""Yapay zekâ sağlayıcılarının istek biçimi ve hata toleransı (gerçek API çağrılmaz)."""

from types import SimpleNamespace

import anthropic
import httpx2
import openai
import pytest

from autosell.ai.anthropic_provider import FALLBACK_BETA, AnthropicProvider
from autosell.ai.base import AINotConfigured, AIRefusal, ImageInput, conform, extract_json
from autosell.ai.openai_provider import OpenAICompatProvider

SCHEMA = {
    "type": "object",
    "properties": {"a": {"type": "string"}, "n": {"type": "number"}},
    "required": ["a", "n"],
    "additionalProperties": False,
}
IMG = ImageInput(media_type="image/jpeg", data_b64="QUJD")


def _msg(text: str = '{"a": "x", "n": 1}', stop: str = "end_turn") -> SimpleNamespace:
    return SimpleNamespace(
        stop_reason=stop,
        stop_details=SimpleNamespace(category="cyber") if stop == "refusal" else None,
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)],
    )


class _Stream:
    def __init__(self, message):
        self.message = message

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self.message


class _FakeAnthropic:
    def __init__(self, *items):
        self.items = list(items)
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **kwargs):
        self.calls.append(kwargs)
        item = self.items.pop(0)
        if isinstance(item, Exception):
            raise item
        return _Stream(item)


def _anthropic_error(cls, status: int, message: str):
    response = httpx2.Response(status, request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))
    return cls(message, response=response, body=None)


def test_claude_request_shape_with_fallback_and_effort():
    fake = _FakeAnthropic(_msg())
    provider = AnthropicProvider(model="claude-opus-5-5", effort="high", client=fake)
    out = provider.generate_json(system="sys", prompt="merhaba", schema=SCHEMA, images=[IMG])
    assert out == {"a": "x", "n": 1}
    call = fake.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["output_config"] == {"format": {"type": "json_schema", "schema": SCHEMA}, "effort": "high"}
    assert call["fallbacks"] == "default" and call["betas"] == [FALLBACK_BETA]
    content = call["messages"][0]["content"]
    assert content[0]["type"] == "image" and content[-1] == {"type": "text", "text": "merhaba"}
    assert "thinking" not in call and "tools" not in call


def test_claude_haiku_skips_effort_and_fallback():
    fake = _FakeAnthropic(_msg())
    AnthropicProvider(model="claude-haiku-4-5", client=fake).generate_json(system="s", prompt="p", schema=SCHEMA)
    call = fake.calls[0]
    assert "effort" not in call["output_config"]
    assert "fallbacks" not in call and call["betas"] == []


def test_claude_web_search_and_pause_turn_continuation():
    fake = _FakeAnthropic(_msg(text="", stop="pause_turn"), _msg())
    provider = AnthropicProvider(model="claude-opus-5-5", client=fake)
    assert provider.generate_json(system="s", prompt="p", schema=SCHEMA, web_search=True)["a"] == "x"
    assert fake.calls[0]["tools"][0]["type"] == "web_search_20260209"
    second = fake.calls[1]["messages"]
    assert second[-1]["role"] == "assistant" and len(second) == 2


def test_claude_refusal_and_errors():
    with pytest.raises(AIRefusal):
        AnthropicProvider(model="claude-opus-5-5", client=_FakeAnthropic(_msg(stop="refusal"))).generate_json(
            system="s", prompt="p", schema=SCHEMA)
    bad = _anthropic_error(anthropic.AuthenticationError, 401, "invalid x-api-key")
    with pytest.raises(AINotConfigured):
        AnthropicProvider(model="claude-opus-5-5", client=_FakeAnthropic(bad)).generate_json(
            system="s", prompt="p", schema=SCHEMA)


def test_claude_retries_without_fallback_when_unsupported():
    err = _anthropic_error(anthropic.BadRequestError, 400, "fallbacks: not enabled for this organization")
    fake = _FakeAnthropic(err, _msg())
    AnthropicProvider(model="claude-opus-5-5", client=fake).generate_json(system="s", prompt="p", schema=SCHEMA)
    assert "fallbacks" in fake.calls[0] and "fallbacks" not in fake.calls[1]
    assert fake.calls[1]["betas"] == []


# ------------------------------------------------------------------ OpenAI uyumlu


def _completion(content: str, refusal=None, finish="stop") -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(finish_reason=finish, message=SimpleNamespace(content=content, refusal=refusal))]
    )


class _FakeOpenAI:
    def __init__(self, *items):
        self.items = list(items)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        item = self.items.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _openai_bad_request(message: str) -> openai.BadRequestError:
    response = httpx2.Response(400, request=httpx2.Request("POST", "https://x/v1/chat/completions"))
    return openai.BadRequestError(message, response=response, body=None)


def test_openai_json_schema_request():
    fake = _FakeOpenAI(_completion('{"a": "y", "n": 2}'))
    provider = OpenAICompatProvider(model="gpt-4.1-mini", base_url="https://api.openai.com/v1", client=fake)
    assert provider.generate_json(system="sys", prompt="p", schema=SCHEMA, images=[IMG]) == {"a": "y", "n": 2}
    call = fake.calls[0]
    assert call["response_format"]["type"] == "json_schema"
    assert call["response_format"]["json_schema"]["strict"] is True
    assert call["messages"][0] == {"role": "system", "content": "sys"}
    parts = call["messages"][1]["content"]
    assert parts[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert call["max_tokens"] == 16000


def test_openai_falls_back_to_json_object_then_text():
    fake = _FakeOpenAI(
        _openai_bad_request("response_format type json_schema is not supported by this server"),
        _openai_bad_request("response_format json_object not supported"),
        _completion('Tabii:\n```json\n{"a": "z", "n": 3}\n```'),
    )
    provider = OpenAICompatProvider(model="llama3.2-vision", base_url="http://localhost:11434/v1", client=fake)
    assert provider.generate_json(system="sys", prompt="p", schema=SCHEMA)["a"] == "z"
    assert fake.calls[1]["response_format"] == {"type": "json_object"}
    assert "response_format" not in fake.calls[2]
    assert "JSON şeması" in fake.calls[2]["messages"][0]["content"]


def test_openai_switches_token_parameter_and_drops_images():
    fake = _FakeOpenAI(
        _openai_bad_request("Unsupported parameter: 'max_tokens' is not supported with this model. "
                            "Use 'max_completion_tokens' instead."),
        _openai_bad_request("This model does not support image_url content"),
        _completion('{"a": "ok", "n": 0}'),
    )
    provider = OpenAICompatProvider(model="some-model", client=fake)
    provider.generate_json(system="s", prompt="p", schema=SCHEMA, images=[IMG])
    assert "max_completion_tokens" in fake.calls[1] and "max_tokens" not in fake.calls[1]
    assert isinstance(fake.calls[2]["messages"][1]["content"], str)  # fotoğraflar çıkarıldı


def test_openai_refusal():
    fake = _FakeOpenAI(_completion(None, refusal="Bu isteğe yardımcı olamam."))
    with pytest.raises(AIRefusal):
        OpenAICompatProvider(model="m", client=fake).generate_json(system="s", prompt="p", schema=SCHEMA)


def test_extract_json_and_conform():
    assert extract_json('önce metin {"a": 1} sonra') == {"a": 1}
    fixed = conform({"a": 5, "n": "3,5", "extra": 1}, SCHEMA)
    assert fixed == {"a": "5", "n": 3.5}
    enum_schema = {"type": "object", "properties": {"durum": {"type": "string", "enum": ["Çok İyi", "İyi"]}}}
    assert conform({"durum": "ÇOK İYİ"}, enum_schema)["durum"] == "Çok İyi"
    assert conform({"durum": "harika"}, enum_schema)["durum"] is None


def test_openai_resolves_model_name_from_server_list():
    err = openai.NotFoundError(
        "The model `muse spark 1.3` does not exist",
        response=httpx2.Response(404, request=httpx2.Request("POST", "https://x/v1/chat/completions")),
        body=None,
    )
    fake = _FakeOpenAI(err, _completion('{"a": "ok", "n": 1}'))
    fake.models = SimpleNamespace(list=lambda: [SimpleNamespace(id="gpt-4o-mini"), SimpleNamespace(id="muse-spark-1.3")])
    provider = OpenAICompatProvider(model="muse spark 1.3", base_url="https://x/v1", client=fake)
    assert provider.generate_json(system="s", prompt="p", schema=SCHEMA)["a"] == "ok"
    assert provider.model == "muse-spark-1.3" and fake.calls[1]["model"] == "muse-spark-1.3"


def test_settings_env_defaults(tmp_path, monkeypatch):
    from autosell.config import SettingsStore

    monkeypatch.setenv("AUTOSELL_AI_PROVIDER", "claude")
    monkeypatch.setenv("AUTOSELL_OPENAI_MODEL", "baska-model")
    store = SettingsStore(tmp_path / "ayarlar.json")
    assert store.get().ai.provider == "claude" and store.get().ai.openai_model == "baska-model"
    store.update({"ai": {"provider": "openai"}})  # panelden kaydedilen değer ortamın önüne geçer
    assert store.get().ai.provider == "openai"
