// صفحات القوائم: الخادم يعيد `limit` صفًّا في الطلب الواحد (50 افتراضًا) لا الجدول كله.

export interface Page<T> {
  items: T[];
  /** كل ما يطابق التصفية في الخادم، لا طول هذه الصفحة. */
  count: number;
  /** عدد الصفوف لكل حالة في الجدول كله. */
  counts: Record<string, number>;
}

export interface PageQuery {
  status?: string;
  offset?: number;
}

export function pageQuery({ status, offset }: PageQuery = {}): string {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (offset) params.set("offset", String(offset));
  const query = params.toString();
  return query ? `?${query}` : "";
}

/** يضيف صفحة تالية إلى ما حُمّل، بلا تكرار صف دخل القائمة بينهما (طلب أُنشئ فأزاح الصفحات). */
export function appendPage<T extends { id: number }>(loaded: T[], next: T[]): T[] {
  const seen = new Set(loaded.map((row) => row.id));
  return [...loaded, ...next.filter((row) => !seen.has(row.id))];
}
