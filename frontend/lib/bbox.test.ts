import { describe, it, expect } from "vitest";
import { parseBbox, bboxToRect } from "./bbox";

describe("parseBbox", () => {
  it("null 입력 → null", () => {
    expect(parseBbox(null)).toBeNull();
  });

  it("vertices 누락 → null", () => {
    expect(parseBbox({})).toBeNull();
  });

  it("vertices 1개 → null (최소 2개 필요)", () => {
    expect(parseBbox({ vertices: [{ x: 1, y: 2 }] })).toBeNull();
  });

  it("정상 boundingPoly 파싱", () => {
    const bbox = parseBbox({
      vertices: [
        { x: 10, y: 20 },
        { x: 110, y: 20 },
        { x: 110, y: 60 },
        { x: 10, y: 60 },
      ],
    });
    expect(bbox).not.toBeNull();
    expect(bbox!.vertices).toHaveLength(4);
  });
});

describe("bboxToRect", () => {
  const bbox = {
    vertices: [
      { x: 100, y: 200 },
      { x: 300, y: 200 },
      { x: 300, y: 280 },
      { x: 100, y: 280 },
    ],
  };

  it("원본 = 표시 크기 (1:1 스케일)", () => {
    const rect = bboxToRect(bbox, 1000, 1000, 1000, 1000);
    expect(rect).toEqual({ left: 100, top: 200, width: 200, height: 80 });
  });

  it("표시 크기 절반 (0.5 배율)", () => {
    const rect = bboxToRect(bbox, 500, 500, 1000, 1000);
    expect(rect).toEqual({ left: 50, top: 100, width: 100, height: 40 });
  });

  it("가로/세로 비등방 스케일", () => {
    // 가로 2배, 세로 0.5배
    const rect = bboxToRect(bbox, 2000, 500, 1000, 1000);
    expect(rect).toEqual({ left: 200, top: 100, width: 400, height: 40 });
  });

  it("기울어진 bbox (회전된 의뢰서) — min/max 외접 사각형", () => {
    const skewed = {
      vertices: [
        { x: 100, y: 210 },
        { x: 295, y: 200 },
        { x: 300, y: 270 },
        { x: 105, y: 280 },
      ],
    };
    const rect = bboxToRect(skewed, 1000, 1000, 1000, 1000);
    expect(rect.left).toBe(100);
    expect(rect.top).toBe(200);
    expect(rect.width).toBe(200);
    expect(rect.height).toBe(80);
  });
});
