#!/usr/bin/env python3
"""Build the standalone Drive Rate site from the fragment.

Input : drive-rate.html (the fragment, source of truth)
Output: site/drive-rate/index.html   (calculator, fonts inlined, no external requests)
        site/drive-rate/privacy.html (short privacy page)
Images (og.png, apple-touch-icon.png) are made by build_images_drive.py.
Shares the font pipeline with build_site.py (Rinse Quote) and leaves that file untouched.
"""
import base64
import html
import pathlib
import re
import sys

from build_site import APP_FONTS, PRIVACY_FONTS, SKELETON_CSS, font_faces

HERE = pathlib.Path(__file__).resolve().parent
SRC = HERE / 'drive-rate.html'
OUT = HERE / 'site' / 'drive-rate'

SITE_URL = 'https://sanjixysti-creator.github.io/drive-rate/'
TITLE = 'Drive Rate: Is This Delivery Offer Worth It? Free Calculator'
DESC = ('Free offer checker for DoorDash, Uber Eats, Instacart and rideshare drivers. See net pay per hour after '
        'car costs, get a clear verdict, and log your day.')
OG_DESC = ('Is this delivery offer worth it? See what it pays per hour after your car costs, with a clear verdict '
           'and a day log. Free, no signup.')
# The numbers in this text are the app's own first-visit example (checked by drive_test.py).
OG_ALT = ('Drive Rate, a free delivery and rideshare offer calculator, next to a sample result: a 6.50 dollar offer '
          'that nets 8.88 dollars an hour after car costs, with the verdict Pass and 12.25 dollars needed to meet the goals.')
MAKER = 'Xysti Software'
UPDATED = 'October 2026'

RED = '#BE123C'
BG_LIGHT, BG_DARK = '#ECEEF1', '#0B0C0F'

# Outside addresses a built page may link to. Everything else is refused.
ALLOWED_LINKS = ('https://sanjixysti-creator.github.io/', 'https://docs.github.com/', 'https://www.irs.gov/')

# Same dash characters the tests look for, written without typing them.
DASHES = ''.join(chr(c) for c in (0x2014, 0x2013, 0x2212))

EDGE_D = 'M8.5 35L16.5 5M31.5 35L23.5 5'
DASH_D = 'M20 30.5v4.5M20 21.5v5M20 14.5v3.5M20 8.5v2.5'

# One place for the mark so the favicon, the touch icon, the link preview and the privacy page agree.
MARK_SVG = (
    '<svg viewBox="0 0 40 40" aria-hidden="true" focusable="false">'
    f'<path class="mk-edge" d="{EDGE_D}" fill="none" stroke-width="4" stroke-linecap="round"/>'
    f'<path class="mk-line" d="{DASH_D}" fill="none" stroke-width="3.2" stroke-linecap="round"/></svg>'
)

# The same art on the red ground (favicon, touch icon, hub tile). Its box is centred on (20, 20) already.
MARK_ON_RED = (
    '<g transform="translate(2 2) scale(.9)">'
    f'<path d="{EDGE_D}" fill="none" stroke="#fff" stroke-width="4" stroke-linecap="round"/>'
    f'<path d="{DASH_D}" fill="none" stroke="#FFD1DC" stroke-width="3.2" stroke-linecap="round"/></g>'
)


def favicon_data_uri():
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40">'
        f'<rect width="40" height="40" rx="9" fill="{RED}"/>{MARK_ON_RED}</svg>'
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
            '<meta property="og:site_name" content="Drive Rate">',
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
    if body.count('<script>') != 1 or body.count('</script>') != 1:
        sys.exit('expected exactly one script block')

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
                'Drive Rate needs JavaScript. Turn it on in your browser settings, then reload this page.</p></noscript>')

    return (
        '<!doctype html>\n<html lang="en">\n<head>\n'
        + head_tags(TITLE, DESC, SITE_URL)
        + '\n<style>\n' + SKELETON_CSS + '\n' + font_faces(APP_FONTS) + '\n' + app_css + '\n</style>\n'
        + '</head>\n<body>\n' + noscript + '\n' + body.rstrip() + '\n</body>\n</html>\n'
    )


