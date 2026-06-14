"use client";

// 화면 1. 의뢰서 업로드 — 파일 선택 → 업로드 → 상태 폴링 → 종료 상태 라우팅

import { useState, useCallback, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { retryOcr } from "@/lib/api";
import { useUploadOrder, useOrderStatus, POLL_STOP_STATUSES } from "@/lib/hooks";
import { RequireLab } from "@/components/RequireLab";
import type { LabSession } from "@/lib/auth";

const MAX_FILE_SIZE_MB = 10;
const ALLOWED_MIME = new Set([
  "image/jpeg",
  "image/png",
  "image/webp",
  "application/pdf",
]);

// 처리 중 상태 레이블
const PROCESSING_STATUS_LABELS: Record<string, string> = {
  uploaded: "업로드됨 — 처리 대기 중",
  preprocessing: "이미지 전처리 중…",
  ocr_running: "OCR 처리 중… (CLOVA)",
  routing: "라우팅 분석 중…",
};

function UploadForm({ lab }: { lab: LabSession }) {
  const router = useRouter();
  const qc = useQueryClient();

  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [uploadedOrderId, setUploadedOrderId] = useState<number | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // 업로드 후 상태 폴링
  const { data: statusData } = useOrderStatus(uploadedOrderId);

  // 종료 상태 도달 시 화면 라우팅 (ocr_failed는 현재 페이지에 머뭄)
  useEffect(() => {
    if (!statusData || !uploadedOrderId) return;
    const { status } = statusData;
    if (status === "needs_review") {
      router.push(`/review/${uploadedOrderId}`);
    } else if (status === "auto_confirmed" || status === "confirmed") {
      router.push(`/orders/${uploadedOrderId}`);
    }
  }, [statusData, uploadedOrderId, router]);

  // 업로드 mutation
  const { mutate: upload, isPending: uploading } = useUploadOrder();

  // OCR 재시도 mutation
  const { mutate: retry, isPending: retrying } = useMutation({
    mutationFn: () => retryOcr(uploadedOrderId!),
    onSuccess: () => {
      // 폴링 재개 — 쿼리 무효화로 refetchInterval이 다시 활성화됨
      qc.invalidateQueries({ queryKey: ["order-status", uploadedOrderId] });
    },
    onError: (err) => setSubmitError((err as Error).message),
  });

  const validateAndSetFile = useCallback((f: File) => {
    if (!ALLOWED_MIME.has(f.type)) {
      setFileError("지원하지 않는 파일 형식입니다. (허용: JPG, PNG, WEBP, PDF)");
      return false;
    }
    if (f.size > MAX_FILE_SIZE_MB * 1024 * 1024) {
      setFileError(`파일이 너무 큽니다. 최대 ${MAX_FILE_SIZE_MB}MB까지 허용됩니다.`);
      return false;
    }
    setFile(f);
    setFileError(null);
    return true;
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      const f = e.dataTransfer.files[0];
      if (f) validateAndSetFile(f);
    },
    [validateAndSetFile],
  );

  const handleFileInput = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const f = e.target.files?.[0];
      if (f) validateAndSetFile(f);
    },
    [validateAndSetFile],
  );

  const handleSubmit = () => {
    if (!file) return;
    setSubmitError(null);
    const fd = new FormData();
    fd.append("image", file);
    fd.append("lab_id", String(lab.labId));
    upload(fd, {
      onSuccess: (data) => {
        setUploadedOrderId(data.order_id);
      },
      onError: (err) => setSubmitError((err as Error).message),
    });
  };

  // 폴링 중 여부 (종료 상태가 아닌 경우)
  const isProcessing =
    uploadedOrderId !== null &&
    statusData !== undefined &&
    !POLL_STOP_STATUSES.has(statusData.status);

  const isOcrFailed = statusData?.status === "ocr_failed";

  return (
    <main className="mx-auto max-w-lg px-4 py-10">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">의뢰서 업로드</h1>
          <p className="mt-0.5 text-xs text-gray-500">{lab.name}</p>
        </div>
        <a href="/" className="text-sm text-brand-600 hover:underline">
          홈으로
        </a>
      </div>

      {uploadedOrderId === null ? (
        /* ── 업로드 폼 ── */
        <div className="flex flex-col gap-5">
          {/* 파일 드롭존 */}
          <div
            role="button"
            tabIndex={0}
            aria-label="파일 선택"
            onDrop={handleDrop}
            onDragOver={(e) => e.preventDefault()}
            onClick={() => fileInputRef.current?.click()}
            onKeyDown={(e) => e.key === "Enter" && fileInputRef.current?.click()}
            className="cursor-pointer rounded-xl border-2 border-dashed border-gray-300 p-8 text-center transition-colors hover:border-brand-400 hover:bg-brand-50 focus:outline-none focus:ring-2 focus:ring-brand-300"
          >
            {file ? (
              <div>
                <p className="text-sm font-medium text-gray-900">{file.name}</p>
                <p className="mt-1 text-xs text-gray-500">
                  {(file.size / 1024).toFixed(0)} KB ·{" "}
                  {file.type.split("/")[1]?.toUpperCase()}
                </p>
                <p className="mt-2 text-xs text-brand-500">다른 파일을 선택하려면 클릭</p>
              </div>
            ) : (
              <div className="text-gray-500">
                <svg
                  className="mx-auto mb-3 h-10 w-10 text-gray-400"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={1.5}
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5m-13.5-9L12 3m0 0 4.5 4.5M12 3v13.5"
                  />
                </svg>
                <p className="text-sm">이미지(JPG/PNG/WEBP) 또는 PDF를 드래그하거나 클릭하여 선택</p>
                <p className="mt-1 text-xs">최대 {MAX_FILE_SIZE_MB}MB</p>
              </div>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp,application/pdf"
              className="hidden"
              onChange={handleFileInput}
            />
          </div>

          {fileError && <p className="text-sm text-red-600">{fileError}</p>}

          {submitError && (
            <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
              {submitError}
            </p>
          )}

          <button
            type="button"
            disabled={!file || uploading}
            onClick={handleSubmit}
            className="rounded-lg bg-brand-600 px-4 py-3 text-sm font-medium text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {uploading ? "업로드 중…" : "업로드"}
          </button>
        </div>
      ) : (
        /* ── 업로드 후 상태 표시 ── */
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <p className="mb-1 text-xs text-gray-400">의뢰서 ID</p>
          <p className="mb-4 text-lg font-bold text-gray-900">#{uploadedOrderId}</p>

          {isProcessing && (
            <div className="flex items-center gap-3 text-brand-600">
              <svg
                className="h-5 w-5 animate-spin"
                fill="none"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8v8H4z"
                />
              </svg>
              <span className="text-sm">
                {PROCESSING_STATUS_LABELS[statusData?.status ?? ""] ??
                  `처리 중… (${statusData?.status})`}
              </span>
            </div>
          )}

          {isOcrFailed && (
            <div>
              <p className="mb-3 text-sm font-medium text-red-600">
                OCR 처리에 실패했습니다. 이미지를 확인한 후 재시도해 주세요.
              </p>
              {submitError && (
                <p className="mb-3 text-xs text-red-500">{submitError}</p>
              )}
              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={() => retry()}
                  disabled={retrying}
                  className="rounded-lg border border-red-300 bg-red-50 px-4 py-2 text-sm font-medium text-red-700 hover:bg-red-100 disabled:opacity-50"
                >
                  {retrying ? "재시도 중…" : "OCR 재시도"}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setUploadedOrderId(null);
                    setFile(null);
                    setSubmitError(null);
                  }}
                  className="rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
                >
                  새 파일 업로드
                </button>
              </div>
            </div>
          )}

          {!isProcessing && !isOcrFailed && statusData && (
            <div className="flex items-center gap-2 text-green-600">
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
              <span className="text-sm">이동 중…</span>
            </div>
          )}

          {/* 업로드 직후 statusData 아직 없을 때 */}
          {!statusData && !isOcrFailed && (
            <div className="flex items-center gap-3 text-gray-500">
              <svg className="h-5 w-5 animate-spin" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
              </svg>
              <span className="text-sm">상태 확인 중…</span>
            </div>
          )}
        </div>
      )}
    </main>
  );
}

export default function UploadPage() {
  return <RequireLab>{(lab) => <UploadForm lab={lab} />}</RequireLab>;
}
