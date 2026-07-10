import { useCallback, useMemo, useRef, useState } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  type Node,
  type Edge,
  type NodeProps,
  Handle,
  Position,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { FileText, HelpCircle, Link2 } from 'lucide-react'
import { cn } from './lib/cn'
import type { Graph, GraphNode } from './lib/api'

type WikiNodeData = { node: GraphNode; justUpdated: boolean }

function WikiNode({ data }: NodeProps) {
  const { node, justUpdated } = data as WikiNodeData
  const Icon = node.kind === 'page' ? FileText : node.kind === 'stub' ? HelpCircle : Link2
  return (
    <div
      data-testid={`wiki-node-${node.id}`}
      className={cn(
        'rounded-lg border px-3 py-2 max-w-52 bg-ink-900',
        node.kind === 'page' && 'border-luna-600',
        node.kind === 'stub' && 'border-ink-600 border-dashed opacity-70',
        node.kind === 'source' && 'border-ink-700 opacity-60',
        justUpdated && 'node-updated',
      )}
    >
      <Handle type="target" position={Position.Top} className="!bg-ink-600 !border-0 !w-1.5 !h-1.5" />
      <div className="flex items-center gap-1.5">
        <Icon size={12} className={node.kind === 'page' ? 'text-luna-400' : 'text-ink-500'} />
        <span className="text-xs font-medium text-ink-100 truncate">{node.label}</span>
      </div>
      {node.summary && (
        <div className="text-[10px] text-ink-500 mt-0.5 line-clamp-2">{node.summary}</div>
      )}
      <Handle type="source" position={Position.Bottom} className="!bg-ink-600 !border-0 !w-1.5 !h-1.5" />
    </div>
  )
}

const nodeTypes = { wiki: WikiNode }

/** Pages on an inner ring, stubs/sources on an outer ring — deterministic,
 * no layout lib needed at wiki scale (tens of pages). */
function layout(graph: Graph, updatedSlug: string | null): { nodes: Node[]; edges: Edge[] } {
  const pages = graph.nodes.filter((n) => n.kind === 'page')
  const rest = graph.nodes.filter((n) => n.kind !== 'page')
  const place = (list: GraphNode[], radius: number, cx: number, cy: number): Node[] =>
    list.map((n, i) => {
      const angle = (2 * Math.PI * i) / Math.max(list.length, 1) - Math.PI / 2
      return {
        id: n.id,
        type: 'wiki',
        position: { x: cx + radius * Math.cos(angle), y: cy + radius * Math.sin(angle) },
        data: { node: n, justUpdated: n.id === updatedSlug },
      }
    })
  const nodes = [
    ...place(pages, Math.max(160, pages.length * 32), 400, 300),
    ...place(rest, Math.max(340, pages.length * 32 + 180), 400, 300),
  ]
  const edges: Edge[] = graph.edges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    animated: e.kind === 'wikilink',
    style: { stroke: e.kind === 'wikilink' ? '#7c3aed' : '#3f3f46', strokeWidth: 1.2 },
  }))
  return { nodes, edges }
}

/** Screen-space hover card: lives OUTSIDE the zoomed viewport transform, so
 * its text always renders at 100% font size no matter how far the graph is
 * zoomed out. One element for the whole graph, one state update per hover. */
type Hover = { node: GraphNode; x: number; y: number; below: boolean }

export function GraphView({
  graph,
  updatedSlug,
  onOpenPage,
}: {
  graph: Graph
  updatedSlug: string | null
  onOpenPage: (slug: string) => void
}) {
  const { nodes, edges } = useMemo(() => layout(graph, updatedSlug), [graph, updatedSlug])
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [hover, setHover] = useState<Hover | null>(null)

  const clearHover = useCallback(() => setHover(null), [])

  const onEnter = useCallback((event: React.MouseEvent, n: Node) => {
    const container = containerRef.current
    const el = (event.target as HTMLElement).closest('.react-flow__node')
    if (!container || !el) return
    const c = container.getBoundingClientRect()
    const r = el.getBoundingClientRect()
    const below = r.top - c.top < 120 // no room above → flip under the node
    setHover({
      node: (n.data as WikiNodeData).node,
      x: Math.min(Math.max(r.left - c.left + r.width / 2, 8), c.width - 8),
      y: below ? r.bottom - c.top + 8 : r.top - c.top - 8,
      below,
    })
  }, [])

  return (
    <div className="h-full w-full relative" data-testid="wiki-graph" ref={containerRef}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        proOptions={{ hideAttribution: true }}
        nodesDraggable
        nodesConnectable={false}
        onNodeMouseEnter={onEnter}
        onNodeMouseLeave={clearHover}
        onNodeDragStart={clearHover}
        onMove={clearHover}
        onNodeClick={(_, n) => {
          clearHover()
          const wn = (n.data as WikiNodeData).node
          if (wn.kind === 'page') onOpenPage(wn.id)
          else if (wn.kind === 'source') window.open(wn.id, '_blank', 'noopener')
        }}
        colorMode="dark"
      >
        <Background color="#1c1c28" gap={24} />
        <Controls showInteractive={false} />
      </ReactFlow>
      {hover && (
        <div
          data-testid="wiki-hover-card"
          className="absolute z-50 pointer-events-none max-w-72 rounded-lg border border-ink-600 bg-ink-900 px-3 py-2 shadow-xl"
          style={{
            left: hover.x,
            top: hover.y,
            transform: `translate(-50%, ${hover.below ? '0' : '-100%'})`,
          }}
        >
          <div className="text-sm font-medium text-ink-100">{hover.node.label}</div>
          {hover.node.summary && (
            <div className="text-xs text-ink-400 mt-1 leading-relaxed line-clamp-4">
              {hover.node.summary}
            </div>
          )}
          {hover.node.kind !== 'page' && (
            <div className="text-[10px] text-ink-500 mt-1 uppercase tracking-wide">
              {hover.node.kind === 'stub' ? 'not written yet' : 'external source'}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
