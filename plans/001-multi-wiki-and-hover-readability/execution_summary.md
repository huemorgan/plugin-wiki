# Execution summary — 001 multi-wiki + hover readability

**Shipped:** plugin-wiki **0.4.0**, published to `official` on marketplaces.com.ai
(commit `053ee0b`, tag `v0.4.0`). Dojo walkthrough **15/15** on a real Luna.

## What was built

### Backend
- `wikis` table (slug, name, description) + `wiki_id` FK on pages; revisions,
  links and questions scope through their page. Self-healing `main` wiki.
- Migration backfills existing pages into `main`; unique index moves from
  `slug` to `(wiki_id, slug)` (`uq_wiki_pages_wiki_slug`) — same slug can live
  in different wikis. Verified on real Postgres.
- Store: every read/write takes `wiki=` (default `main`); `WikiNotFound` → 404.

### Agent surface (the agent can create and navigate wikis)
- New tools: `wiki_list_wikis`, `wiki_create_wiki`, `wiki_update_wiki`
  (name/description — dream uses it to keep descriptions current).
- `wiki` param added to `wiki_write`, `wiki_read`, `wiki_toc`, `wiki_patch`,
  `wiki_ask`, `wiki_resolve_question`.
- Prompt injection lists all wikis (name, description, page count) so the
  model knows what exists before touching tools.

### Routes
- `GET/POST /api/p/plugin-wiki/wikis`; `wiki=` query param on all read routes;
  unknown wiki → 404; duplicate create → 409.
- Fix: `WikiCreate` body model moved to module level — with
  `from __future__ import annotations` a function-local BaseModel can't be
  resolved from module globals and FastAPI silently degrades the body to a
  required query param (422 `loc: ["query","body"]`).

### UI
- Wiki switcher (current wiki name, menu of all wikis, "New wiki…" inline
  form) with per-wiki graph reload; selection persisted in localStorage.
- Hover card rendered in screen space outside `.react-flow__viewport`, so it
  stays at 100% font size (14px) at any zoom.
- SSE graph refreshes scoped: events for a different wiki don't touch the
  open graph.

### plugin-curiosity dream step
- `dream.py` nightly prompt now sweeps every wiki (`wiki_list_wikis` →
  per-wiki `wiki_toc`/age_days gate) and refreshes each touched wiki's
  description via `wiki_update_wiki`.
- **Not released from this plan:** the curiosity working tree has moved to
  0.8.0 with in-progress phase-9.002 work from another workstream; the dream
  change is committed-in-tree there and ships with 0.8.0. Marketplace still
  has 0.7.1.

## Verification
- 34 unit tests (store isolation, migration, tools, injection).
- Dojo `wiki-001-multi-wiki` walkthrough, 15/15 on a real Luna (port 8766):
  API isolation (same slug per wiki, scoped tocs, 404), agent seeding via
  chat tools, switcher/menu/create-form, hover card at 14px while zoomed out,
  SSE live update in the open wiki with no foreign-wiki leak.

## Notes for the next run
- Agent chat steps in walkthroughs must be driven through the API
  (`POST /api/conversations` + streamed `POST …/messages`, holding the SSE
  open until the turn ends), NOT the UI composer: any concurrent streaming
  turn on the account flips the composer into "type to queue" mode and the
  prompt never becomes a turn.
- Port 8765 belongs to a concurrent e2e session; QA Luna for this work runs
  on 8766.
