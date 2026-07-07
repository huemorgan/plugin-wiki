"""plugin-wiki API routes — read-only page browser (left-pane iframe).

Mounted at /api/p/plugin-wiki/* by the loader via manifest.routes_module.
Decoupled to `luna_sdk` — no `import luna.*`."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response

from .store import PageNotFound, WikiStore

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


def register_routes(app, ctx):
    from luna_sdk import get_current_user

    store = WikiStore(ctx.db_session_factory)
    router = APIRouter(prefix="/api/p/plugin-wiki", tags=["wiki"])

    @router.get("/pages")
    async def list_pages(user=Depends(get_current_user)):
        return await store.toc()

    @router.get("/links")
    async def list_links(user=Depends(get_current_user)):
        return await store.links()

    @router.get("/questions")
    async def list_questions(status: str = "open", user=Depends(get_current_user)):
        return await store.list_questions(status=status)

    @router.get("/pages/{slug:path}")
    async def get_page(slug: str, user=Depends(get_current_user)):
        try:
            return await store.get_page(slug)
        except PageNotFound as e:
            raise HTTPException(404, "page not found") from e

    # --- Sidebar pane UI (single inline page; real UI lands in phase 1.5) ---

    @router.get("/ui/")
    async def serve_ui():
        return Response(content=_PANE_HTML, media_type="text/html")

    app.include_router(router)
