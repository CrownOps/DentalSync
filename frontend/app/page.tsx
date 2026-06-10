"use client";

import { useQuery } from "@tanstack/react-query";

import { API_BASE_URL, fetchHealth } from "@/lib/api";

export default function Home() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
  });

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 p-8">
      <h1 className="text-3xl font-bold">DentalSync</h1>
      <p className="text-sm text-gray-500">개발 스모크 — backend /health 연동 확인</p>

      <section className="w-full max-w-md rounded-lg border border-gray-200 p-6 shadow-sm">
        <div className="mb-2 text-xs text-gray-400">{API_BASE_URL}/health</div>
        {isLoading && <p className="text-gray-500">확인 중…</p>}
        {isError && (
          <p className="font-medium text-red-600">
            연결 실패: {(error as Error).message}
          </p>
        )}
        {data && (
          <p className="flex items-center gap-2 font-medium text-green-600">
            <span className="inline-block h-2.5 w-2.5 rounded-full bg-green-500" />
            backend status: {data.status}
          </p>
        )}
      </section>
    </main>
  );
}
