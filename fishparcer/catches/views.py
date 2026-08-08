from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.urls import reverse
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import FormView
from django.views.generic import ListView
from django.views.generic import UpdateView
from django.views.generic import View
from urllib.parse import parse_qsl
from urllib.parse import urlencode

from fishparcer.catches.forms import CatchRecordForm
from fishparcer.catches.forms import FetchUrlForm
from fishparcer.catches.models import CatchRecord
from fishparcer.catches.services.fetcher import CatchFetchService
from fishparcer.catches.services.filters import apply_catch_filters
from fishparcer.catches.services.filters import build_catch_filter_form
from fishparcer.catches.services.filters import list_catch_queryset


def _set_confirmed(catch: CatchRecord, user, confirmed: bool) -> None:
    if confirmed:
        catch.review_status = CatchRecord.ReviewStatus.CONFIRMED
        catch.confirmed_at = timezone.now()
        catch.confirmed_by = user
    else:
        catch.review_status = CatchRecord.ReviewStatus.NEW
        catch.confirmed_at = None
        catch.confirmed_by = None
    catch.save(update_fields=["review_status", "confirmed_at", "confirmed_by"])

class SyncView(LoginRequiredMixin, FormView):
    template_name = "catches/sync.html"
    form_class = FetchUrlForm
    success_url = reverse_lazy("home")

    def form_valid(self, form):
        service = CatchFetchService()
        headers = CatchFetchService.build_headers(
            auth_token=form.cleaned_data.get("auth_token", ""),
            session_cookie=form.cleaned_data.get("session_cookie", ""),
            extra_headers=form.cleaned_data.get("extra_headers", ""),
        )
        source_name = form.cleaned_data.get("source_name", "")
        download_photos = form.cleaned_data.get("download_photos", True)

        try:
            if form.cleaned_data.get("json_body"):
                base_url = ""
                if form.cleaned_data.get("url"):
                    from urllib.parse import urlparse

                    parsed = urlparse(form.cleaned_data["url"])
                    base_url = f"{parsed.scheme}://{parsed.netloc}"
                sync_log, photo_stats = service.import_from_json(
                    form.cleaned_data["json_body"],
                    source_name=source_name,
                    base_url=base_url,
                    download_photos=download_photos,
                )
            else:
                sync_log, photo_stats = service.import_from_url(
                    form.cleaned_data["url"],
                    source_name=source_name,
                    download_photos=download_photos,
                    headers=headers,
                )
        except Exception as exc:
            messages.error(self.request, f"Ошибка загрузки: {exc}")
            return self.form_invalid(form)

        downloaded = sum(stats.get("downloaded", 0) for stats in photo_stats.values())
        messages.success(
            self.request,
            f"Загружено {sync_log.records_fetched} записей "
            f"({sync_log.records_created} новых, {sync_log.records_updated} обновлено). "
            f"Фото скачано: {downloaded}.",
        )
        return super().form_valid(form)


class CatchListView(LoginRequiredMixin, ListView):
    model = CatchRecord
    template_name = "catches/report_list.html"
    context_object_name = "reports"
    paginate_by = 20

    @staticmethod
    def _query_strings_differ(current_qs, canonical_qs):
        return sorted(parse_qsl(current_qs, keep_blank_values=True)) != sorted(
            parse_qsl(canonical_qs, keep_blank_values=True),
        )

    def _build_filter_form(self):
        return build_catch_filter_form(self.request.GET or None)

    def get(self, request, *args, **kwargs):
        filter_form = self._build_filter_form()
        if filter_form.is_valid() and request.GET:
            canonical_qs = filter_form.get_query_string()
            current_qs = urlencode(
                [(key, value) for key, value in request.GET.items() if key != "page"],
                doseq=True,
            )
            if self._query_strings_differ(current_qs, canonical_qs):
                redirect_url = request.path
                if canonical_qs:
                    redirect_url = f"{redirect_url}?{canonical_qs}"
                return redirect(redirect_url)
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        self.filter_form = self._build_filter_form()
        queryset = list_catch_queryset()
        if self.filter_form.is_valid():
            queryset = apply_catch_filters(queryset, self.filter_form)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_form"] = self.filter_form
        context["filter_query"] = (
            self.filter_form.get_query_string() if self.filter_form.is_valid() else ""
        )
        context["stats"] = {
            "total": CatchRecord.objects.count(),
            "new": CatchRecord.objects.filter(review_status=CatchRecord.ReviewStatus.NEW).count(),
            "confirmed": CatchRecord.objects.filter(
                review_status=CatchRecord.ReviewStatus.CONFIRMED,
            ).count(),
        }
        return context


class CatchUpdateView(LoginRequiredMixin, UpdateView):
    model = CatchRecord
    form_class = CatchRecordForm
    template_name = "catches/report_form.html"
    slug_field = "external_id"
    slug_url_kwarg = "external_id"

    def get_queryset(self):
        return CatchRecord.objects.select_related("user", "weather", "location").prefetch_related(
            "photos",
            "tags",
        )

    def get_context_data(self, **kwargs):
        import json

        context = super().get_context_data(**kwargs)
        context["photos"] = self.object.photos.all()
        context["raw_payload_json"] = json.dumps(
            self.object.raw_payload,
            ensure_ascii=False,
            indent=2,
        )
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        is_confirmed = form.cleaned_data.get("is_confirmed", False)
        _set_confirmed(self.object, self.request.user, is_confirmed)
        messages.success(self.request, f"Отчёт {self.object.external_id} сохранён.")
        return response
    def get_success_url(self):
        return reverse("catches:report_edit", kwargs={"external_id": self.object.external_id})


class CatchToggleConfirmView(LoginRequiredMixin, View):
    def post(self, request, external_id):
        catch = get_object_or_404(CatchRecord, external_id=external_id)
        confirmed = request.POST.get("confirmed") == "1"
        _set_confirmed(catch, request.user, confirmed)

        next_url = request.POST.get("next") or reverse("home")
        return redirect(next_url)