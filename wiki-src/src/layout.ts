import type { Graph, GraphNode } from './lib/api'

/** Condensed ring layout (004). Pages sit on an inner ring, stubs/sources on
 * an outer ring. The radius grows with page count but is CAPPED so a
 * 100-page wiki still fits the viewport at max zoom-out; when neighbours get
 * closer than a node is wide, odd nodes step onto a slightly smaller radius
 * so labels interleave instead of stacking. Shared by the full graph and the
 * home-page miniatures so both speak the same visual language. */

export const CX = 400
export const CY = 300
export const MAX_RADIUS = 800
export const OUTER_GAP = 180
export const NODE_W = 208 // max-w-52
export const STAGGER = 44

export type Pos = { x: number; y: number }

export function ringLayout(graph: Graph): {
  positions: Map<string, Pos>
  radius: number
  outerRadius: number
} {
  const pages = graph.nodes.filter((n) => n.kind === 'page')
  const rest = graph.nodes.filter((n) => n.kind !== 'page')
  const radius = Math.min(Math.max(160, pages.length * 32), MAX_RADIUS)
  const outerRadius = radius + OUTER_GAP
  const positions = new Map<string, Pos>()
  const place = (list: GraphNode[], r: number) => {
    const n = Math.max(list.length, 1)
    const spacing = (2 * Math.PI * r) / n
    const stagger = spacing < NODE_W ? STAGGER : 0
    list.forEach((node, i) => {
      const angle = (2 * Math.PI * i) / n - Math.PI / 2
      const rr = r - (i % 2 === 1 ? stagger : 0)
      positions.set(node.id, { x: CX + rr * Math.cos(angle), y: CY + rr * Math.sin(angle) })
    })
  }
  place(pages, radius)
  place(rest, outerRadius)
  return { positions, radius, outerRadius }
}
