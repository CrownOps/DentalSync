"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useLogin } from "@/lib/hooks";
import { useLabAuth } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const { login } = useLabAuth();
  const { mutate, isPending } = useLogin();

  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    mutate(
      { code: code.trim(), password },
      {
        onSuccess: (data) => {
          login(data);
          router.push("/");
        },
        onError: (err) => setError((err as Error).message),
      },
    );
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/CrownOps_logo.png" alt="CrownOps" className="mb-3 h-14 w-14" />
          <h1 className="text-2xl font-bold tracking-tight text-gray-900">CrownOps</h1>
          <p className="mt-1 text-sm text-gray-500">기공소 로그인</p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="flex flex-col gap-4 rounded-2xl border border-gray-200 bg-white p-6 shadow-sm"
        >
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-700">
              로그인 코드
            </label>
            <input
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="예: crownops-01"
              autoComplete="username"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-200"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-700">
              비밀번호
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-200"
            />
          </div>

          {error && (
            <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={isPending || code.trim() === "" || password === ""}
            className="mt-1 rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isPending ? "로그인 중…" : "로그인"}
          </button>
        </form>

        <p className="mt-5 text-center text-sm text-gray-500">
          아직 계정이 없으신가요?{" "}
          <Link href="/signup" className="font-medium text-brand-600 hover:underline">
            기공소 회원가입
          </Link>
        </p>
      </div>
    </main>
  );
}
