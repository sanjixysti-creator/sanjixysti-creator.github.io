"""Shared pieces for the QR Forever browser tests: a local server for the built site, a page factory, small helpers and readers."""
import contextlib, functools, http.server, io, json, math, os, re, threading

import cv2
import numpy as np
import zxingcpp
from PIL import Image
from playwright.sync_api import sync_playwright

D = os.path.dirname(os.path.abspath(__file__))
STANDALONE = os.environ.get('QR_STANDALONE', D + '/site/qr-forever/index.html')
SITE_DIR = os.path.dirname(STANDALONE)
SERVE = os.path.dirname(SITE_DIR)
PAGE_PATH = '/' + os.path.basename(SITE_DIR) + '/'
SITE_URL = 'https://sanjixysti-creator.github.io/qr-forever/'
SITE_TITLE = 'QR Forever: Free QR Code Generator That Never Expires'
STORE = 'qr-forever-v1'
SUPPORT = re.search(r"var SUPPORT = '([^']*)'", open(STANDALONE, encoding='utf-8').read()).group(1)


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=SERVE))
PORT = httpd.server_address[1]
threading.Thread(target=httpd.serve_forever, daemon=True).start()
ORIGIN = 'http://127.0.0.1:%d' % PORT
URL = ORIGIN + PAGE_PATH + '#test'
URL_PLAIN = ORIGIN + PAGE_PATH

fails, passes, errs, ext_reqs = [], 0, [], []


def eq(name, got, want):
    global passes
    if got == want:
        passes += 1
    else:
        fails.append('%s\n    got:  %r\n    want: %r' % (name, got, want))


def has(name, text, needle):
    global passes
    if needle in (text or ''):
        passes += 1
    else:
        fails.append('%s\n    missing: %r\n    in: %r' % (name, needle, (text or '')[:700]))


def lacks(name, text, needle):
    global passes
    if needle not in (text or ''):
        passes += 1
    else:
        fails.append('%s\n    should not contain: %r\n    in: %r' % (name, needle, (text or '')[:700]))


def truth(name, cond, detail=''):
    global passes
    if cond:
        passes += 1
    else:
        fails.append(name + ('\n    ' + str(detail)[:700] if detail != '' else ''))


@contextlib.contextmanager
def section(name):
    try:
        yield
    except Exception as e:
        fails.append('%s\n    EXCEPTION: %s' % (name, str(e).strip().splitlines()[0][:400] if str(e).strip() else repr(e)))


# Stubs: a clipboard that records what is written, a print that records instead of opening a dialog.
STUB_OK = """
window.__copied = null; window.__clipImage = null; window.__printed = 0; window.__printHTML = '';
Object.defineProperty(navigator, 'clipboard', {configurable: true, value: {
  writeText: function (t) { window.__copied = t; return Promise.resolve(); },
  write: function (items) { window.__clipImage = items; return Promise.resolve(); }
}});
window.print = function () { window.__printed++; window.__printHTML = document.getElementById('printArea').innerHTML; };
"""
STUB_REJECT = """
window.__copied = null;
Object.defineProperty(navigator, 'clipboard', {configurable: true, value: {
  writeText: function () { return Promise.reject(new Error('blocked')); },
  write: function () { return Promise.reject(new Error('blocked')); }
}});
document.execCommand = function () { return false; };
window.print = function () { window.__printed = (window.__printed || 0) + 1; };
"""
STUB_SHARE = """
window.__shared = null;
navigator.canShare = function (d) { return !!(d && d.files && d.files.length); };
navigator.share = function (d) { window.__shared = d; return Promise.resolve(); };
"""


def launch(p):
    try:
        return p.chromium.launch()
    except Exception:
        return p.chromium.launch(executable_path='/opt/pw-browsers/chromium-1194/chrome-linux/chrome')


