# Installing the structural-recognition extension into mcp-server-for-revit-python

Two files here add six structural-specific tools to your existing
[mcp-servers-for-revit/mcp-server-for-revit-python](https://github.com/mcp-servers-for-revit/mcp-server-for-revit-python)
install, following that repo's own documented "Creating Your Own Tools" pattern
exactly (its README, Parts 1–3). Nothing here works standalone — both files are
meant to be copied into your existing clone of that repo.

## 1. Copy the files

```bash
cp structural_recognition_routes.py <your-clone>/revit-mcp-python.extension/revit_mcp/structural_recognition.py
cp structural_recognition_tools.py  <your-clone>/tools/structural_recognition_tools.py
```

## 2. Register the route module

In `<your-clone>/revit-mcp-python.extension/startup.py`, inside `register_routes()`,
add alongside the existing registrations:

```python
from revit_mcp.structural_recognition import register_structural_recognition_routes
# ...
register_structural_recognition_routes(api)
```

## 3. Register the tool module

In `<your-clone>/tools/__init__.py`, inside `register_tools()`, add alongside the
existing registrations:

```python
from .structural_recognition_tools import register_structural_recognition_tools
# ...
register_structural_recognition_tools(mcp_server, revit_get_func, revit_post_func, revit_image_func)
```

## 4. Reload

- In Revit: pyRevit tab → reload the extension (or restart Revit if it doesn't pick up the change).
- Restart your MCP client (Claude Desktop / Claude Code) so it re-reads the tool list.

## 5. Test the Revit-side route directly before trusting the full tool

With a project open in Revit and Routes active, open a browser to:

```
http://localhost:48884/revit_mcp/structural_columns/
```

You should get back JSON with `"status": "success"` and a list of columns. This
is the same pattern the base repo's own README uses to test `/status/` — do this
first. If it 500s, the error detail in the response names which parameter lookup
failed; that's the most likely failure mode (see the caveat in
`structural_recognition_routes.py`'s module docstring — this was written against
the public Revit API but has not been executed against a live session).

Once `/structural_columns/` returns real data, the other five routes
(`/structural_framing/`, `/walls/`, `/floors/`, `/structural_foundations/`,
`/grids/`) share the same helper functions and are very likely to work the same
way — but check at least one more (`/walls/` is the highest-value one to
confirm, since wall classification is where the most is riding on the data
being right) before running the full pipeline.

## If you'd rather not modify your local server yet

`execute_revit_code` is already implemented in the base repo and needs no
installation — it runs arbitrary IronPython against the live document. See
`references/mcp_pyrevit_python_guide.md` for equivalent snippets you can run
through it directly, at the cost of a much noisier response to parse each time
versus these six purpose-built tools.
