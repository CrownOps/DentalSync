// bbox 좌표 변환 유틸 — CLOVA boundingPoly(원본 이미지 기준)를 표시 배율로 스케일.

export interface BBox {
  vertices: { x: number; y: number }[];
}

export interface Rect {
  left: number;
  top: number;
  width: number;
  height: number;
}

export function parseBbox(raw: Record<string, unknown> | null): BBox | null {
  if (!raw) return null;
  const verts = (raw as { vertices?: { x: number; y: number }[] }).vertices;
  if (!verts || verts.length < 2) return null;
  return { vertices: verts };
}

export function bboxToRect(
  bbox: BBox,
  imgW: number,
  imgH: number,
  naturalW: number,
  naturalH: number,
): Rect {
  const scaleX = imgW / naturalW;
  const scaleY = imgH / naturalH;
  const xs = bbox.vertices.map((v) => v.x * scaleX);
  const ys = bbox.vertices.map((v) => v.y * scaleY);
  return {
    left: Math.min(...xs),
    top: Math.min(...ys),
    width: Math.max(...xs) - Math.min(...xs),
    height: Math.max(...ys) - Math.min(...ys),
  };
}
