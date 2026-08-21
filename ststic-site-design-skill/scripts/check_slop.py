#!/usr/bin/env python3
"""
check_slop.py -- mechanical pass for references/anti-slop-checklist.md

Scans HTML/CSS/JS(X)/TS(X) files under a directory for the subset of the checklist
that's actually detectable by pattern matching: banned first-choice fonts, purple-to-blue
gradients, pure black, reflexive Tailwind utility classes, forbidden copywriting clichés,
leftover placeholder names/images, emoji-as-icon, LABEL // YEAR formatting, wasteful
`transition: all`, root-absolute internal links/assets that won't survive a change of host
or subpath, internal links to a bare `.html` file instead of the folder+index.html pattern,
and a couple of accessibility landmines (images with no alt attribute, click handlers on
non-interactive elements). CSS/JS "/* */" and HTML "<!-- -->" comments are excluded from
every check, so a comment explaining a decision ("/* deliberately not pure black */") won't
get flagged as if it were live code.

This is a floor, not the whole checklist -- it can't tell you whether the hero is actually
distinctive or the copy is actually specific to this brief. Read
references/anti-slop-checklist.md for the rest.

Usage:
    python3 check_slop.py [path]        # defaults to the current directory

Exit code: 0 if no findings, 1 if findings exist. A non-zero exit is a prompt to review
the listed lines, not an assertion that the site is broken -- some of these checks
(forbidden words in particular) can fire on legitimate, unrelated usage.
"""

import argparse
import colorsys
import re
import sys
from pathlib import Path

SCAN_EXTENSIONS = {".html", ".htm", ".css", ".js", ".jsx", ".ts", ".tsx"}
SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".next", "vendor", "__pycache__"}


class Finding:
    def __init__(self, path, line_no, tier, category, message, snippet=""):
        self.path = path
        self.line_no = line_no
        self.tier = tier  # "P0" | "P1" | "P2" | "A11Y"
        self.category = category
        self.message = message
        self.snippet = snippet.strip()[:100]

    def render(self):
        loc = f"{self.path}:{self.line_no}"
        head = f"  [{self.tier}] {loc} -- {self.category}"
        if self.snippet:
            return f"{head}\n        {self.message}\n        > {self.snippet}"
        return f"{head}\n        {self.message}"


# ---------------------------------------------------------------------------
# Color helpers -- used by the gradient / pure-black checks
# ---------------------------------------------------------------------------

HEX_RE = re.compile(r'#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b')
NAMED_HUE_BUCKET = {
    "purple": "purple", "violet": "purple", "indigo": "purple", "fuchsia": "purple",
    "blueviolet": "purple", "mediumpurple": "purple", "darkviolet": "purple",
    "blue": "blue", "royalblue": "blue", "dodgerblue": "blue", "cornflowerblue": "blue",
}


def hex_to_hue(token):
    """Return hue in degrees for a hex color, or None if it's near-neutral (gray/black/white)."""
    token = token.lstrip('#')
    if len(token) == 3:
        token = ''.join(c * 2 for c in token)
    if len(token) != 6:
        return None
    try:
        r = int(token[0:2], 16) / 255
        g = int(token[2:4], 16) / 255
        b = int(token[4:6], 16) / 255
    except ValueError:
        return None
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    if s < 0.15 or l < 0.05 or l > 0.95:
        return None  # too desaturated / too dark / too light for hue to mean anything
    return h * 360.0


def hue_bucket(hue):
    if hue is None:
        return None
    if 255 <= hue <= 300:
        return "purple"
    if 205 <= hue < 255:
        return "blue"
    return None


def find_matching_paren(text, open_paren_idx):
    """Given the index of a '(', return the index of its matching ')'."""
    depth = 1
    i = open_paren_idx + 1
    while i < len(text) and depth:
        if text[i] == '(':
            depth += 1
        elif text[i] == ')':
            depth -= 1
        i += 1
    return i - 1 if depth == 0 else -1


def line_of(text, pos):
    return text.count('\n', 0, pos) + 1


# CSS/JS "/* ... */" and HTML "<!-- ... -->" comments, blanked (not removed) so line numbers
# and match positions stay valid. A pattern inside a comment -- most often someone explaining
# a decision, e.g. "/* deliberately not pure black */" -- isn't live code and shouldn't be
# flagged as if it were.
_COMMENT_RES = (re.compile(r'/\*.*?\*/', re.DOTALL), re.compile(r'<!--.*?-->', re.DOTALL))


