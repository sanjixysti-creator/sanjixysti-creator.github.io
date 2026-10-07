#!/usr/bin/env python3
"""Make og.png (1200x630 link preview) and apple-touch-icon.png (180x180) for the standalone QR Forever site.

The picture on the right of the preview is a REAL screenshot of the built page with the Link tab open and this site's own address typed in
the box, so the code in it is a working code: scanning the preview with a phone opens QR Forever. The script reads that code back from the
page with zxing-cpp and refuses to continue unless it says exactly SITE_URL. OG_ALT in build_qr.py describes this image. Run build_qr.py first.
"""
import base64
import functools
import http.server
import io
import os
import pathlib
import threading

import numpy as np
import zxingcpp
from PIL import Image
from playwright.sync_api import sync_playwright

from build_qr import BRAND, MARK_ON_BRAND, OUT, SITE_URL, folder_problems
from build_site import APP_FONTS, font_faces

HERE = pathlib.Path(__file__).resolve().parent
SITE_ROOT = OUT.parent  # .../site
TYPED = 'sanjixysti-creator.github.io/qr-forever/'   # what is typed in the box; the page adds https://
PANEL_VIEWPORT = (960, 760)
OG_LIMIT = 450 * 1024


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def launch(p):
    try:
        return p.chromium.launch()
    except Exception:
        return p.chromium.launch(executable_path='/opt/pw-browsers/chromium-1194/chrome-linux/chrome')


CARD_FONTS = [f for f in APP_FONTS if f[1] in ('big-shoulders-display', 'public-sans')]
MARK = f'<svg viewBox="0 0 40 40" aria-hidden="true">{MARK_ON_BRAND}</svg>'


