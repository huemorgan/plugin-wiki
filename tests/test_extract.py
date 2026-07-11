"""Extraction API (0.7.0): get_section / get_table parsing against messy
pages, plus the provider surface (page-scoped extraction, newest-first
revisions, `reason` alias on writes)."""

from __future__ import annotations

import pytest

from plugin_wiki.extract import get_section, get_table
from plugin_wiki.provider import WikiProvider

MESSY = """\
# Job Description

Intro prose that is not a list.

## What I do

Some framing prose between the header and the list.

1. **Price increase strategy** — research competitor pricing
2. No-show elimination — deposits and penalties
3) Subscription plan for regulars

Trailing prose after the list.

## Success criteria

- revenue per slot up 20%
- [ ] no-show rate under 5%
- nested detail:
  - deposit collected at booking

### Deep dive

- sub-section bullet — the ### stays inside the ## section above

## What I do

- DUPLICATE header — must never win

## Metrics

| Metric | Target | Notes |
|:-------|-------:|-------|
| revenue/slot | +20% | vs June \\| July baseline |
| no-shows | <5% |
prose right after the table

## Empty

## Another table zone

prose, then no separator:
| not | a table |
| still | prose |
"""


# ── sections ──────────────────────────────────────────────────────────


def test_section_numbered_items_with_prose_between_blocks():
    s = get_section(MESSY, "What I do")
    assert s["header"] == "What I do"
    assert s["items"] == [
        "**Price increase strategy** — research competitor pricing",
        "No-show elimination — deposits and penalties",
        "Subscription plan for regulars",
    ]
    assert s["numbered"] is True
    assert "framing prose" in s["text"]
    # stops at the next same-level header — the duplicate's item is absent
    assert "DUPLICATE" not in s["text"]


def test_section_duplicate_header_first_wins():
    s = get_section(MESSY, "what i do")  # case-insensitive
    assert "Price increase" in s["items"][0]


def test_section_bullets_keep_text_verbatim_and_include_nested():
    s = get_section(MESSY, "Success criteria")
    assert "revenue per slot up 20%" in s["items"]
    assert "[ ] no-show rate under 5%" in s["items"]  # checkbox kept verbatim
    assert any("deposit collected" in i for i in s["items"])  # nested included
    assert s["numbered"] is False


def test_section_spans_subsections_but_not_siblings():
    s = get_section(MESSY, "Success criteria")
    assert "Deep dive" in s["text"]  # ### stays inside the ## section
    assert "Metric" not in s["text"]  # next ## does not


def test_section_missing_header_is_none_and_empty_section_is_empty():
    assert get_section(MESSY, "No Such Header") is None
    s = get_section(MESSY, "Empty")
    assert s["items"] == [] and s["text"] == ""


def test_section_empty_header_means_whole_body():
    s = get_section(MESSY, "")
    assert "Intro prose" in s["text"]


# ── tables ────────────────────────────────────────────────────────────


def test_table_parses_columns_rows_escaped_pipes_and_ragged_rows():
    t = get_table(MESSY, "Metrics")
    assert t["columns"] == ["Metric", "Target", "Notes"]
    assert t["rows"][0] == ["revenue/slot", "+20%", "vs June | July baseline"]
    assert t["rows"][1] == ["no-shows", "<5%", ""]  # ragged row padded
    assert len(t["rows"]) == 2  # prose after the table ends it


def test_table_requires_separator_row():
    assert get_table(MESSY, "Another table zone") is None


def test_table_whole_body_finds_first():
    t = get_table(MESSY)
    assert t["columns"][0] == "Metric"


def test_table_missing_header_is_none():
    assert get_table(MESSY, "No Such Header") is None


# ── provider surface ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_provider_extraction_and_revisions(store):
    p = WikiProvider(store)
    await store.upsert_page("jd", "Job Description", MESSY, note="first draft")
    await store.upsert_page("jd", "Job Description", MESSY + "\n\nmore", note="the job changed")

    s = await p.get_section("jd", "What I do")
    assert s["numbered"] is True and len(s["items"]) == 3
    t = await p.get_table("jd", "Metrics")
    assert t["rows"][0][1] == "+20%"
    assert await p.get_section("missing-page", "x") is None
    assert await p.get_table("jd", "No Such Header") is None

    revs = await p.revisions("jd")
    assert [r["note"] for r in revs] == ["the job changed", "first draft"]  # newest-first
    assert all("created_at" in r and "chars" in r for r in revs)
    assert await p.revisions("missing-page") == []
    assert await p.revisions("jd", wiki="no-such-wiki") == []
