"""Proficiência, urgência e prioridade — as três contas do motor."""

from __future__ import annotations

from datetime import date

from .types import EngineParams, TopicState


def proficiency(state: TopicState, params: EngineParams) -> float:
    """proficiência = (k·a + c) / (k + n).

    A autoavaliação `a` vale como `k` questões e perde peso conforme as questões
    reais entram. Sem nenhuma questão feita, a proficiência é a autoavaliação.
    """
    k = params.k
    return (k * state.self_assessment + state.correct) / (k + state.answered)


def urgency(state: TopicState, day: date, exam_date: date, params: EngineParams) -> float:
    """Sobe conforme a prova principal se aproxima e com revisão vencida.

    Vale 1.0 no horizonte inteiro e cresce até 2.0 na véspera; revisão vencida
    soma 0.5 por semana de atraso, limitada a 1.0.
    """
    days_left = (exam_date - day).days
    if days_left <= 0:
        proximity = 2.0
    else:
        horizon = params.exam_horizon_days
        proximity = 1.0 + max(0.0, (horizon - days_left) / horizon)

    overdue = 0.0
    if state.review_due_days is not None and state.review_due_days > 0:
        overdue = min(1.0, 0.5 * state.review_due_days / 7)

    return proximity + overdue


def priority(state: TopicState, day: date, exam_date: date, params: EngineParams) -> float:
    """prioridade = incidência × (1 − proficiência) × urgência."""
    return (
        state.incidence
        * (1.0 - proficiency(state, params))
        * urgency(state, day, exam_date, params)
    )
