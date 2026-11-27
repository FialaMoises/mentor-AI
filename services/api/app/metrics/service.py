"""Os números do piloto, tirados do histórico — não de contador paralelo.

As quatro perguntas da spec: quantos continuam na semana 3, quantas tarefas por
semana, quanto tempo até o primeiro plano e quantos lançam acertos.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import PlanVersion, ProgressEvent, Student, Subscription, Task

#: "Ativo na semana 3" = marcou alguma coisa entre o 15º e o 21º dia de conta.
WEEK_THREE_START = 14
WEEK_THREE_END = 21


@dataclass(frozen=True, slots=True)
class PilotMetrics:
    students: int
    reached_week_three: int
    active_week_three: int
    retention_week_three: float
    tasks_done_last_week: int
    tasks_done_per_active_student: float
    median_minutes_to_first_plan: float | None
    students_logging_answers: int
    answer_logging_rate: float
    by_subscription_status: dict[str, int]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _as_utc(momento: datetime) -> datetime:
    return momento if momento.tzinfo else momento.replace(tzinfo=UTC)


def _empty() -> PilotMetrics:
    return PilotMetrics(
        students=0,
        reached_week_three=0,
        active_week_three=0,
        retention_week_three=0.0,
        tasks_done_last_week=0,
        tasks_done_per_active_student=0.0,
        median_minutes_to_first_plan=None,
        students_logging_answers=0,
        answer_logging_rate=0.0,
        by_subscription_status={},
    )


def collect(session: Session, today: date) -> PilotMetrics:
    alunos = list(session.scalars(select(Student)))
    if not alunos:
        return _empty()

    eventos = session.execute(
        select(Task.student_id, ProgressEvent.occurred_at).join(
            ProgressEvent, ProgressEvent.task_id == Task.id
        )
    ).all()
    por_aluno: dict[object, list[datetime]] = {}
    for aluno_id, quando in eventos:
        if quando is not None:
            por_aluno.setdefault(aluno_id, []).append(_as_utc(quando))

    chegaram = 0
    ativos = 0
    for aluno in alunos:
        nascimento = _as_utc(aluno.created_at).date()
        if (today - nascimento).days < WEEK_THREE_START:
            continue
        chegaram += 1
        inicio = nascimento + timedelta(days=WEEK_THREE_START)
        fim = nascimento + timedelta(days=WEEK_THREE_END)
        if any(inicio <= q.date() <= fim for q in por_aluno.get(aluno.id, [])):
            ativos += 1

    desde = today - timedelta(days=7)
    feitas = (
        session.scalar(
            select(func.count())
            .select_from(Task)
            .where(Task.status == "feita", Task.day >= desde, Task.day <= today)
        )
        or 0
    )

    primeiros_planos = session.execute(
        select(PlanVersion.student_id, func.min(PlanVersion.created_at)).group_by(
            PlanVersion.student_id
        )
    ).all()
    nascimento_de = {a.id: _as_utc(a.created_at) for a in alunos}
    esperas = sorted(
        (_as_utc(quando) - nascimento_de[aluno]).total_seconds() / 60
        for aluno, quando in primeiros_planos
        if quando is not None and aluno in nascimento_de
    )
    mediana: float | None = None
    if esperas:
        meio = len(esperas) // 2
        mediana = esperas[meio] if len(esperas) % 2 else (esperas[meio - 1] + esperas[meio]) / 2

    com_acertos = {
        aluno
        for (aluno,) in session.execute(
            select(Task.student_id)
            .join(ProgressEvent, ProgressEvent.task_id == Task.id)
            .where(ProgressEvent.answered.is_not(None))
            .distinct()
        ).all()
    }

    status: dict[str, int] = {
        nome: quantidade
        for nome, quantidade in session.execute(
            select(Subscription.status, func.count()).group_by(Subscription.status)
        ).all()
    }

    return PilotMetrics(
        students=len(alunos),
        reached_week_three=chegaram,
        active_week_three=ativos,
        retention_week_three=(ativos / chegaram if chegaram else 0.0),
        tasks_done_last_week=feitas,
        tasks_done_per_active_student=(feitas / len(por_aluno) if por_aluno else 0.0),
        median_minutes_to_first_plan=mediana,
        students_logging_answers=len(com_acertos),
        answer_logging_rate=len(com_acertos) / len(alunos),
        by_subscription_status=status,
    )
