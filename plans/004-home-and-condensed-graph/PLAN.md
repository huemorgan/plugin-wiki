# 004 — wiki home page + condensed graph for large wikis

## Why

1. The pane always opens straight into one wiki (`localStorage` or `main`).
   There is no place that shows *what wikis exist* at a glance — the header
   dropdown is the only overview, and it is text-only.
2. Wikis with ~100 pages are unreadable: `layout()` grows the ring radius
   with page count (`n * 32` → 3200 px radius at 100 pages) while ReactFlow's
   default `minZoom` is 0.5, so `fitView` cannot fit the graph and max zoom-out
   shows only the centre with lines. Hover cards already render in screen space
   (001), so overlapping nodes stay readable on hover — density is fine, an
   unfittable graph is not.

## Doctrine

- **Home = the wiki library.** No wiki selected → a card grid, one card per
  wiki. The card is the wiki's identity: name (headline), description
  (support line), page count, and a live miniature of its graph — same ring
  layout, same boxes-and-lines language as the full graph. Two cards per row,
  big enough that the miniature reads.
- **Whole-card hover.** Hover tints the entire card surface (background shifts
  toward violet-tinted panel), not just the border. Calm: one soft transition,
  no glow, no scale bounce.
- **The graph must always fit at max zoom-out.** Layout is *condensed*: ring
  radius is capped so the graph's extent stays within a fixed budget
  (~1 800 px), and `minZoom` is lowered so `fitView` can always frame it.
  Neighbours may overlap; when angular spacing drops below node width, odd
  nodes are staggered onto a slightly smaller radius so labels interleave
  instead of stacking.

## Shape

- `wiki-src/src/layout.ts` (new): pure `ringLayout(graph)` →
  `{ positions: Map<id,{x,y}>, extent }` shared by `GraphView` and the home
  miniature. Constants: `MAX_RADIUS = 800`, outer ring `+180`, stagger `-44`
  when spacing < 200 px.
- `GraphView.tsx`: use `ringLayout`; `minZoom={0.1}`, `fitViewOptions={{padding: 0.08}}`.
- `WikiHome.tsx` (new): `<WikiHome wikis onOpen onCreate/>` — `grid-cols-2`
  card grid (1 col under 640 px), each card fetches `fetchGraph(slug)` once
  and renders an SVG miniature via `ringLayout` (boxes = rounded rects with
  a violet outline for pages, dashed dim for stubs; lines = wikilink edges).
  Trailing "New wiki" card opens the same create form as the switcher.
- `App.tsx`: `currentWiki: string | null`; `null` = home. Header "Wiki"
  button goes home (closes any page first). Switcher shows "All wikis" when
  home and lists an "All wikis" row. Search/page-count hidden on home.
  Live updates on home refresh the wiki list (and the miniatures re-fetch on
  `updated_at` change).
- Selection is still remembered in `localStorage`; a fresh load with nothing
  stored (or a stored slug that no longer exists) lands on home.
- Version 0.7.1 → 0.8.0 (three stamps + `wiki-src/package.json`).

## Out of scope

Force-directed layout, per-wiki colour themes, drag-to-reorder cards.

## Verify

- `npm run build` in `wiki-src` (tsc + vite → `plugin_wiki/ui`).
- Python tests still pass (manifest version test bumped).
- Manual: home renders N cards with miniatures; hover tints the card; click →
  graph; 100-page wiki fits at max zoom-out; "Wiki" header returns home.
