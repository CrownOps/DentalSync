"""전처리 독립 함수 단위 테스트."""

from __future__ import annotations

from app.services import preprocessing as pp
from tests.imaging_utils import blurred_array, encode_png, sharp_array, sharp_jpeg


def test_detect_media_type() -> None:
    assert pp.detect_media_type(sharp_jpeg()) == pp.MEDIA_JPEG
    assert pp.detect_media_type(encode_png(sharp_array(200, 200))) == pp.MEDIA_PNG
    assert pp.detect_media_type(b"%PDF-1.7\n...") == pp.MEDIA_PDF
    assert pp.detect_media_type(b"not an image") is None


def test_decode_jpeg_dimensions() -> None:
    img = pp.decode_image(sharp_jpeg(800, 600), pp.MEDIA_JPEG)
    assert pp.image_dimensions(img) == (800, 600)


def test_laplacian_variance_sharp_gt_blurred() -> None:
    sharp_v = pp.laplacian_variance(sharp_array())
    blurred_v = pp.laplacian_variance(blurred_array())
    assert sharp_v > blurred_v
    assert blurred_v < sharp_v / 2  # 블러로 분명히 낮아짐


def test_resize_max_scales_down_and_keeps_small() -> None:
    big = sharp_array(4000, 3000)
    resized = pp.resize_max(big, 2000)
    w, h = pp.image_dimensions(resized)
    assert max(w, h) == 2000

    small = sharp_array(500, 400)
    assert pp.image_dimensions(pp.resize_max(small, 2000)) == (500, 400)


def test_deskew_and_denoise_return_same_shape() -> None:
    img = sharp_array(600, 800)
    assert pp.deskew(img).shape == img.shape
    assert pp.denoise(img).shape == img.shape


def test_preprocess_pipeline_runs() -> None:
    out = pp.preprocess(sharp_array(2500, 2000), max_dim=1500)
    w, h = pp.image_dimensions(out)
    assert max(w, h) == 1500
