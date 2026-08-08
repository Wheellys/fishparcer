from rest_framework import serializers

from fishparcer.catches.models import CatchComment
from fishparcer.catches.models import CatchLocation
from fishparcer.catches.models import CatchPhoto
from fishparcer.catches.models import CatchRecord
from fishparcer.catches.models import CatchWeather
from fishparcer.catches.models import SourceUser


class SourceUserSerializer(serializers.ModelSerializer[SourceUser]):
    class Meta:
        model = SourceUser
        fields = ["external_id", "name", "initials", "avatar_bg"]


class CatchPhotoSerializer(serializers.ModelSerializer[CatchPhoto]):
    url = serializers.SerializerMethodField()

    class Meta:
        model = CatchPhoto
        fields = [
            "id",
            "original_path",
            "url",
            "sort_order",
            "is_primary",
            "download_status",
        ]

    def get_url(self, obj: CatchPhoto) -> str:
        request = self.context.get("request")
        if obj.local_file:
            if request:
                return request.build_absolute_uri(obj.local_file.url)
            return obj.local_file.url
        return obj.original_path


class CatchWeatherSerializer(serializers.ModelSerializer[CatchWeather]):
    class Meta:
        model = CatchWeather
        fields = [
            "temp",
            "pressure",
            "humidity",
            "wind_speed",
            "wind_dir",
            "cloud_cover",
            "precipitation",
            "condition",
            "moon_phase",
            "moon_phase_label",
        ]


class CatchLocationSerializer(serializers.ModelSerializer[CatchLocation]):
    class Meta:
        model = CatchLocation
        fields = ["mode", "display_text", "lat", "lng"]


class CatchCommentSerializer(serializers.ModelSerializer[CatchComment]):
    class Meta:
        model = CatchComment
        fields = ["external_id", "raw_payload", "created_at_external"]


class FetchCatchesSerializer(serializers.Serializer):
    url = serializers.URLField(help_text="URL API, который возвращает JSON")
    source_name = serializers.CharField(required=False, allow_blank=True, default="")
    download_photos = serializers.BooleanField(default=True)
    headers = serializers.DictField(
        child=serializers.CharField(),
        required=False,
        help_text="Дополнительные HTTP-заголовки, например Authorization",
    )


class CatchRecordListSerializer(serializers.ModelSerializer[CatchRecord]):
    user = SourceUserSerializer(read_only=True)
    primary_photo = serializers.SerializerMethodField()
    tags = serializers.StringRelatedField(many=True)

    class Meta:
        model = CatchRecord
        fields = [
            "id",
            "external_id",
            "fish_type",
            "reservoir_name",
            "region",
            "fishing_date",
            "fishing_style",
            "weight",
            "caught",
            "likes",
            "quote",
            "user",
            "primary_photo",
            "tags",
            "review_status",
            "created_at_external",
        ]

    def get_primary_photo(self, obj: CatchRecord) -> str | None:
        photo = obj.photos.filter(is_primary=True).first() or obj.photos.first()
        if not photo:
            return None
        request = self.context.get("request")
        if photo.local_file:
            if request:
                return request.build_absolute_uri(photo.local_file.url)
            return photo.local_file.url
        return photo.original_path


class CatchRecordDetailSerializer(CatchRecordListSerializer):
    photos = CatchPhotoSerializer(many=True, read_only=True)
    weather = CatchWeatherSerializer(read_only=True)
    location = CatchLocationSerializer(read_only=True)
    comments = CatchCommentSerializer(many=True, read_only=True)
    raw_payload = serializers.JSONField(read_only=True)

    class Meta(CatchRecordListSerializer.Meta):
        fields = [
            *CatchRecordListSerializer.Meta.fields,
            "review_status",
            "confirmed_at",
            "bite_status",
            "time_of_day",
            "time_start",
            "time_end",
            "bites",
            "comments_count",
            "total_comments",
            "is_personal_best",
            "is_spot_member",
            "tackle",
            "photo_tags",
            "photo_size_tags",
            "gear_raw",
            "photos",
            "weather",
            "location",
            "comments",
            "raw_payload",
            "first_synced_at",
            "last_synced_at",
        ]
