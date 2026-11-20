"""فحص صحة عامل Celery على Railway (د8): 200 حين يجهز العامل فعلًا، و503 قبله.

Railway لا يُسقط نشر العامل القديم إلا بعد أن ينجح فحص صحة الجديد. فإن فشل preDeploy الويب وبقيت
الهجرات معلّقة، لا يجهز الجديد أبدًا، فيفشل نشره ويبقى القديم يعمل بشيفرته على المخطط القديم.
الجاهزية ملف يكتبه إشعار `worker_ready` في `config/celery.py` ويحذفه `worker_shutdown`.
مكتبة قياسية وحدها، بلا Django: يبدأ قبل فحص الهجرات ولا يلمس القاعدة.
"""

from __future__ import annotations

import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HEALTH_PATH = "/health/"


def ready_file() -> Path:
    return Path(os.environ["WORKER_READY_FILE"])


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 (اسم تفرضه المكتبة)
        if self.path.split("?", 1)[0] != HEALTH_PATH:
            self.send_error(404)
            return
        ready = ready_file().exists()
        body = b"ok\n" if ready else b"starting\n"
        self.send_response(200 if ready else 503)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        # فحص كل بضع ثوانٍ لا يُغرق سجل العامل.
        return


def serve(port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("0.0.0.0", port), Handler)  # noqa: S104 (Railway يفحص من خارج الحاوية)


if __name__ == "__main__":
    serve(int(os.environ.get("PORT", "8080"))).serve_forever()
