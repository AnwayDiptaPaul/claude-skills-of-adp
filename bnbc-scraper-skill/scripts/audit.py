#!/usr/bin/env python3
"""Re-measure the data-quality claims in SKILL.md against the current repo copy.
Usage: python audit.py [path-to-bnbc-2020-database]   (default: auto-find via bnbc.py)"""
import glob, json, os, re, sys
sys.path.insert(0, os.path.dirname(__file__))
import bnbc

root = sys.argv[1] if len(sys.argv) > 1 else bnbc.find_root()
if not root:
    sys.exit("no local copy - run `python bnbc.py sync` first")
tabs = glob.glob(f"{root}/Part_*/json/*.json")
empty = low = bad = 0
for f in tabs:
    try:
        d = json.load(open(f, encoding="utf-8"))
    except Exception:
        bad += 1; continue
    empty += not d.get("rows")
    low += d.get("_confidence") == "low"
mmd = glob.glob(f"{root}/Part_*/mmd/*.mmd")
boiler = sum("Analyze Condition" in open(f, encoding="utf-8", errors="ignore").read() for f in mmd)
clauses = glob.glob(f"{root}/Part_*/clauses/*.md")
garbled = sum(bool(bnbc.GARBLE.search(open(f, encoding="utf-8", errors="ignore").read())) for f in clauses)
pat = re.compile(r"\nChapter \d+\n(\d+(?:\.\d+)+)\n")
mis = 0
for f in clauses:
    t = open(f, encoding="utf-8", errors="ignore").read()
    own = re.search(r'clause: "([^"]+)"', t)
    mis += any(i != (own.group(1) if own else "") for i in pat.findall(t))
print(f"mis-segmented (embed other section headings, lower bound): {mis}")
print(f"clauses: {len(clauses)} ({garbled} contain unreadable glyphs)")
print(f"tables : {len(tabs)} total, {empty} empty rows, {low} low-confidence, {bad} unparsable")
print(f"flows  : {len(mmd)} total, {boiler} identical placeholders")
print("figures:", len(glob.glob(f"{root}/Part_*/webp/*.webp")))
