import contextlib, functools, http.server, json, math, os, random, re, struct, threading
from playwright.sync_api import sync_playwright

D = os.path.dirname(os.path.abspath(__file__))
SRC = D + '/rinse-mix.html'
OUT = D + '/rm-test.html'

# RM_STANDALONE=/path/to/site/rinse-mix/index.html tests the self-hosted page instead of the artifact fragment.
STANDALONE = os.environ.get('RM_STANDALONE', '')
SITE_URL = 'https://sanjixysti-creator.github.io/rinse-mix/'
SITE_TITLE = 'Rinse Mix: Free Soft Wash Mix Calculator'
STORE = 'rinse-mix-v1'

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
    PAGE_PATH = '/rm-test.html'
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

L_PER_GAL = 3.785411784
OZ = 128.0


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


def near(name, got, want, tol=1e-9):
    global passes
    ok = got is not None and abs(got - want) <= tol * max(1.0, abs(want))
    if ok:
        passes += 1
    else:
        fails.append('%s\n    got:  %r\n    want: %r' % (name, got, want))


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


def tiles(page):
    return {
        'sh': (txt(page, '#shN'), txt(page, '#shU')),
        'water': (txt(page, '#waterN'), txt(page, '#waterU')),
        'soap': (txt(page, '#soapN'), txt(page, '#soapU')),
    }


def liters(page, prefix):
    v = page.get_attribute('#' + prefix + 'Val', 'data-liters')
    return float(v) if v not in (None, '') else None


def pressed(page, group):
    return page.evaluate("id => [...document.querySelectorAll('#' + id + ' button[aria-pressed=true]')].map(b => b.textContent.trim())", group)


def alert(page):
    if not page.is_visible('#mixAlert'):
        return ('', '')
    cls = (page.get_attribute('#mixAlert', 'class') or '').replace('alert', '').strip()
    return (cls, txt(page, '#mixAlert p'))


def read_copied(page):
    return page.evaluate('window.__copied') or ''


def copied(page):
    page.evaluate('window.__copied = null')
    tap(page, '#copyBtn')
    page.wait_for_timeout(80)
    return read_copied(page)


def toast(page):
    return txt(page, '#toast') if page.is_visible('#toast') else ''


def overflow(page, w):
    page.set_viewport_size({'width': w, 'height': 900})
    page.wait_for_timeout(120)
    return page.evaluate('''() => {
        const W = document.documentElement.clientWidth;
        const bad = [];
        document.querySelectorAll('body *').forEach(el => {
            if (getComputedStyle(el).position === 'fixed') return;
            const r = el.getBoundingClientRect();
            if (r.width && (r.right > W + 1 || r.left < -1)) bad.push(el.tagName + '.' + el.className + '#' + el.id);
        });
        return {sw: document.documentElement.scrollWidth, W: W, bad: bad.slice(0, 6)};
    }''')


def ref(batch_l, target, sh, dose):
    V, t, s, d = batch_l, target / 100.0, sh / 100.0, min(1.0, max(0.0, dose))
    if not V > 0:
        return ('batch',)
    if not s > 0:
        return ('sh',)
    if not t > 0:
        return ('target',)
    f = t / s
    if f + d > 1 + 1e-12:
        return ('strong', s * (1 - d) * 100)
    shl, soap = V * f, V * d
    return ('ok', shl, max(0.0, V - shl - soap), soap)


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

CONTRAST_SELS = ['.tagline', '.hint', '.fine', '.lab', '.mname', '.msub', '.mval', '.mval .u', '.chip', '.chip[aria-pressed="true"]',
                 '.btn', '.btn.ghost', '.seg button', '.seg button[aria-pressed="true"]', '.safety-line', '.chart th', '.chart td',
                 '.chart tr.is-now td', '.foot', '.foot a', '.b-lab span', '.b-amt', '.sv-out', '.sv-sum', '.affix .suf', '.affix .pre',
                 '.alert.info p', '.alert.warn p', '.alert.bad p', '.panel.safety .bullets li', '.ledger dt', '.ledger dd', '.surface-note',
                 '.rates summary .h2', '.faq summary', '.faq p']

# ---------------------------------------------------------------- source hygiene
with section('source hygiene'):
    eq('no em dash', '\u2014' in src, False)
    eq('no en dash', '\u2013' in src, False)
    eq('title first', src.startswith('<title>Rinse Mix</title>'), True)
    eq('no document tags', bool(re.search(r'<(html|head|body)[\s>]', src)), False)
    eq('no print', 'window.print' in src, False)
    eq('no mailto links', 'mailto:' in src, False)
    eq('no dialogs', bool(re.search(r'\b(alert|confirm|prompt)\(', src)), False)
    eq('no external scripts', re.findall(r'<script[^>]*\bsrc=', src), [])
    eq('no innerHTML', 'innerHTML' in src, False)
    hosts = set(re.findall(r'https?://([a-z0-9.\-]+)', src))
    eq('only allowed hosts', sorted(hosts - {'fonts.googleapis.com', 'fonts.gstatic.com', 'sanjixysti-creator.github.io'}), [])
    eq('one mail span', src.count('<span class="mail"></span>'), 1)

    if STANDALONE:
        eq('built: doctype first', built.lstrip().lower().startswith('<!doctype html>'), True)
        eq('built: no em dash', '\u2014' in built, False)
        eq('built: no en dash', '\u2013' in built, False)
        eq('built: title', ('<title>%s</title>' % SITE_TITLE) in built, True)
        eq('built: no google fonts', 'fonts.googleapis.com' in built or 'fonts.gstatic.com' in built, False)
        eq('built: no claude.ai link', 'claude.ai' in built.lower(), False)
        eq('built: no external scripts', re.findall(r'<script[^>]*\bsrc=', built), [])
        bh = set(re.findall(r'https?://([a-z0-9.\-]+)', built))
        eq('built: only own hosts', sorted(bh - {'www.w3.org', 'sanjixysti-creator.github.io'}), [])
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

