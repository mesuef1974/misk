// نداءات الشبكة للإنتاج: الألواح، وتخطيطها، وسجل التشغيل.
import { api } from "@/api/client";

export interface Placement {
  order_item_id: number;
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
}

export const productionService = {
  sheets: () => api.get<Sheet[]>("/api/production/sheets"),
  plan: (materialId: number) => api.post<Sheet[]>("/api/production/sheets/plan", { material_id: materialId }),
  /** `requestId` مفتاح idempotency: إعادة الإرسال به تعيد السجل نفسه ولا تسجّل تشغيلًا ثانيًا. */
  recordRun: (sheetId: number, draft: RunDraft, requestId: string) =>
    api.post<Run>(`/api/production/sheets/${sheetId}/runs`, draft, { "X-Request-ID": requestId }),
};
