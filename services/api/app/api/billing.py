"""Assinatura: começar, pausar, retomar, cancelar — e o webhook do provedor."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..billing import (
    BillingError,
    BillingGateway,
    cancel,
    checkout,
    handle_event,
    has_access,
    pause,
    resume,
    subscription_of,
)
from ..clock import today_in
from ..config import get_settings
from ..db import get_session
from ..deps import current_student, get_gateway
from ..models import Student

router = APIRouter(prefix="/api/v1")

UNPROCESSABLE = 422


class SubscriptionOut(BaseModel):
    status: str
    plan: str
    price_cents: int
    trial_ends_on: date | None
    current_period_end: date | None
    paused_until: date | None
    has_access: bool


class CheckoutIn(BaseModel):
    plan: Literal["mensal", "anual"] = "mensal"


class CheckoutOut(BaseModel):
    url: str
    plan: str
    price_cents: int


class PauseIn(BaseModel):
    until: date


def _out(session: Session, student: Student, today: date) -> SubscriptionOut:
    assinatura = subscription_of(session, student)
    if assinatura is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "aluno sem assinatura")
    return SubscriptionOut(
        status=assinatura.status,
        plan=assinatura.plan,
        price_cents=assinatura.price_cents,
        trial_ends_on=assinatura.trial_ends_on,
        current_period_end=assinatura.current_period_end,
        paused_until=assinatura.paused_until,
        has_access=has_access(session, student, today),
    )


@router.get("/me/subscription", response_model=SubscriptionOut)
def get_subscription(
    student: Annotated[Student, Depends(current_student)],
    session: Annotated[Session, Depends(get_session)],
) -> SubscriptionOut:
    return _out(session, student, today_in(student.timezone))


@router.post("/me/subscription/checkout", response_model=CheckoutOut)
def post_checkout(
    payload: CheckoutIn,
    student: Annotated[Student, Depends(current_student)],
    session: Annotated[Session, Depends(get_session)],
    gateway: Annotated[BillingGateway, Depends(get_gateway)],
) -> CheckoutOut:
    """Devolve para onde mandar o aluno pagar. Nenhum dado de cartão passa por aqui."""
    settings = get_settings()
    preco = (
        settings.price_monthly_cents if payload.plan == "mensal" else settings.price_annual_cents
    )
    try:
        resultado = checkout(
            session,
            student,
            plan=payload.plan,
            price_cents=preco,
            gateway=gateway,
            today=today_in(student.timezone),
        )
    except BillingError as erro:
        raise HTTPException(UNPROCESSABLE, str(erro)) from erro

    return CheckoutOut(url=resultado.url, plan=payload.plan, price_cents=preco)


@router.post("/me/subscription/pause", response_model=SubscriptionOut)
def post_pause(
    payload: PauseIn,
    student: Annotated[Student, Depends(current_student)],
    session: Annotated[Session, Depends(get_session)],
) -> SubscriptionOut:
    hoje = today_in(student.timezone)
    try:
        pause(session, student, until=payload.until, today=hoje)
    except BillingError as erro:
        raise HTTPException(UNPROCESSABLE, str(erro)) from erro
    return _out(session, student, hoje)


@router.post("/me/subscription/resume", response_model=SubscriptionOut)
def post_resume(
    student: Annotated[Student, Depends(current_student)],
    session: Annotated[Session, Depends(get_session)],
) -> SubscriptionOut:
    hoje = today_in(student.timezone)
    try:
        resume(session, student, hoje)
    except BillingError as erro:
        raise HTTPException(UNPROCESSABLE, str(erro)) from erro
    return _out(session, student, hoje)


@router.post("/me/subscription/cancel", response_model=SubscriptionOut)
def post_cancel(
    student: Annotated[Student, Depends(current_student)],
    session: Annotated[Session, Depends(get_session)],
    gateway: Annotated[BillingGateway, Depends(get_gateway)],
) -> SubscriptionOut:
    try:
        cancel(session, student, gateway)
    except BillingError as erro:
        raise HTTPException(UNPROCESSABLE, str(erro)) from erro
    return _out(session, student, today_in(student.timezone))


@router.post("/billing/webhook")
async def post_webhook(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    gateway: Annotated[BillingGateway, Depends(get_gateway)],
    x_signature: Annotated[str | None, Header()] = None,
) -> dict[str, bool]:
    """Evento do provedor. Assinatura conferida; evento repetido não repete efeito."""
    corpo = await request.body()
    try:
        evento = gateway.parse_event(corpo, x_signature or "")
    except BillingError as erro:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(erro)) from erro
    except (KeyError, ValueError) as erro:
        raise HTTPException(UNPROCESSABLE, "evento mal formado") from erro

    aplicado = handle_event(session, evento, gateway)
    return {"applied": aplicado}
