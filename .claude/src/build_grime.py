#!/usr/bin/env python3
"""Build the standalone Grime Time site from the fragment.

Input : grime-time.html (the fragment, source of truth)
Output: site/grime-time/index.html   (the game, fonts inlined, no external requests)
        site/grime-time/privacy.html (short privacy page)
Images (og.png, apple-touch-icon.png) are made by build_images_grime.py.
Shares the font pipeline with build_site.py and leaves that file untouched.
"""
import base64
import html
import pathlib
import re
import sys

from build_site import APP_FONTS, PRIVACY_FONTS, SKELETON_CSS, font_faces

HERE = pathlib.Path(__file__).resolve().parent
SRC = HERE / 'grime-time.html'
OUT = HERE / 'site' / 'grime-time'
# The published folder holds these four files and nothing else (the two images come from build_images_grime.py).
FOUR_FILES = ('apple-touch-icon.png', 'index.html', 'og.png', 'privacy.html')

SITE_URL = 'https://sanjixysti-creator.github.io/grime-time/'
TITLE = 'Grime Time: Free Pressure Washing Game, Idle and Satisfying'
DESC = ('Free pressure washing game for your browser. Blast layers of grime off driveways, decks and cars, '
        'earn cash, upgrade your rig and hire a crew.')
OG_DESC = 'A free pressure washing game. Spray the grime away, upgrade your rig and build a crew. No ads, no sign up.'
OG_ALT = ('Grime Time, a free pressure washing game. A screenshot of the Garden Patio job about half washed: clean pavers on the left, '
          'olive grime and a few green moss patches on the right, and a wand blasting a white spray with sparkles along the edge. '
          'Beside it: Blast the grime. Build the business.')
MAKER = 'Xysti Software'
UPDATED = 'October 2026'

# Outside addresses a built page may mention. Everything else is refused. The svg namespace name is an identifier, never fetched.
ALLOWED_LINKS = ('https://sanjixysti-creator.github.io/', 'https://docs.github.com/')
ALLOWED_NAMESPACE = 'http://www.w3.org/2000/svg'
# Calls the page must never contain (no network, no cookies, no browser dialogs).
FORBIDDEN_CALLS = (r'\bfetch\(', r'XMLHttpRequest', r'sendBeacon', r'WebSocket', r'EventSource', r'importScripts', r'document\.cookie',
                   r'\balert\(', r'\bconfirm\(', r'\bprompt\(')

BRAND = '#A21CAF'
BG_LIGHT, BG_DARK = '#F5F1F9', '#120A1D'

# Same dash characters the tests look for, written without typing them.
DASHES = ''.join(chr(c) for c in (0x2014, 0x2013, 0x2212))

FAN_D = 'M20.5 20.5L38 13.5A19 19 0 0 0 27 2.5Z'
WAND_A = 'M5 35L15.5 24.5'
WAND_B = 'M14 26L19 21'

# One place for the mark so the favicon, the touch icon, the link preview and the privacy page agree.
MARK_SVG = (
    '<svg viewBox="0 0 40 40" aria-hidden="true" focusable="false">'
    f'<path class="mk-fan" d="{FAN_D}"/>'
    f'<path class="mk-wand" d="{WAND_A}" fill="none" stroke-width="4.6" stroke-linecap="round"/>'
    f'<path class="mk-wand" d="{WAND_B}" fill="none" stroke-width="7" stroke-linecap="round"/>'
    '<circle class="mk-drop" cx="33.5" cy="23" r="1.9"/><circle class="mk-drop" cx="29" cy="28.5" r="1.4"/>'
    '<circle class="mk-drop" cx="36.5" cy="29" r="1.2"/></svg>'
)

# The same art on the brand ground (favicon, touch icon, hub tile): a white spray fan, wand and drops.
MARK_ON_BRAND = (
    '<g transform="translate(1.9 2.1) scale(.9)">'
    f'<path d="{FAN_D}" fill="#fff" fill-opacity=".94"/>'
    f'<path d="{WAND_A}" fill="none" stroke="#F5D0FE" stroke-width="4.6" stroke-linecap="round"/>'
    f'<path d="{WAND_B}" fill="none" stroke="#fff" stroke-width="7" stroke-linecap="round"/>'
    '<circle cx="33.5" cy="23" r="1.9" fill="#fff"/><circle cx="29" cy="28.5" r="1.4" fill="#fff"/>'
    '<circle cx="36.5" cy="29" r="1.2" fill="#fff"/></g>'
)


