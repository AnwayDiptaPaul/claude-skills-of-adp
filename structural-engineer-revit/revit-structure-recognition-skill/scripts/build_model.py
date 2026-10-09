#!/usr/bin/env python3
"""
build_model.py — the entry point for this skill. Orchestrates
extraction -> resolve_grid_story -> classify_elements, and writes
review_report.html alongside the JSON outputs. Run this rather than the
individual stage scripts unless you're specifically debugging one stage.

Two ways in, same pipeline from stage 2 onward:

    --ifc model.ifc               parse an IFC export (scripts/extract_ifc.py)
    --raw-inventory raw.json      skip extraction — use a raw_inventory.json
                                   you already assembled from live MCP tool
                                   calls (see references/mcp_pyrevit_python_guide.md
                                   or references/mcp_autodesk_official_guide.md)

Usage:
    python3 build_model.py --ifc model.ifc --out output_dir/ \
        [--tolerance-mm 50] [--grade-story "Ground Floor"]
    python3 build_model.py --raw-inventory raw_inventory.json --out output_dir/ \
        [--tolerance-mm 50] [--grade-story "Ground Floor"]

Writes into output_dir/:
    raw_inventory.json        - uninterpreted element inventory (copied through
                                 unchanged if --raw-inventory was used)
    resolved_inventory.json   - + grid/story references
    structural_model.json     - final classified output (see references/schema.md)
    review_report.html        - human-readable summary; open this first
"""
import argparse
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import resolve_grid_story   # noqa: E402
import classify_elements    # noqa: E402


def build_from_ifc(ifc_path, out_dir, tolerance_mm=50.0, grade_story=None):
    # Imported here, not at module level, so the --raw-inventory path (the MCP
    # path, now the primary one) never requires ifcopenshell to be installed.
    import extract_ifc
    import ifcopenshell
    import ifcopenshell.util.unit as uu

    ifc = ifcopenshell.open(str(ifc_path))
    scale = uu.calculate_unit_scale(ifc, "LENGTHUNIT") * 1000.0
    projects = ifc.by_type("IfcProject")

    print(f"[1/3] Extracting from {Path(ifc_path).name} ({ifc.schema}) ...")
    raw = {
        "source_file": Path(ifc_path).name,
        "ifc_schema": ifc.schema,
        "project_name": projects[0].Name if projects else None,
        "grids": extract_ifc.extract_grids(ifc, scale),
        "storeys": extract_ifc.extract_storeys(ifc, scale),
        "elements": extract_ifc.extract_elements(ifc, scale),
    }
    return _run_pipeline(raw, out_dir, tolerance_mm, grade_story)


def build_from_raw_inventory(raw_inventory_path, out_dir, tolerance_mm=50.0, grade_story=None):
    raw = json.loads(Path(raw_inventory_path).read_text())
    for required in ("grids", "storeys", "elements"):
        if required not in raw:
            sys.exit(
                f"raw_inventory.json is missing a top-level '{required}' key. "
                f"See references/schema.md for the shape extract_ifc.py produces — "
                f"a hand-assembled inventory from MCP tool calls needs to match it."
            )
    print(f"[1/3] Using supplied raw inventory ({raw_inventory_path}) ...")
    return _run_pipeline(raw, out_dir, tolerance_mm, grade_story)


def _run_pipeline(raw, out_dir, tolerance_mm, grade_story):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "raw_inventory.json").write_text(json.dumps(raw, indent=2))
    print(f"      {len(raw['elements'])} elements, {len(raw['storeys'])} storeys, {len(raw['grids'])} grid system(s)")

    print(f"[2/3] Resolving grid/story references (tolerance {tolerance_mm:.0f}mm) ...")
    resolved = resolve_grid_story.resolve(raw, tolerance_mm)
    (out_dir / "resolved_inventory.json").write_text(json.dumps(resolved, indent=2))

    print("[3/3] Classifying elements ...")
    model = classify_elements.classify(resolved, grade_story_name=grade_story)
    (out_dir / "structural_model.json").write_text(json.dumps(model, indent=2))

    report_html = render_report(model)
    (out_dir / "review_report.html").write_text(report_html)

    r = model["review"]["counts"]
    print(
        f"\nDone. {r['columns']} columns, {r['framing']} framing, {r['walls']} walls, "
        f"{r['floors']} floors, {r['footings']} footings, {r['piles']} piles.\n"
        f"{r['needs_review']} item(s) flagged for review — open review_report.html first.\n"
        f"Output: {out_dir}/"
    )
    return model


