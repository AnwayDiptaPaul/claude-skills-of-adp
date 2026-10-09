---
name: bnbc-scraper
description: Retrieve clauses, tables and figures from the Bangladesh National Building Code (BNBC 2020) using the structured GitHub knowledge base AnwayDiptaPaul/bnbc-2020-database. Use this skill whenever the user asks about BNBC, "Bangladesh building code", "the code", a BNBC section/clause/table number (e.g. "Sec 2.5.7.1", "Table 6.2.14"), or any Bangladesh design-code requirement - seismic zone coefficient, base shear, storey drift, wind loads, load combinations, RC/steel/masonry/timber/bamboo design, foundations and piles, fire egress and exits, plumbing, lifts, setbacks, permits - even if they never say "BNBC". Also use it to build code-compliance checks, citations, RAG context or reports that must quote BNBC clauses. Do not answer BNBC questions from memory; fetch the clause and verify numbers against the official Part PDFs (also in that repo), because numeric limits are easy to misremember and the extracted text is lossy.
---

# BNBC 2020 retrieval

Source: `github.com/AnwayDiptaPaul/bnbc-2020-database`. Branch `main`: BNBC 2020 split into ~2,570 clause files across 10 Parts, with router indexes, JSON tables, WebP figures. Branch `resources`: the official Part PDFs (`BNBC_2020_Part-N.pdf`, 1-24 MB each, Part 6 is 1,346 pages). `scripts/bnbc.py` wraps both: retrieve the few clauses you need from `main`, then confirm the numbers against the PDF page.

The `main` text is an **unofficial, lossy extraction**. Retrieval is easy; trusting the numbers is the hard part. Read "Reliability protocol" before quoting any value.

## Quick start

```bash
python scripts/bnbc.py pack "storey drift limit" --part 6      # answer-ready context (best default)
python scripts/bnbc.py clause 2.5.7.1 --part 6                 # one clause by id
python scripts/bnbc.py route "means of egress width"           # ranked clause titles, fast
python scripts/bnbc.py search "seismic zone coefficient"       # full-text over clause bodies
python scripts/bnbc.py table 6.2.14 --part 6                   # table JSON, cleaned + flagged
python scripts/bnbc.py figure 6.2.24 --part 6                  # exports PNG -> then `view` it
python scripts/bnbc.py toc --part 6 [--chapter Soils]          # browse structure
python scripts/bnbc.py verify 1.5.6.1 --part 6                 # ground truth: render the official PDF page(s), then `view`
python scripts/bnbc.py pdf-find "Figure 6.2.24" --part 6       # locate text in a Part PDF -> PDF page numbers
python scripts/bnbc.py pdf-page 147 --part 6 --span 2          # render specific PDF pages
```

First run auto-clones the repo (~55 MB) into `~/.cache/bnbc-2020-database`. If git/network is blocked, set `BNBC_NO_CLONE=1` to fall back to raw GitHub files (route/clause/table/figure work; full-text `search` does not). `status` shows which mode is active, `sync --update` refreshes. Network needs `github.com` + `raw.githubusercontent.com` (+ `codeload.github.com` for the tarball fallback). PDFs download on demand from the `resources` branch into `~/.cache/bnbc-pdfs` (set `BNBC_PDF_DIR` to reuse a local folder) and need poppler (`pdftotext`, `pdftoppm`). The GitHub web UI for the `resources` branch may block fetchers; the CLI uses raw URLs, which work.

## Workflow

