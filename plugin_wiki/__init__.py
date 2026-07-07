"""plugin-wiki — Luna's mission knowledge base (Karpathy-style LLM wiki).

The knowledge substrate: authored, revisable markdown pages with [[wikilinks]],
citations, and open questions. Knowledge accumulates by compile-time synthesis
(authored pages), not query-time RAG. Behavior plugins (plugin-curiosity)
consume it via the "wiki" provider. Authored against `luna_sdk` only.
"""

from __future__ import annotations

import logging

from luna_sdk import LunaPlugin, PluginContext, PluginManifest, SidebarSection

from .injection import tier1_note, tier2_toc
from .models import ALL_TABLES
from .provider import WikiProvider
from .store import WikiStore
from .tools import register_tools

log = logging.getLogger("plugin-wiki")


class WikiPlugin(LunaPlugin):
    manifest = PluginManifest(
        name="plugin-wiki",
        shown_name="Wiki",
        icon="book-open",
        version="0.2.0",
        description="Mission knowledge base: wiki pages, revisions, citations, open questions.",
        category="global",
        license="MIT",
        provider="wiki",
        db_tables=[t.name for t in ALL_TABLES],
        routes_module="routes",
        sidebar_sections=[
            SidebarSection(id="wiki", label="Wiki", icon="book-open", sort_order=46),
        ],
    )

    def __init__(self) -> None:
        self._store: WikiStore | None = None

    async def on_load(self, ctx: PluginContext) -> None:
        async with ctx.engine.begin() as conn:
            for table in ALL_TABLES:
                await conn.run_sync(table.create, checkfirst=True)
        self._store = WikiStore(ctx.db_session_factory)
        register_tools(ctx, self._store)
        ctx.provider_registry.register("wiki", WikiProvider(self._store))
        log.info("plugin-wiki loaded (tools=9, tables=%d)", len(ALL_TABLES))

    async def prompt_sections(self) -> list[str]:
        """Tier 1 (thin note) + tier 2 (TOC/summaries, budget-capped).
        Tier 3 (full bodies) only ever arrives via wiki_read tool results."""
        if self._store is None:
            return []
        pages = await self._store.toc()
        open_qs = len(await self._store.list_questions(status="open"))
        sections = [tier1_note(len(pages), open_qs)]
        toc = tier2_toc(pages)
        if toc:
            sections.append(toc)
        return sections
