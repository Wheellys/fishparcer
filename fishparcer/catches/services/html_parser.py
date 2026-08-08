from __future__ import annotations

import json
from typing import Any
from typing import Iterator

from bs4 import BeautifulSoup

RECORD_MARKERS = ("fishType", "fish_type", "reservoir", "reservoir_id", "biteStatus")
LIST_KEYS = ("data", "results", "items", "records", "catches", "list")
MAX_CANDIDATES = 50
MAX_SCAN_LENGTH = 500_000


class HtmlParseError(Exception):
    pass


def extract_payload_from_html(html: str) -> Any:
    if len(html) > MAX_SCAN_LENGTH:
        html = html[:MAX_SCAN_LENGTH]

    soup = BeautifulSoup(html, "html.parser")

    next_data = soup.find("script", id="__NEXT_DATA__")
    if next_data and next_data.string:
        data = json.loads(next_data.string)
        result = _find_catch_payload(data)
        if result is not None:
            return result

    for script in soup.find_all("script", type="application/json"):
        if not script.string:
            continue
        try:
            data = json.loads(script.string)
        except json.JSONDecodeError:
            continue
        result = _find_catch_payload(data)
        if result is not None:
            return result

    for tag in soup.find_all(["pre", "code"]):
        text = tag.get_text(strip=True)
        if not text.startswith(("[", "{")):
            continue
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue
        result = _find_catch_payload(data)
        if result is not None:
            return result

    candidates_seen = 0
    for script in soup.find_all("script"):
        content = script.string or ""
        if not content or len(content) < 2:
            continue
        for candidate in _iter_json_candidates(content):
            candidates_seen += 1
            if candidates_seen > MAX_CANDIDATES:
                break
            try:
                data = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            result = _find_catch_payload(data)
            if result is not None:
                return result
        if candidates_seen > MAX_CANDIDATES:
            break

    msg = (
        "Не удалось извлечь данные из HTML-страницы. "
        "Используйте прямую ссылку на API (как в Postman), а не URL страницы сайта."
    )
    raise HtmlParseError(msg)


def _find_catch_payload(data: Any, depth: int = 0) -> Any | None:
    if depth > 6:
        return None

    if isinstance(data, list):
        if _is_catch_record_list(data):
            return data
        for item in data[:20]:
            if isinstance(item, dict):
                found = _find_catch_payload(item, depth + 1)
                if found is not None:
                    return found
        return None

    if not isinstance(data, dict):
        return None

    if _is_catch_record(data):
        return data

    for key in LIST_KEYS:
        value = data.get(key)
        if isinstance(value, list) and _is_catch_record_list(value):
            return value

    page_props = data.get("pageProps")
    if isinstance(page_props, dict):
        found = _find_catch_payload(page_props, depth + 1)
        if found is not None:
            return found

    props = data.get("props")
    if isinstance(props, dict) and props is not data:
        found = _find_catch_payload(props, depth + 1)
        if found is not None:
            return found

    return None


def _is_catch_record(item: dict[str, Any]) -> bool:
    return bool(item.get("id")) and any(marker in item for marker in RECORD_MARKERS)


def _is_catch_record_list(items: list[Any]) -> bool:
    if not items or not isinstance(items[0], dict):
        return False
    return _is_catch_record(items[0])


def _iter_json_candidates(text: str) -> Iterator[str]:
    for opener, closer in (("[", "]"), ("{", "}")):
        index = 0
        limit = 0
        while index < len(text) and limit < MAX_CANDIDATES:
            start = text.find(opener, index)
            if start == -1:
                break
            end = _find_matching_bracket(text, start, opener, closer)
            if end != -1 and (end - start) < 500_000:
                yield text[start : end + 1]
                limit += 1
                index = end + 1
            else:
                index = start + 1


def _find_matching_bracket(text: str, start: int, opener: str, closer: str) -> int:
    depth = 0
    in_string = False
    escape = False

    for index in range(start, min(len(text), start + 500_000)):
        char = text[index]

        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue

        if char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return index

    return -1
