"use client";

import { useParams, useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchOrderDetail,
  confirmOrder,
  retryOcr,
  OrderFieldDetail,
  OrderDetailResponse,
} from "@/lib/api";
import { useState, useRef, useCallback } from "react";

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

// ── bbox 오버레이 ──────────────────────────────────────────────────────────────

interface BBox {
  vertices: { x: number; y: number }[];
}

function parseBbox(raw: Record<string, unknown> | null): BBox | null {
  if (!raw) return null;
  const verts = (raw as { vertices?: { x: number; y: number }[] }).vertices;
  if (!verts || verts.length < 2) return null;
  return { vertices: verts };
}

function bboxToRect(
  bbox: BBox,
  imgW: number,
  imgH: number,
  naturalW: number,
  naturalH: number,
) {
  const scaleX = imgW / naturalW;
  const scaleY = imgH / naturalH;
  const xs = bbox.vertices.map((v) => v.x * scaleX);
  const ys = bbox.vertices.map((v) => v.y * scaleY);
  return {
    left: Math.min(...xs),
    top: Math.min(...ys),
    width: Math.max(...xs) - Math.min(...xs),
    height: Math.max(...ys) - Math.min(...ys),
  };
}

// ── 이미지 + bbox 오버레이 컴포넌트 ────────────────────────────────────────────

interface ImagePanelProps {
  imageUrl: string;
  fields: OrderFieldDetail[];
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
      {imgSize && naturalSize &&
        fields.map((f) => {
          const bbox = parseBbox(f.raw_bbox);
          if (!bbox) return null;
          const rect = bboxToRect(
            bbox,
            imgSize.w,
            imgSize.h,
            naturalSize.w,
            naturalSize.h,
          );
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

// ── 필드 폼 컴포넌트 ──────────────────────────────────────────────────────────

interface FieldFormProps {
  order: OrderDetailResponse;
  activeKey: string | null;
  onFieldFocus: (key: string) => void;
  onConfirm: () => void;
}

function FieldForm({ order, activeKey, onFieldFocus, onConfirm }: FieldFormProps) {
  const qc = useQueryClient();
  const router = useRouter();
  const [values, setValues] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {};
    for (const f of order.fields) {
      init[f.field_key] = f.corrected_value ?? f.raw_text ?? "";
    }
    return init;
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitError, setSubmitError] = useState<string | null>(null);

  const { mutate, isPending } = useMutation({
    mutationFn: () =>
      confirmOrder(order.order_id, {
        fields: order.fields.map((f) => ({
          field_key: f.field_key,
          corrected_value: values[f.field_key] ?? "",
        })),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["review-queue"] });
      onConfirm();
      router.push("/review");
    },
    onError: (err: Error) => setSubmitError(err.message),
  });

  function validate(): boolean {
    const errs: Record<string, string> = {};
    for (const f of order.fields) {
      if (f.status === "needs_review" && !values[f.field_key]?.trim()) {
        errs[f.field_key] = "필수값 누락";
      }
    }
    setErrors(errs);
    return Object.keys(errs).length === 0;
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitError(null);
    if (validate()) mutate();
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3">
      {order.fields.map((f) => {
        const isEditable = f.status === "needs_review";
        const isActive = f.field_key === activeKey;
        const val = values[f.field_key] ?? "";
        return (
          <div
            key={f.field_key}
            id={`field-${f.field_key}`}
            onClick={() => onFieldFocus(f.field_key)}
            className={`rounded-lg border-2 p-3 transition-colors ${
              isActive ? "border-blue-400 bg-blue-50" : scoreColor(f.score) + " " + scoreBg(f.score)
            }`}
          >
            <div className="mb-1 flex items-center justify-between">
              <label className="text-xs font-semibold text-gray-700 uppercase tracking-wide">
                {f.field_key}
              </label>
              <div className="flex items-center gap-2 text-xs text-gray-500">
                {f.score !== null && (
                  <span>신뢰도 {Math.round(f.score * 100)}%</span>
                )}
                {!isEditable && (
                  <span className="rounded bg-gray-100 px-1.5 py-0.5 text-gray-500">
                    확정됨
                  </span>
                )}
              </div>
            </div>
            {f.raw_text && f.raw_text !== val && (
              <div className="mb-1 text-xs text-gray-400 line-through">
                원본: {f.raw_text}
              </div>
            )}
            {isEditable ? (
              <input
                type="text"
                value={val}
                onChange={(e) =>
                  setValues((prev) => ({ ...prev, [f.field_key]: e.target.value }))
                }
                onFocus={() => onFieldFocus(f.field_key)}
                className="w-full rounded border border-gray-300 px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
              />
            ) : (
              <div className="text-sm text-gray-700">{val || "—"}</div>
            )}
            {errors[f.field_key] && (
              <p className="mt-1 text-xs text-red-600">{errors[f.field_key]}</p>
            )}
          </div>
        );
      })}

      {submitError && (
        <p className="text-sm text-red-600 rounded border border-red-200 bg-red-50 px-3 py-2">
          {submitError}
        </p>
      )}

      <button
        type="submit"
        disabled={isPending}
        className="mt-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
      >
        {isPending ? "저장 중…" : "확정 저장"}
      </button>
    </form>
  );
}

// ── 메인 페이지 ───────────────────────────────────────────────────────────────

export default function ReviewDetailPage() {
  const params = useParams();
  const orderId = Number(params.orderId);
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const qc = useQueryClient();

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["order-detail", orderId],
    queryFn: () => fetchOrderDetail(orderId),
  });

  const { mutate: retry, isPending: retrying } = useMutation({
    mutationFn: () => retryOcr(orderId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["order-detail", orderId] });
      qc.invalidateQueries({ queryKey: ["review-queue"] });
    },
  });

  function handleBboxClick(key: string) {
    setActiveKey(key);
    document.getElementById(`field-${key}`)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function handleFieldFocus(key: string) {
    setActiveKey(key);
  }

  if (isLoading) {
    return <main className="p-8 text-gray-500">불러오는 중…</main>;
  }
  if (isError) {
    return <main className="p-8 text-red-600">오류: {(error as Error).message}</main>;
  }
  if (!data) return null;

  const isOcrFailed = data.status === "ocr_failed";

  return (
    <main className="mx-auto max-w-6xl px-4 py-6">
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
              OCR에 실패한 의뢰서입니다. 좌측 버튼으로 재시도할 수 있습니다.
            </p>
          ) : (
            <FieldForm
              order={data}
              activeKey={activeKey}
              onFieldFocus={handleFieldFocus}
              onConfirm={() => {}}
            />
          )}
        </div>
      </div>
    </main>
  );
}
