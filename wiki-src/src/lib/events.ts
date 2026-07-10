import { CORE_BASE } from './api'

export interface WikiUpdate {
  action: string
  slug: string | null
  wiki?: string | null
}

/**
 * Subscribe to agent wiki mutations via the core SSE bridge
 * (GET /api/events?topics=wiki.*, public endpoint). Native EventSource
 * reconnects on its own; we only need the named-event listener.
 */
export function subscribeWikiUpdates(onUpdate: (u: WikiUpdate) => void): () => void {
  const es = new EventSource(`${CORE_BASE}/api/events?topics=wiki.*`)
  es.addEventListener('wiki.updated', (e) => {
    try {
      onUpdate(JSON.parse((e as MessageEvent).data))
    } catch {
      /* malformed payload — skip */
    }
  })
  return () => es.close()
}
