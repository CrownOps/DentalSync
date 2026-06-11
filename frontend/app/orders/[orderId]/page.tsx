"use client";

// 화면 4. 주문 상세 — 라우팅 결과(Type A/B/C), 섹션별 필드값, 필드별 플래그, OCR 4종 데이터
// 화면 2 (OCR 결과 확인)도 겸함 — raw / corrected / confidence 동시 표시

import { useMemo, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useReviewDetail } from "@/lib/hooks";
import { FieldEnvelope } from "@/lib/api";
import {
  LAYOUT_SECTIONS,
  CRITICAL_FIELD_KEYS,
  PII_FIELD_KEYS,
  REQUIRED_FIELD_KEYS,
  ROUTING_TYPE_LABELS,
  ORDER_STATUS_LABELS,
  getFieldLabel,
  SectionDef,
} from "@/lib/layout";
import {
  ConfidenceBadge,
  CriticalBadge,
  PiiBadge,
  FieldTypeBadge,
  confidenceBorderClass,
  confidenceBgClass,
} from "@/components/ConfidenceBadge";

// ── PII 마스킹 ────────────────────────────────────────────────────────────────

function PiiValue({ value }: { value: string | null }) {
  const [revealed, setRevealed] = useState(false);
  if (!value) return <span className="text-gray-400">—</span>;
  const masked = value[0] + "***";
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="text-sm">{revealed ? value : masked}</span>
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

// ── 상태 뱃지 ──────────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const cls: Record<string, string> = {
    confirmed: "bg-green-100 text-green-800",
    auto_confirmed: "bg-teal-100 text-teal-800",
    needs_review: "bg-yellow-100 text-yellow-800",
    ocr_failed: "bg-red-100 text-red-800",
    uploaded: "bg-gray-100 text-gray-700",
    preprocessing: "bg-blue-100 text-blue-700",
    ocr_running: "bg-blue-100 text-blue-700",
    routing: "bg-blue-100 text-blue-700",
  };
  return (
    <span
      className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${cls[status] ?? "bg-gray-100 text-gray-700"}`}
    >
      {ORDER_STATUS_LABELS[status] ?? status}
    </span>
  );
}

// ── 필드 단일 카드 (화면 2 / 화면 4 공통) ─────────────────────────────────────

interface FieldCardProps {
  field: FieldEnvelope;
}

function FieldCard({ field }: FieldCardProps) {
  const isCritical = CRITICAL_FIELD_KEYS.has(field.field_key);
  const isPii = PII_FIELD_KEYS.has(field.field_key) || field.pii;
  const isRequired = REQUIRED_FIELD_KEYS.has(field.field_key);
  const isNeedsReview = field.status === "needs_review";

  const displayValue = field.value ?? field.raw;
  const hasCorrection = field.value && field.raw && field.value !== field.raw;

  const flags = field.flags as Record<string, unknown> | null;
  const isForcedHitl = !!flags?.forced_hitl;

  return (
    <div
      className={`rounded-lg border-2 p-3 transition-colors ${
        confidenceBorderClass(field.confidence)
      } ${confidenceBgClass(field.confidence)}`}
    >
      {/* 필드 헤더 */}
      <div className="mb-2 flex flex-wrap items-center gap-1.5">
        <span className="text-xs font-semibold text-gray-800">
          {getFieldLabel(field.field_key)}
        </span>
        {isRequired && (
          <span className="text-xs font-bold text-gray-400">*</span>
        )}
        {isCritical && <CriticalBadge />}
        {isPii && <PiiBadge />}
        <FieldTypeBadge fieldType={field.field_type} />
        {isForcedHitl && (
          <span className="rounded bg-orange-100 px-1.5 py-0.5 text-xs text-orange-700">
            강제검토
          </span>
        )}
        {!isNeedsReview && (
          <span className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-500">
            {field.status === "confirmed" ? "확정됨" : field.status}
          </span>
        )}
        {isNeedsReview && (
          <span className="rounded bg-yellow-100 px-1.5 py-0.5 text-xs text-yellow-700">
            검토 필요
          </span>
        )}

        {/* 신뢰도 (우측) */}
        <span className="ml-auto">
          <ConfidenceBadge score={field.confidence} />
        </span>
      </div>

      {/* 현재 값 */}
      <div className="mb-1">
        {isPii ? (
          <PiiValue value={displayValue ?? null} />
        ) : (
          <span className="text-sm font-medium text-gray-900">
            {displayValue || <span className="text-gray-400">—</span>}
          </span>
        )}
      </div>

      {/* OCR 원본 (보정됐을 때만 표시) */}
      {hasCorrection && (
        <div className="mb-1 text-xs text-gray-400 line-through">
          원본: {field.raw}
        </div>
      )}

      {/* 보정 출처 + 시각 */}
      {field.corrected_by && (
        <div className="text-xs text-gray-400">
          수정:{" "}
          {field.corrected_by === "human"
            ? "사람(HITL)"
            : field.corrected_by === "llm"
              ? "LLM"
              : "시스템 룰"}
          {field.corrected_at && (
            <> · {new Date(field.corrected_at).toLocaleString("ko-KR")}</>
          )}
        </div>
      )}

      {/* score_components 상세 (펼침) */}
      {field.score_components && Object.keys(field.score_components).length > 0 && (
        <ScoreComponents components={field.score_components} />
      )}
    </div>
  );
}

// 신뢰도 구성 요소 펼쳐보기
function ScoreComponents({ components }: { components: Record<string, number> }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-1">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="text-xs text-gray-400 underline"
      >
        {open ? "점수 구성 숨기기" : "점수 구성 보기"}
      </button>
      {open && (
        <dl className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-gray-500">
          {Object.entries(components).map(([k, v]) => (
            <div key={k} className="flex gap-1">
              <dt className="text-gray-400">{k}:</dt>
              <dd className="font-medium">{typeof v === "number" ? v.toFixed(2) : String(v)}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}

// ── 섹션 그룹 ─────────────────────────────────────────────────────────────────

interface SectionGroupProps {
  section: SectionDef | { key: string; label: string; fieldKeys: readonly string[] };
  fields: FieldEnvelope[];
}

function SectionGroup({ section, fields }: SectionGroupProps) {
  if (fields.length === 0) return null;
  return (
    <section>
      <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-gray-500">
        {section.label}
        <span className="rounded bg-gray-100 px-1.5 py-0.5 text-xs font-normal text-gray-500 normal-case tracking-normal">
          {fields.length}개 필드
        </span>
      </h2>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {fields.map((f) => (
          <FieldCard key={f.field_key} field={f} />
        ))}
      </div>
    </section>
  );
}

// ── 메인 페이지 ───────────────────────────────────────────────────────────────

export default function OrderDetailPage() {
  const params = useParams();
  const orderId = Number(params.orderId);

  const { data, isLoading, isError, error } = useReviewDetail(orderId);

  // 라우팅 타입 집합 (필드별 field_type 집합)
  const routingTypes = useMemo(() => {
    if (!data) return new Set<string>();
    return new Set(data.fields.map((f) => f.field_type));
  }, [data]);

  // 섹션별로 필드 그룹화
  const sectionedFields = useMemo(() => {
    if (!data) return [];
    const fieldMap = new Map(data.fields.map((f) => [f.field_key, f]));
    const result: Array<{
      section: { key: string; label: string; fieldKeys: readonly string[] };
      fields: FieldEnvelope[];
    }> = [];
    const usedKeys = new Set<string>();

    for (const section of LAYOUT_SECTIONS) {
      const matched = section.fieldKeys
        .map((k) => fieldMap.get(k))
        .filter((f): f is FieldEnvelope => f !== undefined);
      if (matched.length > 0) {
        result.push({ section, fields: matched });
        matched.forEach((f) => usedKeys.add(f.field_key));
      }
    }

    // 레이아웃 정의에 없는 필드는 "기타"로
    const others = data.fields.filter((f) => !usedKeys.has(f.field_key));
    if (others.length > 0) {
      result.push({
        section: { key: "other", label: "기타", fieldKeys: [] },
        fields: others,
      });
    }
    return result;
  }, [data]);

  // ── 로딩 / 에러 / 빈 상태 ──────────────────────────────────────────────────

  if (isLoading) {
    return (
      <main className="mx-auto max-w-4xl px-4 py-10">
        <p className="text-gray-500">불러오는 중…</p>
      </main>
    );
  }
  if (isError) {
    return (
      <main className="mx-auto max-w-4xl px-4 py-10">
        <p className="text-red-600">오류: {(error as Error).message}</p>
        <Link href="/" className="mt-4 block text-sm text-blue-600 hover:underline">
          홈으로 돌아가기
        </Link>
      </main>
    );
  }
  if (!data) return null;

  const isNeedsReview = data.status === "needs_review";

  return (
    <main className="mx-auto max-w-4xl px-4 py-8">
      {/* ── 헤더 ── */}
      <div className="mb-6">
        <div className="mb-1 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-xl font-bold text-gray-900">
              의뢰서 #{data.order_id}
            </h1>
            <p className="mt-0.5 text-sm text-gray-500">
              기공소 {data.lab_id}
              {data.received_at && (
                <> · 접수 {data.received_at.slice(0, 10)}</>
              )}
              {data.due_date && (
                <> · 납기 {data.due_date.slice(0, 10)}</>
              )}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={data.status} />
            {isNeedsReview && (
              <Link
                href={`/review/${data.order_id}`}
                className="rounded-lg bg-yellow-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-yellow-600"
              >
                HITL 검토
              </Link>
            )}
            <Link href="/review" className="text-xs text-blue-500 hover:underline">
              검토 큐
            </Link>
            <Link href="/" className="text-xs text-gray-400 hover:underline">
              홈
            </Link>
          </div>
        </div>

        {/* 라우팅 타입 배지 */}
        {routingTypes.size > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {[...routingTypes].map((t) => (
              <span
                key={t}
                className="rounded border border-gray-200 bg-gray-50 px-2.5 py-1 text-xs text-gray-700"
              >
                {ROUTING_TYPE_LABELS[t] ?? `Type ${t}`}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* ── 원본 이미지 (썸네일) ── */}
      {data.image_url && (
        <div className="mb-6">
          <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
            원본 의뢰서
          </h2>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={data.image_url}
            alt="의뢰서 원본 이미지"
            className="max-h-64 rounded-lg border border-gray-200 object-contain shadow-sm"
          />
        </div>
      )}

      {/* ── 필드 없음 ── */}
      {data.fields.length === 0 && (
        <div className="rounded-lg border border-dashed border-gray-300 py-12 text-center text-sm text-gray-400">
          OCR 결과 필드가 없습니다.
        </div>
      )}

      {/* ── 섹션별 필드 목록 ── */}
      <div className="flex flex-col gap-8">
        {sectionedFields.map(({ section, fields }) => (
          <SectionGroup key={section.key} section={section} fields={fields} />
        ))}
      </div>

      {/* ── 변경 이력 (Phase 1 — API 미제공, placeholder) ── */}
      <section className="mt-8">
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
          변경 이력
        </h2>
        <p className="text-sm text-gray-400">변경 이력 API는 Phase 2에서 제공됩니다.</p>
      </section>
    </main>
  );
}
