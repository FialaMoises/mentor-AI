"""Store em memória, para teste e para rodar a API sem S3 nenhum."""

from __future__ import annotations

from .base import ObjectStore, StorageError


class InMemoryStore(ObjectStore):
    def __init__(self) -> None:
        self._objetos: dict[str, tuple[bytes, str]] = {}

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self._objetos[key] = (data, content_type)

    def get(self, key: str) -> bytes:
        try:
            return self._objetos[key][0]
        except KeyError as erro:
            raise StorageError(f"não consegui ler {key}") from erro

    def delete(self, key: str) -> None:
        self._objetos.pop(key, None)

    def __contains__(self, key: str) -> bool:
        return key in self._objetos

    def __len__(self) -> int:
        return len(self._objetos)
