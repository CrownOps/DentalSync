"""오브젝트 스토리지 추상화 — Cloudflare R2(S3 호환, boto3).

CLAUDE.md: 외부 서비스는 인터페이스 추상화 + mock 가능하게. 테스트는 FakeStorage 주입.
"""

from __future__ import annotations

from typing import Any, Protocol

from app.core.config import Settings
from app.domain.errors import StorageError


class StorageClient(Protocol):
    def put_object(self, key: str, data: bytes, content_type: str) -> None: ...

    def delete_object(self, key: str) -> None: ...


class R2Storage:
    """boto3 S3 호환 클라이언트로 R2 에 객체를 저장/삭제."""

    def __init__(
        self,
        *,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        region: str = "auto",
    ) -> None:
        import boto3

        self._bucket = bucket
        self._client: Any = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> R2Storage:
        endpoint = settings.r2_endpoint or (
            f"https://{settings.r2_account_id}.r2.cloudflarestorage.com"
        )
        return cls(
            endpoint_url=endpoint,
            access_key=settings.r2_access_key_id,
            secret_key=settings.r2_secret_access_key,
            bucket=settings.r2_bucket,
        )

    def put_object(self, key: str, data: bytes, content_type: str) -> None:
        try:
            self._client.put_object(
                Bucket=self._bucket, Key=key, Body=data, ContentType=content_type
            )
        except Exception as exc:
            raise StorageError(f"R2 업로드 실패(key={key}): {exc}") from exc

    def delete_object(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
        except Exception as exc:
            raise StorageError(f"R2 삭제 실패(key={key}): {exc}") from exc
