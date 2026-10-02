import os
import functools, http.server, threading, re, sys
from playwright.sync_api import sync_playwright
D = os.path.dirname(os.path.abspath(__file__))
src = open(D + '/gpu-check.html', encoding='utf-8').read()
skeleton = ('<!doctype html><html><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            '<style>:root{color-scheme:light;padding-block:env(safe-area-inset-top,0px) env(safe-area-inset-bottom,0px)}'
            'body{margin:0;font:14px system-ui,sans-serif;background:#fafafa}img{max-width:100%}[hidden]{display:none!important}</style>'
            '</head><body>' + src + '</body></html>')
open(D + '/gpu-test.html', 'w', encoding='utf-8').write(skeleton)
class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Q, directory=D))
port = httpd.server_address[1]
threading.Thread(target=httpd.serve_forever, daemon=True).start()
errs = []
with sync_playwright() as p:
    try: b = p.chromium.launch()
    except Exception: b = p.chromium.launch(executable_path='/opt/pw-browsers/chromium-1194/chrome-linux/chrome')
    for scheme, w, h, name in (('light', 390, 844, 'gpu-phone-empty'), ('dark', 390, 844, 'gpu-phone-empty-dark')):
        ctx = b.new_context(viewport={'width': w, 'height': h}, color_scheme=scheme, device_scale_factor=2)
        pg = ctx.new_page()
        pg.on('console', lambda m: errs.append((m.type, m.text)) if m.type in ('error', 'warning') and 'ERR_FAILED' not in m.text else None)
        pg.on('pageerror', lambda e: errs.append(('pageerror', str(e))))
        pg.route(re.compile(r'https://fonts\.(googleapis|gstatic)\.com/.*'), lambda r: r.abort())
        pg.goto('http://127.0.0.1:%d/gpu-test.html' % port)
        pg.wait_for_timeout(300)
        pg.screenshot(path=D + '/' + name + '.png', full_page=False)
        if scheme == 'light':
            pg.screenshot(path=D + '/gpu-phone-full.png', full_page=True)
        ctx.close()
    b.close()
print('errors:', errs)
