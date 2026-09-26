from __future__ import annotations

from typing import Any, Iterable
from urllib.parse import quote

import requests


GRAPH_ROOT = "https://graph.microsoft.com/v1.0"


class GraphClient:
    def __init__(self, access_token: str):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            }
        )

    def get(self, path_or_url: str, **params: Any) -> dict[str, Any]:
        url = path_or_url if path_or_url.startswith("https://") else f"{GRAPH_ROOT}{path_or_url}"
        response = self.session.get(url, params={key: value for key, value in params.items() if value is not None}, timeout=60)
        if response.status_code >= 400:
            raise RuntimeError(_format_graph_error(response))
        return response.json()

    def get_text(self, path_or_url: str, **params: Any) -> str:
        url = path_or_url if path_or_url.startswith("https://") else f"{GRAPH_ROOT}{path_or_url}"
        headers = {"Accept": "text/html"}
        response = self.session.get(url, params={key: value for key, value in params.items() if value is not None}, headers=headers, timeout=60)
        if response.status_code >= 400:
            raise RuntimeError(_format_graph_error(response))
        return response.text

    def get_bytes(self, path_or_url: str) -> bytes:
        url = path_or_url if path_or_url.startswith("https://") else f"{GRAPH_ROOT}{path_or_url}"
        response = self.session.get(url, timeout=120)
        if response.status_code >= 400:
            raise RuntimeError(_format_graph_error(response))
        return response.content

    def collection(self, path: str, *, limit: int | None = None, **params: Any) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        next_url: str | None = path

        while next_url:
            payload = self.get(next_url, **params if next_url == path else {})
            batch = payload.get("value", [])
            items.extend(batch)

            if limit is not None and len(items) >= limit:
                return items[:limit]

            next_url = payload.get("@odata.nextLink")

        return items

    def me(self) -> dict[str, Any]:
        return self.get("/me")

    def notebooks(self) -> list[dict[str, Any]]:
        return self.collection("/me/onenote/notebooks", **{"$top": 100})

    def sections(self) -> list[dict[str, Any]]:
        return self.collection("/me/onenote/sections", **{"$top": 100})

    def pages(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for section in self.sections():
            remaining = None if limit is None else max(limit - len(items), 0)
            if remaining == 0:
                break

            for page in self.pages_for_section(section["id"], limit=remaining):
                page["_section"] = {
                    "id": section.get("id"),
                    "displayName": section.get("displayName"),
                }
                items.append(page)

        return items

    def pages_for_section(self, section_id: str, *, limit: int | None = None) -> list[dict[str, Any]]:
        return self.collection(f"/me/onenote/sections/{quote(section_id, safe='')}/pages", limit=limit, **{"$top": 100})

    def page_content(self, page_id: str) -> str:
        return self.get_text(f"/me/onenote/pages/{quote(page_id, safe='')}/content")


def _format_graph_error(response: requests.Response) -> str:
    request_id = response.headers.get("request-id") or response.headers.get("client-request-id")
    try:
        details = response.json()
    except ValueError:
        details = response.text
    return f"Graph request failed: HTTP {response.status_code}; request-id={request_id}; details={details}"


def pick_fields(item: dict[str, Any], fields: Iterable[str]) -> dict[str, Any]:
    return {field: item.get(field) for field in fields if field in item}
