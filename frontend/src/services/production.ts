// نداءات الشبكة للإنتاج: الألواح، وتخطيطها، وسجل التشغيل.
import { api } from "@/api/client";
import { pageQuery, type Page, type PageQuery } from "@/api/paging";

export interface Placement {
  order_item_id: number;
  order_id: number;
  customer_name: string;
  template_slug: string;
  copy_index: number;
  x_mm: string;
  y_mm: string;
  width_mm: string;
  height_mm: string;
}

export interface Sheet {
  id: number;
  material_id: number;
  width_mm: string;
  height_mm: string;
  status: string;
  placements: Placement[];
  /** سجل تشغيل اللوح، الأحدث أولًا. */
  runs: Run[];
}

export interface RunDraft {
  duration_s: number;
  outcome: string;
  calibration_id: number | null;
  notes: string;
}

export interface Run {
  id: number;
  sheet_id: number;
  outcome: string;
  duration_s: number;
  material_cost: string;
  notes: string;
  created_at: string;
}

/** مهمة تخطيط: `done` بألواحها، أو `pending` يُستطلع بمعرّفها، أو `failed` برسالة تُعرض. */
export interface PlanJob {
  /** فارغ حين خُطِّط في الطلب نفسه: لا شيء يُستطلع. */
  id: string;
  status: "pending" | "done" | "failed";
  sheets: Sheet[];
  error: string;
  /** ألواح المادة المخطَّطة التي لم تُقصّ بعد التخطيط: تميّز «لا قطع للمادة» من «قطعها على ألواح قائمة». */
  waiting: number;
}

/** ما يخرج من التخطيط: الألواح الجديدة وعدد ألواح المادة التي تنتظر القصّ. */
export interface PlanOutcome {
  sheets: Sheet[];
  waiting: number;
}

export const productionService = {
  sheets: (query?: PageQuery) => api.get<Page<Sheet>>(`/api/production/sheets${pageQuery(query)}`),
  plan: (materialId: number) => api.post<PlanJob>("/api/production/sheets/plan", { material_id: materialId }),
  planJob: (jobId: string) => api.get<PlanJob>(`/api/production/sheets/plan/${encodeURIComponent(jobId)}`),
  /** `requestId` مفتاح idempotency: إعادة الإرسال به تعيد السجل نفسه ولا تسجّل تشغيلًا ثانيًا. */
  recordRun: (sheetId: number, draft: RunDraft, requestId: string) =>
    api.post<Run>(`/api/production/sheets/${sheetId}/runs`, draft, { "X-Request-ID": requestId }),
  /** idempotent في الخادم: إتلاف لوح تالف يعيده كما هو. */
  scrap: (sheetId: number) => api.post<Sheet>(`/api/production/sheets/${sheetId}/scrap`, {}),
};
