export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export interface HealthResponse {
  status: string;
}

export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch(`${API_BASE_URL}/health`);
  if (!res.ok) {
    throw new Error(`Health check 실패: HTTP ${res.status}`);
  }
  return (await res.json()) as HealthResponse;
}

// ── HITL 검토 ─────────────────────────────────────────────────────────────────

export interface ReviewQueueItem {
  order_id: number;
  lab_id: number;
  status: string;
  received_at: string | null;
  due_date: string | null;
  min_score: number | null;
  field_count: number;
}

export interface OrderFieldDetail {
  id: number;
  field_key: string;
  field_type: string;
  raw_text: string | null;
  raw_bbox: Record<string, unknown> | null;
  raw_ocr_conf: number | null;
  corrected_value: string | null;
  corrected_by: string | null;
  score: number | null;
  score_components: Record<string, number> | null;
  flags: Record<string, unknown> | null;
  status: string;
}

export interface OrderDetailResponse {
  order_id: number;
  lab_id: number;
  status: string;
  image_url: string;
  received_at: string | null;
  due_date: string | null;
  fields: OrderFieldDetail[];
}

export interface FieldUpdate {
  field_key: string;
  corrected_value: string;
}

export interface ConfirmOrderRequest {
  fields: FieldUpdate[];
  actor?: string;
}

export interface ConfirmOrderResponse {
  order_id: number;
  status: string;
  updated_fields: number;
  training_labels_inserted: number;
}

async function apiFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(
      typeof detail.detail === "string"
        ? detail.detail
        : JSON.stringify(detail.detail),
    );
  }
  return (await res.json()) as T;
}

export function fetchReviewQueue(): Promise<ReviewQueueItem[]> {
  return apiFetch<ReviewQueueItem[]>("/api/orders");
}

export function fetchOrderDetail(orderId: number): Promise<OrderDetailResponse> {
  return apiFetch<OrderDetailResponse>(`/api/orders/${orderId}`);
}

export function confirmOrder(
  orderId: number,
  body: ConfirmOrderRequest,
): Promise<ConfirmOrderResponse> {
  return apiFetch<ConfirmOrderResponse>(`/api/orders/${orderId}/confirm`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function retryOcr(orderId: number): Promise<{ order_id: number; status: string; field_count: number }> {
  return apiFetch(`/api/orders/${orderId}/retry-ocr`, { method: "POST" });
}
