"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useLabAuth } from "@/lib/auth";

// 공용 상단 바 — 로고 + 기공소명 + 로그아웃. 로그인/가입 화면에서는 숨긴다.
export function AppHeader() {
  const { lab, hydrated, logout } = useLabAuth();
  const router = useRouter();
  const pathname = usePathname();

  if (pathname === "/login" || pathname === "/signup") return null;

  return (
    <header className="sticky top-0 z-10 border-b border-gray-200 bg-white/90 backdrop-blur">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
        <Link href="/" className="flex items-center gap-2">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/CrownOps_logo.png" alt="CrownOps" className="h-7 w-7" />
          <span className="text-lg font-bold tracking-tight text-gray-900">
            CrownOps
          </span>
        </Link>

        {hydrated && lab && (
          <div className="flex items-center gap-3">
            <span className="hidden text-sm text-gray-600 sm:inline">
              <span className="font-medium text-gray-900">{lab.name}</span>
              <span className="ml-1.5 text-xs text-gray-400">{lab.code}</span>
            </span>
            <button
              type="button"
              onClick={() => {
                logout();
                router.push("/login");
              }}
              className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600 transition-colors hover:bg-gray-50"
            >
              로그아웃
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
