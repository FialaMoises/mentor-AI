"""Painel do piloto. Protegido por token de admin, separado da sessão do aluno."""

from __future__ import annotations

import csv
import io
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..clock import today_in
from ..config import get_settings
from ..db import get_session
from ..deps import require_admin
from ..metrics import collect

router = APIRouter(prefix="/api/v1/admin", dependencies=[Depends(require_admin)])


@router.get("/metrics")
def get_metrics(session: Annotated[Session, Depends(get_session)]) -> dict[str, object]:
    """As quatro perguntas do piloto, mais a quebra por status de assinatura."""
    hoje = today_in(get_settings().default_timezone)
    return collect(session, hoje).as_dict()


@router.get("/metrics.csv")
def get_metrics_csv(session: Annotated[Session, Depends(get_session)]) -> StreamingResponse:
    """A mesma coisa em CSV, para cruzar numa planilha durante o piloto."""
    hoje = today_in(get_settings().default_timezone)
    numeros = collect(session, hoje).as_dict()

    buffer = io.StringIO()
    escritor = csv.writer(buffer)
    escritor.writerow(["metrica", "valor"])
    for chave, valor in numeros.items():
        escritor.writerow([chave, valor])
    buffer.seek(0)

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="metricas-{hoje}.csv"'},
    )
