import contextlib, functools, http.server, json, math, os, random, re, struct, threading
from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction
from playwright.sync_api import sync_playwright

D = os.path.dirname(os.path.abspath(__file__))
SRC = D + '/rinse-rate.html'
OUT = D + '/rate-test.html'

# RATE_STANDALONE=/path/to/site/rinse-rate/index.html tests the self-hosted page instead of the artifact fragment.
STANDALONE = os.environ.get('RATE_STANDALONE', '')
SITE_URL = 'https://sanjixysti-creator.github.io/rinse-rate/'
SITE_TITLE = 'Rinse Rate: Pressure Washing Job Profit Calculator'
STORE = 'rinse-rate-v1'

# Dash look-alikes are checked for without typing them, so this file stays free of them too.
EM, EN, MINUS = chr(0x2014), chr(0x2013), chr(0x2212)
DASHES = EM + EN + MINUS
TIMES, DIVIDE = chr(0xd7), chr(0xf7)

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
    PAGE_PATH = '/rate-test.html'
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


def near(name, got, want, tol=0.0051):
    global passes
    ok = got is not None and want is not None and abs(got - want) <= tol
    if ok:
        passes += 1
    else:
        fails.append('%s\n    got:  %r\n    want: %r (tolerance %r)' % (name, got, want, tol))


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
STUB_NO_STORAGE = (STUB_OK +
                   "Storage.prototype.getItem = function () { throw new Error('blocked'); };"
                   "Storage.prototype.setItem = function () { throw new Error('blocked'); };")


def new_page(browser, stub=STUB_OK, scheme='light', w=390, h=844, pre_state=None, url=None, reduced=False):
    ctx = browser.new_context(viewport={'width': w, 'height': h}, color_scheme=scheme, device_scale_factor=1,
                              reduced_motion='reduce' if reduced else 'no-preference')
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


def open_all(page):
    page.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")


def pressed(page, group):
    return page.evaluate("id => [...document.querySelectorAll('#' + id + ' button[aria-pressed=true]')].map(b => b.textContent.trim())", group)


def alert(page):
    if not page.is_visible('#payAlert'):
        return ('', '')
    cls = (page.get_attribute('#payAlert', 'class') or '').replace('alert', '').strip()
    return (cls, txt(page, '#payAlert p'))


def toast(page):
    return txt(page, '#toast') if page.is_visible('#toast') else ''


def gauge(page):
    return page.evaluate('''() => { const g = document.getElementById('gauge'); const f = document.getElementById('gFill'); const d = document.getElementById('gDot');
        return {state: g.getAttribute('data-state'), f: parseFloat(g.getAttribute('data-f')), path: f.getAttribute('d'), opacity: f.style.opacity,
                cx: parseFloat(d.getAttribute('cx')), cy: parseFloat(d.getAttribute('cy')), tick: document.getElementById('gTick').style.display,
                goal: document.getElementById('gGoal').textContent.trim(), max: document.getElementById('gMax').textContent.trim()}; }''')


def stub_rows(page):
    return page.evaluate("[...document.querySelectorAll('#stub .srow')].filter(r => r.getClientRects().length).map(r => [r.querySelector('dt').textContent.trim(), r.querySelector('dd').textContent.trim()])")


def long_rows(page):
    return page.evaluate('''() => [...document.querySelectorAll('#longBody tr')].map(tr => [tr.children[0].firstChild.textContent.trim(), tr.querySelector('.sub').textContent.trim(),
        tr.children[1].textContent.trim(), tr.children[2].textContent.trim(), tr.classList.contains('is-now')])''')


def price_rows(page):
    return page.evaluate('''() => [...document.querySelectorAll('#priceBody tr')].map(tr => { const th = tr.children[0]; const sub = th.querySelector('.sub').textContent.trim();
        return [th.textContent.replace(sub, '').trim(), sub, tr.children[1].textContent.trim(), tr.children[2].textContent.trim(), tr.classList.contains('is-now'), !!th.querySelector('button')]; })''')


def overflow(page, w):
    page.set_viewport_size({'width': w, 'height': 900})
    page.wait_for_timeout(120)
    return page.evaluate('''() => {
        const W = document.documentElement.clientWidth;
        const bad = [];
        document.querySelectorAll('body *').forEach(el => {
            if (getComputedStyle(el).position === 'fixed') return;
            if (el.closest('.sr-only')) return;
            const r = el.getBoundingClientRect();
            if (!(r.width && (r.right > W + 1 || r.left < -1))) return;
            // a wide table may scroll inside its own box; that is not the page overflowing
            for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
                const o = getComputedStyle(p).overflowX;
                const pr = p.getBoundingClientRect();
                if ((o === 'auto' || o === 'scroll' || o === 'hidden' || o === 'clip') && pr.left >= -1 && pr.right <= W + 1) return;
            }
            bad.push(el.tagName + '.' + el.className + '#' + el.id);
        });
        return {sw: document.documentElement.scrollWidth, W: W, bad: bad.slice(0, 6)};
    }''')


# ---------------------------------------------------------------- independent reference model
# Written separately from the page code: exact fractions, no shared helpers. Every number the page shows
# is compared with these, to within the rounding the page applies.
DEFAULT = dict(price=300, onsiteH=3, crew=2, driveMin=30, miles=28, setupMin=20, chem=15, other=0,
               perMile=0.725, wearH=5, helperPay=18, overheadPct=10, feePct=2.9, feeFixed=0.3, goal=50,
               jobsWeek=5, weeksYear=48)
IDS = dict(price='price', onsiteH='onsite', crew='crew', driveMin='driveMin', miles='miles', setupMin='setupMin', chem='chem', other='other',
           goal='goal', perMile='perMile', wearH='wearH', helperPay='helperPay', overheadPct='overheadPct', feePct='feePct', feeFixed='feeFixed',
           jobsWeek='jobsWeek', weeksYear='weeksYear')


def F(x):
    return Fraction(repr(x)) if isinstance(x, float) else Fraction(x)


def jround(x):
    """JavaScript Math.round: halves go up."""
    return int(math.floor(x + 0.5))


def ref(job):
    j = {k: F(v) for k, v in job.items()}
    hours = j['onsiteH'] + j['driveMin'] / 60 + j['setupMin'] / 60
    rate = (j['feePct'] + j['overheadPct']) / 100
    price = j['price']
    fee = price * j['feePct'] / 100 + j['feeFixed'] if price > 0 else Fraction(0)
    overhead = price * j['overheadPct'] / 100
    vehicle = j['miles'] * j['perMile']
    wear = j['onsiteH'] * j['wearH']
    helpers = (j['crew'] - 1) * hours * j['helperPay']
    direct = j['chem'] + j['other'] + vehicle + wear + helpers
    costs = fee + overhead + direct
    profit = price - costs
    r = dict(hours=hours, rate=rate, rateOk=rate < 1, haveHours=hours > 0, havePrice=price > 0, fee=fee, overhead=overhead,
             chem=j['chem'], other=j['other'], vehicle=vehicle, wear=wear, helpers=helpers, direct=direct, costs=costs, profit=profit,
             crew=int(j['crew']), goal=j['goal'], price=price)
    r['ok'] = r['haveHours'] and r['havePrice']
    r['margin'] = profit / price if price > 0 else None
    r['pay'] = profit / hours if hours > 0 else None
    r['fixed'] = direct + j['feeFixed']
    r['breakEven'] = r['fixed'] / (1 - rate) if rate < 1 else None
    r['needed'] = (j['goal'] * hours + r['fixed']) / (1 - rate) if rate < 1 and hours > 0 else None
    return r


def usd(x, places=2):
    """What Intl.NumberFormat shows for US dollars: half away from zero on the shortest decimal."""
    x = float(x)
    d = Decimal(repr(abs(x))).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    return ('-' if x < 0 else '') + '$' + '{:,.{p}f}'.format(d, p=places)


def mnum(s):
    m = re.fullmatch(r'(-?)\$([0-9,]+(?:\.[0-9]+)?)', (s or '').strip())
    if not m:
        return None
    v = float(m.group(2).replace(',', ''))
    return -v if m.group(1) else v


def pnum(s):
    m = re.fullmatch(r'(-?[0-9,]+(?:\.[0-9]+)?)%', (s or '').strip())
    return float(m.group(1).replace(',', '')) if m else None


def hm_min(s):
    s = (s or '').strip()
    if s in ('', '-'):
        return None
    h = re.search(r'([0-9,]+) h', s)
    mi = re.search(r'(\d+) min', s)
    return (int(h.group(1).replace(',', '')) * 60 if h else 0) + (int(mi.group(1)) if mi else 0)


def hm_text(hours):
    total = jround(float(hours) * 60)
    h, m = divmod(total, 60)
    if h == 0 and m == 0:
        return '0 h'
    if m == 0:
        return '{:,} h'.format(h)
    if h == 0:
        return '%d min' % m
    return '{:,} h {} min'.format(h, m)


def typed(v):
    return repr(v) if isinstance(v, float) else str(v)


def set_job(page, job):
    """Types a whole job at once. Values go in the way a person would type them, one input event each."""
    page.evaluate('''(vals) => { for (const id of Object.keys(vals)) { const el = document.getElementById(id); el.value = vals[id]; el.dispatchEvent(new Event('input', {bubbles: true})); } }''',
                  {IDS[k]: typed(v) for k, v in job.items()})


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

# Graphics that carry meaning (the gauge arc and its dot) need 3:1 against the card behind them.
GRAPHIC_JS = '''() => {
    const parse = c => { const m = c.match(/rgba?\\(([^)]+)\\)/); const p = m[1].split(',').map(parseFloat); return {r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1}; };
    const lin = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    const lum = c => 0.2126 * lin(c.r) + 0.7152 * lin(c.g) + 0.0722 * lin(c.b);
    const bg = parse(getComputedStyle(document.getElementById('payCard')).backgroundColor);
    const out = {};
    for (const [name, sel, prop] of [['fill', '#gFill', 'stroke'], ['dot', '#gDot', 'stroke'], ['tick', '#gTick', 'stroke'], ['track', '.g-track', 'stroke']]) {
        const c = parse(getComputedStyle(document.querySelector(sel))[prop]);
        const a = lum(c), b = lum(bg);
        out[name] = Math.round(((Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)) * 100) / 100;
    }
    return out;
}'''

CONTRAST_SELS = ['.tagline', '.hint', '.fine', '.lab', '.chip', '.chip[aria-pressed="true"]', '.btn', '.btn.ghost', '.btn.sm',
                 '.alert.info p', '.g-goal', '.g-scale span', '.r-num', '.r-unit', '.verdict', '.need p', '.need .fine', '.need .btn',
                 '.srow dt', '.srow dd', '.srow.total dt', '.srow.total dd', '.srow.sub dt', '.srow.sub dd', '.hours-note',
                 '.wi thead th', '.wi tbody th', '.wi td', '.wi .sub', '.wi tr.is-now > *', '.wi tr.is-now .sub', '.wi .pick', '.wi .pick .sub',
                 '.ledger dt', '.ledger dd', '.ledger .total dt', '.sv-total', '.sv-name', '.sv-sum', '.sv-out',
                 '.rates summary .h2', '.rates summary .hint', '.faq summary', '.faq p', '.mline', '.foot', '.foot a', '.linkish',
                 '.b-lab', '.b-amt', '.affix .suf', '.affix .pre', '.sec-head h2', '.masthead h1', '.toast', '.sheet .fine']


def money_or_whole(x):
    x = float(x)
    return usd(x, 0) if abs(x - round(x)) < 0.005 else usd(x, 2)


