"""plugin-wiki API routes — read routes + the sidebar-pane UI.

Mounted at /api/p/plugin-wiki/* by the loader via manifest.routes_module.
Decoupled to `luna_sdk` — no `import luna.*`.

The pane is a React build (wiki-src/ → plugin_wiki/ui, playbooks pattern);
when the dist is absent we fall back to the phase-1 inline HTML browser."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .models import DEFAULT_WIKI
from .store import PageNotFound, WikiNotFound, WikiStore

_UI_DIR = Path(__file__).parent / "ui"
_NO_CACHE = {"Cache-Control": "no-store"}

_PANE_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Wiki</title><style>
  body { margin:0; font:13px/1.5 -apple-system, sans-serif; background:#0e0e14; color:#ddd; }
  #list { padding:10px; } #page { padding:14px; display:none; }
  .item { padding:8px 10px; border-radius:8px; cursor:pointer; }
  .item:hover { background:#1c1c28; }
  .item b { color:#c9b3ff; display:block; }
  .item span { color:#888; font-size:12px; }
  #page pre { white-space:pre-wrap; font:12px/1.6 ui-monospace, monospace; color:#ccc; }
  a.back { color:#c9b3ff; cursor:pointer; display:inline-block; margin-bottom:10px; }
  .empty { color:#777; padding:20px; text-align:center; }
</style></head><body>
<div id="list"></div>
<div id="page"><a class="back" onclick="back()">&larr; all pages</a><h2 id="ptitle"></h2><pre id="pbody"></pre></div>
<script>
let token = localStorage.getItem('luna.token');
if (!token) { try { token = window.parent.localStorage.getItem('luna.token'); } catch (e) {} }
const hdrs = token ? { Authorization: 'Bearer ' + token } : {};
async function load() {
  const r = await fetch('/api/p/plugin-wiki/pages', { headers: hdrs });
  const pages = await r.json();
  const el = document.getElementById('list');
  if (!pages.length) { el.innerHTML = '<div class="empty">No wiki pages yet — Luna authors them as she learns.</div>'; return; }
  el.innerHTML = pages.map(p => `<div class="item" onclick="open_('${p.slug}')"><b>${p.title || p.slug}</b><span>${p.summary || ''}</span></div>`).join('');
}
async function open_(slug) {
  const r = await fetch('/api/p/plugin-wiki/pages/' + encodeURIComponent(slug), { headers: hdrs });
  if (!r.ok) return;
  const p = await r.json();
  document.getElementById('ptitle').textContent = p.title || p.slug;
  document.getElementById('pbody').textContent = p.body;
  document.getElementById('list').style.display = 'none';
  document.getElementById('page').style.display = 'block';
}
function back() {
  document.getElementById('page').style.display = 'none';
  document.getElementById('list').style.display = 'block';
}
load();
</script></body></html>"""


# Module level, NOT inside register_routes: with `from __future__ import
# annotations` FastAPI resolves the `body: WikiCreate` string annotation from
# module globals — a function-local class silently degrades to a query param.
class WikiCreate(BaseModel):
    slug: str
    name: str
    description: str = ""


