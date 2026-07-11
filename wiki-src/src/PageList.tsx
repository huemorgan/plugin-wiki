import { useState } from 'react'
import { Archive, ChevronDown, ChevronRight, FileText } from 'lucide-react'
import { cn } from './lib/cn'

export type ListPage = { slug: string; title: string }

/** Left rail shown while a page is open. The top-ranked rows are the flight
 * targets: they stay invisible until the ghosts land on them, the remaining
 * rows fade in after. Rows carry data-wiki-row so the choreography in App
 * can measure them without threading refs through here. Archived pages live
 * in a collapsed, dimmed section at the bottom — out of the way, one click
 * from inspection. */
export function PageList({
  pages,
  archived,
  topSlugs,
  activeSlug,
  landed,
  onOpen,
}: {
  pages: ListPage[]
  archived: ListPage[]
  topSlugs: string[]
  activeSlug: string | null
  landed: boolean
  onOpen: (slug: string) => void
}) {
  const [showArchived, setShowArchived] = useState(false)
  const rank = new Map(topSlugs.map((s, i) => [s, i]))
  const top = pages
    .filter((p) => rank.has(p.slug))
    .sort((a, b) => rank.get(a.slug)! - rank.get(b.slug)!)
  const rest = pages
    .filter((p) => !rank.has(p.slug))
    .sort((a, b) => (a.title || a.slug).localeCompare(b.title || b.slug))

  return (
    <nav className="h-full overflow-y-auto py-2 flex flex-col" data-testid="wiki-page-list">
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
      {archived.length > 0 && (
        <div className="mt-auto pt-2" data-testid="wiki-archived-section">
          <button
            onClick={() => setShowArchived((v) => !v)}
            data-testid="wiki-archived-toggle"
            className="flex w-full items-center gap-1.5 px-3 py-1.5 text-[10px] uppercase tracking-wide text-ink-500 hover:text-ink-300 border-t border-ink-800"
          >
            {showArchived ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
            Archived · {archived.length}
          </button>
          {showArchived &&
            archived.map((p) => (
              <button
                key={p.slug}
                onClick={() => onOpen(p.slug)}
                data-testid={`wiki-archived-row-${p.slug}`}
                className={cn(
                  'flex w-full items-center gap-1.5 text-left px-3 py-1.5 text-xs hover:bg-ink-800 opacity-60',
                  p.slug === activeSlug ? 'text-luna-300 bg-ink-800/60' : 'text-ink-500',
                )}
              >
                <Archive size={11} className="shrink-0 text-ink-600" />
                <span className="truncate">{p.title || p.slug}</span>
              </button>
            ))}
        </div>
      )}
    </nav>
  )
}
