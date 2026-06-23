from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any

import requests


class NotionAPIError(RuntimeError):
    """Raised when the Notion API returns an error response."""


@dataclass(frozen=True)
class DataSourceInfo:
    id: str
    name: str


class NotionClient:
    base_url = "https://api.notion.com/v1"

    def __init__(self, token: str, notion_version: str = "2025-09-03") -> None:
        token = token.strip()
        if not token:
            raise ValueError("Notion API token이 필요합니다.")
        self._user_cache: dict[str, dict[str, Any]] = {}
        self._user_lookup_disabled = False
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Notion-Version": notion_version,
                "Content-Type": "application/json",
            }
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = self.session.request(
            method,
            f"{self.base_url}{path}",
            json=json,
            params=params,
            timeout=60,
        )
        if response.ok:
            return response.json()

        try:
            payload = response.json()
            message = payload.get("message") or payload
        except ValueError:
            message = response.text
        raise NotionAPIError(f"Notion API {response.status_code}: {message}")

    def retrieve_database(self, database_id: str) -> dict[str, Any]:
        return self.request("GET", f"/databases/{database_id}")

    def retrieve_data_source(self, data_source_id: str) -> dict[str, Any]:
        return self.request("GET", f"/data_sources/{data_source_id}")

    def list_data_sources(self, database_or_data_source_id: str) -> list[DataSourceInfo]:
        try:
            database = self.retrieve_database(database_or_data_source_id)
            data_sources = database.get("data_sources") or []
            if data_sources:
                database_title = _title_from_rich_text(database.get("title")) or "Data source"
                return [
                    DataSourceInfo(
                        id=item["id"],
                        name=item.get("name") or database_title,
                    )
                    for item in data_sources
                ]
        except NotionAPIError:
            pass

        data_source = self.retrieve_data_source(database_or_data_source_id)
        name = data_source.get("name") or _title_from_rich_text(data_source.get("title")) or "Data source"
        return [DataSourceInfo(id=data_source["id"], name=name)]

    def query_data_source(
        self,
        data_source_id: str,
        *,
        filter_payload: dict[str, Any] | None = None,
        page_size: int = 100,
        max_pages: int = 200,
    ) -> list[dict[str, Any]]:
        body: dict[str, Any] = {"page_size": min(page_size, 100)}
        if filter_payload:
            body["filter"] = filter_payload

        results: list[dict[str, Any]] = []
        next_cursor: str | None = None
        while True:
            if next_cursor:
                body["start_cursor"] = next_cursor
            elif "start_cursor" in body:
                del body["start_cursor"]

            payload = self.request("POST", f"/data_sources/{data_source_id}/query", json=body)
            results.extend(payload.get("results", []))
            if len(results) >= max_pages:
                return results[:max_pages]
            if not payload.get("has_more"):
                return results
            next_cursor = payload.get("next_cursor")
            if not next_cursor:
                return results

    def retrieve_page_markdown(self, page_id: str) -> dict[str, Any]:
        return self.request("GET", f"/pages/{page_id}/markdown")

    def retrieve_user(self, user_id: str) -> dict[str, Any]:
        return self.request("GET", f"/users/{user_id}")

    def hydrate_user_reference(self, user: dict[str, Any] | None) -> dict[str, Any]:
        if not user:
            return {}
        user_id = user.get("id")
        if not user_id or user.get("name") or self._user_lookup_disabled:
            return user
        if user_id in self._user_cache:
            return {**user, **self._user_cache[user_id]}

        try:
            full_user = self.retrieve_user(user_id)
        except NotionAPIError as exc:
            if "403" in str(exc):
                self._user_lookup_disabled = True
            self._user_cache[user_id] = user
            return user

        self._user_cache[user_id] = full_user
        return {**user, **full_user}

    def hydrate_comment_authors(self, comments: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for comment in comments:
            comment["created_by"] = self.hydrate_user_reference(comment.get("created_by"))
        return comments

    def list_block_children(self, block_id: str, *, page_size: int = 100) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        next_cursor: str | None = None
        while True:
            params: dict[str, Any] = {"page_size": min(page_size, 100)}
            if next_cursor:
                params["start_cursor"] = next_cursor
            payload = self.request("GET", f"/blocks/{block_id}/children", params=params)
            results.extend(payload.get("results", []))
            if not payload.get("has_more"):
                return results
            next_cursor = payload.get("next_cursor")
            if not next_cursor:
                return results

    def collect_descendant_block_ids(self, root_block_id: str, *, max_blocks: int = 300) -> list[str]:
        seen: list[str] = []
        queue: deque[str] = deque([root_block_id])

        while queue and len(seen) < max_blocks:
            current_id = queue.popleft()
            for child in self.list_block_children(current_id):
                child_id = child.get("id")
                if not child_id:
                    continue
                seen.append(child_id)
                if child.get("has_children") and len(seen) < max_blocks:
                    queue.append(child_id)
                if len(seen) >= max_blocks:
                    break
        return seen

    def list_comments(self, block_id: str, *, page_size: int = 100) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        next_cursor: str | None = None
        while True:
            params: dict[str, Any] = {"block_id": block_id, "page_size": min(page_size, 100)}
            if next_cursor:
                params["start_cursor"] = next_cursor
            payload = self.request("GET", "/comments", params=params)
            for comment in payload.get("results", []):
                comment["_source_block_id"] = block_id
                results.append(comment)
            if not payload.get("has_more"):
                return self.hydrate_comment_authors(results)
            next_cursor = payload.get("next_cursor")
            if not next_cursor:
                return self.hydrate_comment_authors(results)

    def list_page_comments(
        self,
        page_id: str,
        *,
        include_descendant_blocks: bool = True,
        max_blocks: int = 300,
    ) -> list[dict[str, Any]]:
        comments = self.list_comments(page_id)
        if include_descendant_blocks:
            for block_id in self.collect_descendant_block_ids(page_id, max_blocks=max_blocks):
                comments.extend(self.list_comments(block_id))

        deduped: dict[str, dict[str, Any]] = {}
        for comment in comments:
            comment_id = comment.get("id")
            if comment_id:
                deduped[comment_id] = comment
        return list(deduped.values())


def _title_from_rich_text(items: list[dict[str, Any]] | None) -> str:
    if not items:
        return ""
    return "".join(item.get("plain_text") or "" for item in items).strip()
