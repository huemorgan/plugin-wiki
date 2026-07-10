# Execution summary — 002 animated page open

**Shipped:** plugin-wiki **0.5.0**, published to `official` on marketplaces.com.ai
(commit `b471ff5`, tag `v0.5.0`). Dojo walkthrough **16/16** on a real Luna.
UI-only release on top of 0.4.0 — no backend changes.

## What was built

- **State machine** (`App.tsx`): `graph | opening | page | closing`.
  Choreography code runs only in the two transition states. React Flow is
  mounted for the whole session; overlays composite above it.
- **Overlays, not resize**: left rail (280px, `translateX(-100%)→0`) and page
  panel (`translateX(100%)→0`, glowing luna-600 left border = "the line"),
  plus a scrim over the graph and a pointer-events-none ghost layer. Only
  `transform`/`opacity` are animated; `contain: layout paint` on every
  overlay. The graph is never resized, so React Flow never reflows.
- **Ghost flight** (`flight.ts`): top-10 pages by wikilink degree (in+out,
  `updated_at` tiebreak) fly from their node rects onto their list-row rects
  via one WAAPI animation each (300ms, 25ms stagger) — raw DOM, zero React
  state during flight. Row rects are projected to the rail's final position,
  so measurement is correct even mid-slide. On close the flight reverses
  against *current* node positions; a node panned offscreen gets a fade
  instead of an offscreen flight.
- **Rail** (`PageList.tsx`): top rows invisible until the ghosts land, the
  rest fade in staggered; rows carry `data-wiki-row` for measurement; active
  row highlighted; live SSE writes refresh it while a page is open (the
  graph refetch is deferred if a flight is mid-air).
- **Panel** (`PageView.tsx`): X close top-right; spinner holds until the
  page fetch resolves **and** the panel `transitionend` fires, so the
  markdown render (the one main-thread hit) lands after the slide; in-page
  wikilink navigation swaps content with no choreography.
- **Reduced motion**: no ghosts, transitions off, everything still works.

## Verification (dojo `wiki-002-page-open-animation`, 16/16)

- Ghosts fly on open and back on close (9 observed on a 9-page wiki —
  <10 pages → all of them, no empty slots).
- Panel + spinner visible mid-open; content rendered after the slide;
  rail listed all 9 pages with none left hidden; ghosts removed after landing.
- **Graph never remounted**: a JS property stamped on the
  `.react-flow__viewport` DOM element before opening survived a full
  open/close cycle; viewport transform and a hand-dragged node position were
  byte-identical after close.
- Zero long tasks (>150ms) observed during the open/close window.
- Wikilink nav swapped the page in place with zero ghosts; an agent write
  mid-page live-updated the rail without reload and without closing the panel.
- Reduced-motion cycle: no ghosts, open and close both work.

## Notes

- LIST_W (280px) is duplicated between `App.tsx` and `.wiki-rail`/panel CSS —
  keep in sync.
- Panel `transitionend` can be lost (tab background, reduced motion); a 700ms
  fallback timer and an explicit reduced-motion branch set `panelReady`.
