"use client";

import { useParams, useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  updateFieldV1,
  confirmReviewOrderV1,
  retryOcr,
  FieldEnvelope,
  ReviewDetailResponse,
} from "@/lib/api";
import { parseBbox, bboxToRect } from "@/lib/bbox";
import {
  POLL_STOP_STATUSES,
  useReviewDetail,
  useOrderStatus,
} from "@/lib/hooks";
import { useState, useRef, useCallback, useEffect } from "react";

// ── 신뢰도 색상 ────────────────────────────────────────────────────────────────

function scoreColor(score: number | null): string {
  if (score === null) return "border-gray-300";
  if (score >= 0.9) return "border-green-400";
  if (score >= 0.6) return "border-yellow-400";
  return "border-red-400";
}

function scoreBg(score: number | null): string {
  if (score === null) return "";
  if (score >= 0.9) return "bg-green-50";
  if (score >= 0.6) return "bg-yellow-50";
  return "bg-red-50";
}

// ── 이미지 + bbox 오버레이 컴포넌트 ────────────────────────────────────────────

interface ImagePanelProps {
  imageUrl: string;
  fields: FieldEnvelope[];
  activeKey: string | null;
  onBboxClick: (key: string) => void;
}

function ImagePanel({ imageUrl, fields, activeKey, onBboxClick }: ImagePanelProps) {
  const imgRef = useRef<HTMLImageElement>(null);
  const [imgSize, setImgSize] = useState<{ w: number; h: number } | null>(null);
  const [naturalSize, setNaturalSize] = useState<{ w: number; h: number } | null>(null);

  const onLoad = useCallback(() => {
    const el = imgRef.current;
    if (!el) return;
    setImgSize({ w: el.clientWidth, h: el.clientHeight });
    setNaturalSize({ w: el.naturalWidth, h: el.naturalHeight });
  }, []);

  return (
    <div className="relative inline-block w-full">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        ref={imgRef}
        src={imageUrl}
        alt="의뢰서 원본"
        className="w-full rounded border border-gray-200"
        onLoad={onLoad}
      />
      {imgSize &&
        naturalSize &&
        fields.map((f) => {
          const bbox = parseBbox(f.bbox);
          if (!bbox) return null;
          const rect = bboxToRect(bbox, imgSize.w, imgSize.h, naturalSize.w, naturalSize.h);
          const isActive = f.field_key === activeKey;
          return (
            <div
              key={f.field_key}
              onClick={() => onBboxClick(f.field_key)}
              className="absolute cursor-pointer rounded"
              style={{
                left: rect.left,
                top: rect.top,
                width: rect.width,
                height: rect.height,
                border: isActive
                  ? "2px solid #3b82f6"
                  : "1.5px solid rgba(251,191,36,0.7)",
                background: isActive
                  ? "rgba(59,130,246,0.12)"
                  : "rgba(251,191,36,0.08)",
              }}
            />
          );
        })}
    </div>
  );
}

// ── PII 마스킹 ────────────────────────────────────────────────────────────────

function PiiValue({ value }: { value: string | null }) {
  const [revealed, setRevealed] = useState(false);
  const display = revealed ? value : value ? value[0] + "***" : "—";
  return (
    <span className="inline-flex items-center gap-1">
      <span>{display}</span>
      <button
        type="button"
        onClick={() => setRevealed((v) => !v)}
        className="text-xs text-blue-500 underline"
      >
        {revealed ? "숨기기" : "표시"}
      </button>
    </span>
  );
}

// ── 필드 폼 컴포넌트 ──────────────────────────────────────────────────────────

interface FieldFormProps {
  order: ReviewDetailResponse;
  activeKey: string | null;
  onFieldFocus: (key: string) => void;
}