def new_page(browser, stub=STUB_OK, scheme='light', w=1280, h=900, pre_state=None, url=None, mobile=False, dpr=1, extra=''):
    kw = dict(viewport={'width': w, 'height': h}, color_scheme=scheme, device_scale_factor=dpr, accept_downloads=True)
    if mobile:
        kw.update(is_mobile=True, has_touch=True)
    ctx = browser.new_context(**kw)
    ctx.add_init_script(stub + extra)
    if pre_state is not None:
        ctx.add_init_script("try { if (!localStorage.getItem('%s')) localStorage.setItem('%s', %s); } catch (e) {}" % (STORE, STORE, json.dumps(json.dumps(pre_state) if not isinstance(pre_state, str) else pre_state)))
    page = ctx.new_page()
    page.set_default_timeout(5000)
    page.on('console', lambda m: errs.append((m.type, m.text)) if m.type in ('error', 'warning') and 'ERR_FAILED' not in m.text else None)
    page.on('pageerror', lambda e: errs.append(('pageerror', str(e))))
    page.on('request', lambda r: ext_reqs.append(r.url) if not (r.url.startswith(ORIGIN + '/') or r.url.startswith(('data:', 'blob:'))) else None)
    page.route('**/favicon.ico', lambda r: r.fulfill(status=204, body=''))
    page.goto(url or URL)
    page.wait_for_timeout(250)
    return ctx, page


def txt(page, sel):
    return (page.text_content(sel) or '').strip()


def tap(page, sel):
    page.locator(sel).first.evaluate('e => e.click()')


def put(page, sel, val):
    page.fill(sel, str(val))


def pick(page, type_):
    tap(page, '#tab-' + type_)


def hook(page, expr):
    return page.evaluate('(() => { const q = window.__qr; return ' + expr + '; })()')


def cur_text(page):
    return hook(page, 'q.cur().res.text')


def ready(page):
    return hook(page, 'q.cur().ok')


def status(page):
    return txt(page, '#status')


def toast(page):
    return txt(page, '#toast') if page.is_visible('#toast') else ''


def overflow(page, w, h=900):
    page.set_viewport_size({'width': w, 'height': h})
    page.wait_for_timeout(150)
    return page.evaluate('''() => {
        const W = document.documentElement.clientWidth;
        const bad = [];
        document.querySelectorAll('body *').forEach(el => {
            if (getComputedStyle(el).position === 'fixed') return;
            if (el.closest('.printarea')) return;
            const r = el.getBoundingClientRect();
            if (r.width && (r.right > W + 1 || r.left < -1)) bad.push(el.tagName + '.' + el.className + '#' + el.id);
        });
        return {sw: document.documentElement.scrollWidth, W: W, bad: bad.slice(0, 6)};
    }''')


# ---------- readers ----------
def flat(png_bytes, bg=(255, 255, 255)):
    """A PNG as a gray array, with transparency laid over a plain background."""
    im = Image.open(io.BytesIO(png_bytes)).convert('RGBA')
    base = Image.new('RGBA', im.size, bg + (255,))
    base.alpha_composite(im)
    return np.array(base.convert('L'))


def read_zx(gray):
    return zxingcpp.read_barcodes(gray)


_aruco = cv2.QRCodeDetectorAruco()


def read_cv(gray):
    """OpenCV's Aruco based reader on a gray picture, padded so a missing quiet zone does not hide the code."""
    g = cv2.copyMakeBorder(gray, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
    try:
        text, pts, _ = _aruco.detectAndDecode(g)
    except cv2.error:
        return ''
    return text or ''


def parse_hex(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def grid_of(page):
    code = hook(page, '(() => { const c = q.cur().code; return {size: c.size, version: c.version, level: c.level, mask: c.mask, m: Array.from(c.modules)}; })()')
    return code


def expected_scale(size, quiet, target, caption=False):
    w = size + 2 * quiet
    band = w * 0.14 if caption else 0
    return max(1, math.floor(target / max(w, w + band)))


def pixel_check(img_rgba, code, quiet, k, fg, bg, transparent):
    """Every module of an exported picture: the middle of the square must have the right colour. Returns the number of wrong modules."""
    n = code['size']
    m = code['m']
    bad = 0
    a = np.array(img_rgba.convert('RGBA'))
    for y in range(n):
        for x in range(n):
            px = a[(quiet + y) * k + k // 2, (quiet + x) * k + k // 2]
            if m[y * n + x] == 1:
                want = (fg[0], fg[1], fg[2], 255)
            else:
                want = (0, 0, 0, 0) if transparent else (bg[0], bg[1], bg[2], 255)
            if transparent and m[y * n + x] != 1:
                if px[3] != 0:
                    bad += 1
            elif tuple(int(v) for v in px) != want:
                bad += 1
    return bad
