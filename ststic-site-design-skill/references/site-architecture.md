# Static Site Architecture

Visual design decides what a page looks like. Architecture decides whether the tenth page
still looks like the first one, whether a link still works after the site changes host, and
whether the folder you hand off can be dropped anywhere — a domain root, a project subpath,
a USB stick — and just work. All of this is easiest to decide before the second page exists,
not after.

## The rule that shapes everything else: link relative to the file, never to the root

Every internal reference — to another page, a stylesheet, a script, an image — should be
written relative to the file it's written in, never as a root-absolute path (`/about.html`,
`/images/hero.jpg`). A root-absolute path only resolves correctly when the site is deployed
at the exact domain root it was authored against. It silently breaks the moment any of the
following happens, and all of them are ordinary:

- The site deploys to a GitHub Pages **project** repo instead of a `username.github.io` root
  repo, and now lives at `username.github.io/reponame/` instead of the domain root.
- A host stages a preview build at a random subpath before promoting it to production.
- Someone unzips the folder and opens `index.html` straight from disk (`file://`) to check
  something quickly, with no server involved at all.
- The site later moves to a different domain, or gets mounted under an existing site's
  `/docs/` or `/blog/` path.

A relative path doesn't care about any of that — it only encodes where it is relative to
where it's going, which is what makes the whole folder portable by construction. Treat this
as the default, not an optimization to add later: retrofitting it across a finished site
means touching every page.

## Folder structure: a page is a folder, not a file

Give every page its own folder containing an `index.html`, instead of a flat `page-name.html`
file at the top level. A reasonably sophisticated multi-section site looks like this:

```
site/
├── index.html                        # homepage — the one page that stays at the root
├── about/
│   └── index.html
├── services/
│   ├── index.html                    # services overview
│   ├── structural-design/
│   │   └── index.html
│   └── geotechnical/
│       └── index.html
├── projects/
│   ├── index.html                    # projects listing
│   └── project-one/
│       └── index.html
├── contact/
│   └── index.html
├── css/
│   ├── tokens.css                    # :root custom properties — see design-tokens.md
│   ├── base.css
│   └── components.css
├── js/
│   ├── nav.js
│   └── forms.js                      # see embedded-connections.md
├── images/
├── fonts/                            # if self-hosting — see media-and-assets.md
├── partials/                         # source-of-truth header/footer — see below
│   ├── header.html
│   └── footer.html
├── favicon.ico
├── site.webmanifest
├── robots.txt
└── sitemap.xml
```

A page's internal link should point at `services/structural-design/index.html`, not a flat
`services-structural-design.html` — `structural-design` is a real folder, and `index.html` is
the real file inside it. Beyond portability, this shape buys two more things:

- **Clean URLs for free.** Deployed, `services/structural-design/` resolves to that folder's
  `index.html` on every static host with zero server configuration — no `.html` in the
  address bar for anyone who navigates by typing or by a link written without the filename.
- **Room to grow.** A section can go from a single page to a listing-plus-detail structure
  without renaming anything that already links to it — `services/index.html` still means
  "the services page" whether or not it later grows subpages underneath it.

Writing the filename explicitly in the link (`services/structural-design/index.html`, not
the bare `services/structural-design/`) is the more portable choice, not just the more
explicit one — it resolves identically over `file://`, over any static host, and inside a
zipped copy someone opens locally, with no dependency on a server correctly guessing that a
directory request should serve the index file inside it. That's worth the extra characters.

## Worked examples, by depth

The number of `../` a link needs equals how many folders deep the *linking* file sits below
the site root — the source file's depth, not the target's.

**From `index.html` (root — depth 0):**
```html
<a href="about/index.html">About</a>
<a href="services/structural-design/index.html">Structural Design</a>
<link rel="stylesheet" href="css/tokens.css">
<img src="images/hero.jpg" alt="…">
```

**From `about/index.html` (depth 1):**
```html
<a href="../index.html">Home</a>
<a href="../services/index.html">Services</a>
<a href="../services/structural-design/index.html">Structural Design</a>
<link rel="stylesheet" href="../css/tokens.css">
```

**From `services/structural-design/index.html` (depth 2):**
```html
<a href="../../index.html">Home</a>
<a href="../index.html">Services</a>
<a href="../geotechnical/index.html">Geotechnical</a>
<link rel="stylesheet" href="../../css/tokens.css">
```

Everything shared — header, footer, the CSS, a logo — is written once as a template, and its
relative prefix needs recalculating per output file. That's exactly the problem the
header/footer options below have to solve for, not just page content.

