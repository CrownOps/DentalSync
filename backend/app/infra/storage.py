"""오브젝트 스토리지 추상화 — Cloudflare R2(S3 호환, boto3).

CLAUDE.md: 외부 서비스는 인터페이스 추상화 + mock 가능하게. 테스트는 FakeStorage 주입.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from app.core.config import Settings
from app.domain.errors import StorageError


class StorageClient(Protocol):
    def put_object(self, key: str, data: bytes, content_type: str) -> None: ...

    def get_object(self, key: str) -> bytes: ...

    def delete_object(self, key: str) -> None: ...

    def generate_presigned_url(self, key: str, expires: int = 300) -> str: ...


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

    def get_object(self, key: str) -> bytes:
        try:
            resp = self._client.get_object(Bucket=self._bucket, Key=key)
            body: bytes = resp["Body"].read()
            return body
        except Exception as exc:
            raise StorageError(f"R2 조회 실패(key={key}): {exc}") from exc

    def delete_object(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
        except Exception as exc:
            raise StorageError(f"R2 삭제 실패(key={key}): {exc}") from exc

    def generate_presigned_url(self, key: str, expires: int = 300) -> str:
        try:
            url: str = self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=expires,
            )
            return url
        except Exception as exc:
            raise StorageError(f"Presigned URL 생성 실패(key={key}): {exc}") from exc


class LocalDirStorage:
    """로컬 파일시스템 스토리지 — 로컬 개발 전용(storage_backend=local). 운영은 R2.

    URL 은 main.py 가 /local-files 로 마운트한 StaticFiles 경로를 가리킨다.
    """

    def __init__(self, *, root: Path, public_base_url: str) -> None:
        self._root = root
        self._public_base_url = public_base_url.rstrip("/")

    @classmethod
    def from_settings(cls, settings: Settings) -> LocalDirStorage:
        return cls(
            root=settings.local_storage_dir,
            public_base_url=settings.public_base_url,
        )

    def _path(self, key: str) -> Path:
        path = (self._root / key).resolve()
        if not path.is_relative_to(self._root.resolve()):
            raise StorageError(f"잘못된 객체 키(경로 이탈): {key}")
        return path

    def put_object(self, key: str, data: bytes, content_type: str) -> None:
        try:
            path = self._path(key)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        except OSError as exc:
            raise StorageError(f"로컬 저장 실패(key={key}): {exc}") from exc

    def get_object(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except OSError as exc:
            raise StorageError(f"로컬 조회 실패(key={key}): {exc}") from exc

    def delete_object(self, key: str) -> None:
        try:
            self._path(key).unlink(missing_ok=True)
        except OSError as exc:
            raise StorageError(f"로컬 삭제 실패(key={key}): {exc}") from exc

    def generate_presigned_url(self, key: str, expires: int = 300) -> str:
        # 로컬은 서명 불필요 — 정적 마운트 URL 반환
        return f"{self._public_base_url}/local-files/{key}"
