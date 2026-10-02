import contextlib, functools, http.server, json, math, os, random, re, struct, threading
from playwright.sync_api import sync_playwright

D = os.path.dirname(os.path.abspath(__file__))
SRC = D + '/gpu-check.html'
OUT = D + '/gpu-test.html'

# GPU_STANDALONE=/path/to/site/gpu-check/index.html tests the self-hosted page instead of the artifact fragment.
STANDALONE = os.environ.get('GPU_STANDALONE', '')
SITE_URL = 'https://sanjixysti-creator.github.io/gpu-check/'
SITE_TITLE = 'Used GPU Check: Free Risk and Price Checker'
STORE = 'gpu-check-v1'
SEED = int(os.environ.get('GPU_SEED', '20260930'))
CASES = int(os.environ.get('GPU_CASES', '400'))

src = open(SRC, encoding='utf-8').read()
msup = re.search(r"var SUPPORT = '([^']*)'", src)
SUPPORT = msup.group(1) if msup else ''

if STANDALONE:
    built = open(STANDALONE, encoding='utf-8').read()
    SITE_DIR = os.path.dirname(STANDALONE)
    SERVE = os.path.dirname(SITE_DIR)
    PAGE_PATH = '/' + os.path.basename(SITE_DIR) + '/'
else:
    built = ''
    SERVE = D
    PAGE_PATH = '/gpu-test.html'
    skeleton = ('<!doctype html><html><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
                '<style>:root{color-scheme:light;padding-block:env(safe-area-inset-top,0px) env(safe-area-inset-bottom,0px)}'
                'body{margin:0;font:14px system-ui,sans-serif;background:#fafafa}img{max-width:100%}[hidden]{display:none!important}</style>'
                '</head><body>' + src + '</body></html>')
    open(OUT, 'w', encoding='utf-8').write(skeleton)


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=SERVE))
PORT = httpd.server_address[1]
threading.Thread(target=httpd.serve_forever, daemon=True).start()
ORIGIN = 'http://127.0.0.1:%d' % PORT
URL = ORIGIN + PAGE_PATH

fails, passes, errs, ext_reqs = [], 0, [], []


def png_size(path):
    with open(path, 'rb') as f:
        head = f.read(24)
    if head[:8] != b'\x89PNG\r\n\x1a\n':
        return None
    return struct.unpack('>II', head[16:24])


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


@contextlib.contextmanager
def section(name):
    try:
        yield
    except Exception as e:
        fails.append('%s\n    EXCEPTION: %s' % (name, str(e).strip().splitlines()[0][:300]))


STUB_OK = ("window.__copied = null;"
           "Object.defineProperty(navigator, 'clipboard', {configurable: true, value: {writeText: function (t) { window.__copied = t; return Promise.resolve(); }}});")
STUB_REJECT = ("window.__copied = null;"
               "Object.defineProperty(navigator, 'clipboard', {configurable: true, value: {writeText: function () { return Promise.reject(new Error('blocked')); }}});"
               "document.execCommand = function () { return false; };")


def new_page(browser, stub=STUB_OK, scheme='light', w=390, h=844, pre_state=None, url=None):
    ctx = browser.new_context(viewport={'width': w, 'height': h}, color_scheme=scheme, device_scale_factor=1)
    ctx.add_init_script(stub)
    if pre_state is not None:
        ctx.add_init_script("try { if (!localStorage.getItem('%s')) localStorage.setItem('%s', %s); } catch (e) {}" % (STORE, STORE, json.dumps(pre_state)))
    page = ctx.new_page()
    page.set_default_timeout(4000)
    page.on('console', lambda m: errs.append((m.type, m.text)) if m.type in ('error', 'warning') and 'ERR_FAILED' not in m.text else None)
    page.on('pageerror', lambda e: errs.append(('pageerror', str(e))))
    page.on('request', lambda r: ext_reqs.append(r.url) if not (r.url.startswith(ORIGIN + '/') or r.url.startswith(('data:', 'blob:'))) else None)
    page.route(re.compile(r'https://fonts\.(googleapis|gstatic)\.com/.*'), lambda r: r.abort())
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


def pick(page, q, v):
    page.locator('input[data-q="%s"][value="%s"]' % (q, v)).first.evaluate('e => e.click()')


def tick(page, x, on=True):
    el = page.locator('input[data-x="%s"]' % x).first
    if el.evaluate('e => e.checked') != on:
        el.evaluate('e => e.click()')


APPLY_JS = '''(cfg) => {
    const click = s => document.querySelector(s).click();
    const reset = document.getElementById('resetBtn');
    reset.click(); reset.click();
    for (const [q, v] of cfg.a) click('input[data-q="' + q + '"][value="' + v + '"]');
    for (const x of cfg.extras) click('input[data-x="' + x + '"]');
    const set = (id, val) => { const el = document.getElementById(id); el.value = val; el.dispatchEvent(new Event('input', {bubbles: true})); };
    set('ask', cfg.ask); set('typ', cfg.typ); set('card', cfg.card);
}'''

READ_JS = '''() => {
    const c = document.getElementById('riskCard');
    const reasons = [...document.querySelectorAll('#reasons li')].map(li => [li.dataset.key, li.dataset.opt, parseInt(li.dataset.pts, 10)]);
    return {
        level: c.dataset.level, score: c.dataset.score, answered: c.dataset.answered, needed: c.dataset.needed,
        levelText: document.getElementById('riskLevel').textContent.trim(),
        scoreText: document.getElementById('riskScore').textContent.trim(),
        prog: document.getElementById('riskProg').textContent.trim(),
        deal: document.getElementById('dealPill').dataset.deal, tone: document.getElementById('dealPill').dataset.tone,
        pill: document.getElementById('dealPill').textContent.trim(),
        dealLine: document.getElementById('dealLine').textContent.trim(),
        reasons: reasons, goods: document.querySelectorAll('#goods li').length,
        moreHidden: document.getElementById('reasonsMore').hidden,
        moreText: document.getElementById('reasonsMore').textContent.trim(),
        siteVisible: !document.getElementById('secSite').hidden,
        barLevel: document.getElementById('bLevel').textContent.trim(), barScore: document.getElementById('bScore').textContent.trim(),
        barDeal: document.getElementById('bDeal').textContent.trim(), barLab: document.getElementById('bLabRisk').textContent.trim(),
        copyDisabled: document.getElementById('copyBtn').disabled,
        alert: document.getElementById('riskAlert').hidden ? '' : document.querySelector('#riskAlert p').textContent.trim(),
        alertClass: document.getElementById('riskAlert').className
    };
}'''


def apply(page, a=None, extras=(), ask='', typ='', card=''):
    page.evaluate(APPLY_JS, {'a': list((a or {}).items()), 'extras': list(extras), 'ask': str(ask), 'typ': str(typ), 'card': card})
    return page.evaluate(READ_JS)


def reset(page):
    tap(page, '#resetBtn')
    tap(page, '#resetBtn')
    page.wait_for_timeout(20)


def toast(page):
    return txt(page, '#toast') if page.is_visible('#toast') else ''


def read_copied(page):
    return page.evaluate('window.__copied') or ''


def keys(page, sel):
    return page.evaluate("s => [...document.querySelectorAll(s)].map(e => e.dataset.k)", sel)


def overflow(page, w):
    page.set_viewport_size({'width': w, 'height': 900})
    page.wait_for_timeout(120)
    return page.evaluate('''() => {
        const W = document.documentElement.clientWidth;
        const bad = [];
        document.querySelectorAll('body *').forEach(el => {
            if (getComputedStyle(el).position === 'fixed') return;
            if (el.closest('.chart-wrap')) return;
            const r = el.getBoundingClientRect();
            if (r.width && (r.right > W + 1 || r.left < -1)) bad.push(el.tagName + '.' + el.className + '#' + el.id);
        });
        return {sw: document.documentElement.scrollWidth, W: W, bad: bad.slice(0, 6)};
    }''')


# ---------------------------------------------------------------- independent reference (written apart from the page's own table)
CORE = ['platform', 'pay', 'get', 'account', 'feedback', 'contact', 'pressure', 'story', 'photos', 'history']
SITEQ = ['domain', 'business', 'reviews', 'lookalike']
TABLE = {
    'platform': {'ebay': 0, 'store': 0, 'local': 10, 'forum': 8, 'chat': 25, 'site': 12},
    'pay': {'card': 0, 'gs': 3, 'cash': 0, 'app': 30, 'wire': 70},
    'get': {'test': 0, 'notest': 10, 'ship': 6, 'prepay': 25},
    'account': {'old': 0, 'mid': 8, 'new': 22, 'unk': 12},
    'feedback': {'good': 0, 'few': 8, 'none': 20, 'bad': 35},
    'contact': {'clear': 0, 'vague': 12, 'offsite': 12},
    'pressure': {'none': 0, 'some': 8, 'hard': 22},
    'story': {'clear': 0, 'none': 3, 'odd': 22},
    'photos': {'own': 0, 'some': 6, 'stock': 25},
    'history': {'use': 0, 'new': 0, 'mining': 10, 'unk': 8},
    'domain': {'old': 0, 'young': 20, 'unk': 8},
    'business': {'yes': 0, 'some': 8, 'no': 20},
    'reviews': {'good': 0, 'none': 10, 'bad': 35},
    'lookalike': {'no': 0, 'unk': 6, 'yes': 25},
}
EXTRA_ORDER = ['noproof', 'notest', 'odd', 'fee', 'screens']
EXTRAS = {'noproof': 15, 'notest': 25, 'odd': 15, 'fee': 30, 'screens': 10}
INF = float('inf')
BANDS = [(0.5, 'toogood', 30, 'Too good to be true', 'bad'), (0.65, 'low', 18, 'Suspiciously low', 'warn'),
         (0.8, 'great', 6, 'Great price if real', 'good'), (0.95, 'good', 0, 'Good price', 'good'),
         (1.1, 'fair', 0, 'Fair price', 'neutral'), (1.25, 'high', 0, 'A bit high', 'warn'), (INF, 'over', 0, 'Overpriced', 'warn')]
LEVEL_NAMES = {'low': 'Low risk', 'med': 'Medium risk', 'high': 'High risk', 'walk': 'Walk away'}
LEVEL_SHORT = {'low': 'Low', 'med': 'Medium', 'high': 'High', 'walk': 'Walk away'}
DEAL_SHORT = {'toogood': 'Too good', 'low': 'Very low', 'great': 'Great', 'good': 'Good', 'fair': 'Fair', 'high': 'A bit high', 'over': 'Over'}


