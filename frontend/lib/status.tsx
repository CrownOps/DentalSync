// OrderStatus enum 과 1:1 — 한글 라벨 + 배지 색상. 여러 화면(기공소 조회/달력)에서 공용.

export const STATUS_META: Record<string, { label: string; className: string }> = {
  uploaded: { label: "업로드됨", className: "bg-gray-100 text-gray-700" },
  preprocessing: { label: "전처리중", className: "bg-gray-100 text-gray-700" },
  ocr_running: { label: "OCR 진행중", className: "bg-blue-100 text-blue-700" },
  routing: { label: "라우팅중", className: "bg-blue-100 text-blue-700" },
  needs_review: { label: "검토 필요", className: "bg-yellow-100 text-yellow-700" },
  auto_confirmed: { label: "자동 확정", className: "bg-green-100 text-green-700" },
  confirmed: { label: "확정", className: "bg-green-100 text-green-800" },
  ocr_failed: { label: "OCR 실패", className: "bg-red-100 text-red-700" },
};

// 필터 칩 노출 순서 (스캔 완료 → 진행중 → 실패 순)
export const FILTER_STATUSES = [
  "needs_review",
  "auto_confirmed",
  "confirmed",
  "uploaded",
  "preprocessing",
  "ocr_running",
  "routing",
  "ocr_failed",
] as const;

export function StatusBadge({ status }: { status: string }) {
  const meta = STATUS_META[status] ?? {
    label: status,
    className: "bg-gray-100 text-gray-700",
  };
  return (
    <span className={`rounded px-2 py-0.5 text-xs font-medium ${meta.className}`}>
      {meta.label}
    </span>
  );
}