A few files are the standing exception, by convention rather than by choice: `favicon.ico`,
`robots.txt`, `sitemap.xml`, and `site.webmanifest` are expected at the true site root by
browsers and crawlers regardless of what subpath the site lives under. The favicon
specifically is worth knowing about: a browser's *implicit* fallback request for
`/favicon.ico` always targets the domain root, not the current page's folder — so on a site
deployed at a subpath (a GitHub Pages project repo, for instance), that automatic fallback
misses entirely. An explicit `<link rel="icon" href="...">` with the correct relative path
per page is what actually works there.

One deliberate exception in the other direction: `og:url` and `<link rel="canonical">` in
your `<head>` should hold a **full absolute URL, domain included** — not a relative path.
Those tags are read by systems (crawlers, link-preview bots) that have no page context to
resolve a relative path against, so the spec calls for the whole thing. Internal navigation
and asset references stay relative; these two metadata fields are the exception, by design.

## Keeping header, nav, and footer consistent across pages

This is the recurring problem a framework normally solves for you, and without one you have
three real options. Once every page also needs a *correct, depth-appropriate* relative prefix
baked into its shared chrome, the tradeoffs shift a little from a flat, single-level site.

**1. Plain duplication.** Copy the same header/nav/footer markup into every HTML file.

- *Pros:* Zero tooling, zero runtime dependency, works over `file://`, fastest possible page
  load.
- *Cons:* Updating the nav means editing every file — and now every copy also needs its *own*
  correct `../` prefix hand-set for its depth. Manageable at three pages and one level deep;
  error-prone fast once sections start nesting.

**2. Author-time include stitching (recommended once the site has real depth).** Keep
`partials/header.html` and `partials/footer.html` as templates using a placeholder token
in place of the relative prefix — e.g. `{{BASE}}css/tokens.css` — and run a small
script at build time that stitches each partial into every page, substituting `{{BASE}}`
with the correct `../` sequence for that specific output file's depth before writing it.

- *Pros:* Single source of truth for shared chrome, and the depth-prefix problem gets solved
  once, in the script, instead of by hand on every page. The shipped output is still plain
  static HTML — no flash of unstyled content, no JS dependency for critical layout, works
  identically on every host and over `file://`.
- *Cons:* One extra step before deploy (run the script, or wire it into a CI action).

**3. Runtime injection via `fetch()`.** Ship one `partials/header.html`/`footer.html`, and
have a script `fetch()` them into a placeholder element on every page load.

