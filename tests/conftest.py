from __future__ import annotations

import copy
import functools
import http.server
import socketserver
import threading
from pathlib import Path
from typing import Any, Callable, Sequence

import pytest
from PIL import Image

from autosell.ai.base import ImageInput, LLMProvider

FIXTURES = Path(__file__).parent / "fixtures"
MOCK_SITES = FIXTURES / "mock_sites"


class FakeProvider(LLMProvider):
    """Test için sahte yapay zekâ: şemaya göre hazır yanıt ya da fonksiyon çıktısı döner."""

    name = "sahte"
    model = "test-model"

    def __init__(self, responder: Callable[[str, str, dict[str, Any]], dict[str, Any]] | dict[str, Any]):
        self.responder = responder
        self.calls: list[dict[str, Any]] = []

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
        self.calls.append({"system": system, "prompt": prompt, "schema": schema, "images": len(images)})
        if callable(self.responder):
            return self.responder(system, prompt, schema)
        return copy.deepcopy(self.responder)


@pytest.fixture
def make_photo(tmp_path: Path) -> Callable[[str, tuple[int, int, int]], Path]:
    def _make(name: str = "foto.jpg", color: tuple[int, int, int] = (40, 90, 200)) -> Path:
        path = tmp_path / name
        Image.new("RGB", (640, 480), color).save(path, "JPEG")
        return path

    return _make


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass


@pytest.fixture(scope="session")
def mock_server() -> str:
    """tests/fixtures/mock_sites klasörünü yerel HTTP sunucusunda yayınlar."""
    if not MOCK_SITES.exists():
        pytest.skip("Sahte siteler bulunamadı")
    handler = functools.partial(_QuietHandler, directory=str(MOCK_SITES))
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
