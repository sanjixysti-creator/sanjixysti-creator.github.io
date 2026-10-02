import functools, http.server, threading, os
from playwright.sync_api import sync_playwright
ROOT = os.environ.get('SITE_REPO', '/home/claude/sanjixysti-creator.github.io')
D = os.path.dirname(os.path.abspath(__file__))
class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Q, directory=ROOT))
port = httpd.server_address[1]
threading.Thread(target=httpd.serve_forever, daemon=True).start()
base = 'http://127.0.0.1:%d/' % port
fails, passes = [], 0
def eq(n, g, w):
    global passes
    if g == w: passes += 1
    else: fails.append('%s\n   got:  %r\n   want: %r' % (n, g, w))
with sync_playwright() as p:
    try: b = p.chromium.launch()
    except Exception: b = p.chromium.launch(executable_path='/opt/pw-browsers/chromium-1194/chrome-linux/chrome')
    ctx = b.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=1)
    pg = ctx.new_page()
    errs = []
    pg.on('console', lambda m: errs.append(m.text) if m.type in ('error', 'warning') else None)
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.route('**/favicon.ico', lambda r: r.fulfill(status=204, body=''))
    pg.goto(base); pg.wait_for_timeout(300)
    eq('title unchanged', pg.title(), 'Tuner for YouTube - make YouTube yours')
    eq('more section visible', pg.is_visible('.more'), True)
    eq('heading', (pg.text_content('.more h2') or '').strip(), 'More from Xysti Software')
    eq('card hrefs', pg.eval_on_selector_all('.more a.card.link', 'els => els.map(e => e.getAttribute("href"))'), ['rinse-quote/', 'rinse-mix/', 'gpu-check/'])
    eq('card titles', pg.eval_on_selector_all('.more a.card.link h3', 'els => els.map(e => e.textContent.trim())'), ['Rinse Quote', 'Rinse Mix', 'Used GPU Check'])
    eq('card buttons', pg.eval_on_selector_all('.more a.card.link .go', 'els => els.map(e => e.textContent.trim())'), ['Open Rinse Quote', 'Open Rinse Mix', 'Open Used GPU Check'])
    eq('cards have no em dash', pg.evaluate("/[\u2014\u2013]/.test(document.querySelector('.more').textContent)"), False)
    eq('cards are at least 44px tall', pg.evaluate("Math.min(...[...document.querySelectorAll('.more a.card.link')].map(a => a.getBoundingClientRect().height)) >= 44"), True)
    eq('original sections intact', [pg.locator(s).count() for s in ('.hero', '.features', '.pricing', 'footer')], [1, 1, 1, 1])
    eq('feature cards intact', pg.locator('.features .card').count(), 6)
    eq('pricing cards intact', pg.locator('.pricing .card').count(), 2)
    for w in (320, 390, 768, 1200):
        pg.set_viewport_size({'width': w, 'height': 900}); pg.wait_for_timeout(100)
        sw, cw = pg.evaluate('[document.documentElement.scrollWidth, document.documentElement.clientWidth]')
        eq('no sideways scroll at %d' % w, sw <= cw, True)
    pg.set_viewport_size({'width': 390, 'height': 844}); pg.wait_for_timeout(100)
    pg.locator('.more').scroll_into_view_if_needed()
    pg.screenshot(path=D + '/tuner-phone-full.png', full_page=True)
    pg.set_viewport_size({'width': 1200, 'height': 900}); pg.wait_for_timeout(100)
    pg.screenshot(path=D + '/tuner-desktop-full.png', full_page=True)
    pg.set_viewport_size({'width': 390, 'height': 844})
    dests = [('/rinse-quote/', 'Rinse Quote: Free Pressure Washing Quote Calculator'),
             ('/rinse-mix/', 'Rinse Mix: Free Soft Wash Mix Calculator'),
             ('/gpu-check/', 'Used GPU Check: Free Risk and Price Checker')]
    for i, (path, title) in enumerate(dests):
        pg.goto(base); pg.wait_for_timeout(200)
        pg.locator('.more a.card.link').nth(i).click(); pg.wait_for_load_state('load'); pg.wait_for_timeout(500)
        eq('card %d opens %s' % (i, path), (pg.url.endswith(path), pg.title()), (True, title))
        for asset in ('og.png', 'apple-touch-icon.png', 'privacy.html'):
            r = pg.request.get(base.rstrip('/') + path + asset)
            eq('%s%s is served' % (path, asset), r.status, 200)
        pg.set_viewport_size({'width': 390, 'height': 844}); pg.wait_for_timeout(100)
        sw, cw = pg.evaluate('[document.documentElement.scrollWidth, document.documentElement.clientWidth]')
        eq('%s has no sideways scroll on a phone' % path, sw <= cw, True)
    eq('no console errors', errs, [])
    b.close()
httpd.shutdown()
print('TUNER passed', passes, 'failed', len(fails))
for f in fails: print('FAIL', f)
