<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { errorMessage } from "@/api/client";
import {
  buildCalibrationDraft,
  emptyCalibrationForm,
  operationLabel,
  OPERATIONS,
  type CalibrationForm,
  type Errors,
} from "@/domain/catalog";
import { formatDate } from "@/domain/orders";
import { useCatalogStore } from "@/stores/catalog";

const props = defineProps<{ materialId: number }>();
const catalog = useCatalogStore();

const loading = ref(true);
const loadError = ref("");
const form = reactive<CalibrationForm>(emptyCalibrationForm());
const errors = ref<Errors>({});
const saveError = ref("");
const saving = ref(false);

const rows = computed(() => catalog.calibrations[props.materialId] ?? []);

async function load(): Promise<void> {
  loading.value = true;
  loadError.value = "";
  try {
    await catalog.loadCalibrations(props.materialId);
  } catch (error) {
    loadError.value = errorMessage(error);
  } finally {
    loading.value = false;
  }
}

onMounted(load);

async function submit(): Promise<void> {
  saveError.value = "";
  const result = buildCalibrationDraft(form);
  errors.value = result.errors;
  if (!result.draft) return;
  saving.value = true;
  try {
    await catalog.addCalibration(props.materialId, result.draft);
    Object.assign(form, emptyCalibrationForm());
  } catch (error) {
    saveError.value = errorMessage(error);
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <section class="calibrations">
    <h3>المعايرات</h3>

    <div v-if="loadError" class="notice" role="alert">
      {{ loadError }}
      <button type="button" class="btn retry" @click="load()">إعادة المحاولة</button>
    </div>
    <p v-else-if="loading" class="muted" role="status">يحمّل المعايرات…</p>
    <p v-else-if="rows.length === 0" class="muted">
      لا معايرة بعد. الطلب على هذه المادة لا يُؤكَّد قبل تسجيل نتيجة قصاصة اختبار.
    </p>
    <div v-else class="scroll">
      <table>
        <thead>
          <tr>
            <th>التاريخ</th>
            <th>العملية</th>
            <th>القدرة</th>
            <th>السرعة</th>
            <th>المرات</th>
            <th>خطوط/سم</th>
            <th>أصغر خط</th>
            <th>ملاحظات</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.id">
            <td>{{ formatDate(row.measured_on) }}</td>
            <td>{{ operationLabel(row.operation) }}</td>
            <td class="num">{{ row.power_pct }}%</td>
            <td class="num">{{ row.speed_mm_s }} مم/ث</td>
            <td class="num">{{ row.passes }}</td>
            <td class="num">{{ row.lines_per_cm ?? "—" }}</td>
            <td class="num">{{ row.min_line_mm }} مم</td>
            <td class="note">{{ row.notes }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <form novalidate @submit.prevent="submit">
      <h4>تسجيل معايرة</h4>
      <div class="form-grid">
        <label class="field">
          <span>العملية</span>
          <select v-model="form.operation" :aria-invalid="Boolean(errors.operation)">
            <option value="">اختر العملية</option>
            <option v-for="operation in OPERATIONS" :key="operation" :value="operation">
              {{ operationLabel(operation) }}
            </option>
          </select>
          <span v-if="errors.operation" class="error">{{ errors.operation }}</span>
        </label>
        <label class="field">
          <span>القدرة (%)</span>
          <input v-model.number="form.power" type="number" min="1" max="100" step="1" inputmode="numeric" :aria-invalid="Boolean(errors.power)" />
          <span v-if="errors.power" class="error">{{ errors.power }}</span>
        </label>
        <label class="field">
          <span>السرعة (مم/ث)</span>
          <input v-model.number="form.speed" type="number" min="0.1" step="0.1" inputmode="decimal" :aria-invalid="Boolean(errors.speed)" />
          <span v-if="errors.speed" class="error">{{ errors.speed }}</span>
        </label>
        <label class="field">
          <span>عدد المرات</span>
          <input v-model.number="form.passes" type="number" min="1" step="1" inputmode="numeric" :aria-invalid="Boolean(errors.passes)" />
          <span v-if="errors.passes" class="error">{{ errors.passes }}</span>
        </label>
        <label class="field">
          <span>خطوط/سم (اختياري)</span>
          <input v-model.number="form.linesPerCm" type="number" min="1" step="1" inputmode="numeric" :aria-invalid="Boolean(errors.linesPerCm)" />
          <span v-if="errors.linesPerCm" class="error">{{ errors.linesPerCm }}</span>
        </label>
        <label class="field">
          <span>أصغر خط مقروء (مم)</span>
          <input v-model.number="form.minLine" type="number" min="0.01" step="0.01" inputmode="decimal" :aria-invalid="Boolean(errors.minLine)" />
          <span v-if="errors.minLine" class="error">{{ errors.minLine }}</span>
        </label>
        <label class="field">
          <span>تاريخ القياس</span>
          <input v-model="form.measuredOn" type="date" :aria-invalid="Boolean(errors.measuredOn)" />
          <span v-if="errors.measuredOn" class="error">{{ errors.measuredOn }}</span>
        </label>
        <label class="field wide">
          <span>ملاحظات (اختياري)</span>
          <textarea v-model="form.notes" rows="2"></textarea>
        </label>
      </div>
      <div v-if="saveError" class="notice" role="alert">{{ saveError }}</div>
      <div class="form-actions">
        <button type="submit" class="btn primary" :disabled="saving">{{ saving ? "يحفظ…" : "حفظ المعايرة" }}</button>
      </div>
    </form>
  </section>
</template>

<style scoped>
.calibrations { margin-block-start: 16px; padding-block-start: 12px; border-block-start: 1px dashed var(--line); }
h3 { font-size: 18px; margin-block: 0 8px; }
h4 { font-size: 16px; margin-block: 16px 8px; }
.scroll { overflow-x: auto; }
table { inline-size: 100%; border-collapse: collapse; font-size: 15px; }
th, td { padding: 6px 10px; text-align: start; border-block-end: 1px solid var(--line); white-space: nowrap; }
th { color: var(--muted); font-weight: 600; }
td.note { white-space: normal; min-inline-size: 160px; overflow-wrap: anywhere; }
.notice { margin-block-start: 12px; }
.retry { margin-inline-start: 12px; }
</style>
