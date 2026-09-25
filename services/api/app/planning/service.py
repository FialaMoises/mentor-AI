"""A camada entre o banco e o motor.

O motor não conhece banco nem relógio: aqui os dados do aluno viram entrada
pura, o plano volta, e só então vira linha de tabela.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..engine import (
    DayCapacity,
    EngineParams,
    HorizonPlan,
    StudyMode,
    TaskKind,
    TopicState,
    plan_horizon,
    restart_capacities,
)
from ..models import (
    DailyCapacity,
    PlanVersion,
    Proficiency,
    ProgressEvent,
    Student,
    TargetExam,
    Task,
    TopicIncidence,
)

#: Usado enquanto o aluno não subiu rotina nenhuma (a fase 3 traz os uploads).
DEFAULT_FREE_MINUTES = 120


@dataclass(frozen=True, slots=True)
class ReplanResult:
    version: PlanVersion
    created: int
    removed: int
    plan: HorizonPlan

    @property
    def fits(self) -> bool:
        return self.plan.projection.fits


class PlanningError(RuntimeError):
    """O aluno não tem o mínimo para planejar (prova principal, por exemplo)."""


def primary_exam(session: Session, student: Student) -> TargetExam:
    alvo = session.scalar(
        select(TargetExam).where(
            TargetExam.student_id == student.id, TargetExam.is_primary.is_(True)
        )
    )
    if alvo is None:
        raise PlanningError("aluno sem prova principal")
    return alvo


def capacities_between(
    session: Session, student: Student, start: date, end: date
) -> list[DayCapacity]:
    """Capacidade dia a dia: a registrada quando existe, o padrão no resto."""
    registradas = {
        row.day: row
        for row in session.scalars(
            select(DailyCapacity).where(
                DailyCapacity.student_id == student.id,
                DailyCapacity.day >= start,
                DailyCapacity.day <= end,
            )
        )
    }
    dias: list[DayCapacity] = []
    dia = start
    while dia <= end:
        registrada = registradas.get(dia)
        dias.append(
            DayCapacity(day=dia, free_minutes=registrada.free_minutes, light=registrada.light)
            if registrada is not None
            else DayCapacity(day=dia, free_minutes=DEFAULT_FREE_MINUTES)
        )
        dia += timedelta(days=1)
    return dias


def topic_states(session: Session, student: Student, exam_id: object) -> dict[str, TopicState]:
    """O estado de cada tema que o aluno se autoavaliou, com o histórico dele."""
    proficiencias = list(
        session.scalars(select(Proficiency).where(Proficiency.student_id == student.id))
    )
    incidencias = {
        row.topic_id: row.weight
        for row in session.scalars(select(TopicIncidence).where(TopicIncidence.exam_id == exam_id))
    }

    feitas = list(
        session.scalars(select(Task).where(Task.student_id == student.id, Task.status == "feita"))
    )
    estudado_em: dict[object, date] = {}
    revisoes_feitas: dict[object, int] = {}
    for tarefa in feitas:
        if tarefa.kind == TaskKind.TEORIA.value:
            anterior = estudado_em.get(tarefa.topic_id)
            if anterior is None or tarefa.day > anterior:
                estudado_em[tarefa.topic_id] = tarefa.day
        elif tarefa.kind == TaskKind.REVISAO.value:
            revisoes_feitas[tarefa.topic_id] = revisoes_feitas.get(tarefa.topic_id, 0) + 1

    estados: dict[str, TopicState] = {}
    for proficiencia in proficiencias:
        estados[str(proficiencia.topic_id)] = TopicState(
            topic_id=str(proficiencia.topic_id),
            incidence=incidencias.get(proficiencia.topic_id, 1.0),
            self_assessment=proficiencia.self_assessment,
            answered=proficiencia.answered,
            correct=proficiencia.correct,
            studied_on=estudado_em.get(proficiencia.topic_id),
            reviews_done=revisoes_feitas.get(proficiencia.topic_id, 0),
        )
    return estados


def is_inactive(session: Session, student: Student, today: date, params: EngineParams) -> bool:
    """Sumiu? Nenhum evento de progresso nos últimos `inactivity_days` dias."""
    ultimo = session.scalar(
        select(ProgressEvent.occurred_at)
        .join(Task, Task.id == ProgressEvent.task_id)
        .where(Task.student_id == student.id)
        .order_by(ProgressEvent.occurred_at.desc())
    )
    if ultimo is None:
        return False
    return (today - ultimo.date()).days >= params.inactivity_days


def summarize(plan: HorizonPlan, created: int, removed: int, exam_date: date) -> str:
    if created == 0 and removed == 0:
        return "Nada mudou no plano."

    partes = [f"{created} tarefas replanejadas até {exam_date:%d/%m}"]
    if removed:
        partes.append(f"{removed} saíram do lugar antigo")
    if not plan.projection.fits:
        projecao = plan.projection
        partes.append(
            f"o conteúdo não cabe: faltam {projecao.missing_minutes} min — "
            f"somar {projecao.extra_minutes_per_day} min por dia ou "
            f"cortar {len(projecao.unscheduled_topics)} subtemas de menor peso"
        )
    return "; ".join(partes) + "."


def project(
    session: Session,
    student: Student,
    today: date,
    *,
    params: EngineParams | None = None,
    from_tomorrow: bool = True,
) -> HorizonPlan:
    """Monta o plano sem gravar nada — usado para responder 'isso cabe até a prova?'."""
    params = params or EngineParams()
    alvo = primary_exam(session, student)
    inicio = today + timedelta(days=1) if from_tomorrow else today

    capacidades = capacities_between(session, student, inicio, alvo.exam_date)
    if is_inactive(session, student, today, params):
        capacidades = restart_capacities(capacidades, params)

    return plan_horizon(
        capacidades,
        topic_states(session, student, alvo.exam_id),
        alvo.exam_date,
        params,
        mode=StudyMode(student.mode),
    )


def replan(
    session: Session,
    student: Student,
    today: date,
    *,
    reason: str = "replanejamento",
    params: EngineParams | None = None,
    from_tomorrow: bool = True,
) -> ReplanResult:
    """Recalcula o plano. O dia de hoje nunca é tocado quando `from_tomorrow`.

    Só tarefas pendentes são apagadas: o que o aluno marcou como feito ou como
    não deu é histórico e fica onde está.
    """
    params = params or EngineParams()
    alvo = primary_exam(session, student)
    inicio = today + timedelta(days=1) if from_tomorrow else today

    pendentes_antigas = list(
        session.scalars(
            select(Task.id).where(
                Task.student_id == student.id,
                Task.day >= inicio,
                Task.status == "pendente",
            )
        )
    )
    removidas = len(pendentes_antigas)
    if pendentes_antigas:
        session.execute(delete(Task).where(Task.id.in_(pendentes_antigas)))
    session.flush()

    plano = project(session, student, today, params=params, from_tomorrow=from_tomorrow)

    numero = (
        session.scalar(
            select(PlanVersion.number)
            .where(PlanVersion.student_id == student.id)
            .order_by(PlanVersion.number.desc())
        )
        or 0
    ) + 1
    versao = PlanVersion(
        student_id=student.id,
        number=numero,
        reason=reason,
        summary=summarize(plano, len(plano.tasks), removidas, alvo.exam_date),
    )
    session.add(versao)
    session.flush()

    por_dia: dict[date, int] = {}
    for tarefa in plano.tasks:
        posicao = por_dia.get(tarefa.day, 0)
        por_dia[tarefa.day] = posicao + 1
        session.add(
            Task(
                student_id=student.id,
                plan_version_id=versao.id,
                topic_id=uuid.UUID(tarefa.topic_id),
                kind=tarefa.kind.value,
                day=tarefa.day,
                minutes=tarefa.minutes,
                position=posicao,
                status="pendente",
            )
        )
    session.flush()

    return ReplanResult(version=versao, created=len(plano.tasks), removed=removidas, plan=plano)
