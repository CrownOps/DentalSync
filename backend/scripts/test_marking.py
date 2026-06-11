"""Type A 마킹 + Shade 인식 e2e 수동 검증 스크립트.

실제 의뢰서 샘플 1장으로 검증:
    uv run python scripts/test_marking.py --image 의뢰서.jpg --template template.json

template.json 형식(픽셀 좌표, [x, y, w, h]):
    {
      "checkbox_groups": {
        "prosthesis_type": {"크라운": [50, 100, 60, 60], "브릿지": [150, 100, 60, 60]},
        "material": {"지르코니아": [50, 200, 60, 60], "PFM": [150, 200, 60, 60]}
      },
      "shade_cells": {"A1": [50, 300, 80, 50], "A2": [150, 300, 80, 50]}
    }

샘플이 없으면 합성 데모로 즉시 확인:
    uv run python scripts/test_marking.py --demo
(데모는 .demo_marking/ 에 샘플 이미지+템플릿을 생성 후 동일 경로로 검증)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, cast

import cv2
import numpy as np
from numpy.typing import NDArray
from PIL import Image

from app.core.config import get_settings
from app.core.scoring import load_scoring_config
from app.services.dictionary import DictMatcher
from app.services.marking_detection import MarkingParams, detect_checkbox_group
from app.services.shade_detection import detect_shade


def _print_marking(name: str, result: Any) -> None:
    print(f"\n[Type A] {name}")
    print(f"  value={result.value!r}  rule_pass={result.rule_pass}")
    if "reason" in result.debug_info:
        print(f"  reason={result.debug_info['reason']}")
    for box in result.debug_info["boxes"]:
        mark = "✔" if box["marked"] else ("?" if box["ambiguous"] else " ")
        pen = f" pen={box['pen_color']}" if box["pen_color"] else ""
        print(
            f"   [{mark}] {box['label']:<10} ink={box['ink_density']:.3f}"
            f" color={box['color_ratio']:.3f}{pen}"
        )


def _print_shade(result: Any) -> None:
    print("\n[Shade]")
    print(f"  value={result.value!r}  rule_pass={result.rule_pass}  flags={result.flags}")
    if "reason" in result.debug_info:
        print(f"  reason={result.debug_info['reason']}")
    for cell in result.debug_info["cells"]:
        mark = "✔" if cell["marked"] else " "
        pen = f" pen={cell['pen_color']}" if cell["pen_color"] else ""
        print(f"   [{mark}] {cell['label']:<6} ratio={cell['mark_ratio']:.3f}{pen}")


def run(image_path: Path, template_path: Path) -> None:
    settings = get_settings()
    template = json.loads(template_path.read_text(encoding="utf-8"))

    loaded = cv2.imread(str(image_path))
    if loaded is None:
        raise SystemExit(f"이미지를 읽을 수 없음: {image_path}")
    bgr = cast("NDArray[np.uint8]", loaded)
    pil = Image.open(image_path)

    print(f"image={image_path}  template={template_path}")
    print(f"size={bgr.shape[1]}x{bgr.shape[0]}")

    params = MarkingParams.from_settings(settings)
    for group_name, options in template.get("checkbox_groups", {}).items():
        boxes = {label: tuple(bbox) for label, bbox in options.items()}
        result = detect_checkbox_group(bgr, boxes, params)
        _print_marking(group_name, result)

    shade_cells = template.get("shade_cells")
    if shade_cells:
        matcher = DictMatcher.from_settings(settings)
        threshold = load_scoring_config().threshold_for("shade")
        shade_result = detect_shade(
            pil,
            {label: tuple(bbox) for label, bbox in shade_cells.items()},
            matcher,
            mark_ratio_min=settings.shade_mark_ratio,
            critical_threshold=threshold,
        )
        _print_shade(shade_result)


def make_demo(out_dir: Path) -> tuple[Path, Path]:
    """합성 의뢰서 샘플(보철 체크 + 재료 체크 + 쉐이드 동그라미) 생성."""
    out_dir.mkdir(parents=True, exist_ok=True)
    img = np.full((420, 560, 3), 255, dtype=np.uint8)

    prosthesis = {"크라운": (40, 60, 56, 56), "브릿지": (160, 60, 56, 56),
                  "임플란트": (280, 60, 56, 56), "틀니": (400, 60, 56, 56)}
    material = {"지르코니아": (40, 170, 56, 56), "PFM": (160, 170, 56, 56),
                "골드": (280, 170, 56, 56)}
    shade = {"A1": (40, 290, 80, 50), "A2": (150, 290, 80, 50),
             "A3": (260, 290, 80, 50), "B1": (370, 290, 80, 50)}

    for boxes in (prosthesis, material):
        for x, y, w, h in boxes.values():
            cv2.rectangle(img, (x, y), (x + w, y + h), (0, 0, 0), 2)
    for x, y, w, h in shade.values():
        cv2.rectangle(img, (x, y), (x + w, y + h), (120, 120, 120), 1)

    # 마킹: 크라운=검정 X, 지르코니아=파랑 X, 쉐이드 A2=빨강 동그라미
    def mark_x(bbox: tuple[int, int, int, int], color: tuple[int, int, int]) -> None:
        x, y, w, h = bbox
        cv2.line(img, (x + 12, y + 12), (x + w - 12, y + h - 12), color, 5)
        cv2.line(img, (x + w - 12, y + 12), (x + 12, y + h - 12), color, 5)

    mark_x(prosthesis["크라운"], (0, 0, 0))
    mark_x(material["지르코니아"], (255, 0, 0))  # BGR 파랑
    sx, sy, sw, sh = shade["A2"]
    cv2.ellipse(img, (sx + sw // 2, sy + sh // 2), (32, 20), 0, 0, 360, (0, 0, 255), 4)

    image_path = out_dir / "demo_requisition.png"
    template_path = out_dir / "demo_template.json"
    cv2.imwrite(str(image_path), img)
    template = {
        "checkbox_groups": {
            "prosthesis_type": {k: list(v) for k, v in prosthesis.items()},
            "material": {k: list(v) for k, v in material.items()},
        },
        "shade_cells": {k: list(v) for k, v in shade.items()},
    }
    template_path.write_text(
        json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return image_path, template_path


def main() -> None:
    parser = argparse.ArgumentParser(description="마킹/쉐이드 감지 e2e 수동 검증")
    parser.add_argument("--image", type=Path, help="의뢰서 이미지 경로")
    parser.add_argument("--template", type=Path, help="bbox 템플릿 JSON 경로")
    parser.add_argument("--demo", action="store_true", help="합성 샘플 생성 후 검증")
    args = parser.parse_args()

    if args.demo:
        image_path, template_path = make_demo(Path(".demo_marking"))
        print("합성 데모 샘플 생성 완료")
    elif args.image and args.template:
        image_path, template_path = args.image, args.template
    else:
        parser.error("--image/--template 또는 --demo 를 지정하세요")

    run(image_path, template_path)


if __name__ == "__main__":
    main()
