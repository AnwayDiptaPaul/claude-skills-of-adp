# NOTICE

`static-site-design` is a derivative work combining and adapting material from two
Apache-2.0-licensed sources:

1. **`frontend-design`** — a skill by Anthropic. The overall studio framing, the
   brainstorm → plan → critique → build → critique workflow, the calibration notes on
   current AI design defaults, and the "Writing in design" section carry forward from this
   skill largely as written, with the process section extended to include a concrete token
   system and reference-file pointers.

2. **`stitch-skills`** (github.com/google-labs-code/stitch-skills) — a skill collection by
   Google, specifically ideas and structure from the `taste-design`, `design-md`,
   `stitch-loop`, and `extract-design-md` skills within it. The P0/P1/P2 severity-tier
   diagnostic structure, the `DESIGN.md`/`SITE.md` planning-document pattern, the plain-CSS
   custom-property token conventions, and much of the specific banned-pattern list
   (typography, gradients, layout, component reflexes, copy clichés) are adapted from this
   collection's anti-generic design guidance, rewritten and reorganized for a plain
   HTML/CSS/JS static-site workflow rather than Stitch's own MCP-tool-mediated design
   pipeline.

## What changed

This version is scoped specifically to static, multi-file, deployable sites (HTML/CSS/JS +
docs + media + third-party integrations) rather than either source's original scope —
`frontend-design` was framework-agnostic and visual-design-only; the relevant `stitch-skills`
skills assumed a live Google Stitch MCP connection and, for the build-side skills not drawn
on here, a React/React Native/shadcn target. Specifically new in this version:

- The full [site-architecture.md](references/site-architecture.md) reference: folder
  structure, shared-header/footer patterns without a framework, SEO basics, and deploy-target
  specifics (GitHub Pages, Cloudflare Pages, Netlify, Vercel).
- The full [embedded-connections.md](references/embedded-connections.md) reference: forms,
  analytics, maps, chat/AI widgets, video/social embeds, and the API-key/serverless-proxy
  security pattern.
- The full [media-and-assets.md](references/media-and-assets.md) reference: image
  optimization, font loading, icon curation, and the favicon/OG-image checklist.
- `scripts/check_slop.py`: a dependency-free mechanical scanner for a meaningful subset of
  the checklist (banned fonts, purple-to-blue gradients, pure black, Tailwind reflex classes,
  forbidden copy clichés, placeholder names/images, emoji, `LABEL // YEAR` formatting, and a
  couple of accessibility landmines). Neither source skill shipped an executable check.
- The `DESIGN.md`/`SITE.md` planning-document patterns were stripped of Stitch MCP tool
  calls, project IDs, and screen-generation mechanics, and reframed as plain planning
  documents any agent (or person) can write and read directly.
- The severity-tier checklist, the token-system guide, and the accessibility/performance
  section were rewritten and reorganized from both sources' material rather than reproduced,
  and merged with `frontend-design`'s existing voice and structure.
- The full [motion-and-interactivity.md](references/motion-and-interactivity.md) reference
  and the "link relative to the file, never the root" convention throughout
  [site-architecture.md](references/site-architecture.md) (folder-per-page structure,
  depth-based relative paths, and Custom Elements as a fourth shared-chrome option) are new
  and not adapted from either source — written from current web-platform documentation and
  named where a specific external reference (e.g. Emil Kowalski's *Animations on the Web*)
  informed a specific claim.
- `scripts/check_slop.py` gained a `LINK` tier (root-absolute paths, non-index `.html`
  internal links) and a `transition: all` check to match.

The full Apache License, Version 2.0 text is in `LICENSE.txt`.
