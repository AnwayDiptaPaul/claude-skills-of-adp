# Accessibility & Performance

The quality floor from `SKILL.md` isn't optional polish — a site that's beautiful in a
screenshot and broken for a keyboard user, or gorgeous on a fast connection and unusable on a
slow one, hasn't actually shipped a finished design. This is the concrete version of that bar.

## Accessibility baseline

- **Semantic HTML first.** `<button>` for things that act, `<a>` for things that navigate,
  real heading tags in real hierarchy (`<h1>` once per page, no skipped levels). A `<div>`
  with a click handler is invisible to a screen reader and untabbable by default — don't
  reach for it when a native element already does the job.
- **Landmarks.** `<header>`, `<nav>`, `<main>`, `<footer>` — screen reader users navigate by
  landmark constantly; an all-`<div>` page forces them to read everything linearly to find
  anything.
- **Alt text with judgment.** Real, specific alt text for meaningful images. Empty
  `alt=""` (not a missing attribute) for purely decorative ones, so screen readers skip them
  instead of reading a filename out loud.
- **Color contrast.** WCAG AA at minimum (4.5:1 for body text, 3:1 for large text) — check
  this against the actual token values, not just eyeballed. Status or meaning should never
  be color alone: a form error needs text or an icon alongside the red, not just red.
- **Keyboard navigation.** Everything interactive reachable and operable by keyboard alone,
  with a visible focus state — removing the default outline without replacing it with
  something equally visible is a common and easy-to-avoid mistake.
- **Touch targets.** Minimum ~44×44px for anything tappable, with real spacing between
  adjacent targets — small text links stacked tightly are a common mobile-usability failure.
- **`prefers-reduced-motion`.** Wrap non-essential animation in this media query and
  provide a reduced or static alternative — some visitors have this set for real medical
  reasons, not preference.
- **Forms.** Every input has a real, associated `<label>` (not just a placeholder — see
  [embedded-connections.md](embedded-connections.md)). Errors are announced in a way
  assistive tech picks up (`aria-live`, or focus moved to the error) rather than only
  appearing as a visual color change.

## Performance baseline

You don't need to chase a perfect Lighthouse score, but the three metrics behind Core Web
Vitals map directly to things a design decision can break:

- **Largest Contentful Paint (LCP)** — the hero image or headline should be one of the first
  things requested, not blocked behind render-blocking CSS/JS or a lazy-load that fires too
  late (see the lazy-loading note in [media-and-assets.md](media-and-assets.md)).
- **Cumulative Layout Shift (CLS)** — reserve space for images and embeds (explicit
  width/height or `aspect-ratio`) and for webfonts (`font-display` strategy) so content
  doesn't jump as things load in.
- **Interaction to Next Paint (INP)** — keep JS off the main thread where possible, and keep
  third-party scripts (analytics, chat widgets, embeds) deferred or lazily loaded so they
  don't compete with the page's own interactivity — see
  [embedded-connections.md](embedded-connections.md) for the facade pattern.

Practical habits that cover most of this without special tooling: defer or async every
non-critical script, inline the small amount of CSS needed for the initial viewport if the
full stylesheet is large, and don't ship a third-party embed that hasn't earned its place.

## QA workflow

**Spend real time on the brief before writing code.** A brief, deliberate pass — actually
sketching the layout options, naming what makes this brief different from the last one,
deciding what you're *not* going to do — catches more generic-default drift than any amount
of polishing after the fact. Seniors plan first; the fastest way to end up with a templated
result is to start typing HTML before deciding what's supposed to be different about this one.

**Self-critique with screenshots, if your environment supports it.** Markup that reads fine
as code doesn't always read fine rendered — spacing that looked right in the token system can
still feel cramped or sparse once it's an actual page. A picture is worth a thousand tokens
here.

**Test at real widths, not just "responsive."** At minimum: ~375px (small phone), ~768px
(tablet), ~1024px (small laptop), ~1440px (desktop). Horizontal scroll at any width you claim
to support is a hard failure, not a nitpick.

**Run the mechanical pass.** `scripts/check_slop.py` catches a meaningful chunk of
[anti-slop-checklist.md](anti-slop-checklist.md) automatically — banned fonts and gradients,
leftover placeholder copy, forbidden clichés, a few accessibility landmines like missing alt
attributes. It's a floor under the manual read-through, not a replacement for it:

```bash
python3 scripts/check_slop.py path/to/site
```

**If a headless browser tool is available** (Playwright, Puppeteer, or similar, whether
bundled in your environment or connected as a tool), use it to actually render the pages and
compare against your plan — it catches real rendering bugs a code read-through won't. If
nothing like that is available, a careful manual read-through plus the script above is the
fallback, not a lesser option to feel bad about — thoroughness matters more than the specific
tool.
