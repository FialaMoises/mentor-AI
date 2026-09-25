"""Assinatura: teste grátis, ativação, pausa e cancelamento.

O gateway entra por uma porta. Aqui não passa número de cartão nem dado de
pagamento: a aplicação guarda só a referência que o provedor devolve.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import PaymentEvent, Student, Subscription

TRIAL_DAYS = 14
#: Quem tem acesso ao plano. Pausada e cancelada não têm — os dados ficam.
ACTIVE_STATUSES = frozenset({"trial", "ativa"})


class BillingError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Checkout:
    """Para onde mandar o aluno pagar, e a referência que volta do provedor."""

    url: str
    provider_ref: str


@dataclass(frozen=True, slots=True)
class GatewayEvent:
    external_id: str
    kind: str
    provider_ref: str
    payload: dict[str, Any]


class BillingGateway(Protocol):
    name: str

    def create_checkout(self, student: Student, plan: str, price_cents: int) -> Checkout: ...

    def cancel(self, provider_ref: str) -> None: ...

    def parse_event(self, body: bytes, signature: str) -> GatewayEvent: ...


class FakeGateway(BillingGateway):
    """Gateway de mentira: roda o fluxo inteiro sem sair da máquina."""

    name = "fake"

    def __init__(self, secret: str = "segredo-de-teste") -> None:
        self.secret = secret
        self.checkouts: list[tuple[str, str]] = []
        self.canceled: list[str] = []

    def create_checkout(self, student: Student, plan: str, price_cents: int) -> Checkout:
        referencia = f"fake_{student.id.hex[:12]}_{plan}"
        self.checkouts.append((referencia, plan))
        return Checkout(url=f"https://pagamento.exemplo/{referencia}", provider_ref=referencia)

    def cancel(self, provider_ref: str) -> None:
        self.canceled.append(provider_ref)

    def parse_event(self, body: bytes, signature: str) -> GatewayEvent:
        import hashlib
        import hmac
        import json

        esperado = hmac.new(self.secret.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(esperado, signature):
            raise BillingError("assinatura do webhook não confere")

        dados = json.loads(body)
        return GatewayEvent(
            external_id=str(dados["id"]),
            kind=str(dados["type"]),
            provider_ref=str(dados.get("ref", "")),
            payload=dados,
        )


def subscription_of(session: Session, student: Student) -> Subscription | None:
    return session.scalar(select(Subscription).where(Subscription.student_id == student.id))


def start_trial(session: Session, student: Student, today: date) -> Subscription:
    """Todo aluno novo começa em teste. Sem cartão, sem fricção."""
    assinatura = subscription_of(session, student)
    if assinatura is not None:
        return assinatura

    assinatura = Subscription(
        student_id=student.id,
        status="trial",
        trial_ends_on=today + timedelta(days=TRIAL_DAYS),
    )
    session.add(assinatura)
    student.subscription_status = "trial"
    session.flush()
    return assinatura


def has_access(session: Session, student: Student, today: date) -> bool:
    """Trial vencido sem pagamento perde o acesso — os dados continuam lá."""
    assinatura = subscription_of(session, student)
    if assinatura is None:
        return False
    if assinatura.status == "trial":
        return assinatura.trial_ends_on is None or assinatura.trial_ends_on >= today
    if assinatura.status == "pausada":
        return False
    if assinatura.status == "ativa":
        return assinatura.current_period_end is None or assinatura.current_period_end >= today
    return False


def checkout(
    session: Session,
    student: Student,
    *,
    plan: str,
    price_cents: int,
    gateway: BillingGateway,
    today: date,
) -> Checkout:
    if plan not in ("mensal", "anual"):
        raise BillingError(f"plano desconhecido: {plan}")

    assinatura = start_trial(session, student, today)
    resultado = gateway.create_checkout(student, plan, price_cents)
    assinatura.plan = plan
    assinatura.price_cents = price_cents
    assinatura.provider = gateway.name
    assinatura.provider_ref = resultado.provider_ref
    session.flush()
    return resultado


def pause(session: Session, student: Student, *, until: date, today: date) -> Subscription:
    """O botão de pausar, ao lado do de cancelar: a conta espera o aluno voltar."""
    if until <= today:
        raise BillingError("a pausa precisa terminar no futuro")

    assinatura = subscription_of(session, student)
    if assinatura is None:
        raise BillingError("aluno sem assinatura")
    if assinatura.status == "cancelada":
        raise BillingError("assinatura cancelada não pausa")

    assinatura.status = "pausada"
    assinatura.paused_until = until
    student.subscription_status = "pausada"
    session.flush()
    return assinatura


def resume(session: Session, student: Student, today: date) -> Subscription:
    assinatura = subscription_of(session, student)
    if assinatura is None:
        raise BillingError("aluno sem assinatura")
    if assinatura.status != "pausada":
        return assinatura

    assinatura.paused_until = None
    vigente = assinatura.current_period_end is not None and assinatura.current_period_end >= today
    assinatura.status = "ativa" if vigente else "trial"
    if assinatura.status == "trial" and assinatura.trial_ends_on is None:
        assinatura.trial_ends_on = today + timedelta(days=TRIAL_DAYS)
    student.subscription_status = assinatura.status
    session.flush()
    return assinatura


def cancel(session: Session, student: Student, gateway: BillingGateway) -> Subscription:
    assinatura = subscription_of(session, student)
    if assinatura is None:
        raise BillingError("aluno sem assinatura")

    if assinatura.provider_ref:
        gateway.cancel(assinatura.provider_ref)
    assinatura.status = "cancelada"
    assinatura.canceled_at = datetime.now(UTC)
    student.subscription_status = "cancelada"
    session.flush()
    return assinatura


def handle_event(session: Session, event: GatewayEvent, gateway: BillingGateway) -> bool:
    """Aplica o evento do provedor. Webhook repetido não repete efeito."""
    ja_visto = session.scalar(
        select(PaymentEvent.id).where(
            PaymentEvent.provider == gateway.name,
            PaymentEvent.external_id == event.external_id,
        )
    )
    if ja_visto is not None:
        return False

    session.add(
        PaymentEvent(
            provider=gateway.name,
            external_id=event.external_id,
            kind=event.kind,
            payload=event.payload,
        )
    )

    assinatura = session.scalar(
        select(Subscription).where(Subscription.provider_ref == event.provider_ref)
    )
    if assinatura is not None:
        aluno = session.get(Student, assinatura.student_id)
        if event.kind == "pagamento_confirmado":
            assinatura.status = "ativa"
            periodo = event.payload.get("current_period_end")
            if isinstance(periodo, str):
                assinatura.current_period_end = date.fromisoformat(periodo)
        elif event.kind == "pagamento_falhou":
            assinatura.status = "atrasada"
        elif event.kind == "assinatura_cancelada":
            assinatura.status = "cancelada"
            assinatura.canceled_at = datetime.now(UTC)
        if aluno is not None:
            aluno.subscription_status = assinatura.status

    session.flush()
    return True
