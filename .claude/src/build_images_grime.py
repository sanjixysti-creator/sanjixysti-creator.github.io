#!/usr/bin/env python3
"""Make og.png (1200x630 link preview) and apple-touch-icon.png (180x180) for the standalone Grime Time site.

The picture on the right of the preview is a REAL screenshot of the built game in the middle of a wash: half of the garden patio
is clean, the rest is still grimy, with the nozzle, wand, foam, spray and sparkles. The scripted strokes only drive the game through
its own #test hooks, every pixel in the panel is drawn by the game. OG_ALT in build_grime.py describes this image and the test suite
checks the words of the alt text against the facts in the picture (job name, tip, percent shown). Run build_grime.py first.
"""
import base64
import functools
import http.server
import io
import os
import pathlib
import re
import threading

from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright

from build_grime import BRAND, MARK_ON_BRAND, OUT, folder_problems
from build_site import APP_FONTS, font_faces

HERE = pathlib.Path(__file__).resolve().parent
SITE_ROOT = OUT.parent  # .../site
JOB = 'patio'
PANEL_VIEWPORT = (960, 720)
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

# A rig with a few upgrades, the soap and white tips, and a half clean patio: clean the left part with a slanted edge, lay a band of foam
# along the edge, then spray the edge with the white tip so the fan, droplets and sparkles are in the frame.
STATE = ("()=>window.__grime.setState({tut:true,stars:{driveway:3,patio:3,fence:3,wall:3,deck:3,garage:3,siding:3,car:3},"
         "gear:{soap:true,hot:true,pole:true,surface:false},up:{pressure:6,area:5,tank:3,reach:2,flow:2},money:5000,lifetime:60000,"
         "earned:60000,set:{sound:false,calm:false}})")
WASH_A = """()=>{
  const g=window.__grime, G=g.G(), w=G.w, sp=1100/60;
  const X0=0.30, X1=0.62, BAND=0.12;
  let lx=0, ly=0;
  function stroke(x0,x1,y){ let x=x0; const d=Math.sign(x1-x0); for(let k=0;k<3000&&(x1-x)*d>sp;k++){ x+=d*sp; lx=x; ly=y; g.pointer(x,y,true); g.advance(1000/60);} }
  const edge=(yy)=>w.W*(X0+(X1-X0)*(yy/w.H));
  g.tip('white'); let y=w.H*0.02, d=1;
  while(y<=w.H*0.98){ const xa=w.W*0.02, xb=edge(y); if(d>0) stroke(xa,xb,y); else stroke(xb,xa,y); d=-d; y+=w.H*0.05; }
  g.pointer(lx,ly,false);
  g.tip('soap'); y=w.H*0.06; d=1;
  while(y<=w.H*0.96){ const xa=edge(y), xb=edge(y)+w.W*BAND; if(d>0) stroke(xa,xb,y); else stroke(xb,xa,y); d=-d; y+=w.H*0.07; }
  g.pointer(lx,ly,false);
}"""
# After a pause (so the coins from the long scripted run have flown to the pay chip), the white tip works the foam at the edge.
WASH_B = """()=>{
  const g=window.__grime, G=g.G(), w=G.w;
  const X0=0.30, X1=0.62, NY=0.52;
  const edge=(yy)=>w.W*(X0+(X1-X0)*(yy/w.H));
  g.tip('white');
  const ey=w.H*NY, ex=edge(NY*w.H)+w.W*0.02;
  for(let k=0;k<24;k++){ g.pointer(ex-w.W*0.10+k*w.W*0.008, ey+k*1.2, true); g.advance(1000/60); }
}"""
FACTS = """()=>({job:document.getElementById('wName').textContent, pct:document.getElementById('wPct').textContent,
  tip:(document.querySelector('.tipbtn[aria-pressed="true"]')||{}).dataset.tip, pay:document.getElementById('wPay').textContent})"""