def strip_comments(text):
    def blank(m):
        return re.sub(r'[^\n]', ' ', m.group(0))
    for pattern in _COMMENT_RES:
        text = pattern.sub(blank, text)
    return text


# ---------------------------------------------------------------------------
# Text-pattern checks
# ---------------------------------------------------------------------------

FONT_FAMILY_RE = re.compile(r'font-family\s*:\s*([^;{}"\']+)', re.IGNORECASE)
BANNED_FIRST_FONTS = {"inter", "roboto", "arial", "helvetica", "helvetica neue"}

FORBIDDEN_OPENERS = ["empower", "unlock", "elevate", "transform", "revolutionize", "unleash"]
FORBIDDEN_PHRASES = [
    "seamless integration", "seamlessly integrate", "built for modern teams",
    "cutting-edge", "next-gen", "state-of-the-art", "game-changing",
]
PLACEHOLDER_NAMES = ["john doe", "jane doe", "jane smith", "acme inc", "acme corp", "lorem ipsum"]

LABEL_YEAR_RE = re.compile(r'\b[A-Z]{3,}\s*//\s*(19|20)\d{2}\b')

TAILWIND_REFLEX = {
    r'\brounded-2xl\b': "reflexive default radius -- vary it or justify it for this brief",
    r'\bshadow-lg\b': "reflexive default shadow -- tint and size it deliberately instead",
    r'\bbg-indigo-600\b': "default Tailwind indigo -- pull from your token palette instead",
    r'\bbg-purple-600\b': "default Tailwind purple -- the single most common AI accent color",
    r'\bh-screen\b': "use min-h-screen or min-h-[100dvh] -- h-screen breaks on mobile Safari",
}

EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF\u2700-\u27BF]"
)

UNSPLASH_RE = re.compile(r'unsplash\.com/[^\s"\'()]+', re.IGNORECASE)
PLACEHOLDER_IMG_RE = re.compile(r'via\.placeholder\.com|placeholder\.com/\d+', re.IGNORECASE)

IMG_NO_ALT_RE = re.compile(r'<img\b(?![^>]*\balt\s*=)[^>]*>', re.IGNORECASE)
CLICK_HANDLER_RE = re.compile(
    r'<(div|span)\b(?![^>]*\brole\s*=)(?![^>]*\btabindex\s*=)[^>]*\bonclick\s*=',
    re.IGNORECASE,
)

FULL_HEIGHT_VH_RE = re.compile(r'(?<!min-)(?<!max-)height\s*:\s*100vh\b', re.IGNORECASE)
TRANSITION_ALL_RE = re.compile(r'transition\s*:\s*all\b', re.IGNORECASE)

# href="/foo" / src="/foo" -- a single leading slash, not "//" (protocol-relative) and not
# a full scheme like "https://". Matches data-src etc. too, which is intentional: any
# attribute holding a URL has the same portability problem.
ROOT_ABSOLUTE_ATTR_RE = re.compile(
    r'\b(href|src)\s*=\s*(["\'])(/(?!/))([^"\']*)\2', re.IGNORECASE
)
# url(/foo) in CSS (background-image, @font-face src, etc.), quoted or not.
ROOT_ABSOLUTE_CSS_URL_RE = re.compile(
    r'url\(\s*([\'"]?)(/(?!/))([^\'")]*)\1\s*\)', re.IGNORECASE
)

# href="something.html" or href="folder/something.html" where the target isn't index.html --
# a candidate for the folder+index.html clean-URL pattern instead. Excludes external/scheme
# links, in-page anchors, mailto:, and tel:.
INTERNAL_HTML_LINK_RE = re.compile(r'href\s*=\s*["\']([^"\'#]+\.html)(#[^"\']*)?["\']', re.IGNORECASE)


def check_gradients(text, path, findings):
    for m in re.finditer(r'(?:linear|radial)-gradient\s*\(', text, re.IGNORECASE):
        open_idx = m.end() - 1
        close_idx = find_matching_paren(text, open_idx)
        if close_idx == -1:
            continue
        inner = text[open_idx + 1:close_idx]
        buckets = set()
        for hexm in HEX_RE.finditer(inner):
            b = hue_bucket(hex_to_hue(hexm.group(0)))
            if b:
                buckets.add(b)
        for name, bucket in NAMED_HUE_BUCKET.items():
            if re.search(rf'\b{name}\b', inner, re.IGNORECASE):
                buckets.add(bucket)
        if "purple" in buckets and "blue" in buckets:
            findings.append(Finding(
                path, line_of(text, m.start()), "P0", "purple-to-blue gradient",
                "This is the single most recognizable AI color signature -- replace with "
                "a semantic token from your palette.",
                text[m.start():close_idx + 1],
            ))


