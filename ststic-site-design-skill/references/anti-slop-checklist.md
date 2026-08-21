# Anti-Slop Checklist

A diagnostic pass for the specific patterns that make a site read as generated rather than
designed. Skim this before you plan, and run it again — ideally alongside
`scripts/check_slop.py` — before you call anything finished.

None of these are arbitrary taste calls. Each one is a pattern that shows up so often in
unguided AI output that it's stopped communicating anything except "nobody made a specific
decision here." That's the actual failure mode: not that any single element is ugly, but that
its presence signals the rest of the page probably wasn't considered carefully either, and a
visitor's trust drops accordingly before they've read a word of copy.

## Severity tiers

Not every tell costs the same. Triage effort accordingly.

| Tier | What it signals | Fix cost |
|---|---|---|
| **P0 — screams AI** | Visible in the first second, on the hero, before any content registers | Usually a structural rework: palette, hero layout, or type pairing |
| **P1 — reads as AI on inspection** | Noticed once someone looks past the hero — components, icons, spacing reflexes | Usually a targeted swap, not a rebuild |
| **P2 — cosmetic** | Only visible to someone who builds a lot of these | Cheap to fix, easy to forget |

### P0 — screams AI

| Signal | Why it happens | Fix |
|---|---|---|
| "Inter Default" — Inter, Roboto, or system-ui as the only typeface, no display face | It's the safe fallback every framework ships with | Pick a headline/body pairing specific to this brief (see [design-tokens.md](design-tokens.md)) |
| Purple-to-blue gradient, or a violet/indigo glow behind the hero | The single most common AI color signature in 2025–2026 output | Semantic color tokens with one calibrated accent — see the banned-colors list below |
| Centered hero + three equal feature cards underneath | The most-generated layout shape there is | Break it with CSS Grid asymmetry: split-screen, left-aligned, bento, zig-zag |
| Fabricated statistics ("99.98% uptime," "124ms avg. response," any number nobody gave you) | Filling an empty slot with a plausible-looking number | Use a real number, or a structural placeholder like `[metric]` — never a fake one |

### P1 — reads as AI on inspection

| Signal | Why it happens | Fix |
|---|---|---|
| Uniform `rounded-2xl` / `shadow-lg` on every card, everywhere | Reflexive default, not a decision | Vary radius and elevation by what's actually being communicated; use border-top dividers instead of cards in dense layouts |
| Lucide "Sparkles" or "ArrowRight" on every button and section | Default icon set, default icon choice | Curate a smaller, purposeful icon set; not every link needs an arrow |
| FAQ accordion glued to the bottom of every page regardless of content | Template habit | Only include an FAQ if there are real, specific questions worth answering |
| "Elevated middle pricing tier" on any 3-column pricing table | Copied SaaS-template convention | Only elevate a tier if there's an actual reason to steer people there |
| Inset tabs used for top-level page navigation | Mistaking a component for a nav pattern | Reserve tabs for switching views within a section, not for primary site navigation |
| `Space Grotesk` as the "distinctive" font | It became the *safe* alternative to Inter through overuse | Go further — Fraunces, Instrument Serif, a custom or licensed face, a real mono for a dev-tool feel |

### P2 — cosmetic but telling

| Signal | Fix |
|---|---|
| Flat `gap-4` / `p-6` spacing everywhere, no rhythm | Vary spacing intentionally to guide the eye — see spacing scale in [design-tokens.md](design-tokens.md) |
| Zero motion, or the same generic fade-in-up on every element | Purposeful micro-interactions that communicate state, not decoration for its own sake |
| `LABEL // YEAR` formatting ("SYSTEM // 2026") | Not real typographic convention — drop it |
| Emoji used as icons or bullets in body copy | Use real icons or none |

## Banned or high-risk, specifically

**Typography.** Inter, Roboto, and Arial as the *only* face on a page marketed as distinctive.
Generic serif stacks (Times New Roman, Georgia, Garamond, Palatino) — if a serif is called
for, use a distinctive modern one (Fraunces, Instrument Serif, Editorial New) and never in a
dashboard or utility UI. Space Grotesk used as if it were still a bold choice.

**Color.** Purple-to-blue gradients and violet glows. Pure black (`#000000` — use an
off-black or a near-black like `#18181B`). More than one accent color competing for
attention. Mixed warm/cool grays within the same page. Oversaturated accents (roughly >80%
saturation) that feel like they're shouting.

**Layout.** Centered hero followed by three identical cards. Any layout built entirely from
`calc()` percentage math instead of CSS Grid. `height: 100vh` for full-height sections (use
`min-height: 100dvh` — `100vh` jumps on mobile Safari when the address bar hides).

**Copy.** Sentences opening with "Empower," "Unlock," "Elevate," or "Transform." The phrases
"seamless," "powerful," or "built for modern teams." Generic placeholder names ("John Doe,"
"Acme Inc.," "Jane Smith") left in shipped copy. Every concrete claim should carry a real
number, name, or mechanism — otherwise cut it. See [SKILL.md § Writing in design](../SKILL.md#writing-in-design).

**Images.** Broken or generic hotlinked stock photography (dead Unsplash URLs are a
particularly common tell). Obviously-AI-generated "plastic" illustration standing in for real
product screenshots. See [media-and-assets.md](media-and-assets.md) for what to do instead.

**Filler UI text.** "Scroll to explore," bouncing chevrons, scroll-down arrows. If the content
doesn't pull people down the page on its own, more filler text won't fix that.

## Pre-ship checklist

Run through this — and `scripts/check_slop.py` — before calling a build done:

- [ ] No sentence opens with a banned verb; no banned filler phrase appears anywhere
- [ ] Every concrete claim (a number, a stat, a testimonial) is real or clearly a placeholder — nothing fabricated
- [ ] Zero P0 tells: no default-Inter-only type, no purple/blue gradient, no centered-hero-plus-three-cards
- [ ] Colors and spacing trace back to the token system, not one-off hex values invented per component
- [ ] At least one layout section breaks the standard centered vertical stack
- [ ] No hotlinked stock photography or placeholder illustration standing in as if it were final art
- [ ] Every image, icon, and animation is there because it does something, not because it's a default
