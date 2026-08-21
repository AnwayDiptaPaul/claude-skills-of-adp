# Motion & Interactivity

This is the toolbox for executing the motion and interactivity principles from `SKILL.md` —
not a license to use more of it. Zero motion, or the same generic fade-in-up on every
section, is already a flagged tell in
[anti-slop-checklist.md](anti-slop-checklist.md#p2--cosmetic-but-telling). The fix for
generic motion is *purposeful* motion, not *more* motion, and the right tool for a given
effect is usually a smaller one than reflex reaches for.

## Choosing a motion stack

Default to the lightest tool that does the job, and go heavier only when the effect actually
needs it:

1. **Native CSS transitions and `@keyframes`** for anything state-based and simple — hover,
   focus, a menu opening, a basic fade or slide. Zero JavaScript, zero dependency, and it's
   almost always enough.
2. **CSS scroll-driven animations** (`animation-timeline`) for scroll-linked reveals,
   progress bars, and parallax — see below. This is now broadly supported and has replaced
   most of what used to need `IntersectionObserver` plus a class toggle.
3. **GSAP** when an effect genuinely needs pinned sections, scrubbed/scroll-linked
   choreography across multiple elements, or precise sequencing CSS can't express yet.
   It's free — including plugins that used to be paid, like ScrollTrigger and SplitText —
   and framework-agnostic, so it drops into a plain HTML/JS site with no build step:
   ```
   npm install gsap
   ```
   ```js
   import gsap from "gsap";
   import { ScrollTrigger } from "gsap/ScrollTrigger";
   gsap.registerPlugin(ScrollTrigger);
   ```
   ScrollTrigger specifically has no real native-CSS equivalent yet for pinning a section
   while scrubbing an animation against scroll position — reach for it exactly when that's
   the effect, not by default.
4. **Anime.js** as a lighter option (~9KB) when you want JavaScript-level control — timelines,
   SVG, staggered sequences — without GSAP's fuller footprint, and don't need ScrollTrigger's
   pinning/scrubbing specifically.

Skip React-only libraries (Motion, formerly Framer Motion) entirely here — they assume a
component tree that a hand-authored static site doesn't have.

## CSS scroll-driven animations

`animation-timeline` ties a `@keyframes` animation to scroll position instead of the clock,
runs on the compositor thread (smooth even under a busy main thread), and needs no JS at all:

```css
.reveal-on-scroll {
  opacity: 0;
  transform: translateY(24px);
  animation: reveal-up 1s linear both;
  animation-timeline: view();       /* tied to this element's own visibility */
  animation-range: entry 0% entry 40%;
}

@keyframes reveal-up {
  to { opacity: 1; transform: translateY(0); }
}

/* Feature detection — browsers that don't understand animation-timeline just
   ignore it, so give them the settled end state instead of a stuck, invisible one */
@supports not (animation-timeline: view()) {
  .reveal-on-scroll { opacity: 1; transform: none; }
}
```

`animation-timeline: scroll()` works the same way but ties to a scroll container's overall
progress instead of one element's visibility — useful for a reading-progress bar. Support is
broad across Chromium and Safari; Firefox has been catching up behind a flag, so the
`@supports` fallback above isn't optional polish, it's what keeps the page usable everywhere
in the meantime. This is still the wrong tool for pinning a section in place while scrubbing
a multi-step animation against it — that's GSAP ScrollTrigger's job, not this API's.

## View Transitions API — the flagship feature for a multi-page site

This is the single highest-leverage browser feature for exactly the kind of site this skill
builds: a folder-per-page static site with real navigations between real documents. It gives
native, GPU-accelerated cross-fades (or a custom animation) between two page loads, with no
client-side router and no JavaScript required for the baseline case.

**Opt in with two lines of CSS, once per page** (or once in a shared stylesheet every page
already loads):

```css
@view-transition {
  navigation: auto;
}
```

That's the entire baseline setup. In a browser that supports cross-document view transitions,
clicking an internal link now cross-fades instead of hard-cutting. In one that doesn't, the
navigation just happens normally — there is no broken state to code around, which is what
makes this safe to turn on today rather than wait for full support. Support is currently
strongest in Chromium and Safari, with Firefox mid-rollout — treat it as a progressive
enhancement, not a dependency, and don't build a feature that only works with it.

**Named transitions for shared elements** are what turn a generic cross-fade into something
that feels directly connected to the content — a project thumbnail on a listing page morphing
into that project's hero image on its detail page, for instance:

```css
/* projects/index.html — the listing page */
.project-thumb[data-project="project-one"] { view-transition-name: project-one-image; }

/* projects/project-one/index.html — the detail page */
.project-hero-image { view-transition-name: project-one-image; }
```

When both pages are visible in the same navigation, the browser animates between the two
elements sharing that name instead of cross-fading the whole page. Keep transition names
unique per element pair and don't assign one to everything — a page with dozens of named
transitions firing at once is slower and reads as chaotic, not polished.

If you want to go further, pairing this with the **Speculation Rules API** (prerendering the
pages a visitor is likely to click next) closes most of the remaining gap with an SPA's
perceived speed — worth knowing about, not something to reach for by default.

## Purposeful motion, mechanically

- **Animate `transform` and `opacity` only.** These skip layout and paint and run on the
  compositor — animating `width`, `height`, `top`, or `left` forces the browser to
  recalculate layout on every frame, which is the difference between smooth and janky. Watch
  for `transition: all` specifically — it's an easy default that quietly includes expensive
  properties along with the cheap ones; name the properties you actually mean to animate.
- **Calibrate duration and easing to what the motion represents**, not a single default for
  everything. Emil Kowalski's *Animations on the Web* is a well-regarded reference point
  here: fast, `ease-out` motion for something entering (it should feel like it's arriving
  under its own momentum and settling), symmetric or slightly longer easing for something
  leaving, and spring-based motion — rather than a fixed duration — for anything a person
  might interrupt mid-gesture, like a dragged panel, since a spring can change direction
  fluidly where a fixed-duration animation restarting from zero can't.
- **Respect `prefers-reduced-motion` globally, once**, rather than remembering it per
  component:
  ```css
  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
      animation-duration: 0.01ms !important;
      animation-iteration-count: 1 !important;
      transition-duration: 0.01ms !important;
      scroll-behavior: auto !important;
    }
  }
  ```

## CSS architecture for a site that stays consistent as it grows

**Cascade layers (`@layer`)** solve the specificity fights `SKILL.md` already warns about —
a `.section` type-adjacent selector quietly beating a `.cta` utility class isn't about which
selector is "stronger," it's about which layer it's in. Declare the order once, and anything
in a later layer wins over anything in an earlier one regardless of selector specificity:

```css
@layer reset, tokens, base, components, utilities;

@import url("reset.css") layer(reset);
@import url("tokens.css") layer(tokens);       /* the :root custom properties — design-tokens.md */
@import url("base.css") layer(base);
@import url("components.css") layer(components);
```

**Container queries (`@container`)** let a component adapt to the width of whatever it's
placed inside, not the viewport — the same card component can sit correctly in a full-width
grid on one page and a narrow sidebar on another without a page-specific override:

```css
.card-grid { container-type: inline-size; }

@container (min-width: 480px) {
  .card { grid-template-columns: auto 1fr; }
}
```

**`:has()`** lets a parent react to its children's state without JavaScript — a form field
that highlights when the input inside it is invalid, or a card whose layout shifts slightly
when it happens to contain an image:

```css
.form-field:has(:invalid) { border-color: var(--color-feedback-error); }
```

## A few more native features worth knowing about

- **`<dialog>`** for modals — built-in focus trapping, a `::backdrop` pseudo-element to style,
  and `.showModal()`/`.close()` in a couple lines of JS, no modal library required.
- **The Popover API** (`popovertarget`/`popover`) for tooltips, menus, and other transient
  UI — top-layer rendering (nothing to fight with `z-index` for) and dismiss-on-outside-click
  built in natively.
- **Custom Elements** for a component defined once and reused with real markup, not copied
  text — see
  [site-architecture.md's fourth shared-chrome option](site-architecture.md#keeping-header-nav-and-footer-consistent-across-pages)
  for using this specifically for header/footer; the same pattern works for anything reused
  across pages with real internal structure, like a project card.

## What this toolbox is not permission to do

Having more tools available is not a reason to use more of them on one page. A scroll-reveal
on every single section, a page transition added because it's possible rather than because
it serves the content, motion on elements nobody's attention needed directed toward — these
are still the P2 tell from the checklist, just executed with better APIs. Spend motion where
[SKILL.md](../SKILL.md#design-principles) already says to spend boldness: on the one thing
this build should be remembered for, not spread evenly across everything.
