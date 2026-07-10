"""3-tier context injection (retires R4).

Tier 1 — thin always-on capability note (~40 tokens).
Tier 2 — per-wiki TOC + page summaries, budget-capped. Wikis are ordered by
         their most recent page update, pages by recency inside each wiki, so
         the busiest knowledge naturally dominates the budget.
         `prompt_sections()` has no view of the current user message, so
         ranking is recency, not query relevance (recorded as a core-seam
         limitation; revisit when the hook grows a turn argument).
Tier 3 — full bodies ONLY via the wiki_read tool result, never auto-injected.
"""

from __future__ import annotations

from typing import Any

# ~tokens ≈ chars/4. Tier-2 budget: 600 tokens ≈ 2400 chars on a 20-page wiki.
TIER2_CHAR_BUDGET = 2400


def tier1_note(page_count: int, open_questions: int, wiki_count: int = 1) -> str:
    wikis = (
        f"{wiki_count} isolated wikis" if wiki_count > 1 else "a persistent mission wiki"
    )
    return (
        f"You keep {wikis} ({page_count} pages, "
        f"{open_questions} open questions). They are your long-term domain "
        "knowledge — consult them before answering domain questions and author "
        "them as you learn. Wikis map: `wiki_list_wikis`; pages map: `wiki_toc`; "
        "full page: `wiki_read`; write: `wiki_write`/`wiki_patch` (use [[slug]] "
        "links; pass `wiki` to target a specific wiki, new spaces via "
        "`wiki_create_wiki`)."
    )


def _latest(pages: list[dict[str, Any]]) -> str:
    return max((p.get("updated_at") or "" for p in pages), default="")


def tier2_toc(wikis: list[dict[str, Any]], budget: int = TIER2_CHAR_BUDGET) -> str:
    """Summaries only — full bodies never appear here (tier 3 is wiki_read).

    `wikis`: [{slug, name, description, pages: [page-meta…]}, …] (store.overview()).
    Backward-compatible: a flat list of page dicts is treated as the main wiki.
    """
    if wikis and "pages" not in wikis[0] and "slug" in wikis[0] and "summary" in wikis[0]:
        wikis = [{"slug": "main", "name": "Main", "description": "", "pages": wikis}]
    wikis = [w for w in wikis if w.get("pages")]
    if not wikis:
        return ""

    header = "## Wiki contents (summaries — wiki_read a slug for the full page)"
    lines: list[str] = [header]
    used = len(header)
    skipped = 0
    multi = len(wikis) > 1

    for w in sorted(wikis, key=lambda w: _latest(w["pages"]), reverse=True):
        if multi:
            desc = (w.get("description") or "").strip().replace("\n", " ")
            wl = f"### {w.get('name') or w['slug']} (wiki: {w['slug']})" + (
                f" — {desc}" if desc else ""
            )
            if used + len(wl) > budget:
                skipped += len(w["pages"])
                continue
            lines.append(wl)
            used += len(wl)
        ranked = sorted(w["pages"], key=lambda p: p.get("updated_at") or "", reverse=True)
        for p in ranked:
            summary = (p.get("summary") or "").strip().replace("\n", " ")
            line = f"- [[{p['slug']}]] {p.get('title', '')}" + (f" — {summary}" if summary else "")
            if used + len(line) > budget:
                skipped += 1
                continue
            lines.append(line)
            used += len(line)
    if skipped:
        lines.append(f"- …and {skipped} more pages (see wiki_toc / wiki_list_wikis)")
    return "\n".join(lines)
