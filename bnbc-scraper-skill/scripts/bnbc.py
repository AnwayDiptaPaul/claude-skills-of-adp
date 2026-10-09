#!/usr/bin/env python3
"""
bnbc.py - retrieval CLI for the BNBC 2020 knowledge base
(github.com/AnwayDiptaPaul/bnbc-2020-database)

Commands
  status                      where the data lives, how fresh it is
  sync [--update]             clone / refresh the local copy
  toc [--part N] [--chapter K] [--all]
  route "query" [--part N] [-n 8]       rank clauses by title/number (fast)
  search "query" [--part N] [-n 8]      full-text rank over clause bodies
  pack "query" [--part N] [-n 4]        route+search, then print clause bodies,
                                        table summaries, figure paths (answer-ready context)
  clause ID [--part N] [--children]     print one clause (+ related assets)
  table ID --part N                     print a table JSON (cleaned, with confidence)
  figure ID --part N                    export a figure to PNG and print its path
  verify ID --part N [--span 2]         GROUND TRUTH: locate the clause in the official Part PDF and
                                        render its page(s) to PNG (then `view` them)
  pdf-find "text" --part N [--clause ID] search the Part PDF text layer -> PDF page numbers
  pdf-page N --part P [--span 1]        render PDF page(s) to PNG

Data location, in order: $BNBC_DB, ./bnbc-2020-database, ~/.cache/bnbc-2020-database,
then an auto shallow clone into the cache, then (last resort) raw.githubusercontent.com.
PDFs live on the repo's `resources` branch; they download on demand into ~/.cache/bnbc-pdfs
(override with $BNBC_PDF_DIR). Needs poppler (pdftotext, pdftoppm).
Set BNBC_NO_CLONE=1 to skip the clone and use the raw-file fallback.
"""
import argparse, glob, json, os, re, shutil, subprocess, sys, tarfile, tempfile, urllib.request, io
from collections import OrderedDict

REPO = "AnwayDiptaPaul/bnbc-2020-database"
RAW = f"https://raw.githubusercontent.com/{REPO}/main/"
BLOB = f"https://github.com/{REPO}/blob/main/"
CACHE = os.path.expanduser("~/.cache/bnbc-2020-database")
RAW_CACHE = os.path.expanduser("~/.cache/bnbc-raw")
FIG_OUT = os.path.join(tempfile.gettempdir(), "bnbc_figs")
PDF_RAW = f"https://raw.githubusercontent.com/{REPO}/resources/"
PDF_CACHE = os.path.expanduser("~/.cache/bnbc-pdfs")

PART_DIRS = {
    1: "Part_01_Scope_and_Definitions",
    2: "Part_02_Administration_and_Enforcement",
    3: "Part_03_General_Building_Requirements",
    4: "Part_04_Fire_Protection",
    5: "Part_05_Building_Materials",
    6: "Part_06_Structural_Design",
    7: "Part_07_Construction_Practices_and_Safety",
    8: "Part_08_Building_Services",
    9: "Part_09_Alteration_and_Addition",
    10: "Part_10_Signs_and_Outdoor_Display",
}

# Soft domain priors (from MAP.md): a hit only nudges ranking, never filters.
DOMAIN = {
    1: "definition abbreviation scope unit terminology",
    2: "permit inspection authority penalty enforcement",
    3: "occupancy setback floor area energy parking open space height construction type",
    4: "fire egress exit sprinkler alarm evacuation smoke extinguisher stair",
    5: "cement aggregate brick quality testing material",
    6: ("seismic earthquake wind load dead live snow base shear drift foundation footing pile soil "
        "concrete reinforced steel masonry timber bamboo prestressed ferrocement composite beam "
        "column slab shear wall detailing reinforcement ductile bearing settlement retaining "
        "storey period zone"),
    7: "construction site safety scaffolding demolition excavation formwork",
    8: "electrical wiring plumbing drainage hvac ventilation air-conditioning lift elevator "
       "escalator gas sanitary pipe",
    9: "alteration addition conservation heritage retrofit existing",
    10: "sign billboard hoarding neon display",
}

