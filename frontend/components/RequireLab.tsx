"use client";

import { useEffect, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { useLabAuth, type LabSession } from "@/lib/auth";

/**
 * 로그인된 기공소가 있을 때만 children(렌더 함수)을 그린다.
 * 미로그인 상태(hydrate 완료 후)면 /login 으로 리다이렉트한다.
 */
export function RequireLab({
  children,
}: {
  children: (lab: LabSession) => ReactNode;
}) {
  const { lab, hydrated } = useLabAuth();
  const router = useRouter();

  useEffect(() => {
    if (hydrated && !lab) router.replace("/login");
  }, [hydrated, lab, router]);

  if (!hydrated) {
    return (
      <main className="mx-auto max-w-3xl px-4 py-16 text-center text-sm text-gray-400">
        불러오는 중…
      </main>
    );
  }
  if (!lab) {
    return (
      <main className="mx-auto max-w-3xl px-4 py-16 text-center text-sm text-gray-500">
        로그인이 필요합니다. 로그인 화면으로 이동합니다…
      </main>
    );
  }
  return <>{children(lab)}</>;
}
