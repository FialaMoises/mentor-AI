from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import (
    AuthError,
    logout,
    normalize_email,
    request_login,
    revoke_all,
    student_for_token,
    verify_login,
)
from app.models import AuthSession, LoginToken, Student

AGORA = datetime(2026, 9, 25, 12, tzinfo=UTC)


def test_o_token_em_claro_nunca_vai_para_o_banco(session: Session) -> None:
    link = request_login(session, "aluno@exemplo.com", now=AGORA)
    session.flush()

    registro = session.scalar(select(LoginToken))
    assert registro is not None
    assert registro.token_hash != link.token
    assert link.token not in registro.token_hash


def test_email_e_normalizado() -> None:
    assert normalize_email("  Aluno@Exemplo.COM ") == "aluno@exemplo.com"
    with pytest.raises(AuthError):
        normalize_email("sem-arroba")


def test_link_cria_o_aluno_na_primeira_entrada(session: Session) -> None:
    link = request_login(session, "novo@exemplo.com", now=AGORA)
    entrada = verify_login(session, link.token, now=AGORA)
    session.flush()

    assert entrada.is_new is True
    assert entrada.student.email == "novo@exemplo.com"


def test_segunda_entrada_acha_o_mesmo_aluno(session: Session) -> None:
    primeiro = verify_login(
        session, request_login(session, "a@exemplo.com", now=AGORA).token, now=AGORA
    )
    segundo = verify_login(
        session, request_login(session, "a@exemplo.com", now=AGORA).token, now=AGORA
    )
    session.flush()

    assert primeiro.student.id == segundo.student.id
    assert segundo.is_new is False
    assert len(list(session.scalars(select(Student)))) == 1


def test_link_serve_uma_vez_so(session: Session) -> None:
    link = request_login(session, "a@exemplo.com", now=AGORA)
    verify_login(session, link.token, now=AGORA)
    session.flush()

    with pytest.raises(AuthError, match="já foi usado"):
        verify_login(session, link.token, now=AGORA)


def test_link_expirado_nao_entra(session: Session) -> None:
    link = request_login(session, "a@exemplo.com", now=AGORA)

    with pytest.raises(AuthError, match="expirado"):
        verify_login(session, link.token, now=AGORA + timedelta(hours=1))


def test_token_inventado_nao_entra(session: Session) -> None:
    with pytest.raises(AuthError, match="inválido"):
        verify_login(session, "token-que-eu-inventei", now=AGORA)


def test_sessao_reconhece_o_aluno(session: Session) -> None:
    entrada = verify_login(
        session, request_login(session, "a@exemplo.com", now=AGORA).token, now=AGORA
    )
    session.flush()

    achado = student_for_token(session, entrada.token, now=AGORA)
    assert achado is not None and achado.id == entrada.student.id


def test_sessao_expirada_nao_vale(session: Session) -> None:
    entrada = verify_login(
        session, request_login(session, "a@exemplo.com", now=AGORA).token, now=AGORA
    )
    session.flush()

    assert student_for_token(session, entrada.token, now=AGORA + timedelta(days=31)) is None


def test_sair_derruba_a_sessao(session: Session) -> None:
    entrada = verify_login(
        session, request_login(session, "a@exemplo.com", now=AGORA).token, now=AGORA
    )
    session.flush()

    logout(session, entrada.token, now=AGORA)

    assert student_for_token(session, entrada.token, now=AGORA) is None


def test_sair_de_todos_os_aparelhos(session: Session) -> None:
    primeira = verify_login(
        session, request_login(session, "a@exemplo.com", now=AGORA).token, now=AGORA
    )
    segunda = verify_login(
        session, request_login(session, "a@exemplo.com", now=AGORA).token, now=AGORA
    )
    session.flush()

    assert revoke_all(session, primeira.student, now=AGORA) == 2
    assert student_for_token(session, primeira.token, now=AGORA) is None
    assert student_for_token(session, segunda.token, now=AGORA) is None
    assert len(list(session.scalars(select(AuthSession)))) == 2


def test_pedido_de_link_responde_igual_para_email_conhecido_ou_nao(
    client: TestClient, session: Session
) -> None:
    conhecido = client.post("/api/v1/auth/magic-link", json={"email": "a@exemplo.com"})
    session.commit()
    desconhecido = client.post("/api/v1/auth/magic-link", json={"email": "z@exemplo.com"})

    assert conhecido.status_code == desconhecido.status_code == 202
    assert conhecido.json() == desconhecido.json()


def test_email_malformado_e_recusado_na_api(client: TestClient) -> None:
    assert client.post("/api/v1/auth/magic-link", json={"email": "sem-arroba"}).status_code == 422


def test_verificar_pela_api_devolve_sessao_e_abre_o_trial(
    client: TestClient, session: Session
) -> None:
    link = request_login(session, "a@exemplo.com")
    session.commit()

    corpo = client.post("/api/v1/auth/verify", json={"token": link.token}).json()
    cabecalho = {"Authorization": f"Bearer {corpo['token']}"}
    eu = client.get("/api/v1/me", headers=cabecalho).json()

    assert eu["email"] == "a@exemplo.com"
    assert eu["subscription_status"] == "trial"
    assert eu["trial_ends_on"] is not None


def test_sair_pela_api_invalida_o_token(client: TestClient, session: Session) -> None:
    link = request_login(session, "a@exemplo.com")
    session.commit()
    corpo = client.post("/api/v1/auth/verify", json={"token": link.token}).json()
    cabecalho = {"Authorization": f"Bearer {corpo['token']}"}

    assert client.post("/api/v1/auth/logout", headers=cabecalho).status_code == 204
    assert client.get("/api/v1/me", headers=cabecalho).status_code == 401
