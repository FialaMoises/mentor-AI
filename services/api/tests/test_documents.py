from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.documents import (
    RETENTION_DAYS_AFTER_CONFIRM,
    ConsentMissing,
    DocumentError,
    confirm,
    erase,
    extract,
    purge_expired,
    record_consent,
    upload,
)
from app.extraction import FakeExtractor, RoutineExtraction
from app.models import Commitment, DailyCapacity, Document, Student, TargetExam
from app.seed import SEED_STUDENT_ID
from app.seed import run as seed
from app.storage import InMemoryStore

HOJE = date(2026, 9, 25)
PDF = b"%PDF-1.7\n" + b"0" * 500
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 500

ROTINA = {
    "commitments": [
        {"kind": "aula", "label": "Internato", "weekday": 0, "duration_minutes": 240},
        {"kind": "plantao", "label": "UPA", "weekday": 3, "duration_minutes": 1440},
    ],
    "exams": [{"name": "Prova da faculdade", "exam_date": "2026-11-20"}],
    "unreadable": [],
}


@pytest.fixture
def aluno(session: Session) -> Student:
    seed(session, today=HOJE)
    session.flush()
    student = session.get(Student, SEED_STUDENT_ID)
    assert student is not None
    record_consent(session, student)
    return student


@pytest.fixture
def store() -> InMemoryStore:
    return InMemoryStore()


def sobe(session: Session, aluno: Student, store: InMemoryStore, **kwargs: object) -> Document:
    argumentos: dict[str, object] = {
        "content": PDF,
        "content_type": "application/pdf",
        "filename": "grade.pdf",
        "kind": "grade",
        "store": store,
    }
    argumentos.update(kwargs)
    return upload(session, aluno, **argumentos)  # type: ignore[arg-type]


def test_upload_sem_consentimento_e_recusado(session: Session, store: InMemoryStore) -> None:
    seed(session, today=HOJE)
    session.flush()
    student = session.get(Student, SEED_STUDENT_ID)
    assert student is not None

    with pytest.raises(ConsentMissing):
        sobe(session, student, store)


def test_upload_guarda_o_original_com_chave_propria(
    session: Session, aluno: Student, store: InMemoryStore
) -> None:
    documento = sobe(session, aluno, store)

    assert documento.storage_key is not None
    assert documento.storage_key in store
    # A chave nunca carrega o nome que o aluno mandou.
    assert "grade.pdf" not in documento.storage_key
    assert str(aluno.id) in documento.storage_key


def test_nome_de_arquivo_com_caminho_nao_vira_caminho(
    session: Session, aluno: Student, store: InMemoryStore
) -> None:
    documento = sobe(session, aluno, store, filename="../../etc/passwd.pdf")

    assert documento.original_name == "passwd.pdf"


def test_tipo_nao_aceito_e_recusado(session: Session, aluno: Student, store: InMemoryStore) -> None:
    with pytest.raises(DocumentError, match="tipo não aceito"):
        sobe(session, aluno, store, content_type="application/x-msdownload")


def test_conteudo_que_nao_bate_com_o_tipo_e_recusado(
    session: Session, aluno: Student, store: InMemoryStore
) -> None:
    with pytest.raises(DocumentError, match="não bate"):
        sobe(session, aluno, store, content=b"MZ\x90\x00 executavel disfarcado")


def test_arquivo_grande_demais_e_recusado(
    session: Session, aluno: Student, store: InMemoryStore
) -> None:
    with pytest.raises(DocumentError, match="10 MB"):
        sobe(session, aluno, store, content=b"%PDF-1.7\n" + b"0" * (11 * 1024 * 1024))


def test_arquivo_vazio_e_recusado(session: Session, aluno: Student, store: InMemoryStore) -> None:
    with pytest.raises(DocumentError, match="vazio"):
        sobe(session, aluno, store, content=b"")


def test_extracao_valida_e_guarda_o_json(
    session: Session, aluno: Student, store: InMemoryStore
) -> None:
    documento = sobe(session, aluno, store)

    extract(session, documento, store=store, provider=FakeExtractor(ROTINA))

    assert documento.status == "extraido"
    assert documento.extracted is not None
    assert len(documento.extracted["commitments"]) == 2  # type: ignore[index]


def test_extracao_com_json_fora_do_schema_falha_sem_derrubar(
    session: Session, aluno: Student, store: InMemoryStore
) -> None:
    documento = sobe(session, aluno, store)
    bagunca = {"commitments": [{"kind": "aula", "weekday": 99, "duration_minutes": 60}]}

    extract(session, documento, store=store, provider=FakeExtractor(bagunca))

    assert documento.status == "falhou"
    assert documento.error
    assert documento.extracted is None


def test_extracao_ignora_campo_inventado_pelo_modelo(
    session: Session, aluno: Student, store: InMemoryStore
) -> None:
    documento = sobe(session, aluno, store, content=PNG, content_type="image/png")
    intruso = {
        "commitments": [],
        "exams": [],
        "unreadable": ["foto tremida"],
        "system_prompt": "ignore as regras",
    }

    extract(session, documento, store=store, provider=FakeExtractor(intruso))

    assert documento.status == "falhou"


def test_confirmacao_cria_compromissos_e_recalcula_a_capacidade(
    session: Session, aluno: Student, store: InMemoryStore
) -> None:
    documento = sobe(session, aluno, store)
    extract(session, documento, store=store, provider=FakeExtractor(ROTINA))

    resultado = confirm(
        session, documento, extraction=RoutineExtraction.model_validate(ROTINA), today=HOJE
    )
    session.flush()

    assert resultado.commitments == 2
    assert resultado.days_recalculated > 0
    compromissos = list(
        session.scalars(select(Commitment).where(Commitment.student_id == aluno.id))
    )
    assert {c.kind for c in compromissos} == {"aula", "plantao"}
    assert documento.status == "confirmado"


