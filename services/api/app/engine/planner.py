"""Preenchimento do dia: heurística gulosa por prioridade.

Fase 0 entrega o preenchimento de um dia. Fase 2 estende para o horizonte
inteiro, revisões geradas e replanejamento noturno.
"""

from __future__ import annotations

from datetime import date

from .scoring import priority
from .types import LIGHT_DAY_KINDS, Candidate, DayCapacity, EngineParams, PlannedTask, TopicState


def fill_day(
    capacity: DayCapacity,
    candidates: list[Candidate],
    topics: dict[str, TopicState],
    exam_date: date,
    params: EngineParams | None = None,
) -> list[PlannedTask]:
    """Enche a capacidade do dia com as tarefas de maior prioridade.

    Determinístico: com a mesma entrada devolve exatamente o mesmo plano. O
    desempate é pelo par (tipo, tema), nunca pela ordem de chegada da lista.
    """
    params = params or EngineParams()

    for candidate in candidates:
        if candidate.topic_id not in topics:
            raise KeyError(f"tema sem estado: {candidate.topic_id}")

    allowed = [
        candidate
        for candidate in candidates
        if not capacity.light or candidate.kind in LIGHT_DAY_KINDS
    ]

    scored = [(priority(topics[c.topic_id], capacity.day, exam_date, params), c) for c in allowed]
    scored.sort(key=lambda pair: (-pair[0], pair[1].kind.value, pair[1].topic_id))

    plan: list[PlannedTask] = []
    remaining = capacity.free_minutes
    for score, candidate in scored:
        if candidate.minutes > remaining:
            continue
        remaining -= candidate.minutes
        plan.append(
            PlannedTask(
                day=capacity.day,
                topic_id=candidate.topic_id,
                kind=candidate.kind,
                minutes=candidate.minutes,
                priority=score,
            )
        )
    return plan
