"use client";

import { useState } from "react";
import Link from "next/link";
import { ReviewQueueItem } from "@/lib/api";
import { useLabOrders } from "@/lib/hooks";

// OrderStatus enum 과 1:1 — 한글 라벨 + 배지 색상
const STATUS_META: Record<string, { label: string; className: string }> = {
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
const FILTER_STATUSES = [
  "needs_review",
  "auto_confirmed",
  "confirmed",
  "uploaded",
  "preprocessing",
  "ocr_running",
  "routing",
  "ocr_failed",
] as const;

function StatusBadge({ status }: { status: string }) {
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

function ScoreBadge({ score }: { score: number | null }) {
  if (score === null) return <span className="text-xs text-gray-400">—</span>;
  const pct = Math.round(score * 100);
  const color =
    score >= 0.9
      ? "bg-green-100 text-green-800"
      : score >= 0.6
        ? "bg-yellow-100 text-yellow-800"
        : "bg-red-100 text-red-800";
  return (
    <span className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium ${color}`}>
      {pct}%
    </span>
  );
}

function OrderRow({ item }: { item: ReviewQueueItem }) {
  return (
    <Link
      href={`/orders/${item.order_id}`}
      className="flex items-center gap-4 rounded-lg border border-gray-200 px-4 py-3 hover:bg-gray-50"
    >
      <span className="w-16 font-mono text-sm text-gray-500">#{item.order_id}</span>
      <StatusBadge status={item.status} />
      <span className="flex-1 text-xs text-gray-500">
        {item.received_at ? item.received_at.slice(0, 10) : "—"}
      </span>
      <span className="w-20 text-xs text-gray-500">필드 {item.field_count}개</span>
      <ScoreBadge score={item.min_score} />
    </Link>
  );
}

export default function LabOrdersPage() {
  const [labInput, setLabInput] = useState("");
  const [labId, setLabId] = useState<number | null>(null);
  const [statuses, setStatuses] = useState<string[]>([]);

  const { data, isLoading, isError, error, isFetching } = useLabOrders(
    labId,
    statuses.length > 0 ? statuses : undefined,
  );

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    const parsed = parseInt(labInput, 10);
    setLabId(Number.isNaN(parsed) ? null : parsed);
  }

  function toggleStatus(s: string) {
    setStatuses((prev) =>
      prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s],
    );
  }

  return (
    <main className="mx-auto max-w-3xl px-4 py-8">
      <h1 className="mb-6 text-2xl font-bold text-gray-900">기공소별 의뢰서 조회</h1>

      {/* 기공소 ID 입력 */}
      <form onSubmit={handleSearch} className="mb-4 flex items-center gap-2">
        <input
          type="number"
          min={1}
          value={labInput}
          onChange={(e) => setLabInput(e.target.value)}
          placeholder="기공소 ID 입력"
          className="w-48 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-400 focus:outline-none"
        />
        <button
          type="submit"
          disabled={labInput.trim() === ""}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:bg-gray-300"
        >
          조회
        </button>
      </form>

      {/* 상태 필터 */}
      <div className="mb-6 flex flex-wrap gap-2">
        {FILTER_STATUSES.map((s) => {
          const active = statuses.includes(s);
          return (
            <button
              key={s}
              type="button"
              onClick={() => toggleStatus(s)}
              className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                active
                  ? "border-blue-500 bg-blue-50 text-blue-700"
                  : "border-gray-200 bg-white text-gray-500 hover:bg-gray-50"
              }`}
            >
              {STATUS_META[s].label}
            </button>
          );
        })}
        {statuses.length > 0 && (
          <button
            type="button"
            onClick={() => setStatuses([])}
            className="rounded-full px-3 py-1 text-xs font-medium text-gray-400 underline"
          >
            전체
          </button>
        )}
      </div>

      {/* 결과 */}
      {labId === null && (
        <p className="text-gray-500">기공소 ID를 입력하고 조회하세요.</p>
      )}
      {labId !== null && (isLoading || isFetching) && (
        <p className="text-gray-500">불러오는 중…</p>
      )}
      {isError && <p className="text-red-600">오류: {(error as Error).message}</p>}
      {data && !isFetching && data.length === 0 && (
        <p className="text-gray-500">
          기공소 {labId}의 의뢰서가 없습니다
          {statuses.length > 0 ? " (선택한 상태 기준)" : ""}.
        </p>
      )}
      {data && data.length > 0 && (
        <>
          <p className="mb-3 text-sm text-gray-500">{data.length}건</p>
          <div className="flex flex-col gap-2">
            {data.map((item) => (
              <OrderRow key={item.order_id} item={item} />
            ))}
          </div>
        </>
      )}
    </main>
  );
}