PRIVACY_CSS = """
:root {
  --bg: #ECEEF1; --surface: #FFFFFF; --ink: #16181D; --muted: #545968; --line: #D3D6DE;
  --accent: #BE123C; --on-accent: #FFFFFF; --accent-ink: #A50F34;
  --font-display: 'Big Shoulders Display', 'Arial Narrow', 'Helvetica Neue', Arial, sans-serif;
  --font-body: 'Public Sans', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #0B0C0F; --surface: #15171C; --ink: #EDEEF2; --muted: #A4A8B5; --line: #2A2D36;
    --accent: #FF7A95; --on-accent: #2A0610; --accent-ink: #FF8FA6; color-scheme: dark;
  }
}
:root[data-theme="dark"] {
  --bg: #0B0C0F; --surface: #15171C; --ink: #EDEEF2; --muted: #A4A8B5; --line: #2A2D36;
  --accent: #FF7A95; --on-accent: #2A0610; --accent-ink: #FF8FA6; color-scheme: dark;
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
.brand .mk-edge { stroke: var(--ink); }
.brand .mk-line { stroke: var(--accent); }
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
    <a class="brand" href="./" aria-label="Drive Rate home">{MARK_SVG}<span>Drive Rate</span></a>
    <a class="back" href="./">Back to the calculator</a>
  </div>
  <main class="doc">
    <div>
      <h1>Privacy policy</h1>
      <p class="updated">Drive Rate, last updated {UPDATED}</p>
    </div>

    <section>
      <h2>The short version</h2>
      <p>Drive Rate has no accounts, no ads, no analytics and no cookies of its own. The offers you check, your car and goal numbers, your daily log and your saved days stay in your browser, on your own device. They are never sent to us or to anyone else. Drive Rate does not ask for your location and does not connect to any delivery or rideshare account.</p>
    </section>

    <section>
      <h2>What is stored on your device</h2>
      <ul>
        <li>The offer you are checking: pay, tip, miles, minutes, waiting time, the trip back and the app you pick</li>
        <li>Your car numbers: fuel prices, mileage, maintenance, depreciation and other costs per mile, or the cost per mile you type in</li>
        <li>Your goals: the lowest net pay per hour, the lowest gross pay per mile and your tax set-aside percentage</li>
        <li>Today's log: the offers you log, with their pay, miles, minutes, app and any note you write, and the hours and miles you type over the totals</li>
        <li>Your saved days: the date, number of offers, gross pay, miles, hours and net of each day, for up to 60 days</li>
      </ul>
      <p style="margin-top:10px">This lives in your browser's local storage for this site. Clearing your browser data removes it, and a different browser or device starts empty. If your browser blocks storage, Drive Rate still works, but nothing is kept after you close the page.</p>
    </section>

    <section>
      <h2>What this page does not do</h2>
      <ul>
        <li>No analytics, tracking pixels or advertising</li>
        <li>No outside fonts or scripts. The fonts are built into the page, so loading it does not contact any font service</li>
        <li>No lookups while you use it. The IRS mileage rate shown on the page is written into the page, so it does not fetch anything and it can go out of date until the page is updated</li>
        <li>No sending of your offers or your log anywhere. Copying a summary puts text on your clipboard, and what you do with it next is up to you</li>
      </ul>
      <p style="margin-top:10px">A few links lead to irs.gov. Those pages open only when you tap a link, and then the IRS site sees your visit under its own policies.</p>
    </section>

    <section>
      <h2>Hosting</h2>
      <p>Drive Rate is hosted on GitHub Pages. Like any web host, GitHub may log technical details such as your IP address and browser type when you load the page, under <a href="https://docs.github.com/site-policy/privacy-policies/github-general-privacy-statement">GitHub's privacy statement</a>. We add no tracking of our own on top of that.</p>
    </section>

    <section>
      <h2>Estimates only</h2>
      <p>Drive Rate does arithmetic on the numbers you give it. It cannot know your real costs, your taxes or your insurance, so treat the results as a guide. It is not tax or financial advice, so ask a tax professional about anything that matters. Drive Rate is not affiliated with or endorsed by any delivery or rideshare company, and their names belong to their owners.</p>
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
        + head_tags('Privacy Policy - Drive Rate',
                    'How Drive Rate handles your data: it stays in your browser, on your device.',
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
        # Nothing may be fetched from another site. Only mailto links and a few reference links are allowed to leave.
        for url in re.findall(r'(?:src|href)="(https?://[^"]*)"', text):
            if not url.startswith(ALLOWED_LINKS):
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
    print('title length', len(TITLE), 'description length', len(DESC), 'og description length', len(OG_DESC))


if __name__ == '__main__':
    main()
