#!/usr/bin/env python3
"""Make og.png (1200x630 link preview) and apple-touch-icon.png (180x180) for the Xysti Software hub.

Both go straight into the site repo root. Uses the same icon art as the page (hub_icons.py).
"""
import os
import pathlib

from playwright.sync_api import sync_playwright

from build_site import font_faces
import hub_icons as ic

REPO = pathlib.Path(os.environ.get('SITE_REPO', '/home/claude/sanjixysti-creator.github.io'))
FONTS = [('Big Shoulders Display', 'big-shoulders-display', 800), ('Public Sans', 'public-sans', 400), ('Public Sans', 'public-sans', 600)]

ROWS = [
    ('Rinse Quote', ic.RINSE_QUOTE),
    ('Rinse Mix', ic.RINSE_MIX),
    ('Used GPU Check', ic.GPU_CHECK),
    ('Tuner for YouTube', ic.TUNER),
]


def launch(p):
    try:
        return p.chromium.launch()
    except Exception:
        return p.chromium.launch(executable_path='/opt/pw-browsers/chromium-1194/chrome-linux/chrome')


def card_html():
    rows = '\n'.join(
        f'<div class="r">{ic.tile_svg(art, cls="t")}<b>{name}</b></div>' for name, art in ROWS)
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
{font_faces(FONTS)}
*{{box-sizing:border-box;margin:0}}
html,body{{width:1200px;height:630px;overflow:hidden}}
body{{position:relative;background:#E5E9EB;color:#0F181D;font-family:'Public Sans',system-ui,sans-serif;-webkit-font-smoothing:antialiased}}
.left{{position:absolute;left:72px;top:60px;bottom:60px;width:560px;display:flex;flex-direction:column;justify-content:space-between}}
.brand{{display:flex;align-items:center;gap:16px}}
.brand svg{{width:58px;height:58px}}
.brand span{{font:800 50px/1 'Big Shoulders Display','Arial Narrow',sans-serif;letter-spacing:.03em}}
h1{{font:800 108px/.92 'Big Shoulders Display','Arial Narrow',sans-serif;letter-spacing:-.005em}}
.sub{{font:400 28px/1.35 'Public Sans',sans-serif;max-width:520px}}
.list{{position:absolute;right:72px;top:60px;bottom:60px;width:430px;display:flex;flex-direction:column;border-bottom:3px solid #0F181D}}
.r{{flex:1;display:flex;align-items:center;gap:22px;border-top:3px solid #0F181D}}
.t{{width:84px;height:84px;border-radius:22.5%;flex:none;display:block}}
.r b{{font:800 44px/1 'Big Shoulders Display','Arial Narrow',sans-serif;letter-spacing:.01em}}
</style></head><body>
<div class="left">
  <div class="brand">{ic.mark_svg()}<span>Xysti Software</span></div>
  <div>
    <h1>Small tools for specific jobs.</h1>
  </div>
  <p class="sub">Free calculators, checkers and add-ons.</p>
</div>
<div class="list">
{rows}
</div>
</body></html>"""


def icon_html():
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
*{{margin:0}}
html,body{{width:180px;height:180px;overflow:hidden}}
body{{background:{ic.INK};display:grid;place-items:center}}
svg{{width:132px;height:132px}}
</style></head><body>
<svg viewBox="0 0 40 40"><path d="M10 10L30 30M30 10L10 30" fill="none" stroke="{ic.CHALK}" stroke-width="6" stroke-linecap="round"/><circle cx="20" cy="20" r="4" fill="{ic.SIGNAL}"/></svg>
</body></html>"""


def main():
    with sync_playwright() as p:
        b = launch(p)
        ctx = b.new_context(viewport={'width': 1200, 'height': 630}, device_scale_factor=1)
        pg = ctx.new_page()
        pg.set_content(card_html(), wait_until='load')
        pg.evaluate('document.fonts.ready')
        pg.wait_for_timeout(300)
        pg.screenshot(path=str(REPO / 'og.png'), clip={'x': 0, 'y': 0, 'width': 1200, 'height': 630})
        ctx.close()
        ctx = b.new_context(viewport={'width': 180, 'height': 180}, device_scale_factor=1)
        pg = ctx.new_page()
        pg.set_content(icon_html(), wait_until='load')
        pg.screenshot(path=str(REPO / 'apple-touch-icon.png'), clip={'x': 0, 'y': 0, 'width': 180, 'height': 180})
        ctx.close()
        b.close()
    for name in ('og.png', 'apple-touch-icon.png'):
        print(name, os.path.getsize(REPO / name), 'bytes')


if __name__ == '__main__':
    main()
