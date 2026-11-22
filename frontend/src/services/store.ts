// نداءات الشبكة لواجهة المتجر العامة: الكتالوج والمصمِّم، السلة والدفع، التتبّع والاستلام.
// كل نداء يحمل لغة الصفحة (`lang`) فتعود رسائل الخادم بها؛ الأخطاء `ApiError` وفي `body` رمزها وحقولها.
import { api } from "@/api/client";
import type { Locale } from "@/domain/locale";
import type { ParamField, ParamValues } from "@/domain/params";

export interface StoreMaterial {
  id: number;
  name: string;
  name_en: string;
  kind: string;
  thickness_mm: string;
}

export interface StoreTemplate {
  slug: string;
  name: string;
  name_en: string;
  description: string;
  description_en: string;
  width_mm: string;
  height_mm: string;
  base_price: string;
  allows_religious_text: boolean;
  fields: ParamField[];
}

export interface StoreTemplateDetail extends StoreTemplate {
  materials: StoreMaterial[];
}

/** تصميم جاهز في القائمة: صورة عرض وسعر يبدأ منه. ملف التصميم لا يصل المتصفح أبدًا. */
export interface StoreDesignImage {
  url: string;
  alt: string;
  alt_en: string;
}

export interface StoreDesign {
  slug: string;
  name: string;
  name_en: string;
  category: string;
  occasion: string;
  price_from: string;
  image: StoreDesignImage | null;
}

export interface StoreDesignOffer {
  material: StoreMaterial;
  price: string;
}

export interface StoreDesignVariant {
  code: string;
  sheet_width_mm: string | null;
  sheet_height_mm: string | null;
  offers: StoreDesignOffer[];
}

export interface StoreDesignDetail extends StoreDesign {
  description: string;
  description_en: string;
  assembled_width_mm: string | null;
  assembled_height_mm: string | null;
  assembled_depth_mm: string | null;
  images: StoreDesignImage[];
  variants: StoreDesignVariant[];
}

/** حدّ حقل نص عند تركيبة من حقول الاختيار (`when`): تقديري للعدّاد، والحكم في المعاينة. */
export interface FieldLimit {
  field: string;
  when: ParamValues;
  max_chars: number;
  min_text_height_mm: number;
}

export interface Preview {
  svg: string;
  sha256: string;
  width_mm: number;
  height_mm: number;
  needs_review: boolean;
  review_reasons: string[];
  text_sizes: Record<string, number>;
}

export interface CartItem {
  id: number;
  template_slug: string;
  name: string;
  name_en: string;
  /** بند تصميم جاهز: رابط صفحته ورمز نسخته؛ بند المصمِّم بلا رابط ورمزه فارغ. */
  design_slug: string | null;
  variant_code: string;
  material_id: number;
  material_name: string;
  material_name_en: string;
  params: ParamValues;
  quantity: number;
  unit_price: string;
  line_total: string;
  needs_review: boolean;
}

export interface Cart {
  status: "empty" | "draft" | "awaiting_payment";
  items: CartItem[];
  subtotal: string;
  delivery_fee: string;
  total: string;
  currency: string;
  ready_on: string | null;
  needs_review: boolean;
  payment_url: string | null;
}

export interface CartItemDraft {
  template_slug: string;
  material_id: number;
  params: ParamValues;
  quantity: number;
  /** بصمة المعاينة التي أقرّها العميل؛ الخادم يرفض الإضافة إن تغيّر الرسم بعدها. */
  sha256: string;
  acknowledged: boolean;
}

export type Fulfillment = "pickup" | "delivery";

export interface CheckoutDraft {
  customer_name: string;
  fulfillment: Fulfillment;
  occasion_date: string | null;
  notes: string;
  source: string;
  delivery_zone_id: number | null;
}

export interface CheckoutResult {
  payment_url: string;
  amount: string;
  currency: string;
  expires_at: string;
  tracking_token: string;
}

export interface DeliveryZone {
  id: number;
  name: string;
  name_en: string;
  fee: string;
}