function FieldForm({ order, activeKey, onFieldFocus }: FieldFormProps) {
  const qc = useQueryClient();
  const router = useRouter();
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  // 로컬 필드 상태 (optimistic update용)
  const [localFields, setLocalFields] = useState<FieldEnvelope[]>(order.fields);

  // 서버 데이터가 갱신되면 로컬 상태 동기화
  useEffect(() => {
    setLocalFields(order.fields);
  }, [order.fields]);

  const pendingFields = localFields.filter((f) => f.status === "needs_review");
  const allConfirmed = pendingFields.length === 0;

  // 인라인 필드 수정
  const { mutate: updateField } = useMutation({
    mutationFn: ({
      fieldKey,
      value,
    }: {
      fieldKey: string;
      value: string;
    }) => updateFieldV1(order.order_id, fieldKey, value),
    onMutate: ({ fieldKey, value }) => {
      // Optimistic update
      setLocalFields((prev) =>
        prev.map((f) =>
          f.field_key === fieldKey ? { ...f, value, status: "confirmed" } : f,
        ),
      );
      setFieldErrors((prev) => {
        const next = { ...prev };
        delete next[fieldKey];
        return next;
      });
    },
    onError: (err, { fieldKey }) => {
      // 롤백
      setLocalFields(order.fields);
      const msg = (err as Error).message;
      try {
        const parsed = JSON.parse(msg);
        setFieldErrors((prev) => ({
          ...prev,
          [fieldKey]: parsed?.error?.message ?? msg,
        }));
      } catch {
        setFieldErrors((prev) => ({ ...prev, [fieldKey]: msg }));
      }
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["review-detail", order.order_id] });
    },
  });

  // 확정
  const { mutate: confirmOrder, isPending: confirming } = useMutation({
    mutationFn: () => confirmReviewOrderV1(order.order_id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["review-queue-v1"] });
      router.push("/review");
    },
    onError: (err) => {
      const msg = (err as Error).message;
      try {
        const parsed = JSON.parse(msg);
        const violations: string[] = parsed?.error?.details ?? [];
        setSubmitError(parsed?.error?.message ?? msg);
        // 위반 필드로 스크롤
        if (violations.length > 0) {
          document.getElementById(`field-${violations[0]}`)?.scrollIntoView({
            behavior: "smooth",
            block: "center",
          });
        }
      } catch {
        setSubmitError(msg);
      }
    },
  });

  return (
    <div className="flex flex-col gap-3">
      {localFields.map((f) => {
        // 의뢰서 확정 전에는 확정된 필드도 재수정 가능 (PII 는 마스킹 유지를 위해 needs_review 일 때만)
        const isEditable =
          f.status === "needs_review" ||
          (order.status === "needs_review" && !f.pii);
        const isActive = f.field_key === activeKey;
        const currentVal = f.value ?? "";
        const fieldError = fieldErrors[f.field_key];

        return (
          <div
            key={f.field_key}
            id={`field-${f.field_key}`}
            onClick={() => onFieldFocus(f.field_key)}
            className={`rounded-lg border-2 p-3 transition-colors ${
              isActive
                ? "border-blue-400 bg-blue-50"
                : scoreColor(f.confidence) + " " + scoreBg(f.confidence)
            }`}
          >
            <div className="mb-1 flex items-center justify-between">
              <label className="text-xs font-semibold uppercase tracking-wide text-gray-700">
                {f.field_key}
                {f.pii && (
                  <span className="ml-1 rounded bg-purple-100 px-1 py-0.5 text-xs font-normal text-purple-700">
                    PII
                  </span>
                )}
              </label>
              <div className="flex items-center gap-2 text-xs text-gray-500">
                {f.confidence !== null && (
                  <span>신뢰도 {Math.round(f.confidence * 100)}%</span>
                )}
                {!!(f.flags as Record<string, unknown> | null)?.forced_hitl && (
                  <span className="rounded bg-orange-100 px-1.5 py-0.5 text-orange-700">
                    강제검토
                  </span>
                )}
                {f.status !== "needs_review" && (
                  <span className="rounded bg-gray-100 px-1.5 py-0.5 text-gray-500">
                    확정됨
                  </span>
                )}
              </div>
            </div>

            {f.raw && f.raw !== currentVal && (
              <div className="mb-1 text-xs text-gray-400 line-through">
                원본: {f.raw}
              </div>
            )}

            {isEditable ? (
              <input
                type="text"
                defaultValue={currentVal}
                onFocus={() => onFieldFocus(f.field_key)}
                onBlur={(e) => {
                  const newVal = e.currentTarget.value;
                  if (newVal !== currentVal) {
                    updateField({ fieldKey: f.field_key, value: newVal });
                  }
                }}
                className="w-full rounded border border-gray-300 px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
              />
            ) : f.pii ? (
              <PiiValue value={currentVal || null} />
            ) : (
              <div className="text-sm text-gray-700">{currentVal || "—"}</div>
            )}

            {fieldError && (
              <p className="mt-1 text-xs text-red-600">{fieldError}</p>
            )}
          </div>
        );
      })}

      {submitError && (
        <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
          {submitError}
        </p>
      )}

      <button
        type="button"
        disabled={!allConfirmed || confirming}
        onClick={() => {
          setSubmitError(null);
          confirmOrder();
        }}
        className="mt-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {confirming
          ? "저장 중…"
          : allConfirmed
            ? "확정 저장"
            : `확정 저장 (미확정 ${pendingFields.length}개)`}
      </button>
    </div>
  );
}

