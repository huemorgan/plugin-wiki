"""3-tier context injection (retires R4).

Tier 1 — thin always-on capability note (~40 tokens).
Tier 2 — TOC + page summaries, budget-capped, most-recently-updated first.
         `prompt_sections()` has no view of the current user message, so
         ranking is recency, not query relevance (recorded as a core-seam
         limitation; revisit when the hook grows a turn argument).
Tier 3 — full bodies ONLY via the wiki_read tool result, never auto-injected.
"""

from __future__ import annotations

from typing import Any

# ~tokens ≈ chars/4. Tier-2 budget: 600 tokens ≈ 2400 chars on a 20-page wiki.
TIER2_CHAR_BUDGET = 2400


def tier1_note(page_count: int, open_questions: int) -> str:
    return (
        f"You keep a persistent mission wiki ({page_count} pages, "
        f"{open_questions} open questions). It is your long-term domain "
        "knowledge — consult it before answering domain questions and author "
        "it as you learn. Map: `wiki_toc`; full page: `wiki_read`; write: "
        "`wiki_write`/`wiki_patch` (use [[slug]] links)."
    )


def tier2_toc(pages: list[dict[str, Any]], budget: int = TIER2_CHAR_BUDGET) -> str:
    """Summaries only — full bodies never appear here (tier 3 is wiki_read)."""
    if not pages:
        return ""
    ranked = sorted(pages, key=lambda p: p.get("updated_at") or "", reverse=True)
    lines: list[str] = ["## Wiki contents (summaries — wiki_read a slug for the full page)"]
    used = len(lines[0])
    skipped = 0
    for p in ranked:
        summary = (p.get("summary") or "").strip().replace("\n", " ")
        line = f"- [[{p['slug']}]] {p.get('title', '')}" + (f" — {summary}" if summary else "")
        if used + len(line) > budget:
            skipped += 1
            continue
        lines.append(line)
        used += len(line)
    if skipped:
        lines.append(f"- …and {skipped} more pages (see wiki_toc)")
    return "\n".join(lines)
