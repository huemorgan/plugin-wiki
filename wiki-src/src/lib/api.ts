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

export interface WikiMeta {
  slug: string
  name: string
  description: string
  page_count: number
  updated_at: string | null
}

export interface PageMeta {
  wiki?: string
  slug: string
  title: string
  summary: string
  updated_at: string | null
  archived?: boolean
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

async function request<T>(method: string, path: string, body?: unknown, retried = false): Promise<T> {
  const token = await getTokenAsync()
  const res = await fetch(`${PLUGIN_BASE}${path}`, {
    method,
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(body !== undefined ? { 'content-type': 'application/json' } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (res.status === 401 && !retried) {
    invalidateToken()
    return request<T>(method, path, body, true)
  }
  if (!res.ok) throw new Error(`${method} ${path} -> ${res.status}`)
  return (await res.json()) as T
}

const get = <T,>(path: string) => request<T>('GET', path)
const w = (wiki: string) => `wiki=${encodeURIComponent(wiki)}`

export const fetchWikis = () => get<WikiMeta[]>('/wikis')
export const createWiki = (slug: string, name: string, description: string) =>
  request<WikiMeta>('POST', '/wikis', { slug, name, description })
export const fetchGraph = (wiki: string) => get<Graph>(`/graph?${w(wiki)}`)
export const fetchArchived = (wiki: string) => get<PageMeta[]>(`/pages?archived=true&${w(wiki)}`)
export const fetchPage = (wiki: string, slug: string) =>
  get<Page>(`/pages/${encodeURIComponent(slug)}?${w(wiki)}`)
export const fetchRevisions = (wiki: string, slug: string) =>
  get<Revision[]>(`/pages/${encodeURIComponent(slug)}/revisions?${w(wiki)}`)
export const fetchQuestions = (wiki: string) => get<Question[]>(`/questions?status=open&${w(wiki)}`)
export const searchPages = (wiki: string, q: string) =>
  get<(PageMeta & { score: number })[]>(`/search?q=${encodeURIComponent(q)}&${w(wiki)}`)
