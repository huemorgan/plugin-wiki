import { useCallback, useEffect, useRef, useState } from 'react'
import { Search, BookOpen, ChevronDown, Plus, Library } from 'lucide-react'
import {
  fetchGraph,
  fetchWikis,
  createWiki,
  searchPages,
  type Graph,
  type PageMeta,
  type WikiMeta,
} from './lib/api'
import { subscribeWikiUpdates } from './lib/events'
import { GraphView } from './GraphView'
import { PageView } from './PageView'

type View = { type: 'graph' } | { type: 'page'; slug: string }

const WIKI_KEY = 'luna.wiki.current'

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
  const [wikis, setWikis] = useState<WikiMeta[]>([])
  const [currentWiki, setCurrentWiki] = useState<string>(
    () => localStorage.getItem(WIKI_KEY) || 'main',
  )
  const [error, setError] = useState<string | null>(null)
  const [updatedSlug, setUpdatedSlug] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<PageMeta[]>([])
  const glowTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const wikiRef = useRef(currentWiki)
  wikiRef.current = currentWiki

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
  }, [])

  useEffect(loadWikis, [loadWikis])
  useEffect(() => {
    localStorage.setItem(WIKI_KEY, currentWiki)
    setGraph(null)
    setView({ type: 'graph' })
    loadGraph()
  }, [currentWiki, loadGraph])

  // Live updates: agent writes refresh the wiki list (counts, descriptions)
  // always, and the graph + open page only when they touch the current wiki.
  useEffect(() => {
    const unsub = subscribeWikiUpdates((u) => {
      loadWikis()
      if (u.wiki && u.wiki !== wikiRef.current) return
      loadGraph()
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

  const openPage = useCallback((slug: string) => {
    setView({ type: 'page', slug })
    setQuery('')
    setResults([])
  }, [])

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
          onClick={() => setView({ type: 'graph' })}
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

      <main className="flex-1 min-h-0">
        {error && (
          <div className="p-6 text-sm text-red-400" data-testid="wiki-error">
            {error}
          </div>
        )}
        {!error && view.type === 'graph' && (
          <>
            {!graph && <div className="p-6 text-sm text-ink-500">Loading graph…</div>}
            {graph && graph.nodes.length === 0 && (
              <div className="p-6 text-sm text-ink-500" data-testid="wiki-empty">
                No pages yet — Luna writes here as it learns.
              </div>
            )}
            {graph && graph.nodes.length > 0 && (
              <GraphView graph={graph} updatedSlug={updatedSlug} onOpenPage={openPage} />
            )}
          </>
        )}
        {!error && view.type === 'page' && (
          <PageView
            wiki={currentWiki}
            slug={view.slug}
            refreshKey={refreshKey}
            onBack={() => setView({ type: 'graph' })}
            onNavigate={openPage}
          />
        )}
      </main>
    </div>
  )
}