SYN = {
    "earthquake": ["seismic"], "quake": ["seismic"], "seismic": ["earthquake"],
    "story": ["storey"], "stories": ["storeys"], "storey": ["story"],
    "rcc": ["reinforced", "concrete"], "rc": ["reinforced", "concrete"],
    "pga": ["seismic", "zone"], "sway": ["drift"], "drift": ["sway"],
    "rebar": ["reinforcement"], "stirrup": ["tie", "transverse"],
    "elevator": ["lift"], "lift": ["elevator"],
    "exit": ["egress"], "egress": ["exit"],
    "footing": ["foundation"], "foundation": ["footing"],
    "wind": ["cyclone"], "cyclone": ["wind"],
    "deflection": ["serviceability"], "cover": ["concrete cover"],
}
STOP = set("a an the of for and or to in on at by is are be what which how does do with from as per "
           "under over shall required requirement requirements bnbc code clause section sec "
           "bangladesh national building my me i we it this that".split())

GARBLE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f\ue000-\uf8ff]")


# ----------------------------------------------------------------------------- data source
def _has_db(p):
    return p and os.path.isfile(os.path.join(p, "MAP.md")) and os.path.isdir(os.path.join(p, "Part_06_Structural_Design"))


def _run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def sync(update=False, quiet=False):
    """Shallow-clone (or refresh) the repo into CACHE. Falls back to the codeload tarball."""
    log = (lambda *a: None) if quiet else (lambda *a: print(*a, file=sys.stderr))
    if _has_db(CACHE) and os.path.isdir(os.path.join(CACHE, ".git")):
        if update:
            r = _run(["git", "-C", CACHE, "pull", "--ff-only", "--depth", "1"])
            log("git pull:", (r.stdout or r.stderr).strip()[:200])
        return CACHE
    if _has_db(CACHE) and not update:
        return CACHE
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    if os.path.exists(CACHE):
        import shutil; shutil.rmtree(CACHE, ignore_errors=True)
    log("cloning", REPO, "...")
    try:
        r = _run(["git", "clone", "--depth", "1", f"https://github.com/{REPO}.git", CACHE], timeout=240)
        if r.returncode == 0 and _has_db(CACHE):
            return CACHE
        log("git clone failed:", r.stderr.strip()[:200])
    except Exception as e:
        log("git unavailable:", e)
    try:  # tarball fallback
        url = f"https://codeload.github.com/{REPO}/tar.gz/refs/heads/main"
        data = urllib.request.urlopen(url, timeout=120).read()
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf, tempfile.TemporaryDirectory() as td:
            tf.extractall(td)
            inner = os.path.join(td, os.listdir(td)[0])
            import shutil; shutil.copytree(inner, CACHE)
        return CACHE if _has_db(CACHE) else None
    except Exception as e:
        log("tarball fallback failed:", e)
        return None


def find_root():
    for p in (os.environ.get("BNBC_DB"), os.path.join(os.getcwd(), "bnbc-2020-database"), os.getcwd(), CACHE):
        if _has_db(p):
            return p
    if os.environ.get("BNBC_NO_CLONE"):
        return None
    return sync(quiet=False)


class Src:
    """Reads files from a local checkout, or from raw.githubusercontent.com as a fallback."""
    def __init__(self, root):
        self.root = root

    @property
    def remote(self):
        return self.root is None

    def _raw(self, rel, binary=False):
        os.makedirs(RAW_CACHE, exist_ok=True)
        cp = os.path.join(RAW_CACHE, rel.replace("/", "__"))
        if os.path.exists(cp):
            return open(cp, "rb").read() if binary else open(cp, encoding="utf-8", errors="replace").read()
        try:
            data = urllib.request.urlopen(RAW + urllib.request.quote(rel), timeout=60).read()
        except Exception:
            return None
        open(cp, "wb").write(data)
        return data if binary else data.decode("utf-8", "replace")

    def text(self, rel):
        if self.root:
            p = os.path.join(self.root, rel)
            return open(p, encoding="utf-8", errors="replace").read() if os.path.isfile(p) else None
        return self._raw(rel)

    def local_path(self, rel):
        """Absolute path to a file (downloads it first in remote mode)."""
        if self.root:
            p = os.path.join(self.root, rel)
            return p if os.path.isfile(p) else None
        data = self._raw(rel, binary=True)
        if data is None:
            return None
        out = os.path.join(FIG_OUT, "raw", os.path.basename(rel))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        open(out, "wb").write(data)
        return out

    def glob(self, pattern):
        if not self.root:
            return None
        return sorted(os.path.relpath(p, self.root) for p in glob.glob(os.path.join(self.root, pattern)))


# ----------------------------------------------------------------------------- helpers
def clean(text):
    """Replace unreadable extraction glyphs with a visible marker; return (text, count)."""
    n = len(GARBLE.findall(text))
    text = GARBLE.sub("⟨?⟩", text)
    text = re.sub(r"(⟨\?⟩\s*){3,}", "⟨?⟩…", text)
    return text, n


