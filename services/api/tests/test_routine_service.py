from __future__ import annotations

import uuid
from datetime import date, time, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.documents import confirm, erase, record_consent, upload
from app.extraction import RoutineExtraction
from app.models import Commitment, DailyCapacity, PlanVersion, Student, TargetExam, Task
from app.routine import (
    RoutineError,
    SeriesInput,
    SeriesNotFound,
    create_series,
    delete_series,
    update_series,
    week_view,
)
from app.seed import SEED_STUDENT_ID
from app.seed import run as seed
from app.storage import InMemoryStore

HOJE = date(2026, 9, 25)  # sexta
AMANHA = HOJE + timedelta(days=1)
SEGUNDA_SEGUINTE = date(2026, 9, 28)
SEMANA_ATUAL = date(2026, 9, 21)
PDF = b"%PDF-1.7\n" + b"0" * 500


def academia(**mudancas: object) -> SeriesInput:
    base: dict[str, object] = {
        "kind": "academia",
        "label": "Musculação",
        "weekdays": (0, 2, 4),
        "on_day": None,
        "starts_at": time(18, 0),
        "duration_minutes": 75,
    }
    base.update(mudancas)
    return SeriesInput(**base)  # type: ignore[arg-type]


@pytest.fixture
def aluno(session: Session) -> Student:
    seed(session, today=HOJE)
    session.flush()
    student = session.get(Student, SEED_STUDENT_ID)
    assert student is not None
    return student


@pytest.fixture
def sem_prova(session: Session) -> Student:
    student = Student(phase="formado", mode="independente", timezone="America/Fortaleza")
    session.add(student)
    session.flush()
    return student


def da_serie(session: Session, serie: uuid.UUID) -> list[Commitment]:
    return list(session.scalars(select(Commitment).where(Commitment.series_id == serie)))


def vigentes(session: Session, serie: uuid.UUID) -> list[Commitment]:
    return [c for c in da_serie(session, serie) if c.ends_on is None or c.ends_on > HOJE]


def test_criar_serie_semanal_grava_um_registro_por_dia_comecando_amanha(
    session: Session, aluno: Student
) -> None:
    resultado = create_series(session, aluno, academia(), today=HOJE)

    assert resultado.series_id is not None
    registros = da_serie(session, resultado.series_id)
    assert sorted(c.weekday for c in registros if c.weekday is not None) == [0, 2, 4]
    assert {c.starts_on for c in registros} == {AMANHA}
    assert all(c.document_id is None for c in registros)
    assert all(c.starts_at == time(18, 0) for c in registros)


def test_criar_recalcula_de_amanha_e_nao_toca_hoje(session: Session, aluno: Student) -> None:
    hoje_antes = session.scalar(
        select(DailyCapacity).where(DailyCapacity.student_id == aluno.id, DailyCapacity.day == HOJE)
    )
    assert hoje_antes is not None
    minutos_de_hoje = hoje_antes.free_minutes
    tarefas_de_hoje = {
        t.id
        for t in session.scalars(select(Task).where(Task.student_id == aluno.id, Task.day == HOJE))
    }

    resultado = create_series(
        session, aluno, academia(weekdays=(0,), duration_minutes=600), today=HOJE
    )

    assert resultado.replan_summary
    assert hoje_antes.free_minutes == minutos_de_hoje
    assert {
        t.id
        for t in session.scalars(select(Task).where(Task.student_id == aluno.id, Task.day == HOJE))
    } == tarefas_de_hoje
    segunda = session.scalar(
        select(DailyCapacity).where(
            DailyCapacity.student_id == aluno.id, DailyCapacity.day == SEGUNDA_SEGUINTE
        )
    )
    assert segunda is not None and segunda.free_minutes == 0


def test_editar_fecha_a_vigencia_e_abre_outra_na_mesma_serie(
    session: Session, aluno: Student
) -> None:
    serie = create_series(session, aluno, academia(starts_on=date(2026, 9, 1)), today=HOJE)
    assert serie.series_id is not None
    # A série já estava valendo: simula um registro que começou antes de hoje.
    for registro in da_serie(session, serie.series_id):
        registro.starts_on = date(2026, 9, 1)
    session.flush()

    resultado = update_series(
        session, aluno, serie.series_id, academia(starts_at=time(7, 0)), today=HOJE
    )

    assert resultado.series_id == serie.series_id
    registros = da_serie(session, serie.series_id)
    antigos = [c for c in registros if c.starts_at == time(18, 0)]
    novos = [c for c in registros if c.starts_at == time(7, 0)]
    assert len(antigos) == 3 and all(c.ends_on == HOJE for c in antigos)
    assert len(novos) == 3 and all(c.starts_on == AMANHA for c in novos)


