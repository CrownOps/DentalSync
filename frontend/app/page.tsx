"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { API_BASE_URL, fetchHealth } from "@/lib/api";

export default function Home() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
  });

  return (
    <main className="mx-auto max-w-xl px-4 py-10">
      <h1 className="mb-2 text-3xl font-bold text-gray-900">DentalSync</h1>
      <p className="mb-8 text-sm text-gray-500">치과기공소 의뢰서 OCR 파이프라인</p>

      {/* 백엔드 연결 상태 */}
      <section className="mb-8 rounded-lg border border-gray-200 px-4 py-3 text-xs text-gray-400">
        <span className="mr-2">{API_BASE_URL}/health</span>
        {isLoading && <span>확인 중…</span>}
        {isError && (
          <span className="text-red-500">연결 실패: {(error as Error).message}</span>
        )}
        {data && (
          <span className="flex items-center gap-1.5 text-green-600">
            <span className="inline-block h-2 w-2 rounded-full bg-green-500" />
            {data.status}
          </span>
        )}
      </section>

      {/* 메인 네비게이션 */}
      <div className="flex flex-col gap-3">
        <Link
          href="/upload"
          className="flex items-center justify-between rounded-xl border border-gray-200 bg-white px-5 py-4 shadow-sm transition-colors hover:border-blue-300 hover:bg-blue-50"
        >
          <div>
            <p className="text-sm font-semibold text-gray-900">의뢰서 업로드</p>
            <p className="mt-0.5 text-xs text-gray-500">이미지 업로드 → OCR → 결과 확인</p>
          </div>
          <svg className="h-5 w-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
          </svg>
        </Link>

        <Link
          href="/review"
          className="flex items-center justify-between rounded-xl border border-gray-200 bg-white px-5 py-4 shadow-sm transition-colors hover:border-yellow-300 hover:bg-yellow-50"
        >
          <div>
            <p className="text-sm font-semibold text-gray-900">HITL 검토 큐</p>
            <p className="mt-0.5 text-xs text-gray-500">검토 필요 의뢰서 목록 — 신뢰도 낮은 순</p>
          </div>
          <svg className="h-5 w-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
          </svg>
        </Link>

        <Link
          href="/lab"
          className="flex items-center justify-between rounded-xl border border-gray-200 bg-white px-5 py-4 shadow-sm transition-colors hover:border-blue-300 hover:bg-blue-50"
        >
          <div>
            <p className="text-sm font-semibold text-gray-900">기공소별 의뢰서 조회</p>
            <p className="mt-0.5 text-xs text-gray-500">기공소 ID로 OCR 스캔 의뢰서 조회 — 상태별 필터</p>
          </div>
          <svg className="h-5 w-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
          </svg>
        </Link>
      </div>
    </main>
  );
}