def check_pure_black(text, path, findings):
    for m in re.finditer(r'#(000000|000)\b', text):
        findings.append(Finding(
            path, line_of(text, m.start()), "P2", "pure black",
            "Pure #000 reads harsher than intended -- use an off-black (e.g. #18181B).",
            text[max(0, m.start() - 20):m.start() + 20],
        ))


def check_fonts(text, path, findings):
    for m in FONT_FAMILY_RE.finditer(text):
        stack = m.group(1)
        first = stack.split(',')[0].strip().strip('"\'').lower()
        if first in BANNED_FIRST_FONTS:
            findings.append(Finding(
                path, line_of(text, m.start()), "P0", "default typeface",
                f'"{first}" as the primary face -- pick a headline/body pairing specific '
                f'to this brief (see references/design-tokens.md).',
                m.group(0),
            ))


def check_tailwind_reflex(text, path, findings):
    for pattern, message in TAILWIND_REFLEX.items():
        for m in re.finditer(pattern, text):
            findings.append(Finding(
                path, line_of(text, m.start()), "P1", "reflexive utility class",
                message, m.group(0),
            ))


def check_full_height(text, path, findings):
    for m in FULL_HEIGHT_VH_RE.finditer(text):
        findings.append(Finding(
            path, line_of(text, m.start()), "P2", "100vh full height",
            "min-height: 100dvh avoids the mobile-Safari address-bar jump that height:100vh causes.",
            text[max(0, m.start() - 10):m.start() + 30],
        ))
    for m in TRANSITION_ALL_RE.finditer(text):
        findings.append(Finding(
            path, line_of(text, m.start()), "P2", "transition: all",
            "Animates every property, including expensive ones -- name transform/opacity "
            "explicitly instead (see references/motion-and-interactivity.md).",
            text[max(0, m.start() - 10):m.start() + 30],
        ))


def check_link_portability(text, path, findings):
    for m in ROOT_ABSOLUTE_ATTR_RE.finditer(text):
        findings.append(Finding(
            path, line_of(text, m.start()), "LINK", "root-absolute path",
            "Starts with / -- breaks if the site is hosted at a subpath (a GitHub Pages "
            "project repo, a preview deploy, a moved domain). Use a relative path instead "
            "(see references/site-architecture.md).",
            m.group(0),
        ))
    for m in ROOT_ABSOLUTE_CSS_URL_RE.finditer(text):
        findings.append(Finding(
            path, line_of(text, m.start()), "LINK", "root-absolute path",
            "Starts with / -- breaks if the site is hosted at a subpath. Use a relative "
            "path instead (see references/site-architecture.md).",
            m.group(0),
        ))
    for m in INTERNAL_HTML_LINK_RE.finditer(text):
        href = m.group(1)
        if re.match(r'^(https?:)?//', href, re.IGNORECASE):
            continue
        if href.lower().startswith(('mailto:', 'tel:', 'javascript:')):
            continue
        basename = href.rsplit('/', 1)[-1]
        if basename.lower() != 'index.html':
            findings.append(Finding(
                path, line_of(text, m.start()), "LINK", "non-index internal link",
                f'"{href}" points at a bare filename -- consider the folder + index.html '
                f'pattern (see references/site-architecture.md) for clean, portable URLs.',
                m.group(0),
            ))