def test_desmarcar_um_dia_nao_recria_esse_dia(session: Session, aluno: Student) -> None:
    serie = create_series(session, aluno, academia(), today=HOJE)
    assert serie.series_id is not None

    update_series(session, aluno, serie.series_id, academia(weekdays=(0, 4)), today=HOJE)

    assert sorted(c.weekday for c in vigentes(session, serie.series_id)) == [0, 4]


def test_apagar_preserva_semanas_passadas(session: Session, aluno: Student) -> None:
    serie = create_series(session, aluno, academia(), today=HOJE)
    assert serie.series_id is not None
    for registro in da_serie(session, serie.series_id):
        registro.starts_on = date(2026, 9, 1)
    session.flush()

    resultado = delete_series(session, aluno, serie.series_id, today=HOJE)

    assert resultado.series_id is None
    passada = week_view(session, aluno, SEMANA_ATUAL, today=HOJE)
    seguinte = week_view(session, aluno, SEGUNDA_SEGUINTE, today=HOJE)
    assert any(item.label == "Musculação" for dia in passada.days for item in dia.items)
    assert not any(item.label == "Musculação" for dia in seguinte.days for item in dia.items)


def test_serie_que_ainda_nao_comecou_e_apagada_de_verdade(session: Session, aluno: Student) -> None:
    serie = create_series(session, aluno, academia(), today=HOJE)
    assert serie.series_id is not None

    delete_series(session, aluno, serie.series_id, today=HOJE)

    assert da_serie(session, serie.series_id) == []


def test_data_unica_de_hoje_nao_se_edita(session: Session, aluno: Student) -> None:
    dentista = Commitment(
        student_id=aluno.id,
        kind="outro",
        label="Dentista",
        on_day=HOJE,
        duration_minutes=60,
        series_id=uuid.uuid4(),
    )
    session.add(dentista)
    session.flush()
    assert dentista.series_id is not None

    with pytest.raises(RoutineError):
        delete_series(session, aluno, dentista.series_id, today=HOJE)


def test_data_unica_futura_e_criada_e_editada_direto(session: Session, aluno: Student) -> None:
    entrada = academia(kind="outro", label="Dentista", weekdays=(), on_day=date(2026, 10, 8))
    serie = create_series(session, aluno, entrada, today=HOJE)
    assert serie.series_id is not None

    update_series(
        session,
        aluno,
        serie.series_id,
        academia(kind="outro", label="Dentista", weekdays=(), on_day=date(2026, 10, 9)),
        today=HOJE,
    )

    registros = da_serie(session, serie.series_id)
    assert [c.on_day for c in registros] == [date(2026, 10, 9)]


def test_data_unica_no_passado_e_recusada_na_criacao(session: Session, aluno: Student) -> None:
    with pytest.raises(RoutineError):
        create_series(session, aluno, academia(weekdays=(), on_day=HOJE), today=HOJE)


def test_semanal_e_data_unica_juntos_sao_recusados(session: Session, aluno: Student) -> None:
    with pytest.raises(RoutineError):
        create_series(session, aluno, academia(on_day=date(2026, 10, 8)), today=HOJE)


def test_serie_de_outro_aluno_nao_e_encontrada(
    session: Session, aluno: Student, sem_prova: Student
) -> None:
    serie = create_series(session, aluno, academia(), today=HOJE)
    assert serie.series_id is not None

    with pytest.raises(SeriesNotFound):
        update_series(session, sem_prova, serie.series_id, academia(), today=HOJE)
    with pytest.raises(SeriesNotFound):
        delete_series(session, sem_prova, serie.series_id, today=HOJE)


def _bloco_de_arquivo(session: Session, aluno: Student) -> tuple[uuid.UUID, uuid.UUID]:
    record_consent(session, aluno)
    store = InMemoryStore()
    documento = upload(
        session,
        aluno,
        content=PDF,
        content_type="application/pdf",
        filename="grade.pdf",
        kind="grade",
        store=store,
    )
    extracao = RoutineExtraction.model_validate(
        {
            "commitments": [
                {
                    "kind": "aula",
                    "label": "Enfermaria",
                    "weekday": d,
                    "duration_minutes": 360,
                    "starts_at": "07:00",
                    "starts_on": "2026-09-01",
                }
                for d in range(5)
            ],
            "exams": [],
            "unreadable": [],
        }
    )
    confirm(session, documento, extraction=extracao, today=HOJE)
    session.flush()
    serie = session.scalar(
        select(Commitment.series_id).where(Commitment.document_id == documento.id)
    )
    assert serie is not None
    return documento.id, serie


