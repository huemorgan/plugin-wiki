import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Search, BookOpen, ChevronDown, Plus, Library } from 'lucide-react'
import {
  fetchArchived,
  fetchGraph,
  fetchWikis,
  createWiki,
  searchPages,
  type Graph,
  type PageMeta,
  type WikiMeta,
} from './lib/api'
import { subscribeWikiUpdates } from './lib/events'
import { cn } from './lib/cn'
import { GraphView } from './GraphView'
import { PageView } from './PageView'
import { PageList } from './PageList'
import { flyTitles, reducedMotion, type Flight, type FlightRect } from './flight'

/** 002 state machine: 'opening'/'closing' are the only states where
 * choreography code runs; the graph stays mounted through all four. */
type View =
  | { type: 'graph' }
  | { type: 'opening'; slug: string }
  | { type: 'page'; slug: string }
  | { type: 'closing'; slug: string }

const WIKI_KEY = 'luna.wiki.current'
const LIST_W = 280 // px — keep in sync with .wiki-rail / .wiki-panel in index.css

const nextFrame = () =>
  new Promise<void>((r) => requestAnimationFrame(() => requestAnimationFrame(() => r())))

const relTo = (r: DOMRect, origin: DOMRect): FlightRect => ({
  left: r.left - origin.left,
  top: r.top - origin.top,
  width: r.width,
  height: r.height,
})

