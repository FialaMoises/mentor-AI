"""Marcar tarefa como feita ou não deu, inclusive o que foi marcado sem sinal.

A marcação carrega um id gerado no navegador. Reenviar a mesma marcação — o que
acontece toda vez que a fila offline sincroniza duas vezes — não vira dois
eventos de progresso.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Proficiency, ProgressEvent, Student, Task


@dataclass(frozen=True, slots=True)
class ProgressEntry:
    task_id: uuid.UUID
    action: str
    answered: int | None = None
    correct: int | None = None
    client_event_id: uuid.UUID | None = None
    occurred_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class SyncResult:
    applied: int
    duplicates: int
    unknown: int


class ProgressError(ValueError):
    pass


def _already_applied(session: Session, client_event_id: uuid.UUID | None) -> bool:
    if client_event_id is None:
        return False
    return (
        session.scalar(
            select(ProgressEvent.id).where(ProgressEvent.client_event_id == client_event_id)
        )
        is not None
    )


def apply_progress(
    session: Session,
    task: Task,
    *,
    action: str,
    answered: int | None = None,
    correct: int | None = None,
    client_event_id: uuid.UUID | None = None,
    occurred_at: datetime | None = None,
) -> bool:
    """Devolve False quando a marcação já tinha sido aplicada antes."""
    if answered is not None and correct is not None and correct > answered:
        raise ProgressError("acertos não podem passar das questões feitas")
    if _already_applied(session, client_event_id):
        return False

    task.status = action
    evento = ProgressEvent(
        task_id=task.id,
        action=action,
        answered=answered,
        correct=correct,
        client_event_id=client_event_id,
    )
    if occurred_at is not None:
        evento.occurred_at = occurred_at
    session.add(evento)

    if answered:
        proficiencia = session.scalar(
            select(Proficiency).where(
                Proficiency.student_id == task.student_id,
                Proficiency.topic_id == task.topic_id,
            )
        )
        if proficiencia is not None:
            proficiencia.answered += answered
            proficiencia.correct += correct or 0

    session.flush()
    return True


#: Marcação sem hora vai para o fim da fila, e nunca mistura ingênuo com com-fuso.
_SEM_HORA = datetime.max.replace(tzinfo=UTC)


def _quando(entry: ProgressEntry) -> datetime:
    momento = entry.occurred_at
    if momento is None:
        return _SEM_HORA
    return momento if momento.tzinfo else momento.replace(tzinfo=UTC)


def sync(session: Session, student: Student, entries: list[ProgressEntry]) -> SyncResult:
    """A fila que o navegador acumulou offline, aplicada em ordem de acontecimento."""
    aplicadas = duplicadas = desconhecidas = 0

    for entrada in sorted(entries, key=_quando):
        tarefa = session.get(Task, entrada.task_id)
        if tarefa is None or tarefa.student_id != student.id:
            desconhecidas += 1
            continue
        if apply_progress(
            session,
            tarefa,
            action=entrada.action,
            answered=entrada.answered,
            correct=entrada.correct,
            client_event_id=entrada.client_event_id,
            occurred_at=entrada.occurred_at,
        ):
            aplicadas += 1
        else:
            duplicadas += 1

    return SyncResult(applied=aplicadas, duplicates=duplicadas, unknown=desconhecidas)
