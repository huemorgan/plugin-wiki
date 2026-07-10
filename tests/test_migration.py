"""0.3.x → 0.4.0 migration: a DB created with the old single-wiki schema
(global-unique slug, no wiki_id anywhere) must come out of on_load with all
rows in the `main` wiki and the per-wiki unique index in place — twice
(idempotent), because every future upgrade re-runs the ladder."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import anyio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_OLD_SCHEMA = [
    """CREATE TABLE wiki_pages (
        id CHAR(32) PRIMARY KEY, mission_id CHAR(32),
        slug VARCHAR(256) NOT NULL, title VARCHAR(512) NOT NULL,
        summary TEXT NOT NULL, body TEXT NOT NULL,
        created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)""",
    "CREATE UNIQUE INDEX ix_wiki_pages_slug ON wiki_pages (slug)",
    """CREATE TABLE wiki_revisions (
        id CHAR(32) PRIMARY KEY, page_id CHAR(32) NOT NULL,
        body TEXT NOT NULL, note TEXT NOT NULL, created_at DATETIME NOT NULL)""",
    """CREATE TABLE wiki_citations (
        id CHAR(32) PRIMARY KEY, page_id CHAR(32) NOT NULL,
        url TEXT NOT NULL, note TEXT NOT NULL, created_at DATETIME NOT NULL)""",
    """CREATE TABLE wiki_open_questions (
        id CHAR(32) PRIMARY KEY, page_id CHAR(32),
        question TEXT NOT NULL, status VARCHAR(16) NOT NULL,
        created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)""",
    """CREATE TABLE wiki_links (
        id CHAR(32) PRIMARY KEY, from_page VARCHAR(256) NOT NULL,
        to_page VARCHAR(256) NOT NULL, kind VARCHAR(16) NOT NULL,
        created_at DATETIME NOT NULL)""",
]

_NOW = "2026-01-01 00:00:00"


class _Registry:
    def __init__(self):
        self.impls = {}

    def register(self, key, impl):
        self.impls[key] = impl

    def replace(self, key, impl):
        self.impls[key] = impl

    def has(self, key):
        return key in self.impls


class _Events:
    async def emit(self, *a, **kw):
        pass


class _Tools:
    def register(self, *a, **kw):
        pass


def test_migration_backfills_into_main_and_is_idempotent(tmp_path):
    from plugin_wiki import WikiPlugin
    from plugin_wiki.store import WikiStore

    async def scenario():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/old.db")
        async with engine.begin() as conn:
            for ddl in _OLD_SCHEMA:
                await conn.execute(text(ddl))
            pid = uuid.uuid4().hex
            await conn.execute(
                text(
                    "INSERT INTO wiki_pages (id, slug, title, summary, body, created_at, updated_at)"
                    f" VALUES ('{pid}', 'legacy', 'Legacy', 'old page', 'body [[other]]', '{_NOW}', '{_NOW}')"
                )
            )
            await conn.execute(
                text(
                    "INSERT INTO wiki_links (id, from_page, to_page, kind, created_at)"
                    f" VALUES ('{uuid.uuid4().hex}', 'legacy', 'other', 'wikilink', '{_NOW}')"
                )
            )
            await conn.execute(
                text(
                    "INSERT INTO wiki_open_questions (id, question, status, created_at, updated_at)"
                    f" VALUES ('{uuid.uuid4().hex}', 'old question?', 'open', '{_NOW}', '{_NOW}')"
                )
            )
        sf = async_sessionmaker(engine, expire_on_commit=False)
        ctx = SimpleNamespace(
            engine=engine,
            db_session_factory=sf,
            provider_registry=_Registry(),
            tool_registry=_Tools(),
            events=_Events(),
        )
        await WikiPlugin().on_load(ctx)
        await WikiPlugin().on_load(ctx)  # idempotent re-run (upgrade path)

        store = WikiStore(sf)
        wikis = await store.list_wikis()
        assert [w["slug"] for w in wikis] == ["main"]
        assert wikis[0]["page_count"] == 1
        page = await store.get_page("legacy")  # resolves inside main
        assert page["body"] == "body [[other]]"
        assert [l["to"] for l in await store.links()] == ["other"]
        assert len(await store.list_questions()) == 1
        # per-wiki slugs now coexist where the old schema forbade duplicates
        await store.create_wiki("second", "Second")
        await store.upsert_page("legacy", "Legacy (second)", "fresh", wiki="second")
        assert (await store.get_page("legacy", wiki="second"))["title"] == "Legacy (second)"
        assert (await store.get_page("legacy"))["title"] == "Legacy"
        await engine.dispose()

    anyio.run(scenario)
