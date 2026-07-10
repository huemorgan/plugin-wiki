# 001 — plugin-wiki: Multiple isolated wikis + readable node hover

**Produces version:** plugin-wiki 0.4.0 (+ a small plugin-curiosity bump for the dream prompt)
**Base:** plugin-wiki 0.3.2

## Context

Today the wiki is one flat namespace: `wiki_pages.slug` is globally unique
(models.py:27), and `toc()`, `search()`, `links()`, questions, the graph
route, the tools, and tier-2 injection all operate over everything. The only
scoping hooks that exist are dormant: `mission_id` (a column nothing filters
by) and `/` in slugs (a convention nothing respects as a boundary).

Two changes in this plan:

1. **Multiple wikis, each isolated.** A wiki is a first-class row with a
   `slug`, a `name`, and a `description`. Pages, links, and open questions
   belong to exactly one wiki; nothing crosses the boundary (TOC, search,
   graph, wikilinks, injection). The description is *maintained by the
   nightly dream* — dreaming summarizes what each wiki now covers and writes
   it back, so descriptions stay current without owner effort.
2. **Readable hover in the graph.** Hovering a node shows its title +
   summary at 100% font size regardless of zoom level, so the graph is
   readable zoomed-out without pinching in.

## Goals

1. `wikis` table: `id`, `slug` (unique, kebab), `name`, `description`,
   timestamps. A `main` wiki always exists; all current data migrates into it.
2. Page slugs unique **per wiki**, not globally — the same `competitors/acme`
   can exist in two wikis without collision.
3. Full isolation in every read path: store, tools, routes, provider,
   injection, graph, live events.
4. Agent can create wikis, list them, and update name/description via tools;
   the dream refreshes descriptions of wikis it touched.
5. UI: wiki switcher in the header (name + description + page count),
   selection persisted; graph/search/page-count all scoped to the selected
   wiki.
6. Hover tooltip in the graph at fixed screen-space font size.
7. Zero breakage for existing callers: every tool/route/provider method
   defaults to `main` when no wiki is given; plugin-curiosity keeps working
   unmodified (its description refresh is an additive prompt step).

## Non-Goals

- Per-wiki permissions/visibility — all wikis belong to the tenant.
- Cross-wiki links or transclusion. A `[[slug]]` always resolves inside the
  page's own wiki; that's the isolation contract.
- Moving pages between wikis (can be a later tool; revisions make it
  non-trivial to do casually).
- Search ranking improvements (still the dumb lexical scorer, now per wiki).
- Deleting wikis from the UI (agent tool only, and only when empty — guard
  against accidental mass deletion of authored knowledge).

## Approach

### Phase A — Schema + migration (`models.py`, `__init__.py`)

New model:

```python
class Wiki(Base):
    __tablename__ = "wikis"
    id: UUID pk
    slug: str unique          # "main", "competitors", ...
    name: str                 # "Main", "Competitor landscape"
    description: Text         # dream-maintained summary of what lives here
    created_at / updated_at
```

Changes:
- `WikiPage.wiki_id` FK → `wikis.id`, indexed. `slug` loses `unique=True`;
  add `UniqueConstraint("wiki_id", "slug")`.
- `WikiLink.wiki_id` FK, indexed (from/to are slugs — only meaningful per
  wiki). Edge index becomes `(wiki_id, from_page, to_page, kind)`.
- `WikiOpenQuestion.wiki_id` FK, indexed (questions can be pageless, so they
  need their own scope).
- `WikiRevision` / `WikiCitation` unchanged (they hang off `page_id`).

Migration runs in `on_load`, idempotent, same pattern as the existing
`checkfirst=True` DDL:
1. Create `wikis` if missing; insert `main` ("Main", empty description) if
   absent.
2. `ALTER TABLE ... ADD COLUMN IF NOT EXISTS wiki_id` on the three tables
   (Postgres); backfill `NULL → main.id`; then create the new unique index
   `(wiki_id, slug)` and drop the old unique index on `slug`.
3. SQLite (tests/dev) always creates tables fresh from the new models — the
   ALTER ladder is Postgres-only, wrapped so a fresh DB skips it.

Production note (memory: managed_plugins overrides in-tree): after shipping,
sync `~/.luna/managed_plugins` or the old code keeps running against the new
schema expectations.

### Phase B — Store (`store.py`)

- `WikiStore` gains a small wiki resolver: `_wiki(s, wiki_slug)` →
  `Wiki` row or raises `WikiNotFound` (new exception, sibling of
  `PageNotFound`).
- Every page-facing method gains `wiki: str = "main"`:
  `upsert_page`, `patch_page`, `get_page`, `toc`, `search`, `count_pages`,
  `revisions`, `add_citation`, `add_question`, `list_questions`, `links`.
  All queries filter by `wiki_id`. `_reparse_links` stamps `wiki_id` on
  every edge and deletes only edges of that wiki.
- New methods:
  - `list_wikis()` → `[{slug, name, description, page_count, updated_at}]`
  - `create_wiki(slug, name, description="")` (slugified; conflict → error)
  - `update_wiki(slug, name=None, description=None)`
  - `delete_wiki(slug)` — refuses `main` and refuses non-empty wikis.
- `on_change` payload gains `wiki` so the UI can ignore events for other
  wikis: `{action, slug, wiki}`.

