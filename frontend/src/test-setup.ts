import { config } from "@vue/test-utils";
import { DEFAULT_LOCALE } from "@/domain/locale";
import { i18n, setLocale } from "@/i18n";

config.global.plugins = [...config.global.plugins, i18n];

// i18n كائن واحد للوحدة كلها: اختبار غيّر اللغة لا يتركها لما بعده.
beforeEach(() => setLocale(DEFAULT_LOCALE));
