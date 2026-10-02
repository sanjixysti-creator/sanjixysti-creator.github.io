import functools, http.server, os, threading
from playwright.sync_api import sync_playwright
D = os.path.dirname(os.path.abspath(__file__))
SERVE = D + '/site'
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=SERVE))
threading.Thread(target=httpd.serve_forever, daemon=True).start()
URL = 'http://127.0.0.1:%d/rinse-rate/' % httpd.server_address[1]
with sync_playwright() as p:
    b = p.chromium.launch()
    for w, scheme in ((320, 'light'), (360, 'light'), (320, 'dark')):
        ctx = b.new_context(viewport={'width': w, 'height': 760}, color_scheme=scheme, device_scale_factor=2)
        pg = ctx.new_page()
        pg.goto(URL)
        pg.wait_for_timeout(400)
        pg.screenshot(path=D + '/s_%d_%s_top.png' % (w, scheme))
        pg.evaluate('window.scrollTo(0, 560)')
        pg.wait_for_timeout(100)
        pg.screenshot(path=D + '/s_%d_%s_mid.png' % (w, scheme))
        ctx.close()
    b.close()
