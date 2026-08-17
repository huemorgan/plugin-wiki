import { useEffect, useMemo, useState } from 'react'
import { Plus } from 'lucide-react'
import { fetchGraph, type Graph, type WikiMeta } from './lib/api'
import { ringLayout, CX, CY } from './layout'
import { cn } from './lib/cn'

/** 004 — the wiki library. One card per wiki: name, description, page count
 * and a live miniature of its graph drawn with the same ring layout as the
 * full view (boxes on a circle, lines between them). Two cards per row. */

const MINI_W = 320
const MINI_H = 200
const BOX_W = 26
const BOX_H = 10

function MiniGraph({ graph }: { graph: Graph | null }) {
  const scene = useMemo(() => {
    if (!graph || graph.nodes.length === 0) return null
    const { positions, outerRadius, radius } = ringLayout(graph)
    const hasOuter = graph.nodes.some((n) => n.kind !== 'page')
    const extent = (hasOuter ? outerRadius : radius) + BOX_W
    // fit the ring into the miniature: scale by the limiting axis, keep centre
    const s = Math.min((MINI_W - 24) / (2 * extent), (MINI_H - 24) / (2 * extent))
    const tx = (p: { x: number; y: number }) => ({
      x: MINI_W / 2 + (p.x - CX) * s,
      y: MINI_H / 2 + (p.y - CY) * s,
    })
    const nodes = graph.nodes.map((n) => ({ ...n, p: tx(positions.get(n.id)!) }))
    const edges = graph.edges
      .filter((e) => positions.has(e.source) && positions.has(e.target))
      .map((e) => ({ ...e, a: tx(positions.get(e.source)!), b: tx(positions.get(e.target)!) }))
    // shrink boxes a little for dense wikis so the ring stays legible
    const bw = graph.nodes.length > 40 ? BOX_W * 0.6 : graph.nodes.length > 16 ? BOX_W * 0.8 : BOX_W
    const bh = graph.nodes.length > 40 ? BOX_H * 0.7 : BOX_H
    return { nodes, edges, bw, bh }
  }, [graph])

  if (!scene) {
    return (
      <div
        className="flex items-center justify-center text-[11px] text-ink-600"
        style={{ height: MINI_H }}
        data-testid="wiki-card-empty"
      >
        {graph ? 'No pages yet' : '…'}
      </div>
    )
  }
  return (
    <svg
      viewBox={`0 0 ${MINI_W} ${MINI_H}`}
      width="100%"
      height={MINI_H}
      className="block"
      data-testid="wiki-card-graph"
      aria-hidden
    >
      {scene.edges.map((e) => (
        <line
          key={e.id}
          x1={e.a.x}
          y1={e.a.y}
          x2={e.b.x}
          y2={e.b.y}
          stroke={e.kind === 'wikilink' ? '#7c3aed' : '#3f3f46'}
          strokeOpacity={e.kind === 'wikilink' ? 0.55 : 0.5}
          strokeWidth={0.8}
        />
      ))}
      {scene.nodes.map((n) => (
        <rect
          key={n.id}
          x={n.p.x - scene.bw / 2}
          y={n.p.y - scene.bh / 2}
          width={scene.bw}
          height={scene.bh}
          rx={2.5}
          fill="#18181b"
          stroke={n.kind === 'page' ? '#7c3aed' : n.kind === 'stub' ? '#52525b' : '#3f3f46'}
          strokeWidth={1}
          strokeDasharray={n.kind === 'stub' ? '2 2' : undefined}
          opacity={n.kind === 'page' ? 1 : 0.7}
        />
      ))}
    </svg>
  )
}

