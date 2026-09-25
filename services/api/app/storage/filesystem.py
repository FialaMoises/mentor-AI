"""Object store em disco, para desenvolvimento.

A porta é a mesma do S3, então o resto do código não sabe a diferença. Existe
para que subir o projeto não dependa de nenhum serviço externo — em produção
quem atende é o S3.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from .base import ObjectStore, StorageError


class FileSystemStore(ObjectStore):
    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        """A chave é nossa, mas trata como se fosse do aluno: nada de sair da raiz."""
        partes = [p for p in PurePosixPath(key).parts if p not in ("", ".", "..")]
        if not partes:
            raise StorageError("chave vazia")
        destino = (self._root / Path(*partes)).resolve()
        if not destino.is_relative_to(self._root):
            raise StorageError(f"chave sai da raiz do store: {key}")
        return destino

    def put(self, key: str, data: bytes, content_type: str) -> None:
        destino = self._path(key)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(data)

    def get(self, key: str) -> bytes:
        destino = self._path(key)
        try:
            return destino.read_bytes()
        except OSError as erro:
            raise StorageError(f"não consegui ler {key}") from erro

    def delete(self, key: str) -> None:
        destino = self._path(key)
        destino.unlink(missing_ok=True)
