"""Minimal `luna_sdk` stub so the plugin package imports without the Luna
runtime (same pattern as plugin-interview). declarative_base/UUID/JSONB are
backed by real SQLAlchemy so models.py still builds, and store tests run
against in-memory aiosqlite."""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest
import pytest_asyncio


def _install_luna_sdk_stub() -> None:
    if "luna_sdk" in sys.modules:
        return

    from sqlalchemy import JSON, Uuid
    from sqlalchemy.orm import DeclarativeBase

    mod = types.ModuleType("luna_sdk")

    class _Kwargs:
        def __init__(self, **kw: Any) -> None:
            self.__dict__.update(kw)

    class PluginManifest(_Kwargs):
        pass

    class SidebarSection(_Kwargs):
        pass

    class ToolDef(_Kwargs):
        pass

    class PluginContext:  # pragma: no cover - structural stand-in
        pass

    class LunaPlugin:  # pragma: no cover - structural stand-in
        manifest: Any

        async def on_load(self, ctx: Any) -> None: ...

    def declarative_base():
        class Base(DeclarativeBase):
            pass

        return Base

    mod.LunaPlugin = LunaPlugin
    mod.PluginContext = PluginContext
    mod.PluginManifest = PluginManifest
    mod.SidebarSection = SidebarSection
    mod.ToolDef = ToolDef
    mod.declarative_base = declarative_base
    mod.UUID = Uuid
    mod.JSONB = JSON
    sys.modules["luna_sdk"] = mod


_install_luna_sdk_stub()


@pytest_asyncio.fixture
async def store():
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from plugin_wiki.models import ALL_TABLES
    from plugin_wiki.store import WikiStore

    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        for table in ALL_TABLES:
            await conn.run_sync(table.create, checkfirst=True)
    sf = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield WikiStore(sf)
    await engine.dispose()
