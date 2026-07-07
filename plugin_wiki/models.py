"""SQLAlchemy rows for plugin-wiki. All tables created idempotently in
on_load (mirrors plugin-interview). Markdown lives in `body`; the link graph
(`wiki_links`) is materialized from `[[slug]]` wikilinks on every write."""

from __future__ import annotations

import uuid as _uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from luna_sdk import UUID, declarative_base

Base = declarative_base()


def _utcnow() -> datetime:
    return datetime.now(UTC)


class WikiPage(Base):
    __tablename__ = "wiki_pages"

    id: Mapped[_uuid.UUID] = mapped_column(UUID(), primary_key=True, default=_uuid.uuid4)
    mission_id: Mapped[_uuid.UUID | None] = mapped_column(UUID(), nullable=True, index=True)
    slug: Mapped[str] = mapped_column(String(256), nullable=False, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class WikiRevision(Base):
    """Append-only page history: one row per wiki_write/wiki_patch."""

    __tablename__ = "wiki_revisions"

    id: Mapped[_uuid.UUID] = mapped_column(UUID(), primary_key=True, default=_uuid.uuid4)
    page_id: Mapped[_uuid.UUID] = mapped_column(
        UUID(), ForeignKey("wiki_pages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class WikiCitation(Base):
    __tablename__ = "wiki_citations"

    id: Mapped[_uuid.UUID] = mapped_column(UUID(), primary_key=True, default=_uuid.uuid4)
    page_id: Mapped[_uuid.UUID] = mapped_column(
        UUID(), ForeignKey("wiki_pages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(Text, default="", nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class WikiOpenQuestion(Base):
    __tablename__ = "wiki_open_questions"

    id: Mapped[_uuid.UUID] = mapped_column(UUID(), primary_key=True, default=_uuid.uuid4)
    page_id: Mapped[_uuid.UUID | None] = mapped_column(
        UUID(), ForeignKey("wiki_pages.id", ondelete="SET NULL"), nullable=True, index=True
    )
    question: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class WikiLink(Base):
    """Materialized graph edge. `wikilink` edges are re-derived from `[[slug]]`
    on every body write; `to_page` is a slug (target page may not exist yet)."""

    __tablename__ = "wiki_links"

    id: Mapped[_uuid.UUID] = mapped_column(UUID(), primary_key=True, default=_uuid.uuid4)
    from_page: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    to_page: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(16), default="wikilink", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    __table_args__ = (Index("ix_wiki_links_edge", "from_page", "to_page", "kind"),)


ALL_TABLES = (
    WikiPage.__table__,
    WikiRevision.__table__,
    WikiCitation.__table__,
    WikiOpenQuestion.__table__,
    WikiLink.__table__,
)
