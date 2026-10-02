import functools, http.server, threading, os
from playwright.sync_api import sync_playwright
D = os.path.dirname(os.path.abspath(__file__))
class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Q, directory=D + '/site'))
port = httpd.server_address[1]
threading.Thread(target=httpd.serve_forever, daemon=True).start()
with sync_playwright() as p:
    try:
        b = p.chromium.launch()
    except Exception:
        b = p.chromium.launch(executable_path='/opt/pw-browsers/chromium-1194/chrome-linux/chrome')
    ctx = b.new_context(viewport={'width': 1200, 'height': 900}, device_scale_factor=2, color_scheme='light')
    pg = ctx.new_page()
    pg.goto('http://127.0.0.1:%d/rinse-quote/' % port)
    pg.wait_for_timeout(400)
    pg.evaluate('document.fonts.ready')
    pg.locator('#ticket').screenshot(path=D + '/ticket-raw.png')
    pg.screenshot(path=D + '/site-desktop.png')
    box = pg.locator('#ticket').bounding_box()
    print('ticket box', box)
    b.close()
httpd.shutdown()
