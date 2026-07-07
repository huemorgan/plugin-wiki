"""Persistence for plugin-wiki. All reads/writes go through WikiStore so the
tools, routes, provider, and injection share one code path. `[[slug]]`
wikilinks are re-parsed into wiki_links on every body write — authoring prose
IS authoring the graph."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import delete, func, select

from .models import WikiCitation, WikiLink, WikiOpenQuestion, WikiPage, WikiRevision

_WIKILINK_RE = re.compile(r"\[\[([^\[\]|#]+)(?:[|#][^\[\]]*)?\]\]")


class PageNotFound(Exception):
    pass


def slugify(raw: str) -> str:
    s = raw.strip().lower()
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"[^a-z0-9/-]", "", s)
    return re.sub(r"-{2,}", "-", s).strip("-/")


def parse_wikilinks(body: str) -> list[str]:
    seen: list[str] = []
    for raw in _WIKILINK_RE.findall(body or ""):
        slug = slugify(raw)
        if slug and slug not in seen:
            seen.append(slug)
    return seen


def _page_meta(p: WikiPage) -> dict[str, Any]:
    return {
        "slug": p.slug,
        "title": p.title,
        "summary": p.summary,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


class WikiStore:
    def __init__(self, session_factory) -> None:
        self._sf = session_factory

    # ── pages ──────────────────────────────────────────────────────────

    async def upsert_page(
        self,
        slug: str,
        title: str,
        body: str,
        summary: str = "",
        note: str = "",
        mission_id=None,
    ) -> dict[str, Any]:
        slug = slugify(slug)
        if not slug:
            raise ValueError("slug is empty after normalization")
        async with self._sf() as s:
            page = (
                await s.execute(select(WikiPage).where(WikiPage.slug == slug))
            ).scalar_one_or_none()
            created = page is None
            if page is None:
                page = WikiPage(slug=slug, mission_id=mission_id)
                s.add(page)
            page.title = title or page.title or slug
            page.body = body
            if summary:
                page.summary = summary
            if mission_id is not None:
                page.mission_id = mission_id
            await s.flush()
            s.add(WikiRevision(page_id=page.id, body=body, note=note))
            links = await self._reparse_links(s, slug, body)
            await s.commit()
            return {**_page_meta(page), "created": created, "links": links}

    async def patch_page(self, slug: str, find: str, replace: str, note: str = "") -> dict[str, Any]:
        """Literal find/replace edit. `find` must occur exactly once so edits
        are unambiguous (same contract as a code-editor patch)."""
        slug = slugify(slug)
        async with self._sf() as s:
            page = (
                await s.execute(select(WikiPage).where(WikiPage.slug == slug))
            ).scalar_one_or_none()
            if page is None:
                raise PageNotFound(slug)
            count = page.body.count(find)
            if count != 1:
                raise ValueError(
                    f"`find` text occurs {count} times in '{slug}' — must occur exactly once"
                )
            page.body = page.body.replace(find, replace)
            await s.flush()
            s.add(WikiRevision(page_id=page.id, body=page.body, note=note or "patch"))
            links = await self._reparse_links(s, slug, page.body)
            await s.commit()
            return {**_page_meta(page), "links": links}

    async def get_page(self, slug: str) -> dict[str, Any]:
        slug = slugify(slug)
        async with self._sf() as s:
            page = (
                await s.execute(select(WikiPage).where(WikiPage.slug == slug))
            ).scalar_one_or_none()
            if page is None:
                raise PageNotFound(slug)
            citations = (
                (await s.execute(select(WikiCitation).where(WikiCitation.page_id == page.id)))
                .scalars()
                .all()
            )
            revs = (
                await s.execute(
                    select(func.count(WikiRevision.id)).where(WikiRevision.page_id == page.id)
                )
            ).scalar_one()
            out_links = (
                (
                    await s.execute(
                        select(WikiLink.to_page, WikiLink.kind).where(WikiLink.from_page == slug)
                    )
                )
                .all()
            )
            return {
                **_page_meta(page),
                "body": page.body,
                "revision_count": revs,
                "citations": [{"url": c.url, "note": c.note} for c in citations],
                "links_out": [{"to": t, "kind": k} for t, k in out_links],
            }

    async def toc(self) -> list[dict[str, Any]]:
        async with self._sf() as s:
            pages = (
                (await s.execute(select(WikiPage).order_by(WikiPage.slug))).scalars().all()
            )
            return [_page_meta(p) for p in pages]

    async def search(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        """Dumb lexical rank: term hits in title (x3), summary (x2), body (x1).
        Ranking quality is a later optimization (plan: keep search dumb)."""
        terms = [t for t in re.split(r"\W+", query.lower()) if len(t) > 1]
        if not terms:
            return []
        async with self._sf() as s:
            pages = (await s.execute(select(WikiPage))).scalars().all()
        scored = []
        for p in pages:
            title, summary, body = p.title.lower(), p.summary.lower(), p.body.lower()
            score = sum(3 * title.count(t) + 2 * summary.count(t) + body.count(t) for t in terms)
            if score > 0:
                scored.append((score, p))
        scored.sort(key=lambda x: -x[0])
        return [{**_page_meta(p), "score": sc} for sc, p in scored[:limit]]

    async def count_pages(self) -> int:
        async with self._sf() as s:
            return (await s.execute(select(func.count(WikiPage.id)))).scalar_one()

    async def revisions(self, slug: str) -> list[dict[str, Any]]:
        slug = slugify(slug)
        async with self._sf() as s:
            page = (
                await s.execute(select(WikiPage).where(WikiPage.slug == slug))
            ).scalar_one_or_none()
            if page is None:
                raise PageNotFound(slug)
            revs = (
                (
                    await s.execute(
                        select(WikiRevision)
                        .where(WikiRevision.page_id == page.id)
                        .order_by(WikiRevision.created_at)
                    )
                )
                .scalars()
                .all()
            )
            return [
                {"note": r.note, "created_at": r.created_at.isoformat(), "chars": len(r.body)}
                for r in revs
            ]

    # ── citations / questions / links ─────────────────────────────────

    async def add_citation(self, slug: str, url: str, note: str = "") -> dict[str, Any]:
        slug = slugify(slug)
        async with self._sf() as s:
            page = (
                await s.execute(select(WikiPage).where(WikiPage.slug == slug))
            ).scalar_one_or_none()
            if page is None:
                raise PageNotFound(slug)
            s.add(WikiCitation(page_id=page.id, url=url, note=note))
            # citation is the second edge kind: page → source
            s.add(WikiLink(from_page=slug, to_page=url, kind="citation"))
            await s.commit()
            return {"slug": slug, "url": url}

    async def add_question(self, question: str, slug: str | None = None) -> dict[str, Any]:
        async with self._sf() as s:
            page_id = None
            if slug:
                page = (
                    await s.execute(select(WikiPage).where(WikiPage.slug == slugify(slug)))
                ).scalar_one_or_none()
                page_id = page.id if page else None
            q = WikiOpenQuestion(page_id=page_id, question=question)
            s.add(q)
            await s.commit()
            return {"id": str(q.id), "question": question, "status": q.status}

    async def resolve_question(self, question_id: str) -> dict[str, Any]:
        import uuid as _uuid

        try:
            qid = _uuid.UUID(str(question_id))
        except ValueError:
            raise PageNotFound(question_id) from None
        async with self._sf() as s:
            q = await s.get(WikiOpenQuestion, qid)
            if q is None:
                raise PageNotFound(question_id)
            q.status = "resolved"
            await s.commit()
            return {"id": str(q.id), "status": q.status}

    async def list_questions(self, status: str = "open") -> list[dict[str, Any]]:
        async with self._sf() as s:
            rows = (
                (
                    await s.execute(
                        select(WikiOpenQuestion, WikiPage.slug)
                        .outerjoin(WikiPage, WikiOpenQuestion.page_id == WikiPage.id)
                        .where(WikiOpenQuestion.status == status)
                        .order_by(WikiOpenQuestion.created_at)
                    )
                )
                .all()
            )
            return [
                {"id": str(q.id), "question": q.question, "status": q.status, "page": slug}
                for q, slug in rows
            ]

    async def links(self) -> list[dict[str, Any]]:
        async with self._sf() as s:
            rows = (
                (await s.execute(select(WikiLink.from_page, WikiLink.to_page, WikiLink.kind)))
                .all()
            )
            return [{"from": f, "to": t, "kind": k} for f, t, k in rows]

    async def _reparse_links(self, s, slug: str, body: str) -> list[str]:
        """Replace this page's wikilink edge set from its current body.
        Citation edges are managed separately and left untouched."""
        targets = parse_wikilinks(body)
        await s.execute(
            delete(WikiLink).where(WikiLink.from_page == slug, WikiLink.kind == "wikilink")
        )
        for t in targets:
            s.add(WikiLink(from_page=slug, to_page=t, kind="wikilink"))
        return targets