def test_editar_bloco_de_arquivo_marca_edited_e_mantem_o_documento(
    session: Session, aluno: Student
) -> None:
    documento_id, serie = _bloco_de_arquivo(session, aluno)

    update_series(
        session,
        aluno,
        serie,
        academia(
            kind="aula",
            label="Enfermaria",
            weekdays=(0, 1, 2, 3, 4),
            starts_at=time(8, 0),
            duration_minutes=300,
        ),
        today=HOJE,
    )

    novos = vigentes(session, serie)
    assert len(novos) == 5
    assert all(c.document_id == documento_id and c.edited_by_student for c in novos)


def test_apagar_documento_leva_inclusive_os_registros_editados(
    session: Session, aluno: Student
) -> None:
    from app.models import Document

    documento_id, serie = _bloco_de_arquivo(session, aluno)
    update_series(
        session,
        aluno,
        serie,
        academia(kind="aula", label="Enfermaria", weekdays=(0, 1), duration_minutes=300),
        today=HOJE,
    )
    documento = session.get(Document, documento_id)
    assert documento is not None

    erase(session, documento, InMemoryStore())

    assert da_serie(session, serie) == []


def test_teto_de_compromissos_vigentes(session: Session, aluno: Student) -> None:
    for _ in range(40):
        create_series(session, aluno, academia(weekdays=(0, 1, 2, 3, 4)), today=HOJE)

    with pytest.raises(RoutineError):
        create_series(session, aluno, academia(weekdays=(5,)), today=HOJE)


def test_semana_sem_capacidade_gravada_vem_calculada(session: Session, sem_prova: Student) -> None:
    create_series(session, sem_prova, academia(weekdays=(0,), duration_minutes=540), today=HOJE)

    semana = week_view(session, sem_prova, date(2026, 10, 1), today=HOJE)

    assert semana.week_start == SEGUNDA_SEGUINTE
    assert len(semana.days) == 7
    assert all(dia.computed for dia in semana.days)
    assert semana.days[0].free_minutes == 60  # janela de 600 - 540
    assert semana.days[1].free_minutes == 120  # meta de 14 h/semana


def test_sem_prova_principal_salva_sem_replanejar(session: Session, sem_prova: Student) -> None:
    resultado = create_series(session, sem_prova, academia(), today=HOJE)

    assert resultado.replan_summary == ""
    assert session.scalar(select(PlanVersion).where(PlanVersion.student_id == sem_prova.id)) is None


def test_changed_today_liga_depois_de_editar(session: Session, aluno: Student) -> None:
    assert week_view(session, aluno, HOJE, today=HOJE).changed_today is False

    create_series(session, aluno, academia(), today=HOJE)

    assert week_view(session, aluno, HOJE, today=HOJE).changed_today is True


def test_semana_traz_itens_ordenados_e_capacidade_gravada(session: Session, aluno: Student) -> None:
    create_series(session, aluno, academia(weekdays=(0,)), today=HOJE)
    create_series(
        session,
        aluno,
        academia(
            kind="leitura", label="Leitura", weekdays=(0,), starts_at=None, duration_minutes=30
        ),
        today=HOJE,
    )
    create_series(
        session,
        aluno,
        academia(
            kind="aula", label="Aula", weekdays=(0,), starts_at=time(7, 0), duration_minutes=60
        ),
        today=HOJE,
    )

    segunda = week_view(session, aluno, SEGUNDA_SEGUINTE, today=HOJE).days[0]

    assert [item.label for item in segunda.items] == ["Leitura", "Aula", "Musculação"]
    assert segunda.computed is False
    assert all(item.editable and item.recurring for item in segunda.items)


def test_prova_principal_some_da_conta_quando_nao_existe(session: Session, aluno: Student) -> None:
    """Sem prova principal o recálculo não roda, mas salvar continua funcionando."""
    for alvo in session.scalars(select(TargetExam).where(TargetExam.student_id == aluno.id)):
        alvo.is_primary = False
    session.flush()

    assert create_series(session, aluno, academia(), today=HOJE).replan_summary == ""


