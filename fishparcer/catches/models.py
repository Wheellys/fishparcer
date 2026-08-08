import hashlib
import json
import secrets
import uuid

from django.conf import settings
from django.db import models


class ApiSource(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    base_url = models.URLField(max_length=512, help_text="Базовый URL для скачивания фото")
    fetch_url = models.URLField(
        max_length=1024,
        blank=True,
        help_text="URL для загрузки JSON со списком уловов",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "API source"
        verbose_name_plural = "API sources"

    def __str__(self) -> str:
        return self.name


class SourceUser(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    external_id = models.CharField(max_length=64, unique=True, db_index=True)
    name = models.CharField(max_length=255, blank=True)
    initials = models.CharField(max_length=16, blank=True)
    avatar_bg = models.CharField(max_length=32, blank=True)
    raw_payload = models.JSONField(default=dict)
    synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "source user"
        verbose_name_plural = "source users"

    def __str__(self) -> str:
        return self.name or self.external_id


class Reservoir(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    external_id = models.CharField(max_length=64, unique=True, db_index=True)
    name = models.CharField(max_length=255, blank=True)
    region = models.CharField(max_length=255, blank=True)
    country = models.CharField(max_length=255, blank=True)
    raw_payload = models.JSONField(default=dict)

    class Meta:
        verbose_name = "reservoir"
        verbose_name_plural = "reservoirs"

    def __str__(self) -> str:
        return self.name or self.external_id


class CatchTag(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=128, unique=True)

    class Meta:
        verbose_name = "catch tag"
        verbose_name_plural = "catch tags"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class CatchRecord(models.Model):
    class ReviewStatus(models.TextChoices):
        NEW = "new", "Новый"
        CONFIRMED = "confirmed", "Подтверждён"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.ForeignKey(
        ApiSource,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="catches",
    )
    external_id = models.CharField(max_length=64, unique=True, db_index=True)
    raw_payload = models.JSONField()

    user = models.ForeignKey(
        SourceUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="catches",
    )
    reservoir = models.ForeignKey(
        Reservoir,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="catches",
    )

    reservoir_name = models.CharField(max_length=255, blank=True)
    region = models.CharField(max_length=255, blank=True)
    country = models.CharField(max_length=255, blank=True)
    fish_type = models.CharField(max_length=128, blank=True)
    weight = models.DecimalField(max_digits=8, decimal_places=3, default=0)
    bite_status = models.CharField(max_length=32, blank=True)
    time_of_day = models.CharField(max_length=64, blank=True)
    tackle = models.JSONField(default=dict, blank=True)
    bites = models.PositiveIntegerField(default=0)
    caught = models.PositiveIntegerField(default=0)
    quote = models.TextField(blank=True)

    created_at_external = models.DateTimeField(null=True, blank=True)
    likes = models.PositiveIntegerField(default=0)
    comments_count = models.PositiveIntegerField(default=0)
    total_comments = models.PositiveIntegerField(default=0)
    is_personal_best = models.BooleanField(default=False)

    time_start = models.CharField(max_length=16, blank=True)
    time_end = models.CharField(max_length=16, blank=True)
    fishing_style = models.CharField(max_length=128, blank=True)
    fishing_date = models.DateField(null=True, blank=True)

    photo_tags = models.JSONField(default=dict, blank=True)
    photo_size_tags = models.JSONField(default=dict, blank=True)
    is_spot_member = models.BooleanField(default=False)
    gear_raw = models.JSONField(default=list, blank=True)

    tags = models.ManyToManyField(CatchTag, related_name="catches", blank=True)

    review_status = models.CharField(
        max_length=16,
        choices=ReviewStatus.choices,
        default=ReviewStatus.NEW,
        db_index=True,
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="confirmed_catches",
    )

    content_hash = models.CharField(max_length=64, db_index=True, blank=True)
    first_synced_at = models.DateTimeField(auto_now_add=True)
    last_synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "catch record"
        verbose_name_plural = "catch records"
        ordering = ["-created_at_external"]
        indexes = [
            models.Index(fields=["fishing_date"]),
            models.Index(fields=["fish_type"]),
            models.Index(fields=["region"]),
        ]

    def __str__(self) -> str:
        return f"{self.external_id} ({self.fish_type})"

    @staticmethod
    def compute_content_hash(payload: dict) -> str:
        normalized = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(normalized.encode()).hexdigest()


class CatchPhoto(models.Model):
    class DownloadStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        DOWNLOADED = "downloaded", "Downloaded"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    catch = models.ForeignKey(
        CatchRecord,
        on_delete=models.CASCADE,
        related_name="photos",
    )
    original_path = models.CharField(max_length=512)
    original_url = models.URLField(max_length=1024, blank=True)
    local_file = models.FileField(upload_to="catches/%Y/%m/", blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_primary = models.BooleanField(default=False)
    download_status = models.CharField(
        max_length=16,
        choices=DownloadStatus.choices,
        default=DownloadStatus.PENDING,
    )
    downloaded_at = models.DateTimeField(null=True, blank=True)
    file_size = models.PositiveBigIntegerField(null=True, blank=True)
    content_type = models.CharField(max_length=128, blank=True)

    class Meta:
        verbose_name = "catch photo"
        verbose_name_plural = "catch photos"
        ordering = ["sort_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["catch", "original_path"],
                name="unique_catch_photo_path",
            ),
        ]

    def __str__(self) -> str:
        return self.original_path


class CatchWeather(models.Model):
    catch = models.OneToOneField(
        CatchRecord,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="weather",
    )
    temp = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    pressure = models.PositiveIntegerField(null=True, blank=True)
    humidity = models.PositiveIntegerField(null=True, blank=True)
    wind_speed = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    wind_dir = models.CharField(max_length=16, blank=True)
    cloud_cover = models.PositiveIntegerField(null=True, blank=True)
    precipitation = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    condition = models.CharField(max_length=64, blank=True)
    moon_phase = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    moon_phase_label = models.CharField(max_length=64, blank=True)
    raw_payload = models.JSONField(default=dict)

    class Meta:
        verbose_name = "catch weather"
        verbose_name_plural = "catch weather"

    def __str__(self) -> str:
        return f"Weather for {self.catch.external_id}"


class CatchLocation(models.Model):
    catch = models.OneToOneField(
        CatchRecord,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="location",
    )
    mode = models.CharField(max_length=32, blank=True)
    display_text = models.CharField(max_length=255, blank=True)
    lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    raw_payload = models.JSONField(default=dict)

    class Meta:
        verbose_name = "catch location"
        verbose_name_plural = "catch locations"

    def __str__(self) -> str:
        return self.display_text or str(self.catch.external_id)


class CatchComment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    catch = models.ForeignKey(
        CatchRecord,
        on_delete=models.CASCADE,
        related_name="comments",
    )
    external_id = models.CharField(max_length=64, blank=True, db_index=True)
    raw_payload = models.JSONField(default=dict)
    created_at_external = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "catch comment"
        verbose_name_plural = "catch comments"
        ordering = ["created_at_external"]

    def __str__(self) -> str:
        return self.external_id or str(self.id)


class SyncLog(models.Model):
    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.ForeignKey(
        ApiSource,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sync_logs",
    )
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.RUNNING,
    )
    records_fetched = models.PositiveIntegerField(default=0)
    records_created = models.PositiveIntegerField(default=0)
    records_updated = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)

    class Meta:
        verbose_name = "sync log"
        verbose_name_plural = "sync logs"
        ordering = ["-started_at"]

    def __str__(self) -> str:
        return f"Sync {self.started_at:%Y-%m-%d %H:%M} ({self.status})"


class PublicApiToken(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, help_text="Название клиента или интеграции")
    token = models.CharField(max_length=64, unique=True, db_index=True, editable=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "public API token"
        verbose_name_plural = "public API tokens"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_urlsafe(32)
        super().save(*args, **kwargs)