1. **Pick the Part.** Structural anything (loads, seismic, wind, RC, steel, foundations, masonry, timber) is Part 6. Fire/egress Part 4; MEP/lifts Part 8; occupancy/setbacks Part 3; materials Part 5; permits Part 2; definitions/abbreviations Part 1. Details in `references/part-index.md`. Passing `--part` sharpens ranking a lot; omit it only when unsure.
2. **Retrieve.** Start with `pack` (route + full-text; prints each clause's heading plus the passage where your terms are densest, and related assets; raise `--max-chars` or use `clause` for the whole file). Use `clause` when the user gave a section number, `toc` to browse, `search` when titles don't match the vocabulary.
3. **Follow the assets.** Each clause prints `Related assets`. Many BNBC values live in tables/figures, not the prose. Open them with `table` / `figure`.
4. **Verify against the PDF** before quoting any number, limit, coefficient or formula: `verify <id> --part N`, then `view` the PNG and read the value off the page image.
5. **Answer with citations** as `BNBC 2020, Part 6, Sec 2.5.4.2` (+ Table/Figure number). Quote values only after the verification step below. Say plainly which values you verified from an image and which you could not.

## Reliability protocol

The repo's own extraction is lossy. Measured on the current data:

- **306 of 400 JSON tables have empty `rows`** (all flagged `low` confidence). Even `high` tables can be junk: Table 6.2.14 has one row, `Seismic | Zone`; the real values (Z = 0.12/0.20/0.28/0.36) are only in `_context` and the clause text.
- **Symbols are lost, sometimes silently.** Control characters appear where Greek letters, subscripts and ≤/≥ were (the CLI prints `⟨?⟩`). Worse, some symbols turn into digits: Sec 2.5.4.2 reads "Z50.12", which is Z = 0.12. Formulas shatter into one-token lines (Sec 2.5.7.1's base-shear expression). Never read a numeral glued to a variable literally.
- **481 of 2,569 clause files contain unreadable control glyphs** (and more have silent substitutions). Re-measure all these figures with `python scripts/audit.py` after the repo updates.
- **~8% of clause files (204 of 2,569, a lower bound) are mis-segmented**: one file holds text from several sections under inline headings. In Part 4, file `3.10.11` also carries Sec 3.11 (ramps) and 3.14.x (exit widths/number of exits); file `3.9.7.5` (an exit-door sentence) carries the stairway-width rules of 3.10. `clause`/`pack` print a ⚠ line for these. **Cite the section number printed inline next to the text you use, not the file id.** The router can't help here because it lists file ids only.
- **All 328 `.mmd` flowcharts are the same placeholder** ("Analyze Condition → Condition Met?"). Ignore them; never present them as BNBC procedure.
- **Table and figure numbers are independent.** `fig_06_6.2.14` is Figure 6.2.14(a), not Table 6.2.14. Take figure ids from a clause's related assets and read the caption in the image.

So, for any number, limit, coefficient or formula that will drive a design decision:

1. Retrieve from `main` to find *where* it is (clause id, related table/figure).
2. Run `verify <id> --part N` (default renders 2 pages, since clauses run over page breaks) and `view` the PNG. The rendered page is the ground truth. The **PDF text layer is not**: it carries the same corruption as `main` (it reads "Z50.12" where the page shows Z=0.12), so don't rely on `pdftotext` output for values. If `verify` can't find a heading, use `pdf-find` with words from the clause (also how to find a figure: `pdf-find "Figure 6.2.24"`), then `pdf-page`.
3. If the PDF is unreachable (no network/poppler), fall back to cross-checking clause prose against `_context`/table rows and the exported figure image, and say the value is unverified against the PDF.
4. Report which values you confirmed from the page image and any residual doubt, e.g. "Sec 1.5.6.1 (PDF p.32): Δ ≤ 0.005h for T < 0.7 s, 0.004h for T ≥ 0.7 s, 0.0025h unreinforced masonry".
5. For compliance decisions, close with a one-line reminder that the PDFs carry a Bangladesh Gazette header dated 11 Feb 2021 and the official BNBC 2020 / any later amendment governs.

PDF page numbers are the file's 1-based index, not the printed page numbers (printed numbers are in Bengali numerals in the gazette header).

## Things that trip people up

- **Clause ids are chapter-relative inside a Part.** "Sec 2.5.7.1" in Part 6 means Chapter 2, 5.7.1. The same id can exist in several Parts; the CLI prints all unless `--part` is given.
- PDFs make mis-segmented clauses easy to resolve: `pdf-find "<phrase from the text>" --part N` lands on the page where the text really lives, and the heading on that page gives the true section number.
- A parent id (e.g. `2.5.7`) may have no file of its own; `clause` then lists sub-clauses, and `--children` prints them.
- Router "Scenario"/"Keywords" blocks are just title tokens, not semantic tags, so phrase queries in code vocabulary ("storey drift", "design base shear", "seismic zoning") and let the synonym handling cover "earthquake", "RCC", "lift" and similar.
- Part 4 and some Part 8 clause titles are truncated sentence fragments; trust the body, not the title.
- BNBC adopts ASCE 7 / ACI 318 style provisions in places, but the repo contains no ACI or ASCE text. If the user needs those, say so rather than inferring.

## Using it programmatically

`route` and `search` accept `--json` for pipelines. Clause files carry YAML-ish front matter (`clause`, `title`, `chapter`, `related_tables`, `related_diagrams`) - the CLI already parses it. For a RAG build, index `Part_*/clauses/*.md` as chunks, keep `related_*` as edges, and carry the garble caveat into the retrieval prompt. Repo license is MIT; cite as "Anway Dipta Paul, BNBC 2020 - AI-Ready Knowledge Base".
