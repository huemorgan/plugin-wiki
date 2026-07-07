import { getTokenAsync, invalidateToken } from './auth'

/**
 * The app is served from <prefix>/api/p/plugin-wiki/ui/ — derive both the
 * plugin API base and the core-API root from our own URL so any reverse-proxy
 * prefix survives.
 */
const _path = window.location.pathname
const _uiIdx = _path.lastIndexOf('/ui/')
export const PLUGIN_BASE = _uiIdx >= 0 ? _path.slice(0, _uiIdx) : '/api/p/plugin-wiki'
export const CORE_BASE = PLUGIN_BASE.replace(/\/api\/p\/plugin-wiki$/, '')

export interface PageMeta {
  slug: string
  title: string
  summary: string
  updated_at: string | null
}

export interface Page extends PageMeta {
  body: string
  revision_count: number
  citations: { url: string; note: string }[]
  links_out: { to: string; kind: string }[]
}

export interface Revision {
  note: string
  created_at: string
  chars: number
}

export interface Question {
  id: string
  question: string
  status: string
  page: string
}

export interface GraphNode {
  id: string
  label: string
  kind: 'page' | 'stub' | 'source'
  summary: string
  updated_at: string | null
}

export interface GraphEdge {
  id: string
  source: string
  target: string
  kind: string
}

export interface Graph {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

async function get<T>(path: string, retried = false): Promise<T> {
  const token = await getTokenAsync()
  const res = await fetch(`${PLUGIN_BASE}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (res.status === 401 && !retried) {
    invalidateToken()
    return get<T>(path, true)
  }
  if (!res.ok) throw new Error(`GET ${path} -> ${res.status}`)
  return (await res.json()) as T
}

export const fetchGraph = () => get<Graph>('/graph')
export const fetchPage = (slug: string) => get<Page>(`/pages/${encodeURIComponent(slug)}`)
export const fetchRevisions = (slug: string) =>
  get<Revision[]>(`/pages/${encodeURIComponent(slug)}/revisions`)
export const fetchQuestions = () => get<Question[]>('/questions?status=open')
export const searchPages = (q: string) =>
  get<(PageMeta & { score: number })[]>(`/search?q=${encodeURIComponent(q)}`)
