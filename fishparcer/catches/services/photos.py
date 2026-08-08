from __future__ import annotations

import mimetypes
from pathlib import Path
from urllib.parse import urljoin

import requests
from django.core.files.base import ContentFile

from fishparcer.catches.models import CatchPhoto
from fishparcer.catches.models import CatchRecord


class PhotoDownloadService:
    def __init__(self, base_url: str = "", timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def download_for_catch(self, catch: CatchRecord) -> dict[str, int]:
        stats = {"downloaded": 0, "failed": 0, "skipped": 0}
        for photo in catch.photos.filter(download_status__in=[
            CatchPhoto.DownloadStatus.PENDING,
            CatchPhoto.DownloadStatus.FAILED,
        ]):
            result = self.download_photo(photo)
            stats[result] += 1
        return stats

    def download_photo(self, photo: CatchPhoto) -> str:
        if photo.download_status == CatchPhoto.DownloadStatus.DOWNLOADED and photo.local_file:
            return "skipped"

        url = photo.original_url or self._build_url(photo.original_path)
        if not url:
            photo.download_status = CatchPhoto.DownloadStatus.FAILED
            photo.save(update_fields=["download_status"])
            return "failed"

        try:
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException:
            photo.download_status = CatchPhoto.DownloadStatus.FAILED
            photo.save(update_fields=["download_status"])
            return "failed"

        filename = Path(photo.original_path).name or f"{photo.catch.external_id}-{photo.sort_order}.jpg"
        content_type = response.headers.get("Content-Type", "")
        photo.local_file.save(filename, ContentFile(response.content), save=False)
        from django.utils import timezone

        photo.download_status = CatchPhoto.DownloadStatus.DOWNLOADED
        photo.downloaded_at = timezone.now()
        photo.file_size = len(response.content)
        photo.content_type = content_type or mimetypes.guess_type(filename)[0] or ""
        photo.original_url = url
        photo.save()
        return "downloaded"

    def _build_url(self, path: str) -> str:
        if path.startswith(("http://", "https://")):
            return path
        if self.base_url:
            return urljoin(f"{self.base_url}/", path.lstrip("/"))
        return ""