- *Pros:* Simplest single-source-of-truth setup, no build step.
- *Cons:* Requires JavaScript to render the header/footer at all, with the usual costs (a
  flash before injection completes, nothing for a crawler that doesn't execute JS). It also
  inherits the depth problem in its trickiest form: the fetch's *own* path needs the right
  relative prefix to find the partial, and that prefix can't be reliably derived from
  `location.pathname` alone once the site is hosted at a subpath — the pathname mixes "how
  deep is this page" with "what subpath is the whole site mounted under," and a script can't
  tell those two apart at runtime. The reliable fix is to declare the depth explicitly per
  page — one inline variable before the script runs (`<script>const BASE = '../';</script>`)
  — rather than trying to infer it.

**4. Custom Elements.** Define `<site-header>` and `<site-footer>` once, in a bundled
`components.js` every page already loads, and let the browser's own Custom Elements registry
render them wherever the tag appears — no separate network request the way `fetch()` needs.

```js
// js/components.js
class SiteHeader extends HTMLElement {
  connectedCallback() {
    const base = this.getAttribute('base') || './';
    this.innerHTML = `
      <header>
        <a href="${base}index.html">Home</a>
        <a href="${base}services/index.html">Services</a>
      </header>`;
  }
}
customElements.define('site-header', SiteHeader);
```
```html
<!-- services/structural-design/index.html -->
<site-header base="../../"></site-header>
```

- *Pros:* Single source of truth with no extra network round-trip — the component's markup
  ships in the same script every page already references, so it avoids `fetch()`'s specific
  depth-inference problem entirely; the depth still needs stating explicitly (the `base`
  attribute above), just once per tag instead of guessed at runtime. If you reach for Shadow
  DOM for style encapsulation, custom properties still inherit through the shadow boundary,
  so the component can use `var(--color-action-primary)` from your token system without
  extra wiring.
- *Cons:* Still needs JavaScript to render at all — the same no-JS/some-crawler blind spot as
  option 3, just without the network-request cost on top of it. Declarative Shadow DOM exists
  for a zero-JS-first-paint version of this, but its authoring ergonomics are still rough
  enough in practice that it doesn't yet beat option 2 for a build that wants zero JS
  dependency for critical layout.

For anything client-facing and content-heavy — marketing pages, docs, anything meant to be
indexed — option 2 gets consistency without the runtime cost or the depth-inference problem.
Options 3 and 4 are reasonable tradeoffs for smaller or more app-like sites where a JS
dependency is already a given; between the two, option 4 at least avoids paying for a network
request on top of that dependency. Whichever you pick, note the choice in `SITE.md` so it
isn't re-litigated file by file.

## SITE.md: a planning doc worth writing past one page

The same logic that makes a `DESIGN.md` worth writing for visual consistency
(see [design-tokens.md](design-tokens.md)) applies to structure. For anything past a single
page, write down the site's shape before generating pages one at a time from memory:

```markdown
# [Project Name] — Site Plan

## Mission & audience
What this site is for, and who's landing on it.

## Voice
2-3 adjectives for tone — this keeps copy consistent across pages written in different
sessions.

## Sitemap (living — check items off as pages ship)
- [x] index.html — home
- [ ] about/index.html — company/personal background
- [ ] services/index.html — offering overview
- [ ] services/structural-design/index.html
- [ ] contact/index.html — form + map (see embedded-connections.md)

## Shared chrome
Which of the three nav/header approaches above, and where the shared partials live.

## Deploy target
Which host, and any host-specific files that need to exist (see below).
```

Update the sitemap checklist as you go rather than writing it once and letting it go stale —
its whole value is knowing, without re-reading every file, what's shipped and what's still
a placeholder link.

## SEO and metadata basics

Cheap to include from the start, expensive to retrofit across every page after launch:

- A unique `<title>` and `<meta name="description">` per page — not the same tag copy-pasted
  across all of them.
- Open Graph tags (`og:title`, `og:description`, `og:image`, `og:url`) so shared links render
  a real preview card instead of a blank one — see the OG-image checklist in
  [media-and-assets.md](media-and-assets.md), and the absolute-URL note above for `og:url`.
- One `<h1>` per page, and a heading hierarchy that doesn't skip levels — this is an
  accessibility requirement as much as an SEO one (see
  [accessibility-performance.md](accessibility-performance.md)).
- Semantic landmarks (`<header>`, `<nav>`, `<main>`, `<footer>`) instead of an all-`<div>`
  page — screen readers and search crawlers both use them to understand structure.
- `sitemap.xml` and `robots.txt` at the root once the site has more than a couple of pages —
  and `sitemap.xml` entries are one more place that wants full absolute URLs, same reasoning
  as `og:url` above.
- A `<link rel="canonical">` if the same content is ever reachable at more than one URL.

## Deploy target specifics

Each static host has its own conventions. Knowing the target before you build means the
right files exist from the start instead of getting bolted on at deploy time.

**GitHub Pages.** Serves straight from a branch (often `gh-pages`) or a `/docs` folder on
`main`. A custom domain needs a `CNAME` file at the root containing just the domain. Project
sites (not a `username.github.io` root repo) are served from a subpath — this is precisely
the scenario the relative-linking rule above exists for: if every internal link and asset
reference is relative, a project site works identically at its subpath with no changes at
all; if any of them were root-absolute, this is where they'd 404.

**Cloudflare Pages.** Static files deploy as-is; a `_headers` file at the root sets custom
response headers (cache control, security headers), and `_redirects` handles URL redirects
and rewrites. If any part of the site needs a server-side secret (an API proxy, for
instance — see [embedded-connections.md](embedded-connections.md)), that's a separate
Cloudflare Worker with its own `wrangler.toml`, not something that belongs in the static
Pages deploy itself.

**Netlify.** Same `_redirects` convention as Cloudflare Pages, plus an optional
`netlify.toml` for build settings, headers, and redirect rules in one place. Netlify Forms
can handle form submissions without a separate backend at all — worth knowing before reaching
for a third-party form service (see [embedded-connections.md](embedded-connections.md)).

**Vercel.** Convention-based routing and a `vercel.json` for headers/redirects/rewrites when
you need to override the defaults. Serverless functions live in `/api` and deploy alongside
the static output automatically — no separate service to stand up for a small proxy endpoint.

Whichever host, keep the host-specific files at the project root from the start rather than
adding them right before the first deploy — it's one less thing to debug under time pressure.
