#!/usr/bin/env python3
"""Checks for the site root (hub), the Tuner page at /tuner/, and what must stay untouched.

Serves the repo working tree locally. Requests to the live address are answered from the same files, so
absolute links in meta tags (share image, canonical) can be tested before anything is pushed.
"""
import os
import functools
import hashlib
import http.server
import mimetypes
import pathlib
import re
import subprocess
import threading

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(os.environ.get('SITE_REPO', '/home/claude/sanjixysti-creator.github.io'))
D = pathlib.Path(__file__).resolve().parent
LIVE = 'https://sanjixysti-creator.github.io/'


class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Q, directory=str(ROOT)))
port = httpd.server_address[1]
threading.Thread(target=httpd.serve_forever, daemon=True).start()
BASE = 'http://127.0.0.1:%d/' % port

fails, passes = [], 0


def eq(name, got, want):
    global passes
    if got == want:
        passes += 1
    else:
        fails.append('%s\n    got:  %r\n    want: %r' % (name, got, want))


def sha(b):
    return hashlib.sha256(b).hexdigest()


def lum(rgb):
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def ratio(a, b):
    la, lb = lum(a), lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def parse(c):
    m = re.match(r'rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\)', c)
    if not m:
        return None
    return (float(m.group(1)), float(m.group(2)), float(m.group(3)))


AUDIT_JS = '''() => {
  const out = [];
  const bgOf = el => {
    for (let e = el; e; e = e.parentElement) {
      const c = getComputedStyle(e).backgroundColor;
      const m = c.match(/rgba?\\(([^)]+)\\)/);
      if (m) { const p = m[1].split(',').map(s => parseFloat(s)); if (p.length < 4 || p[3] === 1) return c; }
    }
    return 'rgb(255, 255, 255)';
  };
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const seen = new Set();
  while (walker.nextNode()) {
    const n = walker.currentNode;
    if (!n.textContent.trim()) continue;
    const el = n.parentElement;
    if (seen.has(el)) continue;
    seen.add(el);
    const r = el.getBoundingClientRect();
    if (r.width <= 2 || r.height <= 2) continue;
    const cs = getComputedStyle(el);
    out.push({ t: n.textContent.trim().slice(0, 36), color: cs.color, bg: bgOf(el), size: parseFloat(cs.fontSize), weight: parseInt(cs.fontWeight, 10) });
  }
  return out;
}'''

OVERFLOW_JS = '''() => {
  const W = document.documentElement.clientWidth;
  const bad = [];
  document.querySelectorAll('body *').forEach(el => {
    if (el.closest('.sr-only')) return;
    const r = el.getBoundingClientRect();
    if (r.width && (r.right > W + 1 || r.left < -1)) bad.push(el.tagName + '.' + el.className + ' ' + Math.round(r.left) + '..' + Math.round(r.right));
  });
  return [document.documentElement.scrollWidth <= W, bad.slice(0, 5)];
}'''

TITLES = {
    'rinse-quote/': 'Rinse Quote: Free Pressure Washing Quote Calculator',
    'rinse-mix/': 'Rinse Mix: Free Soft Wash Mix Calculator',
    'gpu-check/': 'Used GPU Check: Free Risk and Price Checker',
    'tuner/': 'Tuner for YouTube - make YouTube yours',
}


def route_live(route):
    path = route.request.url[len(LIVE):].split('?')[0].split('#')[0] or 'index.html'
    f = ROOT / path
    if f.is_dir():
        f = f / 'index.html'
    if not f.exists():
        route.fulfill(status=404, body='not found')
        return
    route.fulfill(status=200, body=f.read_bytes(), content_type=mimetypes.guess_type(str(f))[0] or 'application/octet-stream')


