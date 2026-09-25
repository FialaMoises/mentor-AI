"""S3 em produção, MinIO em desenvolvimento — o mesmo código nos dois."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from ..config import get_settings
from .base import ObjectStore, StorageError


class S3Store(ObjectStore):
    def __init__(self, client: Any, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data, ContentType=content_type)

    def get(self, key: str) -> bytes:
        try:
            resposta = self._client.get_object(Bucket=self._bucket, Key=key)
        except Exception as erro:  # noqa: BLE001 - o cliente levanta tipos próprios
            raise StorageError(f"não consegui ler {key}") from erro
        conteudo: bytes = resposta["Body"].read()
        return conteudo

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)

    def ensure_bucket(self) -> None:
        """Cria o bucket em dev (MinIO sobe vazio). Em produção ele já existe."""
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except Exception:  # noqa: BLE001
            self._client.create_bucket(Bucket=self._bucket)


@lru_cache
def get_store() -> ObjectStore:
    import boto3

    settings = get_settings()
    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url or None,
        aws_access_key_id=settings.s3_access_key or None,
        aws_secret_access_key=settings.s3_secret_key or None,
        region_name=settings.s3_region,
    )
    store = S3Store(client, settings.s3_bucket)
    if settings.s3_endpoint_url:
        store.ensure_bucket()
    return store
