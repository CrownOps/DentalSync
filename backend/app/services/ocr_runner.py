"""OCR 실행 오케스트레이션.

서비스 레이어는 OCREngine 인터페이스에만 의존한다(구체 CLOVA 엔진 import 금지).
성공: status → routing. OCR 실패: status → ocr_failed 후 예외 재전파(수동 재시도 대상).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Lab, Order
from app.domain.enums import OrderStatus
from app.domain.errors import OrderNotFoundError
from app.infra.ocr.base import OCREngine, OCRExtractionError, OCRField
from app.infra.storage import StorageClient


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

    order.status = OrderStatus.ocr_running
    session.flush()

    image = storage.get_object(order.image_url)  # StorageError 는 상위로 전파(미커밋→롤백)

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
    return OCRRunResult(order_id=order_id, status=OrderStatus.routing, fields=fields)
