"""이미지 검증 단위 테스트 — 반려 코드/재촬영 안내."""

from __future__ import annotations

import pytest

from app.domain.errors import ImageRejectCode, ImageValidationError
from app.services import preprocessing as pp
from app.services.image_validation import (
    ImageValidationConfig,
    validate_upload,
)
from tests.imaging_utils import blurred_jpeg, sharp_jpeg


def _config(
    *,
    max_bytes: int = 100_000_000,
    min_width: int = 200,
    min_height: int = 200,
    blur_min: float = 0.0,
) -> ImageValidationConfig:
    return ImageValidationConfig(
        max_bytes=max_bytes,
        min_width=min_width,
        min_height=min_height,
        blur_min=blur_min,
        pdf_dpi=200,
    )


def test_valid_image_passes() -> None:
    result = validate_upload(sharp_jpeg(800, 600), _config())
    assert result.media_type == pp.MEDIA_JPEG
    assert (result.width, result.height) == (800, 600)


def test_empty_file() -> None:
    with pytest.raises(ImageValidationError) as ei:
        validate_upload(b"", _config())
    assert ei.value.code is ImageRejectCode.EMPTY_FILE


def test_unsupported_type() -> None:
    with pytest.raises(ImageValidationError) as ei:
        validate_upload(b"GIF89a\x00\x00garbage", _config())
    assert ei.value.code is ImageRejectCode.UNSUPPORTED_FILE_TYPE


def test_file_too_large() -> None:
    with pytest.raises(ImageValidationError) as ei:
        validate_upload(sharp_jpeg(800, 600), _config(max_bytes=10))
    assert ei.value.code is ImageRejectCode.FILE_TOO_LARGE


def test_resolution_too_low() -> None:
    with pytest.raises(ImageValidationError) as ei:
        validate_upload(sharp_jpeg(300, 300), _config(min_width=1000, min_height=1000))
    assert ei.value.code is ImageRejectCode.RESOLUTION_TOO_LOW
    assert ei.value.guidance  # 재촬영 안내 포함


def test_corrupt_image() -> None:
    corrupt = b"\xff\xd8\xff" + b"\x00" * 64  # JPEG 매직 + 깨진 본문
    with pytest.raises(ImageValidationError) as ei:
        validate_upload(corrupt, _config())
    assert ei.value.code is ImageRejectCode.CORRUPT_IMAGE


def test_image_too_blurry() -> None:
    data = blurred_jpeg()
    variance = pp.laplacian_variance(pp.decode_image(data, pp.MEDIA_JPEG))
    # 측정값보다 살짝 높은 임계값 → 반드시 블러로 반려 (절댓값 의존 없는 결정적 테스트)
    with pytest.raises(ImageValidationError) as ei:
        validate_upload(data, _config(blur_min=variance + 1.0))
    assert ei.value.code is ImageRejectCode.IMAGE_TOO_BLURRY
    assert "촬영" in ei.value.guidance  # 재촬영 안내
