"use client";

import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchReviewQueue, retryOcr, ReviewQueueItem } from "@/lib/api";

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

function RetryButton({ orderId }: { orderId: number }) {
  const qc = useQueryClient();
  const { mutate, isPending } = useMutation({
    mutationFn: () => retryOcr(orderId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["review-queue"] }),
  });
  return (
    <button
      onClick={(e) => {
        e.preventDefault();
        mutate();
      }}
      disabled={isPending}
      className="rounded border border-gray-300 px-2 py-0.5 text-xs hover:bg-gray-50 disabled:opacity-50"
    >
      {isPending ? "재시도 중…" : "OCR 재시도"}
    </button>
  );
}

function QueueRow({ item }: { item: ReviewQueueItem }) {
  const isOcrFailed = item.status === "ocr_failed";
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
      <span className="w-20 text-xs text-gray-500">
        필드 {item.field_count}개
      </span>
      <ScoreBadge score={item.min_score} />
      {isOcrFailed ? (
        <span className="rounded bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700">
          OCR 실패
        </span>
      ) : (
        <span className="rounded bg-yellow-100 px-2 py-0.5 text-xs font-medium text-yellow-700">
          검토 필요
        </span>
      )}
      {isOcrFailed && <RetryButton orderId={item.order_id} />}
    </Link>
  );
}

export default function ReviewQueuePage() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["review-queue"],
    queryFn: fetchReviewQueue,
    refetchInterval: 5000,
  });

  return (
    <main className="mx-auto max-w-3xl px-4 py-8">
      <h1 className="mb-6 text-2xl font-bold text-gray-900">검토 큐</h1>

      {isLoading && <p className="text-gray-500">불러오는 중…</p>}
      {isError && (
        <p className="text-red-600">오류: {(error as Error).message}</p>
      )}
      {data && data.length === 0 && (
        <p className="text-gray-500">검토할 의뢰서가 없습니다.</p>
      )}
      {data && data.length > 0 && (
        <div className="flex flex-col gap-2">
          {data.map((item) => (
            <QueueRow key={item.order_id} item={item} />
          ))}
        </div>
      )}
    </main>
  );
}
