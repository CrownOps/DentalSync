"""의뢰서 업로드 파이프라인(앞단) 오케스트레이션.

흐름: 검증 → 전처리 → 해시 → 캐시조회 → R2 업로드 + orders 생성.
트랜잭션 단위는 '의뢰서' — R2 또는 DB 실패 시 부분 저장 없이 전체 실패.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Lab, Order
from app.domain.enums import OrderStatus
from app.domain.errors import LabNotFoundError, StorageError
from app.infra.cache import CacheClient
from app.infra.storage import StorageClient
from app.services import preprocessing
from app.services.hashing import sha256_hex
from app.services.image_validation import ImageValidationConfig, validate_upload

_EXT = {
    preprocessing.MEDIA_JPEG: "jpg",
    preprocessing.MEDIA_PNG: "png",
    preprocessing.MEDIA_PDF: "pdf",
}


def cache_key(image_hash: str) -> str:
    return f"imgocr:{image_hash}"


def object_key(image_hash: str, media_type: str) -> str:
    return f"orders/{image_hash}.{_EXT[media_type]}"


@dataclass
class IntakeResult:
    order_id: int
    image_hash: str
    status: OrderStatus
    cache_hit: bool
    ocr_cached: bool  # 캐시 HIT 시 CLOVA 호출 생략 플래그


def intake_order(
    *,
    session: Session,
    lab_id: int,
    data: bytes,
    storage: StorageClient,
    cache: CacheClient,
    settings: Settings,
) -> IntakeResult:
    if session.get(Lab, lab_id) is None:
        raise LabNotFoundError(lab_id)

    # 1) 검증 (실패 시 ImageValidationError → 422)
    validated = validate_upload(data, ImageValidationConfig.from_settings(settings))

    # 2) 전처리 (독립 모듈) — 결과는 후속 OCR 단계 입력. 앞단에서는 파이프라인만 수행.
    preprocessing.preprocess(validated.image)

    # 3) SHA-256 해시
    image_hash = sha256_hex(data)

    # 4) 이미지 해시 캐시 조회 (HIT → CLOVA 생략 플래그)
    cache_hit = cache.get(cache_key(image_hash)) is not None

    # 5~6) R2 업로드 + orders 생성. 트랜잭션 단위=의뢰서, 부분 저장 금지.
    key = object_key(image_hash, validated.media_type)
    order = Order(
        lab_id=lab_id,
        image_url=key,
        image_hash=image_hash,
        status=OrderStatus.uploaded,
    )
    session.add(order)
    session.flush()  # INSERT (아직 커밋 전)

    try:
        storage.put_object(key, data, validated.media_type)
    except StorageError:
        session.rollback()  # R2 실패 → 의뢰서 레코드도 롤백
        raise

    try:
        session.commit()
    except Exception:
        # DB 커밋 실패 → 방금 업로드한 객체 보상 삭제(오펀 방지)
        with contextlib.suppress(StorageError):
            storage.delete_object(key)
        session.rollback()
        raise

    return IntakeResult(
        order_id=order.id,
        image_hash=image_hash,
        status=OrderStatus.uploaded,
        cache_hit=cache_hit,
        ocr_cached=cache_hit,
    )
