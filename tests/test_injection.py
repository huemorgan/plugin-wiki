"""3-tier injection: tier-1 note shape, tier-2 budget cap on a 20-page wiki
(the R4 evidence), and the guarantee that full bodies never leak into tier 2."""

from __future__ import annotations

from plugin_wiki.injection import TIER2_CHAR_BUDGET, tier1_note, tier2_toc


def _pages(n: int) -> list[dict]:
    return [
        {
            "slug": f"topic-{i}",
            "title": f"Topic {i}",
            "summary": f"Summary of topic {i} — two sentences of context about the domain area.",
            "updated_at": f"2026-07-{(i % 28) + 1:02d}T00:00:00",
        }
        for i in range(n)
    ]


def test_tier1_is_thin():
    note = tier1_note(12, 3)
    assert "12 pages" in note
    assert "wiki_toc" in note and "wiki_read" in note
    assert len(note) / 4 < 120  # ~tokens — stays a thin always-on note


def test_tier2_within_budget_on_20_page_wiki():
    out = tier2_toc(_pages(20))
    tokens = len(out) / 4
    assert tokens <= TIER2_CHAR_BUDGET / 4
    # record the R4 evidence number in test output
    print(f"tier2 on 20-page wiki: {len(out)} chars ≈ {int(tokens)} tokens")


def test_tier2_summaries_only_never_bodies():
    pages = _pages(5)
    for p in pages:
        p["body"] = "FULL-BODY-MARKER should never appear in tier 2"
    out = tier2_toc(pages)
    assert "FULL-BODY-MARKER" not in out
    assert "[[topic-1]]" in out


def test_tier2_overflow_is_reported_not_silent():
    out = tier2_toc(_pages(200))
    assert "more pages" in out
    assert len(out) <= TIER2_CHAR_BUDGET + 100


def test_tier2_empty_wiki_is_empty():
    assert tier2_toc([]) == ""