def favicon_data_uri():
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40">'
        f'<rect width="40" height="40" rx="9" fill="{BRAND}"/>{MARK_ON_BRAND}</svg>'
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
            '<meta property="og:site_name" content="Grime Time">',
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
    cut = src.index('<div class="app"')
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
    if src.count('<style>') != 1 or src.count('<script>') != 1:
        sys.exit('expected exactly one style block and one script block')

    # Support address becomes a real mailto link on this standalone page (the script still fills its text).
    sup = re.search(r"var SUPPORT = '([^']+)';", body)
    if not sup:
        sys.exit('SUPPORT not found')
    support = sup.group(1)
    n = body.count('<span class="mail"></span>')
    if n != 1:
        sys.exit(f'expected 1 mail span, found {n}')
    body = body.replace('<span class="mail"></span>', f'<a class="mail" href="mailto:{support}"></a>')

    # Footer: maker line and privacy link.
    foot_old = '<button type="button" class="linkish mail-copy">Copy</button></p>\n  </footer>'
    if body.count(foot_old) != 1:
        sys.exit('footer anchor not found exactly once')
    foot_new = ('<button type="button" class="linkish mail-copy">Copy</button></p>\n'
                f'    <p>Made by {html.escape(MAKER)}. <a href="privacy.html">Privacy</a></p>\n  </footer>')
    body = body.replace(foot_old, foot_new)

    noscript = ('<noscript><p style="padding:16px;font:16px/1.45 system-ui,sans-serif">'
                'Grime Time needs JavaScript. Turn it on in your browser settings, then reload this page.</p></noscript>')

    return (
        '<!doctype html>\n<html lang="en">\n<head>\n'
        + head_tags(TITLE, DESC, SITE_URL)
        + '\n<style>\n' + SKELETON_CSS + '\n' + font_faces(APP_FONTS) + '\n' + app_css + '\n</style>\n'
        + '</head>\n<body>\n' + noscript + '\n' + body.rstrip() + '\n</body>\n</html>\n'
    )