def verify(page, job):
    """Everything the page shows for this job, compared with the reference. Returns the list of differences."""
    r = ref(job)
    bad = []

    def chk(name, got, want, tol=0.0051):
        if got is None or want is None:
            if got is not None or want is not None:
                bad.append('%s got %r want %r' % (name, got, want))
        elif abs(got - want) > tol:
            bad.append('%s got %r want %r' % (name, got, want))

    ok = r['ok']
    goal = float(r['goal'])
    price = float(r['price'])
    pay_text = txt(page, '#payNum')
    if not (ok and re.search(r'[KMBT]$', pay_text)):
        chk('pay', mnum(pay_text) if ok else None, float(r['pay']) if ok else None)
    if not ok and pay_text != '-':
        bad.append('pay should be a dash, got %r' % pay_text)
    chk('profit', mnum(txt(page, '#vProfit')) if ok else None, float(r['profit']) if ok else None)
    if ok and float(r['margin']) * 100 < -999.95:
        if txt(page, '#vMargin') != 'under -1,000%':
            bad.append('margin got %r want the short form' % txt(page, '#vMargin'))
    elif not (ok and float(r['margin']) * 100 < -999.85):
        chk('margin', pnum(txt(page, '#vMargin')) if ok else None, float(r['margin'] * 100) if ok else None, 0.0501)
    mins = hm_min(txt(page, '#vHours'))
    want_min = jround(float(r['hours']) * 60) if r['haveHours'] else None
    if mins != want_min:
        bad.append('hours got %r want %r' % (mins, want_min))
    want_price = usd(price) if r['havePrice'] else '-'
    if txt(page, '#vPrice') != want_price:
        bad.append('price row got %r want %r' % (txt(page, '#vPrice'), want_price))

    for rid, key in (('rowFee', 'fee'), ('rowOverhead', 'overhead'), ('rowChem', 'chem'), ('rowVehicle', 'vehicle'),
                     ('rowWear', 'wear'), ('rowHelpers', 'helpers'), ('rowOther', 'other')):
        v = float(r[key])
        shown = page.is_visible('#' + rid)
        if abs(v - 0.005) > 1e-6 and shown != (v >= 0.005):
            bad.append('%s visible=%r for %r' % (rid, shown, v))
        if shown and v >= 0.005:
            chk(rid, mnum(txt(page, '#' + rid + ' dd')), -v)

    # the message above the gauge
    kind, _ = alert(page)
    want = None
    if not r['rateOk']:
        want = 'bad'
    elif not r['haveHours'] or not r['havePrice']:
        want = 'info'
    elif abs(float(r['profit'])) < 1e-6:
        want = None
    elif float(r['profit']) < 0:
        want = 'bad'
    elif r['crew'] > 1 and F(job['helperPay']) <= 0:
        want = 'warn'
    else:
        want = ''
    if want is not None and kind != want:
        bad.append('alert got %r want %r' % (kind, want))

    # the gauge
    g = gauge(page)
    top = goal * 2 if goal > 0 else 100.0
    if ok:
        pay = float(r['pay'])
        f = max(0.0, min(1.0, pay / top))
        if abs(g['f'] - f) > 1e-4:
            bad.append('gauge f got %r want %r' % (g['f'], f))
        if not any(abs(pay - e) < 1e-6 for e in (0.0, goal, goal * 0.7)):
            if pay <= 0:
                st = 'bad'
            elif goal > 0:
                st = 'good' if pay >= goal else ('warn' if pay >= goal * 0.7 else 'bad')
            else:
                st = 'accent'
            if g['state'] != st:
                bad.append('gauge state got %r want %r' % (g['state'], st))
    elif g['state'] != 'none' or g['f'] != 0:
        bad.append('gauge should be empty, got %r' % ((g['state'], g['f']),))
    if g['goal'] != ('Goal ' + money_or_whole(goal) if goal > 0 else ''):
        bad.append('gauge goal label %r' % g['goal'])
    if g['max'] != money_or_whole(top):
        bad.append('gauge max label %r' % g['max'])
    if (g['tick'] == 'none') != (goal <= 0):
        bad.append('gauge tick display %r' % g['tick'])

    # the note about the price
    need_shown = page.is_visible('#needBox')
    if need_shown != (r['haveHours'] and r['rateOk']):
        bad.append('need box visible=%r' % need_shown)
    if r['haveHours'] and r['rateOk']:
        be = float(r['breakEven'])
        if goal > 0:
            nd = float(r['needed'])
            if abs(nd - round(nd)) > 1e-6 and abs(price - nd) > 1e-6:
                n = math.ceil(nd)
                enough = r['havePrice'] and price >= nd
                if not enough:
                    want_t = 'To earn %s an hour on this job, charge %s.' % (usd(goal), usd(n, 0))
                elif price >= n:
                    want_t = 'Your price covers your goal. You could charge as little as %s and still earn %s an hour.' % (usd(n, 0), usd(goal))
                else:
                    want_t = 'Your price covers your goal.'
                if txt(page, '#needText') != want_t:
                    bad.append('need text got %r want %r' % (txt(page, '#needText'), want_t))
                if page.is_visible('#needBtn') == enough:
                    bad.append('need button visible=%r but enough=%r' % (page.is_visible('#needBtn'), enough))
                if not enough and txt(page, '#needBtn') != 'Use ' + usd(n, 0):
                    bad.append('need button text %r' % txt(page, '#needBtn'))
        elif txt(page, '#needText') != 'Break-even price: %s. Below that you lose money.' % usd(math.ceil(be - 1e-9), 0) and abs(be - round(be)) > 1e-6:
            bad.append('break-even text %r' % txt(page, '#needText'))
        if goal <= 0 and page.is_visible('#needBtn'):
            bad.append('need button should be hidden without a goal')

    # the pinned bar
    bp, bq, bm = txt(page, '#bAmtPay'), txt(page, '#bAmtProfit'), txt(page, '#bAmtMargin')
    if not (ok and re.search(r'[KMBT]$', bp)):
        chk('bar pay', mnum(bp) if ok else None, float(r['pay']) if ok else None, 0.0051 if (not ok or abs(float(r['pay'])) < 1000) else 0.5001)
    if not (ok and re.search(r'[KMBT]$', bq)):
        chk('bar profit', mnum(bq) if ok else None, float(r['profit']) if ok else None, 0.5001)
    if ok and float(r['margin']) * 100 < -999.0001:
        if bm != '<-999%':
            bad.append('bar margin got %r want the short form' % bm)
    elif not (ok and float(r['margin']) * 100 < -998.9999):
        chk('bar margin', pnum(bm) if ok else None, float(r['margin'] * 100) if ok else None, 0.5001)

    # the two what-if tables
    if ok:
        rows = long_rows(page)
        steps = [(1, 'As planned'), (1.25, '25% longer'), (1.5, '50% longer'), (2, 'Twice as long')]
        if len(rows) != 4:
            bad.append('long table has %d rows' % len(rows))
        else:
            for (k, label), row in zip(steps, rows):
                q = ref(dict(job, onsiteH=min(1000, float(job['onsiteH']) * k)))
                if row[0] != label or row[4] != (k == 1):
                    bad.append('long row %r' % (row,))
                mm = hm_min(row[1])
                if mm is None or abs(mm - float(q['hours']) * 60) > 0.5 + 1e-6:
                    bad.append('long hours %r want %r' % (row[1], float(q['hours']) * 60))
                chk('long profit ' + label, mnum(row[2]), float(q['profit']), 0.5001)
                chk('long pay ' + label, mnum(row[3]), float(q['pay']))
        want_rows, seen = [], set()
        for k, label in ((0.8, '20% less'), (0.9, '10% less'), (1, 'Your price'), (1.1, '10% more'), (1.2, '20% more')):
            now = k == 1
            p = price if now else min(10000000, max(1, jround(price * k)))
            if not now and (p == price or p in seen):
                continue
            seen.add(p)
            want_rows.append((p, label, now))
        rows = price_rows(page)
        if len(rows) != len(want_rows):
            bad.append('price table has %d rows, want %d' % (len(rows), len(want_rows)))
        else:
            for row, (p, label, now) in zip(rows, want_rows):
                q = ref(dict(job, price=p))
                if row[1] != label or row[4] != now or row[5] == now:
                    bad.append('price row %r' % (row,))
                chk('price cell ' + label, mnum(row[0]), float(p), 0.0051 if now else 0.5001)
                chk('price profit ' + label, mnum(row[2]), float(q['profit']), 0.5001)
                chk('price pay ' + label, mnum(row[3]), float(q['pay']))
    else:
        if page.is_visible('#longWrap') or page.is_visible('#priceWrap') or not page.is_visible('#longEmpty') or not page.is_visible('#priceEmpty'):
            bad.append('tables should be replaced by their empty messages')

    # the month planner
    jw, wy = job['jobsWeek'], job['weeksYear']
    if ok and jw > 0:
        week = float(r['profit']) * jw
        chk('week', mnum(txt(page, '#pWeek')), week, 0.5001)
        mm = hm_min(txt(page, '#pHours'))
        if mm is None or abs(mm - float(r['hours']) * jw * 60) > 0.5 + 1e-6:
            bad.append('hours per week %r want %r' % (txt(page, '#pHours'), float(r['hours']) * jw * 60))
        if wy > 0:
            chk('month', mnum(txt(page, '#pMonth')), week * wy / 12, 0.5001)
            chk('year', mnum(txt(page, '#pYear')), week * wy, 0.5001)
        elif (txt(page, '#pMonth'), txt(page, '#pYear')) != ('-', '-'):
            bad.append('month and year should be dashes')
    elif (txt(page, '#pWeek'), txt(page, '#pHours'), txt(page, '#pMonth'), txt(page, '#pYear')) != ('-', '-', '-', '-'):
        bad.append('planner should be dashes')

    # buttons follow the same rule
    if page.is_disabled('#copyBtn') == ok or page.is_disabled('#saveBtn') == ok:
        bad.append('copy and save buttons should be enabled exactly when the job works')
    return bad


def rand_job(rnd):
    def pick(zero_chance, make):
        return 0 if rnd.random() < zero_chance else make()

    job = dict(
        price=pick(0.06, lambda: round(math.exp(rnd.uniform(math.log(25), math.log(8000))), rnd.choice([0, 0, 2]))),
        onsiteH=pick(0.05, lambda: round(rnd.randint(1, 240) * 0.05, 2)),
        crew=rnd.choice([1, 1, 2, 2, 3, 4, 5]),
        driveMin=pick(0.15, lambda: rnd.choice([5, 10, 15, 20, 30, 45, 60, 90, rnd.randint(1, 240)])),
        miles=pick(0.15, lambda: round(rnd.uniform(0, 160), 1)),
        setupMin=pick(0.15, lambda: rnd.choice([10, 15, 20, 30, 45, 60, rnd.randint(1, 120)])),
        chem=pick(0.2, lambda: round(rnd.uniform(0, 250), 2)),
        other=pick(0.6, lambda: round(rnd.uniform(0, 400), 2)),
        perMile=rnd.choice([0, 0.725, 0.67, round(rnd.uniform(0.2, 1.2), 3)]),
        wearH=rnd.choice([0, 5, round(rnd.uniform(0, 25), 2)]),
        helperPay=rnd.choice([0, 18, 15, round(rnd.uniform(10, 40), 2)]),
        overheadPct=rnd.choice([0, 10, round(rnd.uniform(0, 35), 2)]),
        feePct=rnd.choice([0, 2.9, round(rnd.uniform(0, 6), 2)]),
        feeFixed=rnd.choice([0, 0.3, round(rnd.uniform(0, 1), 2)]),
        goal=rnd.choice([0, 30, 50, 75, 100, round(rnd.uniform(10, 200), 2)]),
        jobsWeek=rnd.choice([0, 1, 3, 5, 10, rnd.randint(1, 40)]),
        weeksYear=rnd.choice([0, 48, 52, rnd.randint(1, 52)]),
    )
    if rnd.random() < 0.04:
        job['overheadPct'] = 100
    return job


