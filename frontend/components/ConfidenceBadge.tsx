// 신뢰도 색상 코딩 공통 컴포넌트 — 전 화면에서 동일하게 사용 (sSpec 3.2 / 3.3)

interface ConfidenceBadgeProps {
  score: number | null;
}

/** 신뢰도 점수 배지 — 녹(≥0.90) / 황(0.60~) / 적(<0.60) */
export function ConfidenceBadge({ score }: ConfidenceBadgeProps) {
  if (score === null) return <span className="text-gray-400 text-xs">—</span>;
  const pct = Math.round(score * 100);
  const cls =
    score >= 0.9
      ? "bg-green-100 text-green-800"
      : score >= 0.6
        ? "bg-yellow-100 text-yellow-800"
        : "bg-red-100 text-red-800";
  return (
    <span className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium ${cls}`}>
      {pct}%
    </span>
  );
}

/** 신뢰도에 따른 테두리 클래스 */
export function confidenceBorderClass(score: number | null): string {
  if (score === null) return "border-gray-200";
  if (score >= 0.9) return "border-green-300";
  if (score >= 0.6) return "border-yellow-300";
  return "border-red-300";
}

/** 신뢰도에 따른 배경 클래스 */
export function confidenceBgClass(score: number | null): string {
  if (score === null) return "";
  if (score >= 0.9) return "bg-green-50";
  if (score >= 0.6) return "bg-yellow-50";
  return "bg-red-50";
}

/** 치명 필드 배지 (spec 3.3 — 임계값 0.95) */
export function CriticalBadge() {
  return (
    <span className="inline-block rounded bg-red-100 px-1.5 py-0.5 text-xs font-semibold text-red-700">
      치명
    </span>
  );
}

/** PII 필드 배지 */
export function PiiBadge() {
  return (
    <span className="inline-block rounded bg-purple-100 px-1.5 py-0.5 text-xs font-normal text-purple-700">
      PII
    </span>
  );
}

/** 필드 라우팅 타입 배지 */
export function FieldTypeBadge({ fieldType }: { fieldType: string }) {
  const cls: Record<string, string> = {
    A: "bg-blue-100 text-blue-700",
    B: "bg-teal-100 text-teal-700",
    C: "bg-violet-100 text-violet-700",
    SHADE: "bg-orange-100 text-orange-700",
  };
  return (
    <span
      className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium ${cls[fieldType] ?? "bg-gray-100 text-gray-600"}`}
    >
      {fieldType}
    </span>
  );
}
