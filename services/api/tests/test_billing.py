from __future__ import annotations

import hashlib
import hmac
import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billing import (
    TRIAL_DAYS,
    BillingError,
    FakeGateway,
    GatewayEvent,
    cancel,
    checkout,
    handle_event,
    has_access,
    pause,
    resume,
    start_trial,
    subscription_of,
)
from app.models import PaymentEvent, Student, Subscription

HOJE = date(2026, 9, 25)


@pytest.fixture
def aluno(session: Session) -> Student:
    student = Student(phase="formado", mode="independente", email="aluno@exemplo.com")
    session.add(student)
    session.flush()
    return student


@pytest.fixture
def gateway() -> FakeGateway:
    return FakeGateway()


def test_aluno_novo_comeca_em_teste(session: Session, aluno: Student) -> None:
    assinatura = start_trial(session, aluno, HOJE)

    assert assinatura.status == "trial"
    assert assinatura.trial_ends_on == HOJE + timedelta(days=TRIAL_DAYS)
    assert has_access(session, aluno, HOJE) is True


def test_abrir_o_teste_duas_vezes_nao_reinicia_o_prazo(session: Session, aluno: Student) -> None:
    primeiro = start_trial(session, aluno, HOJE)
    segundo = start_trial(session, aluno, HOJE + timedelta(days=5))

    assert primeiro.trial_ends_on == segundo.trial_ends_on


def test_teste_vencido_perde_o_acesso(session: Session, aluno: Student) -> None:
    start_trial(session, aluno, HOJE)

    assert has_access(session, aluno, HOJE + timedelta(days=TRIAL_DAYS + 1)) is False


def test_checkout_guarda_a_referencia_e_nao_toca_em_dado_de_cartao(
    session: Session, aluno: Student, gateway: FakeGateway
) -> None:
    resultado = checkout(
        session, aluno, plan="mensal", price_cents=4900, gateway=gateway, today=HOJE
    )

    assinatura = subscription_of(session, aluno)
    assert assinatura is not None
    assert assinatura.provider_ref == resultado.provider_ref
    assert assinatura.price_cents == 4900
    assert "http" in resultado.url


def test_plano_desconhecido_e_recusado(
    session: Session, aluno: Student, gateway: FakeGateway
) -> None:
    with pytest.raises(BillingError):
        checkout(session, aluno, plan="vitalicio", price_cents=1, gateway=gateway, today=HOJE)


def test_pausar_tira_o_acesso_e_mantem_os_dados(session: Session, aluno: Student) -> None:
    start_trial(session, aluno, HOJE)

    pause(session, aluno, until=HOJE + timedelta(days=30), today=HOJE)

    assert has_access(session, aluno, HOJE) is False
    assert subscription_of(session, aluno) is not None
    assert aluno.subscription_status == "pausada"


def test_pausa_precisa_terminar_no_futuro(session: Session, aluno: Student) -> None:
    start_trial(session, aluno, HOJE)

    with pytest.raises(BillingError):
        pause(session, aluno, until=HOJE, today=HOJE)


def test_retomar_devolve_o_acesso(session: Session, aluno: Student) -> None:
    start_trial(session, aluno, HOJE)
    pause(session, aluno, until=HOJE + timedelta(days=30), today=HOJE)

    resume(session, aluno, HOJE + timedelta(days=5))

    assert has_access(session, aluno, HOJE + timedelta(days=5)) is True


def test_cancelar_avisa_o_provedor(session: Session, aluno: Student, gateway: FakeGateway) -> None:
    resultado = checkout(
        session, aluno, plan="mensal", price_cents=4900, gateway=gateway, today=HOJE
    )

    cancel(session, aluno, gateway)

    assert gateway.canceled == [resultado.provider_ref]
    assert has_access(session, aluno, HOJE) is False


def test_assinatura_cancelada_nao_pausa(
    session: Session, aluno: Student, gateway: FakeGateway
) -> None:
    start_trial(session, aluno, HOJE)
    cancel(session, aluno, gateway)

    with pytest.raises(BillingError):
        pause(session, aluno, until=HOJE + timedelta(days=10), today=HOJE)


