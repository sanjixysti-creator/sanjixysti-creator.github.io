#!/usr/bin/env python3
"""Build the Xysti Software hub (the site root page) from hub.src.html.

Output goes straight into the site repo: index.html. Images (og.png, apple-touch-icon.png) come from
build_images_hub.py. Fonts are embedded as base64 so the page makes no outside requests.
"""
import os
import base64
import html
import pathlib
import re
import sys

from build_site import font_faces
import hub_icons as ic

HERE = pathlib.Path(__file__).resolve().parent
REPO = pathlib.Path(os.environ.get('SITE_REPO', '/home/claude/sanjixysti-creator.github.io'))
SRC = HERE / 'hub.src.html'
OUT = REPO / 'index.html'

SITE_URL = 'https://sanjixysti-creator.github.io/'
TITLE = 'Xysti Software: Small Free Tools for Specific Jobs'
DESC = ('Free calculators, checkers, a QR code maker, a game and add-ons: pressure washing quotes, '
        'delivery offer checks, used GPU checks and a YouTube extension.')
OG_DESC = ('Small free tools for specific jobs: pressure washing quotes and job profit, delivery offer checks, '
           'used GPU checks, a QR code maker, a pressure washing game and a YouTube extension.')
OG_ALT = ('Xysti Software, small free tools for specific jobs, with the icons of Rinse Quote, Rinse Mix, '
          'Rinse Rate, Drive Rate, Used GPU Check, Tuner for YouTube, Grime Time and QR Forever.')
BG_LIGHT = '#E5E9EB'
BG_DARK = '#11171B'

HUB_FONTS = [
    ('Big Shoulders Display', 'big-shoulders-display', 800),
    ('Public Sans', 'public-sans', 400),
    ('Public Sans', 'public-sans', 600),
]


def head_tags():
    t, d = html.escape(TITLE, quote=True), html.escape(DESC, quote=True)
    od, oa = html.escape(OG_DESC, quote=True), html.escape(OG_ALT, quote=True)
    fav = 'data:image/svg+xml;base64,' + base64.b64encode(ic.favicon_svg().encode()).decode('ascii')
    return '\n'.join([
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        f'<title>{t}</title>',
        f'<meta name="description" content="{d}">',
        '<meta name="color-scheme" content="light dark">',
        f'<meta name="theme-color" content="{BG_LIGHT}" media="(prefers-color-scheme: light)">',
        f'<meta name="theme-color" content="{BG_DARK}" media="(prefers-color-scheme: dark)">',
        f'<link rel="canonical" href="{SITE_URL}">',
        f'<link rel="icon" href="{fav}">',
        '<link rel="apple-touch-icon" href="apple-touch-icon.png">',
        '<meta property="og:type" content="website">',
        '<meta property="og:site_name" content="Xysti Software">',
        f'<meta property="og:title" content="{t}">',
        f'<meta property="og:description" content="{od}">',
        f'<meta property="og:url" content="{SITE_URL}">',
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
    ])


def main():
    src = SRC.read_text(encoding='utf-8')
    out = (src.replace('@@HEAD@@', head_tags())
              .replace('@@FONTS@@', font_faces(HUB_FONTS))
              .replace('@@MARK@@', ic.mark_svg())
              .replace('@@TILE_RQ@@', ic.tile_svg(ic.RINSE_QUOTE))
              .replace('@@TILE_RM@@', ic.tile_svg(ic.RINSE_MIX))
              .replace('@@TILE_RATE@@', ic.tile_svg(ic.RINSE_RATE))
              .replace('@@TILE_DRIVE@@', ic.tile_svg(ic.DRIVE_RATE))
              .replace('@@TILE_GPU@@', ic.tile_svg(ic.GPU_CHECK))
              .replace('@@TILE_TUNER@@', ic.tile_svg(ic.TUNER))
              .replace('@@TILE_GRIME@@', ic.tile_svg(ic.GRIME_TIME))
              .replace('@@TILE_QR@@', ic.tile_svg(ic.QR_FOREVER)))
    problems = []
    if '@@' in out:
        problems.append('unreplaced placeholder')
    if re.search('[\u2014\u2013]', out):
        problems.append('dash character found')
    if not 61 <= len(DESC) <= 160:
        problems.append(f'description length {len(DESC)}')
    if len(re.findall(r'<li class="row"', out)) != 8:
        problems.append('expected eight rows')
    # Every internal link must exist in the site repo.
    for href in re.findall(r'href="([^"#:]+)"', out):
        if href.startswith(('data:', 'http')):
            continue
        target = REPO / href
        if target.is_dir():
            target = target / 'index.html'
        if not target.exists():
            problems.append(f'broken link: {href}')
    # Fonts asked for in CSS must be embedded.
    asked = set(re.findall(r"font:\s*\d+\s+[^;]*?var\(--(display|text)\)", out))
    embedded = {f[0] for f in HUB_FONTS}
    if embedded != {'Big Shoulders Display', 'Public Sans'}:
        problems.append('unexpected font set')
    # No outside resources: only the canonical, og/twitter urls and the mailto may mention the host or schemes.
    for m in re.findall(r'(?:src|href)="(https?://[^"]+)"', out):
        if m != SITE_URL:
            problems.append(f'outside link: {m}')
    if problems:
        sys.exit('hub build failed:\n  ' + '\n  '.join(problems))
    OUT.write_text(out, encoding='utf-8')
    print(f'index.html: {len(out.encode()) / 1024:.1f} KB, description {len(DESC)} chars, dashes: 0')


if __name__ == '__main__':
    main()
