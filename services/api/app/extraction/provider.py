"""Quem lê o arquivo: a porta, o dublê de teste e o cliente da Anthropic."""

from __future__ import annotations

import base64
import json
from typing import Any, Protocol

from ..config import get_settings
from .prompt import SYSTEM, user_prompt


class ExtractionError(RuntimeError):
    """O provedor não devolveu JSON utilizável."""


class ExtractionProvider(Protocol):
    def extract(self, *, content: bytes, content_type: str, kind: str) -> dict[str, Any]: ...


class FakeExtractor(ExtractionProvider):
    """Dublê: devolve o que mandarem, sem rede. Usado nos testes e no seed."""

    def __init__(self, payload: dict[str, Any] | None = None) -> None:
        self.payload = payload or {"commitments": [], "exams": [], "unreadable": []}
        self.calls: list[tuple[str, str, int]] = []

    def extract(self, *, content: bytes, content_type: str, kind: str) -> dict[str, Any]:
        self.calls.append((kind, content_type, len(content)))
        return self.payload


def _json_from_text(texto: str) -> dict[str, Any]:
    """O modelo às vezes embrulha o JSON em cerca de código. Aceita os dois."""
    limpo = texto.strip()
    if limpo.startswith("```"):
        limpo = limpo.split("```")[1]
        limpo = limpo.removeprefix("json").strip()
    try:
        dados = json.loads(limpo)
    except json.JSONDecodeError as erro:
        raise ExtractionError("o modelo não devolveu JSON") from erro
    if not isinstance(dados, dict):
        raise ExtractionError("o modelo devolveu JSON que não é objeto")
    return dados


class AnthropicExtractor(ExtractionProvider):
    """Lê PDF e imagem direto, sem OCR próprio."""

    def __init__(self, client: Any | None = None, model: str | None = None) -> None:
        settings = get_settings()
        self._model = model or settings.extraction_model
        if client is not None:
            self._client = client
            return
        import anthropic

        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def _bloco_do_arquivo(self, content: bytes, content_type: str) -> dict[str, Any]:
        dados = base64.standard_b64encode(content).decode("ascii")
        if content_type == "application/pdf":
            return {
                "type": "document",
                "source": {"type": "base64", "media_type": content_type, "data": dados},
            }
        if content_type.startswith("image/"):
            return {
                "type": "image",
                "source": {"type": "base64", "media_type": content_type, "data": dados},
            }
        raise ExtractionError(
            f"{content_type} precisa virar PDF ou imagem antes de ir para o modelo"
        )

    def extract(self, *, content: bytes, content_type: str, kind: str) -> dict[str, Any]:
        resposta = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": [
                        self._bloco_do_arquivo(content, content_type),
                        {"type": "text", "text": user_prompt(kind)},
                    ],
                }
            ],
        )
        partes = [bloco.text for bloco in resposta.content if getattr(bloco, "type", "") == "text"]
        if not partes:
            raise ExtractionError("o modelo respondeu sem texto")
        return _json_from_text("".join(partes))


def get_provider() -> ExtractionProvider:
    settings = get_settings()
    if not settings.anthropic_api_key:
        return FakeExtractor()
    return AnthropicExtractor()
