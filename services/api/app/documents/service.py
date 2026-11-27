"""Upload, extração, confirmação e expurgo dos arquivos de rotina.

Regra da casa aqui: o arquivo do aluno é dado não confiável do começo ao fim —
tipo checado por assinatura, nome nunca usado como caminho, conteúdo tratado
como dado pelo LLM, e o original apagado no prazo combinado.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..clock import now_utc
from ..engine import Commitment as EngineCommitment
from ..engine import capacities_from_commitments, daily_budget
from ..extraction.provider import ExtractionError, ExtractionProvider
from ..extraction.schema import ExtractedCommitment, RoutineExtraction
from ..models import (
    Commitment,
    Consent,
    DailyCapacity,
    Document,
    PlanVersion,
    Student,
    TargetExam,
)
from ..params import engine_params
from ..planning import replan
from ..storage import (
    ALLOWED_CONTENT_TYPES,
    MAX_UPLOAD_BYTES,
    ObjectStore,
    StorageError,
    build_key,
    looks_like,
    safe_display_name,
)

#: Versão do aviso de privacidade que o aluno aceita antes do primeiro upload.
POLICY_VERSION = "2026-09-25"
CONSENT_PURPOSE = "upload_rotina"
#: O original some este tanto de dias depois da confirmação da semana.
RETENTION_DAYS_AFTER_CONFIRM = 7


class DocumentError(RuntimeError):
    pass


class ConsentMissing(DocumentError):
    pass


@dataclass(frozen=True, slots=True)
class ConfirmResult:
    document: Document
    commitments: int
    days_recalculated: int
    replan_summary: str


def has_consent(session: Session, student: Student) -> bool:
    return (
        session.scalar(
            select(Consent.id).where(
                Consent.student_id == student.id, Consent.purpose == CONSENT_PURPOSE
            )
        )
        is not None
    )


def record_consent(session: Session, student: Student) -> Consent:
    consentimento = Consent(
        student_id=student.id, purpose=CONSENT_PURPOSE, policy_version=POLICY_VERSION
    )
    session.add(consentimento)
    session.flush()
    return consentimento


def upload(
    session: Session,
    student: Student,
    *,
    content: bytes,
    content_type: str,
    filename: str,
    kind: str,
    store: ObjectStore,
) -> Document:
    """Guarda o original e devolve o registro. Nada de extração ainda."""
    if not has_consent(session, student):
        raise ConsentMissing("o aluno precisa aceitar o aviso de privacidade antes de enviar")
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise DocumentError(f"tipo não aceito: {content_type}")
    if not content:
        raise DocumentError("arquivo vazio")
    if len(content) > MAX_UPLOAD_BYTES:
        raise DocumentError("arquivo maior que o limite de 10 MB")
    if not looks_like(content, content_type):
        raise DocumentError("o conteúdo do arquivo não bate com o tipo declarado")

    chave = build_key(student.id, content_type)
    store.put(chave, content, content_type)

    documento = Document(
        student_id=student.id,
        kind=kind,
        original_name=safe_display_name(filename),
        storage_key=chave,
        content_type=content_type,
        size_bytes=len(content),
        status="recebido",
    )
    session.add(documento)
    session.flush()
    return documento


def extract(
    session: Session,
    document: Document,
    *,
    store: ObjectStore,
    provider: ExtractionProvider,
) -> Document:
    """Manda o arquivo para o modelo e valida a resposta contra o schema."""
    if document.storage_key is None:
        raise DocumentError("o original já foi apagado; suba o arquivo de novo")

    try:
        conteudo = store.get(document.storage_key)
        bruto = provider.extract(
            content=conteudo, content_type=document.content_type, kind=document.kind
        )
        extraido = RoutineExtraction.model_validate(bruto)
    except (ExtractionError, StorageError, ValueError) as erro:
        document.status = "falhou"
        document.error = str(erro)[:400]
        session.flush()
        return document

    document.extracted = extraido.model_dump(mode="json")
    document.status = "extraido"
    document.error = ""
    session.flush()
    return document


def engine_commitments(rows: list[Commitment]) -> list[EngineCommitment]:
    """Linhas do banco viram compromissos do motor."""
    return [
        EngineCommitment(
            kind=row.kind,
            duration_minutes=row.duration_minutes,
            weekday=row.weekday,
            on_day=row.on_day,
            starts_on=row.starts_on,
            ends_on=row.ends_on,
            starts_at=row.starts_at,
        )
        for row in rows
    ]


def edited_blocks(session: Session, document: Document) -> int:
    """Quantos compromissos deste documento o aluno alterou à mão na rotina.

    A tela de conferência avisa antes de reconfirmar: confirmar de novo
    substitui essas edições.
    """
    series = session.scalars(
        select(Commitment.series_id).where(
            Commitment.document_id == document.id,
            Commitment.edited_by_student.is_(True),
        )
    )
    return len(set(series))


def _series_key(item: ExtractedCommitment) -> tuple[object, ...] | None:
    """O mesmo bloco em dias diferentes da semana é uma série só."""
    if item.weekday is None:
        return None
    return (
        item.kind,
        item.label,
        item.starts_at,
        item.duration_minutes,
        item.starts_on,
        item.ends_on,
    )


def _from_confirmation_day(item: ExtractedCommitment, today: date) -> ExtractedCommitment | None:
    """O compromisso lido no arquivo vale a partir do dia da confirmação, não antes.

    Sem isso a rotina de hoje apareceria nas semanas passadas. O que já acabou
    (vigência encerrada, data única no passado) não entra; o JSON extraído guarda
    tudo do mesmo jeito.
    """
    if item.on_day is not None:
        return item if item.on_day >= today else None
    if item.ends_on is not None and item.ends_on < today:
        return None
    inicio = max(item.starts_on or today, today)
    return item if inicio == item.starts_on else item.model_copy(update={"starts_on": inicio})


def capacity_on(session: Session, student: Student, day: date) -> tuple[int, bool]:
    """A capacidade do dia como o motor a calcula, sem gravar nada.

    Serve ao dia que ainda não tem `DailyCapacity` (por exemplo, depois de seguir
    sem arquivo): mostrar 0 seria mentir, e gravar mexeria no dia congelado.
    """
    compromissos = list(
        session.scalars(select(Commitment).where(Commitment.student_id == student.id))
    )
    calculada = capacities_from_commitments(
        [day], engine_commitments(compromissos), daily_budget(student.weekly_hours), engine_params()
    )[0]
    return calculada.free_minutes, calculada.light


def rebuild_capacities(session: Session, student: Student, start: date, end: date) -> int:
    """Recalcula a capacidade dia a dia a partir dos compromissos confirmados."""
    if end < start:
        return 0

    compromissos = list(
        session.scalars(select(Commitment).where(Commitment.student_id == student.id))
    )
    dias = [start + timedelta(days=d) for d in range((end - start).days + 1)]
    capacidades = capacities_from_commitments(
        dias,
        engine_commitments(compromissos),
        daily_budget(student.weekly_hours),
        engine_params(),
    )

    existentes = {
        row.day: row
        for row in session.scalars(
            select(DailyCapacity).where(
                DailyCapacity.student_id == student.id,
                DailyCapacity.day >= start,
                DailyCapacity.day <= end,
            )
        )
    }
    for capacidade in capacidades:
        linha = existentes.get(capacidade.day)
        if linha is None:
            linha = DailyCapacity(student_id=student.id, day=capacidade.day)
            session.add(linha)
        linha.free_minutes = capacidade.free_minutes
        linha.light = capacidade.light
    session.flush()
    return len(capacidades)


def confirm(
    session: Session,
    document: Document,
    *,
    extraction: RoutineExtraction,
    today: date,
) -> ConfirmResult:
    """O aluno conferiu a semana. A partir daqui a rotina é oficial.

    A extração que vale é a que vem desta chamada — o aluno pode ter corrigido o
    que o modelo errou.
    """
    # Trava a linha do documento: um segundo confirm (clique duplo, duas abas) espera
    # este terminar e então substitui a rotina, em vez de somar uma cópia.
    session.execute(select(Document).where(Document.id == document.id).with_for_update())
    student = session.get(Student, document.student_id)
    if student is None:  # pragma: no cover - FK garante
        raise DocumentError("documento sem aluno")
    # O dia de hoje como o aluno já o viu (sem este arquivo): é ele que fica congelado.
    hoje_antes = capacity_on(session, student, today)

    # A rotina deste documento é substituída por inteiro: sem sobra da versão velha.
    session.execute(sql_delete(Commitment).where(Commitment.document_id == document.id))
    session.flush()

    series: dict[tuple[object, ...], uuid.UUID] = {}
    #: O mesmo bloco duas vezes no mesmo dia (manhã e tarde, sem horário) vira duas
    #: séries: a n-ésima ocorrência de cada dia vai para a n-ésima série.
    ocorrencias: dict[tuple[object, ...], int] = {}
    for lido in extraction.commitments:
        extraido = _from_confirmation_day(lido, today)
        if extraido is None:
            continue
        chave = _series_key(extraido)
        if chave is None:
            serie = uuid.uuid4()
        else:
            por_dia = (*chave, extraido.weekday)
            ordem = ocorrencias.get(por_dia, 0)
            ocorrencias[por_dia] = ordem + 1
            serie = series.setdefault((*chave, ordem), uuid.uuid4())
        session.add(
            Commitment(
                student_id=student.id,
                document_id=document.id,
                kind=extraido.kind,
                label=extraido.label,
                weekday=extraido.weekday,
                on_day=extraido.on_day,
                duration_minutes=extraido.duration_minutes,
                starts_on=extraido.starts_on,
                ends_on=extraido.ends_on,
                starts_at=extraido.starts_at,
                series_id=serie,
            )
        )

    for prova in extraction.exams:
        if prova.exam_date < today:
            # Prova que já passou não é alvo de nada: fica só no JSON extraído.
            continue
        ja_existe = session.scalar(
            select(TargetExam.id).where(
                TargetExam.student_id == student.id,
                TargetExam.name == prova.name,
                TargetExam.exam_date == prova.exam_date,
            )
        )
        if ja_existe is None:
            session.add(
                TargetExam(
                    student_id=student.id,
                    name=prova.name,
                    exam_date=prova.exam_date,
                    is_primary=False,
                )
            )
    session.flush()

    document.extracted = extraction.model_dump(mode="json")
    document.status = "confirmado"
    document.confirmed_at = now_utc()
    document.retention_until = today + timedelta(days=RETENTION_DAYS_AFTER_CONFIRM)
    session.flush()

    alvo = session.scalar(
        select(TargetExam).where(
            TargetExam.student_id == student.id, TargetExam.is_primary.is_(True)
        )
    )
    # Hoje é congelado (regra 3): a capacidade de hoje só nasce aqui na primeira
    # confirmação. Reconfirmar recalcula de amanhã e avisa a rotina da mudança.
    hoje_gravado = (
        session.scalar(
            select(DailyCapacity.id).where(
                DailyCapacity.student_id == student.id, DailyCapacity.day == today
            )
        )
        is not None
    )
    ja_tem_plano = (
        session.scalar(select(PlanVersion.id).where(PlanVersion.student_id == student.id))
        is not None
    )
    if not hoje_gravado and ja_tem_plano:
        # O /hoje já mostrou o dia calculado na hora (sem linha gravada): grava esse dia
        # como estava antes do arquivo. Só o 1º onboarding, sem plano nenhum, calcula
        # hoje já com o arquivo.
        livres, leve = hoje_antes
        session.add(
            DailyCapacity(student_id=student.id, day=today, free_minutes=livres, light=leve)
        )
        session.flush()
        if capacity_on(session, student, today) != hoje_antes:
            student.routine_changed_on = today
        hoje_gravado = True
    elif hoje_gravado:
        student.routine_changed_on = today
    inicio = today + timedelta(days=1) if hoje_gravado else today
    dias = rebuild_capacities(session, student, inicio, alvo.exam_date) if alvo else 0

    resumo = ""
    if alvo is not None:
        resultado = replan(session, student, today, reason="rotina confirmada")
        resumo = resultado.version.summary

    return ConfirmResult(
        document=document,
        commitments=len(extraction.commitments),
        days_recalculated=dias,
        replan_summary=resumo,
    )


def purge_original(session: Session, document: Document, store: ObjectStore) -> None:
    """Apaga o arquivo e mantém o JSON. Idempotente."""
    if document.storage_key is not None:
        store.delete(document.storage_key)
        document.storage_key = None
    document.purged_at = now_utc()
    session.flush()


def purge_expired(session: Session, store: ObjectStore, today: date) -> int:
    """Expurgo do prazo de retenção. Roda no job diário."""
    vencidos = list(
        session.scalars(
            select(Document).where(
                Document.retention_until.is_not(None),
                Document.retention_until <= today,
                Document.storage_key.is_not(None),
            )
        )
    )
    for documento in vencidos:
        purge_original(session, documento, store)
    return len(vencidos)


def erase(session: Session, document: Document, store: ObjectStore) -> None:
    """Exclusão a pedido do aluno: some o arquivo e some o registro."""
    if document.storage_key is not None:
        store.delete(document.storage_key)
    session.execute(sql_delete(Commitment).where(Commitment.document_id == document.id))
    session.delete(document)
    session.flush()


def student_of(session: Session, document_id: uuid.UUID) -> Document | None:
    return session.get(Document, document_id)