def stem(w):
    for suf in ("ings", "ing", "es", "s", "ed"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[: -len(suf)]
    return w


def toks(s):
    return [stem(w) for w in re.findall(r"[a-z0-9][a-z0-9.\-]*", s.lower()) if w not in STOP]


def part_arg(v):
    if v is None:
        return None
    v = str(v).strip().lower()
    if v.isdigit() and int(v) in PART_DIRS:
        return int(v)
    for n, d in PART_DIRS.items():
        if v in d.lower():
            return n
    sys.exit(f"unknown part: {v}")


def part_of(path):
    m = re.match(r"Part_(\d\d)_", path)
    return int(m.group(1)) if m else None


def parse_front(text):
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text
    fm = {}
    for ln in text[3:end].strip().splitlines():
        if ":" in ln:
            k, v = ln.split(":", 1)
            v = v.strip()
            if v.startswith("["):
                try:
                    v = json.loads(v)
                except Exception:
                    v = re.findall(r'"([^"]+)"', v)
            else:
                v = v.strip('"')
            fm[k.strip()] = v
    return fm, text[end + 4:].lstrip("\n")


_ROW = re.compile(r"^\|\s*([^|]+?)\s*\|\s*(.*?)\s*\|\s*`([^`]+)`\s*\|\s*$")


def load_index(src, parts=None):
    """Parse every CLAUSE_ROUTER.md clause index -> list of entry dicts."""
    entries = []
    for n in (parts or sorted(PART_DIRS)):
        txt = src.text(f"{PART_DIRS[n]}/CLAUSE_ROUTER.md")
        if not txt:
            continue
        chapter = ""
        for ln in txt.splitlines():
            m = re.match(r"\| \*\*Chapter: (.*?)\*\*", ln)
            if m:
                chapter = m.group(1)
                continue
            m = _ROW.match(ln)
            if m and m.group(3).startswith("clauses/"):
                entries.append(dict(part=n, clause=m.group(1).strip("* "), title=m.group(2),
                                    chapter=chapter, file=f"{PART_DIRS[n]}/{m.group(3)}"))
    return entries


def expand(query):
    base = toks(query)
    syn = []
    for w in re.findall(r"[a-z0-9]+", query.lower()):
        for s in SYN.get(w, []):
            syn += toks(s)
    return base, [s for s in syn if s not in base]


def domain_boost(qtoks):
    hint = {}
    for n, kw in DOMAIN.items():
        hit = len(set(qtoks) & set(toks(kw)))
        if hit:
            hint[n] = 1 + min(0.5, 0.2 * hit)
    return hint


def score_titles(entries, query):
    base, syn = expand(query)
    ids = set(re.findall(r"\d+(?:\.\d+)+|\b\d+\b", query))
    hints = domain_boost(base + syn)
    phrase = " ".join(base)
    out = []
    for e in entries:
        tt = toks(e["title"])
        ts = set(tt)
        s = sum(1.0 for q in base if q in ts) + sum(0.6 for q in syn if q in ts)
        s += 0.4 * sum(1 for q in base if q in set(toks(e["chapter"])))
        if phrase and len(base) > 1 and phrase in " ".join(tt):
            s += 2.0
        if e["clause"] in ids:
            s += 6.0
        elif any(e["clause"].startswith(i + ".") for i in ids):
            s += 0.8
        if s <= 0:
            continue
        s = s / (1 + 0.03 * len(tt)) * hints.get(e["part"], 1.0)
        out.append((s, e))
    out.sort(key=lambda x: (-x[0], len(x[1]["clause"])))
    return out


def fulltext(src, query, parts=None):
    if src.remote:
        return []
    base, syn = expand(query)
    if not base:
        return []
    phrase = " ".join(re.findall(r"[a-z0-9]+", query.lower()))
    res = []
    for n in parts or sorted(PART_DIRS):
        for rel in src.glob(f"{PART_DIRS[n]}/clauses/*.md") or []:
            txt = src.text(rel)
            low = txt.lower()
            words = [stem(w) for w in re.findall(r"[a-z0-9]+", low)]
            cnt = {}
            for w in words:
                cnt[w] = cnt.get(w, 0) + 1
            s = 0.0
            have = 0
            for q in base:
                c = cnt.get(q, 0)
                if c:
                    have += 1
                    s += min(c, 5)
            if not have:
                continue
            s *= (have / len(base)) ** 2
            s += 0.3 * sum(min(cnt.get(q, 0), 3) for q in syn)
            if len(base) > 1 and phrase in low:
                s += 6
            fm, _ = parse_front(txt)
            res.append((s, dict(part=n, clause=fm.get("clause", ""), title=fm.get("title", ""),
                                chapter=fm.get("chapter_title", ""), file=rel)))
    res.sort(key=lambda x: -x[0])
    return res


def hybrid(src, entries, query, parts=None, k=8):
    t = score_titles(entries, query)
    f = fulltext(src, query, parts)
    merged = OrderedDict()
    tm = t[0][0] if t else 1
    fm_ = f[0][0] if f else 1
    for s, e in t:
        merged[e["file"]] = [0.6 * s / tm, e, "title"]
    for s, e in f[:60]:
        if e["file"] in merged:
            merged[e["file"]][0] += 0.4 * s / fm_
            merged[e["file"]][2] = "title+text"
        else:
            merged[e["file"]] = [0.4 * s / fm_, e, "text"]
    ranked = sorted(merged.values(), key=lambda x: -x[0])
    return [(round(s, 3), e, how) for s, e, how in ranked[:k]]


def read_clause(src, rel):
    txt = src.text(rel)
    if txt is None:
        return None
    fm, body = parse_front(txt)
    return fm, body


def sib(rel, kind):
    """Resolve a '../json/x.json' reference from a clause path into a repo-relative path."""
    base = os.path.dirname(os.path.dirname(rel))
    return os.path.normpath(os.path.join(os.path.dirname(rel), kind)).replace("\\", "/") if kind.startswith("..") else f"{base}/{kind}"


def summarize_table(src, rel):
    txt = src.text(rel)
    if txt is None:
        return None
    try:
        d = json.loads(txt)
    except Exception:
        return None
    rows = d.get("rows") or []
    return dict(file=rel, ref=d.get("bnbc_reference", ""), title=d.get("title", ""),
                conf=d.get("_confidence", "?"), nrows=len(rows), ncols=len(d.get("columns") or []))


def md_table(cols, rows):
    cols = [clean(str(c))[0].replace("\n", " ") for c in cols] or [f"c{i+1}" for i in range(len(rows[0]))]
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        r = [clean(str(c))[0].replace("\n", " ").replace("|", "\\|") for c in r]
        r += [""] * (len(cols) - len(r))
        out.append("| " + " | ".join(r[: len(cols)]) + " |")
    return "\n".join(out)


GARBLE_NOTE = ("NOTE: {n} unreadable glyph(s) marked ⟨?⟩ (symbol-font extraction loss: Greek letters, "
               "subscripts, ≤/≥ and similar). Do not guess them - confirm numeric limits against the figure/"
               "table image or the official BNBC before using them in design.")



def window(body, qtoks, max_chars):
    """Keep the heading, then the stretch of the clause where query terms are densest."""
    if not max_chars or len(body) <= max_chars:
        return body, 0
    head = body[: max(200, max_chars // 4)]
    head = head.rsplit("\n", 1)[0] if "\n" in head else head
    rest = body[len(head):]
    budget = max_chars - len(head)
    if not qtoks:
        return head + rest[:budget], len(body) - max_chars
    lines = rest.split("\n")
    hits = [sum(1 for w in re.findall(r"[a-z0-9]+", ln.lower()) if stem(w) in qtoks) for ln in lines]
    best, best_i = -1, 0
    for i in range(len(lines)):
        tot, size, j = 0, 0, i
        while j < len(lines) and size + len(lines[j]) + 1 <= budget:
            tot += hits[j]; size += len(lines[j]) + 1; j += 1
        if tot > best:
            best, best_i, best_j = tot, i, j
    seg = "\n".join(lines[best_i:best_j])
    skipped = len("\n".join(lines[:best_i]))
    mid = f"\n… [{skipped} chars skipped] …\n" if skipped else "\n"
    return head + mid + seg, len(body) - len(head) - len(seg)

def emit_clause(src, e, max_chars=0, assets=True, qtoks=None):
    got = read_clause(src, e["file"])
    if not got:
        print(f"[missing file] {e['file']}")
        return 0
    fm, body = got
    body, n = clean(body)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    body, cut = window(body, qtoks, max_chars)
    if cut > 0:
        body += f"\n… [{cut} more chars; `bnbc.py clause {fm.get('clause', e['clause'])} --part {e['part']}` for full text]"
    print(f"### BNBC 2020 · Part {e['part']} · Sec {fm.get('clause', e['clause'])} — {fm.get('title', e['title'])}")
    print(f"_Chapter {fm.get('chapter', '?')}: {fm.get('chapter_title', e.get('chapter', ''))} · {BLOB}{e['file']}_")
    own = fm.get("clause", e["clause"])
    other = sorted({i for i in re.findall(r"\nChapter \d+\n(\d+(?:\.\d+)+)\n", "\n" + body) if i != own})
    if other:
        print(f"_⚠ file also contains text under other section headings ({', '.join(other[:6])}); cite the inline section number next to the text you use, not this file's id._")
    print()
    print(body)
    if assets:
        tabs = fm.get("related_tables") or []
        figs = fm.get("related_diagrams") or []
        if tabs or figs:
            print("\n**Related assets**")
        for t in tabs:
            rel = sib(e["file"], t)
            s = summarize_table(src, rel)
            if s:
                flag = "rows usable" if (s["conf"] == "high" and s["nrows"] >= 3) else "rows EMPTY/SUSPECT - use clause text, _context or figure"
                print(f"- table `{s['ref']}` ({s['nrows']} rows, conf={s['conf']}, {flag}) → `bnbc.py table {os.path.basename(rel)[9:-5].lstrip('_')} --part {e['part']}`".replace("table  ", "table "))
        for f in figs:
            rel = sib(e["file"], f)
            fid = re.sub(r"^fig_\d+_|\.webp$", "", os.path.basename(rel))
            print(f"- figure `{os.path.basename(rel)}` → `bnbc.py figure {fid} --part {e['part']}`")
    return n


# ----------------------------------------------------------------------------- commands
def cmd_status(a, src):
    print("mode:", "REMOTE (raw.githubusercontent.com, no full-text search)" if src.remote else f"local · {src.root}")
    if src.root and os.path.isdir(os.path.join(src.root, ".git")):
        r = _run(["git", "-C", src.root, "log", "-1", "--format=%h %ci %s"])
        print("commit:", r.stdout.strip())
    if src.root:
        for n, d in PART_DIRS.items():
            c = len(glob.glob(os.path.join(src.root, d, "clauses", "*.md")))
            print(f"  Part {n:>2}: {c:>5} clauses  {d}")


def cmd_sync(a, src):
    p = sync(update=a.update)
    print("ready:" if p else "FAILED - use BNBC_NO_CLONE=1 for raw fallback", p or "")


def cmd_toc(a, src):
    entries = load_index(src, [part_arg(a.part)] if a.part else None)
    chapters = OrderedDict()
    for e in entries:
        chapters.setdefault((e["part"], e["chapter"]), []).append(e)
    for (p, ch), es in chapters.items():
        if a.chapter and a.chapter.lower() not in ch.lower() and a.chapter != es[0]["clause"].split(".")[0]:
            continue
        print(f"## Part {p} · {ch}  ({len(es)} clauses)")
        if a.part and (a.chapter or a.all):
            for e in es:
                if a.all or e["clause"].count(".") <= 2:
                    print(f"  {e['clause']:<12} {e['title']}")


def cmd_route(a, src):
    p = part_arg(a.part)
    entries = load_index(src, [p] if p else None)
    res = score_titles(entries, a.query)[: a.n]
    if a.json:
        print(json.dumps([dict(score=round(s, 2), **e) for s, e in res], indent=1)); return
    if not res:
        print("no title matches - try `search` (full text) or rephrase with code terminology"); return
    for s, e in res:
        print(f"{s:5.2f}  Part {e['part']:>2}  {e['clause']:<12} {e['title']}\n        {e['file']}")


def cmd_search(a, src):
    if src.remote:
        sys.exit("full-text search needs a local copy: run `bnbc.py sync`")
    p = part_arg(a.part)
    res = fulltext(src, a.query, [p] if p else None)[: a.n]
    if a.json:
        print(json.dumps([dict(score=round(s, 2), **e) for s, e in res], indent=1)); return
    for s, e in res:
        print(f"{s:6.1f}  Part {e['part']:>2}  {e['clause']:<12} {e['title']}\n        {e['file']}")
    if not res:
        print("no hits")


def cmd_pack(a, src):
    p = part_arg(a.part)
    parts = [p] if p else None
    entries = load_index(src, parts)
    res = hybrid(src, entries, a.query, parts, a.n)
    if not res:
        print("no matches; rephrase using code terminology (e.g. 'storey drift', 'design base shear')"); return
    b_, s_ = expand(a.query)
    qt = set(b_ + s_)
    print(f"# BNBC 2020 context pack — query: “{a.query}”\n")
    print("Ranked: " + " · ".join(f"{e['part']}:{e['clause']}" for _, e, _ in res) + "\n")
    garbled = 0
    for s, e, how in res:
        garbled += emit_clause(src, e, a.max_chars, qtoks=qt)
        print("\n---\n")
    if garbled:
        print(GARBLE_NOTE.format(n=garbled))
    print("\nReminder: this is an unofficial structured copy. Verify design-critical values against the official BNBC 2020.")


def _find_entries(src, cid, part):
    entries = load_index(src, [part] if part else None)
    exact = [e for e in entries if e["clause"] == cid]
    kids = [e for e in entries if e["clause"].startswith(cid + ".")]
    if not exact and src.root:  # router may omit a file that exists
        for n in ([part] if part else sorted(PART_DIRS)):
            for rel in src.glob(f"{PART_DIRS[n]}/clauses/clause_{cid}_*.md") or []:
                fm, _ = parse_front(src.text(rel))
                exact.append(dict(part=n, clause=cid, title=fm.get("title", ""), chapter=fm.get("chapter_title", ""), file=rel))
    return exact, kids


def cmd_clause(a, src):
    p = part_arg(a.part)
    cid = a.id.lower().replace("sec", "").strip(" .")
    exact, kids = _find_entries(src, cid, p)
    if len(exact) > 1 and not p:
        print(f"Clause {cid} exists in several Parts - showing all ({', '.join(str(e['part']) for e in exact)}); pass --part to pick one.\n")
    n = 0
    for e in exact:
        n += emit_clause(src, e, a.max_chars)
        print()
    if kids and (a.children or not exact):
        print(f"**Sub-clauses of {cid}** ({len(kids)})")
        for e in kids[:80]:
            print(f"  Part {e['part']} · {e['clause']:<12} {e['title']}")
        if a.children:
            print("\n---\n")
            for e in kids[:40]:
                n += emit_clause(src, e, a.max_chars, assets=False)
                print("\n---\n")
    elif not exact:
        print(f"clause {cid} not found - try `route \"{cid}\"` or `toc --part N --chapter K`")
    if n:
        print(GARBLE_NOTE.format(n=n))


def _table_rel(src, pn, tid):
    base = f"{PART_DIRS[pn]}/json/table_{pn:02d}_"
    cands = [f"{base}{tid}.json", f"{base}{tid}..json", f"{base}{tid.rstrip('.')}.json"]
    for c in cands:
        if src.text(c) is not None:
            return c
    if src.root:
        g = src.glob(f"{PART_DIRS[pn]}/json/table_{pn:02d}_{tid}*.json")
        return g[0] if g else None
    return None


def cmd_table(a, src):
    pn = part_arg(a.part)
    if not pn:
        sys.exit("--part is required for tables (ids repeat across Parts)")
    tid = a.id.replace("Table", "").strip()
    rel = _table_rel(src, pn, tid)
    if not rel:
        sys.exit(f"table {tid} not found in Part {pn}")
    d = json.loads(src.text(rel))
    print(f"### {d.get('bnbc_reference')} · Part {pn} · confidence={d.get('_confidence')}  ({BLOB}{rel})")
    print(f"title field: {clean(d.get('title', ''))[0]!r} (extractor titles are often wrong - trust the context)\n")
    rows = d.get("rows") or []
    if rows and len(rows) >= 3:
        print(md_table(d.get("columns") or [], rows))
    elif rows:
        print("ROWS SUSPECT - only %d row(s), usually a header fragment even when confidence=high:" % len(rows))
        print(md_table(d.get("columns") or [], rows))
        print("→ the real data is probably in _context below; confirm with the figure.")
    else:
        print("ROWS EMPTY - the table was not extracted. Use the figure and the surrounding clause text.")
    ctx, n = clean(d.get("_context", ""))
    if ctx.strip():
        print("\n**Surrounding text (_context)**\n" + ctx.strip()[:1800])
    print("\nNote: figures are numbered independently of tables (Table 6.2.14 != Figure 6.2.14). "
          "Take figure ids from the clause's 'Related assets', and confirm the caption in the image.")
    if n or len(rows) < 3:
        print("\n" + GARBLE_NOTE.format(n=n))


def cmd_figure(a, src):
    pn = part_arg(a.part)
    if not pn:
        sys.exit("--part is required for figures")
    fid = a.id.replace("Figure", "").replace("Fig", "").strip()
    base = f"{PART_DIRS[pn]}/webp/fig_{pn:02d}_"
    rel = next((c for c in (f"{base}{fid}.webp", f"{base}{fid}..webp", f"{base}{fid.rstrip('.')}.webp")
                if (src.local_path(c))), None)
    if not rel and src.root:
        g = src.glob(f"{PART_DIRS[pn]}/webp/fig_{pn:02d}_{fid}*.webp")
        rel = g[0] if g else None
    if not rel:
        sys.exit(f"figure {fid} not found in Part {pn}")
    path = src.local_path(rel)
    os.makedirs(FIG_OUT, exist_ok=True)
    out = os.path.join(FIG_OUT, os.path.basename(rel).replace(".webp", ".png"))
    try:
        from PIL import Image
        im = Image.open(path).convert("RGB")
        if im.width < 900:  # upscale small scans so symbols stay legible when viewed
            f = 900 / im.width
            im = im.resize((int(im.width * f), int(im.height * f)), Image.LANCZOS)
        im.save(out)
    except Exception as ex:
        print(f"(PIL unavailable: {ex}); original webp:", file=sys.stderr)
        out = path
    print(out)
    print("(view the PNG and read its printed caption - the figure id is not guaranteed to match the table you want)",
          file=sys.stderr)


# ----------------------------------------------------------------------------- official PDFs (ground truth)
def pdf_path(pn):
    """Part PDF from $BNBC_PDF_DIR or the cache; downloads from the `resources` branch if missing."""
    name = f"BNBC_2020_Part-{pn}.pdf"
    d = os.environ.get("BNBC_PDF_DIR")
    if d and os.path.isfile(os.path.join(d, name)):
        return os.path.join(d, name)
    os.makedirs(PDF_CACHE, exist_ok=True)
    f = os.path.join(PDF_CACHE, name)
    if not os.path.isfile(f) or os.path.getsize(f) < 10000:
        print(f"downloading {PDF_RAW}{name} (large files take a moment) ...", file=sys.stderr)
        tmp = f + ".part"
        try:
            with urllib.request.urlopen(PDF_RAW + name, timeout=300) as r, open(tmp, "wb") as o:
                shutil.copyfileobj(r, o)
        except Exception as ex:
            sys.exit(f"could not download {name}: {ex}\n(need raw.githubusercontent.com, or set BNBC_PDF_DIR to a folder holding the PDFs)")
        os.replace(tmp, f)
    return f


def pdf_pages(pn):
    """Text layer of a Part PDF as a list of page strings (index 0 = PDF page 1). Cached."""
    pdf = pdf_path(pn)
    txt = os.path.join(PDF_CACHE, f"Part-{pn}.txt")
    if not os.path.isfile(txt):
        os.makedirs(PDF_CACHE, exist_ok=True)
        _run(["pdftotext", "-layout", pdf, txt])
        if not os.path.isfile(txt):
            sys.exit("pdftotext not available - install poppler-utils (apt install poppler-utils)")
    return open(txt, encoding="utf-8", errors="replace").read().split("\f")


def find_heading(pages, cid, title=""):
    """PDF pages where clause `cid` starts a line followed by text (skips table-of-contents dot leaders)."""
    pat = re.compile(r"^[ \t]*" + re.escape(cid) + r"[ \t]+(?=\S)", re.M)
    words = [w for w in re.findall(r"[a-z]{4,}", title.lower())][:2]
    hits = []
    for i, p in enumerate(pages, 1):
        for m in pat.finditer(p):
            line = p[m.start(): p.find("\n", m.start())].strip()
            if re.search(r"\.{4,}|…", line):
                continue
            ok = all(w in line.lower() or w in p[m.end(): m.end() + 200].lower() for w in words) if words else True
            hits.append((0 if ok else 1, i, line[:110]))
    hits.sort()
    return [(i, l) for _, i, l in hits]


def render(pn, first, span=1, dpi=100):
    pdf = pdf_path(pn)
    os.makedirs(FIG_OUT, exist_ok=True)
    prefix = os.path.join(FIG_OUT, f"p{pn}_pdf")
    for old in glob.glob(prefix + f"-{first:04d}*.png") + glob.glob(prefix + f"-{first}.png"):
        os.remove(old)
    r = _run(["pdftoppm", "-f", str(first), "-l", str(first + span - 1), "-r", str(dpi), "-png", pdf, prefix])
    outs = sorted(glob.glob(prefix + "-*.png"), key=os.path.getmtime)[-span:]
    if not outs:
        sys.exit("pdftoppm failed (install poppler-utils): " + r.stderr.strip()[:200])
    return outs


def cmd_pdf_find(a, src):
    pn = part_arg(a.part)
    if not pn:
        sys.exit("--part is required")
    pages = pdf_pages(pn)
    if a.clause:
        hits = find_heading(pages, a.clause.strip(" ."), a.query if a.query != "-" else "")
        if not hits:
            print("no heading hit; try a plain-text query without --clause")
        for i, line in hits[: a.n]:
            print(f"PDF p.{i:<5} {line}")
        return
    q = a.query.lower()
    shown = 0
    for i, p in enumerate(pages, 1):
        low = p.lower()
        if q in low:
            j = low.index(q)
            line = p[max(0, p.rfind("\n", 0, j)): p.find("\n", j)].strip()
            print(f"PDF p.{i:<5} x{low.count(q):<3} {line[:110]}")
            shown += 1
            if shown >= a.n:
                break
    if not shown:
        print("no hit (the text layer garbles symbols/Bengali header; try fewer words)")


def cmd_pdf_page(a, src):
    pn = part_arg(a.part)
    if not pn:
        sys.exit("--part is required")
    for o in render(pn, int(a.page), a.span, a.dpi):
        print(o)


def cmd_verify(a, src):
    cid = a.id.lower().replace("sec", "").strip(" .")
    pn = part_arg(a.part)
    exact, _ = _find_entries(src, cid, pn)
    if not pn:
        parts = sorted({e["part"] for e in exact})
        if len(parts) != 1:
            sys.exit(f"clause {cid}: pass --part (found in Parts {parts or 'none'})")
        pn = parts[0]
    title = exact[0]["title"] if exact else ""
    hits = find_heading(pdf_pages(pn), cid, title)
    if not hits:
        sys.exit(f"heading for {cid} not found in the Part {pn} PDF text layer - use `pdf-find` with words from the clause")
    print(f"Sec {cid} heading hits in Part {pn} PDF: " + "; ".join(f"p.{i}" for i, _ in hits[:5]))
    page = hits[0][0]
    for o in render(pn, page, a.span, a.dpi):
        print(o)
    print(f"→ `view` the PNG(s). Printed page numbers differ from PDF page numbers; read values off the image, "
          f"not the PDF text layer (it has the same symbol corruption, e.g. 'Z50.12' for Z=0.12).", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("status"); s.set_defaults(f=cmd_status)
    s = sp.add_parser("sync"); s.add_argument("--update", action="store_true"); s.set_defaults(f=cmd_sync)
    s = sp.add_parser("toc"); s.add_argument("--part"); s.add_argument("--chapter"); s.add_argument("--all", action="store_true"); s.set_defaults(f=cmd_toc)
    for name, fn, dn in (("route", cmd_route, 8), ("search", cmd_search, 8), ("pack", cmd_pack, 4)):
        s = sp.add_parser(name); s.add_argument("query"); s.add_argument("--part"); s.add_argument("-n", type=int, default=dn)
        s.add_argument("--json", action="store_true"); s.add_argument("--max-chars", type=int, default=2500); s.set_defaults(f=fn)
    s = sp.add_parser("clause"); s.add_argument("id"); s.add_argument("--part"); s.add_argument("--children", action="store_true")
    s.add_argument("--max-chars", type=int, default=0); s.set_defaults(f=cmd_clause)
    s = sp.add_parser("table"); s.add_argument("id"); s.add_argument("--part"); s.set_defaults(f=cmd_table)
    s = sp.add_parser("figure"); s.add_argument("id"); s.add_argument("--part"); s.set_defaults(f=cmd_figure)
    s = sp.add_parser("verify"); s.add_argument("id"); s.add_argument("--part"); s.add_argument("--span", type=int, default=2)
    s.add_argument("--dpi", type=int, default=100); s.set_defaults(f=cmd_verify)
    s = sp.add_parser("pdf-find"); s.add_argument("query"); s.add_argument("--part"); s.add_argument("--clause")
    s.add_argument("-n", type=int, default=8); s.set_defaults(f=cmd_pdf_find)
    s = sp.add_parser("pdf-page"); s.add_argument("page"); s.add_argument("--part"); s.add_argument("--span", type=int, default=1)
    s.add_argument("--dpi", type=int, default=100); s.set_defaults(f=cmd_pdf_page)
    a = ap.parse_args()
    src = Src(None if a.cmd in ("sync", "pdf-find", "pdf-page") else find_root())
    if src.remote and a.cmd not in ("sync", "pdf-find", "pdf-page"):
        print("[remote mode: no local copy; full-text search unavailable]", file=sys.stderr)
    try:
        a.f(a, src)
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
