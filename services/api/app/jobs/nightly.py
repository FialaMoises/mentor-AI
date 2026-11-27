"""Job noturno: replaneja cada aluno depois que o dia dele fecha.

Roda com `python -m app.jobs.nightly`. O dia de hoje já passou para o aluno, e
o replanejamento começa em amanhã — a lista que ele abriu nunca muda embaixo
dele.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..clock import today_in
from ..db import SessionLocal
from ..models import Student, TargetExam
from ..planning import PlanningError, replan


def run(session: Session, today_for: Callable[[str], date] = today_in) -> list[str]:
    """Replaneja todos os alunos com prova principal. Devolve um resumo por aluno.

    `today_for` é o relógio, injetado: o job é a única peça que sabe que dia é
    hoje, e o teste troca essa função por uma data fixa.
    """
    alunos = list(
        session.scalars(
            select(Student)
            .join(TargetExam, TargetExam.student_id == Student.id)
            .where(TargetExam.is_primary.is_(True))
            .distinct()
        )
    )

    resumos: list[str] = []
    for aluno in alunos:
        hoje = today_for(aluno.timezone)
        try:
            resultado = replan(session, aluno, hoje, reason="job noturno")
        except PlanningError as erro:
            resumos.append(f"{aluno.id}: pulado ({erro})")
            continue
        resumos.append(f"{aluno.id}: {resultado.version.summary}")
    return resumos


def main() -> None:
    with SessionLocal() as session:
        resumos = run(session)
        session.commit()
    for linha in resumos:
        print(linha)
    print(f"{len(resumos)} alunos replanejados")


if __name__ == "__main__":
    main()
