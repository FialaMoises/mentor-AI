"""A rotina que o aluno edita à mão: séries de compromissos e a agenda da semana.

Toda mudança vale de amanhã em diante. O dia de hoje fica como o aluno abriu, e
semanas passadas continuam mostrando o que valia nelas: editar ou apagar fecha a
vigência dos registros (`ends_on = hoje`) em vez de apagar a linha. A conta de
capacidade é sempre a do motor — aqui só se grava, recalcula e replaneja.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..documents import engine_commitments, rebuild_capacities
from ..engine import capacities_from_commitments, daily_budget
from ..models import COMMITMENT_KINDS, Commitment, DailyCapacity, Document, Student, TargetExam
from ..params import engine_params
from ..planning import replan

#: Teto de compromissos vigentes por aluno — o mesmo da extração.
MAX_ACTIVE_COMMITMENTS = 200
MAX_LABEL = 160
#: Datas aceitas na rotina: de dois anos atrás a três anos à frente. Fora disso é
#: erro de digitação (o ano 9999 derrubava a conta de semana com OverflowError).
DATE_RANGE_PAST = timedelta(days=2 * 365)
DATE_RANGE_FUTURE = timedelta(days=3 * 365)


class RoutineError(RuntimeError):
    """Pedido que não faz sentido para a rotina. Vira 422."""


class SeriesNotFound(RoutineError):
    """Série inexistente, de outro aluno ou já encerrada. Vira 404."""


@dataclass(frozen=True, slots=True)
class SeriesInput:
    kind: str
    label: str
    weekdays: tuple[int, ...]
    on_day: date | None
    starts_at: time | None
    duration_minutes: int
    starts_on: date | None = None
    ends_on: date | None = None


@dataclass(frozen=True, slots=True)
class SaveResult:
    series_id: uuid.UUID | None
    replan_summary: str


@dataclass(frozen=True, slots=True)
class RoutineItem:
    series_id: uuid.UUID
    kind: str
    label: str
    starts_at: time | None
    duration_minutes: int
    recurring: bool
    document_name: str | None
    edited_by_student: bool
    editable: bool
    #: Fim da vigência deste registro.
    ends_on: date | None = None
    #: O que a série vale de amanhã em diante — é isto que o formulário de edição
    #: abre, e não o que a semana exibida mostra. None = série encerrada.
    series: SeriesInput | None = None


@dataclass(frozen=True, slots=True)
class RoutineDay:
    day: date
    free_minutes: int
    light: bool
    computed: bool
    items: tuple[RoutineItem, ...]


@dataclass(frozen=True, slots=True)
class RoutineWeek:
    week_start: date
    today: date
    changed_today: bool
    days: tuple[RoutineDay, ...]


def _check_date(valor: date, today: date) -> None:
    if not today - DATE_RANGE_PAST <= valor <= today + DATE_RANGE_FUTURE:
        raise RoutineError("data fora da faixa aceita: de dois anos atrás a três anos à frente")


def _validate(data: SeriesInput, today: date) -> None:
    for valor in (data.on_day, data.starts_on, data.ends_on):
        if valor is not None:
            _check_date(valor, today)
    if bool(data.weekdays) == (data.on_day is not None):
        raise RoutineError("compromisso é semanal (dias da semana) ou de um dia só (data)")
    if len(set(data.weekdays)) != len(data.weekdays) or any(
        not 0 <= dia <= 6 for dia in data.weekdays
    ):
        raise RoutineError("dias da semana vão de 0 (segunda) a 6 (domingo), sem repetir")
    if data.on_day is not None and data.on_day <= today:
        raise RoutineError("compromisso de um dia só precisa ser de amanhã em diante")
    if data.kind not in COMMITMENT_KINDS:
        raise RoutineError(f"tipo de compromisso desconhecido: {data.kind}")
    if len(data.label) > MAX_LABEL:
        raise RoutineError(f"nome com mais de {MAX_LABEL} caracteres")
    if not 1 <= data.duration_minutes <= 24 * 60:
        raise RoutineError("duração vai de 1 minuto a 24 horas")
    if data.starts_on and data.ends_on and data.ends_on < data.starts_on:
        raise RoutineError("vigência termina antes de começar")


def _is_active(row: Commitment, today: date) -> bool:
    if row.on_day is not None:
        return row.on_day >= today
    return row.ends_on is None or row.ends_on > today


def _active_count(session: Session, student: Student, today: date) -> int:
    #: O teto vale para o que o aluno digita; cada arquivo já tem o limite da extração.
    rows = session.scalars(
        select(Commitment).where(
            Commitment.student_id == student.id, Commitment.document_id.is_(None)
        )
    )
    return sum(
        1
        for row in rows
        if (row.ends_on is None or row.ends_on > today)
        and (row.on_day is None or row.on_day > today)
    )


def _add_rows(
    session: Session,
    student: Student,
    data: SeriesInput,
    series_id: uuid.UUID,
    today: date,
    *,
    document_id: uuid.UUID | None = None,
    edited: bool = False,
) -> None:
    amanha = today + timedelta(days=1)
    inicio = max(data.starts_on or amanha, amanha)
    if data.ends_on is not None and data.ends_on < inicio:
        raise RoutineError("a vigência termina antes de amanhã")

    dias: list[int | None] = list(data.weekdays) if data.weekdays else [None]
    for dia in dias:
        session.add(
            Commitment(
                student_id=student.id,
                document_id=document_id,
                kind=data.kind,
                label=data.label,
                weekday=dia,
                on_day=data.on_day,
                duration_minutes=data.duration_minutes,
                starts_at=data.starts_at,
                starts_on=None if data.on_day is not None else inicio,
                ends_on=None if data.on_day is not None else data.ends_on,
                series_id=series_id,
                edited_by_student=edited,
            )
        )
    session.flush()

    if _active_count(session, student, today) > MAX_ACTIVE_COMMITMENTS:
        raise RoutineError(f"a rotina passa de {MAX_ACTIVE_COMMITMENTS} compromissos")


def _apply(session: Session, student: Student, today: date) -> str:
    """Recalcula a capacidade de amanhã até a prova e replaneja. Hoje não muda."""
    student.routine_changed_on = today
    session.flush()
    alvo = session.scalar(
        select(TargetExam).where(
            TargetExam.student_id == student.id, TargetExam.is_primary.is_(True)
        )
    )
    if alvo is None or alvo.exam_date is None:
        return ""
    rebuild_capacities(session, student, today + timedelta(days=1), alvo.exam_date)
    resultado = replan(session, student, today, reason="rotina editada")
    return resultado.version.summary


def _series_rows(
    session: Session, student: Student, series_id: uuid.UUID, today: date
) -> list[Commitment]:
    rows = list(
        session.scalars(
            select(Commitment).where(
                Commitment.series_id == series_id, Commitment.student_id == student.id
            )
        )
    )
    if not rows or not any(_is_active(row, today) for row in rows):
        raise SeriesNotFound("compromisso não encontrado")
    return rows


def _close(session: Session, rows: list[Commitment], today: date) -> None:
    """Encerra a série hoje. O que ainda não começou some de verdade."""
    for row in rows:
        if row.on_day is not None:
            if row.on_day <= today:
                raise RoutineError("compromisso de hoje ou do passado não se altera")
            session.delete(row)
        elif row.starts_on is not None and row.starts_on > today:
            session.delete(row)
        elif row.ends_on is None or row.ends_on > today:
            row.ends_on = today
            # Bloco de arquivo apagado conta como edição: reconfirmar o arquivo avisa.
            if row.document_id is not None:
                row.edited_by_student = True
    session.flush()


def create_series(
    session: Session, student: Student, data: SeriesInput, *, today: date
) -> SaveResult:
    _validate(data, today)
    serie = uuid.uuid4()
    _add_rows(session, student, data, serie, today)
    return SaveResult(series_id=serie, replan_summary=_apply(session, student, today))


def update_series(
    session: Session,
    student: Student,
    series_id: uuid.UUID,
    data: SeriesInput,
    *,
    today: date,
) -> SaveResult:
    _validate(data, today)
    rows = _series_rows(session, student, series_id, today)
    documento = next((row.document_id for row in rows if row.document_id is not None), None)
    _close(session, rows, today)
    _add_rows(
        session,
        student,
        data,
        series_id,
        today,
        document_id=documento,
        edited=documento is not None,
    )
    return SaveResult(series_id=series_id, replan_summary=_apply(session, student, today))


def delete_series(
    session: Session, student: Student, series_id: uuid.UUID, *, today: date
) -> SaveResult:
    _close(session, _series_rows(session, student, series_id, today), today)
    return SaveResult(series_id=None, replan_summary=_apply(session, student, today))


def _sort_key(item: RoutineItem) -> tuple[bool, time, str]:
    return (item.starts_at is not None, item.starts_at or time.min, item.label)


def _definitions(rows: list[Commitment], today: date) -> dict[uuid.UUID, SeriesInput]:
    """A definição vigente de cada série, montada só com os registros que valem amanhã."""
    vigentes: dict[uuid.UUID, list[Commitment]] = {}
    for row in rows:
        ativo = (
            row.on_day > today
            if row.on_day is not None
            else (row.ends_on is None or row.ends_on > today)
        )
        if ativo:
            vigentes.setdefault(row.series_id or row.id, []).append(row)

    saida: dict[uuid.UUID, SeriesInput] = {}
    for serie, registros in vigentes.items():
        base = registros[0]
        inicios = [r.starts_on for r in registros]
        saida[serie] = SeriesInput(
            kind=base.kind,
            label=base.label,
            weekdays=tuple(sorted({r.weekday for r in registros if r.weekday is not None})),
            on_day=base.on_day,
            starts_at=base.starts_at,
            duration_minutes=base.duration_minutes,
            starts_on=None if None in inicios else min(d for d in inicios if d is not None),
            ends_on=base.ends_on,
        )
    return saida


def week_view(session: Session, student: Student, week_of: date, *, today: date) -> RoutineWeek:
    """A semana de segunda a domingo, com a capacidade que o motor deu a cada dia."""
    _check_date(week_of, today)
    inicio = week_of - timedelta(days=week_of.weekday())
    dias = [inicio + timedelta(days=d) for d in range(7)]

    rows = list(session.scalars(select(Commitment).where(Commitment.student_id == student.id)))
    motor = engine_commitments(rows)
    definicoes = _definitions(rows, today)
    documentos = {
        doc.id: doc.original_name
        for doc in session.scalars(select(Document).where(Document.student_id == student.id))
    }
    gravadas = {
        row.day: row
        for row in session.scalars(
            select(DailyCapacity).where(
                DailyCapacity.student_id == student.id,
                DailyCapacity.day >= dias[0],
                DailyCapacity.day <= dias[-1],
            )
        )
    }
    orcamento = daily_budget(student.weekly_hours)
    params = engine_params()

    saida: list[RoutineDay] = []
    for dia in dias:
        itens = tuple(
            sorted(
                (
                    RoutineItem(
                        series_id=row.series_id or row.id,
                        kind=row.kind,
                        label=row.label,
                        starts_at=row.starts_at,
                        duration_minutes=row.duration_minutes,
                        recurring=row.weekday is not None,
                        document_name=documentos.get(row.document_id) if row.document_id else None,
                        edited_by_student=row.edited_by_student,
                        editable=(row.series_id or row.id) in definicoes,
                        ends_on=row.ends_on,
                        series=definicoes.get(row.series_id or row.id),
                    )
                    for row, compromisso in zip(rows, motor, strict=True)
                    if compromisso.happens_on(dia)
                ),
                key=_sort_key,
            )
        )
        gravada = gravadas.get(dia)
        if gravada is not None:
            saida.append(RoutineDay(dia, gravada.free_minutes, gravada.light, False, itens))
        else:
            calculada = capacities_from_commitments([dia], motor, orcamento, params)[0]
            saida.append(RoutineDay(dia, calculada.free_minutes, calculada.light, True, itens))

    mudou_hoje = student.routine_changed_on == today
    return RoutineWeek(week_start=inicio, today=today, changed_today=mudou_hoje, days=tuple(saida))


__all__ = [
    "MAX_ACTIVE_COMMITMENTS",
    "RoutineDay",
    "RoutineError",
    "RoutineItem",
    "RoutineWeek",
    "SaveResult",
    "SeriesInput",
    "SeriesNotFound",
    "create_series",
    "delete_series",
    "update_series",
    "week_view",
]