PRIVACY_CSS = """
:root {
  --bg: #F5F1F9; --surface: #FFFFFF; --ink: #1D1230; --muted: #5A4A6D; --line: #DDD2EA;
  --accent: #A21CAF; --on-accent: #FFFFFF; --accent-ink: #A21CAF;
  --font-display: 'Big Shoulders Display', 'Arial Narrow', 'Helvetica Neue', Arial, sans-serif;
  --font-body: 'Public Sans', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #120A1D; --surface: #1C1230; --ink: #F3EAFA; --muted: #BBA6D1; --line: #33224B;
    --accent: #E879F9; --on-accent: #2A0832; --accent-ink: #E879F9; color-scheme: dark;
  }
}
:root[data-theme="dark"] {
  --bg: #120A1D; --surface: #1C1230; --ink: #F3EAFA; --muted: #BBA6D1; --line: #33224B;
  --accent: #E879F9; --on-accent: #2A0832; --accent-ink: #E879F9; color-scheme: dark;
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
.brand .mk-fan { fill: var(--accent); fill-opacity: 0.9; }
.brand .mk-wand { stroke: var(--ink); }
.brand .mk-drop { fill: var(--accent); }
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
    <a class="brand" href="./" aria-label="Grime Time home">{MARK_SVG}<span>Grime Time</span></a>
    <a class="back" href="./">Back to the game</a>
  </div>
  <main class="doc">
    <div>
      <h1>Privacy policy</h1>
      <p class="updated">Grime Time, last updated {UPDATED}</p>
    </div>

    <section>
      <h2>The short version</h2>
      <p>Grime Time has no accounts, no ads, no analytics and no cookies of its own. Your progress is saved only in this browser, on your own device, and nothing is sent anywhere, not to us and not to anyone else. The sound is made by the page itself while you play.</p>
    </section>

    <section>
      <h2>What is stored on your device</h2>
      <ul>
        <li>Your progress: cash, lifetime earnings, stars on each job, rig upgrades, gear, crew, trucks, Franchise points and your rig colour</li>
        <li>Your settings: sound on or off, and calm mode</li>
        <li>The time of your last save, taken from your device clock, so the game can work out what your crew earned while you were away</li>
        <li>A backup copy of a saved game that the page could not read, if that ever happens</li>
      </ul>
      <p style="margin-top:10px">This lives in your browser's local storage (the localStorage feature) for this site. Clearing your browser data removes it, and a different browser or device starts empty. The Export save button in Settings gives you a code you can keep or paste on another device. If your browser blocks storage, Grime Time still works, but nothing is kept after you close the page.</p>
    </section>

    <section>
      <h2>What this page does not do</h2>
      <ul>
        <li>No cookies, no accounts and no sign up</li>
        <li>No analytics, tracking pixels or advertising</li>
        <li>No outside fonts or scripts. The fonts are built into the page, so loading it does not contact any font service</li>
        <li>No sending of your progress anywhere. A save code is just text that you copy yourself, and the page never sends it</li>
        <li>No audio files and no microphone or camera. Sound effects are generated by the page, using your browser's audio features, while you play</li>
      </ul>
    </section>

    <section>
      <h2>The Share button</h2>
      <p>After a job, the Share button draws a before and after picture on your device, using the page itself. It then hands that picture to your browser's share sheet, so you can send it to an app you choose. If your browser cannot share pictures, it downloads the picture as a PNG file instead. The page never uploads the picture. The picture, and the short message that goes with it, show the job name, what you earned and the address of this game, and nothing else about you.</p>
    </section>

    <section>
      <h2>Hosting</h2>
      <p>Grime Time is hosted on GitHub Pages. Like any web host, GitHub may log technical details such as your IP address and browser type when you load the page, under <a href="https://docs.github.com/site-policy/privacy-policies/github-general-privacy-statement">GitHub's privacy statement</a>. We add no tracking of our own on top of that.</p>
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
        + head_tags('Privacy Policy - Grime Time',
                    'How Grime Time handles your data: your progress stays in your browser, on your device.',
                    SITE_URL + 'privacy.html', og=False)
        + '\n<style>\n' + SKELETON_CSS + '\n' + font_faces(PRIVACY_FONTS) + '\n' + PRIVACY_CSS + '</style>\n'
        + '</head>\n<body>' + body + '</body>\n</html>\n'
    )


def problems_for(name, text, kind):
    """Everything the builder refuses. `kind` is 'index' or 'privacy'. Returns a list of messages (empty means clean)."""
    out = []
    if any(ch in text for ch in DASHES):
        out.append(f'{name}: dash character found')
    if '@@' in text:
        out.append(f'{name}: unreplaced placeholder')
    # Nothing may be fetched from another site. Only this site and the GitHub privacy statement may be named.
    scrubbed = text.replace(ALLOWED_NAMESPACE, '')
    for url in re.findall(r'https?://[^\s"\'<>)]+', scrubbed):
        if not url.startswith(ALLOWED_LINKS):
            out.append(f'{name}: outside address {url}')
    if len(re.findall(r'<h1[ >]', text)) != 1:
        out.append(f'{name}: expected exactly one h1')
    n_scripts = len(re.findall(r'<script\b', text))
    if kind == 'index' and n_scripts != 1:
        out.append(f'{name}: expected exactly one script block, found {n_scripts}')
    if kind == 'privacy' and n_scripts != 0:
        out.append(f'{name}: the privacy page must not have scripts')
    if re.search(r'<script[^>]*\bsrc=', text) or re.search(r'<link[^>]*rel="stylesheet"', text) or '@import' in text or '<iframe' in text:
        out.append(f'{name}: external script, stylesheet or frame')
    for pat in FORBIDDEN_CALLS:
        if re.search(pat, text):
            out.append(f'{name}: forbidden call {pat}')
    return out


def check_meta():
    out = []
    if not len(TITLE) < 60:
        out.append(f'title length {len(TITLE)} is not under 60')
    if not 60 < len(DESC) <= 160:
        out.append(f'description length {len(DESC)} is outside 61-160')
    if not 60 < len(OG_DESC) <= 200:
        out.append(f'og description length {len(OG_DESC)} is outside 61-200')
    if not 40 < len(OG_ALT) <= 420:
        out.append(f'og image alt length {len(OG_ALT)} is outside 41-420')
    return out


def hub_tile():
    """The 40 x 40 tile for hub_icons.py: (ground colour, inner markup)."""
    return (BRAND, MARK_ON_BRAND)


def folder_problems(complete=False):
    """Stray files in the published folder (always refused). With complete=True a missing one is a problem too."""
    names = sorted(p.name for p in OUT.iterdir()) if OUT.is_dir() else []
    out = [f'{OUT.name}: unexpected file {n} (the folder holds only {", ".join(FOUR_FILES)})' for n in names if n not in FOUR_FILES]
    if complete:
        out += [f'{OUT.name}: missing file {n}' for n in FOUR_FILES if n not in names]
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    problems = check_meta() + folder_problems()
    index = build_index()
    support = re.search(r"var SUPPORT = '([^']+)';", index).group(1)
    privacy = build_privacy(support)
    problems += problems_for('index.html', index, 'index') + problems_for('privacy.html', privacy, 'privacy')
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