with sync_playwright() as p:
    try:
        browser = p.chromium.launch()
    except Exception:
        browser = p.chromium.launch(executable_path='/opt/pw-browsers/chromium-1194/chrome-linux/chrome')

    # ------------------------------------------------------------ 1 first paint, phone, light
    ctx1, page = new_page(browser)

    with section('first paint'):
        page.screenshot(path=D + '/rm-phone.png', full_page=True)
        page.screenshot(path=D + '/rm-light-top.png')
        page.locator('#mixCard').screenshot(path=D + '/rm-light-card.png')
        t = tiles(page)
        eq('SH tile', t['sh'], ('12', 'gal'))
        eq('water tile', t['water'], ('37.61', 'gal'))
        eq('soap tile', t['soap'], ('50', 'fl oz'))
        eq('mix sub', txt(page, '#mixSub'), '50 gal at 3%')
        eq('sh sub', txt(page, '#shSub'), '12.5% SH, 24% of the batch')
        eq('water sub', txt(page, '#waterSub'), 'Top up to 50 gal total')
        eq('soap sub', txt(page, '#soapSub'), '1 fl oz per gal, 0.78% of the batch')
        eq('alt units', txt(page, '#altUnits'), 'In metric: SH 45.42 L, water 142.37 L, surfactant 1.48 L.')
        eq('no alert on defaults', alert(page), ('', ''))
        eq('batch field', page.input_value('#batch'), '50')
        eq('target field', page.input_value('#target'), '3')
        eq('sh field', page.input_value('#shPct'), '12.5')
        eq('dose field', page.input_value('#dose'), '1')
        eq('batch chip', pressed(page, 'batchChips'), ['50'])
        eq('target chip', pressed(page, 'targetChips'), ['3%'])
        eq('sh chip', pressed(page, 'shChips'), ['12.5%'])
        eq('dose chip', pressed(page, 'doseChips'), ['1'])
        eq('bar SH', (txt(page, '#bAmtSh'), txt(page, '#bLabSh')), ('12', 'SH, gal'))
        eq('bar water', (txt(page, '#bAmtWater'), txt(page, '#bLabWater')), ('37.61', 'Water, gal'))
        eq('bar soap', (txt(page, '#bAmtSoap'), txt(page, '#bLabSoap')), ('50', 'Soap, fl oz'))
        eq('bar visible on phone', page.is_visible('#bar'), True)
        eq('bar hidden from AT', page.get_attribute('#bar', 'aria-hidden'), 'true')
        eq('cost ledger hidden', page.is_visible('#costLedger'), False)
        eq('surface note hidden', page.is_visible('#surfaceNote'), False)
        eq('save form hidden', page.is_visible('#saveForm'), False)
        near('SH liters', liters(page, 'sh'), 50 * L_PER_GAL * 0.24)
        near('soap liters', liters(page, 'soap'), 50 * L_PER_GAL / 128)
        near('water liters', liters(page, 'water'), 50 * L_PER_GAL * (1 - 0.24 - 1 / 128.0))
        eq('bar label', page.get_attribute('#stackBar', 'aria-label'),
           'Share of the batch: water 75.2%, sodium hypochlorite 24%, surfactant 0.78%')
        eq('units pressed', (page.get_attribute('#unitUs', 'aria-pressed'), page.get_attribute('#unitMetric', 'aria-pressed')), ('true', 'false'))
        eq('batch unit suffix', txt(page, '#batchUnit'), 'gal')
        eq('dose unit suffix', txt(page, '#doseUnit'), 'fl oz per gal')
        eq('mail text', txt(page, '.mail'), SUPPORT)

    with section('math lines'):
        page.evaluate("document.getElementById('mathBox').open = true")
        lines = [txt(page, '#mathLines p:nth-child(%d)' % i) for i in (1, 2, 3)]
        eq('sh line', lines[0], 'SH = 50 gal × 3% ÷ 12.5% = 12 gal')
        eq('soap line', lines[1], 'Surfactant = 50 gal × 1 fl oz per gal = 50 fl oz')
        eq('water line', lines[2], 'Water = 50 gal - 12 gal - 0.39 gal = 37.61 gal')

    with section('quick chart defaults'):
        rows = page.evaluate("[...document.querySelectorAll('#chartBody tr')].map(tr => [...tr.children].map(td => td.textContent.trim()))")
        eq('nine chart rows', len(rows), 9)
        eq('chart 1%', rows[1], ['1%', '4 gal', '45.61 gal'])
        eq('chart 3%', rows[3], ['3%', '12 gal', '37.61 gal'])
        eq('chart 10%', rows[8], ['10%', '40 gal', '9.61 gal'])
        eq('current row marked', page.evaluate("[...document.querySelectorAll('#chartBody tr.is-now')].map(tr => tr.children[0].textContent.trim())"), ['3%'])
        eq('chart note', txt(page, '#chartNote'), 'For 50 gal with 12.5% SH and 1 fl oz per gal of surfactant.')
        tap(page, '#chartBody tr:nth-child(2) .pick')
        page.wait_for_timeout(60)
        eq('chart pick sets strength', page.input_value('#target'), '1')
        eq('chart pick SH', tiles(page)['sh'], ('4', 'gal'))
        eq('chart pick chip', pressed(page, 'targetChips'), ['1%'])
        tap(page, '#chartBody tr:nth-child(4) .pick')


    with section('faq'):
        eq('five questions', page.evaluate("document.querySelectorAll('#faq details').length"), 5)
        eq('questions start closed', page.evaluate("[...document.querySelectorAll('#faq details')].filter(d => d.open).length"), 0)
        tap(page, '#faq details:nth-child(1) summary')
        eq('first question opens', page.evaluate("document.querySelector('#faq details:nth-child(1)').open"), True)
        has('first answer worked example', txt(page, '#faq details:nth-child(1) p'), 'a 50 gallon tank takes 12 gallons of SH')
        tap(page, '#faq details:nth-child(1) summary')
        eq('first question closes', page.evaluate("document.querySelector('#faq details:nth-child(1)').open"), False)
        eq('summaries are tall enough to tap', page.evaluate("[...document.querySelectorAll('#faq summary')].every(s => s.getBoundingClientRect().height >= 44)"), True)
        eq('faq text has no em dash', '\u2014' in txt(page, '#faq'), False)

    # ------------------------------------------------------------ 2 chips and typing
    with section('chips and typing'):
        tap(page, '#batchChips button[data-v="15"]')
        page.wait_for_timeout(60)
        eq('15 gal batch field', page.input_value('#batch'), '15')
        t = tiles(page)
        eq('15 gal SH', t['sh'], ('3.6', 'gal'))
        eq('15 gal water', t['water'], ('11.28', 'gal'))
        eq('15 gal soap', t['soap'], ('15', 'fl oz'))
        eq('15 gal chip', pressed(page, 'batchChips'), ['15'])

        tap(page, '#doseChips button[data-v="0"]')
        page.wait_for_timeout(60)
        eq('no surfactant tile', tiles(page)['soap'], ('None', ''))
        eq('no surfactant sub', txt(page, '#soapSub'), 'Not using any')
        eq('no surfactant bar', txt(page, '#bAmtSoap'), 'None')
        eq('no surfactant water', tiles(page)['water'], ('11.4', 'gal'))
        eq('dose field zero', page.input_value('#dose'), '0')
        eq('dose none chip', pressed(page, 'doseChips'), ['None'])
        eq('no surfactant math', txt(page, '#mathLines p:nth-child(2)'), 'Surfactant = none')

        # trade table check: 50 gal at 1% from 12.5% SH, no surfactant, is 4 gal SH and 46 gal water
        put(page, '#batch', '50')
        put(page, '#target', '1')
        put(page, '#shPct', '12.5')
        eq('50 gal 1% SH', tiles(page)['sh'], ('4', 'gal'))
        eq('50 gal 1% water', tiles(page)['water'], ('46', 'gal'))
        put(page, '#target', '3')
        eq('50 gal 3% SH', tiles(page)['sh'], ('12', 'gal'))
        eq('50 gal 3% water', tiles(page)['water'], ('38', 'gal'))

        # small batch: under a gallon shows fluid ounces, with the gallon figure beside it
        put(page, '#batch', '5')
        put(page, '#target', '1')
        eq('5 gal 1% SH in oz', tiles(page)['sh'], ('51', 'fl oz'))
        eq('5 gal 1% SH sub', txt(page, '#shSub'), '12.5% SH, 8% of the batch, 0.4 gal')
        eq('5 gal water', tiles(page)['water'], ('4.6', 'gal'))
        eq('bar SH label small', txt(page, '#bLabSh'), 'SH, fl oz')

        # comma as the decimal mark, and stray characters
        put(page, '#batch', '12,5')
        eq('comma batch', tiles(page)['sh'], ('1', 'gal'))
        near('comma batch liters', liters(page, 'water') + liters(page, 'sh') + liters(page, 'soap'), 12.5 * L_PER_GAL)
        put(page, '#batch', '1,000')
        near('thousands batch liters', liters(page, 'water') + liters(page, 'sh') + liters(page, 'soap'), 1000 * L_PER_GAL)
        put(page, '#shPct', '12.5%')
        near('percent sign ignored', liters(page, 'sh'), 1000 * L_PER_GAL * 0.01 / 0.125)
        put(page, '#batch', '50')
        put(page, '#target', '3')
        put(page, '#dose', '1')

    # ------------------------------------------------------------ 3 alerts
    with section('alerts'):
        put(page, '#shPct', '8.25')
        put(page, '#target', '10')
        put(page, '#dose', '1')
        kind, msg = alert(page)
        eq('too strong kind', kind, 'bad')
        has('too strong text', msg, 'That strength is out of reach.')
        has('too strong max with surfactant', msg, 'the most you can mix is 8.18%')
        has('mentions surfactant', msg, '1 fl oz per gal of surfactant')
        eq('tiles dashed', tiles(page)['sh'], ('-', ''))
        eq('bar dashed', txt(page, '#bAmtSh'), '-')
        eq('copy disabled', page.is_disabled('#copyBtn'), True)
        eq('save disabled', page.is_disabled('#saveBtn'), True)
        eq('fix button', txt(page, '#mixAlert button'), 'Use 8.18%')
        page.screenshot(path=D + '/rm-error.png')
        # quick chart hides rows that cannot be made and says why
        eq('chart hides impossible rows', page.evaluate("[...document.querySelectorAll('#chartBody tr')].map(tr => tr.children[0].textContent.trim())"),
           ['0.5%', '1%', '2%', '3%', '4%', '5%', '6%', '8%'])
        has('chart note mentions stronger SH', txt(page, '#chartNote'), 'Higher strengths need a stronger SH.')
        tap(page, '#mixAlert button')
        page.wait_for_timeout(60)
        eq('fix applies', page.input_value('#target'), '8.18')
        eq('fix clears alert kind', alert(page)[0], 'warn')   # more than half is SH, so a gentle warning remains
        eq('fix made a mix', tiles(page)['sh'][1], 'gal')
        eq('copy enabled again', page.is_disabled('#copyBtn'), False)

        put(page, '#dose', '0')
        put(page, '#target', '8.25')
        eq('exact max with no surfactant is allowed', tiles(page)['water'], ('0', 'gal'))
        put(page, '#target', '8.26')
        has('max with no surfactant', alert(page)[1], 'the most you can mix is 8.25%')
        eq('no surfactant wording', 'of surfactant' in alert(page)[1], False)

        put(page, '#dose', '1')
        put(page, '#shPct', '12.5')
        put(page, '#target', '8')
        kind, msg = alert(page)
        eq('half SH warning kind', kind, 'warn')
        has('half SH warning text', msg, 'More than half of the batch is SH')
        eq('half SH still calculates', tiles(page)['sh'], ('32', 'gal'))

        put(page, '#target', '3')
        put(page, '#shPct', '20')
        kind, msg = alert(page)
        eq('strong SH warn kind', kind, 'warn')
        has('strong SH warn text', msg, 'does not usually come stronger than 15%')
        put(page, '#shPct', '12.5')

        put(page, '#dose', '10')
        kind, msg = alert(page)
        eq('lot of surfactant kind', kind, 'warn')
        has('lot of surfactant text', msg, 'Surfactant is 7.8% of the batch')
        put(page, '#dose', '1')

        put(page, '#batch', '')
        eq('empty batch info kind', alert(page)[0], 'info')
        has('empty batch text', alert(page)[1], 'Enter how many gallons the tank will hold.')
        eq('empty batch dashes', tiles(page)['water'], ('-', ''))
        eq('empty chart', page.is_visible('#chartEmpty'), True)
        eq('empty chart hides table', page.is_visible('#chartWrap'), False)
        eq('empty math', 'Enter a batch size' in txt(page, '#mathLines'), True)
        put(page, '#batch', '50')
        put(page, '#shPct', '')
        has('empty SH text', alert(page)[1], 'Enter the strength printed on your SH label')
        put(page, '#shPct', '12.5')
        put(page, '#target', '')
        has('empty target text', alert(page)[1], 'Enter the strength you want in the mix')
        put(page, '#target', '3')
        eq('recovered', alert(page), ('', ''))
        eq('recovered tiles', tiles(page)['sh'], ('12', 'gal'))

    # ------------------------------------------------------------ 4 metric
    with section('metric'):
        tap(page, '#unitMetric')
        page.wait_for_timeout(60)
        eq('metric pressed', (page.get_attribute('#unitUs', 'aria-pressed'), page.get_attribute('#unitMetric', 'aria-pressed')), ('false', 'true'))
        eq('metric batch field', page.input_value('#batch'), '189.27')
        eq('metric batch suffix', txt(page, '#batchUnit'), 'L')
        eq('metric dose suffix', txt(page, '#doseUnit'), 'mL per L')
        eq('metric dose label', txt(page, '#doseLab'), 'Dose per liter of mix')
        eq('metric dose field', page.input_value('#dose'), '7.81')
        eq('metric chips', [b for b in page.evaluate("[...document.querySelectorAll('#batchChips button')].map(b => b.textContent.trim())")], ['20', '50', '100', '200', '400'])
        eq('metric dose chips', page.evaluate("[...document.querySelectorAll('#doseChips button')].map(b => b.textContent.trim())"), ['None', '5', '10', '20'])
        t = tiles(page)
        eq('metric SH', t['sh'], ('45.42', 'L'))
        eq('metric water', t['water'], ('142.37', 'L'))
        eq('metric soap', t['soap'], ('1.48', 'L'))
        eq('metric alt line', txt(page, '#altUnits'), 'In US units: SH 12 gal, water 37.61 gal, surfactant 50 fl oz.')
        eq('metric mix sub', txt(page, '#mixSub'), '189.27 L at 3%')
        eq('metric soap sub', txt(page, '#soapSub'), '7.81 mL per L, 0.78% of the batch')
        eq('metric bar', (txt(page, '#bAmtSh'), txt(page, '#bLabSh')), ('45.42', 'SH, L'))
        tap(page, '#batchChips button[data-v="200"]')
        page.wait_for_timeout(60)
        eq('200 L field', page.input_value('#batch'), '200')
        eq('200 L chip', pressed(page, 'batchChips'), ['200'])
        t = tiles(page)
        eq('200 L SH', t['sh'], ('48', 'L'))
        eq('200 L soap', t['soap'], ('1.56', 'L'))
        eq('200 L water', t['water'], ('150.44', 'L'))
        tap(page, '#doseChips button[data-v="5"]')
        page.wait_for_timeout(60)
        eq('5 mL per L soap', tiles(page)['soap'], ('1', 'L'))
        put(page, '#batch', '10')
        eq('small metric batch soap in mL', tiles(page)['soap'], ('50', 'mL'))
        eq('small metric SH in L', tiles(page)['sh'], ('2.4', 'L'))
        put(page, '#batch', '0,5')
        eq('half a liter SH in mL', tiles(page)['sh'], ('120', 'mL'))
        eq('half a liter SH sub', txt(page, '#shSub'), '12.5% SH, 24% of the batch, 0.12 L')
        put(page, '#batch', '189,27')
        # back to US: values come back clean
        tap(page, '#unitUs')
        page.wait_for_timeout(60)
        eq('US batch after round trip', page.input_value('#batch'), '50')
        eq('US dose after metric edit', page.input_value('#dose'), '0.64')
        tap(page, '#doseChips button[data-v="1"]')
        page.wait_for_timeout(60)
        put(page, '#batch', '50')
        eq('unit round trip keeps SH', tiles(page)['sh'], ('12', 'gal'))

    # ------------------------------------------------------------ 5 cost and injector
    with section('cost'):
        page.evaluate("document.getElementById('costBox').open = true")
        put(page, '#shPrice', '3.5')
        eq('ledger shown', page.is_visible('#costLedger'), True)
        eq('SH cost', txt(page, '#costSh'), '$42.00')
        eq('soap cost with no price', txt(page, '#costSoap'), '$0.00')
        eq('batch cost', txt(page, '#costBatch'), '$42.00')
        eq('per gallon', txt(page, '#costPer'), '$0.84')
        put(page, '#soapPrice', '30')
        eq('soap cost', txt(page, '#costSoap'), '$11.72')
        eq('batch cost total', txt(page, '#costBatch'), '$53.72')
        eq('per gallon total', txt(page, '#costPer'), '$1.07')
        eq('per label US', txt(page, '#costPerLab'), 'Per gallon of mix')
        text = copied(page)
        has('copy has cost', text, 'Cost: $53.72 per batch, $1.07 per gallon of mix')
        tap(page, '#unitMetric')
        page.wait_for_timeout(60)
        eq('metric SH price field', page.input_value('#shPrice'), '0.92')
        eq('metric per label', txt(page, '#costPerLab'), 'Per liter of mix')
        eq('metric per liter', txt(page, '#costPer'), '$0.28')
        eq('metric batch cost unchanged', txt(page, '#costBatch'), '$53.72')
        tap(page, '#unitUs')
        page.wait_for_timeout(60)
        eq('US price back', page.input_value('#shPrice'), '3.50')
        put(page, '#shPrice', '')
        put(page, '#soapPrice', '')
        eq('ledger hidden again', page.is_visible('#costLedger'), False)

    with section('injector'):
        page.evaluate("document.getElementById('injBox').open = true")
        eq('draw prompt', txt(page, '#drawOut'), 'Enter a draw to see the strength at the surface.')
        put(page, '#draw', '10')
        eq('surface note shown', page.is_visible('#surfaceNote'), True)
        eq('surface note text', txt(page, '#surfaceNote'), 'At the surface, with a 10% draw, the spray is about 0.3% SH.')
        eq('draw out text', txt(page, '#drawOut'), 'At the surface, with a 10% draw, the spray is about 0.3% SH.')
        put(page, '#target', '12.4')
        eq('surface 12.4', txt(page, '#surfaceNote'), 'At the surface, with a 10% draw, the spray is about 1.24% SH.')
        text = copied(page)
        has('copy has surface line', text, 'At the surface with a 10% draw: about 1.24% SH')
        put(page, '#target', '3')
        put(page, '#draw', '')
        eq('surface note hidden without draw', page.is_visible('#surfaceNote'), False)

    # ------------------------------------------------------------ 6 copy
    with section('copy'):
        text = copied(page)
        eq('copy text', text, '\n'.join([
            'Soft wash mix',
            'Batch: 50 gal at 3% strength',
            'Sodium hypochlorite (12.5%): 12 gal',
            'Water: 37.61 gal (top up to 50 gal)',
            'Surfactant (1 fl oz per gal): 50 fl oz']))
        eq('toast on copy', toast(page), 'Mix copied.')
        eq('a tap under the toast reaches the page', page.evaluate("(() => { const t = document.getElementById('toast'); const r = t.getBoundingClientRect(); const e = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2); return !!e && !t.contains(e); })()"), True)
        tap(page, '#unitMetric')
        page.wait_for_timeout(60)
        text = copied(page)
        has('metric copy batch', text, 'Batch: 189.27 L at 3% strength')
        has('metric copy SH', text, 'Sodium hypochlorite (12.5%): 45.42 L')
        has('metric copy soap', text, 'Surfactant (7.81 mL per L): 1.48 L')
        tap(page, '#unitUs')
        page.wait_for_timeout(60)
        tap(page, '#doseChips button[data-v="0"]')
        text = copied(page)
        has('copy without surfactant', text, 'Surfactant: none')
        tap(page, '#doseChips button[data-v="1"]')

    # ------------------------------------------------------------ 7 saved mixes and persistence
    with section('saved mixes'):
        eq('empty saved text', 'No saved mixes yet' in txt(page, '#savedList'), True)
        tap(page, '#saveBtn')
        eq('save form opens', page.is_visible('#saveForm'), True)
        eq('save name focused', page.evaluate("document.activeElement && document.activeElement.id"), 'saveName')
        put(page, '#saveName', 'Roof, 3%')
        page.locator('#saveForm button[type=submit]').evaluate('e => e.click()')
        page.wait_for_timeout(80)
        eq('save form closes', page.is_visible('#saveForm'), False)
        eq('saved toast', toast(page), 'Saved Roof, 3%.')
        eq('saved name', txt(page, '#savedList .sv-name'), 'Roof, 3%')
        eq('saved summary', txt(page, '#savedList .sv-sum'), '50 gal at 3% from 12.5% SH')
        eq('saved output', txt(page, '#savedList .sv-out'), 'SH 12 gal, water 37.61 gal, surfactant 50 fl oz')

        put(page, '#batch', '15')
        put(page, '#target', '1')
        tap(page, '#saveBtn')
        tap(page, '#saveForm button[type=submit]')     # blank name uses the auto label
        page.wait_for_timeout(80)
        eq('two saved', page.evaluate("document.querySelectorAll('#savedList .saved').length"), 2)
        eq('newest first with auto name', txt(page, '#savedList .saved:nth-child(1) .sv-name'), '15 gal at 1%')

        tap(page, '#unitMetric')
        page.wait_for_timeout(60)
        eq('saved summary re-worded in metric', txt(page, '#savedList .saved:nth-child(2) .sv-sum'), '189.27 L at 3% from 12.5% SH')
        tap(page, '#unitUs')
        page.wait_for_timeout(60)

        tap(page, '#savedList .saved:nth-child(2) .btn.sm:not(.ghost)')
        page.wait_for_timeout(80)
        eq('use mix batch', page.input_value('#batch'), '50')
        eq('use mix target', page.input_value('#target'), '3')
        eq('use mix toast', toast(page), 'Loaded Roof, 3%.')

        page.reload()
        page.wait_for_timeout(250)
        eq('saved survives reload', page.evaluate("document.querySelectorAll('#savedList .saved').length"), 2)
        eq('values survive reload', (page.input_value('#batch'), page.input_value('#target'), page.input_value('#shPct')), ('50', '3', '12.5'))
        stored = page.evaluate("JSON.parse(localStorage.getItem('%s'))" % STORE)
        eq('stored version', stored['v'], 1)
        eq('stored unit', stored['unit'], 'us')
        eq('stored saved count', len(stored['saved']), 2)

        # two-tap delete
        btn = '#savedList .saved:nth-child(1) .btn.ghost'
        eq('delete idle label', txt(page, btn), 'Delete')
        tap(page, btn)
        eq('delete armed label', txt(page, btn), 'Tap again to delete')
        eq('still two after one tap', page.evaluate("document.querySelectorAll('#savedList .saved').length"), 2)
        tap(page, btn)
        page.wait_for_timeout(80)
        eq('deleted', page.evaluate("document.querySelectorAll('#savedList .saved').length"), 1)
        eq('remaining is the roof', txt(page, '#savedList .sv-name'), 'Roof, 3%')

        # cannot save a broken mix
        put(page, '#shPct', '5')
        put(page, '#target', '9')
        eq('save disabled when broken', page.is_disabled('#saveBtn'), True)
        put(page, '#shPct', '12.5')
        put(page, '#target', '3')

        # reset
        put(page, '#batch', '77')
        tap(page, '#resetBtn')
        eq('reset armed', txt(page, '#resetBtn'), 'Tap again to reset')
        tap(page, '#resetBtn')
        page.wait_for_timeout(60)
        eq('reset restores', (page.input_value('#batch'), page.input_value('#target'), page.input_value('#shPct'), page.input_value('#dose')), ('50', '3', '12.5', '1'))
        eq('reset keeps saved', page.evaluate("document.querySelectorAll('#savedList .saved').length"), 1)

    with section('saved cap'):
        many = {'v': 1, 'unit': 'us', 'batchL': 189.27, 'targetPct': 3, 'shPct': 12.5, 'dose': 0.0078125, 'seq': 40,
                'saved': [{'id': 'm%d' % i, 'name': 'Mix %d' % i, 'batchL': 100, 'targetPct': 2, 'shPct': 12.5, 'dose': 0, 'ts': i} for i in range(30)]}
        c2, pg2 = new_page(browser, pre_state=json.dumps(many))
        eq('thirty saved show', pg2.evaluate("document.querySelectorAll('#savedList .saved').length"), 30)
        tap(pg2, '#saveBtn')
        tap(pg2, '#saveForm button[type=submit]')
        pg2.wait_for_timeout(80)
        has('cap toast', toast(pg2), 'You can keep 30 mixes.')
        eq('still thirty', pg2.evaluate("document.querySelectorAll('#savedList .saved').length"), 30)
        c2.close()

    with section('hostile storage'):
        junk = [
            '{"v":1,"unit":"weird","batchL":"abc","targetPct":-5,"shPct":9999,"dose":50,"saved":[{"id":1,"name":"<img src=x onerror=alert(1)>","batchL":"12","targetPct":1,"shPct":12.5,"dose":0},null,5,{"nope":1}]}',
            'not json at all',
            '{"v":2}',
            '{"v":1,"saved":"nope"}',
        ]
        for i, raw in enumerate(junk):
            c3, pg3 = new_page(browser, pre_state=raw)
            eq('junk %d renders a mix or defaults' % i, tiles(pg3)['sh'][1] in ('gal', ''), True)
            eq('junk %d has no page errors' % i, [e for e in errs if e[0] == 'pageerror'], [])
            if i == 0:
                eq('junk name is text, not markup', pg3.evaluate("document.querySelectorAll('#savedList img').length"), 0)
                eq('junk name shown as text', 'onerror' in txt(pg3, '#savedList .sv-name'), True)
                eq('junk unit falls back', pg3.get_attribute('#unitUs', 'aria-pressed'), 'true')
                eq('junk SH strength clamped', pg3.input_value('#shPct'), '100')
            c3.close()

    # ------------------------------------------------------------ 8 clipboard blocked
    ctx4, pg4 = new_page(browser, stub=STUB_REJECT)
    with section('clipboard blocked'):
        tap(pg4, '#copyBtn')
        pg4.wait_for_timeout(120)
        eq('fallback sheet shows', pg4.is_visible('#sheet'), True)
        has('fallback text', pg4.input_value('#sheetText'), 'Soft wash mix')
        tap(pg4, '#sheetClose')
        eq('fallback closes', pg4.is_visible('#sheet'), False)
        tap(pg4, '.mail-copy')
        pg4.wait_for_timeout(120)
        eq('email copy fallback shows address', pg4.input_value('#sheetText'), SUPPORT)
    ctx4.close()

    # ------------------------------------------------------------ 9 math property test against a Python reference
    with section('property test'):
        c5, pg5 = new_page(browser)
        rnd = random.Random(20260930)
        checked = ok_n = strong_n = 0
        for i in range(260):
            metric = rnd.random() < 0.4
            if metric != (pg5.get_attribute('#unitMetric', 'aria-pressed') == 'true'):
                tap(pg5, '#unitMetric' if metric else '#unitUs')
            batch = round(math.exp(rnd.uniform(math.log(0.5), math.log(3000))), rnd.choice([0, 1, 2, 3]))
            if batch <= 0:
                batch = 1.0
            target = round(rnd.uniform(0.1, 14.0), rnd.choice([0, 1, 2]))
            if target <= 0:
                target = 1.0
            sh = rnd.choice([12.5, 10, 8.25, 6, 5.25, 15, round(rnd.uniform(3, 15), 2)])
            dose = 0.0 if rnd.random() < 0.15 else round(rnd.uniform(0, 4 if not metric else 30), rnd.choice([0, 1, 2]))
            put(pg5, '#batch', repr(batch))
            put(pg5, '#target', repr(target))
            put(pg5, '#shPct', repr(sh))
            put(pg5, '#dose', repr(dose))
            batch_l = batch if metric else batch * L_PER_GAL
            dose_frac = dose / 1000.0 if metric else dose / OZ
            want = ref(batch_l, target, sh, dose_frac)
            got = (liters(pg5, 'sh'), liters(pg5, 'water'), liters(pg5, 'soap'))
            label = 'case %d %s batch=%r target=%r sh=%r dose=%r' % (i, 'L' if metric else 'gal', batch, target, sh, dose)
            checked += 1
            if want[0] == 'ok':
                ok_n += 1
                near(label + ' SH', got[0], want[1], 1e-9)
                near(label + ' water', got[1], want[2], 1e-9)
                near(label + ' soap', got[2], want[3], 1e-9)
                eq(label + ' no bad alert', alert(pg5)[0] in ('', 'warn'), True)
                # volumes add up to the batch
                near(label + ' sums to batch', got[0] + got[1] + got[2], batch_l, 1e-9)
            elif want[0] == 'strong':
                strong_n += 1
                eq(label + ' error state', alert(pg5)[0], 'bad')
                eq(label + ' no volumes', got, (None, None, None))
                has(label + ' max shown', alert(pg5)[1], 'the most you can mix is %s%%' % ('%s' % (('%.2f' % (math.floor(want[1] * 100 + 1e-9) / 100.0)).rstrip('0').rstrip('.'))))
            else:
                eq(label + ' needs input', alert(pg5)[0], 'info')
        eq('property test checked cases', checked, 260)
        eq('property test saw both outcomes', (ok_n > 60, strong_n > 10), (True, True))
        c5.close()

    # ------------------------------------------------------------ 10 layouts, widths, dark, contrast
    with section('layout phone'):
        ctx6, pg6 = new_page(browser, pre_state=None)
        pg6.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
        tap(pg6, '#saveBtn')
        put(pg6, '#saveName', 'Front of house')
        tap(pg6, '#saveForm button[type=submit]')
        tap(pg6, '#saveBtn')
        put(pg6, '#shPrice', '3.5')
        put(pg6, '#soapPrice', '30')
        put(pg6, '#draw', '10')
        for w in (320, 360, 390, 768, 1200):
            o = overflow(pg6, w)
            eq('no horizontal overflow at %d' % w, (o['sw'] <= o['W'], o['bad']), (True, []))
        pg6.set_viewport_size({'width': 320, 'height': 700})
        pg6.wait_for_timeout(100)
        # the pinned bar must not cover the last thing on the page
        pg6.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        pg6.wait_for_timeout(100)
        gap = pg6.evaluate('''() => {
            const foot = document.querySelector('.foot').getBoundingClientRect();
            const bar = document.getElementById('bar').getBoundingClientRect();
            return Math.round(bar.top - foot.bottom);
        }''')
        eq('footer clear of the pinned bar', gap >= 0, True)
        # the pinned bar fits in one row of three cells
        cells = pg6.evaluate("[...document.querySelectorAll('#bar .b-cell')].map(c => { const r = c.getBoundingClientRect(); return [Math.round(r.left), Math.round(r.right), Math.round(r.top)]; })")
        eq('three bar cells on one row', len(set(c[2] for c in cells)), 1)
        eq('bar cells inside the screen', all(c[0] >= 0 and c[1] <= 320 for c in cells), True)
        eq('bar text not clipped at 320', pg6.evaluate("[...document.querySelectorAll('#bar .b-amt')].every(e => e.scrollWidth <= e.clientWidth + 1)"), True)
        pg6.set_viewport_size({'width': 390, 'height': 844})
        pg6.wait_for_timeout(100)
        pg6.evaluate('window.scrollTo(0, 0)')
        for sel, fname in (('#mixCard', 'rm-card-full.png'),):
            pg6.locator(sel).screenshot(path=D + '/' + fname)
        pg6.screenshot(path=D + '/rm-phone-open.png', full_page=True)
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
        pg7.screenshot(path=D + '/rm-desktop-light.png')
        pg7.evaluate('window.scrollTo(0, 700)')
        pg7.wait_for_timeout(120)
        eq('results stay in view when scrolled', pg7.evaluate("document.querySelector('.results').getBoundingClientRect().top") < 40, True)
        ctx7.close()
        ctx7b, pg7b = new_page(browser, w=899, h=900)
        eq('bar shows just under the breakpoint', pg7b.is_visible('#bar'), True)
        ctx7b.close()

    with section('dark'):
        ctx8, pg8 = new_page(browser, scheme='dark')
        pg8.screenshot(path=D + '/rm-dark-top.png')
        pg8.locator('#mixCard').screenshot(path=D + '/rm-dark-card.png')
        pg8.screenshot(path=D + '/rm-dark-full.png', full_page=True)
        bgc = pg8.evaluate("getComputedStyle(document.body).backgroundColor")
        eq('dark body background', bgc, 'rgb(10, 22, 21)')
        ctx8.close()
        ctx8b, pg8b = new_page(browser, scheme='dark', w=1200, h=900)
        pg8b.screenshot(path=D + '/rm-desktop-dark.png')
        ctx8b.close()
        # an explicit light choice beats a dark OS setting, and an explicit dark choice beats a light one
        ctx9, pg9 = new_page(browser, scheme='dark')
        pg9.evaluate("document.documentElement.setAttribute('data-theme', 'light')")
        eq('data-theme light wins over dark OS', pg9.evaluate("getComputedStyle(document.body).backgroundColor"), 'rgb(230, 238, 236)')
        ctx9.close()
        ctx9b, pg9b = new_page(browser, scheme='light')
        pg9b.evaluate("document.documentElement.setAttribute('data-theme', 'dark')")
        eq('data-theme dark wins over light OS', pg9b.evaluate("getComputedStyle(document.body).backgroundColor"), 'rgb(10, 22, 21)')
        ctx9b.close()

    for scheme in ('light', 'dark'):
        with section('contrast ' + scheme):
            cx, pgc = new_page(browser, scheme=scheme)
            pgc.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
            put(pgc, '#shPrice', '3.5')
            put(pgc, '#draw', '10')
            tap(pgc, '#saveBtn')
            put(pgc, '#saveName', 'x')
            tap(pgc, '#saveForm button[type=submit]')
            res = pgc.evaluate(CONTRAST_JS, CONTRAST_SELS)
            # alerts need their own states
            put(pgc, '#target', '10')
            put(pgc, '#shPct', '8.25')
            res += pgc.evaluate(CONTRAST_JS, ['.alert.bad p', '.alert.bad .btn'])
            put(pgc, '#shPct', '12.5')
            put(pgc, '#target', '8')
            res += pgc.evaluate(CONTRAST_JS, ['.alert.warn p'])
            put(pgc, '#batch', '')
            res += pgc.evaluate(CONTRAST_JS, ['.alert.info p', '.empty'])
            weak = [(s, r, n) for (s, r, n) in res if r is not None and r < n]
            missing = [s for (s, r, n) in res if r is None and not s.startswith(('.alert.', '.mix', '.surface'))]
            eq('%s contrast is strong enough everywhere' % scheme, weak, [])
            eq('%s contrast audit found its elements' % scheme, missing, [])
            cx.close()

    with section('ios zoom guard'):
        cz, pgz = new_page(browser)
        pgz.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
        tap(pgz, '#saveBtn')
        pgz.evaluate("document.getElementById('sheet').hidden = false")
        res = pgz.evaluate('''() => [...document.querySelectorAll('input, select, textarea')].filter(el => el.type !== 'hidden' && el.type !== 'checkbox' && el.type !== 'radio')
            .map(el => [el.tagName + '#' + el.id, parseFloat(getComputedStyle(el).fontSize)])''')
        eq('controls checked', len(res) >= 9, True)
        eq('every text control is 16px or larger', [r for r in res if r[1] < 16], [])
        cz.close()

    with section('tap targets'):
        cq, pgq = new_page(browser)
        small = pgq.evaluate('''() => [...document.querySelectorAll('button, .pick, summary')].filter(e => e.getClientRects().length).map(e => {
            const r = e.getBoundingClientRect(); return [e.id || e.className || e.tagName, Math.round(r.width), Math.round(r.height)]; })
            .filter(x => x[2] < 38 || x[1] < 38)''')
        # the inline Copy link next to the email address is text-sized by design
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
            eq('8 faces declared', len(res), 8)
            eq('every face loads', [r for r in res if not r.endswith(' loaded')], [])
            eq('display font ready', pgf.evaluate('''document.fonts.check("800 30px 'Big Shoulders Display'")'''), True)
            eq('body font ready', pgf.evaluate('''document.fonts.check("400 16px 'Public Sans'")'''), True)
            eq('mono font ready', pgf.evaluate('''document.fonts.check("400 13px 'IBM Plex Mono'")'''), True)
            eq('h1 uses display font', pgf.evaluate("getComputedStyle(document.querySelector('.masthead h1')).fontFamily").startswith('"Big Shoulders Display"'), True)
            eq('tabular digits survive the subset', pgf.evaluate('''() => {
                const w = (t) => {
                    const s = document.createElement('span');
                    s.style.cssText = "font:400 16px 'Public Sans';position:absolute;visibility:hidden;white-space:pre;font-variant-numeric:tabular-nums";
                    s.textContent = t; document.body.appendChild(s);
                    const r = s.getBoundingClientRect().width; s.remove(); return r;
                };
                return w('1111') === w('0000') && w('1111') > 0;
            }'''), True)
            eq('multiply and divide signs render in the mono face', pgf.evaluate('''() => {
                const w = (t) => {
                    const s = document.createElement('span');
                    s.style.cssText = "font:400 13px 'IBM Plex Mono';position:absolute;visibility:hidden;white-space:pre";
                    s.textContent = t; document.body.appendChild(s);
                    const r = s.getBoundingClientRect().width; s.remove(); return r;
                };
                return w('\\u00d7') > 0 && w('\\u00f7') > 0 && Math.abs(w('\\u00d7') - w('x')) < 0.6;
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
            eq('theme colors', pgm.evaluate("[...document.querySelectorAll('meta[name=theme-color]')].map(m => m.content)"), ['#E6EEEC', '#0A1615'])
            eq('favicon is a data uri', (pgm.get_attribute('link[rel=icon]', 'href') or '').startswith('data:image/svg+xml;base64,'), True)
            eq('apple touch icon', pgm.get_attribute('link[rel=apple-touch-icon]', 'href'), 'apple-touch-icon.png')
            eq('mailto anchor', pgm.get_attribute('a.mail', 'href'), 'mailto:' + SUPPORT)
            eq('privacy link', pgm.get_attribute('.foot a[href="privacy.html"]', 'href'), 'privacy.html')
            eq('rinse quote link', pgm.get_attribute('.foot a[href*="rinse-quote"]', 'href'), 'https://sanjixysti-creator.github.io/rinse-quote/')
            eq('rinse rate link', pgm.get_attribute('.foot a[href*="rinse-rate"]', 'href'), 'https://sanjixysti-creator.github.io/rinse-rate/')
            eq('home link', pgm.get_attribute('.foot a[href="https://sanjixysti-creator.github.io/"]', 'href'), 'https://sanjixysti-creator.github.io/')
            eq('maker line', 'Made by Xysti Software' in txt(pgm, '.foot'), True)
            cm.close()

        for scheme in ('light', 'dark'):
            with section('standalone: privacy ' + scheme):
                cp, pgp = new_page(browser, scheme=scheme, url=ORIGIN + PAGE_PATH + 'privacy.html')
                eq('privacy title', pgp.title(), 'Privacy Policy - Rinse Mix')
                has('privacy says no analytics', txt(pgp, 'body'), 'no analytics')
                eq('privacy mailto', pgp.get_attribute('a[href^="mailto:"]', 'href'), 'mailto:' + SUPPORT)
                eq('privacy back link', pgp.get_attribute('.back', 'href'), './')
                for w in (320, 390, 768, 1200):
                    o = overflow(pgp, w)
                    eq('privacy no overflow %s %d' % (scheme, w), (o['sw'] <= o['W'], o['bad']), (True, []))
                pgp.set_viewport_size({'width': 390, 'height': 844})
                pgp.screenshot(path=D + '/rm-privacy-%s.png' % scheme, full_page=True)
                eq('privacy body bg %s' % scheme, pgp.evaluate("getComputedStyle(document.body).backgroundColor"),
                   'rgb(230, 238, 236)' if scheme == 'light' else 'rgb(10, 22, 21)')
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
