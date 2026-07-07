# plugin-wiki

Luna's mission knowledge base — a Karpathy-style LLM wiki.

Authored, revisable markdown pages with `[[wikilinks]]`, citations, and open
questions. Knowledge accumulates by compile-time synthesis (authored pages),
not query-time RAG. Distinct from memory (atomic facts + semantic recall);
they cross-feed.

Substrate only: behavior plugins (e.g. plugin-curiosity) decide who writes and
when, consuming this plugin via the `wiki` provider
(`ctx.provider_registry.get("wiki")`).

Part of the Luna Curiosity project — see
`research/luna-curiosity/` in the luna-plugins workspace.