def card_html(panel_b64):
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
{font_faces(CARD_FONTS)}
*{{box-sizing:border-box;margin:0}}
html,body{{width:1200px;height:630px;overflow:hidden}}
body{{position:relative;background:{BRAND};color:#fff;font-family:'Public Sans',system-ui,sans-serif;-webkit-font-smoothing:antialiased}}
.bg{{position:absolute;inset:0;background:
  radial-gradient(640px 480px at 76% 52%, rgba(255,255,255,.18), rgba(255,255,255,0) 70%),
  linear-gradient(135deg,#B923C8 0%,#A21CAF 42%,#5E1068 100%)}}
.left{{position:absolute;left:64px;top:0;bottom:0;width:540px;display:flex;flex-direction:column;justify-content:center;gap:22px}}
.left svg{{width:92px;height:92px;flex:none;margin-bottom:-4px}}
.left h1{{font:800 108px/0.92 'Big Shoulders Display','Arial Narrow',Arial,sans-serif;letter-spacing:.02em;text-transform:uppercase;white-space:nowrap}}
.tag{{font:700 37px/1.22 'Public Sans',system-ui,sans-serif;max-width:480px;text-wrap:balance;color:#FCEBFF}}
.pill{{align-self:flex-start;background:#fff;color:#6A0F75;font:800 20px/1 'Public Sans',system-ui,sans-serif;letter-spacing:.09em;text-transform:uppercase;padding:15px 25px;border-radius:999px;margin-top:4px}}
.panel{{position:absolute;right:42px;top:50%;width:520px;transform:translateY(-50%) rotate(-2deg);border-radius:20px;border:5px solid rgba(255,255,255,.96);box-shadow:0 24px 40px rgba(30,0,40,.5);display:block}}
</style></head><body>
<div class="bg"></div>
<div class="left">
  {MARK}
  <h1>Grime Time</h1>
  <p class="tag">Blast the grime. Build the business.</p>
  <span class="pill">Free pressure washing game</span>
</div>
<img class="panel" alt="" src="data:image/png;base64,{panel_b64}">
</body></html>"""


def icon_html():
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
*{{margin:0}}
html,body{{width:180px;height:180px;overflow:hidden}}
body{{background:linear-gradient(135deg,#B923C8,{BRAND} 50%,#7A1486);display:grid;place-items:center}}
svg{{width:152px;height:152px}}
</style></head><body>{MARK}</body></html>"""


MIN_SPARKLE_PIXELS = 400      # below this the picture is refused
GOOD_SPARKLE_PIXELS = 3000    # a take at or above this is used at once
TAKES = 8                     # at most this many takes (single takes ranged from about 1400 to 3500)


def take_panel(browser, port):
    """One take of the mid wash scene on the built page: (png bytes, facts read from the page, near white pixel count)."""
    ctx = browser.new_context(viewport={'width': PANEL_VIEWPORT[0], 'height': PANEL_VIEWPORT[1]}, device_scale_factor=2, color_scheme='light')
    try:
        pg = ctx.new_page()
        pg.goto(f'http://127.0.0.1:{port}/grime-time/#test')
        pg.wait_for_timeout(500)
        pg.evaluate('document.fonts.ready')
        pg.evaluate(STATE)
        pg.evaluate('(j)=>window.__grime.start(j)', JOB)
        pg.wait_for_timeout(600)
        pg.evaluate(WASH_A)
        pg.wait_for_timeout(1300)
        pg.evaluate(WASH_B)
        facts = pg.evaluate(FACTS)
        png = pg.screenshot(clip={'x': 0, 'y': 0, 'width': PANEL_VIEWPORT[0], 'height': PANEL_VIEWPORT[1]})
    finally:
        ctx.close()
    return png, facts, bright_pixels(png)


def bright_pixels(png_bytes):
    """Near white pixels in the middle of the panel (the sparkle stars and the white spray core around the nozzle)."""
    im = Image.open(io.BytesIO(png_bytes)).convert('RGB')
    w, h = im.size
    box = im.crop((int(w * 0.35), int(h * 0.25), int(w * 0.75), int(h * 0.72)))
    r, g, b = box.split()
    lowest = ImageChops.darker(ImageChops.darker(r, g), b)
    return sum(lowest.histogram()[248:])


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

        # 1. The game, mid wash, through its own test hooks. Same state every run, so the scene is repeatable. The sparkles and droplets are random,
        #    so up to TAKES shots are made and the one with the most sparkle is kept (stop early at GOOD_SPARKLE_PIXELS).
        best = None
        for k in range(TAKES):
            panel_png, facts, n_bright = take_panel(browser, port)
            print(f'take {k + 1}: facts {facts} | bright sparkle pixels {n_bright}')
            pct = int(re.search(r'\d+', facts['pct']).group(0))
            if facts['job'] != 'Garden Patio' or facts['tip'] != 'white' or not 40 <= pct <= 60:
                raise SystemExit(f'the scene is not what OG_ALT in build_grime.py describes: {facts}')
            if best is None or n_bright > best[2]:
                best = (panel_png, facts, n_bright)
            if n_bright >= GOOD_SPARKLE_PIXELS:
                break
        panel_png, facts, n_bright = best
        (HERE / 'panel-og-grime.png').write_bytes(panel_png)
        print('kept the take with', n_bright, 'bright sparkle pixels')
        if n_bright < MIN_SPARKLE_PIXELS:
            raise SystemExit(f'the panel has too few sparkles ({n_bright} < {MIN_SPARKLE_PIXELS}): run the script again')

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
    print('site/grime-time holds exactly:', ', '.join(sorted(p.name for p in OUT.iterdir())))


if __name__ == '__main__':
    main()
