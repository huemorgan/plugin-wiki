# 004 — execution summary (0.8.0, 2026-08-17)

Shipped as planned.

- `wiki-src/src/layout.ts`: shared `ringLayout()` — radius capped at 800 px,
  outer ring +180, odd-node stagger (−44 px) when angular spacing < node
  width. Same function drives the full graph and the home miniatures.
- `GraphView.tsx`: uses `ringLayout`; `minZoom 0.1`, `fitViewOptions.padding 0.08`.
  A 100-page / 20-stub wiki now fits the viewport on load and at max zoom-out;
  hover cards still readable (screen-space).
- `WikiHome.tsx`: card grid (2 per row ≥ 640 px), each card = page-count
  eyebrow, name, description, 320×200 SVG miniature (boxes on rings, violet
  wikilinks; box size shrinks for dense wikis). Whole-card hover tint
  (`bg-luna-600/15` + violet border, 200 ms). Trailing "New wiki" card with
  inline create form.
- `App.tsx`: `currentWiki: string | null`; `null` = home. Header "Wiki" button
  → home; switcher gains "All wikis"; search/page-count hidden on home;
  stale/missing selection lands on home; live updates re-fetch miniatures.
- Version 0.7.1 → 0.8.0 (toml, manifest, pyproject, package.json).

Verified with a mock API + Playwright (headless Chromium): home renders 4
cards with miniatures; hover tints the card; click opens the graph; 100-page
graph fully visible at load; header/switcher return home; python tests 51 pass.
