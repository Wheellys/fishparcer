import secrets

from django.contrib import admin

from fishparcer.catches.models import ApiSource
from fishparcer.catches.models import CatchComment
from fishparcer.catches.models import CatchLocation
from fishparcer.catches.models import CatchPhoto
from fishparcer.catches.models import CatchRecord
from fishparcer.catches.models import CatchTag
from fishparcer.catches.models import CatchWeather
from fishparcer.catches.models import PublicApiToken
from fishparcer.catches.models import Reservoir
from fishparcer.catches.models import SourceUser
from fishparcer.catches.models import SyncLog
from fishparcer.catches.services.fetcher import CatchFetchService


class CatchPhotoInline(admin.TabularInline):
    model = CatchPhoto
    extra = 0
    readonly_fields = ["original_path", "original_url", "download_status", "downloaded_at"]


class CatchCommentInline(admin.TabularInline):
    model = CatchComment
    extra = 0
    readonly_fields = ["external_id", "created_at_external"]


@admin.register(PublicApiToken)
class PublicApiTokenAdmin(admin.ModelAdmin):
    list_display = ["name", "token", "is_active", "created_at", "last_used_at"]
    list_filter = ["is_active"]
    search_fields = ["name", "token"]
    readonly_fields = ["token", "created_at", "last_used_at"]
    actions = ["regenerate_tokens"]

    @admin.action(description="Перегенерировать токен")
    def regenerate_tokens(self, request, queryset):
        for api_token in queryset:
            api_token.token = secrets.token_urlsafe(32)
            api_token.save(update_fields=["token"])
        self.message_user(request, f"Токены обновлены: {queryset.count()}.")


@admin.register(CatchRecord)
class CatchRecordAdmin(admin.ModelAdmin):
    list_display = [
        "external_id",
        "fish_type",
        "reservoir_name",
        "fishing_date",
        "review_status",
        "user",
        "last_synced_at",
    ]
    list_filter = ["fish_type", "region", "bite_status", "fishing_date", "review_status"]
    search_fields = ["external_id", "reservoir_name", "quote", "fish_type"]
    readonly_fields = ["content_hash", "first_synced_at", "last_synced_at"]
    filter_horizontal = ["tags"]
    inlines = [CatchPhotoInline, CatchCommentInline]
    date_hierarchy = "fishing_date"


@admin.register(CatchPhoto)
class CatchPhotoAdmin(admin.ModelAdmin):
    list_display = ["catch", "original_path", "is_primary", "download_status", "downloaded_at"]
    list_filter = ["download_status", "is_primary"]
    search_fields = ["catch__external_id", "original_path"]


@admin.register(SourceUser)
class SourceUserAdmin(admin.ModelAdmin):
    list_display = ["external_id", "name", "initials", "synced_at"]
    search_fields = ["external_id", "name"]


@admin.register(Reservoir)
class ReservoirAdmin(admin.ModelAdmin):
    list_display = ["external_id", "name", "region", "country"]
    search_fields = ["external_id", "name", "region"]


@admin.register(CatchTag)
class CatchTagAdmin(admin.ModelAdmin):
    search_fields = ["name"]


@admin.register(CatchWeather)
class CatchWeatherAdmin(admin.ModelAdmin):
    list_display = ["catch", "temp", "condition", "wind_dir"]


@admin.register(CatchLocation)
class CatchLocationAdmin(admin.ModelAdmin):
    list_display = ["catch", "display_text", "lat", "lng", "mode"]


@admin.register(ApiSource)
class ApiSourceAdmin(admin.ModelAdmin):
    list_display = ["name", "fetch_url", "base_url", "created_at"]
    actions = ["sync_from_url"]

    @admin.action(description="Загрузить данные по fetch_url")
    def sync_from_url(self, request, queryset):
        service = CatchFetchService()
        for source in queryset:
            if not source.fetch_url:
                self.message_user(
                    request,
                    f"У источника «{source.name}» не указан fetch_url",
                    level="error",
                )
                continue
            try:
                sync_log, _ = service.import_from_url(
                    source.fetch_url,
                    source_name=source.name,
                    download_photos=True,
                )
                self.message_user(
                    request,
                    f"«{source.name}»: загружено {sync_log.records_fetched} "
                    f"({sync_log.records_created} новых, {sync_log.records_updated} обновлено)",
                )
            except Exception as exc:
                self.message_user(request, f"Ошибка «{source.name}»: {exc}", level="error")


@admin.register(SyncLog)
class SyncLogAdmin(admin.ModelAdmin):
    list_display = [
        "started_at",
        "status",
        "records_fetched",
        "records_created",
        "records_updated",
    ]
    list_filter = ["status"]
    readonly_fields = [
        "started_at",
        "finished_at",
        "records_fetched",
        "records_created",
        "records_updated",
        "error_message",
    ]
