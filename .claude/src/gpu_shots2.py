import os
import functools, http.server, threading, json
from playwright.sync_api import sync_playwright
D = os.path.dirname(os.path.abspath(__file__))
class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Q, directory=D + '/site'))
port = httpd.server_address[1]
threading.Thread(target=httpd.serve_forever, daemon=True).start()
state = {'v': 1, 'card': 'RX 9070 XT', 'ask': 380, 'typ': 640, 'a': {'platform': 'site', 'pay': 'app', 'feedback': 'few', 'domain': 'young'}, 'extras': [], 'saved': []}
with sync_playwright() as p:
    try: b = p.chromium.launch()
    except Exception: b = p.chromium.launch(executable_path='/opt/pw-browsers/chromium-1194/chrome-linux/chrome')
    for scheme, w, tag in (('light', 390, 'phone'), ('dark', 1100, 'desk')):
        ctx = b.new_context(viewport={'width': w, 'height': 844}, color_scheme=scheme, device_scale_factor=2)
        ctx.add_init_script("try{localStorage.setItem('gpu-check-v1', %s)}catch(e){}" % json.dumps(json.dumps(state)))
        pg = ctx.new_page()
        pg.goto('http://127.0.0.1:%d/gpu-check/' % port)
        pg.wait_for_timeout(500)
        pg.evaluate('document.fonts.ready')
        # links block
        el = pg.locator('#links').first
        el.scroll_into_view_if_needed()
        box = el.bounding_box()
        sy = pg.evaluate('window.scrollY')
        pg.screenshot(path=D + '/gpu-links-%s.png' % tag, clip={'x': 0, 'y': max(0, box['y'] + sy - 90), 'width': w, 'height': min(box['height'] + 160, 700)}, full_page=True)
        # listing + website sections
        sec = pg.locator('#qs-listing').first
        pg.evaluate("document.getElementById('h-listing').scrollIntoView()")
        pg.wait_for_timeout(100)
        pg.screenshot(path=D + '/gpu-site-order-%s.png' % tag, full_page=False)
        ctx.close()
    b.close()
print('ok')
