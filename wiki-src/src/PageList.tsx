import { FileText } from 'lucide-react'
import { cn } from './lib/cn'

export type ListPage = { slug: string; title: string }

/** Left rail shown while a page is open. The top-ranked rows are the flight
 * targets: they stay invisible until the ghosts land on them, the remaining
 * rows fade in after. Rows carry data-wiki-row so the choreography in App
 * can measure them without threading refs through here. */
export function PageList({
  pages,
  topSlugs,
  activeSlug,
  landed,
  onOpen,
}: {
  pages: ListPage[]
  topSlugs: string[]
  activeSlug: string | null
  landed: boolean
  onOpen: (slug: string) => void
}) {
  const rank = new Map(topSlugs.map((s, i) => [s, i]))
  const top = pages
    .filter((p) => rank.has(p.slug))
    .sort((a, b) => rank.get(a.slug)! - rank.get(b.slug)!)
  const rest = pages
    .filter((p) => !rank.has(p.slug))
    .sort((a, b) => (a.title || a.slug).localeCompare(b.title || b.slug))

  return (
    <nav className="h-full overflow-y-auto py-2" data-testid="wiki-page-list">
      <div className="px-3 pb-1 text-[10px] uppercase tracking-wide text-ink-500">Pages</div>
      {[...top, ...rest].map((p, i) => {
        const isTop = rank.has(p.slug)
        return (
          <button
            key={p.slug}
            data-wiki-row={p.slug}
            onClick={() => onOpen(p.slug)}
            className={cn(
              'flex w-full items-center gap-1.5 text-left px-3 py-1.5 text-xs hover:bg-ink-800',
              p.slug === activeSlug ? 'text-luna-300 bg-ink-800/60' : 'text-ink-200',
              isTop && !landed && 'invisible',
              !isTop && 'wiki-row-rest',
              !isTop && landed && 'wiki-row-in',
            )}
            style={!isTop && landed ? { transitionDelay: `${Math.min(i * 20, 200)}ms` } : undefined}
          >
            <FileText size={11} className="shrink-0 text-luna-400" />
            <span className="truncate">{p.title || p.slug}</span>
          </button>
        )
      })}
    </nav>
  )
}
