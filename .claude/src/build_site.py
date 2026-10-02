#!/usr/bin/env python3
"""Build the standalone Rinse Quote site from the artifact fragment.

Input : rinse-quote.html (the artifact fragment, source of truth)
Output: site/rinse-quote/index.html   (calculator, fonts inlined, no external requests)
        site/rinse-quote/privacy.html (short privacy page)
Images (og.png, apple-touch-icon.png) are made by build_images.py.
"""
import base64
import html
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
SRC = HERE / 'rinse-quote.html'
FONTS = HERE / 'fonts_build' / 'node_modules' / '@fontsource'
CACHE = HERE / 'fonts_build' / 'subset'
OUT = HERE / 'site' / 'rinse-quote'

SITE_URL = 'https://sanjixysti-creator.github.io/rinse-quote/'
TITLE = 'Rinse Quote: Free Pressure Washing Quote Calculator'
DESC = ('Price a pressure washing job before you leave the driveway. Driveways, house washes, '
        'decks, fences and roofs by the square foot, with extras, tax and deposit. Free, no signup.')
OG_DESC = 'Price a pressure washing job before you leave the driveway. Free quote calculator, no signup.'
OG_ALT = 'Rinse Quote, a free pressure washing quote calculator, next to a sample quote ticket totaling $877.50.'
MAKER = 'Xysti Software'
UPDATED = 'September 2026'

# Latin subset: ASCII, Latin-1 (covers the degree sign and the multiply sign), curly quotes, dashes, bullet, ellipsis, minus.
UNICODES = 'U+0020-007E,U+00A0-00FF,U+2013,U+2018-201D,U+2022,U+2026,U+2212'

# (css family, fontsource package, weight)
APP_FONTS = [
    ('Big Shoulders Display', 'big-shoulders-display', 700),
    ('Big Shoulders Display', 'big-shoulders-display', 800),
    ('Public Sans', 'public-sans', 400),
    ('Public Sans', 'public-sans', 500),
    ('Public Sans', 'public-sans', 600),
    ('Public Sans', 'public-sans', 700),
    ('IBM Plex Mono', 'ibm-plex-mono', 400),
    ('IBM Plex Mono', 'ibm-plex-mono', 500),
]
# The privacy page only needs a few faces.
PRIVACY_FONTS = [
    ('Big Shoulders Display', 'big-shoulders-display', 800),
    ('Public Sans', 'public-sans', 400),
    ('Public Sans', 'public-sans', 600),
    ('Public Sans', 'public-sans', 700),
]

# Same reset the artifact publish step wraps around the fragment, so the page behaves exactly as tested.
SKELETON_CSS = (
    ':root{color-scheme:light;padding-block:env(safe-area-inset-top,0px) env(safe-area-inset-bottom,0px)}'
    'body{margin:0;font:14px system-ui,sans-serif;background:#fafafa}'
    'img{max-width:100%}'
    '[hidden]{display:none!important}'
)


def subset(package, weight):
    """Return subsetted woff2 bytes for one face (cached)."""
    src = FONTS / package / 'files' / f'{package}-latin-{weight}-normal.woff2'
    if not src.exists():
        sys.exit(f'missing font file: {src}')
    CACHE.mkdir(parents=True, exist_ok=True)
    out = CACHE / f'{package}-{weight}.woff2'
    if not out.exists() or out.stat().st_mtime < src.stat().st_mtime:
        subprocess.run(
            ['pyftsubset', str(src), f'--unicodes={UNICODES}', '--flavor=woff2',
             "--layout-features=*", f'--output-file={out}'],
            check=True,
        )
    return out.read_bytes()


def font_faces(spec):
    css = []
    for family, package, weight in spec:
        b64 = base64.b64encode(subset(package, weight)).decode('ascii')
        css.append(
            f"@font-face{{font-family:'{family}';font-style:normal;font-weight:{weight};font-display:swap;"
            f"src:url(data:font/woff2;base64,{b64}) format('woff2')}}"
        )
    return '\n'.join(css)


