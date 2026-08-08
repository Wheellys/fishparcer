from rest_framework import filters
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.mixins import ListModelMixin
from rest_framework.mixins import RetrieveModelMixin
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from fishparcer.catches.models import CatchRecord
from fishparcer.catches.services.fetcher import CatchFetchService
from fishparcer.catches.services.filters import apply_catch_filters
from fishparcer.catches.services.filters import build_catch_filter_form
from fishparcer.catches.services.filters import detail_catch_queryset
from fishparcer.catches.services.filters import list_catch_queryset

from .authentication import StaticApiTokenAuthentication
from .serializers import CatchRecordDetailSerializer
from .serializers import CatchRecordListSerializer
from .serializers import FetchCatchesSerializer


class CatchRecordPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class CatchRecordViewSet(RetrieveModelMixin, ListModelMixin, GenericViewSet):
    lookup_field = "external_id"
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["fish_type", "reservoir_name", "region", "quote"]
    ordering_fields = ["fishing_date", "created_at_external", "likes", "caught"]
    ordering = ["-created_at_external"]

    def get_queryset(self):
        queryset = CatchRecord.objects.select_related(
            "user",
            "reservoir",
            "weather",
            "location",
        ).prefetch_related("photos", "tags", "comments")

        fish_type = self.request.query_params.get("fish_type")
        if fish_type:
            queryset = queryset.filter(fish_type__iexact=fish_type)

        region = self.request.query_params.get("region")
        if region:
            queryset = queryset.filter(region__icontains=region)

        fishing_date = self.request.query_params.get("fishing_date")
        if fishing_date:
            queryset = queryset.filter(fishing_date=fishing_date)

        return queryset

    def get_serializer_class(self):
        if self.action == "retrieve":
            return CatchRecordDetailSerializer
        if self.action == "sync":
            return FetchCatchesSerializer
        return CatchRecordListSerializer

    @action(detail=False, methods=["post"])
    def sync(self, request):
        """Загрузить JSON по URL и сохранить в базу данных."""
        serializer = FetchCatchesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        service = CatchFetchService()
        try:
            sync_log, photo_stats = service.import_from_url(
                serializer.validated_data["url"],
                source_name=serializer.validated_data.get("source_name", ""),
                download_photos=serializer.validated_data.get("download_photos", True),
                headers=serializer.validated_data.get("headers"),
            )
        except Exception as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "status": sync_log.status,
                "records_fetched": sync_log.records_fetched,
                "records_created": sync_log.records_created,
                "records_updated": sync_log.records_updated,
                "photo_stats": photo_stats,
            },
            status=status.HTTP_200_OK,
        )


class PublicCatchRecordViewSet(RetrieveModelMixin, ListModelMixin, GenericViewSet):
    """
    Публичный API отчётов с теми же фильтрами, что и на сайте.

    Query params:
    - q — поиск
    - fish — id рыбы (можно несколько: fish=1&fish=2)
    - region — id региона (можно несколько)
    - is_confirmed — yes / no
    - has_photo — with / without
    - page, page_size — пагинация
    """

    authentication_classes = [StaticApiTokenAuthentication]
    permission_classes = [AllowAny]
    lookup_field = "external_id"
    pagination_class = CatchRecordPagination
    serializer_class = CatchRecordListSerializer

    def _get_filter_form(self):
        if not hasattr(self, "_filter_form"):
            self._filter_form = build_catch_filter_form(self.request.query_params)
        return self._filter_form

    def get_serializer_class(self):
        if self.action == "retrieve":
            return CatchRecordDetailSerializer
        return CatchRecordListSerializer

    def list(self, request, *args, **kwargs):
        filter_form = self._get_filter_form()
        if not filter_form.is_valid():
            return Response(filter_form.errors, status=status.HTTP_400_BAD_REQUEST)
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        if self.action == "retrieve":
            return detail_catch_queryset()

        queryset = list_catch_queryset()
        filter_form = self._get_filter_form()
        if filter_form.is_valid():
            return apply_catch_filters(queryset, filter_form)
        return queryset.none()
