<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { errorMessage } from "@/api/client";
import { operationLabel } from "@/domain/catalog";
import { formatDate } from "@/domain/orders";
import { buildRunDraft, emptyRunForm, OUTCOME_LABELS, OUTCOMES, type RunForm } from "@/domain/production";
import type { Run, Sheet } from "@/services/production";
import { useCatalogStore } from "@/stores/catalog";
import { useProductionStore } from "@/stores/production";

const props = defineProps<{ sheet: Sheet }>();
const emit = defineEmits<{ recorded: [run: Run]; cancel: [] }>();

const catalog = useCatalogStore();
const production = useProductionStore();

// مفتاح واحد لعمر النموذج: إعادة الإرسال بعد انقطاع تعيد السجل نفسه ولا تسجّل تشغيلًا ثانيًا.
const requestId = crypto.randomUUID();
const form = reactive<RunForm>(emptyRunForm());
const errors = ref<Record<string, string>>({});
const saveError = ref("");
const calibrationsError = ref("");
const saving = ref(false);

const calibrations = computed(() => catalog.calibrations[props.sheet.material_id] ?? []);

onMounted(async () => {
  // المعايرة اختيارية في السجل: تعذّر جلبها لا يمنع تسجيل التشغيل.
  try {
    await catalog.loadCalibrations(props.sheet.material_id);
  } catch (error) {
    calibrationsError.value = errorMessage(error);
  }
});

async function submit(): Promise<void> {
  saveError.value = "";
  const result = buildRunDraft(form);
  errors.value = result.errors;
  if (!result.draft) return;
  saving.value = true;
  try {
    emit("recorded", await production.recordRun(props.sheet.id, result.draft, requestId));
  } catch (error) {
    saveError.value = errorMessage(error);
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <form class="run" novalidate @submit.prevent="submit">
    <h3>تسجيل تشغيل اللوح {{ sheet.id }}</h3>
    <div class="form-grid">
      <label class="field">
        <span>المدة: دقائق</span>
        <input v-model.number="form.minutes" type="number" min="0" step="1" inputmode="numeric" :aria-invalid="Boolean(errors.duration)" />
      </label>
      <label class="field">
        <span>ثوانٍ</span>
        <input v-model.number="form.seconds" type="number" min="0" max="59" step="1" inputmode="numeric" :aria-invalid="Boolean(errors.duration)" />
        <span v-if="errors.duration" class="error">{{ errors.duration }}</span>
      </label>
      <label class="field">
        <span>النتيجة</span>
        <select v-model="form.outcome" :aria-invalid="Boolean(errors.outcome)">
          <option v-for="outcome in OUTCOMES" :key="outcome" :value="outcome">{{ OUTCOME_LABELS[outcome] }}</option>
        </select>
        <span v-if="errors.outcome" class="error">{{ errors.outcome }}</span>
      </label>
      <label class="field">
        <span>المعايرة المستعملة (اختياري)</span>
        <select v-model="form.calibrationId">
          <option value="">بلا معايرة</option>
          <option v-for="row in calibrations" :key="row.id" :value="row.id">
            {{ operationLabel(row.operation) }} · {{ row.power_pct }}% · {{ row.speed_mm_s }} مم/ث · {{ formatDate(row.measured_on) }}
          </option>
        </select>
        <span v-if="calibrationsError" class="error">تعذّر جلب المعايرات: {{ calibrationsError }}</span>
      </label>
      <label class="field wide">
        <span>ملاحظات (اختياري)</span>
        <textarea v-model="form.notes" rows="2"></textarea>
      </label>
    </div>
    <p class="hint">النجاح يغلق اللوح نهائيًّا. الفشل يبقيه مخطَّطًا لإعادة التشغيل.</p>
    <div v-if="saveError" class="notice" role="alert">{{ saveError }}</div>
    <div class="form-actions">
      <button type="submit" class="btn primary" :disabled="saving">{{ saving ? "يسجّل…" : "حفظ التشغيل" }}</button>
      <button type="button" class="btn" :disabled="saving" @click="emit('cancel')">إلغاء</button>
    </div>
  </form>
</template>

<style scoped>
.run { margin-block-start: 16px; padding-block-start: 12px; border-block-start: 1px dashed var(--line); }
h3 { font-size: 18px; margin-block: 0 8px; }
.hint { margin-block: 12px 0; }
.notice { margin-block-start: 12px; }
</style>
