"""plugin-wiki — Luna's mission knowledge base (Karpathy-style LLM wiki).

The knowledge substrate: authored, revisable markdown pages with wikilinks,
citations, and open questions. Behavior plugins (plugin-curiosity) consume it
via the "wiki" provider. Authored against `luna_sdk` only.
"""

from __future__ import annotations

from luna_sdk import LunaPlugin, PluginContext, PluginManifest


class WikiPlugin(LunaPlugin):
    manifest = PluginManifest(
        name="plugin-wiki",
        version="0.1.0",
        description="Mission knowledge base: wiki pages, revisions, citations, open questions.",
        provider="wiki",
    )

    async def on_load(self, ctx: PluginContext) -> None:
        # Phase 1 registers tables, wiki_* tools, injection, and the WikiProvider.
        self._ctx = ctx
