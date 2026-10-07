import functools, http.server, os, re, sys, threading
from playwright.sync_api import sync_playwright

D = os.path.dirname(os.path.abspath(__file__))
SERVE = D + '/site'


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=SERVE))
PORT = httpd.server_address[1]
threading.Thread(target=httpd.serve_forever, daemon=True).start()
URL = 'http://127.0.0.1:%d/qr-forever/#test' % PORT


def launch(p):
    try:
        return p.chromium.launch()
    except Exception:
        return p.chromium.launch(executable_path='/opt/pw-browsers/chromium-1194/chrome-linux/chrome')


errs = []
with sync_playwright() as p:
    b = launch(p)
    plan = [('phone-light', 390, 844, 'light'), ('phone-dark', 390, 844, 'dark'), ('desk-light', 1280, 900, 'light'), ('desk-dark', 1280, 900, 'dark'), ('tiny-light', 320, 640, 'light')]
    only = sys.argv[1:] 
    for name, w, h, scheme in plan:
        if only and name not in only:
            continue
        ctx = b.new_context(viewport={'width': w, 'height': h}, color_scheme=scheme, device_scale_factor=1)
        pg = ctx.new_page()
        pg.on('console', lambda m: errs.append((m.type, m.text)) if m.type in ('error', 'warning') else None)
        pg.on('pageerror', lambda e: errs.append(('pageerror', str(e))))
        pg.route(re.compile(r'https://fonts\.(googleapis|gstatic)\.com/.*'), lambda r: r.abort())
        pg.goto(URL)
        pg.wait_for_timeout(400)
        pg.screenshot(path='%s/shots/%s-1-empty.png' % (D, name), full_page=(w < 900))
        pg.screenshot(path='%s/shots/%s-0-first.png' % (D, name))
        pg.fill('#f-url', 'example.com/menu')
        pg.wait_for_timeout(200)
        pg.screenshot(path='%s/shots/%s-0b-typed.png' % (D, name))
        pg.evaluate("document.getElementById('codeCard').scrollIntoView()")
        pg.wait_for_timeout(150)
        pg.screenshot(path='%s/shots/%s-0c-code.png' % (D, name))
        pg.evaluate("window.scrollTo(0, 0)")
        pg.screenshot(path='%s/shots/%s-2-link.png' % (D, name), full_page=(w < 900))
        pg.click('#tab-wifi')
        pg.fill('#f-ssid', 'Home Network')
        pg.fill('#f-password', 'correct horse battery')
        pg.wait_for_timeout(200)
        pg.screenshot(path='%s/shots/%s-3-wifi.png' % (D, name), full_page=(w < 900))
        ctx.close()
    b.close()
print('errors:', errs)
