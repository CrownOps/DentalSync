"""도메인 예외 및 에러 코드."""

from __future__ import annotations

from enum import StrEnum


class ImageRejectCode(StrEnum):
    """이미지 검증 반려 코드."""

    EMPTY_FILE = "EMPTY_FILE"
    UNSUPPORTED_FILE_TYPE = "UNSUPPORTED_FILE_TYPE"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    CORRUPT_IMAGE = "CORRUPT_IMAGE"
    RESOLUTION_TOO_LOW = "RESOLUTION_TOO_LOW"
    IMAGE_TOO_BLURRY = "IMAGE_TOO_BLURRY"


class ImageValidationError(Exception):
    """이미지 검증 실패 — 422 로 매핑되며 재촬영 안내를 포함한다."""

    def __init__(self, code: ImageRejectCode, message: str, guidance: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.guidance = guidance


class LabNotFoundError(Exception):
    """존재하지 않는 기공소 — 404."""

    def __init__(self, lab_id: int) -> None:
        super().__init__(f"lab {lab_id} not found")
        self.lab_id = lab_id


class DuplicateLabCodeError(Exception):
    """이미 사용 중인 기공소 로그인 코드 — 409."""

    def __init__(self, code: str) -> None:
        super().__init__(f"lab code already exists: {code}")
        self.code = code


class StorageError(Exception):
    """오브젝트 스토리지(R2) 작업 실패."""


class OrderNotFoundError(Exception):
    """존재하지 않는 의뢰서 — 404."""

    def __init__(self, order_id: int) -> None:
        super().__init__(f"order {order_id} not found")
        self.order_id = order_id
