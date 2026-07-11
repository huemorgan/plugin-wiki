# 003 — page lifecycle: archive + delete

## Why

Luna migrated 12 pages out of the main wiki and could only empty them and mark
them "MIGRATED" — there was no delete or archive tool. The stubs pollute the
TOC, search, and the tier-2 context injection, and Luna itself asked for a
cleanup feature (2026-07-11 chat with Roy).

## Doctrine

- **Archive is the default retirement path.** Reversible; the page keeps its
  body, revisions, and citations but disappears from everything that feeds the
  agent (toc, search, injection, page counts). This preserves the
  "authored knowledge is never mass-destroyed" stance of `delete_wiki`.
- **Delete is for junk only.** Hard removal of page + revisions + citations +
  outgoing link edges. Tool description steers the agent: empty stubs,
  duplicates, migrated-elsewhere pages.
- **Any body write revives.** `wiki_write`/`wiki_patch` on an archived slug
  clears `archived_at` — a page you're actively writing is not archived.
- Revision history stays append-only; archive doesn't touch it.

## Shape

- `wiki_pages.archived_at TIMESTAMPTZ NULL` (NULL = live), idempotent ALTER in
  `on_load` (same ladder pattern as the 0.4.0 wiki_id migration).
- Store: `set_archived(slug, bool, wiki)`, `delete_page(slug, wiki)`; archived
  excluded from `toc`, `search`, `count_pages`, `list_wikis` counts (and thus
  `overview()` → tier-2 injection). `toc(archived=True)` lists the archive.
  Deletes are explicit, not FK-cascade, so SQLite w/o `foreign_keys=ON`
  matches Postgres. Incoming wikilinks to a deleted page remain as stub edges
  (same as never-written targets); open questions detach (`page_id = NULL`).
- Tools (12 → 15): `wiki_archive_page`, `wiki_unarchive_page`,
  `wiki_delete_page`; `wiki_toc` grows `archived=true`.
- Routes: `/pages?archived=true`; `/graph` drops edges sourced from archived
  pages so nothing dangles from a missing node.
- Pane (per `/vision/ux_guidelines.md`): archived pages leave the graph and
  the live rail; a collapsed, dimmed **Archived · n** section sits at the rail
  bottom; the page view shows an outline **Archived** chip. No new panels, no
  clutter; archive is one click from inspection, zero attention otherwise.

## Verify

- Store tests (aiosqlite): hide/list/revive/delete semantics, events, edges.
- Real Luna (QA :8766): live agent turn exercising all three tools + the HTTP
  surface the pane uses, against Postgres (migration proof).
