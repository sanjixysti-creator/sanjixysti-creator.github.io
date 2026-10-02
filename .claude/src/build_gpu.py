#!/usr/bin/env python3
"""Build the standalone Used GPU Check site from the artifact fragment.

Input : gpu-check.html (the artifact fragment, source of truth)
Output: site/gpu-check/index.html   (checker, fonts inlined, no external requests)
        site/gpu-check/privacy.html (short privacy page)
Images (og.png, apple-touch-icon.png) are made by build_images_gpu.py.
Shares the font pipeline with build_site.py and leaves that file untouched.
"""
import base64
import html
import pathlib
import re
import sys

from build_site import SKELETON_CSS, font_faces

HERE = pathlib.Path(__file__).resolve().parent
SRC = HERE / 'gpu-check.html'
OUT = HERE / 'site' / 'gpu-check'

SITE_URL = 'https://sanjixysti-creator.github.io/gpu-check/'
TITLE = 'Used GPU Check: Free Risk and Price Checker'
DESC = ('Free used graphics card checker. Answer a few questions about a listing to get a risk score, '
        'a price check and what to do before you pay.')
OG_DESC = 'Free used GPU checker. Get a risk score and a price check for a listing before you pay. No signup.'
OG_ALT = ('Used GPU Check, a free checker for used graphics card listings, next to a sample result: high risk, '
          'a score of 66 out of 100 and a suspiciously low price.')
MAKER = 'Xysti Software'
UPDATED = 'September 2026'

INDIGO = '#4338CA'
BG_LIGHT, BG_DARK = '#E8EAF4', '#0C0E1E'

# Only the faces the page uses.
APP_FONTS = [
    ('Chakra Petch', 'chakra-petch', 700),
    ('Public Sans', 'public-sans', 400),
    ('Public Sans', 'public-sans', 500),
    ('Public Sans', 'public-sans', 600),
    ('Public Sans', 'public-sans', 700),
    ('IBM Plex Mono', 'ibm-plex-mono', 400),
]
PRIVACY_FONTS = [
    ('Chakra Petch', 'chakra-petch', 700),
    ('Public Sans', 'public-sans', 400),
    ('Public Sans', 'public-sans', 600),
    ('Public Sans', 'public-sans', 700),
]

# One place for the mark so the favicon, the touch icon, the link preview and the privacy page agree.
BODY_RECTS = [(4.5, 9, 33, 19, 3.5), (1.5, 8, 3.5, 21, 1.2), (11, 28.5, 17, 3, 0.8)]
FANS = [(16, 18.5), (29, 18.5)]


def mark_shapes(body_fill, fan_stroke, hub_fill):
    """The mark as bare SVG shapes with literal colors (for the favicon, the touch icon and the preview card)."""
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{body_fill}"/>' for x, y, w, h, r in BODY_RECTS]
    for cx, cy in FANS:
        out.append(f'<circle cx="{cx}" cy="{cy}" r="5.2" fill="none" stroke="{fan_stroke}" stroke-width="2"/>')
        out.append(f'<circle cx="{cx}" cy="{cy}" r="1.5" fill="{hub_fill}"/>')
    return ''.join(out)


MARK_SVG = (
    '<svg viewBox="0 0 40 40" aria-hidden="true" focusable="false">'
    + ''.join(f'<rect class="body" x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}"/>' for x, y, w, h, r in BODY_RECTS)
    + ''.join(f'<circle class="fan" cx="{cx}" cy="{cy}" r="5.2"/><circle class="hub" cx="{cx}" cy="{cy}" r="1.5"/>' for cx, cy in FANS)
    + '</svg>'
)


def favicon_data_uri():
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40">'
        f'<rect width="40" height="40" rx="9" fill="{INDIGO}"/>'
        '<g transform="translate(4.2 4) scale(.8)">' + mark_shapes('#fff', INDIGO, INDIGO) + '</g></svg>'
    )
    return 'data:image/svg+xml;base64,' + base64.b64encode(svg.encode()).decode('ascii')


def head_tags(title, desc, url, og=True):
    t, d = html.escape(title, quote=True), html.escape(desc, quote=True)
    tags = [
        '<meta charset="utf-8">',
        # No viewport-fit=cover here: on a notched iPhone in landscape the page stays inside the safe area.
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        f'<title>{t}</title>',
        f'<meta name="description" content="{d}">',
        f'<meta name="theme-color" content="{BG_LIGHT}" media="(prefers-color-scheme: light)">',
        f'<meta name="theme-color" content="{BG_DARK}" media="(prefers-color-scheme: dark)">',
        f'<link rel="canonical" href="{url}">',
        f'<link rel="icon" href="{favicon_data_uri()}">',
        '<link rel="apple-touch-icon" href="apple-touch-icon.png">',
    ]
    if og:
        od = html.escape(OG_DESC, quote=True)
        oa = html.escape(OG_ALT, quote=True)
        tags += [
            '<meta property="og:type" content="website">',
            '<meta property="og:site_name" content="Used GPU Check">',
            f'<meta property="og:title" content="{t}">',
            f'<meta property="og:description" content="{od}">',
            f'<meta property="og:url" content="{url}">',
            f'<meta property="og:image" content="{SITE_URL}og.png">',
            '<meta property="og:image:type" content="image/png">',
            '<meta property="og:image:width" content="1200">',
            '<meta property="og:image:height" content="630">',
            f'<meta property="og:image:alt" content="{oa}">',
            '<meta name="twitter:card" content="summary_large_image">',
            f'<meta name="twitter:title" content="{t}">',
            f'<meta name="twitter:description" content="{od}">',
            f'<meta name="twitter:image" content="{SITE_URL}og.png">',
            f'<meta name="twitter:image:alt" content="{oa}">',
        ]
    return '\n'.join(tags)


