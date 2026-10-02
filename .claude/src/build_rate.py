#!/usr/bin/env python3
"""Build the standalone Rinse Rate site from the artifact fragment.

Input : rinse-rate.html (the artifact fragment, source of truth)
Output: site/rinse-rate/index.html   (calculator, fonts inlined, no external requests)
        site/rinse-rate/privacy.html (short privacy page)
Images (og.png, apple-touch-icon.png) are made by build_images_rate.py.
Shares the font pipeline with build_site.py (Rinse Quote) and leaves that file untouched.
"""
import base64
import html
import pathlib
import re
import sys

from build_site import APP_FONTS, PRIVACY_FONTS, SKELETON_CSS, font_faces

HERE = pathlib.Path(__file__).resolve().parent
SRC = HERE / 'rinse-rate.html'
OUT = HERE / 'site' / 'rinse-rate'

SITE_URL = 'https://sanjixysti-creator.github.io/rinse-rate/'
TITLE = 'Rinse Rate: Pressure Washing Job Profit Calculator'
DESC = ('Free pressure washing job profit calculator. Enter your price, hours, drive time and costs to see '
        'what the job paid per hour and what to charge for your goal.')
OG_DESC = 'Free pressure washing job profit calculator. See what a job really paid per hour, and what to charge. No signup.'
OG_ALT = ('Rinse Rate, a free pressure washing job profit calculator, next to a sample result: a 300 dollar job that '
          'paid 36.97 dollars an hour, and a price of 358 dollars to reach a 50 dollar an hour goal.')
MAKER = 'Xysti Software'
UPDATED = 'October 2026'

ORANGE = '#C2410C'
BG_LIGHT, BG_DARK = '#F1ECE5', '#17110C'

# Same dash characters the tests look for, written without typing them.
DASHES = ''.join(chr(c) for c in (0x2014, 0x2013, 0x2212))

ARC_D = 'M6 28a14 14 0 0 1 28 0'
NEEDLE_D = 'M20 28L27.5 15.5'

# One place for the mark so the favicon, the touch icon, the link preview and the privacy page agree.
MARK_SVG = (
    '<svg viewBox="0 0 40 40" aria-hidden="true" focusable="false">'
    f'<path class="mk-arc" d="{ARC_D}" fill="none" stroke-width="4.4" stroke-linecap="round"/>'
    f'<path class="mk-needle" d="{NEEDLE_D}" fill="none" stroke-width="3.4" stroke-linecap="round"/>'
    '<circle class="mk-hub" cx="20" cy="28" r="3.8"/></svg>'
)

# The same art on the orange ground (favicon, touch icon, hub tile). Centered on its own bounds.
MARK_ON_ORANGE = (
    '<g transform="translate(2 .4) scale(.9)">'
    f'<path d="{ARC_D}" fill="none" stroke="#fff" stroke-width="4.4" stroke-linecap="round"/>'
    f'<path d="{NEEDLE_D}" fill="none" stroke="#FFD9BF" stroke-width="3.4" stroke-linecap="round"/>'
    '<circle cx="20" cy="28" r="3.8" fill="#fff"/></g>'
)


def favicon_data_uri():
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40">'
        f'<rect width="40" height="40" rx="9" fill="{ORANGE}"/>{MARK_ON_ORANGE}</svg>'
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
            '<meta property="og:site_name" content="Rinse Rate">',
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
                'Rinse Rate needs JavaScript. Turn it on in your browser settings, then reload this page.</p></noscript>')

    return (
        '<!doctype html>\n<html lang="en">\n<head>\n'
        + head_tags(TITLE, DESC, SITE_URL)
        + '\n<style>\n' + SKELETON_CSS + '\n' + font_faces(APP_FONTS) + '\n' + app_css + '\n</style>\n'
        + '</head>\n<body>\n' + noscript + '\n' + body.rstrip() + '\n</body>\n</html>\n'
    )