def test_pagamento_confirmado_ativa_a_assinatura(
    session: Session, aluno: Student, gateway: FakeGateway
) -> None:
    resultado = checkout(
        session, aluno, plan="mensal", price_cents=4900, gateway=gateway, today=HOJE
    )
    evento = GatewayEvent(
        external_id="evt_1",
        kind="pagamento_confirmado",
        provider_ref=resultado.provider_ref,
        payload={"current_period_end": (HOJE + timedelta(days=30)).isoformat()},
    )

    assert handle_event(session, evento, gateway) is True

    assinatura = subscription_of(session, aluno)
    assert assinatura is not None
    assert assinatura.status == "ativa"
    assert assinatura.current_period_end == HOJE + timedelta(days=30)


def test_webhook_repetido_nao_repete_efeito(
    session: Session, aluno: Student, gateway: FakeGateway
) -> None:
    resultado = checkout(
        session, aluno, plan="mensal", price_cents=4900, gateway=gateway, today=HOJE
    )
    evento = GatewayEvent(
        external_id="evt_1",
        kind="pagamento_confirmado",
        provider_ref=resultado.provider_ref,
        payload={},
    )

    primeiro = handle_event(session, evento, gateway)
    segundo = handle_event(session, evento, gateway)

    assert (primeiro, segundo) == (True, False)
    assert len(list(session.scalars(select(PaymentEvent)))) == 1


def test_pagamento_falhou_marca_atrasada(
    session: Session, aluno: Student, gateway: FakeGateway
) -> None:
    resultado = checkout(
        session, aluno, plan="mensal", price_cents=4900, gateway=gateway, today=HOJE
    )

    handle_event(
        session,
        GatewayEvent("evt_2", "pagamento_falhou", resultado.provider_ref, {}),
        gateway,
    )

    assinatura = subscription_of(session, aluno)
    assert assinatura is not None
    assert assinatura.status == "atrasada"
    assert has_access(session, aluno, HOJE) is False


def test_webhook_com_assinatura_errada_e_recusado(gateway: FakeGateway) -> None:
    corpo = json.dumps({"id": "evt_3", "type": "pagamento_confirmado"}).encode()

    with pytest.raises(BillingError, match="assinatura"):
        gateway.parse_event(corpo, "assinatura-inventada")


def test_webhook_com_assinatura_certa_passa(gateway: FakeGateway) -> None:
    corpo = json.dumps({"id": "evt_3", "type": "pagamento_confirmado", "ref": "r"}).encode()
    assinatura = hmac.new(gateway.secret.encode(), corpo, hashlib.sha256).hexdigest()

    evento = gateway.parse_event(corpo, assinatura)

    assert evento.external_id == "evt_3"


def test_fluxo_de_assinatura_pela_api(client: TestClient, session: Session, login) -> None:  # type: ignore[no-untyped-def]
    aluno = Student(phase="formado", mode="independente", email="api@exemplo.com")
    session.add(aluno)
    session.flush()
    start_trial(session, aluno, date.today())
    session.commit()
    cabecalho = login(aluno)

    inicial = client.get("/api/v1/me/subscription", headers=cabecalho).json()
    pagamento = client.post(
        "/api/v1/me/subscription/checkout", json={"plan": "mensal"}, headers=cabecalho
    ).json()
    pausada = client.post(
        "/api/v1/me/subscription/pause",
        json={"until": (date.today() + timedelta(days=30)).isoformat()},
        headers=cabecalho,
    ).json()
    retomada = client.post("/api/v1/me/subscription/resume", headers=cabecalho).json()

    assert inicial["status"] == "trial"
    assert inicial["has_access"] is True
    assert pagamento["price_cents"] > 0
    assert pausada["status"] == "pausada" and pausada["has_access"] is False
    assert retomada["has_access"] is True


def test_assinatura_exige_sessao(client: TestClient) -> None:
    assert client.get("/api/v1/me/subscription").status_code == 401


def test_webhook_pela_api_confere_a_assinatura(client: TestClient, session: Session) -> None:
    corpo = json.dumps({"id": "evt_9", "type": "pagamento_confirmado", "ref": "x"}).encode()

    recusado = client.post("/api/v1/billing/webhook", content=corpo, headers={"x-signature": "xx"})
    assinatura = hmac.new(b"segredo-de-teste", corpo, hashlib.sha256).hexdigest()
    aceito = client.post(
        "/api/v1/billing/webhook", content=corpo, headers={"x-signature": assinatura}
    )

    assert recusado.status_code == 401
    assert aceito.status_code == 200
    assert aceito.json() == {"applied": True}


def test_aluno_sem_assinatura_nao_tem_acesso(session: Session, aluno: Student) -> None:
    assert has_access(session, aluno, HOJE) is False
    assert not list(session.scalars(select(Subscription)))
