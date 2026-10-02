import functools, http.server, threading, os, sys
from playwright.sync_api import sync_playwright
D = os.path.dirname(os.path.abspath(__file__))
class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Q, directory=D))
port = httpd.server_address[1]
threading.Thread(target=httpd.serve_forever, daemon=True).start()
with sync_playwright() as p:
    try:
        b = p.chromium.launch()
    except Exception:
        b = p.chromium.launch(executable_path='/opt/pw-browsers/chromium-1194/chrome-linux/chrome')
    for scheme in ('light', 'dark'):
        ctx = b.new_context(viewport={'width': 390, 'height': 844}, color_scheme=scheme, device_scale_factor=2)
        pg = ctx.new_page()
        pg.route('https://fonts.googleapis.com/**', lambda r: r.abort())
        pg.route('https://fonts.gstatic.com/**', lambda r: r.abort())
        pg.goto('http://127.0.0.1:%d/rm-test.html' % port)
        pg.wait_for_timeout(250)
        pg.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
        def card(name):
            pg.locator('#mixCard').screenshot(path='%s/rm-state-%s-%s.png' % (D, name, scheme))
        # bad
        pg.fill('#shPct', '8.25'); pg.fill('#target', '10'); card('bad')
        # warn
        pg.fill('#shPct', '12.5'); pg.fill('#target', '8'); card('warn')
        # info
        pg.fill('#batch', ''); card('info')
        pg.fill('#batch', '50'); pg.fill('#target', '3')
        # everything on: cost, draw, save form
        pg.fill('#shPrice', '3.5'); pg.fill('#soapPrice', '30'); pg.fill('#draw', '10')
        pg.locator('#saveBtn').evaluate('e => e.click()')
        card('full')
        ctx.close()
    b.close()
httpd.shutdown()
print('done')
