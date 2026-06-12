"""OCR 실행 오케스트레이션.

서비스 레이어는 OCREngine 인터페이스에만 의존한다(구체 CLOVA 엔진 import 금지).
성공: status → routing → (라우팅 결과 저장) → needs_review | auto_confirmed.
OCR 실패: status → ocr_failed 후 예외 재전파(수동 재시도 대상).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.scoring import get_scoring_config
from app.db.models import Lab, Order
from app.domain.enums import OrderStatus
from app.domain.errors import OrderNotFoundError, StorageError
from app.infra.ocr.base import OCREngine, OCRExtractionError, OCRField
from app.infra.storage import StorageClient
from app.services.routing import route_ocr_fields
from app.services.routing_store import store_routing_result


@dataclass
class OCRRunResult:
    order_id: int
    status: OrderStatus
    fields: list[OCRField]


async def run_ocr(
    *,
    session: Session,
    order_id: int,
    engine: OCREngine,
    storage: StorageClient,
    settings: Settings,
) -> OCRRunResult:
    order = session.get(Order, order_id)
    if order is None:
        raise OrderNotFoundError(order_id)

    # 커밋해야 폴링(타 세션)에서 ocr_running 이 보인다 — flush 는 현 세션 한정.
    order.status = OrderStatus.ocr_running
    session.commit()

    try:
        image = storage.get_object(order.image_url)
    except StorageError:
        # ocr_running 이 커밋된 뒤이므로, 실패를 ocr_failed 로 착지시켜 재시도 대상으로 만든다.
        order.status = OrderStatus.ocr_failed
        session.commit()
        raise

    lab = session.get(Lab, order.lab_id)
    template_id = (lab.template_id if lab and lab.template_id else "") or settings.clova_template_id

    try:
        fields = await engine.extract(image, template_id)
    except OCRExtractionError:
        order.status = OrderStatus.ocr_failed
        session.commit()
        raise

    order.status = OrderStatus.routing
    session.commit()

    # 라우팅 결과 저장 — 상태를 needs_review | auto_confirmed 로 전이.
    # 실패 시 store_routing_result 가 롤백 후 routing 상태를 유지한다.
    cfg = get_scoring_config()
    routed = route_ocr_fields(fields, cfg)
    store_result = store_routing_result(
        session=session,
        order_id=order_id,
        field_results=routed,
        scoring_cfg=cfg,
    )

    return OCRRunResult(order_id=order_id, status=store_result.status, fields=fields)
