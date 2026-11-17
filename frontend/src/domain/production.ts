// الإنتاج: تسميات الحالات، وحسابات اللوح، ونموذج تسجيل التشغيل. منطق خالص يُختبر بلا واجهة.
import type { RunDraft, Sheet } from "@/services/production";

export const SHEET_STATUSES = ["planned", "done", "scrapped"] as const;
export const SHEET_STATUS_LABELS: Record<string, string> = {
  planned: "مخطَّط",
  done: "نُفِّذ",
  scrapped: "تالف",
};

export const OUTCOMES = ["ok", "failed"] as const;
export const OUTCOME_LABELS: Record<string, string> = { ok: "نجح", failed: "فشل" };

export function sheetStatusLabel(status: string): string {
  return SHEET_STATUS_LABELS[status] ?? status;
}

/** نسبة مساحة القطع من مساحة اللوح، بين 0 و1. */
export function usedFraction(sheet: Sheet): number {
  const area = Number(sheet.width_mm) * Number(sheet.height_mm);
  if (!(area > 0)) return 0;
  const used = sheet.placements.reduce(
    (sum, placement) => sum + Number(placement.width_mm) * Number(placement.height_mm),
    0,
  );
  return Math.min(1, used / area);
}

export function formatDuration(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  if (minutes === 0) return `${rest} ث`;
  return rest === 0 ? `${minutes} د` : `${minutes} د ${rest} ث`;
}

/** قطع اللوح مجموعةً بحسب بند الطلب، بترتيب أول ظهور. `number` رقم المجموعة المرسوم على القطعة. */
export interface PieceGroup {
  number: number;
  orderItemId: number;
  orderId: number;
  customerName: string;
  templateSlug: string;
  copies: number;
}

export function groupPlacements(sheet: Sheet): PieceGroup[] {
  const groups = new Map<number, PieceGroup>();
  for (const placement of sheet.placements) {
    const group = groups.get(placement.order_item_id);
    if (group) group.copies += 1;
    else {
      groups.set(placement.order_item_id, {
        number: groups.size + 1,
        orderItemId: placement.order_item_id,
        orderId: placement.order_id,
        customerName: placement.customer_name,
        templateSlug: placement.template_slug,
        copies: 1,
      });
    }
  }
  return [...groups.values()];
}

export interface RunForm {
  minutes: number | "";
  seconds: number | "";
  outcome: string;
  calibrationId: number | "";
  notes: string;
}

export function emptyRunForm(): RunForm {
  return { minutes: "", seconds: "", outcome: "ok", calibrationId: "", notes: "" };
}

export function buildRunDraft(form: RunForm): { draft: RunDraft | null; errors: Record<string, string> } {
  const errors: Record<string, string> = {};
  const minutes = form.minutes === "" ? 0 : form.minutes;
  const seconds = form.seconds === "" ? 0 : form.seconds;
  const whole = (value: number, max: number) => Number.isInteger(value) && value >= 0 && value <= max;
  if (!whole(minutes, 6000) || !whole(seconds, 59)) errors.duration = "دقائق صحيحة، وثوانٍ بين 0 و59";
  else if (minutes * 60 + seconds < 1) errors.duration = "مدة التشغيل مطلوبة";
  if (!(OUTCOMES as readonly string[]).includes(form.outcome)) errors.outcome = "اختر النتيجة";
  if (Object.keys(errors).length > 0) return { draft: null, errors };
  return {
    draft: {
      duration_s: minutes * 60 + seconds,
      outcome: form.outcome,
      calibration_id: form.calibrationId === "" ? null : form.calibrationId,
      notes: form.notes.trim(),
    },
    errors,
  };
}
