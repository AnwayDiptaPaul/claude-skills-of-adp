---
name: static-site-design
description: >-
  Use when designing, building, redesigning, or auditing a static website: a multi-page
  HTML/CSS/JS site, company or marketing site, portfolio, docs site, or landing page for
  GitHub Pages, Cloudflare Pages, Netlify, or Vercel. Trigger even without the word
  "website" — "build a site for my business," "add a contact form / map / chat widget," "set
  up analytics," "our site looks AI-generated," or naming a brand to design for. Covers the
  full build: distinctive non-templated design, file and folder architecture for multi-page
  consistency, safely wiring up real integrations (forms, analytics, maps, chat widgets,
  APIs), image/font/icon assets, accessibility, and performance — while actively guarding
  against "AI slop" (Inter-and-purple-gradient templates, centered-hero-plus-three-cards
  layouts, generic Tailwind defaults, fabricated stats, AI copywriting clichés). Not for
  single-file chat mockups or React/SPA component libraries — use frontend-design or
  web-artifacts-builder instead.
license: >-
  Apache-2.0. Derived from Anthropic's frontend-design skill and Google's stitch-skills
  (both Apache-2.0). See NOTICE.md for attribution and a summary of changes.
---

# Static Site Design

Approach this as the working design lead *and* build lead at a small studio known for two
things at once: every client gets a visual identity that couldn't be mistaken for anyone
else's, and every site that ships actually works — fast, accessible, wired up correctly to
the real services behind it. This client has already rejected proposals that felt templated,
and has also been burned by a "beautiful" mockup that fell apart the moment it needed a real
contact form. You're doing both jobs on this project: no handoff, no excuse.

This skill governs real, deployable output — a folder of HTML, CSS, JS, docs, and media that
someone will actually push to a host. That's different from a one-off React component or a
throwaway chat mockup: it means file structure, multi-page consistency, and live
integrations matter as much as the first screen looks good. If the task really is a
single-file interactive artifact for this conversation, or a React/shadcn component system,
this skill's design judgment still applies but its build guidance won't all fit — see
`frontend-design` or `web-artifacts-builder` instead.

## Ground it in the subject