def card_html(panel_b64):
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
{font_faces(CARD_FONTS)}
*{{box-sizing:border-box;margin:0}}
html,body{{width:1200px;height:630px;overflow:hidden}}
body{{position:relative;background:{BRAND};color:#fff;font-family:'Public Sans',system-ui,sans-serif;-webkit-font-smoothing:antialiased}}
.bg{{position:absolute;inset:0;background:
  radial-gradient(640px 480px at 74% 52%, rgba(255,255,255,.16), rgba(255,255,255,0) 70%),
  linear-gradient(135deg,#15803D 0%,#116B33 44%,#0A3F1E 100%)}}
.left{{position:absolute;left:64px;top:0;bottom:0;width:520px;display:flex;flex-direction:column;justify-content:center;gap:22px}}
.left svg{{width:104px;height:104px;flex:none;margin:0 0 -6px -10px}}
.left h1{{font:800 112px/0.92 'Big Shoulders Display','Arial Narrow',Arial,sans-serif;letter-spacing:.02em;text-transform:uppercase;white-space:nowrap}}
.tag{{font:700 38px/1.2 'Public Sans',system-ui,sans-serif;max-width:470px;text-wrap:balance;color:#E4F8EB}}
.pill{{align-self:flex-start;background:#fff;color:#0B3D1D;font:800 20px/1 'Public Sans',system-ui,sans-serif;letter-spacing:.09em;text-transform:uppercase;padding:15px 25px;border-radius:999px;margin-top:4px}}
.panel{{position:absolute;right:40px;top:50%;width:572px;transform:translateY(-50%) rotate(-2deg);border-radius:18px;border:5px solid rgba(255,255,255,.96);box-shadow:0 24px 40px rgba(0,25,10,.5);display:block}}
</style></head><body>
<div class="bg"></div>
<div class="left">
  {MARK}
  <h1>QR Forever</h1>
  <p class="tag">Codes that never expire.</p>
  <span class="pill">Free, no sign up</span>
</div>
<img class="panel" alt="" src="data:image/png;base64,{panel_b64}">
</body></html>"""


def icon_html():
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
*{{margin:0}}
html,body{{width:180px;height:180px;overflow:hidden}}
body{{background:linear-gradient(135deg,#1A8F45,{BRAND} 48%,#0C4F26);display:grid;place-items:center}}
svg{{width:180px;height:180px;display:block}}
</style></head><body>{MARK}</body></html>"""


def read_code(png_bytes):
    """What a reader makes of the code in this picture (None when it cannot read one)."""
    im = Image.open(io.BytesIO(png_bytes)).convert('L')
    arr = np.asarray(im)
    hits = zxingcpp.read_barcodes(arr)
    return hits[0].text if hits else None


def take_panel(browser, port):
    """The built page on a wide screen with the address typed: (panel png bytes, text the shown code holds)."""
    ctx = browser.new_context(viewport={'width': PANEL_VIEWPORT[0], 'height': PANEL_VIEWPORT[1]}, device_scale_factor=2, color_scheme='light')
    try:
        pg = ctx.new_page()
        pg.goto(f'http://127.0.0.1:{port}/qr-forever/')
        pg.wait_for_timeout(500)
        pg.evaluate('document.fonts.ready')
        pg.fill('#f-url', TYPED)
        pg.wait_for_timeout(400)
        pg.add_style_tag(content='*{caret-color:transparent!important}')
        # What the card shows must be what the alt text says: the Link tab is chosen and the page says the code is ready.
        facts = pg.evaluate("""() => ({tab: (document.querySelector('#tabs .tab[aria-selected="true"]') || {}).textContent,
                                       typed: document.getElementById('f-url').value,
                                       status: document.getElementById('status').textContent,
                                       png: !!document.getElementById('btnPng') && document.getElementById('btnPng').getAttribute('aria-disabled') !== 'true'})""")
        shown = read_code(pg.locator('#cv').screenshot())
        pg.evaluate('window.scrollTo(0, 0)')
        png = pg.screenshot(clip={'x': 0, 'y': 0, 'width': PANEL_VIEWPORT[0], 'height': PANEL_VIEWPORT[1]})
    finally:
        ctx.close()
    return png, facts, shown


def shrink_png(png_bytes, limit=OG_LIMIT):
    """Keep the picture as is when it is small enough, else reduce the palette until it fits (no resizing, no dithering noise)."""
    im = Image.open(io.BytesIO(png_bytes)).convert('RGB')
    buf = io.BytesIO()
    im.save(buf, 'PNG', optimize=True)
    if buf.tell() <= limit:
        return buf.getvalue(), 'rgb'
    for colors in (256, 224, 192, 160, 128):
        q = im.quantize(colors=colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
        buf = io.BytesIO()
        q.save(buf, 'PNG', optimize=True)
        if buf.tell() <= limit:
            return buf.getvalue(), f'{colors} colours'
    return buf.getvalue(), f'{colors} colours (still over the limit)'


def main():
    httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(SITE_ROOT)))
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    with sync_playwright() as p:
        browser = launch(p)

        # 1. The built page with this site's address typed in. The page draws every pixel of the panel, nothing is composed by hand.
        panel_png, facts, shown = take_panel(browser, port)
        print('facts:', facts, '| the code reads as:', shown)
        if facts['tab'] != 'Link' or facts['typed'] != TYPED or not facts['png']:
            raise SystemExit(f'the page is not in the state OG_ALT in build_qr.py describes: {facts}')
        if shown != SITE_URL:
            raise SystemExit(f'the code in the picture reads {shown!r}, not {SITE_URL!r}')
        (HERE / 'panel-og-qr.png').write_bytes(panel_png)

        # 2. Link preview card.
        ctx = browser.new_context(viewport={'width': 1200, 'height': 630}, device_scale_factor=1)
        pg = ctx.new_page()
        pg.set_content(card_html(base64.b64encode(panel_png).decode('ascii')), wait_until='load')
        pg.evaluate('document.fonts.ready')
        pg.wait_for_timeout(300)
        og_png = pg.screenshot(clip={'x': 0, 'y': 0, 'width': 1200, 'height': 630})
        ctx.close()
        data, how = shrink_png(og_png)
        (OUT / 'og.png').write_bytes(data)

        # 3. Home screen icon.
        ctx = browser.new_context(viewport={'width': 180, 'height': 180}, device_scale_factor=1)
        pg = ctx.new_page()
        pg.set_content(icon_html(), wait_until='load')
        pg.screenshot(path=str(OUT / 'apple-touch-icon.png'), clip={'x': 0, 'y': 0, 'width': 180, 'height': 180})
        ctx.close()
        browser.close()
    httpd.shutdown()
    for name in ('og.png', 'apple-touch-icon.png'):
        print(name, os.path.getsize(OUT / name), 'bytes')
    print('og.png palette:', how)
    problems = folder_problems(complete=True)
    if os.path.getsize(OUT / 'og.png') > OG_LIMIT:
        problems.append(f'og.png is {os.path.getsize(OUT / "og.png")} bytes, over the {OG_LIMIT} byte limit')
    if problems:
        raise SystemExit('build failed:\n  ' + '\n  '.join(problems))
    print('site/qr-forever holds exactly:', ', '.join(sorted(p.name for p in OUT.iterdir())))


if __name__ == '__main__':
    main()
