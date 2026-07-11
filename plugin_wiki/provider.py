"""WikiProvider — the seam other plugins consume (registered under key
"wiki" in ctx.provider_registry). plugin-curiosity drives who writes and
when through this; no direct table access across plugins.

0.4.0: every method takes `wiki` (slug, default `main`) — existing callers
keep working unmodified and land in the main wiki."""

from __future__ import annotations

from typing import Any

from .models import DEFAULT_WIKI
from .store import PageNotFound, WikiNotFound, WikiStore


class WikiProvider:
    def __init__(self, store: WikiStore) -> None:
        self._store = store

    # ── wikis ──────────────────────────────────────────────────────────

    async def list_wikis(self) -> list[dict[str, Any]]:
        return await self._store.list_wikis()

    async def create_wiki(self, slug: str, name: str, description: str = "") -> dict[str, Any]:
        return await self._store.create_wiki(slug, name, description=description)

    async def update_wiki(
        self, wiki: str, name: str | None = None, description: str | None = None
    ) -> dict[str, Any]:
        return await self._store.update_wiki(wiki, name=name, description=description)

    # ── pages ──────────────────────────────────────────────────────────

    async def get_page(self, slug: str, wiki: str = DEFAULT_WIKI) -> dict[str, Any] | None:
        try:
            return await self._store.get_page(slug, wiki=wiki)
        except (PageNotFound, WikiNotFound):
            return None

    async def upsert_page(
        self,
        slug: str,
        title: str,
        body: str,
        summary: str = "",
        note: str = "",
        mission_id=None,
        wiki: str = DEFAULT_WIKI,
    ) -> dict[str, Any]:
        return await self._store.upsert_page(
            slug, title, body, summary=summary, note=note, mission_id=mission_id, wiki=wiki
        )

    async def toc(self, wiki: str = DEFAULT_WIKI, archived: bool = False) -> list[dict[str, Any]]:
        return await self._store.toc(wiki=wiki, archived=archived)

    async def set_archived(
        self, slug: str, archived: bool, wiki: str = DEFAULT_WIKI
    ) -> dict[str, Any] | None:
        try:
            return await self._store.set_archived(slug, archived, wiki=wiki)
        except (PageNotFound, WikiNotFound):
            return None

    async def delete_page(self, slug: str, wiki: str = DEFAULT_WIKI) -> dict[str, Any] | None:
        try:
            return await self._store.delete_page(slug, wiki=wiki)
        except (PageNotFound, WikiNotFound):
            return None

    async def search(
        self, query: str, limit: int = 8, wiki: str = DEFAULT_WIKI
    ) -> list[dict[str, Any]]:
        return await self._store.search(query, limit=limit, wiki=wiki)

    async def open_questions(self, wiki: str = DEFAULT_WIKI) -> list[dict[str, Any]]:
        return await self._store.list_questions(status="open", wiki=wiki)

    async def add_question(
        self, question: str, slug: str | None = None, wiki: str = DEFAULT_WIKI
    ) -> dict[str, Any]:
        return await self._store.add_question(question, slug=slug, wiki=wiki)

    async def page_count(self, wiki: str | None = None) -> int:
        """Across all wikis by default (pre-0.4.0 behavior: one global wiki)."""
        return await self._store.count_pages(wiki=wiki)