### Phase C — Tools (`tools.py`)

- All 9 existing tools gain optional `wiki` param (string, default `main`),
  described as "wiki slug; omit for the main wiki; see wiki_list_wikis".
- New tools:
  - `wiki_list_wikis` — slugs, names, descriptions, page counts. The map of
    maps; tool description tells the agent to start here when unsure where
    knowledge lives.
  - `wiki_create_wiki(slug, name, description?)` — for spinning up an
    isolated knowledge space (a new mission, a client, a domain).
  - `wiki_update_wiki(slug, name?, description?)` — how dreaming refreshes
    the description.
- Unknown wiki in any tool → friendly error + the wiki list (mirrors the
  existing PageNotFound → TOC pattern).

### Phase D — Provider + injection (`provider.py`, `injection.py`)

- Provider methods gain `wiki: str = "main"` kwarg; add `list_wikis()` and
  `update_wiki()`. plugin-curiosity's existing calls keep working untouched.
- `tier1_note`: "You keep N wikis (M pages, Q open questions)..." — mention
  `wiki_list_wikis` alongside `wiki_toc`.
- `tier2_toc`: group by wiki. Each wiki contributes a header line
  `### <name> — <description>` followed by its page lines; ranking stays
  recency-first *across* all wikis so the busiest wiki naturally dominates
  the budget. Same `TIER2_CHAR_BUDGET` overall.

### Phase E — Routes (`routes.py`)

- `GET /wikis` — list. `POST /wikis` — create (name, slug, description) for
  the UI's "new wiki" affordance.
- Existing reads gain `?wiki=` query param, default `main`: `/pages`,
  `/links`, `/questions`, `/search`, `/graph`, `/pages/{slug}`,
  `/pages/{slug}/revisions`. Old URLs unchanged → old UI builds keep working.

### Phase F — UI: wiki switcher + hover tooltip (`wiki-src/`)

Switcher:
- `api.ts`: `fetchWikis()`, and `wiki` argument threaded through
  `fetchGraph/fetchPage/fetchRevisions/fetchQuestions/searchPages`.
- `App.tsx`: `currentWiki` state, persisted in `localStorage`
  (`luna.wiki.current`). Header gains a dropdown between the Wiki title and
  search: shows current wiki name; open → list of wikis (name, description,
  page count) + "New wiki…" inline form (name → slugified, description).
  Switching wikis refetches the graph; page count chip becomes per-wiki.
- `events.ts` consumers: only refresh when `event.wiki === currentWiki`
  (still refresh the wiki list so counts stay live).

Hover tooltip (goal 6) — screen-space, not canvas-space:
- One tooltip element for the whole graph, rendered as a sibling of
  `<ReactFlow>` inside the container (`position: absolute`,
  `pointer-events: none`, `z-50`), so it lives **outside** the zoomed/panned
  viewport transform and always renders at 100% font size.
- Driven by ReactFlow's `onNodeMouseEnter` / `onNodeMouseLeave` — one state
  update per hover, zero per-node listeners, no graph re-render (nodes/edges
  memo untouched).
- Position: `getBoundingClientRect()` of the hovered node's DOM element
  (available on the mouse event target), clamped to the container, flipped
  above/below to stay inside. Content: title (text-sm, full — no truncate)
  + summary (text-xs, up to ~4 lines) + kind icon.
- Hide on `onMove` (pan/zoom) and on click — never animate position per
  frame, so hovering costs one paint, not a tracking loop.

### Phase G — Dreaming maintains descriptions (plugin-curiosity)

Additive step in `DREAM_TARGET` (dream.py), after consolidation (step 3.5):
"For each wiki you touched tonight, wiki_update_wiki its `description` to a
current 1–2 sentence summary of what that wiki covers — the description is
the wiki's shelf label; keep it honest." Patch-level bump of
plugin-curiosity (prompt-only change, no code path).

### Versions & shipping

- Bump all three stamps (memory: in-code `PluginManifest` is authoritative):
  `PluginManifest.version` 0.4.0, `luna-plugin.toml`, `wiki-src/package.json`;
  rebuild `wiki-src` → `plugin_wiki/ui`.
- Push → publish to marketplaces.com.ai (standing instruction), gh auth
  huemorgan2 if this repo pushes to a huemorgan2 remote.

## Tests

- `test_store.py`: two wikis holding the same slug stay independent
  (write/read/patch); search/toc/links/questions scoped; `_reparse_links`
  only touches its own wiki's edges; create/update/delete wiki guards
  (`main` undeletable, non-empty undeletable); default-wiki fallback.
- Migration: run `on_load` twice against a DB seeded with 0.3.x-shape data →
  pages land in `main`, second run no-ops.
- `test_injection.py`: tier2 groups by wiki with name+description headers;
  budget still respected; tier1 counts wikis.
- Routes: `?wiki=` filtering, unknown wiki → 404, `POST /wikis` slugify +
  conflict.
- Manifest test: version + new tool count.
- **Real-Luna verification before shipping** (memory: unit tests missed
  cookie-auth/stale-route classes of bugs): create a second wiki via chat,
  confirm agent writes land scoped, switcher + hover tooltip in the actual
  sidebar iframe, live-update glow still fires on the right wiki.
