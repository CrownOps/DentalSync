"use client";

import { useState } from "react";
import Link from "next/link";
import { ReviewQueueItem } from "@/lib/api";
import { useLabOrders } from "@/lib/hooks";
import { RequireLab } from "@/components/RequireLab";
import type { LabSession } from "@/lib/auth";
import { FILTER_STATUSES, STATUS_META, StatusBadge } from "@/lib/status";

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
      className="flex items-center gap-4 rounded-lg border border-gray-200 bg-white px-4 py-3 hover:bg-gray-50"
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

function LabOrders({ lab }: { lab: LabSession }) {
  const [statuses, setStatuses] = useState<string[]>([]);

  const { data, isLoading, isError, error, isFetching } = useLabOrders(
    lab.labId,
    statuses.length > 0 ? statuses : undefined,
  );

  function toggleStatus(s: string) {
    setStatuses((prev) =>
      prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s],
    );
  }

  return (
    <main className="mx-auto max-w-3xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">의뢰서 조회</h1>
          <p className="mt-0.5 text-xs text-gray-500">{lab.name}</p>
        </div>
        <Link
          href="/calendar"
          className="rounded-lg border border-brand-200 bg-brand-50 px-3 py-1.5 text-sm font-medium text-brand-700 transition-colors hover:bg-brand-100"
        >
          달력으로 보기
        </Link>
      </div>

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
                  ? "border-brand-500 bg-brand-50 text-brand-700"
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
      {(isLoading || isFetching) && <p className="text-gray-500">불러오는 중…</p>}
      {isError && <p className="text-red-600">오류: {(error as Error).message}</p>}
      {data && !isFetching && data.length === 0 && (
        <p className="text-gray-500">
          의뢰서가 없습니다
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

export default function LabOrdersPage() {
  return <RequireLab>{(lab) => <LabOrders lab={lab} />}</RequireLab>;
}
