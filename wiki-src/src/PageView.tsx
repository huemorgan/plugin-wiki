import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { ArrowLeft, Clock, ExternalLink, HelpCircle } from 'lucide-react'
import {
  fetchPage,
  fetchRevisions,
  fetchQuestions,
  type Page,
  type Revision,
  type Question,
} from './lib/api'

/** Turn [[slug]] into markdown links on a #wiki: pseudo-protocol so the
 * renderer's <a> handler can route them in-app. */
function preprocessWikilinks(body: string): string {
  return body.replace(/\[\[([^\]]+)\]\]/g, (_, slug) => `[${slug}](#wiki:${slug})`)
}

export function PageView({
  slug,
  refreshKey,
  onBack,
  onNavigate,
}: {
  slug: string
  refreshKey: number
  onBack: () => void
  onNavigate: (slug: string) => void
}) {
  const [page, setPage] = useState<Page | null>(null)
  const [revisions, setRevisions] = useState<Revision[]>([])
  const [questions, setQuestions] = useState<Question[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    setError(null)
    Promise.all([fetchPage(slug), fetchRevisions(slug), fetchQuestions()])
      .then(([p, revs, qs]) => {
        if (!alive) return
        setPage(p)
        setRevisions(revs)
        setQuestions(qs.filter((q) => q.page === slug))
      })
      .catch((e) => alive && setError(String(e)))
    return () => {
      alive = false
    }
  }, [slug, refreshKey])

  if (error)
    return (
      <div className="p-6 text-sm text-red-400" data-testid="wiki-page-error">
        {error}
        <button onClick={onBack} className="block mt-3 text-luna-300 hover:underline">
          Back to graph
        </button>
      </div>
    )
  if (!page) return <div className="p-6 text-sm text-ink-500">Loading page…</div>

  return (
    <div className="h-full overflow-y-auto" data-testid="wiki-page">
      <div className="max-w-3xl mx-auto px-6 py-5">
        <button
          onClick={onBack}
          data-testid="wiki-page-back"
          className="flex items-center gap-1.5 text-xs text-ink-400 hover:text-ink-200 mb-4"
        >
          <ArrowLeft size={13} /> Graph
        </button>

        <h1 className="text-xl font-semibold text-ink-100" data-testid="wiki-page-title">
          {page.title || page.slug}
        </h1>
        <div className="flex items-center gap-3 text-[11px] text-ink-500 mt-1 mb-4">
          <span className="font-mono">{page.slug}</span>
          {page.updated_at && (
            <span className="flex items-center gap-1">
              <Clock size={11} />
              {new Date(page.updated_at).toLocaleString()}
            </span>
          )}
          <span>
            {page.revision_count} revision{page.revision_count === 1 ? '' : 's'}
          </span>
        </div>

        <div className="wiki-md" data-testid="wiki-page-body">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              a: ({ href, children }) => {
                if (href?.startsWith('#wiki:')) {
                  const target = href.slice('#wiki:'.length)
                  return (
                    <a
                      href={href}
                      onClick={(e) => {
                        e.preventDefault()
                        onNavigate(target)
                      }}
                    >
                      {children}
                    </a>
                  )
                }
                return (
                  <a href={href} target="_blank" rel="noopener noreferrer">
                    {children}
                  </a>
                )
              },
            }}
          >
            {preprocessWikilinks(page.body)}
          </ReactMarkdown>
        </div>

        {questions.length > 0 && (
          <section className="mt-6 border-t border-ink-800 pt-4">
            <h2 className="text-xs font-semibold text-ink-400 uppercase tracking-wide mb-2 flex items-center gap-1.5">
              <HelpCircle size={12} /> Open questions
            </h2>
            <ul className="space-y-1.5">
              {questions.map((q) => (
                <li key={q.id} className="text-xs text-ink-300">
                  {q.question}
                </li>
              ))}
            </ul>
          </section>
        )}

        {page.citations.length > 0 && (
          <section className="mt-6 border-t border-ink-800 pt-4">
            <h2 className="text-xs font-semibold text-ink-400 uppercase tracking-wide mb-2 flex items-center gap-1.5">
              <ExternalLink size={12} /> Sources
            </h2>
            <ul className="space-y-1.5">
              {page.citations.map((c, i) => (
                <li key={i} className="text-xs">
                  <a
                    href={c.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-luna-300 hover:underline break-all"
                  >
                    {c.url}
                  </a>
                  {c.note && <span className="text-ink-500 ml-2">{c.note}</span>}
                </li>
              ))}
            </ul>
          </section>
        )}

        {revisions.length > 0 && (
          <section className="mt-6 border-t border-ink-800 pt-4 pb-8">
            <h2 className="text-xs font-semibold text-ink-400 uppercase tracking-wide mb-2 flex items-center gap-1.5">
              <Clock size={12} /> History
            </h2>
            <ul className="space-y-1">
              {revisions.map((r, i) => (
                <li key={i} className="text-[11px] text-ink-500 flex gap-3">
                  <span className="font-mono shrink-0">
                    {new Date(r.created_at).toLocaleString()}
                  </span>
                  <span className="text-ink-400">{r.note || '(no note)'}</span>
                  <span className="ml-auto shrink-0">{r.chars} chars</span>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </div>
  )
}
