"use client";

// HITL 검토 TanStack Query 훅 계층 — 페이지는 이 훅에만 의존한다.

import {
  useQuery,
  useMutation,
  useQueryClient,
  UseQueryResult,
} from "@tanstack/react-query";
import {
  fetchReviewQueueV1,
  fetchReviewDetailV1,
  fetchLabOrders,
  updateFieldV1,
  confirmReviewOrderV1,
  fetchOrderStatus,
  uploadOrder,
  ReviewQueueResponseV1,
  ReviewDetailResponse,
  ReviewQueueItem,
  OrderStatusResponse,
  OrderIntakeResponse,
} from "@/lib/api";

// 폴링 중지 상태 — 파이프라인 종착 상태 도달 시 refetch 중단
export const POLL_STOP_STATUSES = new Set([
  "needs_review",
  "auto_confirmed",
  "confirmed",
  "ocr_failed",
]);

export function useReviewQueue(params?: {
  limit?: number;
  offset?: number;
}): UseQueryResult<ReviewQueueResponseV1> {
  return useQuery({
    queryKey: ["review-queue-v1", params?.limit ?? 50, params?.offset ?? 0],
    queryFn: () => fetchReviewQueueV1(params),
    refetchInterval: 5000,
  });
}

export function useLabOrders(
  labId: number | null,
  statuses?: string[],
): UseQueryResult<ReviewQueueItem[]> {
  return useQuery({
    queryKey: ["lab-orders", labId, statuses ?? []],
    queryFn: () => fetchLabOrders(labId!, statuses),
    enabled: labId !== null,
  });
}

export function useReviewDetail(
  orderId: number,
): UseQueryResult<ReviewDetailResponse> {
  return useQuery({
    queryKey: ["review-detail", orderId],
    queryFn: () => fetchReviewDetailV1(orderId),
  });
}

export function useUpdateField(orderId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ fieldKey, value }: { fieldKey: string; value: string }) =>
      updateFieldV1(orderId, fieldKey, value),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["review-detail", orderId] });
    },
  });
}

export function useConfirmOrder(orderId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => confirmReviewOrderV1(orderId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["review-queue-v1"] });
      qc.invalidateQueries({ queryKey: ["review-detail", orderId] });
    },
  });
}

export function useOrderStatus(
  orderId: number | null,
): UseQueryResult<OrderStatusResponse> {
  return useQuery({
    queryKey: ["order-status", orderId],
    queryFn: () => fetchOrderStatus(orderId!),
    enabled: orderId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status && POLL_STOP_STATUSES.has(status)) return false;
      return 2000;
    },
  });
}

/** 의뢰서 업로드 mutation — 성공 시 검토 큐 캐시 무효화 */
export function useUploadOrder() {
  const qc = useQueryClient();
  return useMutation<OrderIntakeResponse, Error, FormData>({
    mutationFn: (formData: FormData) => uploadOrder(formData),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["review-queue-v1"] });
    },
  });
}
