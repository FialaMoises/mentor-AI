"""Porta do object store: guardar, ler e apagar o arquivo original."""

from __future__ import annotations

import uuid
from pathlib import PurePosixPath
from typing import Protocol

#: Só estes tipos entram. A checagem é no servidor, não no front.
ALLOWED_CONTENT_TYPES: dict[str, str] = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "image/png": ".png",
    "image/jpeg": ".jpg",
}

MAX_UPLOAD_BYTES = 10 * 1024 * 1024

#: Assinatura dos formatos aceitos, para não confiar no content-type do cliente.
MAGIC_BYTES: dict[str, tuple[bytes, ...]] = {
    "application/pdf": (b"%PDF-",),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (b"PK\x03\x04",),
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": (b"PK\x03\x04",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
}


class StorageError(RuntimeError):
    pass


class ObjectStore(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...

    def get(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...


def build_key(student_id: object, content_type: str) -> str:
    """A chave nunca vem do nome que o aluno mandou."""
    extension = ALLOWED_CONTENT_TYPES[content_type]
    return str(PurePosixPath("routines") / str(student_id) / f"{uuid.uuid4().hex}{extension}")


def safe_display_name(name: str) -> str:
    """Nome só para mostrar na tela: sem caminho, sem controle, curto."""
    limpo = PurePosixPath(name.replace("\\", "/")).name
    limpo = "".join(c for c in limpo if c.isprintable() and c not in '<>:"|?*')
    return (limpo or "arquivo")[:255]


def looks_like(content: bytes, content_type: str) -> bool:
    assinaturas = MAGIC_BYTES.get(content_type, ())
    return any(content.startswith(assinatura) for assinatura in assinaturas)
