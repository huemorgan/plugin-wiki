"""Luna plan 089 — every ToolDef declares agent-state modes.

Declared modes are honored exactly by core tool filtering. Write tools
(including wiki_cite / wiki_ask, which record wiki notes and are
planning-legitimate) carry planning/building/fix_approve/fix_publish;
read-only tools additionally carry identify.
"""

from __future__ import annotations

from types import SimpleNamespace

from plugin_wiki.tools import register_tools

WRITE_MODES = ["planning", "building", "fix_approve", "fix_publish"]
READ_MODES = ["planning", "building", "identify", "fix_approve", "fix_publish"]

WRITE_TOOLS = {
    "wiki_create_wiki",
    "wiki_update_wiki",
    "wiki_delete_wiki",
    "wiki_write",
    "wiki_patch",
    "wiki_archive_page",
    "wiki_unarchive_page",
    "wiki_delete_page",
    "wiki_cite",
    "wiki_ask",
    "wiki_resolve_question",
}
READ_TOOLS = {
    "wiki_list_wikis",
    "wiki_toc",
    "wiki_read",
    "wiki_search",
    "wiki_list_questions",
}


class _ToolReg:
    def __init__(self):
        self.defs = {}

    def register(self, _plugin, tool_def, _handler, **_kw):
        self.defs[tool_def.name] = tool_def


def _registered_defs() -> dict:
    reg = _ToolReg()
    ctx = SimpleNamespace(tool_registry=reg)
    register_tools(ctx, store=SimpleNamespace())  # registration never calls the store
    return reg.defs


def test_all_tools_declare_modes():
    defs = _registered_defs()
    assert set(defs) == WRITE_TOOLS | READ_TOOLS
    for name, tool_def in defs.items():
        assert getattr(tool_def, "modes", None), f"{name} must declare modes"


def test_write_tools_have_planning_but_not_identify():
    defs = _registered_defs()
    for name in WRITE_TOOLS:
        assert defs[name].modes == WRITE_MODES, name
        assert "planning" in defs[name].modes
        assert "identify" not in defs[name].modes


def test_read_tools_declare_all_five_modes():
    defs = _registered_defs()
    for name in READ_TOOLS:
        assert defs[name].modes == READ_MODES, name
