from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Proficiency, ProgressEvent, Student, Task
from app.progress import ProgressEntry, ProgressError, apply_progress, sync
from app.seed import SEED_STUDENT_ID
from app.seed import run as seed

HOJE = date(2026, 9, 25)


@pytest.fixture
def aluno(session: Session) -> Student:
    seed(session, today=HOJE)
    session.flush()
    student = session.get(Student, SEED_STUDENT_ID)
    assert student is not None
    return student


def tarefas(session: Session, aluno: Student) -> list[Task]:
    return list(
        session.scalars(
            select(Task)
            .where(Task.student_id == aluno.id, Task.day == HOJE)
            .order_by(Task.position)
        )
    )


def test_marcacao_reenviada_nao_vira_dois_eventos(session: Session, aluno: Student) -> None:
    tarefa = tarefas(session, aluno)[0]
    evento_id = uuid.uuid4()

    primeira = apply_progress(session, tarefa, action="feita", client_event_id=evento_id)
    segunda = apply_progress(session, tarefa, action="feita", client_event_id=evento_id)

    assert (primeira, segunda) == (True, False)
    eventos = list(session.scalars(select(ProgressEvent).where(ProgressEvent.task_id == tarefa.id)))
    assert len(eventos) == 1


def test_marcacao_sem_id_do_cliente_sempre_aplica(session: Session, aluno: Student) -> None:
    tarefa = tarefas(session, aluno)[0]

    apply_progress(session, tarefa, action="feita")
    apply_progress(session, tarefa, action="nao_deu")

    eventos = list(session.scalars(select(ProgressEvent).where(ProgressEvent.task_id == tarefa.id)))
    assert [e.action for e in eventos] == ["feita", "nao_deu"]
    assert tarefa.status == "nao_deu"


def test_acertos_acima_das_questoes_sao_recusados(session: Session, aluno: Student) -> None:
    tarefa = tarefas(session, aluno)[0]

    with pytest.raises(ProgressError):
        apply_progress(session, tarefa, action="feita", answered=5, correct=9)


def test_fila_offline_aplica_na_ordem_em_que_aconteceu(session: Session, aluno: Student) -> None:
    lista = tarefas(session, aluno)
    agora = datetime(2026, 9, 25, 20, tzinfo=UTC)
    entradas = [
        ProgressEntry(
            task_id=lista[1].id,
            action="feita",
            client_event_id=uuid.uuid4(),
            occurred_at=agora,
        ),
        ProgressEntry(
            task_id=lista[0].id,
            action="feita",
            client_event_id=uuid.uuid4(),
            occurred_at=agora - timedelta(hours=2),
        ),
    ]

    resultado = sync(session, aluno, entradas)
    session.flush()

    assert resultado.applied == 2
    eventos = list(session.scalars(select(ProgressEvent).order_by(ProgressEvent.occurred_at)))
    assert [e.task_id for e in eventos] == [lista[0].id, lista[1].id]


def test_fila_reenviada_inteira_nao_duplica_nada(session: Session, aluno: Student) -> None:
    lista = tarefas(session, aluno)
    entradas = [
        ProgressEntry(task_id=t.id, action="feita", client_event_id=uuid.uuid4()) for t in lista[:2]
    ]

    primeira = sync(session, aluno, entradas)
    segunda = sync(session, aluno, entradas)
    session.flush()

    assert (primeira.applied, primeira.duplicates) == (2, 0)
    assert (segunda.applied, segunda.duplicates) == (0, 2)
    assert len(list(session.scalars(select(ProgressEvent)))) == 2


def test_tarefa_de_outro_aluno_e_ignorada_na_sincronizacao(
    session: Session, aluno: Student
) -> None:
    outro = Student(phase="formado", mode="independente")
    session.add(outro)
    session.flush()
    tarefa = tarefas(session, aluno)[0]

    resultado = sync(
        session,
        outro,
        [ProgressEntry(task_id=tarefa.id, action="feita", client_event_id=uuid.uuid4())],
    )

    assert (resultado.applied, resultado.unknown) == (0, 1)
    assert tarefa.status == "pendente"


def test_acertos_da_fila_somam_na_proficiencia(session: Session, aluno: Student) -> None:
    tarefa = next(t for t in tarefas(session, aluno) if t.kind == "questoes")

    sync(
        session,
        aluno,
        [
            ProgressEntry(
                task_id=tarefa.id,
                action="feita",
                answered=20,
                correct=13,
                client_event_id=uuid.uuid4(),
            )
        ],
    )
    session.flush()

    proficiencia = session.scalar(
        select(Proficiency).where(
            Proficiency.student_id == aluno.id, Proficiency.topic_id == tarefa.topic_id
        )
    )
    assert proficiencia is not None
    assert (proficiencia.answered, proficiencia.correct) == (20, 13)


def test_sincronizacao_pela_api_devolve_a_contagem(
    client: TestClient,
    session: Session,
    aluno: Student,
    login,  # type: ignore[no-untyped-def]
) -> None:
    session.commit()
    cabecalho = login(aluno)
    tarefa = tarefas(session, aluno)[0]
    entrada = {
        "task_id": str(tarefa.id),
        "action": "feita",
        "client_event_id": str(uuid.uuid4()),
    }

    primeira = client.post(
        "/api/v1/me/progress/sync", json={"entries": [entrada]}, headers=cabecalho
    ).json()
    segunda = client.post(
        "/api/v1/me/progress/sync", json={"entries": [entrada]}, headers=cabecalho
    ).json()

    assert primeira == {"applied": 1, "duplicates": 0, "unknown": 0}
    assert segunda == {"applied": 0, "duplicates": 1, "unknown": 0}


def test_fila_mistura_marcacao_com_e_sem_hora_sem_quebrar(session: Session, aluno: Student) -> None:
    lista = tarefas(session, aluno)
    entradas = [
        ProgressEntry(task_id=lista[0].id, action="feita", client_event_id=uuid.uuid4()),
        ProgressEntry(
            task_id=lista[1].id,
            action="feita",
            client_event_id=uuid.uuid4(),
            occurred_at=datetime(2026, 9, 25, 9, tzinfo=UTC),
        ),
        ProgressEntry(
            task_id=lista[2].id,
            action="feita",
            client_event_id=uuid.uuid4(),
            occurred_at=datetime(2026, 9, 25, 8),
        ),
    ]

    resultado = sync(session, aluno, entradas)

    assert resultado.applied == 3
