from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Student
from app.ratelimit import RateLimiter

ACADEMIA = {
    "kind": "academia",
    "label": "Musculação",
    "weekdays": [0],
    "starts_at": "07:00",
    "duration_minutes": 60,
}


def test_limitador_bloqueia_depois_do_limite_e_libera_quando_a_janela_passa() -> None:
    limitador = RateLimiter()

    assert limitador.hit("a", limit=2, window_seconds=60, now=0.0) is None
    assert limitador.hit("a", limit=2, window_seconds=60, now=1.0) is None
    espera = limitador.hit("a", limit=2, window_seconds=60, now=2.0)
    assert espera == pytest.approx(58.0)
    assert limitador.hit("b", limit=2, window_seconds=60, now=2.0) is None
    assert limitador.hit("a", limit=2, window_seconds=60, now=60.5) is None


def test_limitador_recusa_limite_invalido() -> None:
    with pytest.raises(ValueError):
        RateLimiter().hit("a", limit=0, window_seconds=60, now=0.0)


@pytest.fixture
def limites_baixos() -> Iterator[None]:
    settings = get_settings()
    antes = (
        settings.rate_limit_per_minute,
        settings.rate_limit_writes_per_minute,
        settings.rate_limit_login_per_window,
    )
    settings.rate_limit_per_minute = 6
    settings.rate_limit_writes_per_minute = 2
    settings.rate_limit_login_per_window = 2
    yield
    (
        settings.rate_limit_per_minute,
        settings.rate_limit_writes_per_minute,
        settings.rate_limit_login_per_window,
    ) = antes


def _aluno(session: Session) -> Student:
    aluno = Student(phase="formado", mode="independente", timezone="America/Fortaleza")
    session.add(aluno)
    session.commit()
    return aluno


def test_escritas_demais_respondem_429_com_retry_after(
    client: TestClient,
    session: Session,
    limites_baixos: None,
    login,  # type: ignore[no-untyped-def]
) -> None:
    cabecalho = login(_aluno(session))

    for _ in range(2):
        resposta = client.post("/api/v1/me/commitment-series", json=ACADEMIA, headers=cabecalho)
        assert resposta.status_code == 201
    bloqueada = client.post("/api/v1/me/commitment-series", json=ACADEMIA, headers=cabecalho)

    assert bloqueada.status_code == 429
    assert int(bloqueada.headers["retry-after"]) >= 1
    assert "tente de novo" in bloqueada.json()["detail"]
    # Ler continua liberado: o limite de escrita é separado do geral.
    assert client.get("/api/v1/me/routine", headers=cabecalho).status_code == 200


def test_limite_e_por_aluno(
    client: TestClient,
    session: Session,
    limites_baixos: None,
    login,  # type: ignore[no-untyped-def]
) -> None:
    primeiro = login(_aluno(session))
    segundo = login(_aluno(session))
    for _ in range(3):
        client.post("/api/v1/me/commitment-series", json=ACADEMIA, headers=primeiro)

    resposta = client.post("/api/v1/me/commitment-series", json=ACADEMIA, headers=segundo)

    assert resposta.status_code == 201


def test_limite_geral_vale_para_leitura(
    client: TestClient,
    session: Session,
    limites_baixos: None,
    login,  # type: ignore[no-untyped-def]
) -> None:
    cabecalho = login(_aluno(session))
    respostas = [client.get("/api/v1/me", headers=cabecalho).status_code for _ in range(7)]

    assert respostas[:6] == [200] * 6
    assert respostas[6] == 429


def test_link_magico_tem_limite_por_email(client: TestClient, limites_baixos: None) -> None:
    corpo = {"email": "alguem@exemplo.com"}
    for _ in range(2):
        assert client.post("/api/v1/auth/magic-link", json=corpo).status_code == 202

    assert client.post("/api/v1/auth/magic-link", json=corpo).status_code == 429
    assert (
        client.post("/api/v1/auth/magic-link", json={"email": "ALGUEM@exemplo.com"}).status_code
        == 429
    )


def test_health_e_webhook_ficam_fora_do_limite(client: TestClient, limites_baixos: None) -> None:
    for _ in range(10):
        assert client.get("/health").status_code == 200
    respostas = {
        client.post("/api/v1/billing/webhook", content=b"{}").status_code for _ in range(10)
    }

    assert 429 not in respostas
