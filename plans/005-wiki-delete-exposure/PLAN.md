# 005 — expose wiki deletion (route + guarded tool)

From luna `plans/092-prompt-evolution/fix-plan.md` #4. Evidence: FINDINGS §7-§8 —
a wiki created by accident (`dojo-perform`) could not be removed by any route or
tool; `store.delete_wiki` exists (store.py:179) but nothing exposes it. Rename
already ships (`wiki_update_wiki`).

## Doctrine (unchanged from 003)
Authored knowledge is never mass-destroyed in one call: `delete_wiki` refuses
`main` and refuses non-empty wikis. That stays. Emptying a junk wiki is already
possible page-by-page (`wiki_delete_page`), so exposure completes the path.

## Changes (0.9.0 → 0.10.0)
1. **REST**: `DELETE /wikis/{wiki}` → `store.delete_wiki` (400s surface the
   guard messages). `?purge_pages=true` (owner REST only) deletes remaining
   pages first — one deliberate flag for cleanup jobs, still refuses `main`.
2. **Tool**: `wiki_delete_wiki(wiki)` — thin wrapper, policy `ask`,
   risk `high`, empty-only (NO purge arg for the agent; it can empty
   page-by-page, each with its own approval).
3. Pane: wikis rail already handles a wiki disappearing via on_change events —
   verify, no new UI.

## Tests
- route: deletes empty wiki; 400 on main / non-empty; purge_pages deletes
  pages then wiki; graph/toc consistent after.
- tool: registered with ask policy; empty-only guard holds.

## Ship
pytest → bump toml + manifest to 0.10.0 → commit, tag v0.10.0, push →
package → publish `official` → verify index.json.
