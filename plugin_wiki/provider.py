"""WikiProvider — the seam other plugins consume (registered under key
"wiki" in ctx.provider_registry). plugin-curiosity drives who writes and
when through this; no direct table access across plugins."""

from __future__ import annotations

from typing import Any

from .store import PageNotFound, WikiStore


class WikiProvider:
    def __init__(self, store: WikiStore) -> None:
        self._store = store

    async def get_page(self, slug: str) -> dict[str, Any] | None:
        try:
            return await self._store.get_page(slug)
        except PageNotFound:
            return None

    async def upsert_page(
        self, slug: str, title: str, body: str, summary: str = "", note: str = "", mission_id=None
    ) -> dict[str, Any]:
        return await self._store.upsert_page(
            slug, title, body, summary=summary, note=note, mission_id=mission_id
        )

    async def toc(self) -> list[dict[str, Any]]:
        return await self._store.toc()

    async def search(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        return await self._store.search(query, limit=limit)

    async def open_questions(self) -> list[dict[str, Any]]:
        return await self._store.list_questions(status="open")

    async def add_question(self, question: str, slug: str | None = None) -> dict[str, Any]:
        return await self._store.add_question(question, slug=slug)

    async def page_count(self) -> int:
        return await self._store.count_pages()
