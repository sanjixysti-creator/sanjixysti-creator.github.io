import functools, http.server, threading, os, json
from playwright.sync_api import sync_playwright
D = os.path.dirname(os.path.abspath(__file__))
class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Q, directory=D + '/site'))
port = httpd.server_address[1]
threading.Thread(target=httpd.serve_forever, daemon=True).start()
JS = '''() => {
  const out = [];
  document.querySelectorAll('input, select, textarea').forEach(el => {
    if (el.type === 'hidden' || el.type === 'checkbox' || el.type === 'radio') return;
    const fs = parseFloat(getComputedStyle(el).fontSize);
    out.push([el.tagName + '#' + (el.id || el.className || el.type), fs]);
  });
  return out;
}'''
with sync_playwright() as p:
    try:
        b = p.chromium.launch()
    except Exception:
        b = p.chromium.launch(executable_path='/opt/pw-browsers/chromium-1194/chrome-linux/chrome')
    ctx = b.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=1)
    pg = ctx.new_page()
    pg.goto('http://127.0.0.1:%d/rinse-quote/' % port)
    pg.wait_for_timeout(300)
    # open the details and the pro code form so hidden controls are measured too
    pg.evaluate("document.getElementById('rates').open = true")
    pg.evaluate("document.getElementById('codeForm').hidden = false")
    pg.evaluate("document.getElementById('restoreBox') && (document.getElementById('restoreBox').hidden = false)")
    res = pg.evaluate(JS)
    small = [r for r in res if r[1] < 16]
    print('controls checked:', len(res), '| below 16px:', small)
    b.close()
httpd.shutdown()
