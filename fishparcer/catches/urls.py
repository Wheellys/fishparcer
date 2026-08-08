from django.urls import path

from fishparcer.catches.views import CatchListView
from fishparcer.catches.views import CatchToggleConfirmView
from fishparcer.catches.views import CatchUpdateView
from fishparcer.catches.views import SyncView

app_name = "catches"
urlpatterns = [
    path("sync/", SyncView.as_view(), name="sync"),
    path("reports/", CatchListView.as_view(), name="report_list"),
    path("reports/<slug:external_id>/", CatchUpdateView.as_view(), name="report_edit"),
    path(
        "reports/<slug:external_id>/confirm/",
        CatchToggleConfirmView.as_view(),
        name="report_toggle_confirm",
    ),
]
