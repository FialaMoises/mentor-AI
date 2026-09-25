from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.engine import EngineParams
from app.jobs.nightly import run as run_nightly
from app.models import DailyCapacity, PlanVersion, ProgressEvent, Student, TargetExam, Task
from app.planning import DEFAULT_FREE_MINUTES, PlanningError, capacities_between, replan
from app.seed import SEED_STUDENT_ID
from app.seed import run as seed

HOJE = date(2026, 9, 25)
PARAMS = EngineParams()


@pytest.fixture
def aluno(session: Session) -> Student:
    seed(session, today=HOJE)
    session.flush()
    student = session.get(Student, SEED_STUDENT_ID)
    assert student is not None
    return student


def tarefas_de(session: Session, student: Student, dia: date) -> list[Task]:
    return list(
        session.scalars(
            select(Task)
            .where(Task.student_id == student.id, Task.day == dia)
            .order_by(Task.position)
        )
    )


def test_replanejamento_nao_toca_no_dia_de_hoje(session: Session, aluno: Student) -> None:
    antes = [(t.id, t.kind, t.topic_id, t.status) for t in tarefas_de(session, aluno, HOJE)]
    assert antes

    replan(session, aluno, HOJE, params=PARAMS)
    session.flush()

    depois = [(t.id, t.kind, t.topic_id, t.status) for t in tarefas_de(session, aluno, HOJE)]
    assert depois == antes


def test_replanejamento_preenche_os_dias_seguintes_ate_a_prova(
    session: Session, aluno: Student
) -> None:
    resultado = replan(session, aluno, HOJE, params=PARAMS)
    session.flush()

    alvo = session.scalar(select(TargetExam).where(TargetExam.student_id == aluno.id))
    assert alvo is not None
    futuras = list(
        session.scalars(select(Task).where(Task.student_id == aluno.id, Task.day > HOJE))
    )
    assert futuras
    assert resultado.created == len(futuras)
    assert all(HOJE < t.day <= alvo.exam_date for t in futuras)


def test_cada_replanejamento_gera_uma_versao_com_resumo(session: Session, aluno: Student) -> None:
    resultado = replan(session, aluno, HOJE, params=PARAMS)
    session.flush()

    versoes = list(session.scalars(select(PlanVersion).where(PlanVersion.student_id == aluno.id)))
    assert len(versoes) == 2  # a do seed e a do replanejamento
    assert resultado.version.number == 2
    assert resultado.version.reason == "replanejamento"
    assert "replanejadas" in resultado.version.summary


def test_tarefa_feita_no_futuro_sobrevive_ao_replanejamento(
    session: Session, aluno: Student
) -> None:
    replan(session, aluno, HOJE, params=PARAMS)
    session.flush()
    amanha = HOJE + timedelta(days=1)
    tarefa = tarefas_de(session, aluno, amanha)[0]
    tarefa.status = "feita"
    session.flush()

    replan(session, aluno, HOJE, params=PARAMS)
    session.flush()

    assert session.get(Task, tarefa.id) is not None


def test_replanejar_duas_vezes_seguidas_nao_duplica_o_futuro(
    session: Session, aluno: Student
) -> None:
    primeiro = replan(session, aluno, HOJE, params=PARAMS)
    session.flush()
    segundo = replan(session, aluno, HOJE, params=PARAMS)
    session.flush()

    assert primeiro.created == segundo.created


def test_aluno_sem_prova_principal_nao_e_planejado(session: Session, aluno: Student) -> None:
    alvo = session.scalar(select(TargetExam).where(TargetExam.student_id == aluno.id))
    assert alvo is not None
    alvo.is_primary = False
    session.flush()

    with pytest.raises(PlanningError):
        replan(session, aluno, HOJE, params=PARAMS)


def test_capacidade_registrada_vence_o_padrao(session: Session, aluno: Student) -> None:
    amanha = HOJE + timedelta(days=1)
    session.add(DailyCapacity(student_id=aluno.id, day=amanha, free_minutes=15, light=True))
    session.flush()

    dias = capacities_between(session, aluno, HOJE, HOJE + timedelta(days=2))

    por_dia = {d.day: d for d in dias}
    assert por_dia[amanha].free_minutes == 15
    assert por_dia[amanha].light is True
    assert por_dia[HOJE + timedelta(days=2)].free_minutes == DEFAULT_FREE_MINUTES


def test_aluno_sumido_volta_com_carga_reduzida(session: Session, aluno: Student) -> None:
    tarefa = tarefas_de(session, aluno, HOJE)[0]
    session.add(
        ProgressEvent(
            task_id=tarefa.id,
            action="feita",
            occurred_at=datetime(2026, 9, 10, tzinfo=UTC),
        )
    )
    session.flush()

    replan(session, aluno, HOJE, params=PARAMS)
    session.flush()

    amanha = HOJE + timedelta(days=1)
    minutos = sum(t.minutes for t in tarefas_de(session, aluno, amanha))
    assert minutos <= DEFAULT_FREE_MINUTES * PARAMS.restart_floor


def test_job_noturno_replaneja_quem_tem_prova_principal(session: Session, aluno: Student) -> None:
    resumos = run_nightly(session, today_for=lambda _tz: HOJE)
    session.flush()

    assert len(resumos) == 1
    assert str(aluno.id) in resumos[0]
    assert list(session.scalars(select(Task).where(Task.day > HOJE)))


def test_job_noturno_usa_o_fuso_do_aluno_para_saber_que_dia_e(
    session: Session, aluno: Student
) -> None:
    fusos: list[str] = []

    def relogio(timezone_do_aluno: str) -> date:
        fusos.append(timezone_do_aluno)
        return HOJE

    run_nightly(session, today_for=relogio)

    assert fusos == [aluno.timezone]
