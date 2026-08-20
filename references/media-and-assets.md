# Media & Assets

Type and color decisions can be exactly right and still get undercut in half a second of
scrolling by a stock photo that's obviously stock, a broken hotlinked image, or the same
default icon set every other AI-built page reaches for. Assets carry as much signal as
layout does.

## Real imagery vs. placeholders — be honest about which you're using

Ground the site in real photography, product screenshots, or brand assets whenever they
exist — ask for them before inventing a substitute (see
[SKILL.md § Ground it in the subject](../SKILL.md#ground-it-in-the-subject)). When they
genuinely don't exist yet (a brand-new company with no photography, a feature that hasn't
shipped a UI yet), the honest options are:

- A deliberate illustration style, chosen and applied consistently — not a single
  AI-generated "hero illustration" dropped in and left looking like a placeholder.
- Clean geometric/abstract treatments (gradients-as-texture, shape compositions) that don't
  pretend to be photography.
- Clearly-labeled placeholder blocks if the real asset is coming later — better than a fake
  stand-in that looks finished.

What to avoid either way: hotlinked stock photography from URLs that can go dead at any time
(a broken Unsplash link is a specific, recognizable tell), and generic "plastic" AI
illustration standing in as if it were bespoke art.

## Image formats and optimization

- **Format:** WebP or AVIF for photos, with a JPEG/PNG fallback via `<picture>` if you need
  to support older browsers. SVG for anything vector — icons, logos, simple illustrations.
- **Responsive images:** `srcset` + `sizes`, or `<picture>` with multiple `<source>`
  breakpoints, so a phone doesn't download a 4K hero image meant for a desktop monitor.
- **Lazy loading:** `loading="lazy"` on any image below the fold. Skip it on the hero/LCP
  image — lazy-loading the thing you most want painted first works against you.
- **Explicit dimensions:** always set `width`/`height` (or `aspect-ratio` in CSS) on images,
  so the browser reserves the right space before the image loads instead of the layout
  jumping around it (this is a direct hit to Cumulative Layout Shift — see
  [accessibility-performance.md](accessibility-performance.md)).

## Icons

Pick a small, purposeful set rather than defaulting to whatever icon library ships with the
first component example you reach for. If every button has an arrow and every feature card
has the same sparkle icon, that's a tell, not a design system (see
[anti-slop-checklist.md](anti-slop-checklist.md)). Inline SVG for icons that need to inherit
`currentColor` or animate; a sprite sheet if there are many repeated icons and inlining every
instance would bloat the HTML.

## Fonts

- **Hosting:** self-hosting gives you the most control over `font-display` and avoids a
  third-party request, but a font CDN (Google Fonts and similar) is simpler to set up and
  fine for most projects — pick based on how much you care about that one extra request
  versus setup time.
- **`font-display: swap`** (or `optional` if you'd rather show the fallback than risk a
  layout shift when the webfont finally loads) — without it, text can stay invisible until
  the font arrives.
- **Preload the critical font** (the one used in the hero/above-the-fold text) with
  `<link rel="preload" as="font">` so it doesn't wait behind the rest of the page's requests.
- **Subset and limit weights.** Loading all nine weights of a variable font when the design
  only uses three is a real, avoidable performance cost.

## Favicons and share previews

Easy to forget until someone actually shares the link and the preview card is blank or the
browser tab shows a broken image. The practical checklist:

- `favicon.ico` at the root (still the most universally-respected fallback)
- A modern PNG favicon set (at minimum 32×32 and 16×16) plus `apple-touch-icon.png` (180×180)
  for iOS home-screen saves
- `site.webmanifest` if you want the site installable as a lightweight PWA, even a minimal one
- An `og:image` sized appropriately (1200×630 is the safe default most platforms expect) —
  and something that actually represents the page it's attached to, not one generic image
  reused across every page's share card

## Documentation and media-heavy pages

For a docs section or any long-form content page:

- Keep a consistent doc-page shell (sidebar or in-page nav, breadcrumb, "on this page" table
  of contents for long pages) so the reading experience doesn't reset page to page — this is
  the same shared-chrome problem covered in
  [site-architecture.md](site-architecture.md#keeping-header-nav-and-footer-consistent-across-pages),
  applied to a nav sidebar instead of a header.
- Code blocks need a monospace face from the token system (not a random default), and enough
  contrast to actually be readable — don't let syntax highlighting fight the page's own color
  tokens.
- If content is authored in Markdown and converted to HTML, keep the conversion step simple
  and inspect the output — auto-generated heading IDs and table markup are common places
  where the result silently breaks the page's actual design system.
