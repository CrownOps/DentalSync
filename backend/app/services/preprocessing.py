"""이미지 전처리 — OpenCV 기반 독립 함수 모음.

각 함수는 부수효과 없이 ndarray 를 입력받아 ndarray(또는 스칼라)를 반환한다.
파이프라인(preprocess)과 개별 단계(deskew/denoise/resize)를 분리해 단위 테스트가
가능하도록 한다.
"""

from __future__ import annotations

import cv2
import fitz  # PyMuPDF
import numpy as np
from numpy.typing import NDArray

Image = NDArray[np.uint8]

MEDIA_JPEG = "image/jpeg"
MEDIA_PNG = "image/png"
MEDIA_PDF = "application/pdf"

_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", MEDIA_JPEG),
    (b"\x89PNG\r\n\x1a\n", MEDIA_PNG),
    (b"%PDF", MEDIA_PDF),
)


def detect_media_type(data: bytes) -> str | None:
    """매직 바이트로 실제 포맷을 판별(클라이언트 content-type 불신)."""
    for magic, media in _MAGIC:
        if data.startswith(magic):
            return media
    return None


def _decode_pdf_first_page(data: bytes, dpi: int) -> Image:
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        if doc.page_count < 1:
            raise ValueError("빈 PDF")
        page = doc.load_page(0)
        zoom = dpi / 72.0
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        buf = np.frombuffer(pix.samples, dtype=np.uint8)
        arr = buf.reshape(pix.height, pix.width, pix.n)
        if pix.n == 4:
            return cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
        if pix.n == 3:
            return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        return cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)
    finally:
        doc.close()


def decode_image(data: bytes, media_type: str, *, pdf_dpi: int = 200) -> Image:
    """원본 바이트 → BGR 이미지. 디코드 실패 시 ValueError."""
    if media_type == MEDIA_PDF:
        return _decode_pdf_first_page(data, pdf_dpi)
    if media_type in (MEDIA_JPEG, MEDIA_PNG):
        buf = np.frombuffer(data, dtype=np.uint8)
        img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("이미지 디코드 실패")
        return img
    raise ValueError(f"지원하지 않는 media_type: {media_type}")


def to_grayscale(img: Image) -> Image:
    if img.ndim == 2:
        return img
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def image_dimensions(img: Image) -> tuple[int, int]:
    """(width, height)."""
    h, w = img.shape[:2]
    return int(w), int(h)


def laplacian_variance(img: Image) -> float:
    """Laplacian variance — 값이 클수록 선명, 작을수록 흐릿(블러)."""
    gray = to_grayscale(img)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def deskew(img: Image) -> Image:
    """전경 텍스트의 최소외접사각형 각도로 기울기 보정."""
    gray = to_grayscale(img)
    inverted = cv2.bitwise_not(gray)
    _, thresh = cv2.threshold(inverted, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    coords = cv2.findNonZero(thresh)
    if coords is None:
        return img
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = 90 + angle
    if abs(angle) < 0.1:
        return img
    h, w = img.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(
        img, matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
    )


def denoise(img: Image) -> Image:
    """엣지 보존 노이즈 제거(bilateral filter)."""
    return cv2.bilateralFilter(img, d=9, sigmaColor=75, sigmaSpace=75)


def resize_max(img: Image, max_dim: int) -> Image:
    """긴 변이 max_dim 을 넘으면 비율 유지 축소(작으면 그대로)."""
    h, w = img.shape[:2]
    longest = max(h, w)
    if longest <= max_dim:
        return img
    scale = max_dim / longest
    new_size = (round(w * scale), round(h * scale))
    return cv2.resize(img, new_size, interpolation=cv2.INTER_AREA)


def preprocess(img: Image, *, max_dim: int = 2000) -> Image:
    """전처리 파이프라인: deskew → denoise → resize."""
    return resize_max(denoise(deskew(img)), max_dim)
