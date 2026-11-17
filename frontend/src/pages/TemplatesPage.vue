<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { errorMessage } from "@/api/client";
import BrandIcon from "@/components/BrandIcon.vue";
import {
  buildTemplateDraft,
  describeField,
  emptyTemplateForm,
  FIELD_TYPE_LABELS,
  FIELD_TYPES,
  newSchemaField,
  templateFormFrom,
  templateIcon,
  type Errors,
  type TemplateForm,
} from "@/domain/catalog";
import { formatMoney } from "@/domain/orders";
import type { ProductTemplate } from "@/services/catalog";
import { useCatalogStore } from "@/stores/catalog";

const catalog = useCatalogStore();

/** القالب قبل التعديل؛ null لقالب جديد. `editing` يفتح النموذج. */
const original = ref<ProductTemplate | null>(null);
const editing = ref(false);
const form = reactive<TemplateForm>(emptyTemplateForm());
const errors = ref<Errors>({});
const saveError = ref("");
const saving = ref(false);
let nextKey = 1;

onMounted(() => catalog.ensureLoaded());

function open(template?: ProductTemplate): void {
  Object.assign(form, template ? templateFormFrom(template) : emptyTemplateForm());
  nextKey = form.fields.length + 1;
  original.value = template ?? null;
  errors.value = {};
  saveError.value = "";
  editing.value = true;
}

function close(): void {
  editing.value = false;
}

function addField(): void {
  form.fields.push(newSchemaField(nextKey++));
}