# ---------------------------------------------------------------- source hygiene
with section('source hygiene'):
    eq('no dash look-alikes', [c for c in DASHES if c in src], [])
    eq('title first', src.startswith('<title>Rinse Rate</title>'), True)
    eq('no document tags', bool(re.search(r'<(html|head|body)[\s>]', src)), False)
    eq('no print', 'window.print' in src, False)
    eq('no mailto links', 'mailto:' in src, False)
    eq('no dialogs', bool(re.search(r'\b(alert|confirm|prompt)\(', src)), False)
    eq('no external scripts', re.findall(r'<script[^>]*\bsrc=', src), [])
    eq('no innerHTML', 'innerHTML' in src, False)
    eq('no eval', bool(re.search(r'\b(eval|new Function)\b', src)), False)
    eq('no network calls', bool(re.search(r'\b(fetch|XMLHttpRequest|sendBeacon|WebSocket)\b', src)), False)
    eq('no cookies', 'document.cookie' in src, False)
    hosts = set(re.findall(r'https?://([a-z0-9.\-]+)', src))
    eq('only allowed hosts', sorted(hosts - {'fonts.googleapis.com', 'fonts.gstatic.com', 'sanjixysti-creator.github.io'}), [])
    eq('one mail span', src.count('<span class="mail"></span>'), 1)
    eq('one h1', len(re.findall(r'<h1[ >]', src)), 1)
    ids = re.findall(r'\bid="([^"]+)"', src)
    eq('ids are unique', sorted(set(i for i in ids if ids.count(i) > 1)), [])
    for_ids = re.findall(r'\bfor="([^"]+)"', src) + re.findall(r'aria-describedby="([^"]+)"', src) + re.findall(r'aria-labelledby="([^"]+)"', src)
    eq('every label, description and heading reference exists', sorted(set(i for i in for_ids if i not in ids)), [])
    js_ids = set(re.findall(r"\$\('([A-Za-z0-9_-]+)'\)", src))
    eq('every id the script uses exists in the markup', sorted(i for i in js_ids if i not in ids), [])

    if STANDALONE:
        eq('built: doctype first', built.lstrip().lower().startswith('<!doctype html>'), True)
        eq('built: no dash look-alikes', [c for c in DASHES if c in built], [])
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
        page.screenshot(path=D + '/rate-phone.png', full_page=True)
        page.screenshot(path=D + '/rate-light-top.png')
        page.locator('#payCard').screenshot(path=D + '/rate-light-card.png')
        eq('pay reading', txt(page, '#payNum'), '$36.97')
        eq('per hour unit', txt(page, '.r-unit'), 'per hour')
        eq('pay sub', txt(page, '#paySub'), '3 h on site, 2 people')
        eq('verdict', txt(page, '#verdict'), 'That is $13.03 an hour under your $50.00 goal.')
        eq('need text', txt(page, '#needText'), 'To earn $50.00 an hour on this job, charge $358.')
        eq('need button', txt(page, '#needBtn'), 'Use $358')
        eq('need fine print', txt(page, '#needFine'), 'Rounded up to the next dollar. Break-even is $138, and below that you lose money.')
        eq('no alert on the example', alert(page), ('', ''))
        eq('stub rows', stub_rows(page), [
            ['Price you charge', '$300.00'], ['Payment fee (2.9% + $0.30)', '-$9.00'], ['Overhead (10%)', '-$30.00'],
            ['Chemicals and supplies', '-$15.00'], ['Vehicle (28 mi)', '-$20.30'], ['Machine wear (3 h)', '-$15.00'],
            ['Helper pay (1 x 3 h 50 min)', '-$69.00'], ['Profit', '$141.70'], ['Profit margin', '47.2%'], ['Hours you worked', '3 h 50 min']])
        eq('other costs row hidden at zero', page.is_visible('#rowOther'), False)
        eq('hours note', txt(page, '#hoursNote'), '3 h on site, 30 min driving, 20 min setup.')
        g = gauge(page)
        eq('gauge state', g['state'], 'warn')
        near('gauge fraction', g['f'], 36.9652 / 100, 0.0001)
        eq('gauge goal label', g['goal'], 'Goal $50')
        eq('gauge max label', g['max'], '$100')
        eq('gauge tick shown', g['tick'], '')
        # the arc ends at the point on the circle for this fraction
        t = math.pi * (1 - float(ref(DEFAULT)['pay']) / 100)
        ex, ey = 120 + 96 * math.cos(t), 120 - 96 * math.sin(t)
        eq('gauge arc path', g['path'], 'M24 120A96 96 0 0 1 %.2f %.2f' % (ex, ey))
        near('gauge dot x', g['cx'], ex, 0.011)
        near('gauge dot y', g['cy'], ey, 0.011)
        eq('bar values', (txt(page, '#bAmtPay'), txt(page, '#bAmtProfit'), txt(page, '#bAmtMargin')), ('$36.97', '$142', '47%'))
        eq('bar labels', page.evaluate("[...document.querySelectorAll('#bar .b-lab')].map(e => e.textContent.trim())"), ['Per hour', 'Profit', 'Margin'])
        eq('bar visible on phone', page.is_visible('#bar'), True)
        eq('bar hidden from AT', page.get_attribute('#bar', 'aria-hidden'), 'true')
        eq('example banner shown', page.is_visible('#exampleNote'), True)
        has('example banner text', txt(page, '#exampleNote'), 'This is an example job.')
        eq('hours chip', pressed(page, 'hoursChips'), ['3'])
        eq('crew chip', pressed(page, 'crewChips'), ['2'])
        eq('goal chip', pressed(page, 'goalChips'), ['$50'])
        eq('fee chip', pressed(page, 'feeChips'), ['Card 2.9% + $0.30'])
        eq('inputs', {i: page.input_value('#' + i) for i in ('price', 'onsite', 'crew', 'driveMin', 'miles', 'setupMin', 'chem', 'other', 'goal',
                                                              'perMile', 'wearH', 'helperPay', 'overheadPct', 'feePct', 'feeFixed', 'jobsWeek', 'weeksYear')},
           {'price': '300.00', 'onsite': '3', 'crew': '2', 'driveMin': '30', 'miles': '28', 'setupMin': '20', 'chem': '15.00', 'other': '', 'goal': '50.00',
            'perMile': '0.725', 'wearH': '5.00', 'helperPay': '18.00', 'overheadPct': '10', 'feePct': '2.9', 'feeFixed': '0.30', 'jobsWeek': '5', 'weeksYear': '48'})
        eq('long table', [r[:4] for r in long_rows(page)], [
            ['As planned', '3 h 50 min', '$142', '$36.97'], ['25% longer', '4 h 35 min', '$124', '$27.15'],
            ['50% longer', '5 h 20 min', '$107', '$20.10'], ['Twice as long', '6 h 50 min', '$73', '$10.64']])
        eq('price table', [r[:4] for r in price_rows(page)], [
            ['$240', '20% less', '$89', '$23.33'], ['$270', '10% less', '$116', '$30.15'], ['$300', 'Your price', '$142', '$36.97'],
            ['$330', '10% more', '$168', '$43.78'], ['$360', '20% more', '$194', '$50.60']])
        eq('planner', (txt(page, '#pWeek'), txt(page, '#pHours'), txt(page, '#pMonth'), txt(page, '#pYear')), ('$709', '19 h 10 min', '$2,834', '$34,008'))
        eq('saved list starts empty', 'No saved jobs yet' in txt(page, '#savedList'), True)
        eq('saved total hidden', page.is_visible('#savedTotal'), False)
        eq('save form hidden', page.is_visible('#saveForm'), False)
        eq('mail text', txt(page, '.mail'), SUPPORT)
        eq('verify() agrees on the example', verify(page, DEFAULT), [])

    with section('math lines'):
        page.evaluate("document.getElementById('mathBox').open = true")
        r0 = ref(DEFAULT)
        lines = page.evaluate("[...document.querySelectorAll('#mathLines p')].map(p => p.textContent.trim())")
        eq('math line count', len(lines), 7)
        eq('hours line', lines[0], 'Hours = 3 h on site + 30 min driving + 20 min setup = 3 h 50 min (3.83 h)')
        eq('costs line', lines[1], 'Costs = fee $9.00 + overhead $30.00 + chemicals $15.00 + other $0.00 + vehicle $20.30 + machine wear $15.00 + helper pay $69.00 = $158.30')
        eq('profit line', lines[2], 'Profit = $300.00 - $158.30 = $141.70')
        eq('pay line', lines[3], 'Pay per hour = $141.70 %s 3.83 h = $36.97' % DIVIDE)
        eq('fixed line', lines[4], 'Costs that do not move with the price = $119.30 + $0.30 fixed fee = $119.60')
        eq('break-even line', lines[5], 'Break-even price = $119.60 %s (1 - 0.129) = %s' % (DIVIDE, usd(r0['breakEven'])))
        eq('goal line', lines[6], 'Price for your goal = ($50.00 %s 3.83 h + $119.60) %s (1 - 0.129) = %s, rounded up to $358' % (TIMES, DIVIDE, usd(r0['needed'])))
        eq('math text has no dash look-alikes', [c for c in DASHES if c in txt(page, '#mathLines')], [])
        page.evaluate("document.getElementById('mathBox').open = false")

    with section('faq'):
        eq('seven questions', page.evaluate("document.querySelectorAll('#faq details').length"), 7)
        eq('questions start closed', page.evaluate("[...document.querySelectorAll('#faq details')].filter(d => d.open).length"), 0)
        tap(page, '#faq details:nth-child(1) summary')
        eq('first question opens', page.evaluate("document.querySelector('#faq details:nth-child(1)').open"), True)
        has('first answer mentions drive and setup', txt(page, '#faq details:nth-child(1) p'), 'including driving and setup')
        tap(page, '#faq details:nth-child(1) summary')
        eq('first question closes', page.evaluate("document.querySelector('#faq details:nth-child(1)').open"), False)
        eq('summaries are tall enough to tap', page.evaluate("[...document.querySelectorAll('#faq summary')].every(s => s.getBoundingClientRect().height >= 44)"), True)
        eq('faq text has no dash look-alikes', [c for c in DASHES if c in txt(page, '#faq')], [])

    # ------------------------------------------------------------ 2 editing, the example, start blank
    with section('editing ends the example'):
        put(page, '#price', '320')
        page.wait_for_timeout(60)
        eq('banner gone after an edit', page.is_visible('#exampleNote'), False)
        eq('pay follows the price', txt(page, '#payNum'), usd(ref(dict(DEFAULT, price=320))['pay']))
        put(page, '#price', '300')
        page.wait_for_timeout(60)
        eq('banner stays gone', page.is_visible('#exampleNote'), False)
        eq('back to the example numbers', txt(page, '#payNum'), '$36.97')

    with section('start blank'):
        c2, pg2 = new_page(browser)
        tap(pg2, '#exampleClear')
        pg2.wait_for_timeout(80)
        eq('banner gone', pg2.is_visible('#exampleNote'), False)
        eq('job fields are empty', [pg2.input_value('#' + i) for i in ('price', 'onsite', 'driveMin', 'miles', 'setupMin', 'chem', 'other')], [''] * 7)
        eq('crew goes back to one', pg2.input_value('#crew'), '1')
        eq('crew chip', pressed(pg2, 'crewChips'), ['1'])
        eq('usual numbers stay', (pg2.input_value('#goal'), pg2.input_value('#perMile'), pg2.input_value('#helperPay')), ('50.00', '0.725', '18.00'))
        eq('info message', alert(pg2), ('info', 'Enter the hours on site to see what the job pays per hour.'))
        eq('reading dashes', (txt(pg2, '#payNum'), txt(pg2, '#bAmtPay'), txt(pg2, '#vProfit'), txt(pg2, '#vMargin'), txt(pg2, '#vHours')), ('-', '-', '-', '-', '-'))
        eq('price note hidden', pg2.is_visible('#needBox'), False)
        eq('verdict empty', txt(pg2, '#verdict'), '')
        eq('pay sub empty', txt(pg2, '#paySub'), '')
        eq('tables replaced by messages', (pg2.is_visible('#longWrap'), pg2.is_visible('#longEmpty'), pg2.is_visible('#priceWrap'), pg2.is_visible('#priceEmpty')), (False, True, False, True))
        eq('copy and save disabled', (pg2.is_disabled('#copyBtn'), pg2.is_disabled('#saveBtn')), (True, True))
        eq('gauge empty', (gauge(pg2)['state'], gauge(pg2)['f'], gauge(pg2)['opacity']), ('none', 0.0, '0'))
        eq('planner dashes', (txt(pg2, '#pWeek'), txt(pg2, '#pYear')), ('-', '-'))
        eq('verify() agrees on the blank job', verify(pg2, dict(DEFAULT, price=0, onsiteH=0, crew=1, driveMin=0, miles=0, setupMin=0, chem=0, other=0)), [])
        pg2.wait_for_timeout(350)
        stored = pg2.evaluate("JSON.parse(localStorage.getItem('%s'))" % STORE)
        eq('stored: blank job and no example', (stored['price'], stored['onsiteH'], stored['crew'], stored['example']), (0, 0, 1, False))
        pg2.reload()
        pg2.wait_for_timeout(250)
        eq('blank job survives a reload', (pg2.input_value('#price'), pg2.input_value('#crew'), pg2.is_visible('#exampleNote')), ('', '1', False))
        # typing a price alone: hours still missing
        put(pg2, '#price', '250')
        eq('price alone still asks for hours', alert(pg2)[0], 'info')
        put(pg2, '#onsite', '2')
        eq('price and hours give a reading', txt(pg2, '#payNum'), usd(ref(dict(DEFAULT, price=250, onsiteH=2, crew=1, driveMin=0, miles=0, setupMin=0, chem=0, other=0))['pay']))
        # clear this job takes two taps and keeps the crew
        put(pg2, '#crew', '3')
        tap(pg2, '#clearBtn')
        eq('clear armed', txt(pg2, '#clearBtn'), 'Tap again to clear')
        eq('first tap keeps the job', pg2.input_value('#price'), '250.00')
        tap(pg2, '#clearBtn')
        pg2.wait_for_timeout(60)
        eq('clear empties the job', pg2.input_value('#price'), '')
        eq('clear keeps the crew', pg2.input_value('#crew'), '3')
        eq('clear toast', toast(pg2), 'Job cleared.')
        eq('clear button label back', txt(pg2, '#clearBtn'), 'Clear this job')
        c2.close()

    # ------------------------------------------------------------ 3 typing hours
    with section('typing hours'):
        c3, pg3 = new_page(browser)
        tap(pg3, '#exampleClear')
        put(pg3, '#price', '100')
        cases = [('2.5', '2 h 30 min'), ('2:30', '2 h 30 min'), ('2h30', '2 h 30 min'), ('2h 30m', '2 h 30 min'), ('2 hours 30 minutes', '2 h 30 min'),
                 ('2 h 30', '2 h 30 min'), ('90m', '1 h 30 min'), ('90 min', '1 h 30 min'), ('45min', '45 min'), ('1.5 hours', '1 h 30 min'),
                 ('1.5h', '1 h 30 min'), ('1,5', '1 h 30 min'), ('1,5h', '1 h 30 min'), ('0:45', '45 min'), ('12:00', '12 h'), ('8', '8 h'),
                 ('3 hrs', '3 h'), ('2.999', '3 h'), ('0.25', '15 min'), ('1000', '1,000 h'), ('5000', '1,000 h'), ('-3', ''), ('abc', ''),
                 ('2:75', ''), ('1:60', ''), ('2h75', ''), (':30', ''), ('', '')]
        for typed_text, want in cases:
            put(pg3, '#onsite', typed_text)
            sub = txt(pg3, '#paySub')
            eq('hours %r' % typed_text, sub, (want + ' on site, 1 person') if want else '')
        put(pg3, '#onsite', '2:30')
        pg3.locator('#onsite').evaluate('e => e.blur()')
        eq('field shows plain hours after leaving it', pg3.input_value('#onsite'), '2.5')
        put(pg3, '#onsite', '1h20')
        pg3.locator('#onsite').evaluate('e => e.blur()')
        eq('odd length is shown as a decimal', pg3.input_value('#onsite'), '1.333')
        c3.close()

    # ------------------------------------------------------------ 4 messages above the gauge
    with section('alerts'):
        c4, pg4 = new_page(browser)
        open_all(pg4)
        put(pg4, '#price', '100')
        kind, msg = alert(pg4)
        eq('losing job kind', kind, 'bad')
        r4 = ref(dict(DEFAULT, price=100))
        eq('losing job text', msg, 'You lose %s on this job. It costs more than you charge.' % usd(-float(r4['profit'])))
        eq('losing job gauge', (gauge(pg4)['state'], gauge(pg4)['f']), ('bad', 0.0))
        eq('losing job reading is negative', txt(pg4, '#payNum').startswith('-$'), True)
        eq('losing job stub profit is negative', txt(pg4, '#vProfit').startswith('-$'), True)
        eq('losing job still says what to charge', txt(pg4, '#needText'), 'To earn $50.00 an hour on this job, charge $358.')
        eq('verify() agrees on a losing job', verify(pg4, dict(DEFAULT, price=100)), [])
        pg4.screenshot(path=D + '/rate-error.png')
        put(pg4, '#price', '300')
        eq('recovers', alert(pg4), ('', ''))

        put(pg4, '#helperPay', '0')
        kind, msg = alert(pg4)
        eq('unpaid helper warning kind', kind, 'warn')
        has('unpaid helper warning text', msg, 'You have 1 helper on the job but pay them $0 an hour.')
        put(pg4, '#crew', '4')
        has('plural helpers', alert(pg4)[1], 'You have 3 helpers on the job')
        put(pg4, '#crew', '1')
        eq('no helper warning alone', alert(pg4), ('', ''))
        put(pg4, '#crew', '2')
        put(pg4, '#helperPay', '18')

        put(pg4, '#overheadPct', '100')
        kind, msg = alert(pg4)
        eq('fees and overhead too high kind', kind, 'bad')
        has('fees and overhead text', msg, 'Fees and overhead add up to 102.9% of the price.')
        eq('price note hidden when no price can work', pg4.is_visible('#needBox'), False)
        eq('verify() agrees at 102.9%', verify(pg4, dict(DEFAULT, overheadPct=100)), [])
        put(pg4, '#overheadPct', '97.1')
        eq('exactly 100% is also refused', alert(pg4)[0], 'bad')
        put(pg4, '#overheadPct', '97')
        eq('99.9% is a valid but absurd rate: the job loses money', alert(pg4)[0], 'bad')
        has('99.9% loss wording', alert(pg4)[1], 'You lose ')
        eq('99.9% shows a price note', pg4.is_visible('#needBox'), True)
        want_n = math.ceil(float(ref(dict(DEFAULT, overheadPct=97))['needed']))
        eq('99.9% price note', txt(pg4, '#needText'), 'To earn $50.00 an hour on this job, charge %s.' % usd(want_n, 0))
        eq('verify() agrees at 99.9%', verify(pg4, dict(DEFAULT, overheadPct=97)), [])
        put(pg4, '#overheadPct', '10')

        put(pg4, '#price', '')
        kind, msg = alert(pg4)
        eq('no price kind', kind, 'info')
        eq('no price text', msg, 'Enter what you charge to see what the job pays. The price for your goal is worked out below.')
        eq('price note still helps with no price', txt(pg4, '#needText'), 'To earn $50.00 an hour on this job, charge $358.')
        eq('use button sets the price', (pg4.is_visible('#needBtn'), txt(pg4, '#needBtn')), (True, 'Use $358'))
        tap(pg4, '#needBtn')
        pg4.wait_for_timeout(60)
        eq('price filled in', pg4.input_value('#price'), '358.00')
        eq('now it reaches the goal', alert(pg4), ('', ''))
        eq('goal reached or beaten', mnum(txt(pg4, '#payNum')) >= 50, True)
        eq('verdict says above', txt(pg4, '#verdict').startswith('That is ') and ' above your $50.00 goal.' in txt(pg4, '#verdict'), True)
        eq('gauge is good', gauge(pg4)['state'], 'good')
        eq('price note now says it covers the goal', txt(pg4, '#needText'), 'Your price covers your goal. You could charge as little as $358 and still earn $50.00 an hour.')
        eq('use button hidden when the price is enough', pg4.is_visible('#needBtn'), False)
        # a price a little under the rounded figure but over the exact one
        r_need = float(ref(DEFAULT)['needed'])
        put(pg4, '#price', '%.2f' % (r_need + 0.05))
        eq('price between the exact figure and the rounded one', txt(pg4, '#needText'), 'Your price covers your goal.')
        eq('no button there either', pg4.is_visible('#needBtn'), False)
        put(pg4, '#price', '%.2f' % (r_need - 0.05))
        eq('just under the exact figure still asks for more', txt(pg4, '#needText'), 'To earn $50.00 an hour on this job, charge $358.')

        put(pg4, '#price', '300')
        put(pg4, '#goal', '0')
        eq('goal off: price note', txt(pg4, '#needText'), 'Break-even price: $138. Below that you lose money.')
        eq('goal off: no button', pg4.is_visible('#needBtn'), False)
        eq('goal off: fine print', txt(pg4, '#needFine'), 'Set a goal above to see the price that earns it.')
        eq('goal off: no verdict', txt(pg4, '#verdict'), '')
        g = gauge(pg4)
        eq('goal off: gauge', (g['state'], g['goal'], g['max'], g['tick']), ('accent', '', '$100', 'none'))
        eq('goal off: chips', pressed(pg4, 'goalChips'), [])
        put(pg4, '#goal', '')
        eq('empty goal counts as none', gauge(pg4)['state'], 'accent')
        tap(pg4, '#goalChips button[data-v="75"]')
        pg4.wait_for_timeout(60)
        eq('goal chip sets the goal', pg4.input_value('#goal'), '75.00')
        eq('goal chip pressed', pressed(pg4, 'goalChips'), ['$75'])
        eq('goal 75 verdict', txt(pg4, '#verdict'), 'That is $38.03 an hour under your $75.00 goal.')
        eq('goal 75 gauge is bad (under 70%)', gauge(pg4)['state'], 'bad')
        put(pg4, '#goal', '36.97')
        eq('almost on the goal is above or right on', alert(pg4)[0], '')
        put(pg4, '#goal', '36.9652')
        eq('exactly on the goal wording', txt(pg4, '#verdict') in ('That is right on your $36.97 an hour goal.', 'That is $0.00 an hour under your $36.97 goal.', 'That is $0.00 an hour above your $36.97 goal.'), True)
        c4.close()

    # ------------------------------------------------------------ 5 gauge states and geometry
    with section('gauge'):
        c5, pg5 = new_page(browser)
        open_all(pg5)
        base = dict(DEFAULT, crew=1, helperPay=0, chem=0, miles=0, driveMin=0, setupMin=0, wearH=0, overheadPct=0, feePct=0, feeFixed=0, onsiteH=1, goal=50)
        # with no costs, pay per hour equals the price for a one hour job, so the price sets the needle exactly
        for price, state, f in ((0.5, 'bad', 0.005), (34.99, 'bad', 0.3499), (35, 'warn', 0.35), (49.99, 'warn', 0.4999), (50, 'good', 0.5),
                                (75, 'good', 0.75), (100, 'good', 1.0), (160, 'good', 1.0), (250000, 'good', 1.0)):
            set_job(pg5, dict(base, price=price))
            g = gauge(pg5)
            eq('gauge $%s/h state' % price, g['state'], state)
            near('gauge $%s/h fraction' % price, g['f'], f, 0.00006)
            t = math.pi * (1 - min(0.9995, g['f']))
            ex, ey = 120 + 96 * math.cos(t), 120 - 96 * math.sin(t)
            eq('gauge $%s/h arc end' % price, g['path'], 'M24 120A96 96 0 0 1 %.2f %.2f' % (ex, ey))
            near('gauge $%s/h dot x' % price, g['cx'], ex, 0.011)
            near('gauge $%s/h dot y' % price, g['cy'], ey, 0.011)
            eq('gauge $%s/h arc visible' % price, g['opacity'], '1')
            eq('gauge $%s/h reading' % price, txt(pg5, '#payNum'), usd(price))
            eq('gauge $%s/h verify' % price, verify(pg5, dict(base, price=price)), [])
        # the dot never leaves the arc: its distance from the centre is the radius
        set_job(pg5, dict(base, price=100))
        g = gauge(pg5)
        near('full needle still on the circle', math.hypot(g['cx'] - 120, g['cy'] - 120), 96, 0.02)
        # a different goal moves the scale: the top of the dial is twice the goal
        set_job(pg5, dict(base, price=60, goal=30))
        g = gauge(pg5)
        eq('goal 30 scale', (g['goal'], g['max'], g['state']), ('Goal $30', '$60', 'good'))
        near('goal 30 needle at the top', g['f'], 1.0, 0.00006)
        set_job(pg5, dict(base, price=15, goal=30))
        near('goal 30 needle half way to the goal', gauge(pg5)['f'], 0.25, 0.00006)
        set_job(pg5, dict(base, price=21, goal=30))
        eq('exactly 70% of goal is the warn edge', gauge(pg5)['state'], 'warn')
        set_job(pg5, dict(base, price=20.99, goal=30))
        eq('just under 70% of goal is bad', gauge(pg5)['state'], 'bad')
        set_job(pg5, dict(base, price=37.5, goal=37.5))
        eq('right on the goal is good', gauge(pg5)['state'], 'good')
        eq('right on the goal wording', txt(pg5, '#verdict'), 'That is right on your $37.50 an hour goal.')
        set_job(pg5, dict(base, price=37.5, goal=12.34))
        eq('goal with cents shows cents', (gauge(pg5)['goal'], gauge(pg5)['max']), ('Goal $12.34', '$24.68'))
        # no goal: a neutral colour for any pay above zero, scale to $100
        set_job(pg5, dict(base, price=40, goal=0))
        g = gauge(pg5)
        eq('no goal gauge', (g['state'], g['goal'], g['max'], g['tick']), ('accent', '', '$100', 'none'))
        near('no goal fraction', g['f'], 0.4, 0.00006)
        set_job(pg5, dict(base, price=1, onsiteH=1, other=5, goal=0))
        eq('no goal, losing: bad', gauge(pg5)['state'], 'bad')
        eq('no goal, losing: needle at the start', gauge(pg5)['f'], 0.0)
        # exactly zero pay
        set_job(pg5, dict(base, price=10, other=10, goal=50))
        eq('zero pay is bad', gauge(pg5)['state'], 'bad')
        c5.close()

    # ------------------------------------------------------------ 6 chips and the usual numbers
    with section('chips and usual numbers'):
        c6, pg6 = new_page(browser)
        open_all(pg6)
        tap(pg6, '#hoursChips button[data-v="6"]')
        pg6.wait_for_timeout(60)
        eq('6 hour chip fills the field', pg6.input_value('#onsite'), '6')
        eq('6 hour chip pressed', pressed(pg6, 'hoursChips'), ['6'])
        eq('6 hours reading', txt(pg6, '#payNum'), usd(ref(dict(DEFAULT, onsiteH=6))['pay']))
        put(pg6, '#onsite', '2.5')
        eq('no chip pressed for 2.5 hours', pressed(pg6, 'hoursChips'), [])
        tap(pg6, '#crewChips button[data-v="3"]')
        eq('crew chip fills the field', pg6.input_value('#crew'), '3')
        eq('crew chip pressed', pressed(pg6, 'crewChips'), ['3'])
        eq('crew sub text', txt(pg6, '#paySub'), '2 h 30 min on site, 3 people')
        eq('helper row says 2 helpers', stub_rows(pg6)[6][0], 'Helper pay (2 x 3 h 20 min)')
        put(pg6, '#crew', '0')
        eq('crew cannot go below one', txt(pg6, '#paySub'), '2 h 30 min on site, 1 person')
        put(pg6, '#crew', '2.9')
        eq('crew is a whole number', txt(pg6, '#paySub'), '2 h 30 min on site, 2 people')
        put(pg6, '#crew', '999')
        eq('crew is capped at 50', txt(pg6, '#paySub'), '2 h 30 min on site, 50 people')
        tap(pg6, '#crewChips button[data-v="2"]')
        # payment fee presets
        tap(pg6, '#feeChips button[data-v="0"]')
        pg6.wait_for_timeout(60)
        eq('fee None clears the percent', (pg6.input_value('#feePct'), pg6.input_value('#feeFixed')), ('', ''))
        eq('fee None pressed', pressed(pg6, 'feeChips'), ['None'])
        eq('fee row hidden with no fee', pg6.is_visible('#rowFee'), False)
        eq('fee None label', 'Payment fee' in ' '.join(r[0] for r in stub_rows(pg6)), False)
        tap(pg6, '#feeChips button[data-v="1"]')
        eq('card preset fills the fields', (pg6.input_value('#feePct'), pg6.input_value('#feeFixed')), ('2.9', '0.30'))
        eq('card preset pressed', pressed(pg6, 'feeChips'), ['Card 2.9% + $0.30'])
        put(pg6, '#feePct', '3.5')
        eq('custom fee: no preset pressed', pressed(pg6, 'feeChips'), [])
        eq('custom fee label', stub_rows(pg6)[1][0], 'Payment fee (3.5% + $0.30)')
        put(pg6, '#feeFixed', '')
        eq('percent only label', stub_rows(pg6)[1][0], 'Payment fee (3.5%)')
        put(pg6, '#feePct', '')
        put(pg6, '#feeFixed', '0.25')
        eq('fixed only label', stub_rows(pg6)[1][0], 'Payment fee ($0.25)')
        tap(pg6, '#feeChips button[data-v="1"]')
        # vehicle
        put(pg6, '#miles', '10')
        put(pg6, '#perMile', '1')
        eq('vehicle row', [r for r in stub_rows(pg6) if r[0].startswith('Vehicle')], [['Vehicle (10 mi)', '-$10.00']])
        put(pg6, '#miles', '12.5')
        eq('half mile shown', [r[0] for r in stub_rows(pg6) if r[0].startswith('Vehicle')], ['Vehicle (12.5 mi)'])
        put(pg6, '#perMile', '0')
        eq('no vehicle row at zero cost per mile', [r for r in stub_rows(pg6) if r[0].startswith('Vehicle')], [])
        # other costs row appears
        put(pg6, '#other', '40')
        eq('other costs row', [r for r in stub_rows(pg6) if r[0] == 'Other costs'], [['Other costs', '-$40.00']])
        # reset the usual numbers (two taps), job numbers stay
        put(pg6, '#helperPay', '33')
        put(pg6, '#goal', '65')
        tap(pg6, '#usualResetBtn')
        eq('reset armed', txt(pg6, '#usualResetBtn'), 'Tap again to reset')
        eq('first tap changes nothing', pg6.input_value('#helperPay'), '33.00')
        tap(pg6, '#usualResetBtn')
        pg6.wait_for_timeout(60)
        eq('usual numbers restored', [pg6.input_value('#' + i) for i in ('perMile', 'wearH', 'helperPay', 'overheadPct', 'feePct', 'feeFixed', 'goal')],
           ['0.725', '5.00', '18.00', '10', '2.9', '0.30', '50.00'])
        eq('job numbers kept by reset', (pg6.input_value('#other'), pg6.input_value('#miles'), pg6.input_value('#onsite')), ('40.00', '12.5', '2.5'))
        eq('reset toast', toast(pg6), 'Usual numbers reset.')
        # comma as the decimal mark, thousands separators, stray characters
        put(pg6, '#price', '1,234.50')
        eq('thousands separator', pg6.evaluate("document.getElementById('vPrice').textContent"), '$1,234.50')
        put(pg6, '#price', '12,5')
        eq('comma as decimal mark', txt(pg6, '#vPrice'), '$12.50')
        put(pg6, '#price', '$300')
        eq('dollar sign ignored', txt(pg6, '#vPrice'), '$300.00')
        put(pg6, '#price', 'abc')
        eq('letters give nothing', txt(pg6, '#vPrice'), '-')
        put(pg6, '#price', '-50')
        eq('negative price counts as none', txt(pg6, '#vPrice'), '-')
        put(pg6, '#price', '99999999999')
        eq('price is capped', txt(pg6, '#vPrice'), '$10,000,000.00')
        put(pg6, '#overheadPct', '250')
        has('percent is capped at 100', alert(pg6)[1], 'Fees and overhead add up to 102.9% of the price.')
        c6.close()

    # ------------------------------------------------------------ 7 copy
    with section('copy'):
        c7, pg7 = new_page(browser)
        tap(pg7, '#copyBtn')
        pg7.wait_for_timeout(80)
        eq('copy text', pg7.evaluate('window.__copied'), '\n'.join([
            'Job pay check, from Rinse Rate',
            'Price: $300.00',
            'Time: 3 h on site, 30 min driving, 20 min setup (3 h 50 min in all), 2 people',
            'Payment fee: -$9.00',
            'Overhead: -$30.00',
            'Chemicals and supplies: -$15.00',
            'Vehicle: -$20.30',
            'Machine wear: -$15.00',
            'Helper pay: -$69.00',
            'Profit: $141.70 (47.2% of the price)',
            'Pay per hour: $36.97',
            'Goal: $50.00 per hour, which takes a price of $358']))
        eq('copy toast', toast(pg7), 'Summary copied.')
        eq('copied text has no dash look-alikes', [c for c in DASHES if c in pg7.evaluate('window.__copied')], [])
        open_all(pg7)
        put(pg7, '#goal', '0')
        put(pg7, '#driveMin', '')
        put(pg7, '#setupMin', '')
        put(pg7, '#miles', '')
        put(pg7, '#crew', '1')
        put(pg7, '#other', '12')
        pg7.evaluate('window.__copied = null')
        tap(pg7, '#copyBtn')
        pg7.wait_for_timeout(80)
        lines = pg7.evaluate('window.__copied').split('\n')
        eq('lean copy has no goal line', [l for l in lines if l.startswith('Goal')], [])
        eq('lean copy time line', lines[2], 'Time: 3 h on site (3 h in all), 1 person')
        eq('lean copy other line', 'Other costs: -$12.00' in lines, True)
        eq('lean copy has no vehicle or helper line', [l for l in lines if l.startswith(('Vehicle', 'Helper'))], [])
        c7.close()

    c8, pg8 = new_page(browser, stub=STUB_REJECT)
    with section('clipboard blocked'):
        tap(pg8, '#copyBtn')
        pg8.wait_for_timeout(120)
        eq('fallback sheet shows', pg8.is_visible('#sheet'), True)
        has('fallback text', pg8.input_value('#sheetText'), 'Job pay check, from Rinse Rate')
        tap(pg8, '#sheetClose')
        eq('fallback closes', pg8.is_visible('#sheet'), False)
        tap(pg8, '.mail-copy')
        pg8.wait_for_timeout(120)
        eq('email copy fallback shows address', pg8.input_value('#sheetText'), SUPPORT)
    c8.close()

    with section('clipboard missing'):
        c8b, pg8b = new_page(browser, stub="Object.defineProperty(navigator, 'clipboard', {configurable: true, value: undefined}); document.execCommand = function () { return false; };")
        tap(pg8b, '#copyBtn')
        pg8b.wait_for_timeout(120)
        eq('fallback sheet shows without a clipboard', pg8b.is_visible('#sheet'), True)
        c8b.close()

    # ------------------------------------------------------------ 8 what-if tables and the month planner
    with section('what-if tables'):
        c9, pg9 = new_page(browser)
        tap(pg9, '#priceBody tr:nth-child(1) .pick')
        pg9.wait_for_timeout(60)
        eq('pick sets the price', pg9.input_value('#price'), '240.00')
        eq('pick ends the example', pg9.is_visible('#exampleNote'), False)
        eq('table follows the new price', [r[0] for r in price_rows(pg9)], ['$192', '$216', '$240', '$264', '$288'])
        eq('middle row is marked', [r[4] for r in price_rows(pg9)], [False, False, True, False, False])
        eq('only the other rows are buttons', [r[5] for r in price_rows(pg9)], [True, True, False, True, True])
        has('pick label for screen readers', pg9.get_attribute('#priceBody tr:nth-child(1) .pick', 'aria-label'), 'Use $192 as the price')
        eq('long table marks the planned row', [r[4] for r in long_rows(pg9)], [True, False, False, False])
        eq('verify() agrees at $240', verify(pg9, dict(DEFAULT, price=240)), [])
        for price in ('99.5', '1', '3', '2', '0.4', '1234.56'):
            put(pg9, '#price', price)
            eq('tables at price %s' % price, verify(pg9, dict(DEFAULT, price=float(price) if '.' in price else int(price))), [])
        put(pg9, '#price', '1')
        eq('a $1 job shows one price row', len(price_rows(pg9)), 1)
        put(pg9, '#price', '99.5')
        eq('cents price label', price_rows(pg9)[2][0], '$99.50')
        eq('prices round to whole dollars', [r[0] for r in price_rows(pg9)], ['$80', '$90', '$99.50', '$109', '$119'])
        put(pg9, '#price', '300')
        # the planner
        put(pg9, '#jobsWeek', '3')
        put(pg9, '#weeksYear', '50')
        eq('planner 3 a week for 50 weeks', verify(pg9, dict(DEFAULT, jobsWeek=3, weeksYear=50)), [])
        put(pg9, '#jobsWeek', '2.7')
        eq('jobs a week is a whole number', verify(pg9, dict(DEFAULT, jobsWeek=2, weeksYear=50)), [])
        put(pg9, '#weeksYear', '60')
        eq('weeks are capped at 52', verify(pg9, dict(DEFAULT, jobsWeek=2, weeksYear=52)), [])
        put(pg9, '#jobsWeek', '0')
        eq('no jobs a week gives dashes', (txt(pg9, '#pWeek'), txt(pg9, '#pHours'), txt(pg9, '#pMonth'), txt(pg9, '#pYear')), ('-', '-', '-', '-'))
        put(pg9, '#jobsWeek', '1')
        put(pg9, '#weeksYear', '0')
        eq('no weeks gives weekly figures only', (txt(pg9, '#pWeek') != '-', txt(pg9, '#pMonth'), txt(pg9, '#pYear')), (True, '-', '-'))
        put(pg9, '#jobsWeek', '5000')
        put(pg9, '#weeksYear', '48')
        eq('jobs a week is capped at 1000', verify(pg9, dict(DEFAULT, jobsWeek=1000, weeksYear=48)), [])
        c9.close()

    # ------------------------------------------------------------ 9 saved jobs and persistence
    with section('saved jobs'):
        c10, pg10 = new_page(browser)
        eq('save form starts closed', pg10.is_visible('#saveForm'), False)
        tap(pg10, '#saveBtn')
        eq('save form opens', pg10.is_visible('#saveForm'), True)
        eq('name field focused', pg10.evaluate('document.activeElement && document.activeElement.id'), 'saveName')
        put(pg10, '#saveName', 'Miller driveway')
        pg10.locator('#saveForm button[type=submit]').evaluate('e => e.click()')
        pg10.wait_for_timeout(80)
        eq('save form closes', pg10.is_visible('#saveForm'), False)
        eq('saved toast', toast(pg10), 'Saved Miller driveway.')
        eq('saved name', txt(pg10, '#savedList .sv-name'), 'Miller driveway')
        eq('saved summary', txt(pg10, '#savedList .sv-sum'), '$300 job, 3 h 50 min, 2 people')
        eq('saved output', txt(pg10, '#savedList .sv-out'), '$36.97 an hour, profit $141.70')
        eq('total line', txt(pg10, '#savedTotal'), '1 job: $141.70 profit over 3 h 50 min, $36.97 an hour on average.')

        put(pg10, '#price', '450')
        put(pg10, '#goal', '80')
        tap(pg10, '#saveBtn')
        tap(pg10, '#saveForm button[type=submit]')          # blank name uses the automatic label
        pg10.wait_for_timeout(80)
        eq('two saved', pg10.evaluate("document.querySelectorAll('#savedList .saved').length"), 2)
        eq('newest first with automatic name', txt(pg10, '#savedList .saved:nth-child(1) .sv-name'), '$450 job, 3 h 50 min')
        r1, r2 = ref(DEFAULT), ref(dict(DEFAULT, price=450))
        tp, th = float(r1['profit'] + r2['profit']), float(r1['hours'] + r2['hours'])
        eq('total line for two', txt(pg10, '#savedTotal'), '2 jobs: %s profit over %s, %s an hour on average.' % (usd(tp), hm_text(th), usd(tp / th)))

        tap(pg10, '#savedList .saved:nth-child(2) .btn.sm:not(.ghost)')
        pg10.wait_for_timeout(80)
        eq('use job restores the price', pg10.input_value('#price'), '300.00')
        eq('use job restores the goal it was saved with', pg10.input_value('#goal'), '50.00')
        eq('use job reading', txt(pg10, '#payNum'), '$36.97')
        eq('use job toast', toast(pg10), 'Loaded Miller driveway.')

        pg10.wait_for_timeout(300)
        pg10.reload()
        pg10.wait_for_timeout(250)
        eq('saved jobs survive a reload', pg10.evaluate("document.querySelectorAll('#savedList .saved').length"), 2)
        eq('values survive a reload', (pg10.input_value('#price'), pg10.input_value('#goal'), pg10.is_visible('#exampleNote')), ('300.00', '50.00', False))
        stored = pg10.evaluate("JSON.parse(localStorage.getItem('%s'))" % STORE)
        eq('stored version', stored['v'], 1)
        eq('stored saved count', len(stored['saved']), 2)
        eq('stored job has numbers', (stored['saved'][1]['price'], stored['saved'][1]['name']), (300, 'Miller driveway'))
        eq('stored example flag', stored['example'], False)

        btn = '#savedList .saved:nth-child(1) .btn.ghost'
        eq('delete idle label', txt(pg10, btn), 'Delete')
        tap(pg10, btn)
        eq('delete armed label', txt(pg10, btn), 'Tap again to delete')
        eq('still two after one tap', pg10.evaluate("document.querySelectorAll('#savedList .saved').length"), 2)
        tap(pg10, btn)
        pg10.wait_for_timeout(80)
        eq('deleted', pg10.evaluate("document.querySelectorAll('#savedList .saved').length"), 1)
        eq('the older job remains', txt(pg10, '#savedList .sv-name'), 'Miller driveway')
        eq('total line follows', txt(pg10, '#savedTotal'), '1 job: $141.70 profit over 3 h 50 min, $36.97 an hour on average.')
        pg10.reload()
        pg10.wait_for_timeout(250)
        eq('delete survives a reload', pg10.evaluate("document.querySelectorAll('#savedList .saved').length"), 1)
        tap(pg10, '#savedList .saved .btn.ghost')
        tap(pg10, '#savedList .saved .btn.ghost')
        pg10.wait_for_timeout(80)
        eq('all gone: empty message', 'No saved jobs yet' in txt(pg10, '#savedList'), True)
        eq('all gone: no total', pg10.is_visible('#savedTotal'), False)

        # a job that cannot be worked out cannot be saved
        put(pg10, '#price', '')
        eq('save disabled without a price', pg10.is_disabled('#saveBtn'), True)
        put(pg10, '#price', '300')
        eq('save enabled again', pg10.is_disabled('#saveBtn'), False)
        # opening the form and then breaking the job closes it
        tap(pg10, '#saveBtn')
        eq('form open', pg10.is_visible('#saveForm'), True)
        put(pg10, '#onsite', '')
        put(pg10, '#driveMin', '')
        put(pg10, '#setupMin', '')
        eq('form closes when the job stops working', pg10.is_visible('#saveForm'), False)
        c10.close()

    with section('saved cap and odd saved jobs'):
        fields = dict(DEFAULT)
        base_state = dict(fields, v=1, example=False, seq=60)
        many = dict(base_state, saved=[dict(fields, id='j%d' % i, name='Job %d' % i, ts=i) for i in range(50)])
        c11, pg11 = new_page(browser, pre_state=json.dumps(many))
        eq('fifty saved jobs show', pg11.evaluate("document.querySelectorAll('#savedList .saved').length"), 50)
        eq('fifty jobs total line', txt(pg11, '#savedTotal').startswith('50 jobs: '), True)
        tap(pg11, '#saveBtn')
        tap(pg11, '#saveForm button[type=submit]')
        pg11.wait_for_timeout(80)
        eq('cap toast', toast(pg11), 'You can keep 50 jobs. Delete one to save another.')
        eq('still fifty', pg11.evaluate("document.querySelectorAll('#savedList .saved').length"), 50)
        c11.close()

        odd = dict(base_state, saved=[dict(fields, id='a', name='Empty one', price=0, ts=1), dict(fields, id='b', name='', ts=2)])
        c12, pg12 = new_page(browser, pre_state=json.dumps(odd))
        eq('unusable job says so', txt(pg12, '#savedList .saved:nth-child(1) .sv-sum'), 'Not enough numbers to work out the pay.')
        eq('unnamed job gets a name', txt(pg12, '#savedList .saved:nth-child(2) .sv-name'), 'Saved job')
        eq('total counts only usable jobs', txt(pg12, '#savedTotal').startswith('1 job: '), True)
        c12.close()

    with section('persistence timing'):
        c13, pg13 = new_page(browser)
        put(pg13, '#price', '321')
        pg13.wait_for_timeout(400)
        pg13.reload()
        pg13.wait_for_timeout(250)
        eq('edit survives a reload after the delay', pg13.input_value('#price'), '321.00')
        put(pg13, '#price', '322')
        pg13.reload()                    # straight away: the page-hide handler writes it
        pg13.wait_for_timeout(250)
        eq('edit survives an immediate reload', pg13.input_value('#price'), '322.00')
        eq('stored numbers are plain numbers', pg13.evaluate("typeof JSON.parse(localStorage.getItem('%s')).price" % STORE), 'number')
        c13.close()

    with section('hostile storage'):
        junk = [
            '{"v":1,"example":"yes","price":"abc","onsiteH":-5,"crew":9999,"goal":"1e99","feePct":"500","overheadPct":null,"saved":[{"id":1,"name":"<img src=x onerror=alert(1)>","price":"12","onsiteH":1},null,5,{"nope":1}]}',
            'not json at all',
            '{"v":2}',
            '{"v":1,"saved":"nope"}',
            '[]',
            'null',
            '{"v":1,"price":{"a":1},"crew":[3],"saved":[{"id":"x","name":{"a":1},"ts":"zzz"}]}',
            '{"v":1,"saved":[' + ','.join('{"id":"k%d","price":100,"onsiteH":2}' % i for i in range(200)) + ']}',
        ]
        for i, raw in enumerate(junk):
            n_err = len(errs)
            c14, pg14 = new_page(browser, pre_state=raw)
            eq('junk %d renders a reading or a dash' % i, bool(re.fullmatch(r'-?\$[0-9,.]+|-|-?\$[0-9.]+[KMBT]', txt(pg14, '#payNum'))), True)
            eq('junk %d has no page errors' % i, [e for e in errs[n_err:] if e[0] == 'pageerror'], [])
            eq('junk %d keeps every field in range' % i, pg14.evaluate('''() => ['price','onsite','crew','driveMin','miles','setupMin','chem','other','goal','perMile','wearH','helperPay','overheadPct','feePct','feeFixed','jobsWeek','weeksYear']
                .every(id => { const v = parseFloat(document.getElementById(id).value.replace(/,/g, '')); return document.getElementById(id).value === '' || (v >= 0 && v <= 10000000); })'''), True)
            if i == 0:
                eq('junk name is text, not markup', pg14.evaluate("document.querySelectorAll('#savedList img').length"), 0)
                eq('junk name shown as text', 'onerror' in txt(pg14, '#savedList .sv-name'), True)
                eq('junk crew is capped', pg14.input_value('#crew'), '50')
                eq('junk bad price falls back to the default', pg14.input_value('#price'), '300.00')
                eq('junk example flag is not trusted', pg14.is_visible('#exampleNote'), False)
            if i == 7:
                eq('saved jobs are capped at 50 when loading', pg14.evaluate("document.querySelectorAll('#savedList .saved').length"), 50)
            c14.close()
        # fresh stored state with the example flag on shows the banner
        c15, pg15 = new_page(browser, pre_state=json.dumps(dict(DEFAULT, v=1, example=True, seq=0, saved=[])))
        eq('stored example flag shows the banner', pg15.is_visible('#exampleNote'), True)
        c15.close()

    with section('storage unavailable'):
        n_err = len(errs)
        c16, pg16 = new_page(browser, stub=STUB_NO_STORAGE)
        eq('page works with storage blocked', txt(pg16, '#payNum'), '$36.97')
        put(pg16, '#price', '320')
        eq('edits still work', txt(pg16, '#payNum'), usd(ref(dict(DEFAULT, price=320))['pay']))
        tap(pg16, '#saveBtn')
        tap(pg16, '#saveForm button[type=submit]')
        pg16.wait_for_timeout(80)
        eq('saving still works in memory', pg16.evaluate("document.querySelectorAll('#savedList .saved').length"), 1)
        eq('no page errors with storage blocked', [e for e in errs[n_err:] if e[0] == 'pageerror'], [])
        c16.close()

    with section('screen reader summary'):
        c17, pg17 = new_page(browser)
        eq('live region is polite and atomic', (pg17.get_attribute('#srRead', 'role'), pg17.get_attribute('#srRead', 'aria-live'), pg17.get_attribute('#srRead', 'aria-atomic')),
           ('status', 'polite', 'true'))
        pg17.wait_for_timeout(1000)
        eq('summary of the example', txt(pg17, '#srRead'),
           'You earn $36.97 per hour. That is $13.03 an hour under your $50.00 goal. Profit $141.70, 47.2% of the price. Price for your goal: $358.')
        before = txt(pg17, '#srRead')
        pg17.locator('#price').click()
        pg17.wait_for_timeout(60)
        pg17.keyboard.type('9999', delay=0)
        pg17.wait_for_timeout(250)
        eq('not announced while typing', txt(pg17, '#srRead'), before)
        pg17.wait_for_timeout(900)
        r17 = ref(dict(DEFAULT, price=9999))
        eq('announced once typing stops', txt(pg17, '#srRead'),
           'You earn %s per hour. That is %s an hour above your $50.00 goal. Profit %s, %s of the price. Price for your goal: $358.' % (
               usd(r17['pay']), usd(float(r17['pay']) - 50), usd(r17['profit']), '%.1f%%' % (float(r17['margin']) * 100)))
        put(pg17, '#price', '')
        pg17.wait_for_timeout(900)
        eq('summary cleared when there is no result', txt(pg17, '#srRead'), '')
        c17.close()

    # ------------------------------------------------------------ 10 the maths against the independent reference
    with section('property test'):
        c18, pg18 = new_page(browser)
        rnd = random.Random(20261002)
        shown = ok_n = inv_n = lose_n = rate_bad = no_goal = 0
        for i in range(360):
            job = rand_job(rnd)
            set_job(pg18, job)
            r = ref(job)
            problems = verify(pg18, job)
            eq('case %d %s' % (i, json.dumps(job, sort_keys=True)), problems, [])
            ok_n += 1 if r['ok'] else 0
            lose_n += 1 if r['ok'] and r['profit'] < 0 else 0
            rate_bad += 1 if not r['rateOk'] else 0
            no_goal += 1 if float(r['goal']) <= 0 else 0
            # What the page says to charge really does reach the goal, and one dollar less does not.
            if r['ok'] and r['rateOk'] and float(r['goal']) > 0 and inv_n < 140:
                nd = float(r['needed'])
                be = float(r['breakEven'])
                if abs(nd - round(nd)) > 1e-6 and abs(be - round(be)) > 1e-6:
                    inv_n += 1
                    n, b = math.ceil(nd), math.ceil(be)
                    set_job(pg18, dict(job, price=n))
                    near('case %d pay at the price it names' % i, max(mnum(txt(pg18, '#payNum')), float(r['goal'])), mnum(txt(pg18, '#payNum')), 0.0051)
                    if n - 1 >= 1:
                        set_job(pg18, dict(job, price=n - 1))
                        pay_less = mnum(txt(pg18, '#payNum'))
                        near('case %d pay one dollar under it' % i, min(pay_less, float(r['goal'])), pay_less, 0.0051)
                    set_job(pg18, dict(job, price=b))
                    prof = mnum(txt(pg18, '#vProfit'))
                    near('case %d profit at break-even' % i, max(prof, 0.0), prof, 0.0051)
                    if b - 1 >= 1:
                        set_job(pg18, dict(job, price=b - 1))
                        prof = mnum(txt(pg18, '#vProfit'))
                        near('case %d profit one dollar under break-even' % i, min(prof, 0.0), prof, 0.0051)
        eq('property test saw working jobs', ok_n > 250, True)
        eq('property test saw losing jobs', lose_n > 15, True)
        eq('property test saw impossible rates', rate_bad >= 3, True)
        eq('property test saw jobs with no goal', no_goal > 20, True)
        eq('property test ran the price and break-even checks', inv_n >= 60, True)
        c18.close()

    with section('rounding edges'):
        c19, pg19 = new_page(browser)
        open_all(pg19)
        # exact cases worked by hand: one hour, no costs, so pay equals price
        simple = dict(DEFAULT, crew=1, helperPay=0, chem=0, miles=0, driveMin=0, setupMin=0, wearH=0, overheadPct=0, feePct=0, feeFixed=0, onsiteH=1, other=0)
        for price, text in ((1.004, '$1.00'), (2.676, '$2.68'), (123456.789, '$123,456.79'), (999999.994, '$999,999.99'), (12.5, '$12.50')):
            set_job(pg19, dict(simple, price=price))
            eq('reading for $%s' % price, txt(pg19, '#payNum'), text)
        set_job(pg19, dict(simple, price=1000000))
        eq('a million an hour uses short form', txt(pg19, '#payNum'), '$1M')
        set_job(pg19, dict(simple, price=1234567.89))
        eq('compact million reading', txt(pg19, '#payNum'), '$1.2M')
        set_job(pg19, dict(simple, price=10000000, onsiteH=0.001))
        eq('billions an hour', txt(pg19, '#payNum'), '$10B')
        eq('compact reading in the bar', txt(pg19, '#bAmtPay'), '$10B')
        set_job(pg19, dict(simple, price=1, other=1234567.89))
        eq('negative compact reading', txt(pg19, '#payNum'), '-$1.2M')
        eq('no dash look-alike in a negative reading', [c for c in DASHES if c in txt(pg19, '#payNum')], [])
        c19.close()

    with section('pinned bar figures'):
        cb, pgb = new_page(browser)
        simple = dict(DEFAULT, crew=1, helperPay=0, chem=0, miles=0, driveMin=0, setupMin=0, wearH=0, overheadPct=0, feePct=0, feeFixed=0, onsiteH=1, other=0)
        for label, job, want, cls in (
                ('three figures with cents', dict(simple, price=412.11), ('$412.11', '$412', '100%'), ''),
                ('four figures drop the cents', dict(simple, price=3896.7), ('$3,897', '$3,897', '100%'), ''),
                ('five figures', dict(simple, price=29016.47), ('$29,016', '$29,016', '100%'), ''),
                ('six figures', dict(simple, price=391909.2), ('$391,909', '$391,909', '100%'), 'sm'),
                ('a million', dict(simple, price=1234567), ('$1.2M', '$1.2M', '100%'), ''),
                ('negative six figures', dict(simple, price=1, other=450040.36), ('-$450,039', '-$450,039', '<-999%'), 'sm'),
                ('negative huge', dict(simple, price=1, other=10000000), ('-$10M', '-$10M', '<-999%'), '')):
            set_job(pgb, job)
            got = (txt(pgb, '#bAmtPay'), txt(pgb, '#bAmtProfit'), txt(pgb, '#bAmtMargin'))
            eq('bar: %s' % label, got, want)
            if cls != '':
                eq('bar: %s gets a smaller size' % label, 'sm' in (pgb.get_attribute('#bAmtPay', 'class') or '') or 'xs' in (pgb.get_attribute('#bAmtPay', 'class') or ''), True)
        set_job(pgb, dict(simple, price=100))
        eq('bar: short figures keep the full size', [pgb.get_attribute('#b%s' % n, 'class') for n in ('AmtPay', 'AmtProfit', 'AmtMargin')], ['b-amt'] * 3)
        eq('stub margin for a very bad job', (lambda: (set_job(pgb, dict(simple, price=1, other=5000)), txt(pgb, '#vMargin'))[1])(), 'under -1,000%')
        has('copy text for a very bad job', (lambda: (tap(pgb, '#copyBtn'), pgb.wait_for_timeout(60), pgb.evaluate('window.__copied'))[2])(), '(under -1,000% of the price)')
        cb.close()

    # ------------------------------------------------------------ 11 layouts, widths, extremes
    with section('layout phone'):
        ctx20, pg20 = new_page(browser)
        open_all(pg20)
        tap(pg20, '#saveBtn')
        put(pg20, '#saveName', 'Front of house and the long driveway out to the detached garage on the corner lot')
        tap(pg20, '#saveForm button[type=submit]')
        tap(pg20, '#saveBtn')
        tap(pg20, '#copyBtn')
        for w in (320, 340, 360, 375, 390, 430, 600, 768, 899, 900, 1024, 1280, 1440, 1920):
            o = overflow(pg20, w)
            eq('no horizontal overflow at %d' % w, (o['sw'] <= o['W'], o['bad']), (True, []))
        pg20.set_viewport_size({'width': 320, 'height': 700})
        pg20.wait_for_timeout(100)
        pg20.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        pg20.wait_for_timeout(100)
        gap = pg20.evaluate('''() => {
            const foot = document.querySelector('.foot').getBoundingClientRect();
            const bar = document.getElementById('bar').getBoundingClientRect();
            return Math.round(bar.top - foot.bottom);
        }''')
        eq('footer clear of the pinned bar', gap >= 0, True)
        cells = pg20.evaluate("[...document.querySelectorAll('#bar .b-cell')].map(c => { const r = c.getBoundingClientRect(); return [Math.round(r.left), Math.round(r.right), Math.round(r.top)]; })")
        eq('three bar cells on one row', len(set(c[2] for c in cells)), 1)
        eq('bar cells inside the screen', all(c[0] >= 0 and c[1] <= 320 for c in cells), True)
        eq('bar text not clipped at 320', pg20.evaluate("[...document.querySelectorAll('#bar .b-amt')].every(e => e.scrollWidth <= e.clientWidth + 1)"), True)
        pg20.set_viewport_size({'width': 390, 'height': 844})
        pg20.wait_for_timeout(100)
        pg20.evaluate('window.scrollTo(0, 0)')
        pg20.locator('#payCard').screenshot(path=D + '/rate-card-full.png')
        pg20.screenshot(path=D + '/rate-phone-open.png', full_page=True)
        ctx20.close()

    with section('layout extremes'):
        ctx21, pg21 = new_page(browser)
        open_all(pg21)
        extremes = [
            ('huge price', dict(DEFAULT, price=10000000)),
            ('tiny hours', dict(DEFAULT, price=10000000, onsiteH=0.001, driveMin=0, setupMin=0, miles=0, crew=1)),
            ('huge loss', dict(DEFAULT, price=1, chem=10000000, other=10000000)),
            ('max hours', dict(DEFAULT, onsiteH=1000, price=500000)),
            ('big crew', dict(DEFAULT, crew=50)),
            ('long fee label', dict(DEFAULT, feePct=12.34, feeFixed=1234567.89, price=10000000)),
            ('six figure pay', dict(DEFAULT, price=900000, onsiteH=2, driveMin=0, setupMin=0)),
            ('four figure pay', dict(DEFAULT, price=9000, onsiteH=2, driveMin=0, setupMin=0, crew=1)),
            ('nine character pay', dict(DEFAULT, price=100000, onsiteH=3, driveMin=0, setupMin=0, crew=1)),
            ('negative six figures', dict(DEFAULT, price=1, other=900000, onsiteH=2, driveMin=0, setupMin=0)),
            ('big fixed fee', dict(DEFAULT, feeFixed=9999999)),
            ('very small numbers', dict(DEFAULT, price=0.01, onsiteH=0.01, driveMin=0, setupMin=0, miles=0, chem=0, wearH=0, crew=1)),
        ]
        for label, job in extremes:
            set_job(pg21, job)
            for w in (320, 390, 1280):
                o = overflow(pg21, w)
                eq('%s: no horizontal overflow at %d' % (label, w), (o['sw'] <= o['W'], o['bad']), (True, []))
            pg21.set_viewport_size({'width': 320, 'height': 800})
            pg21.wait_for_timeout(100)
            fit = pg21.evaluate('''() => {
                const n = document.getElementById('payNum').getBoundingClientRect();
                const m = document.getElementById('meter').getBoundingClientRect();
                const sc = document.querySelector('.g-scale').getBoundingClientRect();
                return {left: n.left - m.left, right: m.right - n.right, w: n.width, mw: m.width, clipped: document.getElementById('payNum').scrollWidth > document.getElementById('payNum').clientWidth + 1,
                        overScale: n.bottom > sc.top + 1 && (n.left < sc.left + 40 || n.right > sc.right - 40)};
            }''')
            eq('%s: reading sits inside the dial' % label, (fit['left'] >= 0, fit['right'] >= 0, fit['clipped']), (True, True, False))
            eq('%s: reading is narrower than the dial opening' % label, fit['w'] <= fit['mw'] * 0.72, True)
            # Fit checks need the real font, which only the built page carries.
            if STANDALONE and pg21.is_visible('#bar'):
                eq('%s: bar text not clipped at 320' % label, pg21.evaluate("[...document.querySelectorAll('#bar .b-amt')].filter(e => e.scrollWidth > e.clientWidth + 1).map(e => e.id + ':' + e.textContent)"), [])
            eq('%s: tables do not push the page wide' % label, overflow(pg21, 320)['sw'] <= 320, True)
            if label in ('huge loss', 'nine character pay', 'tiny hours'):
                pg21.set_viewport_size({'width': 320, 'height': 800})
                pg21.evaluate('window.scrollTo(0, 0)')
                pg21.locator('#payCard').screenshot(path=D + '/rate-extreme-%s.png' % label.replace(' ', '-'))
        ctx21.close()

    with section('desktop layout'):
        ctx22, pg22 = new_page(browser, w=1280, h=900)
        eq('bar hidden on desktop', pg22.is_visible('#bar'), False)
        pos = pg22.evaluate('''() => {
            const a = document.querySelector('.inputs').getBoundingClientRect();
            const r = document.querySelector('.results').getBoundingClientRect();
            const m = document.querySelector('.more').getBoundingClientRect();
            const app = document.querySelector('.app').getBoundingClientRect();
            return {inputsRight: a.right, resultsLeft: r.left, resultsTop: r.top, inputsTop: a.top, moreLeft: m.left, moreRight: m.right, inputsLeft: a.left, resultsW: r.width, appW: app.width,
                    moreTop: m.top, inputsBottom: a.bottom};
        }''')
        eq('results to the right of inputs', pos['resultsLeft'] > pos['inputsRight'], True)
        eq('results aligned with inputs at the top', abs(pos['resultsTop'] - pos['inputsTop']) < 2, True)
        eq('more shares the inputs column', abs(pos['moreLeft'] - pos['inputsLeft']) < 1 and abs(pos['moreRight'] - pos['inputsRight']) < 1, True)
        eq('more sits under the inputs', pos['moreTop'] >= pos['inputsBottom'] - 1, True)
        eq('results column is 400 wide', round(pos['resultsW']), 400)
        eq('page content is capped at 1040', round(pos['appW']) <= 1040, True)
        pg22.screenshot(path=D + '/rate-desktop-light.png')
        pg22.screenshot(path=D + '/rate-desktop-full.png', full_page=True)
        pg22.evaluate('window.scrollTo(0, 900)')
        pg22.wait_for_timeout(150)
        eq('results stay in view when scrolled', pg22.evaluate("document.querySelector('.results').getBoundingClientRect().top") < 40, True)
        eq('reading still on screen after scrolling', pg22.evaluate("document.getElementById('payNum').getBoundingClientRect().top") > 0, True)
        ctx22.close()
        ctx22b, pg22b = new_page(browser, w=899, h=900)
        eq('bar shows just under the breakpoint', pg22b.is_visible('#bar'), True)
        eq('single column just under the breakpoint', pg22b.evaluate("document.querySelector('.results').getBoundingClientRect().left < 20"), True)
        ctx22b.close()
        ctx22c, pg22c = new_page(browser, w=1440, h=900)
        o = pg22c.evaluate("(() => { const a = document.querySelector('.app').getBoundingClientRect(); return [Math.round(a.left), Math.round(a.right)]; })()")
        eq('wide screens centre the page', abs(o[0] - (1440 - o[1])) <= 1, True)
        ctx22c.close()
        ctx22d, pg22d = new_page(browser, w=1280, h=640)
        pg22d.evaluate('window.scrollTo(0, 400)')
        pg22d.wait_for_timeout(120)
        eq('short window: results panel fits the window', pg22d.evaluate("document.querySelector('.results').getBoundingClientRect().height <= window.innerHeight"), True)
        ctx22d.close()

    with section('dark'):
        ctx23, pg23 = new_page(browser, scheme='dark')
        pg23.screenshot(path=D + '/rate-dark-top.png')
        pg23.locator('#payCard').screenshot(path=D + '/rate-dark-card.png')
        pg23.screenshot(path=D + '/rate-dark-full.png', full_page=True)
        eq('dark body background', pg23.evaluate("getComputedStyle(document.body).backgroundColor"), 'rgb(23, 17, 12)')
        eq('dark color scheme for controls', pg23.evaluate("getComputedStyle(document.documentElement).colorScheme"), 'dark')
        ctx23.close()
        ctx23b, pg23b = new_page(browser, scheme='dark', w=1280, h=900)
        pg23b.screenshot(path=D + '/rate-desktop-dark.png')
        ctx23b.close()
        ctx24, pg24 = new_page(browser, scheme='dark')
        pg24.evaluate("document.documentElement.setAttribute('data-theme', 'light')")
        eq('data-theme light wins over a dark system', pg24.evaluate("getComputedStyle(document.body).backgroundColor"), 'rgb(241, 236, 229)')
        ctx24.close()
        ctx24b, pg24b = new_page(browser, scheme='light')
        pg24b.evaluate("document.documentElement.setAttribute('data-theme', 'dark')")
        eq('data-theme dark wins over a light system', pg24b.evaluate("getComputedStyle(document.body).backgroundColor"), 'rgb(23, 17, 12)')
        eq('data-theme dark sets the dark control colours', pg24b.evaluate("getComputedStyle(document.documentElement).colorScheme"), 'dark')
        ctx24b.close()

    for scheme in ('light', 'dark'):
        with section('contrast ' + scheme):
            cx, pgc = new_page(browser, scheme=scheme)
            open_all(pgc)
            tap(pgc, '#saveBtn')
            put(pgc, '#saveName', 'x')
            tap(pgc, '#saveForm button[type=submit]')
            pgc.evaluate("document.getElementById('sheet').hidden = false")
            res = pgc.evaluate(CONTRAST_JS, CONTRAST_SELS)
            pgc.evaluate("document.getElementById('sheet').hidden = true")
            # each message kind needs its own state
            put(pgc, '#price', '100')
            res += pgc.evaluate(CONTRAST_JS, ['.alert.bad p'])
            put(pgc, '#price', '300')
            put(pgc, '#helperPay', '0')
            res += pgc.evaluate(CONTRAST_JS, ['.alert.warn p'])
            put(pgc, '#helperPay', '18')
            put(pgc, '#price', '')
            res += pgc.evaluate(CONTRAST_JS, ['.alert.info p', '.empty'])
            put(pgc, '#price', '300')
            weak = [(s, r, n) for (s, r, n) in res if r is not None and r < n]
            missing = [s for (s, r, n) in res if r is None]
            eq('%s text contrast is strong enough everywhere' % scheme, weak, [])
            eq('%s contrast audit found its elements' % scheme, missing, [])
            # the dial itself: arc, dot and goal mark need 3:1 against the card, in each state
            for label, job in (('good', dict(DEFAULT, price=400)), ('warn', dict(DEFAULT)), ('bad', dict(DEFAULT, price=150)), ('accent', dict(DEFAULT, goal=0))):
                set_job(pgc, job)
                g = pgc.evaluate(GRAPHIC_JS)
                eq('%s gauge state %s' % (scheme, label), gauge(pgc)['state'], label)
                eq('%s gauge %s: arc, dot and goal mark at least 3:1' % (scheme, label), [k for k in ('fill', 'dot', 'tick') if g[k] < 3.0 and not (k == 'tick' and label == 'accent')], [])
            cx.close()

    with section('ios zoom guard'):
        cz, pgz = new_page(browser)
        open_all(pgz)
        tap(pgz, '#saveBtn')
        pgz.evaluate("document.getElementById('sheet').hidden = false")
        res = pgz.evaluate('''() => [...document.querySelectorAll('input, select, textarea')].filter(el => el.type !== 'hidden')
            .map(el => [el.tagName + '#' + el.id, parseFloat(getComputedStyle(el).fontSize)])''')
        eq('controls checked', len(res) >= 19, True)
        eq('every text control is 16px or larger', [r for r in res if r[1] < 16], [])
        cz.close()

    with section('tap targets'):
        cq, pgq = new_page(browser)
        open_all(pgq)
        tap(pgq, '#saveBtn')
        tap(pgq, '#saveForm button[type=submit]')
        pgq.evaluate("document.getElementById('sheet').hidden = false")
        TAP_JS = '''() => [...document.querySelectorAll('button, .pick, summary, .affix, textarea')].filter(e => e.getClientRects().length).map(e => {
            const r = e.getBoundingClientRect(); return [e.id || e.className || e.tagName, Math.round(r.width), Math.round(r.height)]; })
            .filter(x => x[2] < 40 || x[1] < 40)'''
        for w in (320, 340, 360, 375, 390, 430, 768, 1280):
            pgq.set_viewport_size({'width': w, 'height': 800})
            pgq.wait_for_timeout(100)
            small = pgq.evaluate(TAP_JS)
            # the inline Copy link next to the email address is text-sized by design
            small = [s for s in small if 'mail-copy' not in str(s[0])]
            eq('no undersized tap targets at %d' % w, small, [])
        pgq.set_viewport_size({'width': 390, 'height': 800})
        pgq.wait_for_timeout(100)
        # a text field never gets so narrow that typing a number is awkward
        narrow = pgq.evaluate("[...document.querySelectorAll('.affix input')].filter(e => e.getClientRects().length).map(e => [e.id, Math.round(e.getBoundingClientRect().width)]).filter(x => x[1] < 56)")
        eq('no cramped text fields at 390', narrow, [])
        pgq.set_viewport_size({'width': 320, 'height': 800})
        pgq.wait_for_timeout(100)
        narrow = pgq.evaluate("[...document.querySelectorAll('.affix input')].filter(e => e.getClientRects().length).map(e => [e.id, Math.round(e.getBoundingClientRect().width)]).filter(x => x[1] < 56)")
        eq('no cramped text fields at 320', narrow, [])
        # the whole row of a what-if price is a button, not just its text
        row_h = pgq.evaluate("[...document.querySelectorAll('#priceBody .pick')].map(b => Math.round(b.getBoundingClientRect().height))")
        eq('price picks are at least 40 tall', [h for h in row_h if h < 40], [])
        cq.close()

    with section('keyboard'):
        ck, pgk = new_page(browser)
        pgk.evaluate('document.body.focus()')
        stops = []
        for i in range(34):
            pgk.keyboard.press('Tab')
            stops.append(pgk.evaluate("""() => { const e = document.activeElement; const cs = getComputedStyle(e); const aff = e.closest('.affix'); const acs = aff ? getComputedStyle(aff) : null;
                return [e.id || (e.tagName === 'BUTTON' && e.classList.contains('chip') ? 'chip' : e.tagName.toLowerCase()), cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) > 0,
                        !!acs && acs.outlineStyle !== 'none' && parseFloat(acs.outlineWidth) > 0]; }"""))
        names = [s[0] for s in stops]
        eq('tab order starts at the example button then the price', names[:2], ['exampleClear', 'price'])
        eq('hours chips come before the hours field', names[2:9], ['chip'] * 6 + ['onsite'])
        eq('tab order through the job fields', [n for n in names if n in ('crew', 'driveMin', 'miles', 'setupMin', 'chem', 'other', 'clearBtn', 'goal')],
           ['crew', 'driveMin', 'miles', 'setupMin', 'chem', 'other', 'clearBtn', 'goal'])
        eq('then the usual numbers summary', names[names.index('goal') + 1], 'summary')
        eq('every tab stop shows a focus ring', [n for (n, a, b) in stops if not (a or b)], [])
        # chips work from the keyboard
        pgk.locator('#hoursChips button[data-v="4"]').focus()
        pgk.keyboard.press('Enter')
        eq('Enter presses a chip', pressed(pgk, 'hoursChips'), ['4'])
        pgk.locator('#hoursChips button[data-v="6"]').focus()
        pgk.keyboard.press('Space')
        eq('Space presses a chip', pressed(pgk, 'hoursChips'), ['6'])
        # the details open with Enter
        pgk.locator('#usualBox > summary').focus()
        pgk.keyboard.press('Enter')
        eq('Enter opens the usual numbers', pgk.evaluate("document.getElementById('usualBox').open"), True)
        # Enter in the save name field saves
        pgk.locator('#saveBtn').focus()
        pgk.keyboard.press('Enter')
        pgk.keyboard.type('Keyboard job')
        pgk.keyboard.press('Enter')
        pgk.wait_for_timeout(100)
        eq('Enter in the name field saves the job', txt(pgk, '#savedList .sv-name'), 'Keyboard job')
        ck.close()

    with section('reduced motion'):
        cr, pgr = new_page(browser, reduced=True)
        d1 = pgr.evaluate("getComputedStyle(document.querySelector('.chip')).transitionDuration")
        cr.close()
        cn, pgn = new_page(browser, reduced=False)
        d2 = pgn.evaluate("getComputedStyle(document.querySelector('.chip')).transitionDuration")
        cn.close()
        eq('no transitions when reduced motion is on', d1, '0s')
        eq('short transitions otherwise', d2 != '0s', True)

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
            # every weight the stylesheet asks for has a face behind it
            used = pgf.evaluate('''() => { const out = new Set(); document.querySelectorAll('body *').forEach(el => { const cs = getComputedStyle(el); if (el.getClientRects().length && el.childNodes.length)
                out.add(cs.fontFamily.split(',')[0].replace(/["']/g, '').trim() + ' ' + cs.fontWeight); }); return [...out].sort(); }''')
            have = {'Big Shoulders Display': {700, 800}, 'Public Sans': {400, 500, 600, 700}, 'IBM Plex Mono': {400, 500}}
            missing_w = [u for u in used if u.rsplit(' ', 1)[0] in have and int(u.rsplit(' ', 1)[1]) not in have[u.rsplit(' ', 1)[0]]]
            eq('every font weight in use has an embedded face', missing_w, [])
            eq('tabular digits survive the subset', pgf.evaluate('''() => {
                const w = (t) => {
                    const s = document.createElement('span');
                    s.style.cssText = "font:400 16px 'Public Sans';position:absolute;visibility:hidden;white-space:pre;font-variant-numeric:tabular-nums";
                    s.textContent = t; document.body.appendChild(s);
                    const r = s.getBoundingClientRect().width; s.remove(); return r;
                };
                return w('1111') === w('0000') && w('1111') > 0;
            }'''), True)
            eq('the compact reading letters render in the display face', pgf.evaluate('''() => {
                const w = (t, fam) => {
                    const s = document.createElement('span');
                    s.style.cssText = "font:800 40px " + fam + ";position:absolute;visibility:hidden;white-space:pre";
                    s.textContent = t; document.body.appendChild(s);
                    const r = s.getBoundingClientRect().width; s.remove(); return r;
                };
                return ['$', 'K', 'M', 'B', 'T', '-', '<'].every(c => w(c, "'Big Shoulders Display', monospace") !== w(c, "monospace"));
            }'''), True)
            eq('multiply and divide signs render in the mono face', pgf.evaluate('''() => {
                const w = (t) => {
                    const s = document.createElement('span');
                    s.style.cssText = "font:400 13px 'IBM Plex Mono';position:absolute;visibility:hidden;white-space:pre";
                    s.textContent = t; document.body.appendChild(s);
                    const r = s.getBoundingClientRect().width; s.remove(); return r;
                };
                return w(String.fromCharCode(215)) > 0 && w(String.fromCharCode(247)) > 0 && Math.abs(w(String.fromCharCode(215)) - w('x')) < 0.6;
            }'''), True)
            cf.close()

        with section('standalone: metadata'):
            cm, pgm = new_page(browser)
            eq('document title', pgm.title(), SITE_TITLE)
            eq('lang', pgm.evaluate('document.documentElement.lang'), 'en')
            eq('description length', 60 < len(pgm.get_attribute('meta[name=description]', 'content')) <= 160, True)
            eq('canonical', pgm.get_attribute('link[rel=canonical]', 'href'), SITE_URL)
            eq('og:title', pgm.get_attribute('meta[property="og:title"]', 'content'), SITE_TITLE)
            eq('og:url', pgm.get_attribute('meta[property="og:url"]', 'content'), SITE_URL)
            eq('og:image', pgm.get_attribute('meta[property="og:image"]', 'content'), SITE_URL + 'og.png')
            eq('og:image size', (pgm.get_attribute('meta[property="og:image:width"]', 'content'), pgm.get_attribute('meta[property="og:image:height"]', 'content')), ('1200', '630'))
            eq('og:image alt', len(pgm.get_attribute('meta[property="og:image:alt"]', 'content')) > 30, True)
            eq('twitter card', pgm.get_attribute('meta[name="twitter:card"]', 'content'), 'summary_large_image')
            eq('twitter image', pgm.get_attribute('meta[name="twitter:image"]', 'content'), SITE_URL + 'og.png')
            eq('theme colors', pgm.evaluate("[...document.querySelectorAll('meta[name=theme-color]')].map(m => m.content)"), ['#F1ECE5', '#17110C'])
            eq('favicon is a data uri', (pgm.get_attribute('link[rel=icon]', 'href') or '').startswith('data:image/svg+xml;base64,'), True)
            eq('apple touch icon', pgm.get_attribute('link[rel=apple-touch-icon]', 'href'), 'apple-touch-icon.png')
            eq('mailto anchor', pgm.get_attribute('a.mail', 'href'), 'mailto:' + SUPPORT)
            eq('privacy link', pgm.get_attribute('.foot a[href="privacy.html"]', 'href'), 'privacy.html')
            eq('rinse quote link', pgm.get_attribute('.foot a[href*="rinse-quote"]', 'href'), 'https://sanjixysti-creator.github.io/rinse-quote/')
            eq('rinse mix link', pgm.get_attribute('.foot a[href*="rinse-mix"]', 'href'), 'https://sanjixysti-creator.github.io/rinse-mix/')
            eq('maker line', 'Made by Xysti Software' in txt(pgm, '.foot'), True)
            eq('no robots block', pgm.evaluate("document.querySelectorAll('meta[name=robots]').length"), 0)
            cm.close()

        for scheme in ('light', 'dark'):
            with section('standalone: privacy ' + scheme):
                cp, pgp = new_page(browser, scheme=scheme, url=ORIGIN + PAGE_PATH + 'privacy.html')
                eq('privacy title', pgp.title(), 'Privacy Policy - Rinse Rate')
                has('privacy says no analytics', txt(pgp, 'body'), 'no analytics')
                has('privacy says what is stored', txt(pgp, 'body'), 'The jobs you save, including the names you give them')
                eq('privacy mailto', pgp.get_attribute('a[href^="mailto:"]', 'href'), 'mailto:' + SUPPORT)
                eq('privacy back link', pgp.get_attribute('.back', 'href'), './')
                eq('privacy brand link', pgp.get_attribute('.brand', 'href'), './')
                eq('privacy has no dash look-alikes', [c for c in DASHES if c in txt(pgp, 'body')], [])
                for w in (320, 390, 768, 1200):
                    o = overflow(pgp, w)
                    eq('privacy no overflow %s %d' % (scheme, w), (o['sw'] <= o['W'], o['bad']), (True, []))
                pgp.set_viewport_size({'width': 390, 'height': 844})
                pgp.screenshot(path=D + '/rate-privacy-%s.png' % scheme, full_page=True)
                eq('privacy body bg %s' % scheme, pgp.evaluate("getComputedStyle(document.body).backgroundColor"),
                   'rgb(241, 236, 229)' if scheme == 'light' else 'rgb(23, 17, 12)')
                res = pgp.evaluate(CONTRAST_JS, ['.updated', 'p', 'li', 'a', '.back', 'h1', 'h2', '.brand span'])
                eq('privacy %s contrast' % scheme, [(s, r, n) for (s, r, n) in res if r is not None and r < n], [])
                cp.close()

        with section('standalone: no request leaves the site'):
            eq('external requests', sorted(set(ext_reqs)), [])

    browser.close()

# ---------------------------------------------------------------- report
real_errs = [e for e in errs if not (e[0] == 'warning' and 'font' in e[1].lower())]
if real_errs:
    fails.append('console errors\n    %r' % (real_errs[:6],))

print('checks passed: %d, failed: %d' % (passes, len(fails)))
for f in fails[:400]:
    print('FAIL', f)
if len(fails) > 400:
    print('... and %d more' % (len(fails) - 400))
httpd.shutdown()
raise SystemExit(1 if fails else 0)