PRIVACY_CSS = """
:root {
  --bg: #F1ECE5; --surface: #FFFFFF; --ink: #2A1A10; --muted: #65503F; --line: #DCCFC1;
  --accent: #C2410C; --on-accent: #FFFFFF; --accent-ink: #B03A0A;
  --font-display: 'Big Shoulders Display', 'Arial Narrow', 'Helvetica Neue', Arial, sans-serif;
  --font-body: 'Public Sans', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #17110C; --surface: #211812; --ink: #F5EBE1; --muted: #BBA796; --line: #3D3025;
    --accent: #FF9248; --on-accent: #2B1100; --accent-ink: #FF9248; color-scheme: dark;
  }
}
:root[data-theme="dark"] {
  --bg: #17110C; --surface: #211812; --ink: #F5EBE1; --muted: #BBA796; --line: #3D3025;
  --accent: #FF9248; --on-accent: #2B1100; --accent-ink: #FF9248; color-scheme: dark;
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
.brand .mk-arc { stroke: var(--accent); }
.brand .mk-needle { stroke: var(--ink); }
.brand .mk-hub { fill: var(--ink); }
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
    <a class="brand" href="./" aria-label="Rinse Rate home">{MARK_SVG}<span>Rinse Rate</span></a>
    <a class="back" href="./">Back to the calculator</a>
  </div>
  <main class="doc">
    <div>
      <h1>Privacy policy</h1>
      <p class="updated">Rinse Rate, last updated {UPDATED}</p>
    </div>

    <section>
      <h2>The short version</h2>
      <p>Rinse Rate has no accounts, no ads, no analytics and no cookies of its own. The numbers you type into the calculator and the jobs you save stay in your browser, on your own device. They are never sent to us.</p>
    </section>

    <section>
      <h2>What is stored on your device</h2>
      <ul>
        <li>The price, hours, crew size, drive and cost numbers for the job you are working on</li>
        <li>Your usual numbers: mileage rate, machine wear, helper pay, overhead percent, payment fee and your pay per hour goal</li>
        <li>The jobs per week and weeks per year you enter for the monthly estimate</li>
        <li>The jobs you save, including the names you give them</li>
      </ul>
      <p style="margin-top:10px">This lives in your browser's local storage for this site. Clearing your browser data removes it, and a different browser or device starts empty.</p>
    </section>

    <section>
      <h2>What this page does not do</h2>
      <ul>
        <li>No analytics, tracking pixels or advertising</li>
        <li>No outside fonts or scripts. The fonts are built into the page, so loading it does not contact any font service</li>
        <li>No sending of your jobs anywhere. Copying a summary puts text on your clipboard, and what you do with it next is up to you</li>
      </ul>
    </section>

    <section>
      <h2>Hosting</h2>
      <p>Rinse Rate is hosted on GitHub Pages. Like any web host, GitHub may log technical details such as your IP address and browser type when you load the page, under <a href="https://docs.github.com/site-policy/privacy-policies/github-general-privacy-statement">GitHub's privacy statement</a>. We add no tracking of our own on top of that.</p>
    </section>

    <section>
      <h2>Estimates only</h2>
      <p>Rinse Rate does arithmetic on the numbers you give it. It cannot know your real costs, taxes or insurance, so treat the results as a guide, and ask an accountant about anything that matters.</p>
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
        + head_tags('Privacy Policy - Rinse Rate',
                    'How Rinse Rate handles your data: it stays in your browser, on your device.',
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
    problems = []
    for name, text in (('index.html', index), ('privacy.html', privacy)):
        if any(ch in text for ch in DASHES):
            problems.append(f'{name}: dash character found')
        if '@@' in text:
            problems.append(f'{name}: unreplaced placeholder')
        # Nothing may be fetched from another site. Only mailto links and docs links to GitHub are allowed to leave.
        for url in re.findall(r'(?:src|href)="(https?://[^"]*)"', text):
            if not url.startswith(('https://sanjixysti-creator.github.io/', 'https://docs.github.com/')):
                problems.append(f'{name}: outside address {url}')
    if len(re.findall(r'<h1[ >]', index)) != 1:
        problems.append('index.html: expected exactly one h1')
    if problems:
        sys.exit('build failed:\n  ' + '\n  '.join(problems))
    (OUT / 'index.html').write_text(index, encoding='utf-8')
    (OUT / 'privacy.html').write_text(privacy, encoding='utf-8')
    for name in ('index.html', 'privacy.html'):
        p = OUT / name
        text = p.read_text(encoding='utf-8')
        print(f'{name}: {p.stat().st_size / 1024:.1f} KB, dash characters: {sum(text.count(c) for c in DASHES)}')


if __name__ == '__main__':
    main()
