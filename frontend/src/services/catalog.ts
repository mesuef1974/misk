// نداءات الشبكة للكتالوج: المواد ومعايراتها وقوالب المنتجات.
import { api } from "@/api/client";
import type { ParamField } from "@/domain/params";

export interface Material {
  id: number;
  name: string;
  kind: string;
  thickness_mm: string;
  sheet_width_mm: string;
  sheet_height_mm: string;
  sheet_cost: string;
  supplier: string;
  notes: string;
}

/** الحفظ upsert على (الاسم، السماكة): إرسال الزوج نفسه يحدّث المادة ولا يكرّرها. */
export interface MaterialDraft {
  name: string;
  kind: string;
  thickness_mm: string;
  sheet_cost: string;
  supplier: string;
  notes: string;
}

export interface Calibration {
  id: number;
  material_id: number;
  operation: string;
  power_pct: number;
  speed_mm_s: string;
  passes: number;
  lines_per_cm: number | null;
  min_line_mm: string;
  measured_on: string;
  notes: string;
}

export interface CalibrationDraft {
  operation: string;
  power_pct: number;
  speed_mm_s: string;
  min_line_mm: string;
  measured_on: string;
  passes: number;
  lines_per_cm: number | null;
  notes: string;
}

export interface ProductTemplate {
  id: number;
  slug: string;
  name: string;
  generator: string;
  width_mm: string;
  height_mm: string;
  safe_margin_mm: string;
  param_schema: ParamField[];
  base_price: string;
}

/** الحفظ upsert على slug. */
export interface TemplateDraft {
  slug: string;
  name: string;
  generator: string;
  width_mm: string;
  height_mm: string;
  param_schema: ParamField[];
  base_price: string;
}

export const catalogService = {
  materials: () => api.get<Material[]>("/api/catalog/materials"),
  saveMaterial: (draft: MaterialDraft) => api.post<Material>("/api/catalog/materials", draft),
  calibrations: (materialId: number) =>
    api.get<Calibration[]>(`/api/catalog/materials/${materialId}/calibrations`),
  addCalibration: (materialId: number, draft: CalibrationDraft) =>
    api.post<Calibration>(`/api/catalog/materials/${materialId}/calibrations`, draft),
  templates: () => api.get<ProductTemplate[]>("/api/catalog/templates"),
  saveTemplate: (draft: TemplateDraft) => api.post<ProductTemplate>("/api/catalog/templates", draft),
};
