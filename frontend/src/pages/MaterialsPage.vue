<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { errorMessage } from "@/api/client";
import BrandIcon from "@/components/BrandIcon.vue";
import MaterialCalibrations from "@/components/MaterialCalibrations.vue";
import {
  buildMaterialDraft,
  emptyMaterialForm,
  KIND_ICONS,
  kindLabel,
  MATERIAL_KINDS,
  materialFormFrom,
  type Errors,
  type MaterialForm,
} from "@/domain/catalog";
import { formatMoney } from "@/domain/orders";
import type { Material } from "@/services/catalog";
import { useCatalogStore } from "@/stores/catalog";

const catalog = useCatalogStore();

/** null: النموذج مغلق. "new": مادة جديدة. رقم: تعديل المادة بهذا المعرّف. */
const editing = ref<number | "new" | null>(null);
const form = reactive<MaterialForm>(emptyMaterialForm());
const errors = ref<Errors>({});
const saveError = ref("");
const saving = ref(false);
const opened = ref<number | null>(null);

onMounted(() => catalog.ensureLoaded());

function open(material?: Material): void {
  Object.assign(form, material ? materialFormFrom(material) : emptyMaterialForm());
  errors.value = {};
  saveError.value = "";
  editing.value = material ? material.id : "new";
}

function close(): void {
  editing.value = null;
}

async function submit(): Promise<void> {
  saveError.value = "";
  const result = buildMaterialDraft(form);
  errors.value = result.errors;
  if (!result.draft) return;
  saving.value = true;
  try {
    await catalog.saveMaterial(result.draft);
    close();
  } catch (error) {
    saveError.value = errorMessage(error);
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <div class="page-head">
    <h1>المواد</h1>
    <button v-if="catalog.loaded && editing === null" type="button" class="btn primary" @click="open()">مادة جديدة</button>
  </div>

  <form v-if="editing !== null" class="panel editor" novalidate @submit.prevent="submit">
    <h2>{{ editing === "new" ? "مادة جديدة" : "تعديل المادة" }}</h2>
    <div class="form-grid">
      <label class="field">
        <span>الاسم</span>
        <input v-model="form.name" type="text" maxlength="120" :disabled="editing !== 'new'" :aria-invalid="Boolean(errors.name)" />
        <span v-if="errors.name" class="error">{{ errors.name }}</span>
      </label>
      <label class="field">
        <span>السماكة (مم)</span>
        <input
          v-model.number="form.thickness"
          type="number"
          min="0.1"
          step="0.01"
          inputmode="decimal"
          :disabled="editing !== 'new'"
          :aria-invalid="Boolean(errors.thickness)"
        />
        <span v-if="errors.thickness" class="error">{{ errors.thickness }}</span>
      </label>
      <label class="field">
        <span>النوع</span>
        <select v-model="form.kind" :aria-invalid="Boolean(errors.kind)">
          <option value="">اختر النوع</option>
          <option v-for="kind in MATERIAL_KINDS" :key="kind" :value="kind">{{ kindLabel(kind) }}</option>
        </select>
        <span v-if="errors.kind" class="error">{{ errors.kind }}</span>
      </label>
      <label class="field">
        <span>كلفة اللوح (ر.ق)</span>
        <input v-model.number="form.sheetCost" type="number" min="0" step="0.01" inputmode="decimal" :aria-invalid="Boolean(errors.sheetCost)" />
        <span v-if="errors.sheetCost" class="error">{{ errors.sheetCost }}</span>
      </label>
      <label class="field">
        <span>المورّد (اختياري)</span>
        <input v-model="form.supplier" type="text" maxlength="160" :aria-invalid="Boolean(errors.supplier)" />
        <span v-if="errors.supplier" class="error">{{ errors.supplier }}</span>
      </label>
      <label class="field wide">
        <span>ملاحظات (اختياري)</span>
        <textarea v-model="form.notes" rows="2"></textarea>
      </label>
    </div>
    <p v-if="editing !== 'new'" class="hint">الاسم والسماكة مفتاح المادة ولا يتغيران؛ لسماكة أخرى أضف مادة جديدة.</p>
    <div v-if="saveError" class="notice" role="alert">{{ saveError }}</div>
    <div class="form-actions">
      <button type="submit" class="btn primary" :disabled="saving">{{ saving ? "يحفظ…" : "حفظ المادة" }}</button>
      <button type="button" class="btn" :disabled="saving" @click="close">إلغاء</button>
    </div>
  </form>

  <div v-if="catalog.loadError" class="notice" role="alert">
    {{ catalog.loadError }}
    <button type="button" class="btn retry" @click="catalog.load()">إعادة المحاولة</button>
  </div>
  <p v-else-if="!catalog.loaded" class="muted" role="status">يحمّل المواد…</p>
  <div v-else-if="catalog.materials.length === 0" class="empty">
    <div class="inner"><div class="mark" aria-hidden="true"></div><p>لا مواد بعد. ابدأ بـ«مادة جديدة».</p></div>
  </div>

  <ul v-else class="cards">
    <li v-for="material in catalog.materials" :key="material.id" class="panel material">
      <div class="row">
        <BrandIcon v-if="KIND_ICONS[material.kind]" :name="KIND_ICONS[material.kind]" />
        <div class="what">
          <strong>{{ material.name }} <span class="num">({{ material.thickness_mm }} مم)</span></strong>
          <span class="muted">
            {{ kindLabel(material.kind) }} · لوح
            <span class="num">{{ material.sheet_width_mm }} × {{ material.sheet_height_mm }} مم</span> ·
            <span class="num">{{ formatMoney(material.sheet_cost) }}</span>
            <template v-if="material.supplier"> · {{ material.supplier }}</template>
          </span>
          <span v-if="material.notes" class="notes">{{ material.notes }}</span>
        </div>
        <div class="buttons">
          <button type="button" class="btn" @click="open(material)">تعديل</button>
          <button
            type="button"
            class="btn"
            :aria-expanded="opened === material.id"
            @click="opened = opened === material.id ? null : material.id"
          >
            {{ opened === material.id ? "إخفاء المعايرات" : "المعايرات" }}
          </button>
        </div>
      </div>
      <MaterialCalibrations v-if="opened === material.id" :material-id="material.id" />
    </li>
  </ul>
</template>

<style scoped>
h2 { font-size: 20px; margin-block: 0 12px; }
.editor .notice { margin-block-start: 12px; }
.row { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px 16px; }
.what { display: flex; flex-direction: column; flex: 1 1 280px; min-inline-size: 0; line-height: 1.6; }
.what .muted { font-size: 15px; }
.notes { font-size: 15px; white-space: pre-wrap; overflow-wrap: anywhere; }
.buttons { display: flex; flex-wrap: wrap; gap: 8px; }
.retry { margin-inline-start: 12px; }
</style>