def favicon_data_uri():
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40">'
        '<rect width="40" height="40" rx="9" fill="#0B78A6"/>'
        '<g transform="translate(4 4) scale(.8)">'
        '<rect x="2" y="15" width="13" height="10" rx="2.5" fill="#fff"/>'
        '<rect x="13" y="17.5" width="5" height="5" rx="1" fill="#fff"/>'
        '<g fill="none" stroke="#BDE7F7" stroke-width="2.6" stroke-linecap="round">'
        '<path d="M22 20 L37 9"/><path d="M22 20 L38 14.5"/><path d="M22 20 L38.5 20"/>'
        '<path d="M22 20 L38 25.5"/><path d="M22 20 L37 31"/></g></g></svg>'
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
        '<meta name="theme-color" content="#E8EDEF" media="(prefers-color-scheme: light)">',
        '<meta name="theme-color" content="#0B161B" media="(prefers-color-scheme: dark)">',
        f'<link rel="canonical" href="{url}">',
        f'<link rel="icon" href="{favicon_data_uri()}">',
        '<link rel="apple-touch-icon" href="apple-touch-icon.png">',
    ]
    if og:
        od = html.escape(OG_DESC, quote=True)
        oa = html.escape(OG_ALT, quote=True)
        tags += [
            '<meta property="og:type" content="website">',
            '<meta property="og:site_name" content="Rinse Quote">',
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

    # The fragment head must hold only the title, the three font links and one style block.
    m = re.search(r'<style>(.*?)</style>', head, re.S)
    if not m:
        sys.exit('no <style> block in fragment head')
    app_css = m.group(1).strip('\n')
    leftover = re.sub(r'<style>.*?</style>', '', head, flags=re.S)
    leftover = re.sub(r'<title>.*?</title>', '', leftover, flags=re.S)
    leftover = re.sub(r'<link [^>]*>', '', leftover)
    if leftover.strip():
        sys.exit('unexpected content in fragment head: ' + repr(leftover.strip()[:120]))

    # Support address becomes a real mailto link on this standalone page (fillSupport still sets its text).
    sup = re.search(r"var SUPPORT = '([^']+)';", body)
    if not sup:
        sys.exit('SUPPORT not found')
    support = sup.group(1)
    n = body.count('<span class="mail"></span>')
    if n != 2:
        sys.exit(f'expected 2 mail spans, found {n}')
    body = body.replace('<span class="mail"></span>', f'<a class="mail" href="mailto:{support}"></a>')

    # Footer: maker line and privacy link.
    foot_old = ('<button type="button" class="linkish mail-copy">Copy</button></p>\n      </div>\n    </div>\n\n'
                '    <aside class="aside"')
    if body.count(foot_old) != 1:
        sys.exit('footer anchor not found exactly once')
    foot_new = ('<button type="button" class="linkish mail-copy">Copy</button></p>\n'
                f'        <p>Made by {html.escape(MAKER)}. <a href="privacy.html">Privacy</a></p>\n      </div>\n    </div>\n\n'
                '    <aside class="aside"')
    body = body.replace(foot_old, foot_new)

    extra_css = (
        '.foot a { color: var(--ink); font-weight: 600; text-underline-offset: 3px; }\n'
        '.foot a:hover { color: var(--accent); }\n'
    )

    noscript = ('<noscript><p style="padding:16px;font:16px/1.45 system-ui,sans-serif">'
                'Rinse Quote needs JavaScript. Turn it on in your browser settings, then reload this page.</p></noscript>')

    doc = (
        '<!doctype html>\n<html lang="en">\n<head>\n'
        + head_tags(TITLE, DESC, SITE_URL)
        + '\n<style>\n' + SKELETON_CSS + '\n' + font_faces(APP_FONTS) + '\n' + app_css + '\n' + extra_css + '</style>\n'
        + '</head>\n<body>\n' + noscript + '\n' + body.rstrip() + '\n</body>\n</html>\n'
    )
    return doc


PRIVACY_CSS = """
:root {
  --bg: #E8EDEF; --surface: #FFFFFF; --ink: #0E2029; --muted: #536970; --line: #CBD6DA;
  --accent: #0B78A6; --accent-ink: #086088;
  --font-display: 'Big Shoulders Display', 'Arial Narrow', 'Helvetica Neue', Arial, sans-serif;
  --font-body: 'Public Sans', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #0B161B; --surface: #12232A; --ink: #E5EEF1; --muted: #93A8B0; --line: #23404A;
    --accent: #55C1E7; --accent-ink: #55C1E7; color-scheme: dark;
  }
}
:root[data-theme="dark"] {
  --bg: #0B161B; --surface: #12232A; --ink: #E5EEF1; --muted: #93A8B0; --line: #23404A;
  --accent: #55C1E7; --accent-ink: #55C1E7; color-scheme: dark;
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
.brand svg { width: 34px; height: 34px; flex: none; }
.brand .spray { stroke: var(--accent); }
.brand span { font: 800 26px/1 var(--font-display); letter-spacing: 0.02em; text-transform: uppercase; }
.back { font-size: 14px; font-weight: 600; }
.doc { background: var(--surface); border: 1px solid var(--line); border-radius: 12px; padding: 22px 18px; display: grid; gap: 22px; min-width: 0; }
h1 { font: 800 34px/1.05 var(--font-display); letter-spacing: 0.03em; text-transform: uppercase; text-wrap: balance; }
.updated { color: var(--muted); font-size: 14px; margin-top: 6px; }
h2 { font: 700 20px/1.15 var(--font-display); letter-spacing: 0.06em; text-transform: uppercase; text-wrap: balance; margin-bottom: 6px; }
section { min-width: 0; }
p, li { font-size: 16px; overflow-wrap: anywhere; }
ul { padding-left: 20px; display: grid; gap: 4px; margin-top: 6px; }
"""

MARK_SVG = (
    '<svg viewBox="0 0 40 40" aria-hidden="true" focusable="false">'
    '<rect x="2" y="15" width="13" height="10" rx="2.5" fill="currentColor"/>'
    '<rect x="13" y="17.5" width="5" height="5" rx="1" fill="currentColor"/>'
    '<g class="spray" fill="none" stroke-width="2.6" stroke-linecap="round">'
    '<path d="M22 20 L37 9"/><path d="M22 20 L38 14.5"/><path d="M22 20 L38.5 20"/>'
    '<path d="M22 20 L38 25.5"/><path d="M22 20 L37 31"/></g></svg>'
)


def build_privacy(support):
    body = f"""
<div class="page">
  <div class="top">
    <a class="brand" href="./" aria-label="Rinse Quote home">{MARK_SVG}<span>Rinse Quote</span></a>
    <a class="back" href="./">Back to the calculator</a>
  </div>
  <main class="doc">
    <div>
      <h1>Privacy policy</h1>
      <p class="updated">Rinse Quote, last updated {UPDATED}</p>
    </div>

    <section>
      <h2>The short version</h2>
      <p>Rinse Quote has no accounts, no ads, no analytics and no cookies of its own. The rates, quotes and customer details you type into the calculator stay in your browser, on your own device. They are never sent to us.</p>
    </section>

    <section>
      <h2>What is stored on your device</h2>
      <ul>
        <li>Your rates, tax, deposit and business details</li>
        <li>The quote you are working on</li>
        <li>With Pro: the quotes you save, including any customer names and addresses you typed, and their status</li>
        <li>Whether Pro is unlocked on this device</li>
      </ul>
      <p style="margin-top:10px">This lives in your browser's local storage for this site. Clearing your browser data removes it, and a different browser or device starts empty. The Backup button in Pro copies your saved quotes as text so you can keep a copy wherever you like. We never see that text.</p>
    </section>

    <section>
      <h2>What this page does not do</h2>
      <ul>
        <li>No analytics, tracking pixels or advertising</li>
        <li>No outside fonts or scripts. The fonts are built into the page, so loading it does not contact any font service</li>
        <li>No sending of your quotes anywhere. Copying a quote puts text on your clipboard, and what you do with it next is up to you</li>
      </ul>
    </section>

    <section>
      <h2>Hosting</h2>
      <p>Rinse Quote is hosted on GitHub Pages. Like any web host, GitHub may log technical details such as your IP address and browser type when you load the page, under <a href="https://docs.github.com/site-policy/privacy-policies/github-general-privacy-statement">GitHub's privacy statement</a>. We add no tracking of our own on top of that.</p>
    </section>

    <section>
      <h2>Pro and payments</h2>
      <p>Pro is a one-time purchase sold through a Stripe payment link. Stripe collects and processes your payment details on its own pages, and we never see your card number. Stripe gives us the details of the purchase, such as your email address and what you bought. We use them to deliver your Pro code and to answer support emails. Stripe's handling of your data is covered by <a href="https://stripe.com/privacy">Stripe's privacy policy</a>.</p>
      <p style="margin-top:10px">Your Pro code is checked inside the page, on your device. No server is asked whether it is valid.</p>
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
    doc = (
        '<!doctype html>\n<html lang="en">\n<head>\n'
        + head_tags('Privacy Policy - Rinse Quote',
                    'How Rinse Quote handles your data: it stays in your browser, on your device.',
                    SITE_URL + 'privacy.html', og=False)
        + '\n<style>\n' + SKELETON_CSS + '\n' + font_faces(PRIVACY_FONTS) + '\n' + PRIVACY_CSS + '</style>\n'
        + '</head>\n<body>' + body + '</body>\n</html>\n'
    )
    return doc


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    index = build_index()
    support = re.search(r"var SUPPORT = '([^']+)';", index).group(1)
    privacy = build_privacy(support)
    (OUT / 'index.html').write_text(index, encoding='utf-8')
    (OUT / 'privacy.html').write_text(privacy, encoding='utf-8')
    for name in ('index.html', 'privacy.html'):
        p = OUT / name
        text = p.read_text(encoding='utf-8')
        print(f'{name}: {p.stat().st_size / 1024:.1f} KB, em dashes: {text.count(chr(0x2014))}')


if __name__ == '__main__':
    main()