def register_routes(app, ctx):
    from luna_sdk import get_current_user

    store = WikiStore(ctx.db_session_factory)
    router = APIRouter(prefix="/api/p/plugin-wiki", tags=["wiki"])

    @router.get("/wikis")
    async def list_wikis(user=Depends(get_current_user)):
        return await store.list_wikis()

    @router.post("/wikis")
    async def create_wiki(body: WikiCreate, user=Depends(get_current_user)):
        try:
            return await store.create_wiki(body.slug, body.name, description=body.description)
        except ValueError as e:
            raise HTTPException(409, str(e)) from e

    @router.get("/pages")
    async def list_pages(
        wiki: str = DEFAULT_WIKI, archived: bool = False, user=Depends(get_current_user)
    ):
        try:
            return await store.toc(wiki=wiki, archived=archived)
        except WikiNotFound as e:
            raise HTTPException(404, "wiki not found") from e

    @router.get("/links")
    async def list_links(wiki: str = DEFAULT_WIKI, user=Depends(get_current_user)):
        try:
            return await store.links(wiki=wiki)
        except WikiNotFound as e:
            raise HTTPException(404, "wiki not found") from e

    @router.get("/questions")
    async def list_questions(
        status: str = "open", wiki: str = DEFAULT_WIKI, user=Depends(get_current_user)
    ):
        try:
            return await store.list_questions(status=status, wiki=wiki)
        except WikiNotFound as e:
            raise HTTPException(404, "wiki not found") from e

    @router.get("/search")
    async def search(q: str, wiki: str = DEFAULT_WIKI, user=Depends(get_current_user)):
        try:
            return await store.search(q, wiki=wiki)
        except WikiNotFound as e:
            raise HTTPException(404, "wiki not found") from e

    @router.get("/graph")
    async def graph(wiki: str = DEFAULT_WIKI, user=Depends(get_current_user)):
        """React Flow-shaped graph for one wiki: page nodes + wikilink/citation
        edges. Wikilink targets without a page yet render as stub nodes."""
        try:
            pages = await store.toc(wiki=wiki)
            links = await store.links(wiki=wiki)
        except WikiNotFound as e:
            raise HTTPException(404, "wiki not found") from e
        # archived pages keep their link rows but have no node — drop their
        # outgoing edges so nothing dangles from a missing source
        live = {p["slug"] for p in pages}
        links = [l for l in links if l["from"] in live]
        nodes = [
            {"id": p["slug"], "label": p["title"] or p["slug"], "kind": "page",
             "summary": p["summary"], "updated_at": p["updated_at"]}
            for p in pages
        ]
        have = {n["id"] for n in nodes}
        for l in links:
            if l["kind"] == "wikilink" and l["to"] not in have:
                nodes.append({"id": l["to"], "label": l["to"], "kind": "stub",
                              "summary": "", "updated_at": None})
                have.add(l["to"])
            elif l["kind"] == "citation" and l["to"] not in have:
                nodes.append({"id": l["to"], "label": l["to"], "kind": "source",
                              "summary": "", "updated_at": None})
                have.add(l["to"])
        edges = [
            {"id": f'{l["from"]}->{l["to"]}#{l["kind"]}', "source": l["from"],
             "target": l["to"], "kind": l["kind"]}
            for l in links
        ]
        return {"nodes": nodes, "edges": edges}

    # declared BEFORE the greedy /pages/{slug:path} route
    @router.get("/pages/{slug:path}/revisions")
    async def page_revisions(slug: str, wiki: str = DEFAULT_WIKI, user=Depends(get_current_user)):
        try:
            return await store.revisions(slug, wiki=wiki)
        except WikiNotFound as e:
            raise HTTPException(404, "wiki not found") from e
        except PageNotFound as e:
            raise HTTPException(404, "page not found") from e

    @router.get("/pages/{slug:path}")
    async def get_page(slug: str, wiki: str = DEFAULT_WIKI, user=Depends(get_current_user)):
        try:
            return await store.get_page(slug, wiki=wiki)
        except WikiNotFound as e:
            raise HTTPException(404, "wiki not found") from e
        except PageNotFound as e:
            raise HTTPException(404, "page not found") from e

    # --- Sidebar pane UI ------------------------------------------------
    # Served unauthenticated: the Shell iframes /ui/ with no auth header;
    # the app inside fetches data with the token it gets via postMessage.

    def _versioned_index() -> Response:
        html = (_UI_DIR / "index.html").read_text()
        try:
            import tomllib

            _v = str(
                tomllib.loads(
                    (Path(__file__).parent / "luna-plugin.toml").read_text()
                )["version"]
            )
        except Exception:  # noqa: BLE001
            _v = "0"
        html = html.replace('.js"', f'.js?v={_v}"').replace('.css"', f'.css?v={_v}"')
        return Response(content=html, media_type="text/html", headers=_NO_CACHE)

    @router.get("/ui/")
    async def serve_ui_root():
        if (_UI_DIR / "index.html").exists():
            return _versioned_index()
        return Response(content=_PANE_HTML, media_type="text/html")

    @router.get("/ui/{path:path}")
    async def serve_ui(path: str):
        if not path or path == "/":
            path = "index.html"
        target = (_UI_DIR / path).resolve()
        if not str(target).startswith(str(_UI_DIR.resolve())):
            raise HTTPException(403, "Forbidden")
        if not target.exists():
            if (_UI_DIR / "index.html").exists():
                return _versioned_index()
            raise HTTPException(404, "Not found")
        return FileResponse(str(target), headers=_NO_CACHE)

    app.include_router(router)