def check_copy(text, path, findings):
    for word in FORBIDDEN_OPENERS:
        # Case-sensitive, title-case or ALL-CAPS only -- a real sentence opener ("Transform
        # your workflow", "TRANSFORM YOUR WORKFLOW"), never all-lowercase. This matters most
        # for "transform" specifically, which is also the correct, recommended CSS property
        # name (transition: transform ...) -- matching it case-insensitively would flag the
        # exact pattern this skill tells people to use.
        pattern = rf'\b({word.capitalize()}|{word.upper()})\b'
        for m in re.finditer(pattern, text):
            findings.append(Finding(
                path, line_of(text, m.start()), "P0", "AI copywriting cliche",
                f'"{m.group(0)}" -- see references/anti-slop-checklist.md and '
                f'SKILL.md § Writing in design.',
                text[max(0, m.start() - 30):m.start() + 40],
            ))
    for phrase in FORBIDDEN_PHRASES:
        for m in re.finditer(re.escape(phrase), text, re.IGNORECASE):
            findings.append(Finding(
                path, line_of(text, m.start()), "P0", "AI copywriting cliche",
                f'"{phrase}" carries no information specific to this product.',
                text[max(0, m.start() - 20):m.start() + 60],
            ))
    for name in PLACEHOLDER_NAMES:
        for m in re.finditer(re.escape(name), text, re.IGNORECASE):
            findings.append(Finding(
                path, line_of(text, m.start()), "P0", "placeholder content left in",
                f'"{m.group(0)}" looks like unreplaced placeholder copy.',
                text[max(0, m.start() - 20):m.start() + 40],
            ))
    for m in LABEL_YEAR_RE.finditer(text):
        findings.append(Finding(
            path, line_of(text, m.start()), "P2", "LABEL // YEAR formatting",
            "Not a real typographic convention -- drop it.",
            m.group(0),
        ))


def check_emoji(text, path, findings):
    for m in EMOJI_RE.finditer(text):
        findings.append(Finding(
            path, line_of(text, m.start()), "P2", "emoji in content",
            "Emoji used as an icon or bullet -- use a real icon or none.",
            text[max(0, m.start() - 20):m.start() + 5],
        ))


def check_images(text, path, findings):
    for m in UNSPLASH_RE.finditer(text):
        findings.append(Finding(
            path, line_of(text, m.start()), "P1", "hotlinked stock image",
            "Verify this URL is stable, or self-host the image -- see references/media-and-assets.md.",
            m.group(0),
        ))
    for m in PLACEHOLDER_IMG_RE.finditer(text):
        findings.append(Finding(
            path, line_of(text, m.start()), "P0", "placeholder image left in",
            "Looks like a placeholder-service image was never swapped for real art.",
            m.group(0),
        ))
    for m in IMG_NO_ALT_RE.finditer(text):
        findings.append(Finding(
            path, line_of(text, m.start()), "A11Y", "missing alt attribute",
            'Add alt="..." (descriptive) or alt="" (decorative) -- see '
            'references/accessibility-performance.md.',
            m.group(0),
        ))


def check_click_handlers(text, path, findings):
    for m in CLICK_HANDLER_RE.finditer(text):
        findings.append(Finding(
            path, line_of(text, m.start()), "A11Y", "click handler on non-interactive element",
            "A <div>/<span> with onclick and no role/tabindex is invisible to keyboard and "
            "screen-reader users -- use <button>, or add role and tabindex.",
            m.group(0),
        ))


CHECKS = [
    check_gradients, check_pure_black, check_fonts, check_tailwind_reflex,
    check_full_height, check_link_portability, check_copy, check_emoji, check_images,
    check_click_handlers,
]


def iter_scan_files(root: Path):
    if root.is_file():
        if root.suffix.lower() in SCAN_EXTENSIONS:
            yield root
        return
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in SCAN_EXTENSIONS:
            yield path


def main():
    parser = argparse.ArgumentParser(description="Mechanical anti-slop pass for static sites.")
    parser.add_argument("path", nargs="?", default=".", help="File or directory to scan")
    parser.add_argument("--quiet", action="store_true", help="Only print the summary line")
    args = parser.parse_args()

    root = Path(args.path)
    if not root.exists():
        print(f"error: path not found: {root}", file=sys.stderr)
        sys.exit(2)

    all_findings = []
    files_scanned = 0
    for file_path in iter_scan_files(root):
        try:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            print(f"warning: could not read {file_path}: {exc}", file=sys.stderr)
            continue
        files_scanned += 1
        rel = file_path
        scan_text = strip_comments(text)
        for check in CHECKS:
            check(scan_text, rel, all_findings)

    all_findings.sort(key=lambda f: (str(f.path), f.line_no))

    if not args.quiet:
        for finding in all_findings:
            print(finding.render())
            print()

    tier_counts = {}
    for f in all_findings:
        tier_counts[f.tier] = tier_counts.get(f.tier, 0) + 1

    summary = ", ".join(f"{count} {tier}" for tier, count in sorted(tier_counts.items())) or "none"
    print(f"Scanned {files_scanned} file(s). Findings: {summary}.")
    if all_findings:
        print("Review the lines above against references/anti-slop-checklist.md before shipping.")

    sys.exit(1 if all_findings else 0)


if __name__ == "__main__":
    main()
