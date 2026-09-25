"""Upload da rotina, extração, confirmação da semana e exclusão."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..clock import today_in
from ..db import get_session
from ..deps import get_extraction_provider, get_object_store
from ..documents import ConsentMissing, DocumentError, confirm, erase, extract, upload
from ..extraction import ExtractionProvider, RoutineExtraction
from ..models import Document, Student
from ..storage import MAX_UPLOAD_BYTES, ObjectStore

#: O nome da constante mudou entre versões do Starlette; o número, não.
UNPROCESSABLE = 422

router = APIRouter(prefix="/api/v1")

DocumentKind = Literal["grade", "escala", "cursinho", "outro"]


class DocumentOut(BaseModel):
    id: uuid.UUID
    kind: str
    original_name: str
    status: str
    error: str
    extracted: RoutineExtraction | None
    original_kept: bool


class ConfirmOut(BaseModel):
    document: DocumentOut
    commitments: int
    days_recalculated: int
    replan_summary: str


def _to_out(document: Document) -> DocumentOut:
    extraido = (
        RoutineExtraction.model_validate(document.extracted)
        if document.extracted is not None
        else None
    )
    return DocumentOut(
        id=document.id,
        kind=document.kind,
        original_name=document.original_name,
        status=document.status,
        error=document.error,
        extracted=extraido,
        original_kept=document.storage_key is not None,
    )


def _document_of(document_id: uuid.UUID, session: Session) -> Document:
    documento = session.get(Document, document_id)
    if documento is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "documento não encontrado")
    return documento


@router.post(
    "/students/{student_id}/documents",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
)
async def post_document(
    student_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    store: Annotated[ObjectStore, Depends(get_object_store)],
    provider: Annotated[ExtractionProvider, Depends(get_extraction_provider)],
    file: Annotated[UploadFile, File()],
    kind: Annotated[DocumentKind, Form()] = "grade",
) -> DocumentOut:
    """Recebe o arquivo, guarda o original e já tenta extrair a rotina."""
    aluno = session.get(Student, student_id)
    if aluno is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "aluno não encontrado")

    conteudo = await file.read(MAX_UPLOAD_BYTES + 1)
    try:
        documento = upload(
            session,
            aluno,
            content=conteudo,
            content_type=file.content_type or "",
            filename=file.filename or "arquivo",
            kind=kind,
            store=store,
        )
    except ConsentMissing as erro:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(erro)) from erro
    except DocumentError as erro:
        raise HTTPException(UNPROCESSABLE, str(erro)) from erro

    extract(session, documento, store=store, provider=provider)
    return _to_out(documento)


@router.get("/documents/{document_id}", response_model=DocumentOut)
def get_document(
    document_id: uuid.UUID, session: Annotated[Session, Depends(get_session)]
) -> DocumentOut:
    return _to_out(_document_of(document_id, session))


@router.post("/documents/{document_id}/confirm", response_model=ConfirmOut)
def post_confirm(
    document_id: uuid.UUID,
    payload: RoutineExtraction,
    session: Annotated[Session, Depends(get_session)],
) -> ConfirmOut:
    """A semana que o aluno conferiu — com as correções dele — vira rotina oficial."""
    documento = _document_of(document_id, session)
    aluno = session.get(Student, documento.student_id)
    if aluno is None:  # pragma: no cover - FK garante
        raise HTTPException(status.HTTP_404_NOT_FOUND, "aluno não encontrado")

    try:
        resultado = confirm(session, documento, extraction=payload, today=today_in(aluno.timezone))
    except DocumentError as erro:
        raise HTTPException(UNPROCESSABLE, str(erro)) from erro

    return ConfirmOut(
        document=_to_out(resultado.document),
        commitments=resultado.commitments,
        days_recalculated=resultado.days_recalculated,
        replan_summary=resultado.replan_summary,
    )


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    store: Annotated[ObjectStore, Depends(get_object_store)],
) -> None:
    """Exclusão a pedido do aluno: o arquivo e o registro somem."""
    erase(session, _document_of(document_id, session), store)
