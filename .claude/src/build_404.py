#!/usr/bin/env python3
"""Build 404.html (the page GitHub Pages serves for any address that does not exist) from 404.src.html.

Output goes straight into the site repo root. Fonts are embedded as base64 so the page makes no outside
requests. It is served for addresses of any depth, so it must not use a single relative link.
"""
import base64
import html
import os
import pathlib
import re
import sys

from build_site import font_faces
import hub_icons as ic

HERE = pathlib.Path(__file__).resolve().parent
REPO = pathlib.Path(os.environ.get('SITE_REPO', '/home/claude/sanjixysti-creator.github.io'))
SRC = HERE / '404.src.html'
OUT = REPO / '404.html'

TITLE = 'Page not found - Xysti Software'
BG_LIGHT = '#E5E9EB'
BG_DARK = '#11171B'

FONTS = [
    ('Big Shoulders Display', 'big-shoulders-display', 800),
    ('Public Sans', 'public-sans', 400),
    ('Public Sans', 'public-sans', 600),
]


def head_tags():
    t = html.escape(TITLE, quote=True)
    fav = 'data:image/svg+xml;base64,' + base64.b64encode(ic.favicon_svg().encode()).decode('ascii')
    return '\n'.join([
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        f'<title>{t}</title>',
        '<meta name="robots" content="noindex">',
        '<meta name="color-scheme" content="light dark">',
        f'<meta name="theme-color" content="{BG_LIGHT}" media="(prefers-color-scheme: light)">',
        f'<meta name="theme-color" content="{BG_DARK}" media="(prefers-color-scheme: dark)">',
        f'<link rel="icon" href="{fav}">',
        '<link rel="apple-touch-icon" href="/apple-touch-icon.png">',
    ])


def main():
    src = SRC.read_text(encoding='utf-8')
    out = (src.replace('@@HEAD@@', head_tags())
              .replace('@@FONTS@@', font_faces(FONTS))
              .replace('@@MARK@@', ic.mark_svg())
              .replace('@@TILE_RQ@@', ic.tile_svg(ic.RINSE_QUOTE))
              .replace('@@TILE_RM@@', ic.tile_svg(ic.RINSE_MIX))
              .replace('@@TILE_RATE@@', ic.tile_svg(ic.RINSE_RATE))
              .replace('@@TILE_GPU@@', ic.tile_svg(ic.GPU_CHECK))
              .replace('@@TILE_TUNER@@', ic.tile_svg(ic.TUNER)))
    problems = []
    if '@@' in out:
        problems.append('unreplaced placeholder')
    if re.search('[\u2014\u2013]', out):
        problems.append('dash character found')
    if '<script' in out:
        problems.append('script found')
    if len(re.findall(r'<li class="row"', out)) != 5:
        problems.append('expected five rows')
    # Served for any depth, so no link may be relative. Only root-absolute paths, mailto and data: are allowed.
    for href in re.findall(r'(?:href|src)="([^"]*)"', out):
        if not (href.startswith('/') and not href.startswith('//')) and not href.startswith(('mailto:', 'data:')):
            problems.append(f'link that would break at depth: {href}')
    # Every root-absolute link must exist in the site repo.
    for href in re.findall(r'href="(/[^"#]*)"', out):
        target = REPO / href.lstrip('/')
        if target.is_dir():
            target = target / 'index.html'
        if href != '/' and not target.exists():
            problems.append(f'broken link: {href}')
    if not (REPO / 'index.html').exists():
        problems.append('no home page in repo')
    if 'noindex' not in out:
        problems.append('missing noindex')
    if problems:
        sys.exit('404 build failed:\n  ' + '\n  '.join(problems))
    OUT.write_text(out, encoding='utf-8')
    print(f'404.html: {len(out.encode()) / 1024:.1f} KB, dashes: 0, scripts: 0')


if __name__ == '__main__':
    main()
