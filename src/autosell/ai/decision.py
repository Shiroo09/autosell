"""Hızlı karar motoru: TypeSafe Jev ya da yerelde çalışan Laya.

Bu modeller metin üretmez; verilen bir duruma (ör. bir ilan) yazılı sorulara tek
adımda, olasılıklı cevap verir: ``choice`` (seçeneklerden biri), ``score`` (sıralı
ölçek) ve ``noul`` (cevabın "evet" olma olasılığı). Büyük dil modellerinden onlarca
kat hızlıdırlar; fırsat taramasında aksesuar, farklı model, kusurlu ya da şüpheli
ilanları saniyeler içinde elemek için kullanılır.

İkisi de aynı ``POST /v1/systemone`` protokolünü konuşur: Jev bir API ağ geçidinden,
Laya ise ``laya-serve`` komutuyla bilgisayarınızda (varsayılan http://127.0.0.1:8000)
çalışır. Bu yüzden tek istemci ikisiyle de çalışır.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

DEFAULT_LAYA_URL = "http://127.0.0.1:8000"


class DecisionError(RuntimeError):
    """Karar motoru çağrısı başarısız oldu."""


def systemone_url(base_url: str) -> str:
    """Taban adresi /v1/systemone uç noktasına çevirir (".../v1" ya da kök adres kabul edilir)."""
    from urllib.parse import urlparse

    url = (base_url or "").strip().rstrip("/")
    if not url:
        raise DecisionError("Karar motoru adresi boş.")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise DecisionError(f"Karar motoru adresi geçersiz: {base_url!r} (ör. https://openrouter.ai/api/v1 "
                            "ya da http://127.0.0.1:8000)")
    if url.endswith("/v1/systemone"):
        return url
    if url.endswith("/v1"):
        return url + "/systemone"
    return url + "/v1/systemone"


def noul(answers: dict[str, Any], key: str) -> float | None:
    """Evet/hayır sorusunun "evet" olasılığı (yoksa None)."""
    value = (answers.get(key) or {}).get("noul")
    return float(value) if isinstance(value, (int, float)) else None


def choice(answers: dict[str, Any], key: str) -> tuple[str | None, float]:
    """Seçimli sorunun cevabı ve o cevabın olasılığı."""
    ans = answers.get(key) or {}
    picked = ans.get("choice")
    probs = ans.get("probabilities") or {}
    prob = probs.get(picked)
    if not isinstance(prob, (int, float)):
        # Laya'da olasılık answer_confidence, Jev'de probabilities içinde gelir.
        prob = ans.get("answer_confidence", ans.get("confidence", 0.0))
    return (str(picked) if picked is not None else None), float(prob or 0.0)


class DecisionEngine:
    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        model: str = "",
        *,
        name: str = "",
        timeout: float = 20.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.url = systemone_url(base_url)
        self.model = model.strip()
        self.name = name or self.model or "karar"
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key.strip()}"
        # Aynı bağlantı yeniden kullanılır (her karar için TLS el sıkışması yapılmaz).
        self._client = httpx.Client(timeout=timeout, headers=headers, transport=transport)

    def describe(self) -> str:
        return f"{self.name} ({self.url})"

    def close(self) -> None:
        self._client.close()

    def decide(self, state: Any, questions: dict[str, Any], *, retries: int = 1) -> dict[str, Any]:
        """Soruları cevaplar; {soru_adı: cevap} döndürür."""
        body: dict[str, Any] = {"state": state, "questions": questions}
        if self.model:
            body["model"] = self.model
        for attempt in range(retries + 1):
            try:
                resp = self._client.post(self.url, json=body)
            except httpx.HTTPError as exc:
                if attempt < retries:
                    time.sleep(0.5)
                    continue
                raise DecisionError(f"Karar motoruna ulaşılamadı ({self.url}): {exc}") from exc
            if resp.status_code in (429, 503) and attempt < retries:
                try:
                    wait = float(resp.headers.get("Retry-After") or 1)
                except ValueError:
                    wait = 1.0
                time.sleep(min(max(wait, 0.2), 5.0))
                continue
            if resp.status_code in (401, 403):
                raise DecisionError("Karar motoru API anahtarını kabul etmedi.")
            if resp.status_code >= 400:
                hint = (" Sunucu bu karar modelini şu an sunamıyor olabilir (geçici arıza ya da kota); "
                        "tarama kural tabanlı puanlamayla sürer." if resp.status_code in (400, 404, 502, 503) else "")
                raise DecisionError(f"Karar motoru hatası (HTTP {resp.status_code}): {_error_detail(resp)}.{hint}")
            try:
                answers = resp.json().get("answers")
            except ValueError as exc:
                raise DecisionError("Karar motoru geçerli JSON döndürmedi.") from exc
            if not isinstance(answers, dict):
                raise DecisionError("Karar motoru yanıtında 'answers' yok.")
            return answers
        raise DecisionError("Karar motoru yanıt vermedi.")  # pragma: no cover - döngü hep döner


def _error_detail(resp: httpx.Response) -> str:
    try:
        data = resp.json()
    except ValueError:
        return resp.text[:200]
    err = data.get("error") if isinstance(data, dict) else None
    if isinstance(err, dict):
        return str(err.get("message", ""))[:200]
    if isinstance(data, dict) and data.get("detail"):
        return str(data["detail"])[:200]
    return str(data)[:200]
