"""Persistence for plugin-wiki. All reads/writes go through WikiStore so the
tools, routes, provider, and injection share one code path. `[[slug]]`
wikilinks are re-parsed into wiki_links on every body write — authoring prose
IS authoring the graph.

0.4.0: every operation is scoped to a wiki (default `main`). Wikis are fully
isolated — TOC, search, links, and questions never cross the boundary. The
`main` wiki is created lazily so fresh installs and old callers just work."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, select

from .models import (
    DEFAULT_WIKI,
    Wiki,
    WikiCitation,
    WikiLink,
    WikiOpenQuestion,
    WikiPage,
    WikiRevision,
)

_WIKILINK_RE = re.compile(r"\[\[([^\[\]|#]+)(?:[|#][^\[\]]*)?\]\]")


class PageNotFound(Exception):
    pass


class WikiNotFound(Exception):
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


def _age_days(dt) -> float | None:
    # Server-computed age so callers (and the agent) never do date math —
    # the model has no clock, so a raw ISO timestamp can't answer "recent?".
    if dt is None:
        return None
    now = datetime.now(UTC)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return round((now - dt).total_seconds() / 86400, 1)


def _page_meta(p: WikiPage, wiki: str) -> dict[str, Any]:
    return {
        "wiki": wiki,
        "slug": p.slug,
        "title": p.title,
        "summary": p.summary,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        "age_days": _age_days(p.updated_at),
    }


def _wiki_meta(w: Wiki, page_count: int | None = None) -> dict[str, Any]:
    out = {
        "slug": w.slug,
        "name": w.name or w.slug,
        "description": w.description,
        "updated_at": w.updated_at.isoformat() if w.updated_at else None,
    }
    if page_count is not None:
        out["page_count"] = page_count
    return out


class WikiStore:
    def __init__(self, session_factory) -> None:
        self._sf = session_factory
        # async callback({action, slug, wiki}) fired after each committed
        # mutation — the plugin wires this to the event bus for live UIs.
        self.on_change = None

    async def _changed(self, action: str, slug: str | None, wiki: str | None) -> None:
        if self.on_change is None:
            return
        try:
            await self.on_change({"action": action, "slug": slug, "wiki": wiki})
        except Exception:  # noqa: BLE001 — a UI-notify failure must never fail the write
            pass

    # ── wikis ──────────────────────────────────────────────────────────

    async def _wiki_row(self, s, wiki: str) -> Wiki:
        """Resolve a wiki slug inside an open session. `main` self-heals
        (created on first touch) so old callers and fresh installs never 404."""
        slug = slugify(wiki) or DEFAULT_WIKI
        row = (await s.execute(select(Wiki).where(Wiki.slug == slug))).scalar_one_or_none()
        if row is None:
            if slug != DEFAULT_WIKI:
                raise WikiNotFound(slug)
            row = Wiki(slug=DEFAULT_WIKI, name="Main", description="")
            s.add(row)
            await s.flush()
        return row

    async def ensure_default_wiki(self) -> None:
        async with self._sf() as s:
            await self._wiki_row(s, DEFAULT_WIKI)
            await s.commit()

    async def list_wikis(self) -> list[dict[str, Any]]:
        async with self._sf() as s:
            await self._wiki_row(s, DEFAULT_WIKI)  # main always listed
            rows = (
                (
                    await s.execute(
                        select(Wiki, func.count(WikiPage.id))
                        .outerjoin(WikiPage, WikiPage.wiki_id == Wiki.id)
                        .group_by(Wiki.id)
                        .order_by(Wiki.created_at)
                    )
                )
                .all()
            )
            await s.commit()
            return [_wiki_meta(w, n) for w, n in rows]

    async def create_wiki(self, slug: str, name: str, description: str = "") -> dict[str, Any]:
        slug = slugify(slug)
        if not slug:
            raise ValueError("wiki slug is empty after normalization")
        async with self._sf() as s:
            existing = (
                await s.execute(select(Wiki).where(Wiki.slug == slug))
            ).scalar_one_or_none()
            if existing is not None:
                raise ValueError(f"wiki '{slug}' already exists")
            w = Wiki(slug=slug, name=name or slug, description=description)
            s.add(w)
            await s.commit()
            out = _wiki_meta(w, 0)
        await self._changed("wiki_create", None, slug)
        return out

    async def update_wiki(
        self, wiki: str, name: str | None = None, description: str | None = None
    ) -> dict[str, Any]:
        async with self._sf() as s:
            w = await self._wiki_row(s, wiki)
            if name is not None:
                w.name = name
            if description is not None:
                w.description = description
            await s.commit()
            out = _wiki_meta(w)
        await self._changed("wiki_update", None, out["slug"])
        return out

    async def delete_wiki(self, wiki: str) -> dict[str, Any]:
        """Guarded: `main` is undeletable and only empty wikis may go —
        authored knowledge is never mass-deleted by one tool call."""
        slug = slugify(wiki)
        if slug == DEFAULT_WIKI:
            raise ValueError("the main wiki cannot be deleted")
        async with self._sf() as s:
            w = await self._wiki_row(s, slug)
            n_pages = (
                await s.execute(select(func.count(WikiPage.id)).where(WikiPage.wiki_id == w.id))
            ).scalar_one()
            if n_pages:
                raise ValueError(f"wiki '{slug}' still has {n_pages} pages — move or delete them first")
            await s.delete(w)
            await s.commit()
        await self._changed("wiki_delete", None, slug)
        return {"deleted": slug}

    # ── pages ──────────────────────────────────────────────────────────

    async def upsert_page(
        self,
        slug: str,
        title: str,
        body: str,
        summary: str = "",
        note: str = "",
        mission_id=None,
        wiki: str = DEFAULT_WIKI,
    ) -> dict[str, Any]:
        slug = slugify(slug)
        if not slug:
            raise ValueError("slug is empty after normalization")
        async with self._sf() as s:
            w = await self._wiki_row(s, wiki)
            page = (
                await s.execute(
                    select(WikiPage).where(WikiPage.wiki_id == w.id, WikiPage.slug == slug)
                )
            ).scalar_one_or_none()
            created = page is None
            if page is None:
                page = WikiPage(slug=slug, wiki_id=w.id, mission_id=mission_id)
                s.add(page)
            page.title = title or page.title or slug
            page.body = body
            if summary:
                page.summary = summary
            if mission_id is not None:
                page.mission_id = mission_id
            await s.flush()
            s.add(WikiRevision(page_id=page.id, body=body, note=note))
            links = await self._reparse_links(s, w.id, slug, body)
            await s.commit()
            out = {**_page_meta(page, w.slug), "created": created, "links": links}
        await self._changed("write", slug, out["wiki"])
        return out

    async def patch_page(
        self, slug: str, find: str, replace: str, note: str = "", wiki: str = DEFAULT_WIKI
    ) -> dict[str, Any]:
        """Literal find/replace edit. `find` must occur exactly once so edits
        are unambiguous (same contract as a code-editor patch)."""
        slug = slugify(slug)
        async with self._sf() as s:
            w = await self._wiki_row(s, wiki)
            page = (
                await s.execute(
                    select(WikiPage).where(WikiPage.wiki_id == w.id, WikiPage.slug == slug)
                )
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
            links = await self._reparse_links(s, w.id, slug, page.body)
            await s.commit()
            out = {**_page_meta(page, w.slug), "links": links}
        await self._changed("patch", slug, out["wiki"])
        return out

    async def get_page(self, slug: str, wiki: str = DEFAULT_WIKI) -> dict[str, Any]:
        slug = slugify(slug)
        async with self._sf() as s:
            w = await self._wiki_row(s, wiki)
            page = (
                await s.execute(
                    select(WikiPage).where(WikiPage.wiki_id == w.id, WikiPage.slug == slug)
                )
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
                        select(WikiLink.to_page, WikiLink.kind).where(
                            WikiLink.wiki_id == w.id, WikiLink.from_page == slug
                        )
                    )
                )
                .all()
            )
            return {
                **_page_meta(page, w.slug),
                "body": page.body,
                "revision_count": revs,
                "citations": [{"url": c.url, "note": c.note} for c in citations],
                "links_out": [{"to": t, "kind": k} for t, k in out_links],
            }

    async def toc(self, wiki: str = DEFAULT_WIKI) -> list[dict[str, Any]]:
        async with self._sf() as s:
            w = await self._wiki_row(s, wiki)
            pages = (
                (
                    await s.execute(
                        select(WikiPage).where(WikiPage.wiki_id == w.id).order_by(WikiPage.slug)
                    )
                )
                .scalars()
                .all()
            )
            await s.commit()  # main may have been lazily created
            return [_page_meta(p, w.slug) for p in pages]

    async def overview(self) -> list[dict[str, Any]]:
        """All wikis with their TOCs — one call for injection/prompt building."""
        wikis = await self.list_wikis()
        for w in wikis:
            w["pages"] = await self.toc(wiki=w["slug"])
        return wikis

    async def search(
        self, query: str, limit: int = 8, wiki: str = DEFAULT_WIKI
    ) -> list[dict[str, Any]]:
        """Dumb lexical rank: term hits in title (x3), summary (x2), body (x1).
        Ranking quality is a later optimization (plan: keep search dumb)."""
        terms = [t for t in re.split(r"\W+", query.lower()) if len(t) > 1]
        if not terms:
            return []
        async with self._sf() as s:
            w = await self._wiki_row(s, wiki)
            pages = (
                (await s.execute(select(WikiPage).where(WikiPage.wiki_id == w.id)))
                .scalars()
                .all()
            )
            await s.commit()
        scored = []
        for p in pages:
            title, summary, body = p.title.lower(), p.summary.lower(), p.body.lower()
            score = sum(3 * title.count(t) + 2 * summary.count(t) + body.count(t) for t in terms)
            if score > 0:
                scored.append((score, p))
        scored.sort(key=lambda x: -x[0])
        return [{**_page_meta(p, w.slug), "score": sc} for sc, p in scored[:limit]]

    async def count_pages(self, wiki: str | None = None) -> int:
        """Total pages; scoped when `wiki` is given, across all wikis when None."""
        async with self._sf() as s:
            q = select(func.count(WikiPage.id))
            if wiki is not None:
                w = await self._wiki_row(s, wiki)
                q = q.where(WikiPage.wiki_id == w.id)
            return (await s.execute(q)).scalar_one()

    async def revisions(self, slug: str, wiki: str = DEFAULT_WIKI) -> list[dict[str, Any]]:
        slug = slugify(slug)
        async with self._sf() as s:
            w = await self._wiki_row(s, wiki)
            page = (
                await s.execute(
                    select(WikiPage).where(WikiPage.wiki_id == w.id, WikiPage.slug == slug)
                )
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

    async def add_citation(
        self, slug: str, url: str, note: str = "", wiki: str = DEFAULT_WIKI
    ) -> dict[str, Any]:
        slug = slugify(slug)
        async with self._sf() as s:
            w = await self._wiki_row(s, wiki)
            page = (
                await s.execute(
                    select(WikiPage).where(WikiPage.wiki_id == w.id, WikiPage.slug == slug)
                )
            ).scalar_one_or_none()
            if page is None:
                raise PageNotFound(slug)
            s.add(WikiCitation(page_id=page.id, url=url, note=note))
            # citation is the second edge kind: page → source
            s.add(WikiLink(wiki_id=w.id, from_page=slug, to_page=url, kind="citation"))
            await s.commit()
            wslug = w.slug
        await self._changed("cite", slug, wslug)
        return {"wiki": wslug, "slug": slug, "url": url}

    async def add_question(
        self, question: str, slug: str | None = None, wiki: str = DEFAULT_WIKI
    ) -> dict[str, Any]:
        async with self._sf() as s:
            w = await self._wiki_row(s, wiki)
            page_id = None
            if slug:
                page = (
                    await s.execute(
                        select(WikiPage).where(
                            WikiPage.wiki_id == w.id, WikiPage.slug == slugify(slug)
                        )
                    )
                ).scalar_one_or_none()
                page_id = page.id if page else None
            q = WikiOpenQuestion(wiki_id=w.id, page_id=page_id, question=question)
            s.add(q)
            await s.commit()
            out = {"id": str(q.id), "question": question, "status": q.status, "wiki": w.slug}
        await self._changed("ask", slug, out["wiki"])
        return out

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
            out = {"id": str(q.id), "status": q.status}
        await self._changed("resolve", None, None)
        return out

    async def list_questions(
        self, status: str = "open", wiki: str | None = DEFAULT_WIKI
    ) -> list[dict[str, Any]]:
        async with self._sf() as s:
            q = (
                select(WikiOpenQuestion, WikiPage.slug)
                .outerjoin(WikiPage, WikiOpenQuestion.page_id == WikiPage.id)
                .where(WikiOpenQuestion.status == status)
                .order_by(WikiOpenQuestion.created_at)
            )
            if wiki is not None:
                w = await self._wiki_row(s, wiki)
                q = q.where(WikiOpenQuestion.wiki_id == w.id)
            rows = (await s.execute(q)).all()
            await s.commit()
            return [
                {"id": str(r.id), "question": r.question, "status": r.status, "page": slug}
                for r, slug in rows
            ]

    async def links(self, wiki: str = DEFAULT_WIKI) -> list[dict[str, Any]]:
        async with self._sf() as s:
            w = await self._wiki_row(s, wiki)
            rows = (
                (
                    await s.execute(
                        select(WikiLink.from_page, WikiLink.to_page, WikiLink.kind).where(
                            WikiLink.wiki_id == w.id
                        )
                    )
                )
                .all()
            )
            await s.commit()
            return [{"from": f, "to": t, "kind": k} for f, t, k in rows]

    async def _reparse_links(self, s, wiki_id, slug: str, body: str) -> list[str]:
        """Replace this page's wikilink edge set (within its wiki) from its
        current body. Citation edges are managed separately and left alone."""
        targets = parse_wikilinks(body)
        await s.execute(
            delete(WikiLink).where(
                WikiLink.wiki_id == wiki_id,
                WikiLink.from_page == slug,
                WikiLink.kind == "wikilink",
            )
        )
        for t in targets:
            s.add(WikiLink(wiki_id=wiki_id, from_page=slug, to_page=t, kind="wikilink"))
        return targets
