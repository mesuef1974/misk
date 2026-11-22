// نداءات الشبكة للطلبات. الصفحات والمخازن لا تستدعي fetch مباشرة.
import { api } from "@/api/client";
import { pageQuery, type Page, type PageQuery } from "@/api/paging";
import type { ParamValues } from "@/domain/params";

export interface OrderItem {
  id: number;
  template_slug: string;
  /** اسم القالب من الخادم: به يُسمّى بند التصميم الجاهز، وقالبه ليس في قائمة القوالب. */
  name: string;
  variant_code: string;
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
  /** ما يتاح للطاقم الآن، من الخادم. */
  next_statuses: string[];
  channel: string;
  fulfillment: string;
  delivery_fee: string;
  source: string;
  occasion_date: string | null;
  notes: string;
  /** مجموع البنود دون رسوم التوصيل. */
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
  list: (query?: PageQuery) => api.get<Page<Order>>(`/api/orders${pageQuery(query)}`),
  get: (orderId: number) => api.get<Order>(`/api/orders/${orderId}`),
  create: (draft: OrderDraft) => api.post<Order>("/api/orders", draft),
  transition: (orderId: number, toStatus: string) =>
    api.post<Order>(`/api/orders/${orderId}/transition`, { to_status: toStatus }),
};
