"""업로드 이미지 검증 — 타입/크기/해상도/블러. 실패 시 ImageValidationError."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.domain.errors import ImageRejectCode, ImageValidationError
from app.services import preprocessing
from app.services.preprocessing import Image

_RESHOOT = "사진을 다시 촬영해 주세요"


@dataclass(frozen=True)
class ImageValidationConfig:
    max_bytes: int
    min_width: int
    min_height: int
    blur_min: float
    pdf_dpi: int

    @classmethod
    def from_settings(cls, settings: Settings) -> ImageValidationConfig:
        return cls(
            max_bytes=settings.max_image_bytes,
            min_width=settings.min_image_width,
            min_height=settings.min_image_height,
            blur_min=settings.blur_laplacian_min,
            pdf_dpi=settings.pdf_render_dpi,
        )


@dataclass(frozen=True)
class ValidatedImage:
    media_type: str
    image: Image
    width: int
    height: int
    blur_variance: float


def validate_upload(data: bytes, config: ImageValidationConfig) -> ValidatedImage:
    """검증 통과 시 디코드된 이미지/메타 반환, 실패 시 ImageValidationError."""
    if not data:
        raise ImageValidationError(
            ImageRejectCode.EMPTY_FILE, "빈 파일입니다", "이미지 파일을 첨부해 주세요"
        )

    if len(data) > config.max_bytes:
        limit_mb = config.max_bytes / (1024 * 1024)
        raise ImageValidationError(
            ImageRejectCode.FILE_TOO_LARGE,
            f"파일이 너무 큽니다(최대 {limit_mb:.0f}MB)",
            "해상도를 낮추거나 다시 촬영해 주세요",
        )

    media_type = preprocessing.detect_media_type(data)
    if media_type is None:
        raise ImageValidationError(
            ImageRejectCode.UNSUPPORTED_FILE_TYPE,
            "지원하지 않는 형식입니다(jpg/png/pdf 만 허용)",
            "jpg, png, pdf 형식으로 다시 업로드해 주세요",
        )

    try:
        image = preprocessing.decode_image(data, media_type, pdf_dpi=config.pdf_dpi)
    except ValueError as exc:
        raise ImageValidationError(
            ImageRejectCode.CORRUPT_IMAGE,
            f"이미지를 읽을 수 없습니다: {exc}",
            _RESHOOT,
        ) from exc

    width, height = preprocessing.image_dimensions(image)
    if width < config.min_width or height < config.min_height:
        raise ImageValidationError(
            ImageRejectCode.RESOLUTION_TOO_LOW,
            f"해상도가 낮습니다({width}x{height}, 최소 {config.min_width}x{config.min_height})",
            f"{_RESHOOT}. 의뢰서가 화면에 가득 차도록 가까이서 촬영해 주세요",
        )

    blur_variance = preprocessing.laplacian_variance(image)
    if blur_variance < config.blur_min:
        raise ImageValidationError(
            ImageRejectCode.IMAGE_TOO_BLURRY,
            f"이미지가 흐립니다(선명도 {blur_variance:.1f}, 최소 {config.blur_min:.0f})",
            f"{_RESHOOT}. 초점을 맞추고 흔들리지 않게 촬영해 주세요",
        )

    return ValidatedImage(
        media_type=media_type,
        image=image,
        width=width,
        height=height,
        blur_variance=blur_variance,
    )
