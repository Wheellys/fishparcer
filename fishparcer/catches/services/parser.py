from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils.dateparse import parse_date, parse_datetime

from fishparcer.catches.models import ApiSource
from fishparcer.catches.models import CatchComment
from fishparcer.catches.models import CatchLocation
from fishparcer.catches.models import CatchPhoto
from fishparcer.catches.models import CatchRecord
from fishparcer.catches.models import CatchTag
from fishparcer.catches.models import CatchWeather
from fishparcer.catches.models import Reservoir
from fishparcer.catches.models import SourceUser
from fishparcer.catches.models import SyncLog


class CatchParserService:
    def __init__(self, source: ApiSource | None = None):
        self.source = source

    @transaction.atomic
    def ingest(self, data: dict[str, Any]) -> tuple[CatchRecord, bool]:
        external_id = data["id"]
        content_hash = CatchRecord.compute_content_hash(data)

        existing = CatchRecord.objects.filter(external_id=external_id).first()
        if existing and existing.content_hash == content_hash:
            return existing, False

        user = self._upsert_user(data.get("user") or {})
        reservoir = self._upsert_reservoir(data)

        defaults = {
            "source": self.source,
            "raw_payload": data,
            "user": user,
            "reservoir": reservoir,
            "reservoir_name": data.get("reservoir", ""),
            "region": data.get("region", ""),
            "country": data.get("country", ""),
            "fish_type": data.get("fishType", ""),
            "weight": data.get("weight", 0) or 0,
            "bite_status": data.get("biteStatus", ""),
            "time_of_day": data.get("timeOfDay", ""),
            "tackle": data.get("tackle") or {},
            "bites": data.get("bites", 0) or 0,
            "caught": data.get("caught", 0) or 0,
            "quote": data.get("quote", ""),
            "created_at_external": self._parse_datetime(data.get("createdAt")),
            "likes": data.get("likes", 0) or 0,
            "comments_count": data.get("comments", 0) or 0,
            "total_comments": data.get("totalComments", 0) or 0,
            "is_personal_best": bool(data.get("isPersonalBest", False)),
            "time_start": data.get("timeStart", ""),
            "time_end": data.get("timeEnd", ""),
            "fishing_style": data.get("fishingStyle", ""),
            "fishing_date": self._parse_date(data.get("fishingDate")),
            "photo_tags": data.get("photoTags") or {},
            "photo_size_tags": data.get("photoSizeTags") or {},
            "is_spot_member": bool(data.get("_isSpotMember", False)),
            "gear_raw": data.get("gear") or [],
            "content_hash": content_hash,
        }

        catch, created = CatchRecord.objects.update_or_create(
            external_id=external_id,
            defaults=defaults,
        )

        self._sync_tags(catch, data.get("tags") or [])
        self._sync_weather(catch, data.get("weather") or {})
        self._sync_location(catch, data.get("location") or {})
        self._sync_photos(catch, data)
        self._sync_comments(catch, data.get("commentsData") or [])

        return catch, created

    def ingest_many(self, items: list[dict[str, Any]]) -> SyncLog:
        sync_log = SyncLog.objects.create(source=self.source, status=SyncLog.Status.RUNNING)
        created_count = 0
        updated_count = 0

        try:
            for item in items:
                _, created = self.ingest(item)
                if created:
                    created_count += 1
                else:
                    updated_count += 1

            sync_log.records_fetched = len(items)
            sync_log.records_created = created_count
            sync_log.records_updated = updated_count
            sync_log.status = SyncLog.Status.SUCCESS
        except Exception as exc:
            sync_log.status = SyncLog.Status.FAILED
            sync_log.error_message = str(exc)
            raise
        finally:
            from django.utils import timezone

            sync_log.finished_at = timezone.now()
            sync_log.save()

        return sync_log

    def _upsert_user(self, user_data: dict[str, Any]) -> SourceUser | None:
        external_id = user_data.get("id")
        if not external_id:
            return None

        user, _ = SourceUser.objects.update_or_create(
            external_id=external_id,
            defaults={
                "name": user_data.get("name", ""),
                "initials": user_data.get("initials", ""),
                "avatar_bg": user_data.get("avatarBg", ""),
                "raw_payload": user_data,
            },
        )
        return user

    def _upsert_reservoir(self, data: dict[str, Any]) -> Reservoir | None:
        external_id = data.get("reservoir_id")
        if not external_id:
            return None

        reservoir, _ = Reservoir.objects.update_or_create(
            external_id=external_id,
            defaults={
                "name": data.get("reservoir", ""),
                "region": data.get("region", ""),
                "country": data.get("country", ""),
                "raw_payload": {
                    "reservoir_id": external_id,
                    "reservoir": data.get("reservoir", ""),
                    "region": data.get("region", ""),
                    "country": data.get("country", ""),
                },
            },
        )
        return reservoir

    def _sync_tags(self, catch: CatchRecord, tags: list[str]) -> None:
        tag_objects = []
        for tag_name in tags:
            if not tag_name:
                continue
            tag, _ = CatchTag.objects.get_or_create(name=tag_name)
            tag_objects.append(tag)
        catch.tags.set(tag_objects)

    def _sync_weather(self, catch: CatchRecord, weather_data: dict[str, Any]) -> None:
        if not weather_data:
            CatchWeather.objects.filter(catch=catch).delete()
            return

        CatchWeather.objects.update_or_create(
            catch=catch,
            defaults={
                "temp": weather_data.get("temp"),
                "pressure": weather_data.get("pressure"),
                "humidity": weather_data.get("humidity"),
                "wind_speed": weather_data.get("windSpeed"),
                "wind_dir": weather_data.get("windDir", ""),
                "cloud_cover": weather_data.get("cloudCover"),
                "precipitation": weather_data.get("precipitation"),
                "condition": weather_data.get("condition", ""),
                "moon_phase": weather_data.get("moonPhase"),
                "moon_phase_label": weather_data.get("moonPhaseLabel", ""),
                "raw_payload": weather_data,
            },
        )

    def _sync_location(self, catch: CatchRecord, location_data: dict[str, Any]) -> None:
        if not location_data:
            CatchLocation.objects.filter(catch=catch).delete()
            return

        CatchLocation.objects.update_or_create(
            catch=catch,
            defaults={
                "mode": location_data.get("mode", ""),
                "display_text": location_data.get("displayText", ""),
                "lat": location_data.get("lat"),
                "lng": location_data.get("lng"),
                "raw_payload": location_data,
            },
        )

    def _sync_photos(self, catch: CatchRecord, data: dict[str, Any]) -> None:
        primary_path = data.get("photo", "")
        photo_paths: list[str] = data.get("photos") or []
        if primary_path and primary_path not in photo_paths:
            photo_paths.insert(0, primary_path)

        seen_paths: set[str] = set()
        for index, path in enumerate(photo_paths):
            if not path or path in seen_paths:
                continue
            seen_paths.add(path)
            CatchPhoto.objects.update_or_create(
                catch=catch,
                original_path=path,
                defaults={
                    "sort_order": index,
                    "is_primary": path == primary_path,
                },
            )

        CatchPhoto.objects.filter(catch=catch).exclude(original_path__in=seen_paths).delete()

    def _sync_comments(self, catch: CatchRecord, comments_data: list[dict[str, Any]]) -> None:
        seen_ids: set[str] = set()
        for comment_data in comments_data:
            external_id = comment_data.get("id", "")
            if external_id:
                seen_ids.add(external_id)
                CatchComment.objects.update_or_create(
                    catch=catch,
                    external_id=external_id,
                    defaults={
                        "raw_payload": comment_data,
                        "created_at_external": self._parse_datetime(comment_data.get("createdAt")),
                    },
                )
            else:
                CatchComment.objects.create(
                    catch=catch,
                    raw_payload=comment_data,
                    created_at_external=self._parse_datetime(comment_data.get("createdAt")),
                )

        if seen_ids:
            CatchComment.objects.filter(catch=catch).exclude(external_id__in=seen_ids).delete()

    @staticmethod
    def _parse_datetime(value: str | None) -> datetime | None:
        if not value:
            return None
        parsed = parse_datetime(value)
        if parsed and parsed.tzinfo is None:
            from django.utils import timezone

            return timezone.make_aware(parsed)
        return parsed

    @staticmethod
    def _parse_date(value: str | None):
        if not value:
            return None
        return parse_date(value)
