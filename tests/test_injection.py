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
    assert tier2_toc([{"slug": "main", "name": "Main", "description": "", "pages": []}]) == ""


# ── multi-wiki grouping (0.4.0) ───────────────────────────────────────


def _wikis() -> list[dict]:
    return [
        {
            "slug": "main",
            "name": "Main",
            "description": "General mission knowledge.",
            "pages": _pages(3),
        },
        {
            "slug": "client-acme",
            "name": "Client: Acme",
            "description": "Everything about the Acme engagement.",
            "pages": [
                {
                    "slug": "kickoff",
                    "title": "Kickoff",
                    "summary": "Notes from the kickoff call.",
                    "updated_at": "2026-07-30T00:00:00",
                }
            ],
        },
    ]


def test_tier1_mentions_wiki_count_when_multi():
    note = tier1_note(12, 3, wiki_count=4)
    assert "4 isolated wikis" in note
    assert "wiki_list_wikis" in note and "wiki_create_wiki" in note


def test_tier2_groups_by_wiki_with_descriptions():
    out = tier2_toc(_wikis())
    assert "### Client: Acme (wiki: client-acme) — Everything about the Acme engagement." in out
    assert "### Main (wiki: main)" in out
    # busiest-first: client-acme has the most recent page → listed first
    assert out.index("client-acme") < out.index("### Main")
    assert "[[kickoff]]" in out


def test_tier2_single_wiki_has_no_headers():
    out = tier2_toc([{"slug": "main", "name": "Main", "description": "", "pages": _pages(3)}])
    assert "###" not in out
    assert "[[topic-1]]" in out


def test_tier2_flat_page_list_still_works():
    # pre-0.4.0 call shape: a flat list of page metas
    out = tier2_toc(_pages(3))
    assert "[[topic-1]]" in out
    assert "###" not in out
