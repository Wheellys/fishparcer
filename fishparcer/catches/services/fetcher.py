from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urljoin
from urllib.parse import urlparse

import requests

from fishparcer.catches.models import ApiSource
from fishparcer.catches.models import CatchRecord
from fishparcer.catches.models import SyncLog
from fishparcer.catches.services.parser import CatchParserService
from fishparcer.catches.services.photos import PhotoDownloadService

BASE_HEADERS = {
    "User-Agent": "PostmanRuntime/7.43.0",
    "Accept": "application/json, text/plain, */*",
}


class CatchFetchError(Exception):
    pass


class CatchFetchService:
    LIST_KEYS = (
        "data",
        "results",
        "items",
        "records",
        "catches",
        "list",
        "userCatches",
        "user_catches",
    )
    FISHULSE_API_URL = "https://fishulse.ru/api/user-catches"
    FISHULSE_ORIGIN = "https://fishulse.ru"

    def __init__(self, timeout: int = 60):
        self.timeout = timeout

    def fetch_items(self, url: str, headers: dict[str, str] | None = None) -> list[dict[str, Any]]:
        request_headers = self._prepare_headers(url, headers or {})
        response = self._get(url, request_headers)
        text = response.text.strip()

        if not text:
            raise CatchFetchError(
                f"Сервер вернул пустой ответ (HTTP {response.status_code}).",
            )

        payload = self._try_parse_payload(text)
        if payload is not None:
            return self.extract_items(payload)

        if self._looks_like_html(text):
            if self._is_fishulse_url(url):
                raise CatchFetchError(self._fishulse_auth_error())

            hint = ""
            api_urls = self._find_api_urls(text, url)
            if api_urls:
                hint = f" Найдены API-ссылки: {', '.join(api_urls[:3])}."
            raise CatchFetchError(
                "Сервер вернул HTML вместо JSON."
                f"{hint} "
                "Добавьте Cookie или токен авторизации, либо вставьте JSON из Postman.",
            )

        preview = text[:300].replace("\n", " ")
        raise CatchFetchError(f"Ответ не является JSON. Начало ответа: {preview}")

    def _prepare_headers(self, url: str, headers: dict[str, str]) -> dict[str, str]:
        prepared = {**BASE_HEADERS, **headers}
        if self._is_fishulse_url(url):
            prepared.update(
                {
                    "Accept": "application/json",
                    "Referer": f"{self.FISHULSE_ORIGIN}/",
                    "Origin": self.FISHULSE_ORIGIN,
                },
            )
        return prepared

    @classmethod
    def _is_fishulse_url(cls, url: str) -> bool:
        return "fishulse.ru" in url

    @classmethod
    def _fishulse_auth_error(cls) -> str:
        return (
            "Fishulse вернул HTML вместо JSON — нужна авторизация. "
            "Скопируйте Cookie из Postman (Headers → Cookie) или из браузера: "
            "F12 → Network → запрос user-catches → заголовок Cookie. "
            "Вставьте в поле «Cookie сессии» на форме."
        )

    def import_from_json(
        self,
        json_text: str,
        *,
        source_name: str = "",
        base_url: str = "",
        download_photos: bool = False,
    ) -> tuple[SyncLog, dict[str, dict[str, int]]]:
        try:
            payload = json.loads(json_text.strip())
        except json.JSONDecodeError as exc:
            raise CatchFetchError(f"Некорректный JSON: {exc}") from exc

        resolved_base = base_url or self.FISHULSE_ORIGIN
        is_fishulse = "fishulse.ru" in resolved_base if base_url else False
        if not base_url:
            resolved_base = "https://import.local"
        source, _ = ApiSource.objects.get_or_create(
            name=source_name or ("Fishulse" if is_fishulse else "JSON import"),
            defaults={
                "base_url": resolved_base,
                "fetch_url": self.FISHULSE_API_URL if is_fishulse else "",
            },
        )
        return self._import_items(
            self.extract_items(payload),
            source=source,
            download_photos=download_photos,
        )

    def import_from_url(
        self,
        url: str,
        *,
        source_name: str = "",
        download_photos: bool = False,
        headers: dict[str, str] | None = None,
    ) -> tuple[SyncLog, dict[str, dict[str, int]]]:
        items = self.fetch_items(url, headers=headers)
        source = self.resolve_source(url, source_name=source_name)
        return self._import_items(items, source=source, download_photos=download_photos)

    def _import_items(
        self,
        items: list[dict[str, Any]],
        *,
        source: ApiSource,
        download_photos: bool,
    ) -> tuple[SyncLog, dict[str, dict[str, int]]]:
        parser = CatchParserService(source=source)
        sync_log = parser.ingest_many(items)

        photo_stats: dict[str, dict[str, int]] = {}
        if download_photos and source.base_url and source.base_url not in {"https://import.local"}:
            photo_service = PhotoDownloadService(base_url=source.base_url)
            for catch in CatchRecord.objects.filter(source=source):
                photo_stats[catch.external_id] = photo_service.download_for_catch(catch)

        return sync_log, photo_stats

    def _get(self, url: str, headers: dict[str, str]) -> requests.Response:
        response = requests.get(
            url,
            headers=headers,
            timeout=self.timeout,
            allow_redirects=True,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise CatchFetchError(self._http_error_message(response)) from exc
        return response

    def _try_parse_payload(self, text: str) -> Any | None:
        stripped = text.lstrip("\ufeff")
        if not stripped.startswith(("[", "{")):
            return None
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return None

    def extract_items(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            items = self._filter_records(payload)
            if items:
                return items
            raise CatchFetchError("Получен пустой массив или записи без поля id.")

        if isinstance(payload, dict):
            for key in self.LIST_KEYS:
                value = payload.get(key)
                if isinstance(value, list):
                    items = self._filter_records(value)
                    if items:
                        return items

            props = payload.get("props")
            if isinstance(props, dict):
                page_props = props.get("pageProps")
                if isinstance(page_props, dict):
                    for key in self.LIST_KEYS:
                        value = page_props.get(key)
                        if isinstance(value, list):
                            items = self._filter_records(value)
                            if items:
                                return items

            if payload.get("id"):
                return [payload]

        raise CatchFetchError(
            "Не удалось найти список записей в JSON. "
            "Ожидается массив объектов с полем id.",
        )

    def resolve_source(self, url: str, source_name: str = "") -> ApiSource:
        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        name = source_name or ("Fishulse" if self._is_fishulse_url(url) else parsed.netloc)

        source, _ = ApiSource.objects.update_or_create(
            name=name,
            defaults={
                "base_url": base_url,
                "fetch_url": url,
            },
        )
        return source

    @staticmethod
    def build_headers(
        auth_token: str = "",
        session_cookie: str = "",
        extra_headers: str = "",
    ) -> dict[str, str]:
        headers: dict[str, str] = {}
        token = auth_token.strip()
        if token:
            headers["Authorization"] = token if token.lower().startswith("bearer ") else f"Bearer {token}"

        cookie = session_cookie.strip()
        if cookie:
            if cookie.lower().startswith("cookie:"):
                headers["Cookie"] = cookie.split(":", 1)[1].strip()
            else:
                headers["Cookie"] = cookie

        for line in extra_headers.splitlines():
            line = line.strip()
            if not line or ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip()
            if key.lower() == "cookie" and "Cookie" not in headers:
                headers["Cookie"] = value.strip()
            else:
                headers[key] = value.strip()
        return headers

    def _find_api_urls(self, html: str, page_url: str) -> list[str]:
        patterns = (
            r'["\'](/api/[^"\']+)["\']',
            r'["\'](https?://[^"\']+/api/[^"\']+)["\']',
        )
        found: list[str] = []
        seen: set[str] = set()

        for pattern in patterns:
            for match in re.finditer(pattern, html):
                raw_url = match.group(1)
                full_url = raw_url if raw_url.startswith("http") else urljoin(page_url, raw_url)
                if full_url not in seen:
                    seen.add(full_url)
                    found.append(full_url)
        return found

    @staticmethod
    def _looks_like_html(text: str) -> bool:
        stripped = text.lstrip().lower()
        return stripped.startswith("<!doctype html") or stripped.startswith("<html")

    @staticmethod
    def _http_error_message(response: requests.Response) -> str:
        preview = response.text[:200].replace("\n", " ").strip()
        if preview:
            return f"HTTP {response.status_code}: {preview}"
        return f"HTTP {response.status_code}: запрос отклонён сервером"

    @staticmethod
    def _filter_records(items: list[Any]) -> list[dict[str, Any]]:
        return [item for item in items if isinstance(item, dict) and item.get("id")]