def build_index():
    src = SRC.read_text(encoding='utf-8')
    cut = src.index('<div class="app">')
    head, body = src[:cut], src[cut:]

    # The fragment head must hold only the title, the font links and one style block.
    m = re.search(r'<style>(.*?)</style>', head, re.S)
    if not m:
        sys.exit('no <style> block in fragment head')
    app_css = m.group(1).strip('\n')
    leftover = re.sub(r'<style>.*?</style>', '', head, flags=re.S)
    leftover = re.sub(r'<title>.*?</title>', '', leftover, flags=re.S)
    leftover = re.sub(r'<link [^>]*>', '', leftover)
    if leftover.strip():
        sys.exit('unexpected content in fragment head: ' + repr(leftover.strip()[:120]))

    # The fragment asks Google Fonts for these faces, and the build embeds the same ones.
    asked = set(re.findall(r'family=([A-Za-z+]+)', head))
    have = {f[0].replace(' ', '+') for f in APP_FONTS}
    if asked != have:
        sys.exit(f'font families differ: page asks for {sorted(asked)}, build embeds {sorted(have)}')

    # Support address becomes a real mailto link on this standalone page (fillSupport still sets its text).
    sup = re.search(r"var SUPPORT = '([^']+)';", body)
    if not sup:
        sys.exit('SUPPORT not found')
    support = sup.group(1)
    n = body.count('<span class="mail"></span>')
    if n != 1:
        sys.exit(f'expected 1 mail span, found {n}')
    body = body.replace('<span class="mail"></span>', f'<a class="mail" href="mailto:{support}"></a>')

    # Footer: maker line and privacy link.
    foot_old = '<button type="button" class="linkish mail-copy">Copy</button></p>\n      </div>\n    </div>\n  </div>\n</div>'
    if body.count(foot_old) != 1:
        sys.exit('footer anchor not found exactly once')
    foot_new = ('<button type="button" class="linkish mail-copy">Copy</button></p>\n'
                f'        <p>Made by {html.escape(MAKER)}. <a href="privacy.html">Privacy</a></p>\n      </div>\n    </div>\n  </div>\n</div>')
    body = body.replace(foot_old, foot_new)

    noscript = ('<noscript><p style="padding:16px;font:16px/1.45 system-ui,sans-serif">'
                'Used GPU Check needs JavaScript. Turn it on in your browser settings, then reload this page.</p></noscript>')

    return (
        '<!doctype html>\n<html lang="en">\n<head>\n'
        + head_tags(TITLE, DESC, SITE_URL)
        + '\n<style>\n' + SKELETON_CSS + '\n' + font_faces(APP_FONTS) + '\n' + app_css + '\n</style>\n'
        + '</head>\n<body>\n' + noscript + '\n' + body.rstrip() + '\n</body>\n</html>\n'
    )


PRIVACY_CSS = """
:root {
  --bg: #E8EAF4; --surface: #FFFFFF; --ink: #14162B; --muted: #565A78; --line: #CFD2E4;
  --accent: #4338CA; --on-accent: #FFFFFF; --accent-ink: #4338CA;
  --font-display: 'Chakra Petch', 'Arial Narrow', 'Helvetica Neue', Arial, sans-serif;
  --font-body: 'Public Sans', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #0C0E1E; --surface: #141731; --ink: #E6E8F7; --muted: #9A9EC4; --line: #262A4F;
    --accent: #8B9CFF; --on-accent: #0B0D24; --accent-ink: #8B9CFF; color-scheme: dark;
  }
}
:root[data-theme="dark"] {
  --bg: #0C0E1E; --surface: #141731; --ink: #E6E8F7; --muted: #9A9EC4; --line: #262A4F;
  --accent: #8B9CFF; --on-accent: #0B0D24; --accent-ink: #8B9CFF; color-scheme: dark;
}
*, *::before, *::after { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; text-size-adjust: 100%; }
body {
  background: var(--bg); color: var(--ink);
  font: 400 16px/1.6 var(--font-body);
  padding-inline: 16px; padding-block: 20px 56px;
  -webkit-font-smoothing: antialiased;
}
h1, h2, p, ul { margin: 0; }
a { color: var(--accent-ink); text-underline-offset: 3px; }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.page { max-width: 680px; margin-inline: auto; display: grid; gap: 22px; min-width: 0; }
.top { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.brand { display: inline-flex; align-items: center; gap: 10px; color: var(--ink); text-decoration: none; }
.brand svg { width: 38px; height: 38px; flex: none; }
.brand .body { fill: var(--accent); }
.brand .fan { fill: none; stroke: var(--on-accent); stroke-width: 2; }
.brand .hub { fill: var(--on-accent); }
.brand span { font: 700 22px/1.05 var(--font-display); letter-spacing: 0.04em; text-transform: uppercase; }
.back { font-size: 14px; font-weight: 600; }
.doc { background: var(--surface); border: 1px solid var(--line); border-radius: 12px; padding: 22px 18px; display: grid; gap: 22px; min-width: 0; }
h1 { font: 700 30px/1.1 var(--font-display); letter-spacing: 0.04em; text-transform: uppercase; text-wrap: balance; }
.updated { color: var(--muted); font-size: 14px; margin-top: 6px; }
h2 { font: 700 18px/1.2 var(--font-display); letter-spacing: 0.07em; text-transform: uppercase; text-wrap: balance; margin-bottom: 6px; }
section { min-width: 0; }
p, li { font-size: 16px; overflow-wrap: anywhere; }
ul { padding-left: 20px; display: grid; gap: 4px; margin-top: 6px; }
"""


