"use client";

import Link from "next/link";
import { ReviewQueueItemV1 } from "@/lib/api";
import { useReviewQueue } from "@/lib/hooks";

function ScoreBadge({ score }: { score: number | null }) {
  if (score === null) return <span className="text-gray-400 text-xs">—</span>;
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

function QueueRow({ item }: { item: ReviewQueueItemV1 }) {
  return (
    <Link
      href={`/review/${item.order_id}`}
      className="flex items-center gap-4 rounded-lg border border-gray-200 px-4 py-3 hover:bg-gray-50"
    >
      <span className="w-16 text-sm font-mono text-gray-500">#{item.order_id}</span>
      <span className="flex-1 text-sm text-gray-800">기공소 {item.lab_id}</span>
      <span className="text-xs text-gray-500">
        {item.received_at ? item.received_at.slice(0, 10) : "—"}
      </span>
      <span className="w-24 text-xs text-gray-500">
        검토 {item.needs_review_count}개
      </span>
      <ScoreBadge score={item.min_score} />
      {item.has_forced_hitl && (
        <span className="rounded bg-orange-100 px-2 py-0.5 text-xs font-medium text-orange-700">
          강제검토
        </span>
      )}
      <span className="rounded bg-yellow-100 px-2 py-0.5 text-xs font-medium text-yellow-700">
        검토 필요
      </span>
    </Link>
  );
}

export default function ReviewQueuePage() {
  const { data, isLoading, isError, error } = useReviewQueue({ limit: 50 });

  return (
    <main className="mx-auto max-w-3xl px-4 py-8">
      <h1 className="mb-6 text-2xl font-bold text-gray-900">
        검토 큐
        {data && (
          <span className="ml-3 text-base font-normal text-gray-500">
            {data.total}건
          </span>
        )}
      </h1>

      {isLoading && <p className="text-gray-500">불러오는 중…</p>}
      {isError && (
        <p className="text-red-600">오류: {(error as Error).message}</p>
      )}
      {data && data.items.length === 0 && (
        <p className="text-gray-500">검토할 의뢰서가 없습니다.</p>
      )}
      {data && data.items.length > 0 && (
        <div className="flex flex-col gap-2">
          {data.items.map((item) => (
            <QueueRow key={item.order_id} item={item} />
          ))}
        </div>
      )}
    </main>
  );
}
