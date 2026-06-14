"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useSignup } from "@/lib/hooks";
import { useLabAuth } from "@/lib/auth";

export default function SignupPage() {
  const router = useRouter();
  const { login } = useLabAuth();
  const { mutate, isPending } = useSignup();

  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const codeValid = code.trim().length >= 3;
  const pwValid = password.length >= 6;
  const canSubmit = name.trim() !== "" && codeValid && pwValid;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    mutate(
      { name: name.trim(), code: code.trim(), password },
      {
        onSuccess: (data) => {
          login(data); // 가입 직후 자동 로그인
          router.push("/");
        },
        onError: (err) => setError((err as Error).message),
      },
    );
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/CrownOps_logo.png" alt="CrownOps" className="mb-3 h-14 w-14" />
          <h1 className="text-2xl font-bold tracking-tight text-gray-900">CrownOps</h1>
          <p className="mt-1 text-sm text-gray-500">기공소 회원가입</p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="flex flex-col gap-4 rounded-2xl border border-gray-200 bg-white p-6 shadow-sm"
        >
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-700">
              기공소명
            </label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="예: 크라운옵스 치과기공소"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-200"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-700">
              로그인 코드
            </label>
            <input
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="영문/숫자 3자 이상 (예: crownops-01)"
              autoComplete="username"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-200"
            />
            {code !== "" && !codeValid && (
              <p className="mt-1 text-xs text-red-500">코드는 3자 이상이어야 합니다.</p>
            )}
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-700">
              비밀번호
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="6자 이상"
              autoComplete="new-password"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-200"
            />
            {password !== "" && !pwValid && (
              <p className="mt-1 text-xs text-red-500">비밀번호는 6자 이상이어야 합니다.</p>
            )}
          </div>

          {error && (
            <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={isPending || !canSubmit}
            className="mt-1 rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isPending ? "가입 중…" : "가입하고 시작하기"}
          </button>
        </form>

        <p className="mt-5 text-center text-sm text-gray-500">
          이미 계정이 있으신가요?{" "}
          <Link href="/login" className="font-medium text-brand-600 hover:underline">
            로그인
          </Link>
        </p>
      </div>
    </main>
  );
}
