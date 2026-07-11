"""Agent-facing wiki tools. Thin handlers over WikiStore. Writes touch only
plugin-owned tables, so all tools use the default auto_approve policy.

0.4.0: every tool takes an optional `wiki` (slug, default `main`); three new
tools let the agent create and navigate isolated wikis.
0.6.0: lifecycle tools — wiki_archive_page / wiki_unarchive_page (reversible,
hidden from toc/search/injection) and wiki_delete_page (hard delete).
0.7.0: `reason` accepted as an alias for `note` on wiki_write / wiki_patch."""

from __future__ import annotations

from typing import Any

from luna_sdk import PluginContext, ToolDef

from .models import DEFAULT_WIKI
from .store import PageNotFound, WikiNotFound, WikiStore

_WIKI_PARAM = {
    "type": "string",
    "description": "Wiki slug to operate in (see wiki_list_wikis). Omit for the main wiki.",
}


def register_tools(ctx: PluginContext, store: WikiStore) -> None:
    async def _no_such_wiki(wiki: str) -> dict[str, Any]:
        return {"error": f"no wiki '{wiki}'", "wikis": await store.list_wikis()}

    async def _list_wikis() -> dict[str, Any]:
        return {"wikis": await store.list_wikis()}

    async def _create_wiki(slug: str, name: str, description: str = "") -> dict[str, Any]:
        try:
            return await store.create_wiki(slug, name, description=description)
        except ValueError as e:
            return {"error": str(e), "wikis": await store.list_wikis()}

    async def _update_wiki(
        wiki: str, name: str | None = None, description: str | None = None
    ) -> dict[str, Any]:
        try:
            return await store.update_wiki(wiki, name=name, description=description)
        except WikiNotFound:
            return await _no_such_wiki(wiki)

    async def _toc(wiki: str = DEFAULT_WIKI, archived: bool = False) -> dict[str, Any]:
        try:
            return {"wiki": wiki, "pages": await store.toc(wiki=wiki, archived=archived)}
        except WikiNotFound:
            return await _no_such_wiki(wiki)

    async def _read(slug: str, wiki: str = DEFAULT_WIKI) -> dict[str, Any]:
        try:
            return await store.get_page(slug, wiki=wiki)
        except WikiNotFound:
            return await _no_such_wiki(wiki)
        except PageNotFound:
            return {
                "error": f"no page '{slug}' in wiki '{wiki}'",
                "pages": await store.toc(wiki=wiki),
            }

    async def _search(query: str, wiki: str = DEFAULT_WIKI) -> dict[str, Any]:
        try:
            return {"wiki": wiki, "results": await store.search(query, wiki=wiki)}
        except WikiNotFound:
            return await _no_such_wiki(wiki)

    async def _write(
        slug: str,
        title: str,
        body: str,
        summary: str = "",
        note: str = "",
        reason: str = "",
        wiki: str = DEFAULT_WIKI,
    ) -> dict[str, Any]:
        try:
            return await store.upsert_page(
                slug, title, body, summary=summary, note=note or reason, wiki=wiki
            )
        except WikiNotFound:
            return await _no_such_wiki(wiki)
        except ValueError as e:
            return {"error": str(e)}

    async def _patch(
        slug: str,
        find: str,
        replace: str,
        note: str = "",
        reason: str = "",
        wiki: str = DEFAULT_WIKI,
    ) -> dict[str, Any]:
        try:
            return await store.patch_page(slug, find, replace, note=note or reason, wiki=wiki)
        except WikiNotFound:
            return await _no_such_wiki(wiki)
        except PageNotFound:
            return {"error": f"no page '{slug}' in wiki '{wiki}'"}
        except ValueError as e:
            return {"error": str(e)}

    async def _archive(slug: str, wiki: str = DEFAULT_WIKI) -> dict[str, Any]:
        try:
            return await store.set_archived(slug, True, wiki=wiki)
        except WikiNotFound:
            return await _no_such_wiki(wiki)
        except PageNotFound:
            return {"error": f"no page '{slug}' in wiki '{wiki}'"}

    async def _unarchive(slug: str, wiki: str = DEFAULT_WIKI) -> dict[str, Any]:
        try:
            return await store.set_archived(slug, False, wiki=wiki)
        except WikiNotFound:
            return await _no_such_wiki(wiki)
        except PageNotFound:
            return {"error": f"no page '{slug}' in wiki '{wiki}'"}

    async def _delete(slug: str, wiki: str = DEFAULT_WIKI) -> dict[str, Any]:
        try:
            return await store.delete_page(slug, wiki=wiki)
        except WikiNotFound:
            return await _no_such_wiki(wiki)
        except PageNotFound:
            return {"error": f"no page '{slug}' in wiki '{wiki}'"}

    async def _cite(slug: str, url: str, note: str = "", wiki: str = DEFAULT_WIKI) -> dict[str, Any]:
        try:
            return await store.add_citation(slug, url, note=note, wiki=wiki)
        except WikiNotFound:
            return await _no_such_wiki(wiki)
        except PageNotFound:
            return {"error": f"no page '{slug}' in wiki '{wiki}'"}

    async def _ask(
        question: str, slug: str | None = None, wiki: str = DEFAULT_WIKI
    ) -> dict[str, Any]:
        try:
            return await store.add_question(question, slug=slug, wiki=wiki)
        except WikiNotFound:
            return await _no_such_wiki(wiki)

    async def _resolve(question_id: str) -> dict[str, Any]:
        try:
            return await store.resolve_question(question_id)
        except PageNotFound:
            return {"error": f"no open question '{question_id}'"}

    async def _questions(status: str = "open", wiki: str = DEFAULT_WIKI) -> dict[str, Any]:
        try:
            return {"wiki": wiki, "questions": await store.list_questions(status=status, wiki=wiki)}
        except WikiNotFound:
            return await _no_such_wiki(wiki)

    defs: list[tuple[ToolDef, Any]] = [
        (
            ToolDef(
                name="wiki_list_wikis",
                description=(
                    "List all wikis: slug, name, description, page count. Wikis are "
                    "isolated knowledge spaces (a mission, a client, a domain each "
                    "get their own). Start here when unsure where knowledge lives; "
                    "pass a wiki's slug as `wiki` to every other wiki_* tool."
                ),
                parameters={"type": "object", "properties": {}},
            ),
            _list_wikis,
        ),
        (
            ToolDef(
                name="wiki_create_wiki",
                description=(
                    "Create a new isolated wiki (e.g. for a new mission, client, or "
                    "domain). Pages, links, search, and questions never cross wiki "
                    "boundaries. Give it a clear name and a 1-2 sentence description "
                    "of what belongs inside."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "slug": {"type": "string", "description": "kebab-case wiki id, e.g. 'client-acme'"},
                        "name": {"type": "string"},
                        "description": {"type": "string", "description": "What this wiki covers (shown as its shelf label)."},
                    },
                    "required": ["slug", "name"],
                },
            ),
            _create_wiki,
        ),
        (
            ToolDef(
                name="wiki_update_wiki",
                description=(
                    "Rename a wiki or refresh its description. Keep descriptions "
                    "current — they are the shelf labels used to route future "
                    "knowledge to the right wiki."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "wiki": {"type": "string", "description": "Wiki slug to update."},
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                    },
                    "required": ["wiki"],
                },
            ),
            _update_wiki,
        ),
        (
            ToolDef(
                name="wiki_toc",
                description=(
                    "Table of contents of one wiki: every page's slug, title, and "
                    "summary. The map — start here before reading or writing. "
                    "Pass archived=true to list the archive instead."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "wiki": _WIKI_PARAM,
                        "archived": {
                            "type": "boolean",
                            "default": False,
                            "description": "List archived pages instead of live ones.",
                        },
                    },
                },
            ),
            _toc,
        ),
        (
            ToolDef(
                name="wiki_read",
                description="Read a wiki page's full markdown body plus citations and outgoing links.",
                parameters={
                    "type": "object",
                    "properties": {"slug": {"type": "string"}, "wiki": _WIKI_PARAM},
                    "required": ["slug"],
                },
            ),
            _read,
        ),
        (
            ToolDef(
                name="wiki_search",
                description=(
                    "Search one wiki's pages; returns relevance-ranked slugs + "
                    "summaries (use wiki_read for full bodies). Searches only the "
                    "given wiki — check wiki_list_wikis if unsure where to look."
                ),
                parameters={
                    "type": "object",
                    "properties": {"query": {"type": "string"}, "wiki": _WIKI_PARAM},
                    "required": ["query"],
                },
            ),
            _search,
        ),
        (
            ToolDef(
                name="wiki_write",
                description=(
                    "Create or fully replace a wiki page (markdown body). Link related "
                    "pages inline with [[slug]] wikilinks — they materialize the "
                    "knowledge graph automatically (links resolve inside the same "
                    "wiki only). Always provide a 1-2 sentence `summary`; it is what "
                    "gets injected into future context. Each write records a revision."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "slug": {"type": "string", "description": "kebab-case page id, e.g. 'competitors/acme'"},
                        "title": {"type": "string"},
                        "body": {"type": "string", "description": "Full markdown body with [[slug]] wikilinks."},
                        "summary": {"type": "string", "description": "1-2 sentence page summary (injected into context)."},
                        "note": {"type": "string", "description": "Short revision note (why this edit)."},
                        "reason": {"type": "string", "description": "Alias for `note`."},
                        "wiki": _WIKI_PARAM,
                    },
                    "required": ["slug", "title", "body"],
                },
            ),
            _write,
        ),
        (
            ToolDef(
                name="wiki_patch",
                description=(
                    "Edit part of a page: replace `find` (must occur exactly once in "
                    "the body) with `replace`. Records a revision and re-derives "
                    "[[slug]] links."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "slug": {"type": "string"},
                        "find": {"type": "string"},
                        "replace": {"type": "string"},
                        "note": {"type": "string", "description": "Short revision note (why this edit)."},
                        "reason": {"type": "string", "description": "Alias for `note`."},
                        "wiki": _WIKI_PARAM,
                    },
                    "required": ["slug", "find", "replace"],
                },
            ),
            _patch,
        ),
        (
            ToolDef(
                name="wiki_archive_page",
                description=(
                    "Archive a page: it disappears from the TOC, search, and your "
                    "injected context but keeps its body, revisions, and citations. "
                    "Reversible (wiki_unarchive_page; any wiki_write to the slug "
                    "also revives it). Default choice for stale or superseded "
                    "pages — prefer this over wiki_delete_page."
                ),
                parameters={
                    "type": "object",
                    "properties": {"slug": {"type": "string"}, "wiki": _WIKI_PARAM},
                    "required": ["slug"],
                },
            ),
            _archive,
        ),
        (
            ToolDef(
                name="wiki_unarchive_page",
                description="Restore an archived page to the live wiki (see wiki_toc with archived=true).",
                parameters={
                    "type": "object",
                    "properties": {"slug": {"type": "string"}, "wiki": _WIKI_PARAM},
                    "required": ["slug"],
                },
            ),
            _unarchive,
        ),
        (
            ToolDef(
                name="wiki_delete_page",
                description=(
                    "Permanently delete a page with its revision history and "
                    "citations. Irreversible — only for junk: empty stubs, "
                    "duplicates, pages migrated elsewhere. For anything with "
                    "real content, use wiki_archive_page instead."
                ),
                parameters={
                    "type": "object",
                    "properties": {"slug": {"type": "string"}, "wiki": _WIKI_PARAM},
                    "required": ["slug"],
                },
            ),
            _delete,
        ),
        (
            ToolDef(
                name="wiki_cite",
                description="Attach a source URL to a page (evidence for a claim).",
                parameters={
                    "type": "object",
                    "properties": {
                        "slug": {"type": "string"},
                        "url": {"type": "string"},
                        "note": {"type": "string"},
                        "wiki": _WIKI_PARAM,
                    },
                    "required": ["slug", "url"],
                },
            ),
            _cite,
        ),
        (
            ToolDef(
                name="wiki_ask",
                description="Record an open question — something you don't know yet and want to research later. Optionally tie it to a page.",
                parameters={
                    "type": "object",
                    "properties": {
                        "question": {"type": "string"},
                        "slug": {"type": "string", "description": "Related page slug (optional)."},
                        "wiki": _WIKI_PARAM,
                    },
                    "required": ["question"],
                },
            ),
            _ask,
        ),
        (
            ToolDef(
                name="wiki_resolve_question",
                description="Mark an open question resolved (after writing the answer into a page).",
                parameters={
                    "type": "object",
                    "properties": {"question_id": {"type": "string"}},
                    "required": ["question_id"],
                },
            ),
            _resolve,
        ),
        (
            ToolDef(
                name="wiki_list_questions",
                description="List open (or resolved) questions in one wiki.",
                parameters={
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "enum": ["open", "resolved"], "default": "open"},
                        "wiki": _WIKI_PARAM,
                    },
                },
            ),
            _questions,
        ),
    ]

    for tool_def, handler in defs:
        ctx.tool_registry.register("plugin-wiki", tool_def, handler)
