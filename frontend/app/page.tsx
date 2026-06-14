"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { API_BASE_URL, fetchHealth } from "@/lib/api";
import { RequireLab } from "@/components/RequireLab";
import type { LabSession } from "@/lib/auth";

interface NavCard {
  href: string;
  title: string;
  desc: string;
  icon: ReactNode;
}

const NAV_CARDS: NavCard[] = [
  {
    href: "/upload",
    title: "의뢰서 업로드",
    desc: "이미지 업로드 → OCR → 결과 확인",
    icon: (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5m-13.5-9L12 3m0 0 4.5 4.5M12 3v13.5"
      />
    ),
  },
  {
    href: "/calendar",
    title: "납기일 달력",
    desc: "납기일 기준으로 의뢰서를 달력에서 확인",
    icon: (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 0 1 2.25-2.25h13.5A2.25 2.25 0 0 1 21 7.5v11.25m-18 0A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75m-18 0v-7.5A2.25 2.25 0 0 1 5.25 9h13.5A2.25 2.25 0 0 1 21 11.25v7.5"
      />
    ),
  },
  {
    href: "/lab",
    title: "의뢰서 목록 조회",
    desc: "상태별 필터로 의뢰서 전체 조회",
    icon: (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M3.75 5.25h16.5m-16.5 6h16.5m-16.5 6h16.5"
      />
    ),
  },
  {
    href: "/review",
    title: "HITL 검토 큐",
    desc: "검토 필요 의뢰서 — 신뢰도 낮은 순",
    icon: (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"
      />
    ),
  },
];

function HomeContent({ lab }: { lab: LabSession }) {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
  });

  return (
    <main className="mx-auto max-w-3xl px-4 py-8">
      {/* 브랜드 히어로 */}
      <section className="mb-8 overflow-hidden rounded-2xl bg-brand-gradient p-6 text-white shadow-sm">
        <div className="flex items-center gap-4">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-white/20 backdrop-blur">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/CrownOps_logo.png" alt="CrownOps" className="h-10 w-10" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">CrownOps</h1>
            <p className="text-sm text-white/90">치과기공소 의뢰서 OCR 파이프라인</p>
          </div>
        </div>
        <p className="mt-4 text-sm text-white/90">
          <span className="font-semibold">{lab.name}</span>
          <span className="ml-2 text-white/70">({lab.code})</span> 으로 로그인됨
        </p>
      </section>

      {/* 백엔드 연결 상태 */}
      <section className="mb-6 flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-4 py-2.5 text-xs text-gray-400">
        <span className="mr-1">{API_BASE_URL}/health</span>
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
      <div className="grid gap-3 sm:grid-cols-2">
        {NAV_CARDS.map((card) => (
          <Link
            key={card.href}
            href={card.href}
            className="group flex items-start gap-4 rounded-xl border border-gray-200 bg-white px-5 py-4 shadow-sm transition-all hover:-translate-y-0.5 hover:border-brand-300 hover:shadow-md"
          >
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-600 transition-colors group-hover:bg-brand-100">
              <svg
                className="h-5 w-5"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={1.8}
                aria-hidden="true"
              >
                {card.icon}
              </svg>
            </span>
            <div>
              <p className="text-sm font-semibold text-gray-900">{card.title}</p>
              <p className="mt-0.5 text-xs text-gray-500">{card.desc}</p>
            </div>
          </Link>
        ))}
      </div>
    </main>
  );
}

export default function Home() {
  return <RequireLab>{(lab) => <HomeContent lab={lab} />}</RequireLab>;
}
