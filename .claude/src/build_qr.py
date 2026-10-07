#!/usr/bin/env python3
"""Build the standalone QR Forever site from the fragment.

Input : qr-forever.html (the fragment, source of truth)
Output: site/qr-forever/index.html   (the generator, fonts inlined, no external requests)
        site/qr-forever/privacy.html (short privacy page)
Images (og.png, apple-touch-icon.png) are made by build_images_qr.py.
Shares the font pipeline with build_site.py and leaves that file untouched.
"""
import base64
import html
import pathlib
import re
import sys

from build_site import APP_FONTS, PRIVACY_FONTS, SKELETON_CSS, font_faces

HERE = pathlib.Path(__file__).resolve().parent
SRC = HERE / 'qr-forever.html'
OUT = HERE / 'site' / 'qr-forever'
# The published folder holds these four files and nothing else (the two images come from build_images_qr.py).
FOUR_FILES = ('apple-touch-icon.png', 'index.html', 'og.png', 'privacy.html')

SITE_URL = 'https://sanjixysti-creator.github.io/qr-forever/'
TITLE = 'QR Forever: Free QR Code Generator That Never Expires'
DESC = ('Make a free QR code for a link, Wi-Fi, contact card, email, map or event. Download PNG or SVG, or print it. '
        'No sign up, no expiry, no tracking.')
OG_DESC = 'Make QR codes that never expire. Links, Wi-Fi, contacts and more. PNG and SVG, free, no sign up, no ads.'
OG_ALT = ('QR Forever, a free QR code generator. A screenshot of the page with the Link tab open: a web address typed in the box '
          'and a finished black and white QR code to the right of it, with a Download PNG button below the code. '
          'Beside the screenshot: Codes that never expire. Free, no sign up.')
MAKER = 'Xysti Software'
UPDATED = 'October 2026'

# Outside addresses a built page may mention. Everything else is refused. The svg namespace name is an identifier, never fetched.
# The Google Maps address is only the text a Map code can hold (the page writes it into a code and never loads it).
ALLOWED_LINKS = ('https://sanjixysti-creator.github.io/', 'https://docs.github.com/', 'https://www.google.com/maps/search/?api=1&query=')
ALLOWED_NAMESPACE = 'http://www.w3.org/2000/svg'
# Calls the page must never contain (no network, no cookies, no browser dialogs).
FORBIDDEN_CALLS = (r'\bfetch\(', r'XMLHttpRequest', r'sendBeacon', r'WebSocket', r'EventSource', r'importScripts', r'document\.cookie',
                   r'\balert\(', r'\bconfirm\(', r'\bprompt\(')

BRAND = '#15803D'
BG_LIGHT, BG_DARK = '#E8F0EA', '#09130E'

# Same dash characters the tests look for, written without typing them.
DASHES = ''.join(chr(c) for c in (0x2014, 0x2013, 0x2212))

RING_A = 'M3 3h14v14H3zM6.2 6.2v7.6h7.6V6.2z'
RING_B = 'M23 3h14v14H23zM26.2 6.2v7.6h7.6V6.2z'
RING_C = 'M3 23h14v14H3zM6.2 26.2v7.6h7.6v-7.6z'
DOTS = ('M8.2 8.2h3.6v3.6H8.2zM28.2 8.2h3.6v3.6h-3.6zM8.2 28.2h3.6v3.6H8.2zM23 23h5.5v5.5H23zM31.5 23H37v5.5h-5.5z'
        'M23 31.5h5.5V37H23zM31.5 31.5H37V37h-5.5z')

# One place for the mark so the favicon, the touch icon, the link preview and the privacy page agree.
MARK_SVG = (
    '<svg viewBox="0 0 40 40" aria-hidden="true" focusable="false">'
    f'<path class="mk-ring" d="{RING_A}"/><path class="mk-ring" d="{RING_B}"/><path class="mk-ring" d="{RING_C}"/>'
    f'<path class="mk-dot" d="{DOTS}"/></svg>'
)

