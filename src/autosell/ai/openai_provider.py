"""OpenAI uyumlu sağlayıcı (resmi openai Python SDK).

OpenAI'nin yanı sıra OpenAI uyumlu uç nokta sunan servislerle de çalışır:
OpenRouter, Groq, DeepSeek, Together, yerel Ollama / LM Studio / vLLM vb.
Sunucu desteklemiyorsa sırasıyla json_schema -> json_object -> serbest metin
kiplerine düşer; görsel desteklemeyen modellerde fotoğraflar otomatik çıkarılır.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Sequence

import openai

from .base import AIError, AINotConfigured, AIRefusal, ImageInput, LLMProvider, extract_json

log = logging.getLogger(__name__)

_JSON_INSTRUCTION = (
    "\n\nYanıtını YALNIZCA aşağıdaki JSON şemasına uyan tek bir geçerli JSON nesnesi olarak ver; "
    "açıklama veya kod bloğu ekleme.\nJSON şeması:\n{schema}"
)


class OpenAICompatProvider(LLMProvider):
    name = "openai"

    def __init__(
        self,
        *,
        model: str,
        base_url: str = "",
        api_key: str = "",
        vision: bool = True,
        client: Any | None = None,
    ):
        if not model:
            raise AINotConfigured("OpenAI uyumlu sağlayıcı için model adı girilmemiş.")
        self.model = model
        self.vision = vision
        self.supports_images = vision
        key = api_key or os.environ.get("OPENAI_API_KEY") or "yerel-anahtar"
        self.client = client or openai.OpenAI(api_key=key, base_url=base_url or None)

    def _messages(
        self, system: str, prompt: str, schema: dict[str, Any], images: Sequence[ImageInput], mode: str
    ) -> list[dict[str, Any]]:
        sys_text = system
        if mode != "json_schema":
            sys_text += _JSON_INSTRUCTION.format(schema=json.dumps(schema, ensure_ascii=False))
        user: list[dict[str, Any]] | str
        if images:
            user = [{"type": "text", "text": prompt}] + [
                {"type": "image_url", "image_url": {"url": f"data:{img.media_type};base64,{img.data_b64}"}}
                for img in images
            ]
        else:
            user = prompt
        return [{"role": "system", "content": sys_text}, {"role": "user", "content": user}]

    def generate_json(
        self,
        *,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        images: Sequence[ImageInput] = (),
        web_search: bool = False,
        max_tokens: int = 16000,
    ) -> dict[str, Any]:
        use_images = list(images) if self.vision else []
        token_key = "max_completion_tokens" if self.model.startswith(("o1", "o3", "o4", "gpt-5")) else "max_tokens"
        token_limit = max_tokens
        switched_key = False
        last_error: Exception | None = None

        for mode in ("json_schema", "json_object", "text"):
            for _ in range(4):  # aynı kipte parametre düzeltmeleriyle yeniden deneme
                kwargs: dict[str, Any] = {
                    "model": self.model,
                    "messages": self._messages(system, prompt, schema, use_images, mode),
                    token_key: token_limit,
                }
                if mode == "json_schema":
                    kwargs["response_format"] = {
                        "type": "json_schema",
                        "json_schema": {"name": "autosell_cikti", "schema": schema, "strict": True},
                    }
                elif mode == "json_object":
                    kwargs["response_format"] = {"type": "json_object"}
                try:
                    response = self.client.chat.completions.create(**kwargs)
                except openai.BadRequestError as exc:
                    last_error = exc
                    msg = str(exc).lower()
                    limit_words = ("too large", "maximum", "exceed", "at most", "less than", "must be")
                    if token_key in msg and not any(w in msg for w in limit_words) and not switched_key:
                        token_key = "max_completion_tokens" if token_key == "max_tokens" else "max_tokens"
                        switched_key = True
                        continue
                    if any(w in msg for w in ("max_tokens", "max_completion_tokens", "context length", "context_length")):
                        if token_limit > 4096:
                            token_limit = 4096
                            continue
                    if use_images and any(w in msg for w in ("image", "vision", "multimodal", "image_url")):
                        log.warning("Model görsel kabul etmiyor; fotoğraflar olmadan deneniyor.")
                        use_images = []
                        continue
                    break  # bir sonraki kipe geç
                except openai.AuthenticationError as exc:
                    raise AINotConfigured(
                        "OpenAI uyumlu API anahtarı geçersiz ya da eksik (Ayarlar > Yapay Zekâ)."
                    ) from exc
                except openai.PermissionDeniedError as exc:
                    raise AINotConfigured(f"OpenAI uyumlu API erişim izni yok: {exc}") from exc
                except openai.NotFoundError as exc:
                    raise AINotConfigured(f"Model ya da uç nokta bulunamadı ({self.model}).") from exc
                except openai.RateLimitError as exc:
                    raise AIError("API hız/kota sınırına takıldı; biraz sonra tekrar deneyin.") from exc
                except openai.APIConnectionError as exc:
                    raise AIError("OpenAI uyumlu API'ye bağlanılamadı (base URL doğru mu?).") from exc
                except openai.APIStatusError as exc:
                    last_error = exc
                    if exc.status_code in (422, 415):
                        break
                    raise AIError(f"OpenAI uyumlu API hatası ({exc.status_code}).") from exc

                if not response.choices:
                    last_error = AIError("Boş yanıt")
                    break
                choice = response.choices[0]
                refusal = getattr(choice.message, "refusal", None)
                if refusal:
                    raise AIRefusal(f"Model isteği reddetti: {refusal}")
                if choice.finish_reason == "length":
                    last_error = AIError("Yanıt uzunluk sınırına takıldı")
                    break
                try:
                    return extract_json(choice.message.content or "")
                except ValueError as exc:
                    last_error = exc
                    break
        raise AIError(f"OpenAI uyumlu modelden geçerli JSON alınamadı: {last_error}")
