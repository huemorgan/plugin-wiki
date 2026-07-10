"""WikiStore behavior: markdown round-trip, revisions, wikilink graph
materialization, search ranking, questions — the phase-1 acceptance criteria
that don't need a live Luna."""

from __future__ import annotations

import pytest

from plugin_wiki.store import PageNotFound, WikiNotFound, parse_wikilinks, slugify

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


# ── multi-wiki isolation (0.4.0) ──────────────────────────────────────


@pytest.mark.asyncio
async def test_default_wiki_self_heals(store):
    wikis = await store.list_wikis()
    assert [w["slug"] for w in wikis] == ["main"]
    assert wikis[0]["page_count"] == 0


@pytest.mark.asyncio
async def test_wiki_crud(store):
    w = await store.create_wiki("Client Acme", "Client: Acme", description="Acme engagement.")
    assert w["slug"] == "client-acme"
    with pytest.raises(ValueError, match="already exists"):
        await store.create_wiki("client-acme", "dup")
    updated = await store.update_wiki("client-acme", description="Refreshed by the dream.")
    assert updated["description"] == "Refreshed by the dream."
    assert updated["name"] == "Client: Acme"  # untouched
    slugs = {x["slug"] for x in await store.list_wikis()}
    assert slugs == {"main", "client-acme"}


@pytest.mark.asyncio
async def test_unknown_wiki_raises(store):
    with pytest.raises(WikiNotFound):
        await store.toc(wiki="nope")
    with pytest.raises(WikiNotFound):
        await store.upsert_page("a", "A", "body", wiki="nope")


@pytest.mark.asyncio
async def test_same_slug_is_independent_across_wikis(store):
    await store.create_wiki("other", "Other")
    await store.upsert_page("acme", "Acme (main)", "main body [[pricing]]")
    await store.upsert_page("acme", "Acme (other)", "other body", wiki="other")

    main = await store.get_page("acme")
    other = await store.get_page("acme", wiki="other")
    assert main["title"] == "Acme (main)" and other["title"] == "Acme (other)"

    # edits don't leak
    await store.patch_page("acme", "other body", "patched", wiki="other")
    assert (await store.get_page("acme"))["body"] == "main body [[pricing]]"
    assert (await store.get_page("acme", wiki="other"))["revision_count"] == 2
    assert (await store.get_page("acme"))["revision_count"] == 1


@pytest.mark.asyncio
async def test_toc_search_links_questions_are_scoped(store):
    await store.create_wiki("other", "Other")
    await store.upsert_page("pricing", "Pricing", "money [[acme]]")
    await store.upsert_page("islands", "Islands", "pricing of islands", wiki="other")
    await store.add_question("main q", wiki="main")
    await store.add_question("other q", wiki="other")

    assert [p["slug"] for p in await store.toc()] == ["pricing"]
    assert [p["slug"] for p in await store.toc(wiki="other")] == ["islands"]
    assert [r["slug"] for r in await store.search("pricing")] == ["pricing"]
    assert [r["slug"] for r in await store.search("pricing", wiki="other")] == ["islands"]
    assert {(l["from"], l["to"]) for l in await store.links()} == {("pricing", "acme")}
    assert await store.links(wiki="other") == []
    assert [q["question"] for q in await store.list_questions(wiki="other")] == ["other q"]
    assert len(await store.list_questions(wiki=None)) == 2
    assert await store.count_pages() == 2
    assert await store.count_pages(wiki="other") == 1


@pytest.mark.asyncio
async def test_reparse_only_touches_own_wiki_edges(store):
    await store.create_wiki("other", "Other")
    await store.upsert_page("acme", "Acme", "[[globex]]")
    await store.upsert_page("acme", "Acme", "[[initech]]", wiki="other")
    await store.upsert_page("acme", "Acme", "no links now", wiki="other")
    assert {l["to"] for l in await store.links()} == {"globex"}
    assert await store.links(wiki="other") == []


@pytest.mark.asyncio
async def test_delete_wiki_guards(store):
    await store.create_wiki("temp", "Temp")
    await store.upsert_page("a", "A", "body", wiki="temp")
    with pytest.raises(ValueError, match="main wiki cannot be deleted"):
        await store.delete_wiki("main")
    with pytest.raises(ValueError, match="still has 1 pages"):
        await store.delete_wiki("temp")
    # page removal not implemented — recreate empty wiki path instead
    await store.create_wiki("empty", "Empty")
    assert (await store.delete_wiki("empty"))["deleted"] == "empty"
    assert "empty" not in {w["slug"] for w in await store.list_wikis()}


@pytest.mark.asyncio
async def test_change_events_carry_wiki(store):
    seen = []

    async def on_change(evt):
        seen.append(evt)

    store.on_change = on_change
    await store.create_wiki("other", "Other")
    await store.upsert_page("acme", "Acme", "body", wiki="other")
    assert {"action": "wiki_create", "slug": None, "wiki": "other"} in seen
    assert {"action": "write", "slug": "acme", "wiki": "other"} in seen


@pytest.mark.asyncio
async def test_overview_groups_pages_by_wiki(store):
    await store.create_wiki("other", "Other", description="side quests")
    await store.upsert_page("a", "A", "body")
    await store.upsert_page("b", "B", "body", wiki="other")
    ov = {w["slug"]: w for w in await store.overview()}
    assert [p["slug"] for p in ov["main"]["pages"]] == ["a"]
    assert [p["slug"] for p in ov["other"]["pages"]] == ["b"]
    assert ov["other"]["description"] == "side quests"
