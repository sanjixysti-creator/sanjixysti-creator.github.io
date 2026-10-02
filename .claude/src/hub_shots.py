import os
import functools, http.server, threading
from playwright.sync_api import sync_playwright
ROOT = os.environ.get('SITE_REPO', '/home/claude/sanjixysti-creator.github.io')
D = os.path.dirname(os.path.abspath(__file__))
class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Q, directory=ROOT))
port = httpd.server_address[1]
threading.Thread(target=httpd.serve_forever, daemon=True).start()
errs = []
with sync_playwright() as p:
    try: b = p.chromium.launch()
    except Exception: b = p.chromium.launch(executable_path='/opt/pw-browsers/chromium-1194/chrome-linux/chrome')
    for scheme, w, h, name in (('light', 390, 844, 'hub-phone-light'), ('dark', 390, 844, 'hub-phone-dark'), ('light', 1200, 900, 'hub-desk-light'), ('dark', 1200, 900, 'hub-desk-dark')):
        ctx = b.new_context(viewport={'width': w, 'height': h}, color_scheme=scheme, device_scale_factor=2 if w < 500 else 1)
        pg = ctx.new_page()
        pg.on('console', lambda m: errs.append((m.type, m.text)) if m.type in ('error', 'warning') else None)
        pg.on('pageerror', lambda e: errs.append(('pageerror', str(e))))
        pg.route('**/favicon.ico', lambda r: r.fulfill(status=204, body=''))
        pg.goto('http://127.0.0.1:%d/' % port)
        pg.wait_for_timeout(400)
        pg.screenshot(path=D + '/%s.png' % name, full_page=True)
        ctx.close()
    b.close()
print('errors:', errs)
