# Design Tokens for Plain CSS

The brainstormed plan from `SKILL.md` (color, type, layout, signature) needs to become real
CSS before it's useful, and it needs to become the *same* real CSS on every page of a
multi-page site. Two problems, one fix: a small set of custom properties that every page
pulls from, defined once.

## Why tokens instead of one-off values

Without them, page three of an eight-page site quietly invents its own shade of the brand
color because nobody's holding the original hex value in view anymore, and by page six the
"consistent" site has four near-identical blues. Tokens make drift visible: if a value isn't
in `:root`, it shouldn't be in the CSS.

They also make the anti-slop pass easier to run mechanically — a scanner (or a person) can
check whether colors trace back to `var(--color-*)` far more reliably than it can judge
whether a hex value "looks purple enough" to flag.

## Naming: semantic, not descriptive

Name a token for what it *does*, not what it looks like right now:

```css
/* Avoid — describes the value, breaks the moment the value changes */
--color-indigo-600: #4f46e5;
--radius-8px: 8px;

/* Prefer — describes the role, survives a rebrand */
--color-action-primary: #4f46e5;
--radius-button: 8px;
```

`--color-action-primary` still means the same thing if the hex behind it changes during a
redesign. `--color-indigo-600` doesn't — the name is now a lie.

## Starter structure

This is scaffolding, not a design. Every value below is a placeholder to replace with
choices made for the specific brief — copying the categories is fine; copying the numbers
defeats the point of the whole skill.

```css
:root {
  /* Color — 4-6 named roles, each with a real hex and a stated job */
  --color-bg: #FCFAFA;              /* page background */
  --color-surface: #F5F5F5;         /* cards, panels */
  --color-text-primary: #2C2C2C;    /* body text, headings */
  --color-text-secondary: #6B6B6B;  /* captions, metadata */
  --color-border: #E0E0E0;
  --color-action-primary: #294056;  /* the one calibrated accent — see anti-slop-checklist.md */
  --color-feedback-success: #10B981;
  --color-feedback-error: #EF4444;

  /* Typography — display / body / mono, each with a real font stack */
  --font-display: /* your headline face */, serif;
  --font-body: /* your body face */, sans-serif;
  --font-mono: /* your data/code face */, monospace;
  --text-scale-ratio: 1.25; /* if using a modular scale */

  /* Spacing — a real scale, not ad-hoc gap-4 everywhere */
  --space-xs: 0.5rem;
  --space-sm: 1rem;
  --space-md: 2rem;
  --space-lg: 4rem;
  --space-xl: 6rem;

  /* Shape */
  --radius-button: 8px;
  --radius-card: 12px;

  /* Elevation — tint shadows toward the background hue instead of pure black */
  --shadow-card: 0 2px 8px rgba(0, 0, 0, 0.06);

  /* Motion */
  --ease-standard: cubic-bezier(0.4, 0, 0.2, 1);
  --duration-fast: 150ms;
  --duration-standard: 250ms;
}
```

A few of these deserve more than a placeholder comment:

- **Accent discipline.** Pick one primary accent. A second, sparingly-used accent for a
  distinct semantic purpose (a status color, say) is fine; two accents both competing for
  primary attention is how pages end up looking indecisive.
- **Off-black over pure black.** `#000000` text on a white page is harsher than it needs to
  be — a near-black (`#18181B`, `#1A1A1A`) reads as more considered.
- **Shadows tinted, not gray.** `rgba(0,0,0,0.06)` is a safe default, but a shadow tinted
  very slightly toward the background hue (a warm shadow on a warm background) reads as more
  intentional than a flat gray one.
- **Font stacks need real fallbacks.** Whatever the display/body faces are, give each a
  sane native fallback (`system-ui`, `serif`, `monospace`) for the flash before a webfont
  loads — see [media-and-assets.md](media-and-assets.md) for `font-display` and loading
  strategy.

## OKLCH, if you want it

Hex is fine, and it's what most of the sites you'll build should use — it's what everyone
reading the CSS already knows. Reach for OKLCH instead when you need to *generate* related
colors programmatically (tints, shades, or a hover state a fixed percentage lighter) and want
those steps to look evenly spaced to the eye, which hex and HSL don't reliably give you:

```css
--color-action-primary: oklch(45% 0.15 260);
--color-action-primary-hover: oklch(55% 0.15 260); /* same hue+chroma, lighter */
```

Don't switch the whole palette to OKLCH purely for novelty — it's a tool for a specific
problem (perceptually-uniform palette generation), not a default.

## Keeping multi-page builds consistent: a lightweight DESIGN.md

For anything past a single page, write the finished token system down in a `DESIGN.md` (or
`.design/DESIGN.md`) at the project root, and open it at the start of every subsequent page
instead of re-deriving the palette from memory. This is the same problem
[site-architecture.md](site-architecture.md)'s `SITE.md` solves for structure — one is the
site's visual contract, the other is its map.

```markdown
# Design System: [Project Name]

## 1. Visual theme & atmosphere
One paragraph: mood, density, the one sentence you'd use to describe this to a client.

## 2. Color palette & roles
- **[Descriptive name]** (`#hexcode`) — functional role
- ...

## 3. Typography
- Display: [face], used for [where]
- Body: [face]
- Mono: [face], used for [where]

## 4. Component conventions
- Buttons: [shape, states]
- Cards: [when used, corners, elevation]
- Forms: [label position, error styling]

## 5. Layout principles
Grid approach, containment width, breakpoint behavior.

## 6. Anti-patterns for this project
Anything from anti-slop-checklist.md that's especially tempting to slip into for this
particular brief — e.g. "no stock photography," "no card grids," "avoid centered layouts
entirely, this brand is asymmetric by definition."
```

Section 6 is worth customizing per project rather than leaving generic — the checklist in
`anti-slop-checklist.md` is universal, but which mistakes you're personally likely to make on
*this* brief is worth naming explicitly so a later pass (or a later session) catches it.
