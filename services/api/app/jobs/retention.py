"""Expurgo diário: apaga o original dos documentos que passaram do prazo.

Roda com `python -m app.jobs.retention`. O JSON extraído fica; o arquivo, não.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from sqlalchemy.orm import Session

from ..clock import today_in
from ..config import get_settings
from ..db import SessionLocal
from ..documents import purge_expired
from ..storage import ObjectStore


def run(session: Session, store: ObjectStore, today: date) -> int:
    return purge_expired(session, store, today)


def main(today_for: Callable[[str], date] = today_in) -> None:
    from ..storage.s3 import get_store

    settings = get_settings()
    with SessionLocal() as session:
        apagados = run(session, get_store(), today_for(settings.default_timezone))
        session.commit()
    print(f"{apagados} arquivos expurgados")


if __name__ == "__main__":
    main()
