"""plugin-wiki — Luna's mission knowledge base (Karpathy-style LLM wiki).

The knowledge substrate: authored, revisable markdown pages with [[wikilinks]],
citations, and open questions, organized into isolated wikis (0.4.0). Knowledge
accumulates by compile-time synthesis (authored pages), not query-time RAG.
Behavior plugins (plugin-curiosity) consume it via the "wiki" provider.
Authored against `luna_sdk` only.
"""

from __future__ import annotations

import logging

from sqlalchemy import inspect as _sa_inspect
from sqlalchemy import text, update

from luna_sdk import LunaPlugin, PluginContext, PluginManifest, SidebarSection

from .injection import tier1_note, tier2_toc
from .models import ALL_TABLES, DEFAULT_WIKI, Wiki, WikiLink, WikiOpenQuestion, WikiPage
from .provider import WikiProvider
from .store import WikiStore
from .tools import register_tools

log = logging.getLogger("plugin-wiki")

_WIKI_ID_TABLES = ("wiki_pages", "wiki_links", "wiki_open_questions")


async def _migrate_multi_wiki(engine, session_factory) -> None:
    """Idempotent 0.3.x → 0.4.0 ladder: add wiki_id columns, retire the
    global-unique slug index for a per-wiki one, backfill rows into `main`.
    Fresh installs no-op (tables are created from the new models)."""

    def _columns(sync_conn, table: str) -> set[str]:
        return {c["name"] for c in _sa_inspect(sync_conn).get_columns(table)}

    async with engine.begin() as conn:
        coltype = "UUID" if conn.dialect.name == "postgresql" else "CHAR(32)"
        for table in _WIKI_ID_TABLES:
            cols = await conn.run_sync(lambda sc, t=table: _columns(sc, t))
            if "wiki_id" not in cols:
                await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN wiki_id {coltype}"))
                log.info("wiki migration: added %s.wiki_id", table)
        # slug uniqueness moves from global to (wiki_id, slug). The old
        # `unique=True, index=True` column emitted CREATE UNIQUE INDEX
        # ix_wiki_pages_slug on both dialects, so index surgery is portable.
        await conn.execute(text("DROP INDEX IF EXISTS ix_wiki_pages_slug"))
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_wiki_pages_slug ON wiki_pages (slug)")
        )
        await conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_wiki_pages_wiki_slug "
                "ON wiki_pages (wiki_id, slug)"
            )
        )
        for table in _WIKI_ID_TABLES:
            await conn.execute(
                text(f"CREATE INDEX IF NOT EXISTS ix_{table}_wiki_id ON {table} (wiki_id)")
            )

    async with session_factory() as s:
        from sqlalchemy import select

        main = (
            await s.execute(select(Wiki).where(Wiki.slug == DEFAULT_WIKI))
        ).scalar_one_or_none()
        if main is None:
            main = Wiki(slug=DEFAULT_WIKI, name="Main", description="")
            s.add(main)
            await s.flush()
        for model in (WikiPage, WikiLink, WikiOpenQuestion):
            await s.execute(
                update(model).where(model.wiki_id.is_(None)).values(wiki_id=main.id)
            )
        await s.commit()


class WikiPlugin(LunaPlugin):
    manifest = PluginManifest(
        name="plugin-wiki",
        shown_name="Wiki",
        icon="book-open",
        version="0.4.0",
        description=(
            "Mission knowledge base: isolated wikis of pages, revisions, "
            "citations, open questions."
        ),
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
        await _migrate_multi_wiki(ctx.engine, ctx.db_session_factory)
        self._store = WikiStore(ctx.db_session_factory)
        await self._store.ensure_default_wiki()

        async def _on_change(evt: dict) -> None:
            # live-update feed for the wiki pane (SSE /api/events?topics=wiki.*)
            await ctx.events.emit("wiki.updated", evt)

        self._store.on_change = _on_change
        register_tools(ctx, self._store)
        # Idempotent on purpose: core teardown (pre-provider-unregister
        # versions) leaves the old registration behind on upgrade, and
        # register() raises on duplicates — which rolled back every update.
        provider = WikiProvider(self._store)
        registry = ctx.provider_registry
        if getattr(registry, "has", None) and registry.has("wiki"):
            registry.replace("wiki", provider)
        else:
            registry.register("wiki", provider)
        log.info("plugin-wiki loaded (tools=12, tables=%d)", len(ALL_TABLES))

    async def prompt_sections(self) -> list[str]:
        """Tier 1 (thin note) + tier 2 (per-wiki TOC/summaries, budget-capped).
        Tier 3 (full bodies) only ever arrives via wiki_read tool results."""
        if self._store is None:
            return []
        wikis = await self._store.overview()
        page_count = sum(len(w.get("pages") or []) for w in wikis)
        open_qs = len(await self._store.list_questions(status="open", wiki=None))
        sections = [tier1_note(page_count, open_qs, wiki_count=len(wikis))]
        toc = tier2_toc(wikis)
        if toc:
            sections.append(toc)
        return sections