# The same art on the brand ground (favicon, touch icon, hub tile): white finder squares and data squares.
MARK_ON_BRAND = (
    '<g transform="translate(5.2 5.2) scale(.74)" fill="#fff">'
    f'<path fill-rule="evenodd" d="{RING_A}{RING_B}{RING_C}"/>'
    f'<path d="{DOTS}"/></g>'
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
            '<meta property="og:site_name" content="QR Forever">',
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
    if src.count('/* PURE-BEGIN') != 1 or src.count('/* PURE-END */') != 1:
        sys.exit('the pure region markers must appear exactly once (the tests read that region)')

    # The fonts the page asks for must be the fonts the build embeds.
    asked = set(re.findall(r'family=([A-Za-z+]+)', head))
    have = {f[0].replace(' ', '+') for f in APP_FONTS}
    if asked != have:
        sys.exit(f'font families differ: page asks for {sorted(asked)}, build embeds {sorted(have)}')

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
    foot_old = '<button type="button" class="linkish mail-copy">Copy</button></p>\n      </footer>'
    if body.count(foot_old) != 1:
        sys.exit('footer anchor not found exactly once')
    foot_new = ('<button type="button" class="linkish mail-copy">Copy</button></p>\n'
                f'        <p>Made by {html.escape(MAKER)}. <a href="privacy.html">Privacy</a></p>\n      </footer>')
    body = body.replace(foot_old, foot_new)

    noscript = ('<noscript><p style="padding:16px;font:16px/1.45 system-ui,sans-serif">'
                'QR Forever needs JavaScript. Turn it on in your browser settings, then reload this page.</p></noscript>')

    return (
        '<!doctype html>\n<html lang="en">\n<head>\n'
        + head_tags(TITLE, DESC, SITE_URL)
        + '\n<style>\n' + SKELETON_CSS + '\n' + font_faces(APP_FONTS) + '\n' + app_css + '\n</style>\n'
        + '</head>\n<body>\n' + noscript + '\n' + body.rstrip() + '\n</body>\n</html>\n'
    )


PRIVACY_CSS = """
:root {
  --bg: #E8F0EA; --surface: #FFFFFF; --ink: #0C2216; --muted: #476052; --line: #C5D8CB;
  --accent: #15803D; --on-accent: #FFFFFF; --accent-ink: #0F6B31;
  --font-display: 'Big Shoulders Display', 'Arial Narrow', 'Helvetica Neue', Arial, sans-serif;
  --font-body: 'Public Sans', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #09130E; --surface: #101D16; --ink: #E3F1E8; --muted: #93AD9F; --line: #213B2C;
    --accent: #4ADE80; --on-accent: #04210F; --accent-ink: #4ADE80; color-scheme: dark;
  }
}
:root[data-theme="dark"] {
  --bg: #09130E; --surface: #101D16; --ink: #E3F1E8; --muted: #93AD9F; --line: #213B2C;
  --accent: #4ADE80; --on-accent: #04210F; --accent-ink: #4ADE80; color-scheme: dark;
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
.brand .mk-ring { fill: var(--accent); fill-rule: evenodd; }
.brand .mk-dot { fill: var(--accent); }
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
    <a class="brand" href="./" aria-label="QR Forever home">{MARK_SVG}<span>QR Forever</span></a>
    <a class="back" href="./">Back to the generator</a>
  </div>
  <main class="doc">
    <div>
      <h1>Privacy policy</h1>
      <p class="updated">QR Forever, last updated {UPDATED}</p>
    </div>

    <section>
      <h2>The short version</h2>
      <p>QR Forever has no accounts, no ads, no analytics and no cookies of its own. Your codes are drawn in your browser, on your own device. What you type is never sent anywhere, not to us and not to anyone else. The codes are static: they hold your content directly and do not go through a link of ours, so nobody can count, see or switch off your scans.</p>
    </section>

    <section>
      <h2>What is stored on your device</h2>
      <ul>
        <li>Your settings: the kind of code you used last, the error correction level, the download size, the white border, the colours, the shape of the squares, the printed size and your choices on the Wi-Fi sign</li>
        <li>What you typed, but only if you turn on Remember what I type on this device. That switch is off until you turn it on. It keeps the text in the forms and the caption</li>
        <li>A Wi-Fi password is never kept, even when that switch is on</li>
      </ul>
      <p style="margin-top:10px">This lives in your browser's local storage (the localStorage feature) for this site. Clearing your browser data removes it, and a different browser or device starts empty. If your browser blocks storage, QR Forever still works, but nothing is kept after you close the page.</p>
    </section>

    <section>
      <h2>What this page does not do</h2>
      <ul>
        <li>No cookies, no accounts and no sign up</li>
        <li>No analytics, tracking pixels or advertising</li>
        <li>No outside fonts or scripts. The fonts are built into the page, so loading it does not contact any font service</li>
        <li>No sending of what you type. Every code is made on your device</li>
        <li>No short links, redirects or tracking of scans. A scan goes straight from the picture to the phone</li>
      </ul>
    </section>

    <section>
      <h2>What is inside a code</h2>
      <p>Everything you type goes into the picture itself, so anyone who scans or photographs the code can read it. Do not put anything secret in a code you will share or print where others can see it. A Wi-Fi code holds the network password in a form that any phone camera can read.</p>
    </section>

    <section>
      <h2>Downloads, copy, share and print</h2>
      <p>Download PNG and Download SVG save a file on your device. Copy image puts the picture on your clipboard. Share hands the picture to your browser's share sheet, where you choose an app, and only appears if your browser can do that. Print opens your browser's print window. None of these send anything to us, and the page never uploads a picture.</p>
    </section>

    <section>
      <h2>Hosting</h2>
      <p>QR Forever is hosted on GitHub Pages. Like any web host, GitHub may log technical details such as your IP address and browser type when you load the page, under <a href="https://docs.github.com/site-policy/privacy-policies/github-general-privacy-statement">GitHub's privacy statement</a>. We add no tracking of our own on top of that.</p>
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
        + head_tags('Privacy Policy - QR Forever',
                    'How QR Forever handles your data: your codes are made in your browser and what you type is not sent anywhere.',
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
    # Nothing may be fetched from another site. Only this site, the GitHub privacy statement and the map link text may be named.
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
    print('title length', len(TITLE), 'description length', len(DESC), 'og description length', len(OG_DESC), 'alt length', len(OG_ALT))


if __name__ == '__main__':
    main()