/** Header dropdown: switch between isolated wikis, create a new one. */
function WikiSwitcher({
  wikis,
  current,
  onSwitch,
  onCreate,
}: {
  wikis: WikiMeta[]
  current: string
  onSwitch: (slug: string) => void
  onCreate: (name: string, description: string) => Promise<void>
}) {
  const [open, setOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [name, setName] = useState('')
  const [desc, setDesc] = useState('')
  const [busy, setBusy] = useState(false)
  const rootRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])

  const cur = wikis.find((w) => w.slug === current)

  const submit = async () => {
    if (!name.trim() || busy) return
    setBusy(true)
    try {
      await onCreate(name.trim(), desc.trim())
      setName('')
      setDesc('')
      setCreating(false)
      setOpen(false)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="relative" ref={rootRef} data-testid="wiki-switcher">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1.5 text-xs text-ink-200 bg-ink-900 border border-ink-700 rounded-md px-2.5 py-1.5 hover:border-luna-600"
        data-testid="wiki-switcher-button"
      >
        <Library size={12} className="text-luna-400" />
        <span className="max-w-36 truncate">{cur?.name || current}</span>
        <ChevronDown size={12} className="text-ink-500" />
      </button>
      {open && (
        <div
          className="absolute top-full mt-1 left-0 w-72 bg-ink-900 border border-ink-700 rounded-md shadow-xl z-50 overflow-hidden"
          data-testid="wiki-switcher-menu"
        >
          {wikis.map((wk) => (
            <button
              key={wk.slug}
              onClick={() => {
                onSwitch(wk.slug)
                setOpen(false)
              }}
              data-testid={`wiki-switcher-item-${wk.slug}`}
              className={
                'block w-full text-left px-3 py-2 hover:bg-ink-800 ' +
                (wk.slug === current ? 'bg-ink-800/60' : '')
              }
            >
              <div className="flex items-center gap-2">
                <span className="text-xs text-ink-100">{wk.name}</span>
                <span className="text-[10px] text-ink-500 ml-auto shrink-0">
                  {wk.page_count} page{wk.page_count === 1 ? '' : 's'}
                </span>
              </div>
              {wk.description && (
                <div className="text-[10px] text-ink-500 line-clamp-2">{wk.description}</div>
              )}
            </button>
          ))}
          <div className="border-t border-ink-800">
            {!creating ? (
              <button
                onClick={() => setCreating(true)}
                data-testid="wiki-switcher-new"
                className="flex items-center gap-1.5 w-full px-3 py-2 text-xs text-luna-300 hover:bg-ink-800"
              >
                <Plus size={12} /> New wiki…
              </button>
            ) : (
              <div className="p-2.5 space-y-1.5" data-testid="wiki-switcher-create-form">
                <input
                  autoFocus
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && submit()}
                  placeholder="Name"
                  data-testid="wiki-new-name"
                  className="w-full bg-ink-950 border border-ink-700 rounded px-2 py-1 text-xs text-ink-200 placeholder-ink-600 outline-none focus:border-luna-600"
                />
                <input
                  value={desc}
                  onChange={(e) => setDesc(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && submit()}
                  placeholder="What lives in this wiki? (optional)"
                  data-testid="wiki-new-description"
                  className="w-full bg-ink-950 border border-ink-700 rounded px-2 py-1 text-xs text-ink-200 placeholder-ink-600 outline-none focus:border-luna-600"
                />
                <div className="flex gap-2 justify-end">
                  <button
                    onClick={() => setCreating(false)}
                    className="text-[11px] text-ink-500 hover:text-ink-300"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={submit}
                    disabled={!name.trim() || busy}
                    data-testid="wiki-new-create"
                    className="text-[11px] text-luna-300 hover:text-luna-200 disabled:opacity-40"
                  >
                    Create
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

const slugifyClient = (raw: string) =>
  raw
    .trim()
    .toLowerCase()
    .replace(/[\s_]+/g, '-')
    .replace(/[^a-z0-9/-]/g, '')
    .replace(/-{2,}/g, '-')
    .replace(/^[-/]+|[-/]+$/g, '')

export function App() {
  const [view, setView] = useState<View>({ type: 'graph' })
  const [graph, setGraph] = useState<Graph | null>(null)
  const [archived, setArchived] = useState<PageMeta[]>([])
  const [wikis, setWikis] = useState<WikiMeta[]>([])
  const [currentWiki, setCurrentWiki] = useState<string>(
    () => localStorage.getItem(WIKI_KEY) || 'main',
  )
  const [error, setError] = useState<string | null>(null)
  const [updatedSlug, setUpdatedSlug] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<PageMeta[]>([])
  // choreography phases: slid drives the rail/panel/scrim transitions,
  // landed flips the list rows visible after the ghost flight
  const [slid, setSlid] = useState(false)
  const [landed, setLanded] = useState(false)
  const [panelReady, setPanelReady] = useState(false)
  const glowTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const wikiRef = useRef(currentWiki)
  wikiRef.current = currentWiki
  const viewRef = useRef(view)
  viewRef.current = view
  const pendingGraph = useRef(false)
  const mainRef = useRef<HTMLElement | null>(null)
  const railRef = useRef<HTMLDivElement | null>(null)
  const panelRef = useRef<HTMLDivElement | null>(null)
  const ghostRef = useRef<HTMLDivElement | null>(null)

  const loadWikis = useCallback(() => {
    fetchWikis()
      .then((ws) => {
        setWikis(ws)
        // stale selection (deleted wiki / stale localStorage) → fall back
        if (ws.length && !ws.some((w) => w.slug === wikiRef.current)) {
          setCurrentWiki('main')
        }
      })
      .catch(() => {})
  }, [])

  const loadGraph = useCallback(() => {
    fetchGraph(wikiRef.current)
      .then((g) => {
        setGraph(g)
        setError(null)
      })
      .catch((e) => setError(String(e)))
    fetchArchived(wikiRef.current)
      .then(setArchived)
      .catch(() => setArchived([]))
  }, [])

  useEffect(loadWikis, [loadWikis])
  useEffect(() => {
    localStorage.setItem(WIKI_KEY, currentWiki)
    setGraph(null)
    setView({ type: 'graph' })
    setSlid(false)
    setLanded(false)
    setPanelReady(false)
    loadGraph()
  }, [currentWiki, loadGraph])

  // Live updates: agent writes refresh the wiki list (counts, descriptions)
  // always, and the graph + open page only when they touch the current wiki.
  // A graph refetch mid-flight would re-render the nodes the ghosts were
  // measured against — defer it until the transition settles.
  useEffect(() => {
    const unsub = subscribeWikiUpdates((u) => {
      loadWikis()
      if (u.wiki && u.wiki !== wikiRef.current) return
      const vt = viewRef.current.type
      if (vt === 'opening' || vt === 'closing') pendingGraph.current = true
      else loadGraph()
      setRefreshKey((k) => k + 1)
      setUpdatedSlug(u.slug)
      if (glowTimer.current) clearTimeout(glowTimer.current)
      glowTimer.current = setTimeout(() => setUpdatedSlug(null), 3000)
    })
    return () => {
      unsub()
      if (glowTimer.current) clearTimeout(glowTimer.current)
    }
  }, [loadGraph, loadWikis])

  useEffect(() => {
    if ((view.type === 'graph' || view.type === 'page') && pendingGraph.current) {
      pendingGraph.current = false
      loadGraph()
    }
  }, [view.type, loadGraph])

  // debounced search (scoped to the current wiki)
  useEffect(() => {
    if (query.trim().length < 2) {
      setResults([])
      return
    }
    const t = setTimeout(() => {
      searchPages(currentWiki, query)
        .then(setResults)
        .catch(() => setResults([]))
    }, 250)
    return () => clearTimeout(t)
  }, [query, currentWiki])

  // Top-10 = the pages that structure this wiki: wikilink degree (in+out)
  // desc, tie-break updated_at recency. Also feeds the rail's row order.
  const pageNodes = useMemo(
    () => (graph ? graph.nodes.filter((n) => n.kind === 'page') : []),
    [graph],
  )
  const topSlugs = useMemo(() => {
    const deg = new Map<string, number>()
    graph?.edges.forEach((e) => {
      if (e.kind !== 'wikilink') return
      deg.set(e.source, (deg.get(e.source) || 0) + 1)
      deg.set(e.target, (deg.get(e.target) || 0) + 1)
    })
    return [...pageNodes]
      .sort(
        (a, b) =>
          (deg.get(b.id) || 0) - (deg.get(a.id) || 0) ||
          (b.updated_at || '').localeCompare(a.updated_at || ''),
      )
      .slice(0, 10)
      .map((n) => n.id)
  }, [graph, pageNodes])
  const listPages = useMemo(
    () => pageNodes.map((n) => ({ slug: n.id, title: n.label })),
    [pageNodes],
  )
  const archivedPages = useMemo(
    () => archived.map((p) => ({ slug: p.slug, title: p.title || p.slug })),
    [archived],
  )
  const titleOf = useCallback(
    (slug: string) => pageNodes.find((n) => n.id === slug)?.label || slug,
    [pageNodes],
  )

  const openPage = useCallback((slug: string) => {
    setQuery('')
    setResults([])
    setView((v) => {
      if (v.type === 'closing') return v // let the close finish
      if (v.type === 'graph') return { type: 'opening', slug }
      return { ...v, slug } // in-page nav: swap content, no choreography
    })
  }, [])

  const closePage = useCallback(() => {
    setView((v) => (v.type === 'page' ? { type: 'closing', slug: v.slug } : v))
  }, [])

  // Open choreography: slide overlays in, fly the top-10 titles from their
  // node rects onto their (still hidden) list rows, then land.
  useEffect(() => {
    if (view.type !== 'opening') return
    let cancelled = false
    const fallback = setTimeout(() => setPanelReady(true), 700) // lost transitionend
    ;(async () => {
      await nextFrame() // overlays painted at their offscreen transform
      if (cancelled) return
      setSlid(true)
      if (reducedMotion()) setPanelReady(true)
      const main = mainRef.current
      const rail = railRef.current
      const layer = ghostRef.current
      if (main && rail && layer && !reducedMotion()) {
        // one read pass: node rects + row rects. The rail is mid-slide, so
        // project each row to the rail's final position (left: 0 in main).
        const mainRect = main.getBoundingClientRect()
        const dx = mainRect.left - rail.getBoundingClientRect().left
        const flights: Flight[] = []
        for (const s of topSlugs) {
          const nodeEl = main.querySelector(`[data-testid="wiki-node-${CSS.escape(s)}"]`)
          const rowEl = rail.querySelector(`[data-wiki-row="${CSS.escape(s)}"]`)
          if (!nodeEl || !rowEl) continue
          const to = relTo(rowEl.getBoundingClientRect(), mainRect)
          to.left += dx
          flights.push({ text: titleOf(s), from: relTo(nodeEl.getBoundingClientRect(), mainRect), to })
        }
        await flyTitles(flights, layer)
      }
      if (cancelled) return
      setLanded(true)
      setView((v) => (v.type === 'opening' ? { type: 'page', slug: v.slug } : v))
    })()
    return () => {
      cancelled = true
      clearTimeout(fallback)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view.type])

  // Close choreography: measure rows and CURRENT node positions (the user
  // may have panned/zoomed before opening), fly back — nodes outside the
  // visible area get a fade instead of an offscreen flight — while the
  // panel/rail slide out; then return to 'graph'.
  useEffect(() => {
    if (view.type !== 'closing') return
    let cancelled = false
    ;(async () => {
      const main = mainRef.current
      const rail = railRef.current
      const layer = ghostRef.current
      const flights: Flight[] = []
      if (main && rail && layer && !reducedMotion()) {
        const mainRect = main.getBoundingClientRect()
        for (const s of topSlugs) {
          const rowEl = rail.querySelector(`[data-wiki-row="${CSS.escape(s)}"]`)
          if (!rowEl) continue
          const nodeEl = main.querySelector(`[data-testid="wiki-node-${CSS.escape(s)}"]`)
          let to: FlightRect | null = null
          if (nodeEl) {
            const nr = nodeEl.getBoundingClientRect()
            const visible =
              nr.right > mainRect.left && nr.left < mainRect.right &&
              nr.bottom > mainRect.top && nr.top < mainRect.bottom
            if (visible) to = relTo(nr, mainRect)
          }
          flights.push({ text: titleOf(s), from: relTo(rowEl.getBoundingClientRect(), mainRect), to })
        }
      }
      setLanded(false) // top rows hide (ghosts take over), rest fade out
      setSlid(false)
      setPanelReady(false)
      const slide = new Promise((r) => setTimeout(r, reducedMotion() ? 0 : 340))
      if (layer) await Promise.all([flyTitles(flights, layer), slide])
      else await slide
      if (cancelled) return
      setView({ type: 'graph' })
    })()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view.type])

  const handleCreateWiki = useCallback(async (name: string, description: string) => {
    const slug = slugifyClient(name)
    if (!slug) return
    await createWiki(slug, name, description)
    await fetchWikis().then(setWikis)
    setCurrentWiki(slug)
  }, [])

  return (
    <div className="h-full flex flex-col" data-testid="wiki-app">
      <header className="flex items-center gap-3 px-4 py-2.5 border-b border-ink-800 shrink-0">
        <button
          onClick={closePage}
          className="flex items-center gap-2 text-sm font-semibold text-ink-100 hover:text-luna-300"
          data-testid="wiki-home"
        >
          <BookOpen size={15} className="text-luna-400" /> Wiki
        </button>
        <WikiSwitcher
          wikis={wikis}
          current={currentWiki}
          onSwitch={setCurrentWiki}
          onCreate={handleCreateWiki}
        />
        <div className="relative ml-auto w-64">
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-500" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search pages…"
            data-testid="wiki-search"
            className="w-full bg-ink-900 border border-ink-700 rounded-md pl-8 pr-3 py-1.5 text-xs text-ink-200 placeholder-ink-600 outline-none focus:border-luna-600"
          />
          {results.length > 0 && (
            <div
              className="absolute top-full mt-1 left-0 right-0 bg-ink-900 border border-ink-700 rounded-md shadow-xl z-50 overflow-hidden"
              data-testid="wiki-search-results"
            >
              {results.map((r) => (
                <button
                  key={r.slug}
                  onClick={() => openPage(r.slug)}
                  className="block w-full text-left px-3 py-2 hover:bg-ink-800"
                >
                  <div className="text-xs text-ink-100">{r.title || r.slug}</div>
                  {r.summary && (
                    <div className="text-[10px] text-ink-500 truncate">{r.summary}</div>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>
        {graph && (
          <span className="text-[11px] text-ink-500 shrink-0" data-testid="wiki-page-count">
            {graph.nodes.filter((n) => n.kind === 'page').length} pages
          </span>
        )}
      </header>

      {/* The graph is mounted for the whole session; opening a page slides
          compositor-only overlays (rail, panel, scrim, ghost layer) over it —
          its viewport, node positions and canvas are never reset. */}
      <main ref={mainRef} className="flex-1 min-h-0 relative overflow-hidden">
        {error && (
          <div className="p-6 text-sm text-red-400" data-testid="wiki-error">
            {error}
          </div>
        )}
        {!error && (
          <>
            {!graph && <div className="p-6 text-sm text-ink-500">Loading graph…</div>}
            {graph && graph.nodes.length === 0 && (
              <div className="p-6 text-sm text-ink-500" data-testid="wiki-empty">
                No pages yet — Luna writes here as it learns.
              </div>
            )}
            {graph && graph.nodes.length > 0 && (
              <GraphView
                graph={graph}
                updatedSlug={updatedSlug}
                onOpenPage={openPage}
                covered={view.type !== 'graph'}
              />
            )}
            {view.type !== 'graph' && graph && (
              <>
                <div className={cn('wiki-scrim', slid && 'wiki-scrim-on')} data-testid="wiki-scrim" />
                <div
                  ref={railRef}
                  className={cn('wiki-rail', slid && 'wiki-rail-open')}
                  data-testid="wiki-list-rail"
                >
                  <PageList
                    pages={listPages}
                    archived={archivedPages}
                    topSlugs={topSlugs}
                    activeSlug={view.slug}
                    landed={landed}
                    onOpen={openPage}
                  />
                </div>
                <div
                  ref={panelRef}
                  className={cn('wiki-panel', slid && 'wiki-panel-open')}
                  style={{ left: LIST_W }}
                  data-testid="wiki-page-panel"
                  onTransitionEnd={(e) => {
                    if (e.target === panelRef.current && e.propertyName === 'transform' && slid)
                      setPanelReady(true)
                  }}
                >
                  <PageView
                    wiki={currentWiki}
                    slug={view.slug}
                    refreshKey={refreshKey}
                    panelReady={panelReady}
                    onClose={closePage}
                    onNavigate={openPage}
                  />
                </div>
                <div ref={ghostRef} className="wiki-ghost-layer" data-testid="wiki-ghost-layer" />
              </>
            )}
          </>
        )}
      </main>
    </div>
  )
}
