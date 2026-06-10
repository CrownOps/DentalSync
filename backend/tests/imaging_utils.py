"""테스트용 합성 이미지 생성 헬퍼 (수집 대상 아님)."""

from __future__ import annotations

import cv2
import numpy as np


def sharp_array(width: int = 1200, height: int = 1600) -> np.ndarray:
    """고주파 노이즈 이미지 — Laplacian variance 가 높음(선명)."""
    rng = np.random.default_rng(1234)
    return rng.integers(0, 256, size=(height, width, 3), dtype=np.uint8)


def blurred_array(width: int = 1200, height: int = 1600) -> np.ndarray:
    """강하게 블러된 이미지 — Laplacian variance 가 낮음."""
    return cv2.GaussianBlur(sharp_array(width, height), (31, 31), 0)


def flat_array(width: int = 1200, height: int = 1600, value: int = 200) -> np.ndarray:
    """단색 이미지 — Laplacian variance 가 0(완전 블러)."""
    return np.full((height, width, 3), value, dtype=np.uint8)


def encode_jpeg(arr: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".jpg", arr)
    assert ok
    return bytes(buf.tobytes())


def encode_png(arr: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", arr)
    assert ok
    return bytes(buf.tobytes())


def sharp_jpeg(width: int = 1200, height: int = 1600) -> bytes:
    return encode_jpeg(sharp_array(width, height))


def blurred_jpeg(width: int = 1200, height: int = 1600) -> bytes:
    return encode_jpeg(blurred_array(width, height))


def flat_jpeg(width: int = 1200, height: int = 1600) -> bytes:
    return encode_jpeg(flat_array(width, height))