def band_of(ask, typ):
    if not (ask > 0 and typ > 0):
        return None
    r = ask / typ
    for mx, key, pts, label, tone in BANDS:
        if r < mx:
            return (r, key, pts, label, tone)


def level_of(total):
    return 'walk' if total >= 70 else 'high' if total >= 45 else 'med' if total >= 25 else 'low'


def ref(a, extras, ask, typ):
    site = a.get('platform') == 'site'
    raw, answered, items, ordn = 0, 0, [], 0
    needed = 10 + (4 if site else 0)
    for qk in CORE + (SITEQ if site else []):
        v = a.get(qk)
        if v in TABLE[qk]:
            answered += 1
            raw += TABLE[qk][v]
            if TABLE[qk][v] > 0:
                items.append((TABLE[qk][v], ordn, qk, v))
                ordn += 1
    for e in EXTRA_ORDER:
        if e in extras:
            raw += EXTRAS[e]
            items.append((EXTRAS[e], ordn, 'extras', e))
            ordn += 1
    b = band_of(ask, typ)
    if b and b[2] > 0:
        raw += b[2]
        items.append((b[2], ordn, 'price', b[1]))
        ordn += 1
    total = min(100, raw)
    items.sort(key=lambda t: (-t[0], t[1]))
    return {'total': total, 'level': level_of(total), 'answered': answered, 'needed': needed, 'items': items,
            'read': answered > 0 or len(items) > 0, 'band': b}


def pct_diff(r):
    return int(math.floor(abs(r - 1) * 100 + 0.5))


def money(n):
    return '$%s' % format(int(round(n)), ',') if round(n * 100) % 100 == 0 else '$%s' % format(n, ',.2f')


CLEAN = {'platform': 'ebay', 'pay': 'card', 'get': 'test', 'account': 'old', 'feedback': 'good', 'contact': 'clear',
         'pressure': 'none', 'story': 'clear', 'photos': 'own', 'history': 'use'}
LOCAL = {'platform': 'local', 'pay': 'cash', 'get': 'notest', 'account': 'mid', 'feedback': 'few', 'contact': 'clear',
         'pressure': 'none', 'story': 'clear', 'photos': 'some', 'history': 'use'}
SCAM = {'platform': 'chat', 'pay': 'app', 'get': 'prepay', 'account': 'new', 'feedback': 'none', 'contact': 'offsite',
        'pressure': 'hard', 'story': 'odd', 'photos': 'stock', 'history': 'unk'}

CONTRAST_JS = '''(sels) => {
    const parse = c => { const m = c.match(/rgba?\\(([^)]+)\\)/); const p = m[1].split(',').map(parseFloat); return {r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1}; };
    const lin = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    const lum = c => 0.2126 * lin(c.r) + 0.7152 * lin(c.g) + 0.0722 * lin(c.b);
    const bgOf = el => { while (el) { const c = parse(getComputedStyle(el).backgroundColor); if (c.a > 0) return c; el = el.parentElement; } return {r: 255, g: 255, b: 255, a: 1}; };
    const out = [];
    for (const sel of sels) {
        const el = [...document.querySelectorAll(sel)].find(e => e.getClientRects().length);
        if (!el) { out.push([sel, null, 0]); continue; }
        const cs = getComputedStyle(el);
        const fg = parse(cs.color), bg = bgOf(el);
        const a = lum(fg), b = lum(bg);
        const ratio = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
        const px = parseFloat(cs.fontSize), wt = parseInt(cs.fontWeight, 10);
        const need = (px >= 24 || (px >= 18.66 && wt >= 700)) ? 3 : 4.5;
        out.push([sel, Math.round(ratio * 100) / 100, need]);
    }
    return out;
}'''

CONTRAST_STATIC = ['.tagline', '.hint', '.fine', '.lab', '.qlab', '.opt span', '.opt input:checked + span', '.btn', '.btn.ghost',
                   '.safety-line', '.foot', '.foot a', '.b-lab', '.b-amt', '.affix .pre', '.ticks span', '.h3', '.sec-head h2',
                   '.bullets li', '.steps li', '.msg', '.links a', '.links a.sold', '.sources a', '.sources .fine', '.faq summary',
                   '.faq p', '.rates summary .h2', '.chart th', '.chart td', '.chart tr.grp th']

# ---------------------------------------------------------------- source hygiene
with section('source hygiene'):
    ALLOWED_HOSTS = {'fonts.googleapis.com', 'fonts.gstatic.com', 'sanjixysti-creator.github.io', 'consumer.ftc.gov', 'www.ebay.com',
                     'www.paypal.com', 'venmo.com', 'pcgamesn.com', 'evezone.evetech.co.za', 'www.amazon.com', 'www.newegg.com',
                     'pcpartpicker.com', 'www.facebook.com', 'offerup.com', 'www.reddit.com', 'www.google.com'}
    eq('no em dash', '\u2014' in src, False)
    eq('no en dash', '\u2013' in src, False)
    eq('title first', src.startswith('<title>Used GPU Check</title>'), True)
    eq('no document tags', bool(re.search(r'<(html|head|body)[\s>]', src)), False)
    eq('no print', 'window.print' in src, False)
    eq('no mailto links', 'mailto:' in src, False)
    eq('no dialogs', bool(re.search(r'\b(alert|confirm|prompt)\(', src)), False)
    eq('no external scripts', re.findall(r'<script[^>]*\bsrc=', src), [])
    eq('no innerHTML', 'innerHTML' in src, False)
    eq('only allowed hosts', sorted(set(re.findall(r'https?://([a-z0-9.\-]+)', src)) - ALLOWED_HOSTS), [])
    eq('one mail span', src.count('<span class="mail"></span>'), 1)
    head = src[:src.index('<div class="app">')]
    left = re.sub(r'<style>.*?</style>', '', head, flags=re.S)
    left = re.sub(r'<title>.*?</title>', '', left, flags=re.S)
    left = re.sub(r'<link [^>]*>', '', left)
    eq('fragment head holds only title, links, one style', left.strip(), '')
    eq('one style block', head.count('<style>'), 1)
    eq('every outbound link opens safely', [m for m in re.findall(r'<a [^>]*href="https?://(?!sanjixysti)[^"]*"[^>]*>', src) if 'noopener' not in m or '_blank' not in m], [])

    if STANDALONE:
        eq('built: doctype first', built.lstrip().lower().startswith('<!doctype html>'), True)
        eq('built: no em dash', '\u2014' in built, False)
        eq('built: no en dash', '\u2013' in built, False)
        eq('built: title', ('<title>%s</title>' % SITE_TITLE) in built, True)
        eq('built: no google fonts', 'fonts.googleapis.com' in built or 'fonts.gstatic.com' in built, False)
        eq('built: no claude.ai link', 'claude.ai' in built.lower(), False)
        eq('built: no external scripts', re.findall(r'<script[^>]*\bsrc=', built), [])
        bh = set(re.findall(r'https?://([a-z0-9.\-]+)', built))
        eq('built: only known hosts', sorted(bh - ALLOWED_HOSTS - {'www.w3.org'}), [])
        eq('built: no print', 'window.print' in built, False)
        eq('built: no dialogs', bool(re.search(r'\b(alert|confirm|prompt)\(', built)), False)
        eq('built: noscript', '<noscript>' in built, True)
        eq('built: one style block', built.count('<style>'), 1)
        eq('built: one mailto anchor', built.count('href="mailto:'), 1)
        eq('built: privacy link', 'href="privacy.html"' in built, True)
        eq('built: canonical', ('<link rel="canonical" href="%s">' % SITE_URL) in built, True)
        eq('built: og image', ('<meta property="og:image" content="%sog.png">' % SITE_URL) in built, True)
        eq('built: viewport has no cover', 'viewport-fit=cover' in built, False)
        for fname, dims in (('og.png', (1200, 630)), ('apple-touch-icon.png', (180, 180))):
            pth = os.path.join(SITE_DIR, fname)
            eq(fname + ' exists', os.path.exists(pth), True)
            if os.path.exists(pth):
                eq(fname + ' size', png_size(pth), dims)

# a design sanity pass on the points table itself
with section('table sanity'):
    for qk, opts in TABLE.items():
        eq('%s has a zero point answer' % qk, min(opts.values()), 0)
        eq('%s keeps its best answer first or at zero' % qk, all(v >= 0 for v in opts.values()), True)
    eq('crypto alone reaches walk away', level_of(TABLE['pay']['wire']), 'walk')
    eq('every clean answer scores zero', ref(CLEAN, [], 0, 0)['total'], 0)
    eq('a typical local deal is medium', ref(LOCAL, [], 0, 0)['level'], 'med')
    eq('the scam profile is capped at 100', ref(SCAM, [], 0, 0)['total'], 100)
    eq('the worst possible answers stay at 100', ref(dict(SCAM, platform='site', pay='wire', **{'domain': 'young', 'business': 'no', 'reviews': 'bad', 'lookalike': 'yes'}), list(EXTRAS), 10, 100)['total'], 100)

