"""Marcar tarefa como feita ou não deu, inclusive o que foi marcado sem sinal.

A marcação carrega um id gerado no navegador. Reenviar a mesma marcação — o que
acontece toda vez que a fila offline sincroniza duas vezes — não vira dois
eventos de progresso.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..clock import now_utc
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
    #: Entradas que o servidor recusou de vez (acertos acima das questões, por exemplo).
    rejected: int = 0
    #: Marcações mais velhas que a última da tarefa: guardadas só como histórico.
    stale: int = 0


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
    return (
        _apply(
            session,
            task,
            action=action,
            answered=answered,
            correct=correct,
            client_event_id=client_event_id,
            occurred_at=occurred_at,
        )
        != "duplicada"
    )


def _apply(
    session: Session,
    task: Task,
    *,
    action: str,
    answered: int | None,
    correct: int | None,
    client_event_id: uuid.UUID | None,
    occurred_at: datetime | None,
) -> Literal["aplicada", "duplicada", "historico"]:
    if answered is not None and correct is not None and correct > answered:
        raise ProgressError("acertos não podem passar das questões feitas")
    if _already_applied(session, client_event_id):
        return "duplicada"

    if occurred_at is not None and _newer_event_exists(session, task, occurred_at):
        # Marcação da fila offline mais velha que a última gravada: vira histórico,
        # sem mudar o status nem a proficiência que a marcação nova definiu.
        session.add(
            ProgressEvent(
                task_id=task.id,
                action=action,
                answered=answered,
                correct=correct,
                client_event_id=client_event_id,
                occurred_at=occurred_at,
            )
        )
        session.flush()
        return "historico"

    proficiencia = _proficiency_of(session, task)
    if proficiencia is not None:
        # Remarcar a tarefa substitui o lançamento anterior, não soma por cima.
        anterior = _counted_launch(session, task)
        if anterior is not None:
            proficiencia.answered = max(0, proficiencia.answered - (anterior.answered or 0))
            proficiencia.correct = max(0, proficiencia.correct - (anterior.correct or 0))
        if action == "feita" and answered:
            proficiencia.answered += answered
            proficiencia.correct += correct or 0

    task.status = action
    evento = ProgressEvent(
        task_id=task.id,
        action=action,
        answered=answered,
        correct=correct,
        client_event_id=client_event_id,
    )
    # Sem hora do cliente, o carimbo vem do relógio da borda: a ordem dos eventos
    # da mesma tarefa decide qual lançamento está valendo.
    evento.occurred_at = occurred_at if occurred_at is not None else now_utc()
    session.add(evento)
    session.flush()
    return "aplicada"


def _utc(momento: datetime) -> datetime:
    return momento if momento.tzinfo else momento.replace(tzinfo=UTC)


def _newer_event_exists(session: Session, task: Task, occurred_at: datetime) -> bool:
    ultimo = session.scalar(
        select(ProgressEvent.occurred_at)
        .where(ProgressEvent.task_id == task.id)
        .order_by(ProgressEvent.occurred_at.desc())
        .limit(1)
    )
    return ultimo is not None and _utc(ultimo) > _utc(occurred_at)


def _proficiency_of(session: Session, task: Task) -> Proficiency | None:
    return session.scalar(
        select(Proficiency).where(
            Proficiency.student_id == task.student_id,
            Proficiency.topic_id == task.topic_id,
        )
    )


def _counted_launch(session: Session, task: Task) -> ProgressEvent | None:
    """O lançamento de questões que está contando na proficiência desta tarefa.

    Só a marcação "feita" mais recente conta; depois de um "não deu", nenhuma.
    """
    if task.status != "feita":
        return None
    return session.scalar(
        select(ProgressEvent)
        .where(ProgressEvent.task_id == task.id, ProgressEvent.action == "feita")
        .order_by(ProgressEvent.occurred_at.desc())
        .limit(1)
    )


#: Marcação sem hora vai para o fim da fila, e nunca mistura ingênuo com com-fuso.
_SEM_HORA = datetime.max.replace(tzinfo=UTC)


def _quando(entry: ProgressEntry) -> datetime:
    momento = entry.occurred_at
    if momento is None:
        return _SEM_HORA
    return momento if momento.tzinfo else momento.replace(tzinfo=UTC)


def sync(session: Session, student: Student, entries: list[ProgressEntry]) -> SyncResult:
    """A fila que o navegador acumulou offline, aplicada em ordem de acontecimento."""
    aplicadas = duplicadas = desconhecidas = recusadas = antigas = 0
    # Relógio do aparelho adiantado: o que vem do futuro vale como agora, senão uma
    # data de 2099 deixaria a tarefa travada para todas as marcações seguintes.
    agora = now_utc()

    for entrada in sorted(entries, key=_quando):
        tarefa = session.get(Task, entrada.task_id)
        if tarefa is None or tarefa.student_id != student.id:
            desconhecidas += 1
            continue
        quando = entrada.occurred_at
        if quando is not None and _utc(quando) > agora:
            quando = agora
        try:
            resultado = _apply(
                session,
                tarefa,
                action=entrada.action,
                answered=entrada.answered,
                correct=entrada.correct,
                client_event_id=entrada.client_event_id,
                occurred_at=quando,
            )
        except ProgressError:
            # Uma entrada ruim não trava a fila: é recusada de vez e as outras seguem.
            recusadas += 1
            continue
        if resultado == "aplicada":
            aplicadas += 1
        elif resultado == "historico":
            antigas += 1
        else:
            duplicadas += 1

    return SyncResult(
        applied=aplicadas,
        duplicates=duplicadas,
        unknown=desconhecidas,
        rejected=recusadas,
        stale=antigas,
    )
