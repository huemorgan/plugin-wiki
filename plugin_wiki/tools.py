"""Agent-facing wiki tools. Thin handlers over WikiStore. Writes touch only
plugin-owned tables, so all tools use the default auto_approve policy."""

from __future__ import annotations

from typing import Any

from luna_sdk import PluginContext, ToolDef

from .store import PageNotFound, WikiStore


def register_tools(ctx: PluginContext, store: WikiStore) -> None:
    async def _toc() -> dict[str, Any]:
        return {"pages": await store.toc()}

    async def _read(slug: str) -> dict[str, Any]:
        try:
            return await store.get_page(slug)
        except PageNotFound:
            return {"error": f"no wiki page '{slug}'", "pages": await store.toc()}

    async def _search(query: str) -> dict[str, Any]:
        return {"results": await store.search(query)}

    async def _write(
        slug: str, title: str, body: str, summary: str = "", note: str = ""
    ) -> dict[str, Any]:
        try:
            return await store.upsert_page(slug, title, body, summary=summary, note=note)
        except ValueError as e:
            return {"error": str(e)}

    async def _patch(slug: str, find: str, replace: str, note: str = "") -> dict[str, Any]:
        try:
            return await store.patch_page(slug, find, replace, note=note)
        except PageNotFound:
            return {"error": f"no wiki page '{slug}'"}
        except ValueError as e:
            return {"error": str(e)}

    async def _cite(slug: str, url: str, note: str = "") -> dict[str, Any]:
        try:
            return await store.add_citation(slug, url, note=note)
        except PageNotFound:
            return {"error": f"no wiki page '{slug}'"}

    async def _ask(question: str, slug: str | None = None) -> dict[str, Any]:
        return await store.add_question(question, slug=slug)

    async def _resolve(question_id: str) -> dict[str, Any]:
        try:
            return await store.resolve_question(question_id)
        except PageNotFound:
            return {"error": f"no open question '{question_id}'"}

    async def _questions(status: str = "open") -> dict[str, Any]:
        return {"questions": await store.list_questions(status=status)}

    defs: list[tuple[ToolDef, Any]] = [
        (
            ToolDef(
                name="wiki_toc",
                description=(
                    "Table of contents of your wiki: every page's slug, title, and "
                    "summary. The map — start here before reading or writing."
                ),
                parameters={"type": "object", "properties": {}},
            ),
            _toc,
        ),
        (
            ToolDef(
                name="wiki_read",
                description="Read a wiki page's full markdown body plus citations and outgoing links.",
                parameters={
                    "type": "object",
                    "properties": {"slug": {"type": "string"}},
                    "required": ["slug"],
                },
            ),
            _read,
        ),
        (
            ToolDef(
                name="wiki_search",
                description="Search wiki pages; returns relevance-ranked slugs + summaries (use wiki_read for full bodies).",
                parameters={
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
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
                    "knowledge graph automatically. Always provide a 1-2 sentence "
                    "`summary`; it is what gets injected into future context. Each "
                    "write records a revision."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "slug": {"type": "string", "description": "kebab-case page id, e.g. 'competitors/acme'"},
                        "title": {"type": "string"},
                        "body": {"type": "string", "description": "Full markdown body with [[slug]] wikilinks."},
                        "summary": {"type": "string", "description": "1-2 sentence page summary (injected into context)."},
                        "note": {"type": "string", "description": "Short revision note (why this edit)."},
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
                        "note": {"type": "string"},
                    },
                    "required": ["slug", "find", "replace"],
                },
            ),
            _patch,
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
                description="List open (or resolved) wiki questions.",
                parameters={
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "enum": ["open", "resolved"], "default": "open"}
                    },
                },
            ),
            _questions,
        ),
    ]

    for tool_def, handler in defs:
        ctx.tool_registry.register("plugin-wiki", tool_def, handler)
