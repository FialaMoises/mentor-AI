"""A chamada ao modelo: qual modelo, com fallback, e o que fazer quando ele não responde o JSON."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.config import Settings
from app.extraction.provider import (
    FALLBACK_BETA,
    AnthropicExtractor,
    ExtractionError,
)


class Mensagens:
    def __init__(self, resposta: SimpleNamespace) -> None:
        self.resposta = resposta
        self.chamadas: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> SimpleNamespace:
        self.chamadas.append(kwargs)
        return self.resposta


class ClienteFalso:
    """Imita só o pedaço do SDK que a extração usa: `client.beta.messages.create`."""

    def __init__(self, resposta: SimpleNamespace) -> None:
        self.mensagens = Mensagens(resposta)
        self.beta = SimpleNamespace(messages=self.mensagens)


def resposta(stop_reason: str, texto: str = "") -> SimpleNamespace:
    blocos = [SimpleNamespace(type="text", text=texto)] if texto else []
    return SimpleNamespace(stop_reason=stop_reason, content=blocos)


JSON_OK = '{"commitments": [], "exams": [], "unreadable": ["nada legível"]}'


def extrair(cliente: ClienteFalso) -> dict[str, Any]:
    extrator = AnthropicExtractor(client=cliente, model="claude-opus-5-5")
    return extrator.extract(content=b"%PDF-1.7", content_type="application/pdf", kind="grade")


def test_modelo_padrao_e_o_atual() -> None:
    """O claude-sonnet-4-5 sai de linha em 30/11/2026."""
    assert Settings().extraction_model == "claude-opus-5-5"


def test_pede_fallback_do_servidor_para_recusa() -> None:
    cliente = ClienteFalso(resposta("end_turn", JSON_OK))

    extrair(cliente)

    chamada = cliente.mensagens.chamadas[0]
    assert chamada["model"] == "claude-opus-5-5"
    assert chamada["betas"] == [FALLBACK_BETA]
    assert chamada["fallbacks"] == "default"


def test_resposta_normal_vira_o_json() -> None:
    cliente = ClienteFalso(resposta("end_turn", JSON_OK))

    assert extrair(cliente)["unreadable"] == ["nada legível"]


def test_recusa_vira_erro_de_extracao_com_explicacao() -> None:
    cliente = ClienteFalso(resposta("refusal"))

    with pytest.raises(ExtractionError, match="recusou"):
        extrair(cliente)


def test_resposta_cortada_nao_vira_json_pela_metade() -> None:
    cliente = ClienteFalso(resposta("max_tokens", '{"commitments": [{"kind": "aula"'))

    with pytest.raises(ExtractionError, match="cortada"):
        extrair(cliente)