def build_privacy(support):
    body = f"""
<div class="page">
  <div class="top">
    <a class="brand" href="./" aria-label="Used GPU Check home">{MARK_SVG}<span>Used GPU Check</span></a>
    <a class="back" href="./">Back to the checker</a>
  </div>
  <main class="doc">
    <div>
      <h1>Privacy policy</h1>
      <p class="updated">Used GPU Check, last updated {UPDATED}</p>
    </div>

    <section>
      <h2>The short version</h2>
      <p>Used GPU Check has no accounts, no ads, no analytics and no cookies of its own. What you type into the checker and the listings you save stay in your browser, on your own device. They are never sent to us.</p>
    </section>

    <section>
      <h2>What is stored on your device</h2>
      <ul>
        <li>The card name and the prices you last entered</li>
        <li>Your answers to the questions</li>
        <li>The listings you save, including the names you give them</li>
        <li>How you sorted your saved listings</li>
      </ul>
      <p style="margin-top:10px">This lives in your browser's local storage for this site. Clearing your browser data removes it, and a different browser or device starts empty.</p>
    </section>

    <section>
      <h2>What this page does not do</h2>
      <ul>
        <li>No analytics, tracking pixels or advertising</li>
        <li>No outside fonts or scripts. The fonts are built into the page, so loading it does not contact any font service</li>
        <li>No sending of your answers anywhere. Copying a summary or a message puts text on your clipboard, and what you do with it next is up to you</li>
      </ul>
    </section>

    <section>
      <h2>Links to other sites</h2>
      <p>The checker links to marketplaces, search pages and the sources it relies on. Those links only open a search or a page in a new tab. Used GPU Check does not read what you find there, and once you follow a link the other site's own privacy policy applies.</p>
    </section>

    <section>
      <h2>Hosting</h2>
      <p>Used GPU Check is hosted on GitHub Pages. Like any web host, GitHub may log technical details such as your IP address and browser type when you load the page, under <a href="https://docs.github.com/site-policy/privacy-policies/github-general-privacy-statement">GitHub's privacy statement</a>. We add no tracking of our own on top of that.</p>
    </section>

    <section>
      <h2>A checklist, not a guarantee</h2>
      <p>Used GPU Check turns your answers into a score using a fixed list of warning signs. It cannot see the listing or the seller, so it cannot prove that a listing is honest or that it is a scam. Test the card and pay in a way that protects you.</p>
    </section>

    <section>
      <h2>Changes</h2>
      <p>If this policy changes, the date at the top will change with it.</p>
    </section>

    <section>
      <h2>Contact</h2>
      <p>Questions about this policy or your data? Email <a href="mailto:{support}">{support}</a>.</p>
    </section>
  </main>
</div>
"""
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n'
        + head_tags('Privacy Policy - Used GPU Check',
                    'How Used GPU Check handles your data: it stays in your browser, on your device.',
                    SITE_URL + 'privacy.html', og=False)
        + '\n<style>\n' + SKELETON_CSS + '\n' + font_faces(PRIVACY_FONTS) + '\n' + PRIVACY_CSS + '</style>\n'
        + '</head>\n<body>' + body + '</body>\n</html>\n'
    )


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    if not 60 < len(DESC) <= 160:
        sys.exit(f'description length {len(DESC)} is outside 61-160')
    index = build_index()
    support = re.search(r"var SUPPORT = '([^']+)';", index).group(1)
    privacy = build_privacy(support)
    (OUT / 'index.html').write_text(index, encoding='utf-8')
    (OUT / 'privacy.html').write_text(privacy, encoding='utf-8')
    for name in ('index.html', 'privacy.html'):
        p = OUT / name
        text = p.read_text(encoding='utf-8')
        print(f'{name}: {p.stat().st_size / 1024:.1f} KB, em dashes: {text.count(chr(0x2014))}')
    print('description length', len(DESC))


if __name__ == '__main__':
    main()
