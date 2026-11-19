// إعداد مشروع Railway. لا يُقرأ عند النشر: يُطبَّق بـ `railway config plan` ثم `railway config apply` من طرفية المالك.
// ما يغيب عن resources يُحذف عند التطبيق؛ راجع الخطة قبل كل تطبيق. القيم السرية preserve() أو مراجع، لا نصوص.
import { defineRailway, github, postgres, preserve, project, redis, service, volume } from "railway/iac";

const REGION = "europe-west4-drams3a";
const REPO = "mesuef1974/misk";

export default defineRailway(() => {
  const Postgres = postgres("Postgres", { region: REGION });
  Postgres.networking = { privateNetworkEndpoint: "postgres" };
  const postgresVolume = volume("postgres-volume", { alerts: { usage: { "100": {}, "80": {}, "95": {} } }, allowOnlineResize: true, region: REGION, sizeMB: 50000 });

  // وسيط Celery والذاكرة المؤقتة (config/settings/base.py: REDIS_URL).
  const Redis = redis("Redis", { region: REGION });

  // checkSuites: لا يُنشر إيداع على main قبل نجاح فحوص CI عليه (قرار المالك 2026-11-19، ج4).
  const misk = service("misk", {
    source: github(REPO, { checkSuites: true }),
    start: "bash scripts/railway-release.sh",
    healthcheck: "/health/",
    healthcheckTimeout: 120,
    preDeploy: "bash scripts/railway-predeploy.sh",
    // من railway.toml المحذوف: إعادة تشغيل عند الفشل بخمس محاولات. ON_FAILURE افتراضي Railway ويُخزَّن null،
    // فذكر restartPolicyType يُبقي فرقًا دائمًا في `railway config plan` بعد كل apply (2026-11-19)؛ لذا يُترك.
    deploy: { restartPolicyMaxRetries: 5 },
    replicas: { [REGION]: 1 },
    env: {
      ALLOWED_HOSTS: preserve(),
      CSRF_TRUSTED_ORIGINS: preserve(),
      DATABASE_URL: preserve(),
      SECRET_KEY: preserve(),
      REDIS_URL: Redis.env.REDIS_URL,
      // مفعَّل في الإنتاج على الخدمتين؛ غيابه هنا قد يحذفه عند التطبيق فيعود التخطيط متزامنًا بصمت (ج3).
      PLANNING_ASYNC: preserve(),
    },
  });

  // عامل Celery: المستودع نفسه بأمر بدء آخر، بلا healthcheck HTTP ولا هجرات (الهجرات في preDeploy الويب وحده).
  const worker = service("worker", {
    source: github(REPO, { checkSuites: true }),
    // ينتظر هجرات preDeploy الويب قبل أن يأخذ مهمة (scripts/railway-worker.sh).
    start: "sh scripts/railway-worker.sh",
    replicas: { [REGION]: 1 },
    env: {
      ALLOWED_HOSTS: misk.env.ALLOWED_HOSTS,
      DATABASE_URL: Postgres.env.DATABASE_URL,
      SECRET_KEY: misk.env.SECRET_KEY,
      REDIS_URL: Redis.env.REDIS_URL,
      PLANNING_ASYNC: preserve(),
    },
  });

  return project("independent-acceptance", {
    resources: [misk, worker, Postgres, postgresVolume, Redis],
  });
});
