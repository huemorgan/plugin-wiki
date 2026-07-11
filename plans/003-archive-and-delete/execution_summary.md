# Execution summary — 003 archive + delete

**Shipped:** plugin-wiki **0.6.0**, published to `official` on
marketplaces.com.ai (commit `52d79fb`, tag `v0.6.0`). Local tests 40/40,
live verification on QA Luna (:8766, Postgres) **13/13**.

## What was built

- `wiki_pages.archived_at` + idempotent `on_load` ALTER (Postgres
  `TIMESTAMPTZ` / SQLite `TIMESTAMP`).
- Store: `set_archived` / `delete_page`. Archived pages hidden from `toc`,
  `search`, `count_pages`, `list_wikis` page counts, and therefore tier-2
  injection; still readable via `get_page` (flagged `archived: true`).
  Any `wiki_write`/`wiki_patch` to the slug revives it. Delete removes page,
  revisions, citations, and outgoing link edges explicitly (no FK-cascade
  reliance); incoming links remain as stub edges; open questions detach.
- Tools 12 → 15: `wiki_archive_page` (default retirement, reversible),
  `wiki_unarchive_page`, `wiki_delete_page` (junk only — description steers
  the agent); `wiki_toc archived=true` lists the archive. Tier-1 injection
  note mentions the lifecycle tools. All three stamps at 0.6.0.
- Routes: `GET /pages?archived=true`; `/graph` drops edges whose source page
  is archived (no dangling edges from missing nodes).
- Pane: collapsed dimmed **Archived · n** section at the rail bottom
  (opacity-60, Archive icon, expand on click); **Archived** outline chip in
  the page-view meta row. Archived pages are out of the graph entirely.
- Provider seam: `set_archived` / `delete_page` / `toc(archived=)`
  passthroughs for behavior plugins.

## Verification

- `pytest` 40/40 (new: hide-from-toc/search/counts, revive-on-write,
  delete removes history + own edges + detaches questions, change events,
  delete-pages-then-wiki).
- Live QA Luna 13/13 (`scratchpad/verify_wiki_060.py` pattern): real agent
  turn called `wiki_write`×2 → `wiki_archive_page` → `wiki_delete_page` →
  `wiki_toc archived=true`; second turn `wiki_unarchive_page` → revive →
  cleanup. HTTP: archived hidden from `/pages`, listed under
  `?archived=true`, readable + flagged on `/pages/{slug}`, deleted page 404s,
  pane served with `v=0.6.0` cache-bust.
- Auth note for future QA runs: single-owner instance — mint a token with
  `luna.auth.jwt.create_token(str(user_id))` using `LUNA_JWT_SECRET` from
  `luna/.env` (signup 409s, never touch the owner password).

## Follow-ups

- Luna instances on 0.5.0 need the marketplace upgrade, then can be asked to
  `wiki_delete_page` the 12 MIGRATED stubs in their main wiki.
- No UI affordance for the owner to archive/delete from the pane (agent-only
  for now) — add owner actions if Roy asks.