function WikiCard({
  wiki,
  refreshKey,
  onOpen,
}: {
  wiki: WikiMeta
  refreshKey: number
  onOpen: (slug: string) => void
}) {
  const [graph, setGraph] = useState<Graph | null>(null)
  useEffect(() => {
    let alive = true
    fetchGraph(wiki.slug)
      .then((g) => alive && setGraph(g))
      .catch(() => alive && setGraph({ nodes: [], edges: [] }))
    return () => {
      alive = false
    }
  }, [wiki.slug, wiki.updated_at, refreshKey])

  return (
    <button
      onClick={() => onOpen(wiki.slug)}
      data-testid={`wiki-card-${wiki.slug}`}
      className={cn(
        'wiki-card group text-left rounded-xl border border-ink-800 bg-ink-900/70 overflow-hidden',
        'transition-colors duration-200 ease-out',
        'hover:bg-luna-600/15 hover:border-luna-600/70 focus-visible:bg-luna-600/15 focus-visible:border-luna-600/70 outline-none',
      )}
    >
      <div className="px-5 pt-4 pb-1">
        <div className="text-[10px] uppercase tracking-wider text-ink-500 group-hover:text-luna-300/80 transition-colors">
          {wiki.page_count} page{wiki.page_count === 1 ? '' : 's'}
        </div>
        <div className="text-base font-semibold text-ink-100 truncate mt-0.5">{wiki.name}</div>
        <div className="text-xs text-ink-500 line-clamp-1 min-h-4 mt-0.5">
          {wiki.description || 'Luna writes here as it learns.'}
        </div>
      </div>
      <div className="px-3 pb-3">
        <MiniGraph graph={graph} />
      </div>
    </button>
  )
}

export function WikiHome({
  wikis,
  refreshKey,
  onOpen,
  onCreate,
}: {
  wikis: WikiMeta[]
  refreshKey: number
  onOpen: (slug: string) => void
  onCreate: (name: string, description: string) => Promise<void>
}) {
  const [creating, setCreating] = useState(false)
  const [name, setName] = useState('')
  const [desc, setDesc] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    if (!name.trim() || busy) return
    setBusy(true)
    try {
      await onCreate(name.trim(), desc.trim())
      setName('')
      setDesc('')
      setCreating(false)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="h-full overflow-y-auto" data-testid="wiki-home-page">
      <div className="max-w-4xl mx-auto px-6 py-6">
        <div className="mb-5">
          <div className="text-[10px] uppercase tracking-wider text-ink-500">Library</div>
          <div className="text-lg font-semibold text-ink-100">
            {wikis.length === 0
              ? 'No wikis yet'
              : `${wikis.length} wiki${wikis.length === 1 ? '' : 's'}`}
          </div>
          <div className="text-xs text-ink-500">Pick a wiki to explore its graph.</div>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {wikis.map((w) => (
            <WikiCard key={w.slug} wiki={w} refreshKey={refreshKey} onOpen={onOpen} />
          ))}
          {!creating ? (
            <button
              onClick={() => setCreating(true)}
              data-testid="wiki-home-new"
              className={cn(
                'rounded-xl border border-dashed border-ink-700 text-ink-500 flex flex-col items-center justify-center gap-2 min-h-56',
                'transition-colors duration-200 ease-out hover:bg-luna-600/10 hover:border-luna-600/60 hover:text-luna-300 outline-none focus-visible:border-luna-600/60',
              )}
            >
              <Plus size={18} />
              <span className="text-xs">New wiki</span>
            </button>
          ) : (
            <div
              className="rounded-xl border border-ink-700 bg-ink-900/70 p-5 flex flex-col gap-2 min-h-56"
              data-testid="wiki-home-create-form"
            >
              <div className="text-[10px] uppercase tracking-wider text-ink-500">New wiki</div>
              <input
                autoFocus
                value={name}
                onChange={(e) => setName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && submit()}
                placeholder="Name"
                data-testid="wiki-home-new-name"
                className="w-full bg-ink-950 border border-ink-700 rounded px-2.5 py-1.5 text-sm text-ink-200 placeholder-ink-600 outline-none focus:border-luna-600"
              />
              <input
                value={desc}
                onChange={(e) => setDesc(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && submit()}
                placeholder="What lives in this wiki? (optional)"
                data-testid="wiki-home-new-description"
                className="w-full bg-ink-950 border border-ink-700 rounded px-2.5 py-1.5 text-xs text-ink-200 placeholder-ink-600 outline-none focus:border-luna-600"
              />
              <div className="flex gap-3 justify-end mt-auto">
                <button
                  onClick={() => setCreating(false)}
                  className="text-xs text-ink-500 hover:text-ink-300"
                >
                  Cancel
                </button>
                <button
                  onClick={submit}
                  disabled={!name.trim() || busy}
                  data-testid="wiki-home-new-create"
                  className="text-xs text-luna-300 hover:text-luna-200 disabled:opacity-40"
                >
                  Create
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
