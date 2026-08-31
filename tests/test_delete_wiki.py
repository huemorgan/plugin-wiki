"""005 — wiki deletion exposure. DELETE /wikis/{wiki} (guard messages surface
as 400s; ?purge_pages=true empties the wiki first, archived pages included)
and the wiki_delete_wiki tool (ask policy, empty-only, no purge argument)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from plugin_wiki.models import WikiCitation, WikiLink, WikiPage, WikiRevision


# ── route ─────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def client(store):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from plugin_wiki.routes import register_routes

    app = FastAPI()
    register_routes(app, SimpleNamespace(db_session_factory=store._sf))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


async def _count(store, model) -> int:
    async with store._sf() as s:
        return (await s.execute(select(func.count(model.id)))).scalar_one()


@pytest.mark.asyncio
async def test_route_deletes_empty_wiki(store, client):
    await store.create_wiki("scratch", "Scratch")
    r = await client.delete("/api/p/plugin-wiki/wikis/scratch")
    assert r.status_code == 200
    assert r.json() == {"deleted": "scratch"}
    assert "scratch" not in {w["slug"] for w in await store.list_wikis()}


@pytest.mark.asyncio
async def test_route_refuses_main(store, client):
    await store.ensure_default_wiki()
    for url in ("/api/p/plugin-wiki/wikis/main",
                "/api/p/plugin-wiki/wikis/main?purge_pages=true"):
        r = await client.delete(url)
        assert r.status_code == 400
        assert "main wiki cannot be deleted" in r.json()["detail"]


@pytest.mark.asyncio
async def test_route_refuses_nonempty_without_flag(store, client):
    await store.create_wiki("scratch", "Scratch")
    await store.upsert_page("keep", "Keep", "body", wiki="scratch")
    r = await client.delete("/api/p/plugin-wiki/wikis/scratch")
    assert r.status_code == 400
    assert "still has 1 pages" in r.json()["detail"]
    assert "scratch" in {w["slug"] for w in await store.list_wikis()}


@pytest.mark.asyncio
async def test_route_404_on_unknown_wiki(client):
    r = await client.delete("/api/p/plugin-wiki/wikis/nope")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_purge_pages_deletes_pages_then_wiki(store, client):
    await store.ensure_default_wiki()
    await store.upsert_page("home", "Home", "main survives", summary="s")
    await store.create_wiki("junk", "Junk")
    await store.upsert_page("a", "A", "links to [[b]] and [[stub]]", wiki="junk")
    await store.upsert_page("b", "B", "plain", wiki="junk")
    await store.add_citation("a", "https://example.com", wiki="junk")
    await store.upsert_page("old", "Old", "archived page", wiki="junk")
    await store.set_archived("old", True, wiki="junk")

    r = await client.delete("/api/p/plugin-wiki/wikis/junk?purge_pages=true")
    assert r.status_code == 200
    assert r.json() == {"deleted": "junk"}
    assert "junk" not in {w["slug"] for w in await store.list_wikis()}

    # graph/toc report the wiki gone rather than half-alive
    assert (await client.get("/api/p/plugin-wiki/graph?wiki=junk")).status_code == 404
    assert (await client.get("/api/p/plugin-wiki/pages?wiki=junk")).status_code == 404

    # no dangling rows: only main's single page (and its data) remain
    assert await _count(store, WikiPage) == 1
    assert await _count(store, WikiLink) == 0
    assert await _count(store, WikiRevision) == 1
    assert await _count(store, WikiCitation) == 0
    graph = (await client.get("/api/p/plugin-wiki/graph")).json()
    assert {n["id"] for n in graph["nodes"]} == {"home"}
    assert graph["edges"] == []


# ── tool ──────────────────────────────────────────────────────────────


class _ToolReg:
    def __init__(self):
        self.defs = {}
        self.handlers = {}

    def register(self, _plugin, tool_def, handler, **_kw):
        self.defs[tool_def.name] = tool_def
        self.handlers[tool_def.name] = handler


def _register(store=None):
    from plugin_wiki.tools import register_tools

    reg = _ToolReg()
    register_tools(SimpleNamespace(tool_registry=reg), store or SimpleNamespace())
    return reg


def test_tool_registered_with_ask_policy():
    reg = _register()
    td = reg.defs["wiki_delete_wiki"]
    assert td.policy == "ask"
    assert td.risk_level == "high"
    assert list(td.parameters["properties"]) == ["wiki"]  # no purge argument
    assert td.parameters["required"] == ["wiki"]


@pytest.mark.asyncio
async def test_tool_refuses_main_and_nonempty(store):
    handler = _register(store).handlers["wiki_delete_wiki"]
    assert "main wiki cannot be deleted" in (await handler("main"))["error"]
    await store.create_wiki("junk", "Junk")
    await store.upsert_page("a", "A", "body", wiki="junk")
    assert "still has 1 pages" in (await handler("junk"))["error"]
    await store.upsert_page("old", "Old", "b", wiki="junk")
    await store.set_archived("old", True, wiki="junk")
    assert "still has 2 pages" in (await handler("junk"))["error"]  # archived count too


@pytest.mark.asyncio
async def test_tool_deletes_empty_wiki_and_handles_unknown(store):
    handler = _register(store).handlers["wiki_delete_wiki"]
    await store.create_wiki("junk", "Junk")
    assert await handler("junk") == {"deleted": "junk"}
    assert "junk" not in {w["slug"] for w in await store.list_wikis()}
    assert "no wiki 'gone'" in (await handler("gone"))["error"]
