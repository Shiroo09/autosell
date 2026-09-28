"""Claude sağlayıcısı (resmi Anthropic Python SDK)."""

from __future__ import annotations

import json
import logging
from typing import Any, Sequence

import anthropic

from .base import AIError, AINotConfigured, AIRefusal, ImageInput, LLMProvider, extract_json

log = logging.getLogger(__name__)

# Sunucu tarafı yedek model (refusal fallback) desteklenen modeller
FALLBACK_MODELS = frozenset({"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"})
FALLBACK_BETA = "server-side-fallback-2026-07-01"
WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search", "max_uses": 4}
MAX_CONTINUATIONS = 4


def supports_effort(model: str) -> bool:
    m = model.lower()
    return not any(x in m for x in ("haiku", "claude-3", "sonnet-4-5", "sonnet-4-0", "opus-4-0", "opus-4-1"))


class AnthropicProvider(LLMProvider):
    name = "claude"
    supports_web_search = True

    def __init__(
        self,
        *,
        model: str,
        effort: str = "high",
        api_key: str = "",
        fallback: bool = True,
        client: Any | None = None,
    ):
        self.model = model
        self.effort = effort
        self.fallback = fallback
        # Anahtar verilmezse SDK ANTHROPIC_API_KEY / `ant auth login` profilini kullanır.
        self.client = client or (anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic())

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
        content: list[dict[str, Any]] = [
            {"type": "image", "source": {"type": "base64", "media_type": img.media_type, "data": img.data_b64}}
            for img in images
        ]
        content.append({"type": "text", "text": prompt})
        messages: list[dict[str, Any]] = [{"role": "user", "content": content}]

        output_config: dict[str, Any] = {"format": {"type": "json_schema", "schema": schema}}
        if supports_effort(self.model):
            output_config["effort"] = self.effort
        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
            "output_config": output_config,
        }
        betas: list[str] = []
        if self.fallback and self.model in FALLBACK_MODELS:
            params["fallbacks"] = "default"
            betas.append(FALLBACK_BETA)
        if web_search:
            params["tools"] = [dict(WEB_SEARCH_TOOL)]

        message = self._call(params, betas)
        # Sunucu araçları (web araması) uzun sürerse tur "pause_turn" ile duraklar; devam ettir.
        for _ in range(MAX_CONTINUATIONS):
            if message.stop_reason != "pause_turn":
                break
            params["messages"] = messages + [{"role": "assistant", "content": message.content}]
            message = self._call(params, betas)

        if message.stop_reason == "refusal":
            details = getattr(message, "stop_details", None)
            category = getattr(details, "category", None) if details else None
            raise AIRefusal(f"Claude isteği reddetti (kategori: {category or 'belirtilmedi'}).")
        if message.stop_reason == "max_tokens":
            raise AIError("Yapay zekâ yanıtı uzunluk sınırına takıldı; lütfen tekrar deneyin.")

        texts = [block.text for block in message.content if getattr(block, "type", "") == "text"]
        for text in reversed(texts):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                try:
                    return extract_json(text)
                except ValueError:
                    continue
        raise AIError("Claude yanıtında geçerli JSON bulunamadı.")

    def _call(self, params: dict[str, Any], betas: list[str]) -> Any:
        try:
            with self.client.beta.messages.stream(**params, betas=list(betas)) as stream:
                return stream.get_final_message()
        except anthropic.BadRequestError as exc:
            if "fallbacks" in params and "fallback" in str(exc).lower():
                # Hesap/model yedek model özelliğini desteklemiyorsa onsuz tekrar dene.
                log.warning("Yedek model desteklenmedi, onsuz deneniyor: %s", exc)
                params.pop("fallbacks", None)
                betas[:] = [b for b in betas if b != FALLBACK_BETA]
                return self._call(params, betas)
            raise AIError(f"Claude isteği geçersiz: {exc.message}") from exc
        except anthropic.AuthenticationError as exc:
            raise AINotConfigured(
                "Claude API anahtarı geçersiz ya da tanımlı değil. Ayarlar > Yapay Zekâ bölümünden "
                "anahtar girin veya ANTHROPIC_API_KEY ortam değişkenini tanımlayın."
            ) from exc
        except anthropic.PermissionDeniedError as exc:
            raise AINotConfigured(f"Claude API erişim izni yok: {exc.message}") from exc
        except anthropic.NotFoundError as exc:
            raise AINotConfigured(f"Claude modeli bulunamadı ({params['model']}).") from exc
        except anthropic.RateLimitError as exc:
            raise AIError("Claude hız sınırına takıldı; biraz sonra tekrar deneyin.") from exc
        except anthropic.APIConnectionError as exc:
            raise AIError("Claude API'ye bağlanılamadı; internet bağlantınızı kontrol edin.") from exc
        except anthropic.APIStatusError as exc:
            raise AIError(f"Claude API hatası ({exc.status_code}): {exc.message}") from exc
        except TypeError as exc:
            # Kimlik bilgisi bulunamadığında SDK istek sırasında TypeError fırlatabilir.
            if "api_key" in str(exc) or "auth" in str(exc).lower():
                raise AINotConfigured("Claude API anahtarı tanımlı değil.") from exc
            raise