export interface TrackStep {
  status: string;
  label: string;
  reached: boolean;
  at: string | null;
}

/** تصميم جاهز يُضاف بلا معاينة: الإقرار بالمقاس والخامة، والسعر من الخادم. */
export interface DesignItemDraft {
  design_slug: string;
  variant_code: string;
  material_id: number;
  quantity: number;
  acknowledged: boolean;
}

export interface TrackItem {
  name: string;
  name_en: string;
  variant_code: string;
  material_name: string;
  material_name_en: string;
  quantity: number;
  line_total: string;
}

export interface Tracking {
  status: string;
  status_label: string;
  fulfillment: Fulfillment | "";
  steps: TrackStep[];
  items: TrackItem[];
  subtotal: string;
  delivery_fee: string;
  total: string;
  currency: string;
  occasion_date: string | null;
  delivery_zone: { name: string; name_en: string } | null;
  pickup: { starts_at: string; ends_at: string } | null;
  can_book_pickup: boolean;
  updated_at: string;
}

export interface PickupSlots {
  slot_min: number;
  days: { day: string; slots: string[] }[];
}

const slug = (value: string) => encodeURIComponent(value);

export const storeService = {
  templates: () => api.get<StoreTemplate[]>("/api/store/templates"),
  template: (templateSlug: string, lang: Locale) =>
    api.get<StoreTemplateDetail>(`/api/store/templates/${slug(templateSlug)}?lang=${lang}`),
  limits: (templateSlug: string, materialId: number, lang: Locale) =>
    api.get<FieldLimit[]>(`/api/store/templates/${slug(templateSlug)}/limits?material_id=${materialId}&lang=${lang}`),
  preview: (templateSlug: string, materialId: number, params: ParamValues, lang: Locale) =>
    api.post<Preview>(`/api/store/templates/${slug(templateSlug)}/preview`, { material_id: materialId, params, lang }),

  designs: () => api.get<StoreDesign[]>("/api/store/designs"),
  design: (designSlug: string, lang: Locale) =>
    api.get<StoreDesignDetail>(`/api/store/designs/${slug(designSlug)}?lang=${lang}`),

  cart: () => api.get<Cart>("/api/store/cart"),
  addItem: (draft: CartItemDraft, lang: Locale) => api.post<Cart>("/api/store/cart/items", { ...draft, lang }),
  addDesignItem: (draft: DesignItemDraft, lang: Locale) =>
    api.post<Cart>("/api/store/cart/design-items", { ...draft, lang }),
  setQuantity: (itemId: number, quantity: number, lang: Locale) =>
    api.patch<Cart>(`/api/store/cart/items/${itemId}`, { quantity, lang }),
  removeItem: (itemId: number, lang: Locale) => api.del<Cart>(`/api/store/cart/items/${itemId}?lang=${lang}`),
  checkout: (draft: CheckoutDraft, lang: Locale) =>
    api.post<CheckoutResult>("/api/store/cart/checkout", { ...draft, lang }),
  zones: () => api.get<DeliveryZone[]>("/api/store/delivery-zones"),

  track: (token: string, lang: Locale) => api.get<Tracking>(`/api/store/track/${slug(token)}?lang=${lang}`),
  pickupSlots: (token: string, lang: Locale) =>
    api.get<PickupSlots>(`/api/store/track/${slug(token)}/pickup-slots?lang=${lang}`),
  bookPickup: (token: string, startsAt: string, lang: Locale) =>
    api.post<Tracking>(`/api/store/track/${slug(token)}/pickup`, { starts_at: startsAt, lang }),

  /** للطاقم ومع مزوّد الاختبار وحده: يحاكي إشعار البوابة لجلسة دفع. */
  simulatePayment: (sessionId: string, outcome: "captured" | "failed") =>
    api.post<{ ok: boolean; outcome: string }>(`/api/payments/test/sessions/${slug(sessionId)}/${outcome}`, {}),
};