# ------------------------------------------------------------------- report

def _e(x):
    return html.escape(str(x)) if x is not None else ""


def _badge(confidence):
    cls = {"high": "ok", "medium": "warn", "low": "bad"}.get(confidence, "warn")
    return f'<span class="badge {cls}">{_e(confidence)}</span>'


def _needs_review_rows(items):
    if not items:
        return '<tr><td colspan="4" class="muted">Nothing flagged — every classification met the confidence bar.</td></tr>'
    rows = []
    for it in items:
        rows.append(
            "<tr>"
            f'<td class="mono">{_e(it.get("element_id") or "—")}</td>'
            f"<td>{_e(it.get('element_type'))}</td>"
            f"<td>{_e(it.get('reason'))}</td>"
            f"<td>{_e(it.get('detail'))}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def _element_rows(items, columns_spec):
    """columns_spec: list of (header, fn(el)->str) pairs."""
    rows = []
    for el in items:
        cells = "".join(f"<td>{fn(el)}</td>" for _, fn in columns_spec)
        rows.append(f"<tr>{cells}</tr>")
    return "\n".join(rows) if rows else f'<tr><td colspan="{len(columns_spec)}" class="muted">None found.</td></tr>'


def _table(title, columns_spec, items):
    headers = "".join(f"<th>{_e(h)}</th>" for h, _ in columns_spec)
    body = _element_rows(items, columns_spec)
    return f"""
    <section class="card">
      <h2>{_e(title)} <span class="count">({len(items)})</span></h2>
      <div class="table-wrap"><table>
        <thead><tr>{headers}</tr></thead>
        <tbody>{body}</tbody>
      </table></div>
    </section>"""


def render_report(model):
    meta = model["meta"]
    project = model["project"]
    counts = model["review"]["counts"]
    fsum = model["foundation_system_summary"]
    needs_review = model["review"]["needs_review"]

    stat_cards = "".join(
        f'<div class="stat"><div class="stat-num">{v}</div><div class="stat-label">{_e(k)}</div></div>'
        for k, v in counts.items() if k != "needs_review"
    )

    columns_table = _table("Columns", [
        ("ID", lambda e: _e(e["id"])),
        ("Story", lambda e: _e((e.get("story") or e.get("base_story") or {}).get("name"))),
        ("Grid", lambda e: _e(_grid_str(e.get("grid_ref")))),
        ("Frame type", lambda e: _e(e["frame_type"]["value"]) + " " + _badge(e["frame_type"]["confidence"])),
        ("Transfer?", lambda e: "⚠ yes — " + _e((e.get("transfer_flag") or {}).get("note", "")) if e.get("is_transfer_column") else "no"),
    ], model["elements"]["columns"])

    framing_table = _table("Framing", [
        ("ID", lambda e: _e(e["id"])),
        ("Story", lambda e: _e((e.get("story") or {}).get("name"))),
        ("Grid", lambda e: _e(_grid_str(e.get("grid_ref")))),
        ("Frame type", lambda e: _e(e["frame_type"]["value"]) + " " + _badge(e["frame_type"]["confidence"])),
        ("Role", lambda e: _e(e["framing_role"]["value"]) + " " + _badge(e["framing_role"]["confidence"])),
    ], model["elements"]["framing"])

    walls_table = _table("Walls", [
        ("ID", lambda e: _e(e["id"])),
        ("Stories", lambda e: _e(f"{(e.get('base_story') or {}).get('name')} \u2192 {(e.get('top_story') or {}).get('name')}")),
        ("Thickness", lambda e: f"{e.get('thickness_mm'):.0f}mm" if e.get("thickness_mm") else "—"),
        ("Class", lambda e: _wall_class_str(e["wall_class"]) + " " + _badge(e["wall_class"]["confidence"])),
    ], model["elements"]["walls"])

    floors_table = _table("Floors / Slabs", [
        ("ID", lambda e: _e(e["id"])),
        ("Story", lambda e: _e((e.get("story") or {}).get("name"))),
        ("Type", lambda e: _e(e["slab_type"]["value"]) + " " + _badge(e["slab_type"]["confidence"])),
    ], model["elements"]["floors"])

    footings_table = _table("Footings", [
        ("ID", lambda e: _e(e["id"])),
        ("Type", lambda e: _e(e["footing_type"]["value"]) + " " + _badge(e["footing_type"]["confidence"])),
        ("Supports", lambda e: _e(", ".join(e.get("supports") or []) or "—")),
    ], model["elements"]["footings"])

    stories_rows = "\n".join(
        f'<tr><td>{_e(s["name"])}</td><td>{s["elevation_mm"]:.0f}mm</td>'
        f'<td>{("%.0fmm" % s["storey_height_mm"]) if s.get("storey_height_mm") else "—"}</td></tr>'
        for s in model["stories"]
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Structure Recognition Report — {_e(project.get('name') or meta.get('source_file'))}</title>
<style>
  :root {{
    --bg: #0d1117; --panel: #151b23; --border: #2a3341; --text: #e6edf3; --muted: #8b96a5;
    --accent: #5b9dd9; --ok: #3fb950; --warn: #d29922; --bad: #f85149;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    background: var(--bg); color: var(--text); margin: 0; padding: 2.5rem 1.5rem 5rem;
    font: 15px/1.55 -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  }}
  .wrap {{ max-width: 1100px; margin: 0 auto; }}
  h1 {{ font-size: 1.5rem; margin: 0 0 .25rem; letter-spacing: -0.01em; }}
  .subtitle {{ color: var(--muted); margin-bottom: 2rem; font-size: .9rem; }}
  .stats {{ display: flex; flex-wrap: wrap; gap: .75rem; margin-bottom: 2rem; }}
  .stat {{ background: var(--panel); border: 1px solid var(--border); border-radius: 10px;
           padding: .9rem 1.1rem; min-width: 100px; }}
  .stat-num {{ font-size: 1.6rem; font-weight: 600; }}
  .stat-label {{ color: var(--muted); font-size: .78rem; text-transform: uppercase; letter-spacing: .04em; }}
  .card {{ background: var(--panel); border: 1px solid var(--border); border-radius: 12px;
           padding: 1.5rem; margin-bottom: 1.5rem; }}
  .card.flagged {{ border-color: var(--warn); }}
  h2 {{ font-size: 1.05rem; margin: 0 0 1rem; }}
  .count {{ color: var(--muted); font-weight: 400; font-size: .85rem; }}
  table {{ width: 100%; border-collapse: collapse; font-size: .87rem; }}
  th {{ text-align: left; color: var(--muted); font-weight: 500; font-size: .75rem;
        text-transform: uppercase; letter-spacing: .03em; padding: .4rem .6rem;
        border-bottom: 1px solid var(--border); position: sticky; top: 0; background: var(--panel); }}
  td {{ padding: .5rem .6rem; border-bottom: 1px solid rgba(255,255,255,.04); vertical-align: top; }}
  .table-wrap {{ max-height: 420px; overflow-y: auto; border-radius: 8px; }}
  .mono {{ font-family: ui-monospace, "SF Mono", Menlo, monospace; }}
  .muted {{ color: var(--muted); font-style: italic; }}
  .badge {{ display: inline-block; font-size: .68rem; padding: .1rem .45rem; border-radius: 99px;
            text-transform: uppercase; letter-spacing: .03em; font-weight: 600; }}
  .badge.ok {{ background: rgba(63,185,80,.15); color: var(--ok); }}
  .badge.warn {{ background: rgba(210,153,34,.15); color: var(--warn); }}
  .badge.bad {{ background: rgba(248,81,73,.15); color: var(--bad); }}
  .foundation-summary {{ display: flex; gap: 2rem; flex-wrap: wrap; }}
  .foundation-summary div {{ font-size: .85rem; }}
  .foundation-summary b {{ display: block; font-size: 1.1rem; }}
  a {{ color: var(--accent); }}
</style>
</head>
<body>
<div class="wrap">
  <h1>Structure Recognition Report</h1>
  <div class="subtitle">
    {_e(project.get('name') or '(unnamed project)')} &middot; source: {_e(meta.get('source_file'))}
    &middot; schema: {_e(meta.get('ifc_schema'))}
  </div>

  <div class="stats">{stat_cards}</div>

  <section class="card {'flagged' if needs_review else ''}">
    <h2>Needs Review <span class="count">({len(needs_review)})</span></h2>
    <p class="muted" style="margin-top:-.5rem">Walk this list before treating structural_model.json as final — see SKILL.md.</p>
    <div class="table-wrap"><table>
      <thead><tr><th>Element</th><th>Type</th><th>Reason</th><th>Detail</th></tr></thead>
      <tbody>{_needs_review_rows(needs_review)}</tbody>
    </table></div>
  </section>

  <section class="card">
    <h2>Foundation system</h2>
    <div class="foundation-summary">
      <div><b>{_e(fsum['predominant_system'])}</b>predominant system</div>
      {"".join(f'<div><b>{v}</b>{_e(k)}</div>' for k, v in fsum['counts'].items())}
    </div>
    {'<p style="color:var(--warn)">⚠ mixed shallow + deep systems present — see Needs Review.</p>' if fsum['mixed_system_flag'] else ''}
  </section>

  <section class="card">
    <h2>Stories</h2>
    <table>
      <thead><tr><th>Name</th><th>Elevation</th><th>Height to next</th></tr></thead>
      <tbody>{stories_rows}</tbody>
    </table>
  </section>

  {columns_table}
  {framing_table}
  {walls_table}
  {floors_table}
  {footings_table}

</div>
</body>
</html>"""


def _grid_str(ref):
    if not ref:
        return "—"
    if "at" in ref:
        offset = ref.get("offset_mm")
        suffix = "" if ref.get("on_grid") or offset is None else f" (+{offset:.0f}mm)"
        return f"{ref['at'][0] or '?'}/{ref['at'][1] or '?'}" + suffix
    if ref.get("along_gridline"):
        bay = "-".join(ref.get("spans_bay") or []) or "?"
        return f"along {ref['along_gridline']}, bay {bay}"
    return "off-grid"


def _wall_class_str(wc):
    if wc.get("dual_role"):
        return f"{wc['primary']} + {wc['secondary']}"
    return wc.get("primary", "unknown")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = ap.add_mutually_exclusive_group(required=True)
    source.add_argument("--ifc", help="Path to an IFC file (extracted via ifcopenshell)")
    source.add_argument("--raw-inventory", help="Path to a pre-assembled raw_inventory.json (from live MCP tool calls)")
    ap.add_argument("--out", required=True, help="Output directory")
    ap.add_argument("--tolerance-mm", type=float, default=50.0)
    ap.add_argument("--grade-story", default=None,
                     help="Story name/substring representing grade level, e.g. 'Ground Floor'")
    args = ap.parse_args()
    if args.ifc:
        build_from_ifc(args.ifc, args.out, tolerance_mm=args.tolerance_mm, grade_story=args.grade_story)
    else:
        build_from_raw_inventory(args.raw_inventory, args.out, tolerance_mm=args.tolerance_mm, grade_story=args.grade_story)


if __name__ == "__main__":
    main()
