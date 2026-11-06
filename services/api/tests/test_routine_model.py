from __future__ import annotations

import uuid
from datetime import time

from sqlalchemy.orm import Session

from app.models import COMMITMENT_KINDS, Commitment
from app.seed import SEED_STUDENT_ID
from app.seed import run as seed


def test_compromisso_guarda_horario_serie_e_nasce_sem_edicao(session: Session) -> None:
    seed(session)
    serie = uuid.uuid4()
    compromisso = Commitment(
        student_id=SEED_STUDENT_ID,
        kind="leitura",
        label="Leitura antes de dormir",
        weekday=0,
        duration_minutes=30,
        starts_at=time(21, 0),
        series_id=serie,
    )
    session.add(compromisso)
    session.flush()
    session.expire_all()

    lido = session.get(Commitment, compromisso.id)
    assert lido is not None
    assert lido.starts_at == time(21, 0)
    assert lido.series_id == serie
    assert lido.edited_by_student is False


def test_leitura_e_um_tipo_de_compromisso() -> None:
    assert "leitura" in COMMITMENT_KINDS
