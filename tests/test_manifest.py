"""Manifest sanity: the three version stamps agree, provider registration is
upgrade-safe (phase 8 — the 0.3.0→0.3.1 update rolled back on a duplicate
'wiki' provider left behind by core teardown)."""

from __future__ import annotations

import tomllib
from pathlib import Path

import anyio

ROOT = Path(__file__).parent.parent
PKG = ROOT / "plugin_wiki"


def _toml() -> dict:
    with open(PKG / "luna-plugin.toml", "rb") as f:
        return tomllib.load(f)


def _pyproject() -> dict:
    with open(ROOT / "pyproject.toml", "rb") as f:
        return tomllib.load(f)


def _manifest():
    from plugin_wiki import WikiPlugin

    return WikiPlugin.manifest


def test_versions_agree_everywhere():
    toml, manifest = _toml(), _manifest()
    assert toml["name"] == manifest.name == "plugin-wiki"
    assert toml["version"] == manifest.version == _pyproject()["project"]["version"]


def test_provider_declared():
    assert _toml()["provider"] == _manifest().provider == "wiki"


def test_on_load_is_idempotent_for_the_provider(tmp_path):
    """Simulates the upgrade path on cores whose teardown does not unregister
    providers: the old registration is still present when the new version's
    on_load runs. register() raises on duplicates; on_load must not."""
    from types import SimpleNamespace

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from plugin_wiki import WikiPlugin
    from plugin_wiki.provider import WikiProvider

    class Registry:
        def __init__(self):
            self.impls = {}

        def register(self, key, impl):
            if key in self.impls:
                raise RuntimeError(f"Two implementations registered for provider '{key}'")
            self.impls[key] = impl

        def replace(self, key, impl):
            self.impls[key] = impl

        def has(self, key):
            return key in self.impls

    class Events:
        async def emit(self, *a, **kw):
            pass

    class Tools:
        def register(self, *a, **kw):
            pass

    async def scenario():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/wiki.db")
        ctx = SimpleNamespace(
            engine=engine,
            db_session_factory=async_sessionmaker(engine, expire_on_commit=False),
            provider_registry=Registry(),
            tool_registry=Tools(),
            events=Events(),
        )
        await WikiPlugin().on_load(ctx)          # fresh install
        await WikiPlugin().on_load(ctx)          # upgrade over stale registration
        assert isinstance(ctx.provider_registry.impls["wiki"], WikiProvider)
        await engine.dispose()

    anyio.run(scenario)
