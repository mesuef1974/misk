// نداءات الشبكة للكتالوج: ما تحتاجه واجهة الطلبات من مواد وقوالب.
import { api } from "@/api/client";
import type { ParamField } from "@/domain/params";

export interface Material {
  id: number;
  name: string;
  kind: string;
  thickness_mm: string;
}

export interface ProductTemplate {
  id: number;
  slug: string;
  name: string;
  param_schema: ParamField[];
  base_price: string;
}

export const catalogService = {
  materials: () => api.get<Material[]>("/api/catalog/materials"),
  templates: () => api.get<ProductTemplate[]>("/api/catalog/templates"),
};