with sync_playwright() as p:
    try:
        browser = p.chromium.launch()
    except Exception:
        browser = p.chromium.launch(executable_path='/opt/pw-browsers/chromium-1194/chrome-linux/chrome')

    # ------------------------------------------------------------ 1 first paint, phone, light
    with section('first paint'):
        ctx, page = new_page(browser)
        r = page.evaluate(READ_JS)
        eq('starts with no read', (r['level'], r['score'], r['levelText'], r['scoreText']), ('none', '', 'No read yet', '-'))
        eq('progress 0 of 10', (r['prog'], r['answered'], r['needed']), ('0 of 10 answered', '0', '10'))
        eq('info alert', (r['alertClass'], 'Answer the questions' in r['alert']), ('alert info', True))
        eq('copy and save disabled', page.evaluate("[document.getElementById('copyBtn').disabled, document.getElementById('saveBtn').disabled]"), [True, True])
        eq('no reasons box', page.is_visible('#whyBox'), False)
        eq('no good signs box', page.is_visible('#goodBox'), False)
        eq('no price check yet', (r['pill'], r['tone']), ('No price check yet', 'none'))
        eq('deal line asks for both prices', r['dealLine'], 'Add the asking price and the typical sold price to check the deal.')
        eq('site section hidden', r['siteVisible'], False)
        eq('bar shows dashes', (r['barLevel'], r['barScore'], r['barDeal'], r['barLab']), ('-', '-', '-', 'Risk'))
        eq('51 radios and 5 checkboxes, none ticked', page.evaluate("[document.querySelectorAll('input[type=radio]').length, document.querySelectorAll('input[type=checkbox]').length, document.querySelectorAll('input:checked').length]"), [51, 5, 0])
        eq('every radio group has a label', page.evaluate("[...document.querySelectorAll('[role=radiogroup],[role=group][aria-labelledby]')].every(g => document.getElementById(g.getAttribute('aria-labelledby')))"), True)
        eq('links hidden without a card name', (page.is_visible('#links'), page.is_visible('#linksEmpty')), (False, True))
        eq('type help without a card', txt(page, '#typHelp'), 'Type the card name to get a link to what it really sold for.')
        eq('default message', txt(page, '#msgText').split('\n')[0], 'Hi, is the graphics card still available?')
        eq('default checklist', keys(page, '#todoList li'), ['test', 'keep'])
        has('empty saved text', txt(page, '#savedList'), 'No saved listings yet')
        eq('sort row hidden until two are saved', page.is_visible('#sortRow'), False)
        eq('meter pointer hidden', page.is_visible('#riskPtr'), False)
        eq('meter label while waiting', page.get_attribute('#riskMeter', 'aria-label'), 'Risk meter, waiting for answers')
        eq('exactly one level icon visible', page.evaluate("[...document.querySelectorAll('.lvicon svg')].filter(s => getComputedStyle(s).display !== 'none').length"), 1)
        eq('footer email filled', txt(page, '.mail'), SUPPORT)
        eq('page has one h1', page.evaluate("document.querySelectorAll('h1').length"), 1)
        eq('every button has a name', page.evaluate("[...document.querySelectorAll('button')].filter(b => !(b.textContent.trim() || b.getAttribute('aria-label'))).map(b => b.id)"), [])
        ctx.close()

    # ------------------------------------------------------------ 2 golden scenarios
    ctx, page = new_page(browser)
    with section('golden: all clean'):
        r = apply(page, CLEAN)
        eq('clean is low, zero', (r['level'], r['score'], r['levelText'], r['scoreText']), ('low', '0', 'Low risk', '0'))
        eq('clean is complete', (r['prog'], r['answered'], r['needed']), ('All 10 answered', '10', '10'))
        eq('clean has no reasons', r['reasons'], [])
        eq('clean shows the no warning line', page.is_visible('#noReasons'), True)
        eq('good signs are capped at five', r['goods'], 5)
        eq('bar label plain when complete', (r['barLab'], r['barLevel'], r['barScore']), ('Risk', 'Low', '0'))
        eq('pointer at the far left', page.evaluate("document.getElementById('riskPtr').style.left"), '0%')
        eq('meter label', page.get_attribute('#riskMeter', 'aria-label'), 'Risk meter: score 0 out of 100, low risk')
        has('low advice', txt(page, '#riskAdvice'), 'No big warning signs')
        eq('copy enabled once there is a read', page.evaluate("document.getElementById('copyBtn').disabled"), False)

    with section('golden: typical local deal'):
        r = apply(page, LOCAL)
        eq('local is medium 42', (r['level'], r['score'], r['levelText']), ('med', '42', 'Medium risk'))
        eq('local reasons in order', r['reasons'], [['platform', 'local', 10], ['get', 'notest', 10], ['account', 'mid', 8], ['feedback', 'few', 8], ['photos', 'some', 6]])
        eq('five reasons need no show all button', r['moreHidden'], True)
        eq('pointer at 42%', page.evaluate("document.getElementById('riskPtr').style.left"), '42%')

    with section('golden: scam profile'):
        r = apply(page, SCAM)
        eq('scam is walk away 100', (r['level'], r['score'], r['levelText']), ('walk', '100', 'Walk away'))
        eq('scam shows five reasons first', [x[:2] for x in r['reasons']], [['pay', 'app'], ['platform', 'chat'], ['get', 'prepay'], ['photos', 'stock'], ['account', 'new']])
        eq('show all button offered', (r['moreHidden'], r['moreText']), (False, 'Show all 10 reasons'))
        tap(page, '#reasonsMore')
        r2 = page.evaluate(READ_JS)
        eq('all ten reasons after show all', (len(r2['reasons']), r2['moreText']), (10, 'Show fewer'))
        eq('reasons stay sorted by points', [x[2] for x in r2['reasons']], sorted([x[2] for x in r2['reasons']], reverse=True))
        tap(page, '#reasonsMore')
        eq('show fewer goes back to five', len(page.evaluate(READ_JS)['reasons']), 5)
        eq('bar for walk away', (page.evaluate(READ_JS)['barLevel'], page.evaluate(READ_JS)['barScore']), ('Walk away', '100'))

    with section('golden: crypto alone'):
        r = apply(page, {'pay': 'wire'})
        eq('wire alone is walk away 70', (r['level'], r['score'], r['answered']), ('walk', '70', '1'))
        eq('read so far wording', r['prog'], '1 of 10 answered, a read so far')
        eq('bar says risk so far', r['barLab'], 'Risk so far')
        eq('single reason', r['reasons'], [['pay', 'wire', 70]])
        eq('walk advice', txt(page, '#riskAdvice'), 'Too many warning signs to trust this listing. Do not send money.')

    with section('golden: price only'):
        r = apply(page, {}, ask=300, typ=700)
        eq('price only still gives a read', (r['level'], r['score'], r['answered']), ('med', '30', '0'))
        eq('price reason', r['reasons'], [['price', 'toogood', 30]])
        eq('deal pill', (r['pill'], r['deal'], r['tone']), ('Too good to be true', 'toogood', 'bad'))
        eq('bar deal', r['barDeal'], 'Too good')
        r = apply(page, {}, ask=600, typ=700)
        eq('a fair price alone is not a read', (r['level'], r['score']), ('none', ''))
        eq('but the price check works', (r['pill'], r['deal']), ('Good price', 'good'))
        r = apply(page, {}, ask=400)
        eq('ask only prompts for typical price', r['dealLine'], 'Add the typical sold price to check the deal.')
        r = apply(page, {}, typ=400)
        eq('typical only prompts for asking price', r['dealLine'], 'Add the asking price to check the deal.')

    with section('price bands and boundaries'):
        cases = [(49, 'toogood'), (50, 'low'), (64, 'low'), (65, 'great'), (79, 'great'), (80, 'good'), (94, 'good'), (95, 'fair'),
                 (109, 'fair'), (110, 'high'), (124, 'high'), (125, 'over'), (300, 'over'), (10, 'toogood')]
        for ask, want in cases:
            r = apply(page, {}, ask=ask, typ=100)
            eq('ask %d of 100 is %s' % (ask, want), r['deal'], want)
            b = band_of(ask, 100)
            eq('ask %d label' % ask, r['pill'], b[3])
            eq('ask %d tone' % ask, r['tone'], b[4])
        r = apply(page, {}, ask=420, typ=560)
        eq('deal line below', r['dealLine'], 'Asking $420, typical sold $560: 25% below typical.')
        r = apply(page, {}, ask=616, typ=560)
        eq('deal line above', r['dealLine'], 'Asking $616, typical sold $560: 10% above typical.')
        r = apply(page, {}, ask=500, typ=500)
        eq('deal line equal', r['dealLine'], 'Asking $500, typical sold $500: about the same as typical.')
        r = apply(page, {}, ask='12.5', typ='25')
        eq('cents shown when needed', r['dealLine'], 'Asking $12.50, typical sold $25: 50% below typical.')
        r = apply(page, {}, ask='1,200', typ='2,400')
        eq('thousands separator parsed', r['dealLine'], 'Asking $1,200, typical sold $2,400: 50% below typical.')
        r = apply(page, {}, ask='12,5', typ='25')
        eq('comma decimal parsed', r['dealLine'], 'Asking $12.50, typical sold $25: 50% below typical.')
        r = apply(page, {}, ask='abc', typ='25')
        eq('junk price counts as nothing', r['dealLine'], 'Add the asking price to check the deal.')
        r = apply(page, {}, ask='-5', typ='25')
        eq('negative price counts as nothing', r['dealLine'], 'Add the asking price to check the deal.')
        put(page, '#ask', '99999999')
        put(page, '#typ', '5')
        page.locator('#ask').evaluate('e => e.blur()')
        eq('huge price is capped at one million', page.input_value('#ask'), '1,000,000')

    with section('price sanity alerts'):
        r = apply(page, {}, ask=5000, typ=1000)
        eq('over 3x warns', (r['alertClass'], 'more than 3 times' in r['alert']), ('alert warn', True))
        r = apply(page, {}, ask=300, typ=100)
        eq('exactly 3x does not warn', 'warn' in r['alertClass'], False)
        r = apply(page, {}, ask=50, typ=1000)
        eq('under a tenth warns', (r['alertClass'], 'under a tenth' in r['alert']), ('alert warn', True))
        r = apply(page, {}, ask=100, typ=1000)
        eq('exactly a tenth does not warn', 'warn' in r['alertClass'], False)
        r = apply(page, LOCAL)
        eq('alert clears with a normal read', r['alertClass'], 'alert')

    with section('site checks'):
        r = apply(page, {'platform': 'site'})
        eq('site shows the website section', (r['siteVisible'], r['needed'], r['score']), (True, '14', '12'))
        eq('site section has four questions', page.evaluate("document.querySelectorAll('#qs-site .q').length"), 4)
        r = apply(page, {'platform': 'site', 'domain': 'young', 'business': 'no', 'reviews': 'bad', 'lookalike': 'yes'})
        eq('website answers add up to 100', (r['score'], r['level'], r['answered']), ('100', 'walk', '5'))
        eq('site progress', r['prog'], '5 of 14 answered, a read so far')
        pick(page, 'platform', 'ebay')
        r = page.evaluate(READ_JS)
        eq('leaving site hides the section and drops its points', (r['siteVisible'], r['needed'], r['score'], r['answered']), (False, '10', '0', '1'))
        eq('stale website answers are ignored', r['reasons'], [])
        pick(page, 'platform', 'site')
        r = page.evaluate(READ_JS)
        eq('coming back to site restores its answers', (r['siteVisible'], r['score'], r['answered']), (True, '100', '5'))
        r = apply(page, dict(CLEAN, platform='site', domain='old', business='yes', reviews='good', lookalike='no'))
        eq('a clean website scores only the site base points', (r['score'], r['answered'], r['needed'], r['prog']), ('12', '14', '14', 'All 14 answered'))
        eq('site checklist item', 'site' in keys(page, '#todoList li'), True)

    with section('extras'):
        r = apply(page, {}, extras=['fee'])
        eq('one extra gives a read', (r['level'], r['score'], r['answered']), ('med', '30', '0'))
        r = apply(page, {}, extras=list(EXTRAS))
        eq('all extras sum to 95', (r['score'], r['level'], len(r['reasons'])), ('95', 'walk', 5))
        eq('extras listed in a fixed order among ties', [x[1] for x in r['reasons']], ['fee', 'notest', 'noproof', 'odd', 'screens'])
        tick(page, 'fee', False)
        tick(page, 'notest', False)
        r = page.evaluate(READ_JS)
        eq('unticking removes points', r['score'], '40')
        r_a = apply(page, {}, extras=['odd', 'noproof'])
        r_b = apply(page, {}, extras=['noproof', 'odd'])
        eq('tick order does not change the reasons', r_a['reasons'], r_b['reasons'])

    with section('real taps and keyboard'):
        reset(page)
        page.locator('label.opt', has_text='Reddit or a forum').click()
        eq('a real tap on the row picks it', page.evaluate("document.querySelector('input[data-q=platform]:checked').value"), 'forum')
        eq('and the read follows', page.evaluate(READ_JS)['score'], '8')
        page.locator('input[data-q="platform"][value="ebay"]').focus()
        page.keyboard.press('ArrowDown')
        eq('arrow key moves the choice', page.evaluate("document.querySelector('input[data-q=platform]:checked').value"), 'store')
        ol = page.evaluate("getComputedStyle(document.querySelector('input[data-q=platform]:checked + span')).outlineStyle")
        eq('keyboard focus is visible', ol, 'solid')
        eq('a visible row is at least 44px tall', page.evaluate("Math.min(...[...document.querySelectorAll('label.opt')].filter(l => l.getClientRects().length).map(l => l.getBoundingClientRect().height))") >= 44, True)
        page.locator('input[data-x="fee"]').evaluate('e => e.click()')
        eq('checkbox tick shows a check mark', page.evaluate("getComputedStyle(document.querySelector('input[data-x=fee] + span'), '::after').opacity"), '1')
        page.locator('label.opt', has_text='Asks for extra fees').click()
        eq('a real tap unticks it', page.evaluate("document.querySelector('input[data-x=fee]').checked"), False)

    # ------------------------------------------------------------ 3 checklist, message, links
    with section('checklist'):
        r = apply(page, {'pay': 'wire'})
        eq('wire first', keys(page, '#todoList li')[0], 'wire')
        has('wire text', txt(page, '#todoList li[data-k=wire]'), 'Do not pay by crypto')
        has('wire text says hard to get back', txt(page, '#todoList li[data-k=wire]'), 'hard to get back')
        lacks('wire text makes no absolute claim', txt(page, '#todoList li[data-k=wire]'), 'cannot get the money back')
        wr = page.evaluate("document.querySelector('#reasons li[data-key=pay]').textContent")
        has('wire reason says hard to get back', wr, 'hard to get back')
        has('wire reason says a money order has no buyer protection', wr, 'A money order has no buyer protection either')
        body_text = page.evaluate('document.body.textContent')
        for phrase in ('gone for good', 'almost impossible', 'cannot get the money back'):
            lacks('no absolute claim: %s' % phrase, body_text, phrase)
        apply(page, {'pay': 'app'})
        has('app text names both apps', txt(page, '#todoList li[data-k=app]'), 'Venmo Purchase Protection has to be turned on')
        has('app text on PayPal', txt(page, '#todoList li[data-k=app]'), 'PayPal does not cover personal payments')
        has('app text hedges the in-person exclusion', txt(page, '#todoList li[data-k=app]'), 'mostly does not cover items you collect in person')
        apply(page, {'platform': 'ebay'})
        has('ebay text', txt(page, '#todoList li[data-k=ebay]'), 'not covered by the eBay Money Back Guarantee')
        has('ebay deadline', txt(page, '#todoList li[data-k=ebay]'), '30 days')
        apply(page, {'get': 'prepay'})
        eq('prepay item', 'prepay' in keys(page, '#todoList li'), True)
        apply(page, {}, extras=['notest'])
        eq('notest item', 'notest' in keys(page, '#todoList li'), True)
        for plat in ('local', 'forum', 'chat'):
            apply(page, {'platform': plat})
            eq('meet item for %s' % plat, 'meet' in keys(page, '#todoList li'), True)
        for plat in ('ebay', 'store', 'site'):
            apply(page, {'platform': plat})
            eq('no meet item for %s' % plat, 'meet' in keys(page, '#todoList li'), False)
        apply(page, {}, ask=64, typ=100)
        eq('reused photos tip for a low price', 'photos' in keys(page, '#todoList li'), True)
        apply(page, {}, ask=65, typ=100)
        eq('no photos tip at 65%', 'photos' in keys(page, '#todoList li'), False)
        apply(page, {'platform': 'local', 'pay': 'wire', 'get': 'prepay'}, extras=['fee', 'notest'], ask=40, typ=100)
        eq('checklist order', keys(page, '#todoList li'), ['wire', 'fee', 'prepay', 'notest', 'meet', 'photos', 'test', 'keep'])
        apply(page, {'platform': 'ebay', 'pay': 'app'}, extras=['fee'])
        eq('checklist order with ebay', keys(page, '#todoList li'), ['fee', 'app', 'ebay', 'test', 'keep'])

    with section('message'):
        apply(page, {}, card='RX 9070 XT')
        m = txt(page, '#msgText')
        eq('message first line uses the card name', m.split('\n')[0], 'Hi, is the RX 9070 XT still available?')
        has('asks for a dated photo', m, "1. A photo of the card next to a note with today's date")
        has('asks for the serial number', m, '2. A photo of the serial number sticker')
        has('asks for a video', m, '3. A short video of the card running in your PC')
        has('generic payment line', m, "I would like to pay in a way that covers us both, like the site's checkout or PayPal Goods and Services, or cash after I test it.")
        eq('ends with thanks', m.split('\n')[-1], 'Thanks!')
        for pay, want in (('wire', 'I do not pay by crypto, wire transfer or gift card.'),
                          ('app', "I would like to pay with PayPal Goods and Services or the site's checkout so we are both covered."),
                          ('cash', 'I would like to pay cash once I have tested the card.'),
                          ('gs', 'I will pay with PayPal Goods and Services.'),
                          ('card', "I will pay through the site's checkout.")):
            apply(page, {'pay': pay})
            has('message for pay %s' % pay, txt(page, '#msgText'), want)
        for get, want in (('prepay', 'I do not pay a deposit before I have seen the card.'),
                          ('ship', 'Can you confirm you will take it back if it is not as described?'),
                          ('notest', 'Can we meet somewhere I can see it running first, or can you show it running on a video call?'),
                          ('test', 'I would like to see it running before I pay. Is that okay?')):
            apply(page, {'get': get})
            has('message for get %s' % get, txt(page, '#msgText'), want)
        apply(page, {'pay': 'wire', 'get': 'prepay'}, card='RTX 4070')
        lacks('no double blank lines', page.text_content('#msgText'), '\n\n\n')
        tap(page, '#msgCopy')
        page.wait_for_timeout(60)
        eq('message copy puts the text on the clipboard', read_copied(page), page.text_content('#msgText'))
        eq('message copy toast', toast(page), 'Message copied.')

    with section('links'):
        apply(page, {}, card='RX 9070 XT')
        eq('nine search links', keys(page, '#links a'), ['ebay-sold', 'ebay', 'amazon', 'newegg', 'pcpp', 'fb', 'offerup', 'reddit', 'google'])
        hrefs = page.evaluate("Object.fromEntries([...document.querySelectorAll('#links a')].map(a => [a.dataset.k, a.getAttribute('href')]))")
        eq('ebay sold url', hrefs['ebay-sold'], 'https://www.ebay.com/sch/i.html?_nkw=RX%209070%20XT&LH_Sold=1&LH_Complete=1')
        eq('ebay url', hrefs['ebay'], 'https://www.ebay.com/sch/i.html?_nkw=RX%209070%20XT')
        eq('amazon url', hrefs['amazon'], 'https://www.amazon.com/s?k=RX%209070%20XT')
        eq('newegg url', hrefs['newegg'], 'https://www.newegg.com/p/pl?d=RX%209070%20XT')
        eq('pcpartpicker url', hrefs['pcpp'], 'https://pcpartpicker.com/search/?q=RX%209070%20XT')
        eq('facebook url', hrefs['fb'], 'https://www.facebook.com/marketplace/search/?query=RX%209070%20XT')
        eq('offerup url', hrefs['offerup'], 'https://offerup.com/search?q=RX%209070%20XT')
        eq('reddit url', hrefs['reddit'], 'https://www.reddit.com/r/hardwareswap/search/?q=RX%209070%20XT&restrict_sr=1&sort=new')
        eq('google shopping url', hrefs['google'], 'https://www.google.com/search?tbm=shop&q=RX%209070%20XT')
        eq('all links open in a new tab safely', page.evaluate("[...document.querySelectorAll('#links a')].every(a => a.target === '_blank' && /noopener/.test(a.rel))"), True)
        eq('sold link first and highlighted', page.evaluate("document.querySelector('#links li:first-child a').classList.contains('sold')"), True)
        eq('help link points at sold listings', page.get_attribute('#typHelp a', 'href'), hrefs['ebay-sold'])
        eq('sold link spans the whole row', page.evaluate('''() => {
            const ul = document.getElementById('links').getBoundingClientRect();
            const li = document.querySelector('#links li.sold').getBoundingClientRect();
            return Math.abs(li.width - ul.width) < 1 && Math.abs(li.left - ul.left) < 1;
        }'''), True)
        eq('the other links sit in two columns', page.evaluate('''() => new Set([...document.querySelectorAll('#links li:not(.sold)')].map(l => Math.round(l.getBoundingClientRect().left))).size'''), 2)
        eq('only the sold link is marked', page.evaluate("document.querySelectorAll('#links li.sold').length"), 1)
        eq('empty hint hides', (page.is_visible('#links'), page.is_visible('#linksEmpty')), (True, False))
        apply(page, {}, card='RTX 4070 Ti & Super "OC"')
        h = page.get_attribute('#links a[data-k=amazon]', 'href')
        eq('special characters are encoded', h, 'https://www.amazon.com/s?k=RTX%204070%20Ti%20%26%20Super%20%22OC%22')
        apply(page, {}, card='   ')
        eq('spaces alone give no links', (page.is_visible('#links'), page.is_visible('#linksEmpty')), (False, True))
        apply(page, {}, card='x' * 200)
        eq('card name is capped at 60 in the read', txt(page, '#msgText').split('\n')[0], 'Hi, is the ' + 'x' * 60 + ' still available?')
        eq('card box has a 60 character limit', page.get_attribute('#card', 'maxlength'), '60')
        n_err = len([e for e in errs if e[0] == 'pageerror'])
        apply(page, {}, card='a' * 59 + '\U0001F600' + 'zzz')
        eq('an emoji cut by the limit causes no page error', len([e for e in errs if e[0] == 'pageerror']), n_err)
        eq('the cut emoji is dropped, not left in half', txt(page, '#msgText').split('\n')[0], 'Hi, is the ' + 'a' * 59 + ' still available?')
        eq('links are still built after the cut', page.evaluate("document.querySelectorAll('#links a').length"), 9)
        eq('cut card is encoded cleanly', page.get_attribute('#links a[data-k=amazon]', 'href'), 'https://www.amazon.com/s?k=' + 'a' * 59)
        apply(page, {}, card='RTX \U0001F600')
        eq('a whole emoji encodes as UTF-8', page.get_attribute('#links a[data-k=amazon]', 'href'), 'https://www.amazon.com/s?k=RTX%20%F0%9F%98%80')

    with section('section order'):
        eq('website section follows the listing section', page.evaluate("document.getElementById('secSite').previousElementSibling.getAttribute('aria-labelledby')"), 'h-listing')
        eq('the seller section follows the website section', page.evaluate("document.getElementById('secSite').nextElementSibling.getAttribute('aria-labelledby')"), 'h-seller')

    with section('screen reader read'):
        ctx_sr, pg_sr = new_page(browser)
        eq('live region is empty on load', txt(pg_sr, '#srRead'), '')
        eq('live region is polite, atomic and a status', pg_sr.evaluate("(e => [e.getAttribute('aria-live'), e.getAttribute('aria-atomic'), e.getAttribute('role')])(document.getElementById('srRead'))"), ['polite', 'true', 'status'])
        box = pg_sr.evaluate("(r => [Math.round(r.width), Math.round(r.height)])(document.getElementById('srRead').getBoundingClientRect())")
        eq('live region takes no room on screen', box, [1, 1])
        apply(pg_sr, {'platform': 'local', 'pay': 'app', 'feedback': 'few'}, ask=380, typ=640, card='RX 9070 XT')
        eq('live region reads the risk and the price check', txt(pg_sr, '#srRead'), 'High risk, score 66 out of 100. 3 of 10 answered, a read so far. Price check: Suspiciously low.')
        apply(pg_sr, {'platform': 'ebay'})
        eq('live region without a price', txt(pg_sr, '#srRead'), 'Low risk, score 0 out of 100. 1 of 10 answered, a read so far.')
        apply(pg_sr, {'platform': 'ebay', 'pay': 'card', 'get': 'test', 'account': 'old', 'feedback': 'good', 'contact': 'clear',
                      'pressure': 'none', 'story': 'clear', 'photos': 'own', 'history': 'use'}, ask=600, typ=640)
        eq('live region when everything is answered', txt(pg_sr, '#srRead'), 'Low risk, score 0 out of 100. All 10 answered. Price check: Good price.')
        reset(pg_sr)
        eq('live region clears on start over', txt(pg_sr, '#srRead'), '')
        ctx_sr.close()
        ctx_sr, pg_sr = new_page(browser, pre_state=json.dumps({'v': 1, 'a': {'platform': 'local'}}))
        eq('a saved read is not announced on load', txt(pg_sr, '#srRead'), '')
        ctx_sr.close()

    with section('copy summary'):
        r = apply(page, {'platform': 'local', 'pay': 'app', 'feedback': 'few'}, ask=380, typ=640, card='RX 9070 XT')
        eq('summary read', (r['score'], r['level'], r['answered']), ('66', 'high', '3'))
        tap(page, '#copyBtn')
        page.wait_for_timeout(60)
        want = '\n'.join([
            'Used GPU check',
            'Card: RX 9070 XT',
            'Price: asking $380, typical sold $640 (suspiciously low, 41% below)',
            'Risk: High risk, 66 of 100 (3 of 10 questions answered)',
            'Warning signs:',
            '+30 Payment apps sent to a stranger are hard to undo, and PayPal does not cover personal payments.',
            '+18 The asking price is well below the typical sold price. Prices this far under market are a common warning sign.',
            '+10 Local listings are easy to fake and usually come with little or no buyer protection.',
            '+8 The seller has little history to check.',
            'This is a checklist result, not proof. Test the card and pay with protection.'])
        eq('summary text', read_copied(page), want)
        eq('summary toast', toast(page), 'Summary copied.')
        r = apply(page, {'platform': 'ebay'})
        tap(page, '#copyBtn')
        page.wait_for_timeout(60)
        c = read_copied(page)
        has('summary with nothing wrong', c, 'No warning signs in the answers so far.')
        lacks('summary has no card line without a card', c, 'Card:')
        lacks('summary has no price line without a price', c, 'Price:')
        r = apply(page, {'platform': 'ebay'}, ask=420)
        tap(page, '#copyBtn')
        page.wait_for_timeout(60)
        has('summary with only an asking price', read_copied(page), 'Price: asking $420\n')
    ctx.close()

    # ------------------------------------------------------------ 4 saved listings, persistence, hostile storage
    with section('saved listings'):
        ctx, page = new_page(browser)
        apply(page, {'platform': 'local', 'pay': 'app', 'feedback': 'few'}, ask=380, typ=640, card='RX 9070 XT')
        tap(page, '#saveBtn')
        eq('save form opens', page.is_visible('#saveForm'), True)
        eq('save name focused', page.evaluate("document.activeElement && document.activeElement.id"), 'saveName')
        put(page, '#saveName', 'Mike on Marketplace')
        page.locator('#saveForm button[type=submit]').evaluate('e => e.click()')
        page.wait_for_timeout(80)
        eq('save form closes', page.is_visible('#saveForm'), False)
        eq('saved toast', toast(page), 'Saved Mike on Marketplace.')
        eq('saved name', txt(page, '#savedList .sv-name'), 'Mike on Marketplace')
        eq('saved summary', txt(page, '#savedList .sv-sum'), 'Asking $380, typical sold $640: suspiciously low')
        eq('saved chip', txt(page, '#savedList .lvchip'), 'High risk 66')
        eq('saved progress', txt(page, '#savedList .sv-risk span:last-child'), '3 of 10 answered')
        eq('saved level attribute', page.get_attribute('#savedList .saved', 'data-level'), 'high')

        apply(page, dict(CLEAN), ask=520, typ=600, card='RTX 4070')
        tap(page, '#saveBtn')
        tap(page, '#saveForm button[type=submit]')
        page.wait_for_timeout(80)
        eq('blank name uses card and price', txt(page, '#savedList .saved:nth-child(1) .sv-name'), 'RTX 4070 at $520')
        eq('newest first', [txt(page, '#savedList .saved:nth-child(%d) .sv-name' % i) for i in (1, 2)], ['RTX 4070 at $520', 'Mike on Marketplace'])
        eq('sort row appears with two saved', page.is_visible('#sortRow'), True)

        apply(page, dict(SCAM), ask=150, typ=600, card='RX 7800 XT')
        tap(page, '#saveBtn')
        put(page, '#saveName', 'Too good')
        tap(page, '#saveForm button[type=submit]')
        page.wait_for_timeout(60)
        apply(page, {'platform': 'store'})
        tap(page, '#saveBtn')
        tap(page, '#saveForm button[type=submit]')
        page.wait_for_timeout(60)
        eq('no price and no card gets a plain name', txt(page, '#savedList .saved:nth-child(1) .sv-name'), 'Saved listing')
        names = lambda: page.evaluate("[...document.querySelectorAll('#savedList .sv-name')].map(e => e.textContent)")
        eq('four saved newest first', names(), ['Saved listing', 'Too good', 'RTX 4070 at $520', 'Mike on Marketplace'])
        tap(page, '#sortRisk')
        eq('sort by lowest risk', names(), ['Saved listing', 'RTX 4070 at $520', 'Mike on Marketplace', 'Too good'])
        eq('risk sort shows scores rising', page.evaluate("[...document.querySelectorAll('#savedList .saved')].map(e => parseInt(e.dataset.score, 10))"), [0, 0, 66, 100])
        tap(page, '#sortPrice')
        eq('sort by lowest price puts unpriced last', names(), ['Too good', 'Mike on Marketplace', 'RTX 4070 at $520', 'Saved listing'])
        eq('sort buttons show the active one', page.evaluate("[...document.querySelectorAll('[data-sort]')].map(b => b.getAttribute('aria-pressed'))"), ['false', 'false', 'true'])
        tap(page, '#sortNew')
        eq('back to newest', names()[0], 'Saved listing')

        # load one back
        apply(page, {})
        tap(page, '#savedList .saved:nth-child(2) .btn.sm:not(.ghost)')
        page.wait_for_timeout(80)
        r = page.evaluate(READ_JS)
        eq('load restores the read', (r['score'], r['level'], r['answered']), ('100', 'walk', '10'))
        eq('load restores the inputs', (page.input_value('#card'), page.input_value('#ask'), page.input_value('#typ')), ('RX 7800 XT', '150', '600'))
        eq('load restores the answers', page.evaluate("document.querySelector('input[data-q=pay]:checked').value"), 'app')
        eq('load toast', toast(page), 'Loaded Too good.')

        # persistence
        page.reload()
        page.wait_for_timeout(250)
        eq('everything survives a reload', (page.input_value('#card'), page.input_value('#ask'), page.evaluate(READ_JS)['score']), ('RX 7800 XT', '150', '100'))
        eq('saved survive a reload', page.evaluate("document.querySelectorAll('#savedList .saved').length"), 4)
        stored = page.evaluate("JSON.parse(localStorage.getItem('%s'))" % STORE)
        eq('stored version and counts', (stored['v'], len(stored['saved']), stored['sort'], stored['a']['pay']), (1, 4, 'new', 'app'))
        eq('stored saved carries answers', stored['saved'][0]['a'], {'platform': 'store'})

        # two-tap delete
        btn = '#savedList .saved:nth-child(1) .btn.ghost'
        eq('delete idle label', txt(page, btn), 'Delete')
        tap(page, btn)
        eq('delete armed label', txt(page, btn), 'Tap again to delete')
        eq('still four after one tap', page.evaluate("document.querySelectorAll('#savedList .saved').length"), 4)
        tap(page, btn)
        page.wait_for_timeout(80)
        eq('deleted', page.evaluate("document.querySelectorAll('#savedList .saved').length"), 3)
        page.reload()
        page.wait_for_timeout(200)
        eq('delete survives a reload', page.evaluate("document.querySelectorAll('#savedList .saved').length"), 3)

        # a sort choice survives too
        tap(page, '#sortRisk')
        page.reload()
        page.wait_for_timeout(200)
        eq('sort choice survives a reload', page.get_attribute('#sortRisk', 'aria-pressed'), 'true')

        # start over keeps the saved ones
        tap(page, '#resetBtn')
        eq('start over armed', txt(page, '#resetBtn'), 'Tap again to start over')
        tap(page, '#resetBtn')
        page.wait_for_timeout(60)
        r = page.evaluate(READ_JS)
        eq('start over clears the read', (r['level'], page.input_value('#card'), page.input_value('#ask')), ('none', '', ''))
        eq('start over keeps saved', page.evaluate("document.querySelectorAll('#savedList .saved').length"), 3)
        eq('start over unticks everything', page.evaluate("document.querySelectorAll('input:checked').length"), 0)
        eq('start over toast', toast(page), 'Started over.')
        ctx.close()

    with section('cannot save an empty read'):
        ctx, page = new_page(browser)
        eq('save disabled with nothing', page.is_disabled('#saveBtn'), True)
        apply(page, {}, ask=600, typ=700)
        eq('save still disabled with a fair price only', page.is_disabled('#saveBtn'), True)
        apply(page, {'platform': 'ebay'})
        eq('save enabled after one answer', page.is_disabled('#saveBtn'), False)
        tap(page, '#saveBtn')
        eq('form is open', page.is_visible('#saveForm'), True)
        apply(page, {})
        eq('form closes when the read goes away', page.is_visible('#saveForm'), False)
        ctx.close()

    with section('saved cap'):
        many = {'v': 1, 'card': '', 'ask': 0, 'typ': 0, 'a': {'platform': 'ebay'}, 'extras': [], 'seq': 40, 'sort': 'new',
                'saved': [{'id': 'g%d' % i, 'name': 'Listing %d' % i, 'card': 'X', 'ask': 100 + i, 'typ': 200, 'a': {'platform': 'ebay'}, 'extras': [], 'ts': i} for i in range(30)]}
        c2, pg2 = new_page(browser, pre_state=json.dumps(many))
        eq('thirty saved show', pg2.evaluate("document.querySelectorAll('#savedList .saved').length"), 30)
        tap(pg2, '#saveBtn')
        tap(pg2, '#saveForm button[type=submit]')
        pg2.wait_for_timeout(80)
        has('cap toast', toast(pg2), 'You can keep 30 listings.')
        eq('still thirty', pg2.evaluate("document.querySelectorAll('#savedList .saved').length"), 30)
        over = dict(many, saved=many['saved'] + [{'id': 'zz', 'name': 'extra', 'a': {}}])
        c3, pg3 = new_page(browser, pre_state=json.dumps(over))
        eq('stored lists over thirty are trimmed', pg3.evaluate("document.querySelectorAll('#savedList .saved').length"), 30)
        c2.close()
        c3.close()

    with section('hostile storage'):
        junk = [
            json.dumps({'v': 1, 'card': 123, 'ask': 'abc', 'typ': -5, 'a': {'platform': 'nope', 'pay': 'wire', 'zzz': 'x', 'get': ['test']},
                        'extras': ['fee', 'fee', 'bogus', 5], 'sort': 'weird',
                        'saved': [{'id': 1, 'name': '<img src=x onerror=alert(1)>', 'card': '<b>x</b>', 'ask': '12', 'typ': 1, 'a': {'platform': 'ebay'}, 'extras': ['fee']}, None, 5, {'nope': 1}]}),
            'not json at all',
            '{"v":2}',
            '{"v":1,"saved":"nope"}',
            '{"v":1,"a":"nope","extras":"nope","ask":{"x":1}}',
        ]
        for i, raw in enumerate(junk):
            n_err = len([e for e in errs if e[0] == 'pageerror'])
            c3, pg3 = new_page(browser, pre_state=raw)
            r = pg3.evaluate(READ_JS)
            eq('junk %d has no page errors' % i, len([e for e in errs if e[0] == 'pageerror']), n_err)
            if i == 0:
                eq('junk keeps the one valid answer and extra', (r['level'], r['score'], r['answered']), ('walk', '100', '1'))
                eq('junk card is text', pg3.input_value('#card'), '123')
                eq('junk price falls back to blank', (pg3.input_value('#ask'), pg3.input_value('#typ')), ('', ''))
                eq('junk sort falls back', pg3.get_attribute('#sortNew', 'aria-pressed'), 'true')
                eq('junk saved keeps one row', pg3.evaluate("document.querySelectorAll('#savedList .saved').length"), 1)
                eq('junk name is text, not markup', pg3.evaluate("document.querySelectorAll('#savedList img, #savedList b').length"), 0)
                eq('junk name shown as text', 'onerror' in txt(pg3, '#savedList .sv-name'), True)
                eq('duplicate and bogus extras dropped', pg3.evaluate("[...document.querySelectorAll('input[data-x]:checked')].map(e => e.value)"), ['fee'])
            else:
                eq('junk %d falls back to a blank start' % i, (r['level'], r['answered']), ('none', '0'))
            c3.close()
        c3, pg3 = new_page(browser, pre_state='{"v":1,"card":"ab\\ud800cd","saved":[{"id":"q","name":"n\\udc00","card":"x\\ud83d","a":{"platform":"ebay"}}]}')
        eq('a lone surrogate in storage still builds links', pg3.get_attribute('#links a[data-k=amazon]', 'href'), 'https://www.amazon.com/s?k=abcd')
        eq('a lone surrogate in a saved row still lists it', pg3.evaluate("document.querySelectorAll('#savedList .saved').length"), 1)
        c3.close()
        # storage that throws on every call
        cb = browser.new_context(viewport={'width': 390, 'height': 844})
        cb.add_init_script("Object.defineProperty(window, 'localStorage', {get: function () { throw new Error('denied'); }});")
        pb = cb.new_page()
        pb.on('pageerror', lambda e: errs.append(('pageerror', str(e))))
        pb.route(re.compile(r'https://fonts\.(googleapis|gstatic)\.com/.*'), lambda r: r.abort())
        pb.goto(URL)
        pb.wait_for_timeout(200)
        r = apply(pb, LOCAL)
        eq('page works with storage denied', (r['score'], r['level']), ('42', 'med'))
        cb.close()

    # ------------------------------------------------------------ 5 clipboard blocked
    ctx4, pg4 = new_page(browser, stub=STUB_REJECT)
    with section('clipboard blocked'):
        apply(pg4, LOCAL, card='RX 9070 XT')
        tap(pg4, '#copyBtn')
        pg4.wait_for_timeout(120)
        eq('fallback sheet shows', pg4.is_visible('#sheet'), True)
        has('fallback text', pg4.input_value('#sheetText'), 'Used GPU check')
        tap(pg4, '#sheetClose')
        eq('fallback closes', pg4.is_visible('#sheet'), False)
        tap(pg4, '#msgCopy')
        pg4.wait_for_timeout(120)
        has('message fallback', pg4.input_value('#sheetText'), 'Hi, is the RX 9070 XT still available?')
        tap(pg4, '#sheetClose')
        tap(pg4, '.mail-copy')
        pg4.wait_for_timeout(120)
        eq('email copy fallback shows address', pg4.input_value('#sheetText'), SUPPORT)
    ctx4.close()

    # ------------------------------------------------------------ 6 rules table
    with section('rules table'):
        ctx, page = new_page(browser)
        rows = page.evaluate("[...document.querySelectorAll('#rulesBody tr[data-q]')].map(r => [r.dataset.q, r.dataset.o, parseInt(r.dataset.pts, 10), r.children[1].textContent.trim()])")
        want = []
        for qk in CORE + SITEQ:
            for o, pts in TABLE[qk].items():
                want.append([qk, o, pts, ('+%d' % pts) if pts else '0'])
        for e in EXTRA_ORDER:
            want.append(['extras', e, EXTRAS[e], '+%d' % EXTRAS[e]])
        for mx, key, pts, label, tone in BANDS:
            want.append(['price', key, pts, ('+%d' % pts) if pts else '0'])
        eq('rules table row count', len(rows), len(want))
        eq('rules table matches the independent table', sorted(rows), sorted(want))
        eq('rules table labels each group', page.evaluate("document.querySelectorAll('#rulesBody tr.grp').length"), 10 + 4 + 1 + 1)
        eq('score band line', txt(page, '#levelRules'), 'Score bands: low risk 0 to 24, medium risk 25 to 44, high risk 45 to 69, walk away 70 and up.')
        price_rows = page.evaluate("[...document.querySelectorAll('#rulesBody tr[data-q=price] td:first-child')].map(e => e.textContent)")
        eq('price rows read in order', price_rows, ['Under 50%: Too good to be true', '50% to under 65%: Suspiciously low', '65% to under 80%: Great price if real',
                                                     '80% to under 95%: Good price', '95% to under 110%: Fair price', '110% to under 125%: A bit high', 'Over 125%: Overpriced'])
        # each reason text is unique so a reader can tell them apart
        ctx.close()

    # ------------------------------------------------------------ 7 property test against the independent reference
    with section('property test'):
        ctx5, pg5 = new_page(browser)
        rng = random.Random(SEED)
        price_pool = [0, 0, 5, 40, 79, 80, 100, 150, 250, 300, 380, 420, 500, 640, 700, 850, 1200]
        bad, seen_levels, seen_bands = [], set(), set()
        for i in range(CASES):
            a = {}
            for qk in CORE + SITEQ:
                if rng.random() < 0.7:
                    a[qk] = rng.choice(list(TABLE[qk]))
            if rng.random() < 0.25:
                a['platform'] = 'site'
            extras = [e for e in EXTRA_ORDER if rng.random() < 0.25]
            rng.shuffle(extras)
            if rng.random() < 0.06:
                a, extras = {}, []
            ask, typ = rng.choice(price_pool), rng.choice(price_pool)
            exp = ref(a, extras, ask, typ)
            got = apply(pg5, a, extras, ask=ask if ask else '', typ=typ if typ else '')
            seen_levels.add(exp['level'] if exp['read'] else 'none')
            if exp['band']:
                seen_bands.add(exp['band'][1])
            want_items = [[k, o, pts] for (pts, _o, k, o) in exp['items']][:5]
            want = {
                'level': exp['level'] if exp['read'] else 'none',
                'score': str(exp['total']) if exp['read'] else '',
                'answered': str(exp['answered']), 'needed': str(exp['needed']),
                'reasons': want_items,
                'deal': exp['band'][1] if exp['band'] else '',
                'siteVisible': a.get('platform') == 'site',
            }
            have = {k: got[k] for k in want}
            if have != want:
                bad.append((i, a, extras, ask, typ, have, want))
                if len(bad) >= 3:
                    break
        eq('%d random cases match the reference (%d mismatches shown below)' % (CASES, len(bad)), [b[:5] for b in bad], [])
        for b in bad:
            fails.append('property mismatch detail\n    case: %r\n    have: %r\n    want: %r' % (b[:5], b[5], b[6]))
        eq('the random cases reached every level', sorted(seen_levels), ['high', 'low', 'med', 'none', 'walk'])
        eq('the random cases reached every price band', sorted(seen_bands), sorted(b[1] for b in BANDS))
        ctx5.close()

    with section('property: more answers never lower the score'):
        ctx5, pg5 = new_page(browser)
        rng = random.Random(SEED + 1)
        broke = []
        for i in range(60):
            a = {qk: rng.choice(list(TABLE[qk])) for qk in CORE if rng.random() < 0.5}
            extras = [e for e in EXTRA_ORDER if rng.random() < 0.2]
            before = int(apply(pg5, a, extras)['score'] or 0)
            qk = rng.choice(CORE)
            worse = max(TABLE[qk], key=lambda o: TABLE[qk][o])
            was = a.get(qk)
            if was is not None and TABLE[qk][was] >= TABLE[qk][worse]:
                continue
            pick(pg5, qk, worse)
            after = int(pg5.evaluate(READ_JS)['score'] or 0)
            if after < before:
                broke.append((a, qk, worse, before, after))
        eq('a worse answer never lowers the score', broke, [])
        ctx5.close()

    # ------------------------------------------------------------ 8 layouts, widths, dark, contrast
    with section('layout phone'):
        ctx6, pg6 = new_page(browser)
        pg6.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
        apply(pg6, dict(SCAM, platform='site', domain='young', business='no', reviews='bad', lookalike='yes'), list(EXTRAS), ask=380, typ=640, card='GeForce RTX 4070 Ti Super 16GB Founders Edition')
        tap(pg6, '#reasonsMore')
        tap(pg6, '#saveBtn')
        put(pg6, '#saveName', 'A very long listing name from a seller with a very long username on a marketplace')
        tap(pg6, '#saveForm button[type=submit]')
        apply(pg6, LOCAL, ask=420, typ=560, card='RX 9070 XT')
        tap(pg6, '#saveBtn')
        tap(pg6, '#saveForm button[type=submit]')
        tap(pg6, '#saveBtn')
        for w in (320, 360, 390, 768, 1200):
            o = overflow(pg6, w)
            eq('no horizontal overflow at %d' % w, (o['sw'] <= o['W'], o['bad']), (True, []))
        pg6.set_viewport_size({'width': 320, 'height': 700})
        pg6.wait_for_timeout(100)
        pg6.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        pg6.wait_for_timeout(100)
        gap = pg6.evaluate('''() => {
            const foot = document.querySelector('.foot').getBoundingClientRect();
            const bar = document.getElementById('bar').getBoundingClientRect();
            return Math.round(bar.top - foot.bottom);
        }''')
        eq('footer clear of the pinned bar', gap >= 0, True)
        cells = pg6.evaluate("[...document.querySelectorAll('#bar .b-cell')].map(c => { const r = c.getBoundingClientRect(); return [Math.round(r.left), Math.round(r.right), Math.round(r.top)]; })")
        eq('three bar cells on one row', len(set(c[2] for c in cells)), 1)
        eq('bar cells inside the screen', all(c[0] >= 0 and c[1] <= 320 for c in cells), True)
        # every level and deal label fits in its bar cell at 320px
        combos = [(CLEAN, 0, 0), (LOCAL, 0, 0), ({'pay': 'app', 'platform': 'local', 'feedback': 'few'}, 380, 640), (SCAM, 300, 100), ({'pay': 'wire'}, 40, 100),
                  ({'platform': 'ebay'}, 0, 0), ({'pay': 'wire'}, 55, 100), ({'pay': 'wire'}, 70, 100), ({'pay': 'wire'}, 85, 100),
                  ({'pay': 'wire'}, 100, 100), ({'pay': 'wire'}, 120, 100), ({'pay': 'wire'}, 150, 100)]
        clipped = []
        for a, ask, typ in combos:
            r = apply(pg6, a, ask=ask or '', typ=typ or '')
            for sel in ('#bLevel', '#bScore', '#bDeal', '#bLabRisk'):
                if not pg6.evaluate("s => { const e = document.querySelector(s); return e.scrollWidth <= e.clientWidth + 1; }", sel):
                    clipped.append((r['level'], r['deal'], sel, txt(pg6, sel)))
        eq('bar text is never clipped at 320', clipped, [])
        apply(pg6, {'pay': 'wire'}, ask=40, typ=100)
        eq('level and score do not overlap in the card', pg6.evaluate('''() => {
            const a = document.querySelector('.lvtxt').getBoundingClientRect(), b = document.querySelector('.score').getBoundingClientRect();
            return a.right <= b.left + 0.5;
        }'''), True)
        pg6.set_viewport_size({'width': 390, 'height': 844})
        pg6.wait_for_timeout(100)
        pg6.evaluate('window.scrollTo(0, 0)')
        apply(pg6, {'platform': 'local', 'pay': 'app', 'feedback': 'few', 'account': 'mid', 'photos': 'stock'}, ['noproof'], ask=380, typ=640, card='RX 9070 XT')
        pg6.locator('#riskCard').screenshot(path=D + '/gpu-card-full.png')
        pg6.screenshot(path=D + '/gpu-phone-open.png', full_page=True)
        ctx6.close()

    with section('desktop layout'):
        ctx7, pg7 = new_page(browser, w=1200, h=900)
        eq('bar hidden on desktop', pg7.is_visible('#bar'), False)
        pos = pg7.evaluate('''() => {
            const a = document.querySelector('.inputs').getBoundingClientRect();
            const r = document.querySelector('.results').getBoundingClientRect();
            const m = document.querySelector('.more').getBoundingClientRect();
            return {inputsRight: a.right, resultsLeft: r.left, resultsTop: r.top, inputsTop: a.top, moreLeft: m.left, moreRight: m.right, inputsLeft: a.left};
        }''')
        eq('results to the right of inputs', pos['resultsLeft'] > pos['inputsRight'], True)
        eq('results aligned with inputs at the top', abs(pos['resultsTop'] - pos['inputsTop']) < 2, True)
        eq('more shares the inputs column', abs(pos['moreLeft'] - pos['inputsLeft']) < 1 and abs(pos['moreRight'] - pos['inputsRight']) < 1, True)
        apply(pg7, LOCAL, ask=420, typ=560, card='RX 9070 XT')
        pg7.evaluate('window.scrollTo(0, 0)')
        pg7.screenshot(path=D + '/gpu-desktop-light.png')
        pg7.evaluate('window.scrollTo(0, 900)')
        pg7.wait_for_timeout(120)
        eq('results stay in view when scrolled', pg7.evaluate("document.querySelector('.results').getBoundingClientRect().top") < 40, True)
        eq('results card is never taller than the screen', pg7.evaluate("document.querySelector('.results').getBoundingClientRect().height") <= 900, True)
        ctx7.close()
        ctx7b, pg7b = new_page(browser, w=899, h=900)
        eq('bar shows just under the breakpoint', pg7b.is_visible('#bar'), True)
        ctx7b.close()
        ctx7c, pg7c = new_page(browser, w=768, h=900)
        apply(pg7c, {}, card='RX 9070 XT')
        eq('tablet gets three link columns', pg7c.evaluate("getComputedStyle(document.getElementById('links')).gridTemplateColumns.split(' ').length"), 3)
        ctx7c.close()
        ctx7d, pg7d = new_page(browser, w=390, h=900)
        apply(pg7d, {}, card='RX 9070 XT')
        eq('phone gets two link columns', pg7d.evaluate("getComputedStyle(document.getElementById('links')).gridTemplateColumns.split(' ').length"), 2)
        ctx7d.close()

    with section('dark'):
        ctx8, pg8 = new_page(browser, scheme='dark')
        apply(pg8, {'platform': 'local', 'pay': 'app', 'feedback': 'few', 'account': 'mid', 'photos': 'stock'}, ['noproof'], ask=380, typ=640, card='RX 9070 XT')
        pg8.evaluate('window.scrollTo(0, 0)')
        pg8.screenshot(path=D + '/gpu-dark-top.png')
        pg8.locator('#riskCard').screenshot(path=D + '/gpu-dark-card.png')
        pg8.screenshot(path=D + '/gpu-dark-full.png', full_page=True)
        eq('dark body background', pg8.evaluate("getComputedStyle(document.body).backgroundColor"), 'rgb(12, 14, 30)')
        ctx8.close()
        ctx8b, pg8b = new_page(browser, scheme='dark', w=1200, h=900)
        apply(pg8b, LOCAL, ask=420, typ=560, card='RX 9070 XT')
        pg8b.evaluate('window.scrollTo(0, 0)')
        pg8b.screenshot(path=D + '/gpu-desktop-dark.png')
        ctx8b.close()
        ctx9, pg9 = new_page(browser, scheme='dark')
        pg9.evaluate("document.documentElement.setAttribute('data-theme', 'light')")
        eq('data-theme light wins over dark OS', pg9.evaluate("getComputedStyle(document.body).backgroundColor"), 'rgb(232, 234, 244)')
        ctx9.close()
        ctx9b, pg9b = new_page(browser, scheme='light')
        pg9b.evaluate("document.documentElement.setAttribute('data-theme', 'dark')")
        eq('data-theme dark wins over light OS', pg9b.evaluate("getComputedStyle(document.body).backgroundColor"), 'rgb(12, 14, 30)')
        ctx9b.close()

    LEVEL_STATES = [
        ('none', {}, '', ''),
        ('low', CLEAN, '', ''),
        ('med', LOCAL, '', ''),
        ('high', {'platform': 'local', 'pay': 'app', 'feedback': 'few'}, 380, 640),
        ('walk', {'pay': 'wire'}, '', ''),
    ]
    TONE_PRICES = [('none', '', ''), ('bad', 40, 100), ('warn', 55, 100), ('good', 70, 100), ('good', 85, 100), ('neutral', 100, 100), ('warn', 120, 100)]
    LEVEL_SELS = ['.lvname', '.lvsub', '.advice', '.score', '.score small', '.pill', '.b-amt.lv', '.b-amt.tn', '.reasons li', '.reasons .pts', '.goods li', '.lvchip', '.deal .fine', '.alert.info p']
    for scheme in ('light', 'dark'):
        with section('contrast ' + scheme):
            cx, pgc = new_page(browser, scheme=scheme)
            pgc.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
            weak, missing = [], []
            res = pgc.evaluate(CONTRAST_JS, ['.empty', '#savedList .empty', '#linksEmpty', '.alert.info p'])
            # saved listings next so chips, sort buttons and cards exist
            for lvl, a, ask, typ in LEVEL_STATES[1:]:
                apply(pgc, a, ask=ask, typ=typ, card='RX 9070 XT')
                tap(pgc, '#saveBtn')
                put(pgc, '#saveName', 'x')
                tap(pgc, '#saveForm button[type=submit]')
            apply(pgc, dict(CLEAN), ask=520, typ=600, card='RX 9070 XT')
            res += pgc.evaluate(CONTRAST_JS, CONTRAST_STATIC + ['.seg button', '.seg button[aria-pressed="true"]', '.sv-sum', '.sv-risk', '.sv-name', '.saved .btn'])
            for lvl, a, ask, typ in LEVEL_STATES:
                r = apply(pgc, a, ask=ask, typ=typ, card='RX 9070 XT')
                eq('%s state reaches level %s' % (scheme, lvl), r['level'], lvl)
                sels = [s for s in LEVEL_SELS if not (s.startswith('.alert') and lvl != 'none')]
                rr = pgc.evaluate(CONTRAST_JS, sels)
                res += [[lvl + ' ' + s, ratio, need] for s, ratio, need in rr if not (ratio is None and s in ('.reasons li', '.reasons .pts', '.goods li', '.b-amt.tn', '.deal .fine'))]
            for tone, ask, typ in TONE_PRICES:
                apply(pgc, {}, ask=ask, typ=typ)
                res += [['tone %s %s' % (tone, s), ratio, need] for s, ratio, need in pgc.evaluate(CONTRAST_JS, ['.pill', '.b-amt.tn'])]
            apply(pgc, {}, ask=5000, typ=1000)
            res += pgc.evaluate(CONTRAST_JS, ['.alert.warn p'])
            weak = [(s, r, n) for (s, r, n) in res if r is not None and r < n]
            missing = [s for (s, r, n) in res if r is None]
            eq('%s contrast is strong enough everywhere' % scheme, weak, [])
            eq('%s contrast audit found its elements' % scheme, missing, [])
            cx.close()

    with section('non text contrast'):
        for scheme, ring_need in (('light', 3.0), ('dark', 3.0)):
            cx, pgn = new_page(browser, scheme=scheme)
            vals = pgn.evaluate('''() => {
                const parse = c => { const m = c.match(/rgba?\\(([^)]+)\\)/); const p = m[1].split(',').map(parseFloat); return {r: p[0], g: p[1], b: p[2]}; };
                const lin = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
                const lum = c => 0.2126 * lin(c.r) + 0.7152 * lin(c.g) + 0.0722 * lin(c.b);
                const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
                const cs = getComputedStyle(document.documentElement);
                const surf = parse(getComputedStyle(document.querySelector('.panel')).backgroundColor);
                const ring = parse(getComputedStyle(document.querySelector('.opt span'), '::before').borderTopColor);
                const zones = ['.z1', '.z2', '.z3', '.z4'].map(s => ratio(parse(getComputedStyle(document.querySelector(s)).backgroundColor), surf));
                return {ring: ratio(ring, surf), zones: zones};
            }''')
            eq('%s radio ring contrast' % scheme, vals['ring'] >= ring_need, True)
            eq('%s meter zones contrast with the card' % scheme, [z >= 3.0 for z in vals['zones']], [True] * 4)
            cx.close()

    with section('ios zoom guard'):
        cz, pgz = new_page(browser)
        pgz.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
        apply(pgz, {'platform': 'ebay'})
        tap(pgz, '#saveBtn')
        pgz.evaluate("document.getElementById('sheet').hidden = false")
        res = pgz.evaluate('''() => [...document.querySelectorAll('input, select, textarea')].filter(el => el.type !== 'hidden' && el.type !== 'checkbox' && el.type !== 'radio')
            .map(el => [el.tagName + '#' + el.id, parseFloat(getComputedStyle(el).fontSize)])''')
        eq('controls checked', len(res) >= 5, True)
        eq('every text control is 16px or larger', [r for r in res if r[1] < 16], [])
        cz.close()

    with section('tap targets'):
        cq, pgq = new_page(browser)
        apply(pgq, LOCAL, ask=420, typ=560, card='RX 9070 XT')
        for _ in range(2):
            tap(pgq, '#saveBtn')
            tap(pgq, '#saveForm button[type=submit]')
        small = pgq.evaluate('''() => [...document.querySelectorAll('button, summary, .links a, label.opt')].filter(e => e.getClientRects().length).map(e => {
            const r = e.getBoundingClientRect(); return [e.id || e.className || e.tagName, Math.round(r.width), Math.round(r.height)]; })
            .filter(x => x[2] < 40 || x[1] < 40)''')
        small = [s for s in small if 'mail-copy' not in str(s[0])]
        eq('no undersized tap targets', small, [])
        cq.close()

    if STANDALONE:
        with section('standalone: fonts'):
            cf, pgf = new_page(browser)
            res = pgf.evaluate('''async () => {
                const out = [];
                for (const f of [...document.fonts]) {
                    try { await f.load(); out.push(f.family.replace(/["']/g, '') + ' ' + f.weight + ' ' + f.status); }
                    catch (e) { out.push(f.family + ' ' + f.weight + ' ERROR ' + e.message); }
                }
                return out;
            }''')
            eq('6 faces declared', len(res), 6)
            eq('every face loads', [r for r in res if not r.endswith(' loaded')], [])
            eq('display font ready', pgf.evaluate('''document.fonts.check("700 30px 'Chakra Petch'")'''), True)
            eq('body font ready', pgf.evaluate('''document.fonts.check("400 16px 'Public Sans'")'''), True)
            eq('mono font ready', pgf.evaluate('''document.fonts.check("400 13px 'IBM Plex Mono'")'''), True)
            eq('h1 uses display font', pgf.evaluate("getComputedStyle(document.querySelector('.masthead h1')).fontFamily").startswith('"Chakra Petch"'), True)
            eq('tabular digits survive the subset', pgf.evaluate('''() => {
                const w = (t) => {
                    const s = document.createElement('span');
                    s.style.cssText = "font:400 16px 'Public Sans';position:absolute;visibility:hidden;white-space:pre;font-variant-numeric:tabular-nums";
                    s.textContent = t; document.body.appendChild(s);
                    const r = s.getBoundingClientRect().width; s.remove(); return r;
                };
                return w('1111') === w('0000') && w('1111') > 0;
            }'''), True)
            cf.close()

        with section('standalone: metadata'):
            cm, pgm = new_page(browser)
            eq('document title', pgm.title(), SITE_TITLE)
            eq('lang', pgm.evaluate('document.documentElement.lang'), 'en')
            eq('description length', 60 < len(pgm.get_attribute('meta[name=description]', 'content')) <= 160, True)
            eq('canonical', pgm.get_attribute('link[rel=canonical]', 'href'), SITE_URL)
            eq('og:title', pgm.get_attribute('meta[property="og:title"]', 'content'), SITE_TITLE)
            eq('og:image', pgm.get_attribute('meta[property="og:image"]', 'content'), SITE_URL + 'og.png')
            eq('twitter card', pgm.get_attribute('meta[name="twitter:card"]', 'content'), 'summary_large_image')
            eq('theme colors', pgm.evaluate("[...document.querySelectorAll('meta[name=theme-color]')].map(m => m.content)"), ['#E8EAF4', '#0C0E1E'])
            eq('favicon is a data uri', (pgm.get_attribute('link[rel=icon]', 'href') or '').startswith('data:image/svg+xml;base64,'), True)
            eq('apple touch icon', pgm.get_attribute('link[rel=apple-touch-icon]', 'href'), 'apple-touch-icon.png')
            eq('mailto anchor', pgm.get_attribute('a.mail', 'href'), 'mailto:' + SUPPORT)
            eq('privacy link', pgm.get_attribute('.foot a[href="privacy.html"]', 'href'), 'privacy.html')
            eq('home link', pgm.get_attribute('.foot a[href="https://sanjixysti-creator.github.io/"]', 'href'), 'https://sanjixysti-creator.github.io/')
            eq('maker line', 'Made by Xysti Software' in txt(pgm, '.foot'), True)
            cm.close()

        for scheme in ('light', 'dark'):
            with section('standalone: privacy ' + scheme):
                cp, pgp = new_page(browser, scheme=scheme, url=ORIGIN + PAGE_PATH + 'privacy.html')
                eq('privacy title', pgp.title(), 'Privacy Policy - Used GPU Check')
                has('privacy says no analytics', txt(pgp, 'body'), 'no analytics')
                eq('privacy mailto', pgp.get_attribute('a[href^="mailto:"]', 'href'), 'mailto:' + SUPPORT)
                eq('privacy back link', pgp.get_attribute('.back', 'href'), './')
                for w in (320, 390, 768, 1200):
                    o = overflow(pgp, w)
                    eq('privacy no overflow %s %d' % (scheme, w), (o['sw'] <= o['W'], o['bad']), (True, []))
                pgp.set_viewport_size({'width': 390, 'height': 844})
                pgp.screenshot(path=D + '/gpu-privacy-%s.png' % scheme, full_page=True)
                eq('privacy body bg %s' % scheme, pgp.evaluate("getComputedStyle(document.body).backgroundColor"),
                   'rgb(232, 234, 244)' if scheme == 'light' else 'rgb(12, 14, 30)')
                cp.close()

        with section('standalone: no request leaves the site'):
            eq('external requests', sorted(set(ext_reqs)), [])

    browser.close()

# ---------------------------------------------------------------- report
real_errs = [e for e in errs if not (e[0] == 'warning' and 'font' in e[1].lower())]
if real_errs:
    fails.append('console errors\n    %r' % (real_errs[:6],))

print('checks passed: %d, failed: %d' % (passes, len(fails)))
for f in fails:
    print('FAIL', f)
httpd.shutdown()
raise SystemExit(1 if fails else 0)
