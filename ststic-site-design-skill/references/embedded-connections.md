# Embedded Connections

A "static" site rarely means a site where nothing happens — it means the HTML is served as
files rather than rendered by a server per request. Most real sites still need a form that
goes somewhere, analytics, a map, and sometimes a chat widget or another API-backed feature.
Each of these is both a design surface and a specific engineering decision, and the wrong
default on the engineering side (a leaked API key, an unthrottled third-party script) can
undo a well-designed page fast.

The rule that overrides every pattern below: **a static site has no server to keep a secret
on.** Anything shipped in a `<script>` tag is visible to anyone who opens dev tools. If a
feature needs an API key, a database credential, or anything else that shouldn't be public,
it does not go in client-side JS — it goes behind a small serverless function or edge worker
that the browser calls instead, and the real secret lives only in that function's environment
config. This is the same shape regardless of host: a Cloudflare Worker, a Netlify Function, a
Vercel Edge Function, or an AWS Lambda behind API Gateway. The browser talks to your proxy;
your proxy (and only your proxy) talks to the third-party API with the real key attached
server-side.

## Forms

**Options without standing up your own backend:** Formspree, Netlify Forms (if already
hosting there), Getform, or a similar form-relay service — the form posts to their endpoint,
they email or webhook you the submission.

**Design it like a real form, not an afterthought:**
- Label every field (visually, not just via `placeholder` — placeholder text disappears the
  moment someone starts typing, which is a real accessibility problem for anyone who looks
  away mid-fill).
- Validate on the client for immediate feedback, but always also validate server-side (the
  form-relay service or your own function) — client-side validation is a courtesy, not
  security.
- Write real error and success states — see
  [SKILL.md § Writing in design](../SKILL.md#writing-in-design). "Something went wrong" tells
  a visitor nothing; "That email address looks incomplete" tells them what to fix.
- Add a honeypot field (a hidden input real users never fill, bots often do) or the form
  service's built-in spam filtering — an unprotected public form fills with spam within days
  of launch.

## Analytics

Decide what you're optimizing for before picking a tool:

- **Google Analytics (GA4)** — the default choice, free, deep feature set, but it's a
  meaningful third-party script (real weight, real privacy tradeoff) and in many
  jurisdictions requires a cookie-consent flow before it fires.
- **Privacy-focused alternatives** (Plausible, Fathom, and similar) — lighter scripts,
  typically no cookie-consent requirement since they don't do cross-site tracking, at the
  cost of some of GA's depth.

Whichever you use, load it with `async` or `defer` so it never blocks page render, and don't
add analytics you haven't been asked for — every script is a small performance and privacy
cost that should be justified, not defaulted to.

## Maps

An embedded Google Maps iframe is the simplest path, but a naive embed loads a meaningful
chunk of JS the instant the page does, whether or not anyone scrolls that far. Prefer a
**facade pattern**: show a lightweight static preview (a static map image, or just a styled
placeholder with the address) and swap in the real iframe only on click or when it scrolls
into view. This is the same idea as the video facade pattern below, applied to maps.

## Chat and AI widgets

If the "chat widget" is a hosted third-party product (Intercom, Crisp, and similar), it's
usually just a script tag — the vendor's own servers hold the relevant keys.

If it's a custom assistant backed by a model API, the proxy pattern at the top of this file
is not optional: the browser calls your own lightweight endpoint, which holds the real API
key server-side and forwards the request to the model provider. Never call the model API
directly from client-side JS with the key embedded — it will be extracted and abused within
hours of a public site going live. While you're building that proxy, also think about:

- **Rate limiting** — even a proxy without limits can run up a real bill if someone scripts
  requests against it.
- **Scope** — the proxy should do exactly one job (forward a chat message, say) rather than
  exposing a general-purpose passthrough to the underlying API.
- **Graceful failure** — if the proxy or the upstream API is down, the widget should say so
  plainly rather than hanging or failing silently (again, see
  [SKILL.md § Writing in design](../SKILL.md#writing-in-design) on error states).

## Video and social embeds

A raw YouTube/Vimeo `<iframe>` loads a surprising amount of third-party JS before anyone has
pressed play. The standard fix is a **facade**: render a static thumbnail with a play button
that looks like the real embed, and only inject the actual iframe on click. Visitors who
never press play never pay the loading cost. The same logic applies to embedded tweets/posts
and other social widgets — load the lightweight static version by default, upgrade to the
live embed on interaction or when it's actually in view.

## General principle

Every third-party script is a standing liability: it's something that can slow the page down,
leak user data to a vendor, or break silently when the vendor changes their API. Before adding
one, it's worth asking whether it's earning its place — and once it's in, load it as lazily as
the feature allows (`defer`/`async`, facade-on-interaction, or intersection-observer-triggered
loading) so the pages that don't need it don't pay for it.
