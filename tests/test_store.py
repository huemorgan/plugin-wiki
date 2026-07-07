"""WikiStore behavior: markdown round-trip, revisions, wikilink graph
materialization, search ranking, questions — the phase-1 acceptance criteria
that don't need a live Luna."""

from __future__ import annotations

import pytest

from plugin_wiki.store import PageNotFound, parse_wikilinks, slugify

# ── slug/link parsing (pure) ──────────────────────────────────────────


def test_slugify_normalizes():
    assert slugify("Hello World") == "hello-world"
    assert slugify("Competitors/Acme Corp") == "competitors/acme-corp"
    assert slugify("  já--weird__chars!  ") == "j-weird-chars"


def test_parse_wikilinks_dedupes_and_supports_aliases():
    body = "See [[Acme Corp]] and [[acme-corp|the rival]] plus [[pricing#tiers]]."
    assert parse_wikilinks(body) == ["acme-corp", "pricing"]


# ── round-trip + revisions ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_write_read_roundtrip_verbatim(store):
    body = "# Acme\n\nMarkdown **round-trip** with `code` and\n\n- lists\n- [[pricing]]\n"
    await store.upsert_page("Acme Corp", "Acme", body, summary="Rival vendor.")
    page = await store.get_page("acme-corp")
    assert page["body"] == body
    assert page["title"] == "Acme"
    assert page["summary"] == "Rival vendor."
    assert page["revision_count"] == 1


@pytest.mark.asyncio
async def test_edit_creates_revision(store):
    await store.upsert_page("acme", "Acme", "v1")
    await store.upsert_page("acme", "Acme", "v2", note="rewrite")
    page = await store.get_page("acme")
    assert page["body"] == "v2"
    assert page["revision_count"] == 2
    revs = await store.revisions("acme")
    assert [r["note"] for r in revs] == ["", "rewrite"]


@pytest.mark.asyncio
async def test_patch_requires_unique_find(store):
    await store.upsert_page("acme", "Acme", "alpha beta alpha")
    with pytest.raises(ValueError, match="2 times"):
        await store.patch_page("acme", "alpha", "gamma")
    result = await store.patch_page("acme", "beta", "delta")
    assert (await store.get_page("acme"))["body"] == "alpha delta alpha"
    assert result["slug"] == "acme"
    assert (await store.get_page("acme"))["revision_count"] == 2


@pytest.mark.asyncio
async def test_read_missing_page_raises(store):
    with pytest.raises(PageNotFound):
        await store.get_page("nope")


# ── wikilink graph materialization ────────────────────────────────────


@pytest.mark.asyncio
async def test_wikilinks_materialize_edges(store):
    await store.upsert_page("acme", "Acme", "Competes with [[globex]] on [[pricing]].")
    links = await store.links()
    assert {(l["from"], l["to"]) for l in links} == {("acme", "globex"), ("acme", "pricing")}


@pytest.mark.asyncio
async def test_editing_body_updates_edge_set(store):
    await store.upsert_page("acme", "Acme", "See [[globex]] and [[pricing]].")
    await store.upsert_page("acme", "Acme", "Now only [[globex]] and [[initech]].")
    links = await store.links()
    assert {l["to"] for l in links if l["kind"] == "wikilink"} == {"globex", "initech"}


@pytest.mark.asyncio
async def test_citation_is_second_edge_kind(store):
    await store.upsert_page("acme", "Acme", "body")
    await store.add_citation("acme", "https://example.com/report", note="2026 report")
    page = await store.get_page("acme")
    assert page["citations"] == [{"url": "https://example.com/report", "note": "2026 report"}]
    kinds = {l["kind"] for l in await store.links()}
    assert "citation" in kinds
    # citation edges survive body rewrites (only wikilink edges are re-derived)
    await store.upsert_page("acme", "Acme", "new body, no links")
    assert "citation" in {l["kind"] for l in await store.links()}


# ── search / toc / questions ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_ranks_title_over_body(store):
    await store.upsert_page("pricing", "Pricing strategy", "about money")
    await store.upsert_page("acme", "Acme", "they changed their pricing last year")
    results = await store.search("pricing")
    assert [r["slug"] for r in results] == ["pricing", "acme"]


@pytest.mark.asyncio
async def test_toc_lists_meta_only(store):
    await store.upsert_page("a", "A", "body a", summary="sum a")
    toc = await store.toc()
    assert toc[0]["slug"] == "a"
    assert "body" not in toc[0]


@pytest.mark.asyncio
async def test_questions_lifecycle(store):
    await store.upsert_page("acme", "Acme", "body")
    q = await store.add_question("Who funds Acme?", slug="acme")
    assert (await store.list_questions())[0]["page"] == "acme"
    await store.resolve_question(q["id"])
    assert await store.list_questions(status="open") == []
    assert len(await store.list_questions(status="resolved")) == 1
