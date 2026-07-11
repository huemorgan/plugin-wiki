"""Structured extraction from markdown page bodies — no LLM, pure parsing.

0.7.0: consumers (via WikiProvider.get_section / get_table) read a page's
bullets or a table without re-implementing markdown parsing or shipping the
whole body through a prompt. Rules are deliberately plain:

- a "section" is an ATX header (#..######) plus everything until the next
  header of the same or higher level; duplicate headers → first wins
- items are top-to-bottom `- * +` bullets and `1. 1)` numbered lines, text
  kept verbatim after the marker (checkboxes etc. stay — callers parse)
- a table is a GFM pipe table: header row, `---` separator, data rows
"""

from __future__ import annotations

import re
from typing import Any

_HEADER_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.*\S)\s*$")
_NUMBERED_RE = re.compile(r"^\s*\d+[.)]\s+")
_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")


def _norm_header(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _section_lines(body: str, header: str) -> tuple[str, list[str]] | None:
    """(matched header text, lines of the section) — first match wins.
    Empty/None header means the whole body."""
    lines = (body or "").splitlines()
    if not header or not header.strip():
        return ("", lines)
    want = _norm_header(header)
    start = level = None
    matched = ""
    for i, line in enumerate(lines):
        m = _HEADER_RE.match(line)
        if not m:
            continue
        if start is None:
            if _norm_header(m.group(2)) == want:
                start, level, matched = i + 1, len(m.group(1)), m.group(2).strip()
        elif len(m.group(1)) <= level:
            return (matched, lines[start:i])
    if start is None:
        return None
    return (matched, lines[start:])


def _split_row(line: str) -> list[str]:
    inner = line.strip()
    if inner.startswith("|"):
        inner = inner[1:]
    if inner.endswith("|"):
        inner = inner[:-1]
    # split on unescaped pipes
    cells = re.split(r"(?<!\\)\|", inner)
    return [c.replace("\\|", "|").strip() for c in cells]


def get_section(body: str, header: str) -> dict[str, Any] | None:
    """The section under `header`: its raw text plus parsed list items.
    None when the header doesn't exist."""
    found = _section_lines(body, header)
    if found is None:
        return None
    matched, lines = found
    items: list[str] = []
    numbered = 0
    for line in lines:
        m = _ITEM_RE.match(line)
        if m:
            items.append(m.group(1))
            if _NUMBERED_RE.match(line):
                numbered += 1
    return {
        "header": matched,
        "text": "\n".join(lines).strip(),
        "items": items,
        "numbered": bool(items) and numbered == len(items),
    }


def get_table(body: str, header: str = "") -> dict[str, Any] | None:
    """The first GFM pipe table under `header` (whole body when header is
    empty): column names + rows, cells as trimmed strings. None when the
    header doesn't exist or the section holds no table."""
    found = _section_lines(body, header)
    if found is None:
        return None
    matched, lines = found
    for i in range(len(lines) - 1):
        line, sep = lines[i], lines[i + 1]
        if "|" not in line or not _TABLE_SEP_RE.match(sep):
            continue
        columns = _split_row(line)
        rows: list[list[str]] = []
        for row_line in lines[i + 2 :]:
            if "|" not in row_line or not row_line.strip():
                break
            cells = _split_row(row_line)
            # ragged rows are padded/truncated to the header width
            cells = (cells + [""] * len(columns))[: len(columns)]
            rows.append(cells)
        return {"header": matched, "columns": columns, "rows": rows}
    return None