// ── 상태 폴링 배너 ────────────────────────────────────────────────────────────

function StatusPollingBanner({ orderId }: { orderId: number }) {
  const qc = useQueryClient();
  const { data } = useOrderStatus(orderId);

  useEffect(() => {
    if (data?.status && POLL_STOP_STATUSES.has(data.status)) {
      qc.invalidateQueries({ queryKey: ["review-detail", orderId] });
    }
  }, [data?.status, orderId, qc]);

  if (!data || POLL_STOP_STATUSES.has(data.status)) return null;

  return (
    <div className="mb-4 rounded-lg border border-blue-200 bg-blue-50 px-4 py-2 text-sm text-blue-700">
      처리 중… (상태: {data.status})
    </div>
  );
}

// ── 메인 페이지 ───────────────────────────────────────────────────────────────

export default function ReviewDetailPage() {
  const params = useParams();
  const orderId = Number(params.orderId);
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const qc = useQueryClient();

  const { data, isLoading, isError, error } = useReviewDetail(orderId);

  const { mutate: retry, isPending: retrying } = useMutation({
    mutationFn: () => retryOcr(orderId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["review-detail", orderId] });
      qc.invalidateQueries({ queryKey: ["review-queue-v1"] });
    },
  });

  function handleBboxClick(key: string) {
    setActiveKey(key);
    document
      .getElementById(`field-${key}`)
      ?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  if (isLoading) {
    return <main className="p-8 text-gray-500">불러오는 중…</main>;
  }
  if (isError) {
    return (
      <main className="p-8 text-red-600">오류: {(error as Error).message}</main>
    );
  }
  if (!data) return null;

  const isOcrFailed = data.status === "ocr_failed";

  return (
    <main className="mx-auto max-w-6xl px-4 py-6">
      <StatusPollingBanner orderId={orderId} />

      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900">
            의뢰서 #{data.order_id}
          </h1>
          <p className="text-sm text-gray-500">
            기공소 {data.lab_id} · 상태:{" "}
            <span className="font-medium">{data.status}</span>
          </p>
        </div>
        {isOcrFailed && (
          <button
            onClick={() => retry()}
            disabled={retrying}
            className="rounded-lg border border-red-300 bg-red-50 px-3 py-1.5 text-sm text-red-700 hover:bg-red-100 disabled:opacity-50"
          >
            {retrying ? "재시도 중…" : "OCR 재시도"}
          </button>
        )}
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* 좌측: 원본 이미지 + bbox 오버레이 */}
        <div className="overflow-auto rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
          <ImagePanel
            imageUrl={data.image_url}
            fields={data.fields}
            activeKey={activeKey}
            onBboxClick={handleBboxClick}
          />
        </div>

        {/* 우측: 필드 폼 */}
        <div className="overflow-y-auto rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
          {isOcrFailed ? (
            <p className="text-sm text-gray-500">
              OCR에 실패한 의뢰서입니다. 상단 버튼으로 재시도할 수 있습니다.
            </p>
          ) : (
            <FieldForm
              order={data}
              activeKey={activeKey}
              onFieldFocus={setActiveKey}
            />
          )}
        </div>
      </div>
    </main>
  );
}
