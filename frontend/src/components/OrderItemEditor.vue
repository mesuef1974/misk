<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import { materialName, templateName } from "@/domain/catalog";
import { formatMoney } from "@/domain/orders";
import { withTemplate, type ItemErrors, type ItemForm } from "@/domain/orderForm";
import { choiceLabel, fieldLabel, type ParamValue } from "@/domain/params";
import type { Material, ProductTemplate } from "@/services/catalog";

const props = withDefaults(
  defineProps<{
    item: ItemForm;
    index: number;
    templates: ProductTemplate[];
    materials: Material[];
    errors?: ItemErrors;
    removable?: boolean;
  }>(),
  { errors: () => ({}), removable: false },
);
// التغييرات تُرسل جزئيةً والأب يطبّقها على حالته فورًا: حدثان في النبضة نفسها (تعبئة تلقائية مثلًا)
// لا يمحو أحدهما الآخر، كما كان سيحدث لو بُني كل تغيير على نسخة الخاصية قبل إعادة الرسم.
const emit = defineEmits<{
  patch: [change: Partial<ItemForm>];
  param: [name: string, value: ParamValue];
  remove: [];
}>();

const { t } = useI18n();

const template = computed(() => props.templates.find((candidate) => candidate.slug === props.item.templateSlug));
const schema = computed(() => template.value?.param_schema ?? []);
const pricePlaceholder = computed(() => (template.value ? formatMoney(template.value.base_price) : ""));
const uid = computed(() => `item-${props.item.key}`);

function patch(change: Partial<ItemForm>): void {
  emit("patch", change);
}

function chooseTemplate(event: Event): void {
  const slug = (event.target as HTMLSelectElement).value;
  const next = withTemplate(
    props.item,
    props.templates.find((candidate) => candidate.slug === slug),
  );
  patch({ templateSlug: next.templateSlug, params: next.params });
}

function numberOf(event: Event): number | "" {
  const raw = (event.target as HTMLInputElement).value;
  return raw === "" ? "" : Number(raw);
}

function setParam(name: string, value: ParamValue): void {
  emit("param", name, value);
}

function textOf(event: Event): string {
  return (event.target as HTMLInputElement).value;
}

/** قيمة الخيار تُقرأ من المخطط لا من نص <option>، فتبقى الخيارات الرقمية أرقامًا. */
function chooseParam(name: string, choices: ParamValue[], event: Event): void {
  const index = (event.target as HTMLSelectElement).selectedIndex - 1;
  setParam(name, index >= 0 ? choices[index] : "");
}
</script>

<template>
  <fieldset class="item">
    <legend>{{ t("orders.item.legend", { number: index + 1 }) }}</legend>

    <div class="grid">
      <label class="field">
        <span>{{ t("orders.item.template") }}</span>
        <select :value="item.templateSlug" :aria-invalid="Boolean(errors.template)" @change="chooseTemplate">
          <option value="">{{ t("orders.item.chooseTemplate") }}</option>
          <option v-for="option in templates" :key="option.slug" :value="option.slug">{{ templateName(option) }}</option>
        </select>
        <span v-if="errors.template" class="error">{{ errors.template }}</span>
      </label>

      <label class="field">
        <span>{{ t("orders.item.material") }}</span>
        <select
          :value="item.materialId"
          :aria-invalid="Boolean(errors.material)"
          @change="patch({ materialId: numberOf($event) })"
        >
          <option value="">{{ t("orders.item.chooseMaterial") }}</option>
          <option v-for="option in materials" :key="option.id" :value="option.id">
            {{ t("orders.item.materialOption", { name: materialName(option), thickness: option.thickness_mm }) }}
          </option>
        </select>
        <span v-if="errors.material" class="error">{{ errors.material }}</span>
      </label>

      <label class="field">
        <span>{{ t("orders.item.quantity") }}</span>
        <input
          type="number"
          min="1"
          step="1"
          inputmode="numeric"
          :value="item.quantity"
          :aria-invalid="Boolean(errors.quantity)"
          @input="patch({ quantity: numberOf($event) })"
        />
        <span v-if="errors.quantity" class="error">{{ errors.quantity }}</span>
      </label>

      <label class="field">
        <span>{{ t("orders.item.unitPrice") }}</span>
        <input
          type="number"
          min="0"
          step="0.01"
          inputmode="decimal"
          :value="item.unitPrice"
          :placeholder="pricePlaceholder"
          :aria-invalid="Boolean(errors.unitPrice)"
          @input="patch({ unitPrice: numberOf($event) })"
        />
        <span v-if="errors.unitPrice" class="error">{{ errors.unitPrice }}</span>
      </label>
    </div>

    <div v-if="schema.length" class="grid params">
      <template v-for="field in schema" :key="field.name">
        <label v-if="field.type === 'bool'" class="check">
          <input
            type="checkbox"
            :checked="item.params[field.name] === true"
            @change="setParam(field.name, ($event.target as HTMLInputElement).checked)"
          />
          <span>{{ fieldLabel(field) }}</span>
        </label>

        <label v-else class="field">
          <span>{{ fieldLabel(field) }}<template v-if="field.required === false"> {{ t("orders.optional") }}</template></span>
          <select
            v-if="field.type === 'choice'"
            :id="`${uid}-${field.name}`"
            :aria-invalid="Boolean(errors[`param:${field.name}`])"
            @change="chooseParam(field.name, field.choices ?? [], $event)"
          >
            <option value="" :selected="item.params[field.name] === ''">{{ t("orders.item.choose") }}</option>
            <option
              v-for="choice in field.choices"
              :key="String(choice)"
              :selected="item.params[field.name] === choice"
            >
              {{ choiceLabel(field, choice) }}
            </option>
          </select>
          <input
            v-else-if="field.type === 'int'"
            type="number"
            step="1"
            inputmode="numeric"
            :min="field.min"
            :max="field.max"
            :value="item.params[field.name]"
            :aria-invalid="Boolean(errors[`param:${field.name}`])"
            @input="setParam(field.name, numberOf($event))"
          />
          <input
            v-else
            type="text"
            :maxlength="field.max_length"
            :value="item.params[field.name]"
            :aria-invalid="Boolean(errors[`param:${field.name}`])"
            @input="setParam(field.name, textOf($event))"
          />
          <span v-if="errors[`param:${field.name}`]" class="error">{{ errors[`param:${field.name}`] }}</span>
        </label>
      </template>
    </div>

    <button v-if="removable" type="button" class="btn danger remove" @click="emit('remove')">{{ t("orders.item.remove") }}</button>
  </fieldset>
</template>

<style scoped>
.item { border: 1px solid var(--line); border-radius: calc(var(--radius) * 2); padding: 20px; margin: 0; min-inline-size: 0; background: var(--surface); }
legend { padding-inline: 8px; font-weight: 600; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px 16px; }
.params { margin-block-start: 12px; padding-block-start: 12px; border-block-start: 1px dashed var(--line); }
.check { display: flex; align-items: center; gap: 8px; min-block-size: 44px; align-self: end; }
.remove { margin-block-start: 12px; }
</style>
