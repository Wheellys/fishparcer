from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CatchesConfig(AppConfig):
    name = "fishparcer.catches"
    verbose_name = _("Catches")
