import { useCallback, useEffect, useRef, useState } from 'react'
import { Search, BookOpen } from 'lucide-react'
import { fetchGraph, searchPages, type Graph, type PageMeta } from './lib/api'
import { subscribeWikiUpdates } from './lib/events'
import { GraphView } from './GraphView'
import { PageView } from './PageView'

type View = { type: 'graph' } | { type: 'page'; slug: string }

export function App() {
  const [view, setView] = useState<View>({ type: 'graph' })
  const [graph, setGraph] = useState<Graph | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [updatedSlug, setUpdatedSlug] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<PageMeta[]>([])
  const glowTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const loadGraph = useCallback(() => {
    fetchGraph()
      .then((g) => {
        setGraph(g)
        setError(null)
      })
      .catch((e) => setError(String(e)))
  }, [])

  useEffect(loadGraph, [loadGraph])

  // Live updates: any agent write/patch/cite refreshes the graph and the
  // open page, and briefly glows the touched node.
  useEffect(() => {
    const unsub = subscribeWikiUpdates((u) => {
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
  }, [loadGraph])

  // debounced search
  useEffect(() => {
    if (query.trim().length < 2) {
      setResults([])
      return
    }
    const t = setTimeout(() => {
      searchPages(query)
        .then(setResults)
        .catch(() => setResults([]))
    }, 250)
    return () => clearTimeout(t)
  }, [query])

  const openPage = useCallback((slug: string) => {
    setView({ type: 'page', slug })
    setQuery('')
    setResults([])
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