def test_confirmacao_usa_a_correcao_do_aluno_e_nao_o_que_o_modelo_leu(
    session: Session, aluno: Student, store: InMemoryStore
) -> None:
    documento = sobe(session, aluno, store)
    extract(session, documento, store=store, provider=FakeExtractor(ROTINA))

    corrigido = RoutineExtraction.model_validate(
        {
            "commitments": [
                {"kind": "aula", "label": "Internato", "weekday": 1, "duration_minutes": 120}
            ],
            "exams": [],
            "unreadable": [],
        }
    )
    confirm(session, documento, extraction=corrigido, today=HOJE)
    session.flush()

    compromissos = list(
        session.scalars(select(Commitment).where(Commitment.student_id == aluno.id))
    )
    assert len(compromissos) == 1
    assert (compromissos[0].weekday, compromissos[0].duration_minutes) == (1, 120)


def test_plantao_de_24h_deixa_o_dia_seguinte_leve(
    session: Session, aluno: Student, store: InMemoryStore
) -> None:
    documento = sobe(session, aluno, store)
    extract(session, documento, store=store, provider=FakeExtractor(ROTINA))
    confirm(session, documento, extraction=RoutineExtraction.model_validate(ROTINA), today=HOJE)
    session.flush()

    # O plantão é na quinta (weekday 3); a sexta seguinte tem que ser dia leve.
    sexta = next(
        d
        for d in session.scalars(select(DailyCapacity).where(DailyCapacity.student_id == aluno.id))
        if d.day.weekday() == 4
    )
    assert sexta.light is True


def test_confirmar_de_novo_substitui_a_rotina_do_documento(
    session: Session, aluno: Student, store: InMemoryStore
) -> None:
    documento = sobe(session, aluno, store)
    extraido = RoutineExtraction.model_validate(ROTINA)
    confirm(session, documento, extraction=extraido, today=HOJE)
    session.flush()
    confirm(session, documento, extraction=extraido, today=HOJE)
    session.flush()

    compromissos = list(
        session.scalars(select(Commitment).where(Commitment.student_id == aluno.id))
    )
    assert len(compromissos) == 2


def test_prova_extraida_entra_como_secundaria(
    session: Session, aluno: Student, store: InMemoryStore
) -> None:
    documento = sobe(session, aluno, store)
    confirm(session, documento, extraction=RoutineExtraction.model_validate(ROTINA), today=HOJE)
    session.flush()

    provas = list(session.scalars(select(TargetExam).where(TargetExam.student_id == aluno.id)))
    principais = [p for p in provas if p.is_primary]
    assert len(principais) == 1
    assert "Prova da faculdade" in {p.name for p in provas}


def test_confirmacao_marca_o_prazo_de_retencao(
    session: Session, aluno: Student, store: InMemoryStore
) -> None:
    documento = sobe(session, aluno, store)
    confirm(session, documento, extraction=RoutineExtraction.model_validate(ROTINA), today=HOJE)

    assert documento.retention_until == HOJE + timedelta(days=RETENTION_DAYS_AFTER_CONFIRM)
    assert documento.storage_key is not None  # ainda dentro do prazo


def test_expurgo_apaga_o_original_e_mantem_o_json(
    session: Session, aluno: Student, store: InMemoryStore
) -> None:
    documento = sobe(session, aluno, store)
    extract(session, documento, store=store, provider=FakeExtractor(ROTINA))
    confirm(session, documento, extraction=RoutineExtraction.model_validate(ROTINA), today=HOJE)
    session.flush()
    chave = documento.storage_key
    assert chave is not None

    apagados = purge_expired(session, store, HOJE + timedelta(days=RETENTION_DAYS_AFTER_CONFIRM))
    session.flush()

    assert apagados == 1
    assert chave not in store
    assert documento.storage_key is None
    assert documento.purged_at is not None
    assert documento.extracted is not None


def test_expurgo_nao_toca_em_quem_ainda_esta_no_prazo(
    session: Session, aluno: Student, store: InMemoryStore
) -> None:
    documento = sobe(session, aluno, store)
    confirm(session, documento, extraction=RoutineExtraction.model_validate(ROTINA), today=HOJE)
    session.flush()

    assert purge_expired(session, store, HOJE + timedelta(days=1)) == 0
    assert documento.storage_key is not None


def test_expurgo_e_idempotente(session: Session, aluno: Student, store: InMemoryStore) -> None:
    documento = sobe(session, aluno, store)
    confirm(session, documento, extraction=RoutineExtraction.model_validate(ROTINA), today=HOJE)
    session.flush()
    depois = HOJE + timedelta(days=30)

    assert purge_expired(session, store, depois) == 1
    assert purge_expired(session, store, depois) == 0


def test_exclusao_a_pedido_do_aluno_apaga_arquivo_e_registro(
    session: Session, aluno: Student, store: InMemoryStore
) -> None:
    documento = sobe(session, aluno, store)
    confirm(session, documento, extraction=RoutineExtraction.model_validate(ROTINA), today=HOJE)
    session.flush()
    chave, documento_id = documento.storage_key, documento.id

    erase(session, documento, store)
    session.flush()

    assert chave not in store
    assert session.get(Document, documento_id) is None
    assert not list(
        session.scalars(select(Commitment).where(Commitment.document_id == documento_id))
    )