def test_item_traz_a_definicao_vigente_da_serie(session: Session, aluno: Student) -> None:
    """Rodízio que começa no meio da semana: o item diz a série inteira, não a semana."""
    create_series(
        session, aluno, academia(weekdays=(0, 1, 2, 3, 4), starts_on=date(2026, 10, 7)), today=HOJE
    )

    quarta = week_view(session, aluno, date(2026, 10, 5), today=HOJE).days[2]

    serie = quarta.items[0].series
    assert serie is not None
    assert serie.weekdays == (0, 1, 2, 3, 4)
    assert serie.starts_on == date(2026, 10, 7)
    assert serie.on_day is None


def test_bloco_encerrado_hoje_mostra_a_definicao_nova(session: Session, aluno: Student) -> None:
    criada = create_series(session, aluno, academia(), today=HOJE)
    assert criada.series_id is not None
    for registro in da_serie(session, criada.series_id):
        registro.starts_on = date(2026, 9, 1)
    session.flush()
    update_series(
        session,
        aluno,
        criada.series_id,
        academia(weekdays=(0, 4), starts_at=time(19, 0)),
        today=HOJE,
    )

    segunda_passada = week_view(session, aluno, SEMANA_ATUAL, today=HOJE).days[0]

    item = segunda_passada.items[0]
    assert item.starts_at == time(18, 0)  # o que valia naquela segunda
    assert item.series is not None
    assert item.series.starts_at == time(19, 0)  # o que vale de amanhã em diante
    assert item.series.weekdays == (0, 4)
    assert item.series.ends_on is None


def test_serie_encerrada_nao_e_editavel(session: Session, aluno: Student) -> None:
    criada = create_series(session, aluno, academia(), today=HOJE)
    assert criada.series_id is not None
    for registro in da_serie(session, criada.series_id):
        registro.starts_on = date(2026, 9, 1)
    session.flush()
    delete_series(session, aluno, criada.series_id, today=HOJE)

    segunda_passada = week_view(session, aluno, SEMANA_ATUAL, today=HOJE).days[0]

    assert segunda_passada.items[0].series is None
    assert segunda_passada.items[0].editable is False


def test_data_fora_da_faixa_e_recusada(session: Session, aluno: Student) -> None:
    with pytest.raises(RoutineError):
        create_series(session, aluno, academia(weekdays=(), on_day=date(9999, 12, 31)), today=HOJE)
    with pytest.raises(RoutineError):
        create_series(session, aluno, academia(ends_on=date(2100, 1, 1)), today=HOJE)
    with pytest.raises(RoutineError):
        week_view(session, aluno, date(9999, 12, 31), today=HOJE)


def test_changed_today_vem_da_ultima_edicao_e_nao_da_vigencia_do_arquivo(
    session: Session, aluno: Student
) -> None:
    """Rodízio de arquivo que termina hoje não é mudança do aluno."""
    _bloco_de_arquivo(session, aluno)
    for compromisso in session.scalars(select(Commitment).where(Commitment.student_id == aluno.id)):
        compromisso.ends_on = HOJE
    session.flush()
    assert week_view(session, aluno, HOJE, today=HOJE).changed_today is False

    futura = create_series(session, aluno, academia(starts_on=date(2026, 10, 7)), today=HOJE)
    assert futura.series_id is not None
    aluno.routine_changed_on = None
    delete_series(session, aluno, futura.series_id, today=HOJE)

    assert week_view(session, aluno, HOJE, today=HOJE).changed_today is True


def test_apagar_bloco_de_arquivo_entra_no_aviso_de_reconfirmacao(
    session: Session, aluno: Student
) -> None:
    from app.documents import edited_blocks
    from app.models import Document

    documento_id, serie = _bloco_de_arquivo(session, aluno)
    delete_series(session, aluno, serie, today=HOJE)

    documento = session.get(Document, documento_id)
    assert documento is not None
    assert edited_blocks(session, documento) == 1  # um bloco (seg–sex), não cinco registros


def test_teto_conta_so_os_compromissos_digitados(session: Session, aluno: Student) -> None:
    from app.models import Document

    documento = Document(
        student_id=aluno.id,
        kind="escala",
        original_name="escala.xlsx",
        content_type="application/pdf",
        size_bytes=10,
    )
    session.add(documento)
    session.flush()
    for dia in range(7):
        for _ in range(40):
            session.add(
                Commitment(
                    student_id=aluno.id,
                    document_id=documento.id,
                    kind="plantao",
                    weekday=dia,
                    duration_minutes=60,
                    series_id=uuid.uuid4(),
                )
            )
    session.flush()

    assert create_series(session, aluno, academia(), today=HOJE).series_id is not None