with sync_playwright() as p:
    try:
        b = p.chromium.launch()
    except Exception:
        b = p.chromium.launch(executable_path='/opt/pw-browsers/chromium-1194/chrome-linux/chrome')
    errs, foreign = [], []

    def new(path='', scheme='light', w=390, h=844, reduced=False):
        ctx = b.new_context(viewport={'width': w, 'height': h}, color_scheme=scheme, device_scale_factor=1,
                            reduced_motion='reduce' if reduced else 'no-preference')
        pg = ctx.new_page()
        pg.set_default_timeout(5000)
        pg.on('console', lambda m: errs.append((path, m.text)) if m.type in ('error', 'warning') else None)
        pg.on('pageerror', lambda e: errs.append((path, str(e))))
        pg.on('request', lambda r: foreign.append(r.url) if not r.url.startswith((BASE, LIVE, 'data:', 'blob:')) else None)
        pg.route('**/favicon.ico', lambda r: r.fulfill(status=204, body=''))
        pg.route(LIVE + '**', route_live)
        pg.goto(BASE + path)
        pg.wait_for_timeout(300)
        return ctx, pg

    # ------------------------------------------------------------------ files that must not change
    eq('privacy.html is byte for byte what the store listing points at',
       sha((ROOT / 'privacy.html').read_bytes()), sha(subprocess.check_output(['git', '-C', str(ROOT), 'show', 'HEAD:privacy.html'])))
    changed = subprocess.check_output(['git', '-C', str(ROOT), 'status', '--porcelain', 'rinse-quote', 'rinse-mix', 'gpu-check']).decode().strip()
    eq('the three tools are untouched', changed, '')
    for rel in ('index.html', 'tuner/index.html'):
        txt = (ROOT / rel).read_text(encoding='utf-8')
        eq('%s has no em or en dash' % rel, bool(re.search('[\u2014\u2013]', txt)), False)
    hub_src = (ROOT / 'index.html').read_text(encoding='utf-8')
    eq('hub has no script', '<script' in hub_src, False)
    eq('hub makes no outside link or request',
       sorted(set(re.findall(r'(?:src|href)="(https?://[^"]+)"', hub_src))), [LIVE])
    eq('og.png is 1200x630', Image.open(ROOT / 'og.png').size, (1200, 630))
    eq('apple-touch-icon.png is 180x180', Image.open(ROOT / 'apple-touch-icon.png').size, (180, 180))
    eq('og.png stays small enough to share', (ROOT / 'og.png').stat().st_size < 400_000, True)

    # ------------------------------------------------------------------ hub, structure
    ctx, pg = new('')
    eq('hub title', pg.title(), 'Xysti Software: Small Free Tools for Specific Jobs')
    desc = pg.get_attribute('meta[name=description]', 'content')
    eq('hub description length', 61 <= len(desc) <= 160, True)
    eq('hub canonical', pg.get_attribute('link[rel=canonical]', 'href'), LIVE)
    eq('hub og url', pg.get_attribute('meta[property="og:url"]', 'content'), LIVE)
    eq('hub og image', pg.get_attribute('meta[property="og:image"]', 'content'), LIVE + 'og.png')
    eq('hub twitter card', pg.get_attribute('meta[name="twitter:card"]', 'content'), 'summary_large_image')
    eq('hub theme colors', pg.eval_on_selector_all('meta[name=theme-color]', 'els => els.map(e => e.content)'), ['#E5E9EB', '#11171B'])
    eq('hub lang', pg.get_attribute('html', 'lang'), 'en')
    eq('hub landmarks', [pg.locator(s).count() for s in ('header', 'main', 'footer', 'footer nav')], [1, 1, 1, 1])
    eq('one h1', pg.eval_on_selector_all('h1', 'els => els.map(e => e.textContent.trim())'), ['Small tools for specific jobs.'])
    eq('four tools in order', pg.eval_on_selector_all('.row h3 a', 'els => els.map(e => e.textContent.trim())'),
       ['Rinse Quote', 'Rinse Mix', 'Used GPU Check', 'Tuner for YouTube'])
    eq('tool links', pg.eval_on_selector_all('.row h3 a', 'els => els.map(e => e.getAttribute("href"))'),
       ['rinse-quote/', 'rinse-mix/', 'gpu-check/', 'tuner/'])
    eq('tool kinds', pg.eval_on_selector_all('.row .meta .type', 'els => els.map(e => e.textContent.trim())'),
       ['Web app', 'Web app', 'Web app', 'Chrome extension'])
    eq('icons are hidden from screen readers', pg.evaluate("[...document.querySelectorAll('svg')].every(s => s.getAttribute('aria-hidden') === 'true')"), True)
    eq('mail link', pg.get_attribute('.mailto', 'href'), 'mailto:fireseabrook2566@gmail.com')
    eq('privacy links', pg.eval_on_selector_all('.priv a', 'els => els.map(e => e.getAttribute("href"))'),
       ['rinse-quote/privacy.html', 'rinse-mix/privacy.html', 'gpu-check/privacy.html', 'privacy.html'])
    for href in ('rinse-quote/privacy.html', 'rinse-mix/privacy.html', 'gpu-check/privacy.html', 'privacy.html'):
        r = pg.request.get(BASE + href)
        eq('%s is served' % href, r.status, 200)
    for asset in ('og.png', 'apple-touch-icon.png'):
        eq('%s is served' % asset, pg.request.get(BASE + asset).status, 200)
    og = pg.evaluate('''() => new Promise(res => { const i = new Image(); i.onload = () => res([i.naturalWidth, i.naturalHeight]); i.onerror = () => res(null); i.src = document.querySelector('meta[property="og:image"]').content; })''')
    eq('og image loads from its absolute address', og, [1200, 630])
    faces = pg.evaluate('''async () => { const o = []; for (const f of [...document.fonts]) { try { await f.load(); o.push(f.family.replace(/"/g, '') + ' ' + f.weight + ' ' + f.status); } catch (e) { o.push('ERR'); } } return o.sort(); }''')
    eq('three fonts embedded and loaded', faces, ['Big Shoulders Display 800 loaded', 'Public Sans 400 loaded', 'Public Sans 600 loaded'])
    eq('no running animations', pg.evaluate('document.getAnimations().length'), 0)
    ctx.close()

    # ------------------------------------------------------------------ hub, layout and touch
    ctx, pg = new('')
    for w in (320, 360, 390, 414, 768, 1024, 1440):
        pg.set_viewport_size({'width': w, 'height': 900})
        pg.wait_for_timeout(100)
        ok, bad = pg.evaluate(OVERFLOW_JS)
        eq('hub has no sideways scroll at %d' % w, (ok, bad), (True, []))
    pg.set_viewport_size({'width': 390, 'height': 844})
    pg.wait_for_timeout(100)
    for i in range(4):
        hit = pg.evaluate('''(i) => {
          const row = document.querySelectorAll('.row')[i];
          const link = row.querySelector('h3 a');
          const r = row.getBoundingClientRect();
          row.scrollIntoView({block: 'center'});
          const r2 = row.getBoundingClientRect();
          const pts = [[r2.left + 8, r2.top + 8], [r2.left + r2.width / 2, r2.top + r2.height / 2], [r2.right - 8, r2.bottom - 8], [r2.left + 40, r2.bottom - 8]];
          return pts.map(([x, y]) => { const e = document.elementFromPoint(x, y); return !!e && e.closest('a') === link; });
        }''', i)
        eq('row %d is one big tap target' % i, hit, [True, True, True, True])
    small = pg.evaluate('''() => [...document.querySelectorAll('a')].filter(a => a.getClientRects().length).map(a => [a.textContent.trim(), Math.round(a.getBoundingClientRect().height)]).filter(x => x[1] < 40 && !x[0].match(/^(Rinse Quote|Rinse Mix|Used GPU Check|Tuner for YouTube)$/) || false)''')
    eq('footer links are at least 40px tall', small, [])
    row_h = pg.evaluate("Math.min(...[...document.querySelectorAll('.row')].map(r => r.getBoundingClientRect().height))")
    eq('rows are at least 100px tall', row_h >= 100, True)
    # the first screen already shows the first tool on a phone
    eq('first tool is visible without scrolling on a phone', pg.evaluate("document.querySelector('.row h3 a').getBoundingClientRect().bottom < innerHeight"), True)
    ctx.close()

    # ------------------------------------------------------------------ hub, keyboard and hover
    ctx, pg = new('', w=1200, h=900)
    order = []
    for _ in range(9):
        pg.keyboard.press('Tab')
        order.append(pg.evaluate("document.activeElement.getAttribute('href')"))
        if len(order) == 1:
            outline = pg.evaluate("(a => { const s = getComputedStyle(a, '::after'); return [s.outlineStyle, s.outlineWidth]; })(document.activeElement)")
            eq('focus ring is a solid 3px outline', outline, ['solid', '3px'])
    eq('tab order', order, ['rinse-quote/', 'rinse-mix/', 'gpu-check/', 'tuner/', 'mailto:fireseabrook2566@gmail.com',
                            'rinse-quote/privacy.html', 'rinse-mix/privacy.html', 'gpu-check/privacy.html', 'privacy.html'])
    pg.mouse.move(5, 5)
    before = pg.evaluate("getComputedStyle(document.querySelectorAll('.row')[1]).backgroundColor")
    mb = pg.locator('.row:nth-child(2) .meta').bounding_box()
    pg.mouse.move(mb['x'] + 6, mb['y'] + 6)
    after = pg.evaluate("getComputedStyle(document.querySelectorAll('.row')[1]).backgroundColor")
    eq('rows start with no fill', before, 'rgba(0, 0, 0, 0)')
    eq('hovering a row tints it', after != 'rgba(0, 0, 0, 0)', True)
    ctx.close()

    # ------------------------------------------------------------------ hub, contrast in both color schemes
    for scheme, ground in (('light', (229, 233, 235)), ('dark', (17, 23, 27))):
        for w in (390, 1200):
            ctx, pg = new('', scheme=scheme, w=w)
            eq('hub ground (%s)' % scheme, parse(pg.evaluate("getComputedStyle(document.body).backgroundColor")), tuple(float(v) for v in ground))
            bad = []
            for item in pg.evaluate(AUDIT_JS):
                fg, bg = parse(item['color']), parse(item['bg'])
                need = 3.0 if (item['size'] >= 24 or (item['size'] >= 18.66 and item['weight'] >= 700)) else 4.5
                got = ratio(fg, bg)
                if got < need:
                    bad.append((item['t'], round(got, 2), need))
            eq('every text meets contrast (%s, %d)' % (scheme, w), bad, [])
            ctx.close()

    # ------------------------------------------------------------------ hub, every link goes where it says
    for i, (href, title) in enumerate(TITLES.items()):
        ctx, pg = new('')
        pg.locator('.row h3 a').nth(i).click()
        pg.wait_for_load_state('load')
        eq('%s opens from its name' % href, (pg.url == BASE + href, pg.title()), (True, title))
        ctx.close()
        ctx, pg = new('')
        meta = pg.locator('.row .meta').nth(i)
        meta.scroll_into_view_if_needed()
        box = meta.bounding_box()
        pg.mouse.click(box['x'] + 6, box['y'] + 6)
        pg.wait_for_url(BASE + href)
        pg.wait_for_load_state('load')
        eq('%s opens from the empty part of its row' % href, (pg.url == BASE + href, pg.title()), (True, title))
        ctx.close()

    # ------------------------------------------------------------------ Tuner at /tuner/
    ctx, pg = new('tuner/')
    eq('tuner title unchanged', pg.title(), 'Tuner for YouTube - make YouTube yours')
    eq('tuner description unchanged', pg.get_attribute('meta[name=description]', 'content'),
       'Tuner is a Chrome extension that cleans up YouTube: hide Shorts, keep notes on videos, organize playlists into groups, and theme the whole site.')
    eq('tuner canonical', pg.get_attribute('link[rel=canonical]', 'href'), LIVE + 'tuner/')
    eq('tuner original sections intact', [pg.locator(s).count() for s in ('.hero', '.features', '.pricing', 'footer')], [1, 1, 1, 1])
    eq('tuner feature cards', pg.locator('.features .card').count(), 6)
    eq('tuner pricing cards', pg.locator('.pricing .card').count(), 2)
    eq('tuner no longer promotes the other tools', pg.locator('.more').count(), 0)
    eq('tuner nav', pg.eval_on_selector_all('header nav a', 'els => els.map(e => [e.textContent.trim(), e.getAttribute("href")])'),
       [['All tools', '../'], ['Privacy', '../privacy.html']])
    eq('tuner footer links', pg.eval_on_selector_all('footer a', 'els => els.map(e => [e.textContent.trim(), e.getAttribute("href")])'),
       [['Privacy policy', '../privacy.html'], ['More tools by Xysti Software', '../']])
    eq('tuner mentions the free tools nowhere', 'Rinse' in pg.text_content('body'), False)
    eq('tuner install button and review note kept', (pg.text_content('#install').strip(), 'Chrome Web Store listing in review' in pg.text_content('.cta-row')), ('Add to Chrome', True))
    for w in (320, 390, 768, 1200):
        pg.set_viewport_size({'width': w, 'height': 900})
        pg.wait_for_timeout(100)
        ok, bad = pg.evaluate(OVERFLOW_JS)
        eq('tuner has no sideways scroll at %d' % w, (ok, bad), (True, []))
    pg.set_viewport_size({'width': 390, 'height': 844})
    pg.screenshot(path=str(D / 'tuner-new-top.png'))
    pg.locator('header nav a', has_text='All tools').click()
    pg.wait_for_load_state('load')
    eq('All tools goes to the hub', (pg.url, pg.title()), (BASE, 'Xysti Software: Small Free Tools for Specific Jobs'))
    pg.goto(BASE + 'tuner/')
    pg.locator('header nav a', has_text='Privacy').click()
    pg.wait_for_load_state('load')
    eq('Privacy goes to the unchanged policy', (pg.url, pg.title()), (BASE + 'privacy.html', 'Privacy policy - Tuner for YouTube'))
    pg.goto(BASE + 'tuner/')
    pg.locator('footer a', has_text='More tools').click()
    pg.wait_for_load_state('load')
    eq('footer link goes to the hub', pg.url, BASE)
    ctx.close()

    # ------------------------------------------------------------------ the three tools still load and link back
    for href, title in list(TITLES.items())[:3]:
        ctx, pg = new(href)
        eq('%s still loads' % href, pg.title(), title)
        ctx.close()

    # ------------------------------------------------------------------ pictures for the report
    for scheme, w, h, name in (('light', 390, 844, 'hub-phone-light'), ('dark', 390, 844, 'hub-phone-dark'),
                               ('light', 1200, 900, 'hub-desk-light'), ('dark', 1200, 900, 'hub-desk-dark')):
        ctx, pg = new('', scheme=scheme, w=w, h=h)
        pg.screenshot(path=str(D / (name + '.png')), full_page=True)
        ctx.close()
    b.close()

real = [e for e in errs]
eq('no console errors on any page', real, [])
eq('nothing outside the site was requested', sorted(set(foreign)), [])
httpd.shutdown()
print('SITE passed', passes, 'failed', len(fails))
for f in fails:
    print('FAIL', f)
