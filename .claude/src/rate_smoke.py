import functools, http.server, os, re, threading, sys
from playwright.sync_api import sync_playwright

D = os.path.dirname(os.path.abspath(__file__))
src = open(D + '/rinse-rate.html', encoding='utf-8').read()
skeleton = ('<!doctype html><html><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            '<style>:root{color-scheme:light;padding-block:env(safe-area-inset-top,0px) env(safe-area-inset-bottom,0px)}'
            'body{margin:0;font:14px system-ui,sans-serif;background:#fafafa}img{max-width:100%}[hidden]{display:none!important}</style>'
            '</head><body>' + src + '</body></html>')
open(D + '/rate-test.html', 'w', encoding='utf-8').write(skeleton)

class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=D))
PORT = httpd.server_address[1]
threading.Thread(target=httpd.serve_forever, daemon=True).start()
URL = 'http://127.0.0.1:%d/rate-test.html' % PORT

with sync_playwright() as p:
    b = p.chromium.launch()
    errs = []
    for scheme in ('light', 'dark'):
        for w, h in ((390, 844), (1280, 900)):
            ctx = b.new_context(viewport={'width': w, 'height': h}, color_scheme=scheme, device_scale_factor=1)
            pg = ctx.new_page()
            pg.on('console', lambda m: errs.append(('console', m.type, m.text)) if m.type in ('error', 'warning') else None)
            pg.on('pageerror', lambda e: errs.append(('pageerror', str(e))))
            pg.goto(URL)
            pg.wait_for_timeout(500)
            if scheme == 'light' and w == 390:
                for i in ('payNum', 'paySub', 'verdict', 'needText', 'vPrice', 'vProfit', 'vMargin', 'vHours', 'hoursNote', 'payAlert'):
                    el = pg.query_selector('#' + i)
                    print(i, '=>', repr(el.inner_text()) if el else None)
                print('gauge state', pg.get_attribute('#payCard', 'data-state'), pg.get_attribute('#gauge', 'data-f'))
            pg.screenshot(path=D + '/rate_%s_%d.png' % (scheme, w), full_page=True)
            ctx.close()
    b.close()
print('errors:', errs)
