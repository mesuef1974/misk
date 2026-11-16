// نداءات الشبكة للطلبات. الصفحات والمخازن لا تستدعي fetch مباشرة.
import { api } from "@/api/client";
import type { ParamValues } from "@/domain/params";

export interface OrderItem {
  id: number;
  template_slug: string;
  material_id: number;
  params: ParamValues;
  quantity: number;
  unit_price: string;
}

export interface Order {
  id: number;
  client_ref: string;
  customer_name: string;
  status: string;
  occasion_date: string | null;
  total: string;
  items: OrderItem[];
}

export interface OrderItemDraft {
  template_slug: string;
  material_id: number;
  params: ParamValues;
  quantity: number;
  /** null يترك السعر لسعر القالب الأساسي في الخادم. */
  unit_price: string | null;
}

export interface OrderDraft {
  /** مفتاح idempotency: إعادة الإرسال به تعيد الطلب نفسه ولا تنشئ ثانيًا. */
  client_ref: string;
  customer_name: string;
  occasion_date: string | null;
  notes: string;
  items: OrderItemDraft[];
}

export const ordersService = {
  list: () => api.get<Order[]>("/api/orders"),
  create: (draft: OrderDraft) => api.post<Order>("/api/orders", draft),
  transition: (orderId: number, toStatus: string) =>
    api.post<Order>(`/api/orders/${orderId}/transition`, { to_status: toStatus }),
};