async function submit(): Promise<void> {
  saveError.value = "";
  const result = buildTemplateDraft(form, original.value ?? undefined);
  errors.value = result.errors;
  if (!result.draft) {
    saveError.value = "صحّح الحقول المعلَّمة ثم أعد الحفظ";
    return;
  }
  saving.value = true;
  try {
    await catalog.saveTemplate(result.draft);
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
    <h1>القوالب</h1>
    <button v-if="catalog.loaded && !editing" type="button" class="btn primary" @click="open()">قالب جديد</button>
  </div>

  <form v-if="editing" class="panel editor" novalidate @submit.prevent="submit">
    <h2>{{ original ? "تعديل القالب" : "قالب جديد" }}</h2>
    <div class="form-grid">
      <label class="field">
        <span>المعرّف (slug)</span>
        <input v-model="form.slug" type="text" maxlength="64" dir="ltr" :disabled="original !== null" :aria-invalid="Boolean(errors.slug)" />
        <span v-if="errors.slug" class="error">{{ errors.slug }}</span>
      </label>
      <label class="field">
        <span>الاسم</span>
        <input v-model="form.name" type="text" maxlength="120" :aria-invalid="Boolean(errors.name)" />
        <span v-if="errors.name" class="error">{{ errors.name }}</span>
      </label>
      <label class="field">
        <span>مفتاح المولّد</span>
        <input v-model="form.generator" type="text" maxlength="64" dir="ltr" :aria-invalid="Boolean(errors.generator)" />
        <span v-if="errors.generator" class="error">{{ errors.generator }}</span>
      </label>
      <label class="field">
        <span>العرض (مم)</span>
        <input v-model.number="form.width" type="number" min="1" step="0.1" inputmode="decimal" :aria-invalid="Boolean(errors.width)" />
        <span v-if="errors.width" class="error">{{ errors.width }}</span>
      </label>
      <label class="field">
        <span>الارتفاع (مم)</span>
        <input v-model.number="form.height" type="number" min="1" step="0.1" inputmode="decimal" :aria-invalid="Boolean(errors.height)" />
        <span v-if="errors.height" class="error">{{ errors.height }}</span>
      </label>
      <label class="field">
        <span>السعر الأساسي (ر.ق)</span>
        <input v-model.number="form.basePrice" type="number" min="0" step="0.01" inputmode="decimal" :aria-invalid="Boolean(errors.basePrice)" />
        <span v-if="errors.basePrice" class="error">{{ errors.basePrice }}</span>
      </label>
    </div>

    <h3>حقول الطلب</h3>
    <p v-if="form.fields.length === 0" class="hint">لا حقول: القالب يُطلب بلا معاملات.</p>
    <fieldset v-for="(field, index) in form.fields" :key="field.key" class="schema-field">
      <legend>الحقل {{ index + 1 }}</legend>
      <div class="form-grid">
        <label class="field">
          <span>الاسم البرمجي</span>
          <input v-model="field.name" type="text" dir="ltr" :aria-invalid="Boolean(errors[`field:${field.key}`])" />
        </label>
        <label class="field">
          <span>التسمية الظاهرة (اختياري)</span>
          <input v-model="field.label" type="text" />
        </label>
        <label class="field">
          <span>النوع</span>
          <select v-model="field.type">
            <option v-for="type in FIELD_TYPES" :key="type" :value="type">{{ FIELD_TYPE_LABELS[type] }}</option>
          </select>
        </label>
        <label v-if="field.type === 'text'" class="field">
          <span>أقصى طول (اختياري)</span>
          <input v-model.number="field.maxLength" type="number" min="1" step="1" inputmode="numeric" />
        </label>
        <template v-if="field.type === 'int'">
          <label class="field">
            <span>الحد الأدنى (اختياري)</span>
            <input v-model.number="field.min" type="number" step="1" inputmode="numeric" />
          </label>
          <label class="field">
            <span>الحد الأقصى (اختياري)</span>
            <input v-model.number="field.max" type="number" step="1" inputmode="numeric" />
          </label>
        </template>
        <label v-if="field.type === 'choice'" class="field wide">
          <span>الخيارات (خيار في كل سطر)</span>
          <textarea v-model="field.choices" rows="3"></textarea>
        </label>
        <label v-if="field.type !== 'bool'" class="check">
          <input v-model="field.required" type="checkbox" />
          <span>مطلوب</span>
        </label>
      </div>
      <span v-if="errors[`field:${field.key}`]" class="error" role="alert">{{ errors[`field:${field.key}`] }}</span>
      <button type="button" class="btn danger remove" @click="form.fields.splice(index, 1)">حذف الحقل</button>
    </fieldset>
    <button type="button" class="btn" @click="addField">إضافة حقل</button>

    <p v-if="original" class="hint">
      تغيير الحقول لا يعدّل الطلبات المحفوظة؛ حذف حقل أو تضييق حدوده يسري على الطلبات الجديدة فقط.
    </p>
    <div v-if="saveError" class="notice" role="alert">{{ saveError }}</div>
    <div class="form-actions">
      <button type="submit" class="btn primary" :disabled="saving">{{ saving ? "يحفظ…" : "حفظ القالب" }}</button>
      <button type="button" class="btn" :disabled="saving" @click="close">إلغاء</button>
    </div>
  </form>

  <div v-if="catalog.loadError" class="notice" role="alert">
    {{ catalog.loadError }}
    <button type="button" class="btn retry" @click="catalog.load()">إعادة المحاولة</button>
  </div>
  <p v-else-if="!catalog.loaded" class="muted" role="status">يحمّل القوالب…</p>
  <div v-else-if="catalog.templates.length === 0" class="empty">
    <div class="inner"><div class="mark" aria-hidden="true"></div><p>لا قوالب بعد. ابدأ بـ«قالب جديد».</p></div>
  </div>

  <ul v-else class="cards">
    <li v-for="template in catalog.templates" :key="template.id" class="panel template">
      <BrandIcon :name="templateIcon(template.generator)" />
      <div class="what">
        <strong>{{ template.name }}</strong>
        <span class="muted">
          <span dir="ltr">{{ template.slug }}</span> ·
          <span class="num">{{ template.width_mm }} × {{ template.height_mm }} مم</span> ·
          <span class="num">{{ formatMoney(template.base_price) }}</span>
        </span>
        <span v-if="template.param_schema.length" class="fields">
          {{ template.param_schema.map(describeField).join("، ") }}
        </span>
      </div>
      <button type="button" class="btn" @click="open(template)">تعديل</button>
    </li>
  </ul>
</template>

<style scoped>
h2 { font-size: 20px; margin-block: 0 12px; }
h3 { font-size: 18px; margin-block: 20px 8px; }
.schema-field { border: 1px solid var(--line); border-radius: var(--radius); padding: 12px 16px; margin: 0 0 12px; min-inline-size: 0; }
.schema-field legend { padding-inline: 8px; font-weight: 600; }
.schema-field .check { align-self: end; }
.schema-field .error { display: block; margin-block-start: 8px; font-size: 14px; color: var(--risk); }
.remove { margin-block-start: 12px; }
.editor .notice { margin-block-start: 12px; }
.template { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px 16px; }
.what { display: flex; flex-direction: column; flex: 1 1 280px; min-inline-size: 0; line-height: 1.6; }
.what .muted, .fields { font-size: 15px; }
.retry { margin-inline-start: 12px; }
</style>