If the brief doesn't pin down what the site or business actually is, pin it yourself before
designing: name one concrete subject, its audience, and the site's single job, and state your
choice. Check memory and the conversation for the human's own context — a company they've
described, a domain they work in, sites they've built before, brand assets they've already
produced — and use that as ground truth rather than inventing generic substitutes. The
subject's own world — its materials, instruments, artifacts, and vernacular — is where
distinctive choices come from. Build with the brief's real content and subject matter
throughout, and use the client's real logo, copy, photography, and data wherever it exists
rather than placeholder stand-ins (see [Media & assets](references/media-and-assets.md) for
what to do when it doesn't exist yet).

## The bar: not AI slop

Unguided generation regresses toward the statistical median of its training data, and right
now that median has a very recognizable look: a warm cream background with a high-contrast
serif and a terracotta accent, or a near-black page with one acid-green or violet glow, or a
centered hero over a row of three identical rounded cards. None of these are wrong in
principle — they're wrong because they show up regardless of what the brief actually is. A
generic, templated interface reads as a lack of care, and it costs trust before a visitor
reads a word of copy.

For calibration, specifically: AI-generated design right now clusters around three looks —
(1) a warm cream background (near `#F4F1EA`) with a high-contrast serif display and a
terracotta or warm-clay accent (often near `#D97757` — Anthropic's own Claude-interaction
accent, so on a user's brief it reads as a tell); (2) a near-black background with a single
bright acid-green or vermilion accent; (3) a broadsheet-style layout with hairline rules,
zero border-radius, and dense newspaper-like columns. All three are legitimate for some
briefs, but they are defaults rather than choices, and they appear regardless of subject.
Where the brief pins down a visual direction, follow it exactly — the brief's own words
always win, including when it asks for one of these looks. Where it leaves an axis free,
don't spend that freedom on one of these defaults.

Before building anything, skim
[references/anti-slop-checklist.md](references/anti-slop-checklist.md) — it's the fast
diagnostic pass for the specific fonts, gradients, layouts, component reflexes, and copy
clichés that read as generated rather than designed, organized by how badly each one gives
the game away. Come back to it again before you ship: it doubles as the final QA pass, and
`scripts/check_slop.py` can catch a good chunk of it mechanically (see
[Quality bar](#quality-bar-before-you-call-it-done) below).

## Design principles

The hero is a thesis. Open with the most characteristic thing in the subject's world, in
whatever form makes sense for it: a headline, an image, an animation, a live demo, an
interactive moment. Be deliberate with your choice — a big number with a small label,
supporting stats, and a gradient accent is the template answer; only use it if it's truly the
best option for this brief. Never invent the number to fill the slot (see the fabricated-data
ban in the checklist) — if there's no real metric yet, say so structurally instead of
guessing one that sounds plausible.

Typography carries the personality of the page. Pair the display and body faces
deliberately, not the same families you'd reach for on any other project, and set a clear
type scale with intentional weights, widths, and spacing. Make the type treatment itself a
memorable part of the design, not a neutral delivery vehicle for the content.

Structure is information. Structural devices — numbering, eyebrows, dividers, labels —
should encode something true about the content, not decorate it. Numbered markers (01 / 02 /
03) are only appropriate if the content actually is a sequence, like a real process or a
timeline where order carries information the reader needs. Question whether a device like
that actually earns its place before reaching for it out of habit.

Leverage motion deliberately. Think about where, and whether, animation can serve the
subject: a page-load sequence, a scroll-triggered reveal, hover micro-interactions, ambient
atmosphere. An orchestrated moment usually lands harder than scattered effects. But less is
often more — animation on every element is one of the fastest ways a page reads as
AI-generated. When you do animate, animate `transform` and `opacity`, not `top`/`left`/
`width`/`height` — it's the difference between smooth on every device and janky on most of
them. [references/motion-and-interactivity.md](references/motion-and-interactivity.md) has
the current toolkit for executing this well — native CSS, scroll-driven animation, GSAP, and
the View Transitions API for page-to-page navigation — and a rule of thumb for which one a
given effect actually calls for.

Match complexity to the vision. Maximalist directions need elaborate execution; minimal
directions need precision in spacing, type, and detail. Elegance is executing the chosen
vision well, at every breakpoint (more on that in
[Media & assets](references/media-and-assets.md) and
[Accessibility & performance](references/accessibility-performance.md)).

Consider written content carefully. A design brief often doesn't contain real copy, and it's
up to you to write it. Copy can make a design feel as templated as the layout does — see
[Writing in design](#writing-in-design) below.

## Process: brainstorm, plan, critique, build, critique again

Work in two passes before you touch production code.

**First, brainstorm a compact design plan.** For a single page this can stay in your head or
scratch notes; for anything with more than two or three pages, write it down as a token
system, since you'll need to hold it steady across every page you build:

- **Color** — 4–6 named values with hex codes and a functional role for each (not just
  "blue," but what it's *for*).
- **Type** — the typefaces for 2+ roles: a characterful display face used with restraint, a
  complementary body face, and a utility/mono face for captions, code, or data if needed.
- **Layout** — a layout concept in one-sentence prose plus an ASCII wireframe or two, enough
  to compare options before committing.
- **Signature** — the single unique element this build will be remembered by, one that
  embodies the brief specifically.

[references/design-tokens.md](references/design-tokens.md) has the full pattern for turning
this into real CSS custom properties, naming conventions, and — for multi-page builds — a
lightweight `DESIGN.md` you keep alongside the project so every page you write later pulls
from the same source of truth instead of drifting.

**Then review that plan against the brief before building.** If any part of it reads like the
generic default you'd produce for any similar brief — work through a similar prompt mentally
and see if you land somewhere similar — revise that part, and note what you changed and why.
Only once you've confirmed the plan is actually specific to this brief should you start
writing code, following the revised plan and deriving every color and type decision from it.

When you do write the code, watch your CSS selector specificity. It's easy to write classes
that quietly cancel each other out — a type selector like `.section` fighting an
element/utility selector like `.cta` is a common way padding and margin go wrong between
sections without an obvious cause.

Do most of this planning and iteration in your own thinking, and only surface ideas once
you have real confidence they'll land. If you're keeping working notes as you go, a quick
line on what you tried and rejected helps later passes avoid repeating a dead end.

## Static site architecture

A real static site is a folder, not a single file, and the folder's shape is a design
decision as much as the CSS is. Before writing the first page, decide:

- **Where pages, styles, scripts, and media live, and how every link resolves.** Give each
  page its own folder with an `index.html` inside, and write every internal link and asset
  reference relative to the file it's in — never root-absolute (`/about.html`) — so the same
  folder works unmodified at a domain root, a hosting subpath, or opened straight from disk.
  This is a rule, not a style preference: a root-absolute path silently 404s the moment the
  site's deploy path changes.
- **How header/nav/footer stay consistent across every page without a framework** — there
  are a few real options with different tradeoffs (plain duplication, author-time include
  stitching, runtime `fetch()` injection, Custom Elements), not one correct answer.
- **What the deploy target expects.** GitHub Pages, Cloudflare Pages, Netlify, and Vercel
  each have their own conventions for redirects, headers, and custom domains that are much
  cheaper to plan for up front than to retrofit.
- **How the site stays navigable and indexable** — sitemap, meta tags, semantic landmarks,
  a favicon set — which are easy to treat as an afterthought and expensive to bolt on later.

[references/site-architecture.md](references/site-architecture.md) covers all of this in
depth, including a lightweight `SITE.md` planning template worth writing for anything past a
single page — it's the same idea as the design token system, but for the site's structure and
roadmap instead of its visual language, and it keeps a multi-page build from drifting
page-to-page the way an unplanned one does.

## Embedded connections

Most real sites aren't static in the sense of "nothing happens" — they have a contact form
that goes somewhere, an analytics snippet, a map, sometimes a chat widget or another
API-backed feature. Each of these is a design surface (its states need the same care as
everything else — see [Writing in design](#writing-in-design) for error and empty states)
and an engineering decision with a wrong answer that's tempting to reach for: **never ship a
private API key in client-side JavaScript.** Anything that needs a secret belongs behind a
serverless function or edge worker that the browser calls instead — the same pattern as
proxying a model API through a Cloudflare Worker rather than calling it straight from the
page.

[references/embedded-connections.md](references/embedded-connections.md) covers the concrete
patterns for forms, analytics, maps, chat/AI widgets, and video or social embeds, including
how to keep third-party scripts from wrecking the performance budget you just earned.

## Media & assets

Images, icons, and fonts are where "distinctive" and "generic" show up as fast as anywhere
else on the page. A stock photo that's clearly stock, a broken hotlinked Unsplash URL, or the
same three Lucide icons every AI-built page reaches for will undercut careful type and color
work in about half a second of scrolling. [references/media-and-assets.md](references/media-and-assets.md)
covers sourcing real vs. placeholder imagery honestly, image formats and optimization,
font loading, icon selection, and the favicon/OG-image checklist that's easy to forget until
someone shares the link and the preview card is blank.

## Quality bar before you call it done

Spend your boldness in one place. Let the signature element be the one memorable thing, keep
everything around it quiet and disciplined, and cut any decoration that doesn't serve the
brief. Not taking a risk can be a risk itself — but a page that's loud everywhere is louder
nowhere in particular. Consider Chanel's advice: before leaving the house, take a look in the
mirror and remove one accessory.

Build to a quality floor without announcing it, and don't treat this as optional polish —
it's the difference between a page that photographs well and a site a real visitor can
actually use:

- Responsive down to mobile, with no horizontal scroll at any width you claim to support.
- Visible keyboard focus on every interactive element, and `prefers-reduced-motion` respected.
- Real alt text, a sane heading hierarchy, and color contrast that holds up — status should
  never be color alone.
- Fast: optimized images, deferred non-critical JS, no render-blocking surprises.

[references/accessibility-performance.md](references/accessibility-performance.md) has the
full checklist and the viewport widths worth actually testing at. Take screenshots and
critique your own work as you build if your environment supports it — a picture is worth a
thousand tokens, and things that read fine as markup often don't read fine as a rendered
page. Before you call a build finished, run it through the anti-slop pass one more time:

```bash
python3 scripts/check_slop.py <path-to-your-site>
```

The script catches a meaningful subset of the checklist mechanically — banned fonts and
gradients, leftover placeholder copy and images, forbidden marketing clichés, root-absolute
links that won't survive a move to a different host or subpath, a few accessibility
landmines — but it's a floor, not a substitute for the read-through. It can't tell you
whether the hero is actually a thesis or the layout actually earned its asymmetry; that part
is still yours.

## Writing in design

Words appear in a design for one reason: to make it easier to understand, and therefore
easier to use. They are design material, not decoration. Bring the same intentionality to
copy that you'd bring to spacing and color. Before writing anything, ask what the design
needs to say, and how it can best be said to help the person navigate the experience.

Write from the end user's side of the screen. Name things by what people control and
recognize, never by how the system is built — a person manages notifications, not webhook
config. Describe what something does in plain terms rather than selling it. Being specific is
always better than being clever, and it's also the fastest way to avoid the clichés that
mark a page as machine-written: sentences that open with "Empower," "Unlock," "Elevate," or
"Transform," and phrases like "seamless," "powerful," or "built for modern teams" read as
filler because they carry no information specific to this product. Every real claim should
be either concrete (a number, a name, a mechanism) or cut.

Use active voice as default. A control should say exactly what happens when it's used: "Save
changes," not "Submit." An action keeps the same name through the whole flow, so the button
that says "Publish" produces a toast that says "Published." The vocabulary of an interface is
the signposting for someone navigating the product — cohesion and consistency are how people
learn their way around it.

Treat failure and emptiness as moments for direction, not mood. Explain what went wrong and
how to fix it, in the interface's voice rather than a person's. Errors don't apologize, and
they're never vague about what happened. An empty screen is an invitation to act, not a dead
end with "no data" stamped on it.

Keep the register conversational and tuned: plain verbs, sentence case, no filler, tone
matched to the brand and the audience. Let each element do exactly one job — a label labels,
an example demonstrates, and nothing quietly does double duty.

## Reference map

| File | Read it when... |
|---|---|
| [references/anti-slop-checklist.md](references/anti-slop-checklist.md) | Before building (diagnostic pass) and again before shipping (QA pass) |
| [references/design-tokens.md](references/design-tokens.md) | Turning your brainstormed plan into real CSS custom properties, and keeping multi-page builds consistent |
| [references/site-architecture.md](references/site-architecture.md) | Setting up folders, relative linking, shared nav/header/footer, SEO basics, and deploy-target specifics |
| [references/embedded-connections.md](references/embedded-connections.md) | Wiring up a form, analytics, a map, a chat widget, or any API-backed feature |
| [references/media-and-assets.md](references/media-and-assets.md) | Sourcing and optimizing images, icons, fonts, and favicons |
| [references/motion-and-interactivity.md](references/motion-and-interactivity.md) | Picking a motion/animation approach, wiring up page transitions, or reaching for a modern CSS feature |
| [references/accessibility-performance.md](references/accessibility-performance.md) | Final QA — accessibility, performance, and what to actually test |
| `scripts/check_slop.py` | Mechanical pass for the checklist's most detectable items — run before you ship |
