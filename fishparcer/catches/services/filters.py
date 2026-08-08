import secrets

from django.db.models import Count
from django.db.models import Q
from django.db.models import QuerySet

from fishparcer.catches.forms import CatchFilterForm
from fishparcer.catches.models import CatchRecord


def get_fish_options() -> list[str]:
    return list(
        CatchRecord.objects.exclude(fish_type="")
        .exclude(fish_type__isnull=True)
        .values_list("fish_type", flat=True)
        .distinct()
        .order_by("fish_type"),
    )


def get_region_options() -> list[str]:
    return list(
        CatchRecord.objects.exclude(region="")
        .exclude(region__isnull=True)
        .values_list("region", flat=True)
        .distinct()
        .order_by("region"),
    )


def build_catch_filter_form(data) -> CatchFilterForm:
    return CatchFilterForm(
        data,
        fish_options=get_fish_options(),
        region_options=get_region_options(),
    )


def list_catch_queryset() -> QuerySet[CatchRecord]:
    return CatchRecord.objects.select_related("user", "source").prefetch_related(
        "photos",
        "tags",
    )


def detail_catch_queryset() -> QuerySet[CatchRecord]:
    return CatchRecord.objects.select_related(
        "user",
        "reservoir",
        "weather",
        "location",
    ).prefetch_related("photos", "tags", "comments")


def apply_catch_filters(queryset: QuerySet[CatchRecord], filter_form: CatchFilterForm):
    if not filter_form.is_valid():
        return queryset

    query = filter_form.cleaned_data.get("q")
    fish_names = filter_form.resolve_fish_names()
    region_names = filter_form.resolve_region_names()
    is_confirmed = filter_form.cleaned_data.get("is_confirmed")
    has_photo = filter_form.cleaned_data.get("has_photo")

    if query:
        queryset = queryset.filter(
            Q(fish_type__icontains=query)
            | Q(reservoir_name__icontains=query)
            | Q(region__icontains=query)
            | Q(quote__icontains=query)
            | Q(external_id__icontains=query),
        )
    if fish_names:
        queryset = queryset.filter(fish_type__in=fish_names)
    if region_names:
        queryset = queryset.filter(region__in=region_names)
    if is_confirmed == CatchFilterForm.CONFIRMED_YES:
        queryset = queryset.filter(review_status=CatchRecord.ReviewStatus.CONFIRMED)
    elif is_confirmed == CatchFilterForm.CONFIRMED_NO:
        queryset = queryset.filter(review_status=CatchRecord.ReviewStatus.NEW)
    if has_photo == CatchFilterForm.PHOTO_WITH:
        queryset = queryset.annotate(photo_count=Count("photos")).filter(photo_count__gt=0)
    elif has_photo == CatchFilterForm.PHOTO_WITHOUT:
        queryset = queryset.annotate(photo_count=Count("photos")).filter(photo_count=0)

    return queryset
