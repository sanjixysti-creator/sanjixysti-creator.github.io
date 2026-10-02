#!/usr/bin/env python3
"""Build the standalone Rinse Mix site from the artifact fragment.

Input : rinse-mix.html (the artifact fragment, source of truth)
Output: site/rinse-mix/index.html   (calculator, fonts inlined, no external requests)
        site/rinse-mix/privacy.html (short privacy page)
Images (og.png, apple-touch-icon.png) are made by build_images_mix.py.
Shares the font pipeline with build_site.py (Rinse Quote) and leaves that file untouched.
"""
import base64
import html
import pathlib
import re
import sys

from build_site import APP_FONTS, PRIVACY_FONTS, SKELETON_CSS, font_faces

HERE = pathlib.Path(__file__).resolve().parent
SRC = HERE / 'rinse-mix.html'
OUT = HERE / 'site' / 'rinse-mix'

SITE_URL = 'https://sanjixysti-creator.github.io/rinse-mix/'
TITLE = 'Rinse Mix: Free Soft Wash Mix Calculator'
DESC = ('Free soft wash mix calculator. Enter your batch size, the strength you want and your '
        'sodium hypochlorite percent to get the SH, water and surfactant to add.')
OG_DESC = 'Free soft wash mix calculator. Get the SH, water and surfactant for any batch size. No signup.'
OG_ALT = ('Rinse Mix, a free soft wash mix calculator, next to a sample result: 12 gallons of sodium hypochlorite '
          'and 37.61 gallons of water for a 50 gallon batch.')
MAKER = 'Xysti Software'
UPDATED = 'September 2026'

TEAL = '#0A7A72'
BG_LIGHT, BG_DARK = '#E6EEEC', '#0A1615'

DROP_D = 'M20 3.5C20 3.5 7.5 17.8 7.5 26a12.5 12.5 0 0 0 25 0C32.5 17.8 20 3.5 20 3.5Z'
WAVE_D = 'M10 26q2.5-3.4 5 0t5 0 5 0 5 0'

# One place for the mark so the favicon, the touch icon, the link preview and the privacy page agree.
MARK_SVG = (
    '<svg viewBox="0 0 40 40" aria-hidden="true" focusable="false">'
    f'<path class="drop" d="{DROP_D}"/>'
    f'<path class="wave" d="{WAVE_D}" fill="none" stroke-width="2.6" stroke-linecap="round"/></svg>'
)


def favicon_data_uri():
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40">'
        f'<rect width="40" height="40" rx="9" fill="{TEAL}"/>'
        '<g transform="translate(4 4) scale(.8)">'
        f'<path d="{DROP_D}" fill="#fff"/>'
        f'<path d="{WAVE_D}" fill="none" stroke="{TEAL}" stroke-width="2.6" stroke-linecap="round"/>'
        '</g></svg>'
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
            '<meta property="og:site_name" content="Rinse Mix">',
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
                'Rinse Mix needs JavaScript. Turn it on in your browser settings, then reload this page.</p></noscript>')

    return (
        '<!doctype html>\n<html lang="en">\n<head>\n'
        + head_tags(TITLE, DESC, SITE_URL)
        + '\n<style>\n' + SKELETON_CSS + '\n' + font_faces(APP_FONTS) + '\n' + app_css + '\n</style>\n'
        + '</head>\n<body>\n' + noscript + '\n' + body.rstrip() + '\n</body>\n</html>\n'
    )


PRIVACY_CSS = """
:root {
  --bg: #E6EEEC; --surface: #FFFFFF; --ink: #0D2422; --muted: #4E6864; --line: #C7D8D5;
  --accent: #0A7A72; --on-accent: #FFFFFF; --accent-ink: #076860;
  --font-display: 'Big Shoulders Display', 'Arial Narrow', 'Helvetica Neue', Arial, sans-serif;
  --font-body: 'Public Sans', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #0A1615; --surface: #112321; --ink: #E3EFED; --muted: #92AAA6; --line: #21403C;
    --accent: #4CC9BC; --on-accent: #032622; --accent-ink: #4CC9BC; color-scheme: dark;
  }
}
:root[data-theme="dark"] {
  --bg: #0A1615; --surface: #112321; --ink: #E3EFED; --muted: #92AAA6; --line: #21403C;
  --accent: #4CC9BC; --on-accent: #032622; --accent-ink: #4CC9BC; color-scheme: dark;
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
.brand .drop { fill: var(--accent); }
.brand .wave { stroke: var(--on-accent); }
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


def build_privacy(support):
    body = f"""
<div class="page">
  <div class="top">
    <a class="brand" href="./" aria-label="Rinse Mix home">{MARK_SVG}<span>Rinse Mix</span></a>
    <a class="back" href="./">Back to the calculator</a>
  </div>
  <main class="doc">
    <div>
      <h1>Privacy policy</h1>
      <p class="updated">Rinse Mix, last updated {UPDATED}</p>
    </div>

    <section>
      <h2>The short version</h2>
      <p>Rinse Mix has no accounts, no ads, no analytics and no cookies of its own. The numbers you type into the calculator and the mixes you save stay in your browser, on your own device. They are never sent to us.</p>
    </section>

    <section>
      <h2>What is stored on your device</h2>
      <ul>
        <li>Your choice of units</li>
        <li>The batch size, strengths and surfactant dose you last entered</li>
        <li>Any prices and injector draw you entered</li>
        <li>The mixes you save, including the names you give them</li>
      </ul>
      <p style="margin-top:10px">This lives in your browser's local storage for this site. Clearing your browser data removes it, and a different browser or device starts empty.</p>
    </section>

    <section>
      <h2>What this page does not do</h2>
      <ul>
        <li>No analytics, tracking pixels or advertising</li>
        <li>No outside fonts or scripts. The fonts are built into the page, so loading it does not contact any font service</li>
        <li>No sending of your mixes anywhere. Copying a mix puts text on your clipboard, and what you do with it next is up to you</li>
      </ul>
    </section>

    <section>
      <h2>Hosting</h2>
      <p>Rinse Mix is hosted on GitHub Pages. Like any web host, GitHub may log technical details such as your IP address and browser type when you load the page, under <a href="https://docs.github.com/site-policy/privacy-policies/github-general-privacy-statement">GitHub's privacy statement</a>. We add no tracking of our own on top of that.</p>
    </section>

    <section>
      <h2>Estimates only</h2>
      <p>Rinse Mix does arithmetic on the numbers you give it. It cannot know how strong your product really is, so follow your product labels and safety data sheets, and test before you spray.</p>
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
        + head_tags('Privacy Policy - Rinse Mix',
                    'How Rinse Mix handles your data: it stays in your browser, on your device.',
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


if __name__ == '__main__':
    main()
