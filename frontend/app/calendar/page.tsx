"use client";

// 납기일(due_date) 기준 달력 조회 — 로그인된 기공소의 의뢰서를 월 그리드에 표시.
// 새 npm 의존성 없이 순수 Date 로 월 그리드를 구성한다.

import { useMemo, useState } from "react";
import Link from "next/link";
import { ReviewQueueItem } from "@/lib/api";
import { useLabOrders } from "@/lib/hooks";
import { RequireLab } from "@/components/RequireLab";
import type { LabSession } from "@/lib/auth";
import { StatusBadge } from "@/lib/status";

const WEEKDAYS = ["일", "월", "화", "수", "목", "금", "토"];

/** Date → 로컬 타임존 기준 YYYY-MM-DD (due_date 문자열과 비교용) */
function toKey(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

interface CalendarCell {
  date: Date;
  inMonth: boolean;
  key: string;
}

/** 해당 월을 주 단위(일~토)로 채운 6주 그리드 */
function buildGrid(year: number, month: number): CalendarCell[] {
  const first = new Date(year, month, 1);
  const start = new Date(first);
  start.setDate(1 - first.getDay()); // 그 주의 일요일로 back-fill

  const cells: CalendarCell[] = [];
  for (let i = 0; i < 42; i++) {
    const date = new Date(start);
    date.setDate(start.getDate() + i);
    cells.push({ date, inMonth: date.getMonth() === month, key: toKey(date) });
  }
  return cells;
}

function OrderLine({ item }: { item: ReviewQueueItem }) {
  return (
    <Link
      href={`/orders/${item.order_id}`}
      className="flex items-center gap-3 rounded-lg border border-gray-200 bg-white px-3 py-2 hover:bg-gray-50"
    >
      <span className="w-14 font-mono text-xs text-gray-500">#{item.order_id}</span>
      <StatusBadge status={item.status} />
      <span className="flex-1 text-xs text-gray-400">필드 {item.field_count}개</span>
    </Link>
  );
}

function Calendar({ lab }: { lab: LabSession }) {
  const today = new Date();
  const [cursor, setCursor] = useState({
    year: today.getFullYear(),
    month: today.getMonth(),
  });
  const [selected, setSelected] = useState<string | null>(null);

  const { data, isLoading, isError, error } = useLabOrders(lab.labId);

  // due_date(YYYY-MM-DD) → 의뢰서 목록 버킷
  const byDue = useMemo(() => {
    const map = new Map<string, ReviewQueueItem[]>();
    const unscheduled: ReviewQueueItem[] = [];
    for (const item of data ?? []) {
      const key = item.due_date ? item.due_date.slice(0, 10) : null;
      if (!key) {
        unscheduled.push(item);
        continue;
      }
      const list = map.get(key) ?? [];
      list.push(item);
      map.set(key, list);
    }
    return { map, unscheduled };
  }, [data]);

  const grid = useMemo(
    () => buildGrid(cursor.year, cursor.month),
    [cursor.year, cursor.month],
  );

  const todayKey = toKey(today);
  const selectedItems = selected ? (byDue.map.get(selected) ?? []) : [];

  function move(delta: number) {
    setSelected(null);
    setCursor((c) => {
      const d = new Date(c.year, c.month + delta, 1);
      return { year: d.getFullYear(), month: d.getMonth() };
    });
  }

  return (
    <main className="mx-auto max-w-3xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">납기일 달력</h1>
          <p className="mt-0.5 text-xs text-gray-500">{lab.name}</p>
        </div>
        <Link
          href="/lab"
          className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-50"
        >
          목록으로 보기
        </Link>
      </div>

      {/* 월 네비게이션 */}
      <div className="mb-4 flex items-center justify-between">
        <button
          type="button"
          onClick={() => move(-1)}
          className="rounded-lg border border-gray-200 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50"
        >
          ‹ 이전
        </button>
        <h2 className="text-lg font-semibold text-gray-900">
          {cursor.year}년 {cursor.month + 1}월
        </h2>
        <button
          type="button"
          onClick={() => move(1)}
          className="rounded-lg border border-gray-200 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50"
        >
          다음 ›
        </button>
      </div>

      {isLoading && <p className="text-gray-500">불러오는 중…</p>}
      {isError && <p className="text-red-600">오류: {(error as Error).message}</p>}

      {!isLoading && !isError && (
        <>
          {/* 요일 헤더 */}
          <div className="mb-1 grid grid-cols-7 gap-1 text-center text-xs font-medium text-gray-400">
            {WEEKDAYS.map((w) => (
              <div key={w} className="py-1">
                {w}
              </div>
            ))}
          </div>

          {/* 날짜 그리드 */}
          <div className="grid grid-cols-7 gap-1">
            {grid.map((cell) => {
              const count = byDue.map.get(cell.key)?.length ?? 0;
              const isToday = cell.key === todayKey;
              const isSelected = cell.key === selected;
              return (
                <button
                  key={cell.key}
                  type="button"
                  disabled={count === 0}
                  onClick={() => setSelected(cell.key)}
                  className={`flex aspect-square flex-col items-center justify-start rounded-lg border p-1.5 text-left transition-colors ${
                    isSelected
                      ? "border-brand-500 bg-brand-50"
                      : count > 0
                        ? "border-brand-200 bg-white hover:bg-brand-50"
                        : "border-gray-100 bg-white"
                  } ${cell.inMonth ? "" : "opacity-40"} ${
                    count === 0 ? "cursor-default" : "cursor-pointer"
                  }`}
                >
                  <span
                    className={`text-xs ${
                      isToday
                        ? "flex h-5 w-5 items-center justify-center rounded-full bg-brand-600 font-bold text-white"
                        : "text-gray-700"
                    }`}
                  >
                    {cell.date.getDate()}
                  </span>
                  {count > 0 && (
                    <span className="mt-auto inline-flex items-center justify-center rounded-full bg-brand-100 px-1.5 py-0.5 text-[10px] font-semibold text-brand-700">
                      {count}건
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          {/* 선택한 날짜의 의뢰서 */}
          {selected && (
            <section className="mt-6">
              <h3 className="mb-2 text-sm font-semibold text-gray-900">
                {selected} 납기 의뢰서 {selectedItems.length}건
              </h3>
              <div className="flex flex-col gap-2">
                {selectedItems.map((item) => (
                  <OrderLine key={item.order_id} item={item} />
                ))}
              </div>
            </section>
          )}

          {/* 납기일 미지정 */}
          {byDue.unscheduled.length > 0 && (
            <section className="mt-8 rounded-xl border border-dashed border-gray-200 p-4">
              <h3 className="mb-2 text-sm font-semibold text-gray-700">
                납기일 미지정 {byDue.unscheduled.length}건
              </h3>
              <p className="mb-3 text-xs text-gray-400">
                due_date 가 비어 있는 의뢰서 — OCR 결과에 납기일이 없으면 여기에 표시됩니다.
              </p>
              <div className="flex flex-col gap-2">
                {byDue.unscheduled.map((item) => (
                  <OrderLine key={item.order_id} item={item} />
                ))}
              </div>
            </section>
          )}
        </>
      )}
    </main>
  );
}

export default function CalendarPage() {
  return <RequireLab>{(lab) => <Calendar lab={lab} />}</RequireLab>;
}
