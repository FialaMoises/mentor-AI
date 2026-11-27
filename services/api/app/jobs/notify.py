"""Job das notificações: a lista do dia, o aviso de estouro e o convite de recomeço.

Roda com `python -m app.jobs.notify`, de manhã. O relógio entra por parâmetro,
como no job noturno.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..clock import today_in
from ..db import SessionLocal
from ..models import Student, TargetExam
from ..notifications import Senders, notify_daily_list, notify_overflow, notify_restart
from ..params import engine_params
from ..planning import PlanningError, is_inactive, project


def run(
    session: Session, senders: Senders, today_for: Callable[[str], date] = today_in
) -> list[str]:
    alunos = list(
        session.scalars(
            select(Student)
            .join(TargetExam, TargetExam.student_id == Student.id)
            .where(TargetExam.is_primary.is_(True))
            .distinct()
        )
    )

    params = engine_params()
    resumos: list[str] = []
    for aluno in alunos:
        hoje = today_for(aluno.timezone)
        enviados: list[str] = []

        if notify_daily_list(session, aluno, hoje, senders):
            enviados.append("lista do dia")

        try:
            projecao = project(session, aluno, hoje).projection
        except PlanningError:
            projecao = None
        if projecao is not None and not projecao.fits:
            if notify_overflow(
                session,
                aluno,
                hoje,
                projecao.missing_minutes,
                projecao.extra_minutes_per_day,
                senders,
            ):
                enviados.append("aviso de estouro")

        if is_inactive(session, aluno, hoje, params) and notify_restart(
            session, aluno, hoje, senders
        ):
            enviados.append("recomeço")

        resumos.append(f"{aluno.id}: {', '.join(enviados) if enviados else 'nada a avisar'}")
    return resumos


def main() -> None:
    from ..deps import get_senders

    with SessionLocal() as session:
        resumos = run(session, get_senders())
        session.commit()
    for linha in resumos:
        print(linha)


if __name__ == "__main__":
    main()
