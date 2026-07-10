# 002 — plugin-wiki UI: Animated page open (right-slide panel + node→list flight)

**Produces version:** plugin-wiki 0.5.0 (UI-only; builds on 001's multi-wiki UI)
**Base:** plugin-wiki 0.4.0

## Context

Opening a page today is a hard swap: `App.tsx` unmounts `<GraphView>` and
mounts `<PageView>`. The graph dies and is reborn on every open/close —
React Flow re-inits, `fitView` re-runs, node positions and viewport reset.

Target interaction (owner spec):

1. Click a page node → a vertical line animates in **from the right**,
   opening a right-side space for the page. That space shows a loading
   indicator, then the page.
2. Meanwhile the left area (now narrower) becomes a page list — but not by
   killing the graph and mounting a list. The **top 10 page nodes' titles
   fly** from their graph positions into the top of the left list; the
   remaining pages fade in under them when the flight completes.
3. The page has a top-right **X**. Closing reverses it: the top-10 titles
   fly back to their nodes, the rest of the list dissolves, the panel slides
   out, and the graph — which never unmounted — is exactly as you left it.

Hard requirement: **the graph must not stall or die-and-reborn.** Everything
below is designed around compositor-only animation and a permanently mounted
React Flow.

## Goals

1. Right page panel slides in/out with a visible leading edge (the "line"),
   loading indicator inside, content appearing without jank.
2. Top-10 title flight graph→list on open, list→graph on close; remaining
   list items staggered in after the flight.
3. React Flow stays mounted for the whole session — open/close never resets
   viewport, node positions, or triggers canvas re-init.
4. 60fps target on the animation path: transform/opacity only; no layout
   properties animated; no per-frame React state.
5. Wikilink navigation inside an open page swaps content in place (no re-run
   of the open choreography); search-result open from graph view runs it.
6. `prefers-reduced-motion` → skip flights, instant panel, everything still
   works.

## Non-Goals

- Backend changes. None — this is `wiki-src/` only.
- Animating the graph nodes themselves (they stay put; ghosts fly).
- Mobile/touch layout work beyond not breaking the current behavior.
- List virtualization (wiki scale is tens of pages).

## Approach

### Layering model — overlays, not resize

The naive read of the spec — shrink the graph container and grow a page
container — animates *layout* (width), forcing React Flow through a resize
observer + canvas reflow every frame. That is exactly the stall to avoid.

Instead the graph keeps 100% of the main area forever, and two overlay
layers composite on top (all children of the same `relative` main element):

```
main (relative, overflow hidden)
├─ GraphView            — always mounted, full size, never resized
├─ .list-rail  (left)   — absolute, width = LIST_W (~280px), translateX(-100%)→0
├─ .page-panel (right)  — absolute, left = LIST_W → right edge,
│                         translateX(100%)→0, 1px luna-600 left border = "the line"
└─ .ghost-layer         — absolute inset-0, pointer-events none,
                          populated only during flights
```

- Panel open = `transform: translateX(100%) → 0` (320ms cubic-bezier
  ease-out). Its glowing left border *is* the line that "animates in from
  the right to create the space" — the edge leads, the space follows.
- List rail slides `translateX(-100%) → 0` in the same timeline, so the
  "left pane getting smaller" reads as such, while the graph underneath is
  untouched (dimmed via `opacity` on a scrim, `pointer-events: none`).
- Both overlays are compositor-only: transform + opacity, `will-change`
  applied just before the transition and removed on `transitionend`
  (permanent will-change wastes GPU memory).
- Graph interactivity gated off while covered; on close it is instantly
  live again — same instance, same viewport, same dragged positions.

### Open choreography (state machine in App.tsx)

`view: 'graph' | 'opening' | 'page' | 'closing'` — transitions are the only
places animation code runs.

On node click (t=0, one rAF-batched sequence):
1. **Read pass** — pick top-10 page nodes and `getBoundingClientRect()` each
   node's DOM element (`[data-testid="wiki-node-<id>"]`), all reads together
   (no interleaved writes → no layout thrash). Fire `fetchPage(slug)`
   immediately — network overlaps animation.
2. **Write pass** — mount list rail (full page list already known from the
   graph data; no fetch needed) with the top-10 rows `visibility: hidden`
   and the rest `opacity: 0`; mount panel with spinner; add transition
   classes. Next frame, measure the ten hidden list rows (read), then spawn
   ten **ghosts** in the ghost layer: absolutely positioned divs containing
   just the title text, styled as list rows, placed at the node rects.
3. **Flight** — each ghost runs one WAAPI animation
   (`el.animate([{transform: from}, {transform: to}], …)`): translate +
   scale from node rect to its list-row rect. 300ms, ~25ms stagger,
   ease-out. WAAPI keeps it off the React render path entirely — zero
   setState during flight.
4. **Land** — on the last ghost's `finished`: top-10 rows flip to visible,
   ghosts removed, remaining rows fade in (opacity 0→1, 150ms, small
   stagger). State → `'page'`.
5. **Page content** — spinner until `fetchPage` resolves **and** the panel
   `transitionend` has fired, then render markdown (fade-in 120ms).
   Rationale: ReactMarkdown rendering is main-thread work; doing it
   mid-slide is the one thing that could visibly hitch the panel. Sequencing
   it after the slide costs ≤320ms perceived and buys a clean animation.

Top-10 ranking: wikilink degree (in+out) desc, tie-break `updated_at`
recency — "the ten pages that structure this wiki", not just the newest.

### Close choreography (X button, top-right of panel)

Exact reverse: read list-row rects → spawn ghosts on rows → hide rows →
fly to (current) node rects — re-measured at close time, since the user may
have panned/zoomed; if a node is outside the visible viewport, that ghost
fades out at the list edge instead of flying offscreen. Panel and rail
translate out; scrim fades; state → `'graph'`. The X replaces PageView's
current "← Graph" back button (`ArrowLeft` → `X`, moved top-right).

### In-page navigation

`onNavigate` (wikilink click / search hit while a page is open) stays inside
`'page'`: swap panel content with the spinner-then-fade pattern; the list
rail highlights the active row. No flights.

### Performance rules (the contract for implementation + review)

- Animate **only** `transform` and `opacity`. Never width/left/top/height;
  never box-shadow mid-flight (the `node-updated` glow is paused on covered
  graph anyway).
- All DOM measurement batched: one read pass, one write pass per
  transition; ghosts positioned via `transform: translate()` from a single
  `inset: 0` origin, not `top/left`.
- WAAPI (or CSS transitions) for every animation — no rAF-driven setState,
  no React re-render per frame. React state changes: exactly one per
  phase boundary (4 per full open/close cycle).
- `contain: layout paint` (or `content`) on rail/panel/ghost-layer so their
  churn can't invalidate graph layout.
- ≤10 ghosts, plain text nodes — no icons/borders mid-flight.
- ReactFlow stays mounted with stable `nodes`/`edges` references during
  transitions (the `useMemo` already guarantees this while `graph` object
  is unchanged — do not refetch the graph on open/close).
- Live `wiki.updated` events during `'page'`: refresh page + list data, but
  defer graph refetch to close time if a flight is in progress.
- `@media (prefers-reduced-motion: reduce)`: transitions 0ms, no ghosts —
  rows just appear; panel appears in place.

### File changes (all in `wiki-src/src/`)

- `App.tsx` — state machine, layered layout, choreography orchestration.
- `PageList.tsx` (new) — left rail: full page list, active row, top-10 rows
  addressable by slug for FLIP measurement.
- `flight.ts` (new) — measure/ghost/WAAPI helper (`flyTitles(from[], to[])
  → Promise`), reduced-motion guard lives here.
- `GraphView.tsx` — expose node-rect lookup (by data-testid), accept
  `covered` prop (scrim + pointer-events), keep 001's hover tooltip
  suppressed while covered.
- `PageView.tsx` — becomes panel content: X button top-right, spinner state,
  deferred markdown render, fade-in.
- `index.css` — rail/panel/scrim/ghost classes, transitions,
  reduced-motion block.

### Versions & shipping

- Three stamps → 0.5.0 (`PluginManifest`, `luna-plugin.toml`,
  `wiki-src/package.json`), rebuild → `plugin_wiki/ui`, sync managed_plugins,
  push, publish to marketplaces.com.ai.

## Verification

No JS test infra in this plugin — verification is real-Luna, per memory:

- Open/close cycle: node positions + viewport preserved (drag a node, open,
  close → still where you put it; zoom preserved).
- DevTools Performance: record open + close with 4× CPU throttle — no long
  task > 50ms during the flight window, panel slide holds 60fps
  (compositor-only frames), no ReactFlow re-init (no `fitView` refire).
- Flight correctness after pan/zoom (ghosts land on current node positions;
  offscreen-node fallback fades).
- Slow network (throttled): spinner visible, content fades in after slide,
  no layout jump.
- Wikilink navigation in-page, search-open from both views, live-update
  event mid-page, reduced-motion mode, small wikis (< 10 pages → flight
  uses all of them, no empty slots).
