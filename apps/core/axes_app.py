"""django-axes باسم عربي في لوحة الإدارة. سلوكه كما هو: الصنف يرث إعداده كله ولا يغيّر إلا الاسم الظاهر."""

from axes.apps import AppConfig as AxesAppConfig


class MiskAxesConfig(AxesAppConfig):
    verbose_name = "حماية الدخول"
