import contextlib, datetime, functools, http.server, json, math, os, random, re, struct, threading
from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction
from playwright.sync_api import sync_playwright

D = os.path.dirname(os.path.abspath(__file__))
SRC = D + '/drive-rate.html'
OUT = D + '/drive-test.html'

# DRIVE_STANDALONE=/path/to/site/drive-rate/index.html tests the self-hosted page instead of the fragment.
STANDALONE = os.environ.get('DRIVE_STANDALONE', '')
# DRIVE_SECTIONS=math,ui,... runs only some groups while developing. Empty means everything.
SECTIONS = set(x for x in os.environ.get('DRIVE_SECTIONS', '').split(',') if x)
SITE_URL = 'https://sanjixysti-creator.github.io/drive-rate/'
SITE_TITLE = 'Drive Rate: Is This Delivery Offer Worth It? Free Calculator'
STORE = 'drive-rate-v1'
ALLOWED_HOSTS = {'fonts.googleapis.com', 'fonts.gstatic.com', 'sanjixysti-creator.github.io', 'www.irs.gov'}
NOW0 = '2026-10-02T09:30:00'


def on(name):
    return not SECTIONS or name in SECTIONS


# Dash look-alikes are checked for without typing them, so this file stays free of them too.
EM, EN, MINUS = chr(0x2014), chr(0x2013), chr(0x2212)
DASHES = EM + EN + MINUS
TIMES, DIVIDE = chr(0xd7), chr(0xf7)

src = open(SRC, encoding='utf-8').read()
msup = re.search(r"var SUPPORT = '([^']*)'", src)
SUPPORT = msup.group(1) if msup else ''
mm = re.search(r'/\* MATH-BLOCK-START[^*]*\*/(.*?)/\* MATH-BLOCK-END \*/', src, re.S)
MATH = mm.group(1) if mm else ''

if STANDALONE:
    built = open(STANDALONE, encoding='utf-8').read()
    SITE_DIR = os.path.dirname(STANDALONE)
    SERVE = os.path.dirname(SITE_DIR)
    PAGE_PATH = '/' + os.path.basename(SITE_DIR) + '/'
else:
    built = ''
    SERVE = D
    PAGE_PATH = '/drive-test.html'
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


def batch(name, bad, count):
    """One check per case: `count` cases were compared, `bad` holds the differences."""
    global passes
    if bad:
        fails.append('%s: %d of %d cases differ, first: %s' % (name, len(bad), count, ' | '.join(bad[:4])))
    else:
        passes += count


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
STUB_NO_CLIP = ("window.__copied = null;"
                "Object.defineProperty(navigator, 'clipboard', {configurable: true, value: undefined});"
                "document.execCommand = function () { return false; };")
STUB_NO_STORAGE = (STUB_OK +
                   "Storage.prototype.getItem = function () { throw new Error('blocked'); };"
                   "Storage.prototype.setItem = function () { throw new Error('blocked'); };"
                   "Storage.prototype.removeItem = function () { throw new Error('blocked'); };")

# A clock the tests can set. Only Date is replaced, so timers behave normally.
CLOCK_JS = """(function () {
  var RealDate = Date, offset = 0;
  function setNow(s) { offset = new RealDate(s).getTime() - RealDate.now(); }
  setNow(%s);
  function FakeDate() {
    var a = arguments;
    if (!(this instanceof FakeDate)) return new RealDate(RealDate.now() + offset).toString();
    if (a.length === 0) return new RealDate(RealDate.now() + offset);
    if (a.length === 1) return new RealDate(a[0]);
    return new RealDate(a[0], a[1], a[2] == null ? 1 : a[2], a[3] || 0, a[4] || 0, a[5] || 0, a[6] || 0);
  }
  FakeDate.prototype = RealDate.prototype;
  FakeDate.now = function () { return RealDate.now() + offset; };
  FakeDate.UTC = RealDate.UTC;
  FakeDate.parse = RealDate.parse;
  window.Date = FakeDate;
  window.__setNow = setNow;
})();"""


def new_page(browser, stub=STUB_OK, scheme='light', w=390, h=844, pre_state=None, url=None, reduced=False, now=NOW0, raw_state=None):
    ctx = browser.new_context(viewport={'width': w, 'height': h}, color_scheme=scheme, device_scale_factor=1,
                              reduced_motion='reduce' if reduced else 'no-preference', timezone_id='America/Los_Angeles', locale='en-US')
    ctx.add_init_script(stub)
    if now:
        ctx.add_init_script(CLOCK_JS % json.dumps(now))
    if pre_state is not None:
        ctx.add_init_script("try { if (!localStorage.getItem('%s')) localStorage.setItem('%s', %s); } catch (e) {}" % (STORE, STORE, json.dumps(json.dumps(pre_state))))
    if raw_state is not None:
        ctx.add_init_script("try { if (!localStorage.getItem('%s')) localStorage.setItem('%s', %s); } catch (e) {}" % (STORE, STORE, json.dumps(raw_state)))
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


def toast(page):
    return txt(page, '#toast') if page.is_visible('#toast') else ''


def stub(page, sel='#stub'):
    return page.evaluate("sel => [...document.querySelectorAll(sel + ' .srow')].map(r => [r.querySelector('dt').textContent.trim(), r.querySelector('dd').textContent.trim()])", sel)


def stub_map(page, sel='#stub'):
    return {k: v for k, v in stub(page, sel)}


def vdata(page):
    return page.get_attribute('#dash', 'data-v')


def stored(page):
    raw = page.evaluate("localStorage.getItem('%s')" % STORE)
    return json.loads(raw) if raw else None


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
def F(x):
    if isinstance(x, Fraction):
        return x
    return Fraction(repr(x)) if isinstance(x, float) else Fraction(x)


def jround(x):
    """JavaScript Math.round: halves go up."""
    return int(math.floor(x + 0.5))


def usd(x, places=2):
    """What Intl.NumberFormat shows for US dollars: half away from zero on the shortest decimal."""
    x = float(x)
    d = Decimal(repr(abs(x))).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    s = '{:,.{p}f}'.format(d, p=places)
    neg = x < 0 and d != 0
    return ('-' if neg else '') + '$' + s


def mnum(s):
    m = re.fullmatch(r'(-?)\$([0-9,]+(?:\.[0-9]+)?)', (s or '').strip())
    if not m:
        return None
    v = float(m.group(2).replace(',', ''))
    return -v if m.group(1) else v


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


def ceil_cents(x):
    return Fraction(math.ceil(x * 100), 100)


def floor_cents(x):
    return Fraction(math.floor(x * 100), 100)


CAR0 = dict(fuel='gas', gasPrice=3.5, mpg=28, kwhPrice=0.17, mikwh=3.2, maint=0.09, depr=0.12, carOther=0, know=False, cpm=0)
GOALS0 = dict(goalHour=20, goalMile=1.5, taxPct=20)
OFFER0 = dict(pay=6.5, tip=0, miles=4.2, minutes=22, wait=5, retMiles=1.5, retMin=4)


def ref_car(c):
    if c['fuel'] == 'electric':
        price, eff = F(c['kwhPrice']), F(c['mikwh'])
    else:
        price, eff = F(c['gasPrice']), F(c['mpg'])
    fuel = price / eff if eff > 0 else Fraction(0)
    missing = (not eff > 0) or (not price > 0)
    total = fuel + F(c['maint']) + F(c['depr']) + F(c['carOther'])
    cpm = F(c['cpm']) if c['know'] else total
    return dict(fuel=fuel, sum=total, cpm=cpm, fuelMissing=(not c['know']) and missing)


def ref_offer(o, cpm):
    gross = F(o['pay']) + F(o['tip'])
    miles = F(o['miles']) + F(o['retMiles'])
    minutes = F(o['minutes']) + F(o['wait']) + F(o['retMin'])
    hours = minutes / 60
    car = miles * cpm
    net = gross - car
    gh = F(o['goalHour']) if F(o['goalHour']) > 0 else None
    gm = F(o['goalMile']) if F(o['goalMile']) > 0 else None
    tax = F(o['taxPct'])
    r = dict(gross=gross, miles=miles, minutes=minutes, hours=hours, carCost=car, net=net, goalHour=gh, goalMile=gm)
    r['havePay'] = gross > 0
    r['haveMiles'] = miles > 0
    r['haveHours'] = minutes > 0
    r['nph'] = net / hours if minutes > 0 else None
    r['gpm'] = gross / miles if miles > 0 else None
    r['npm'] = net / miles if miles > 0 else None
    gains = net > 0
    r['setAside'] = net * tax / 100 if gains else None
    r['keep'] = net * (1 - tax / 100) if gains else None
    hr = r['nph'] / gh if (gh and r['nph'] is not None) else None
    mr = r['gpm'] / gm if (gm and r['gpm'] is not None) else None
    r['hourRatio'], r['mileRatio'] = hr, mr

    def zone(ratio):
        if ratio is None:
            return ''
        return 'take' if ratio >= 1 else ('maybe' if ratio >= Fraction(4, 5) else 'pass')
    r['hourZone'], r['mileZone'] = zone(hr), zone(mr)
    needH = (gh is not None and not r['haveHours'])
    needM = (gm is not None and not r['haveMiles'])
    if not r['havePay']:
        v = 'empty'
    elif gh is None and gm is None:
        v = 'nogoals'
    elif not gains:
        v = 'pass'
    elif needH or needM:
        v = 'need'
    else:
        ok = (gh is None or r['nph'] >= gh) and (gm is None or r['gpm'] >= gm)
        near_ = (gh is None or r['nph'] >= gh * Fraction(4, 5)) and (gm is None or r['gpm'] >= gm * Fraction(4, 5))
        v = 'take' if ok else ('borderline' if near_ else 'pass')
    r['v'] = v
    r['needHours'] = bool(gains and r['havePay'] and gh is not None and not r['haveHours']) if v == 'need' else False
    r['needMiles'] = bool(gains and r['havePay'] and gm is not None and not r['haveMiles']) if v == 'need' else False
    nh = gh * hours + car if (gh is not None and r['haveHours']) else None
    nm = gm * miles if (gm is not None and r['haveMiles']) else None
    r['needHour'], r['needMile'] = nh, nm
    known = (gh is not None or gm is not None) and (gh is None or nh is not None) and (gm is None or nm is not None)
    r['minPayKnown'] = known
    r['minPay'], r['binds'] = None, ''
    if known:
        cands = [x for x in (nh, nm) if x is not None]
        exact = max(cands)
        up = ceil_cents(exact)
        floor_pay = floor_cents(car) + Fraction(1, 100)
        r['minPay'] = max(up, floor_pay)
        if up < floor_pay:
            r['binds'] = 'cost'
        elif nh is not None and nm is not None and nh == nm:
            r['binds'] = 'both'
        else:
            r['binds'] = 'hour' if (nm is None or (nh is not None and nh >= nm)) else 'mile'
    return r


def ref_shift(entries, hours_ov, miles_ov, cpm, tax, rate):
    gross = sum((F(e['pay']) for e in entries), Fraction(0))
    paid = sum((F(e['miles']) for e in entries), Fraction(0))
    back = sum((F(e['ret']) for e in entries), Fraction(0))
    mins = sum((F(e['min']) for e in entries), Fraction(0))
    hours = F(hours_ov) if F(hours_ov) > 0 else mins / 60
    miles = F(miles_ov) if F(miles_ov) > 0 else paid + back
    car = miles * cpm
    net = gross - car
    aside = max(Fraction(0), net) * F(tax) / 100
    return dict(n=len(entries), gross=gross, hours=hours, miles=miles, carCost=car, net=net,
                nph=net / hours if hours > 0 else None, npm=net / miles if miles > 0 else None,
                gpm=gross / miles if miles > 0 else None, setAside=aside, takeHome=net - aside, deduction=miles * F(rate),
                hoursAuto=mins / 60, milesAuto=paid + back)


def day_num(s):
    import datetime
    y, m, d = [int(x) for x in s.split('-')]
    return datetime.date(y, m, d).toordinal()


def ref_rate(date):
    return Fraction(76, 100) if date >= '2026-07-01' else Fraction(725, 1000)


def ref_week(days, today, tax):
    t = day_num(today)
    inside = [d for d in days if 0 <= t - day_num(d['date']) <= 6]
    w = dict(n=len(inside), orders=sum(d['orders'] for d in inside), gross=sum((F(d['gross']) for d in inside), Fraction(0)),
             miles=sum((F(d['miles']) for d in inside), Fraction(0)), hours=sum((F(d['hours']) for d in inside), Fraction(0)),
             net=sum((F(d['net']) for d in inside), Fraction(0)), deduction=sum((F(d['miles']) * ref_rate(d['date']) for d in inside), Fraction(0)))
    w['carCost'] = w['gross'] - w['net']
    w['nph'] = w['net'] / w['hours'] if w['hours'] > 0 else None
    w['npm'] = w['net'] / w['miles'] if w['miles'] > 0 else None
    w['setAside'] = max(Fraction(0), w['net']) * F(tax) / 100
    w['takeHome'] = w['net'] - w['setAside']
    return w


def close_num(got, want, tol=0.0051):
    """Cents-level agreement, or 1e-9 relative for very large numbers. None and NaN count as 'undefined'."""
    gu = got is None or (isinstance(got, float) and math.isnan(got))
    wu = want is None
    if gu or wu:
        return gu and wu
    w = float(want)
    return abs(got - w) <= tol or abs(got - w) <= 1e-9 * abs(w)


def typed(v):
    return repr(v) if isinstance(v, float) else str(v)


def rand_offer(rnd, huge=False):
    def pick(zero, make):
        return 0 if rnd.random() < zero else make()
    o = dict(
        pay=pick(0.05, lambda: round(rnd.uniform(0.5, 60), 2)),
        tip=pick(0.6, lambda: round(rnd.uniform(0, 15), 2)),
        miles=pick(0.07, lambda: round(rnd.uniform(0.1, 40), rnd.choice([1, 2]))),
        minutes=pick(0.07, lambda: rnd.choice([5, 10, 15, 20, 30, 45, 60, rnd.randint(1, 180)])),
        wait=pick(0.5, lambda: rnd.choice([3, 5, 10, 15, rnd.randint(1, 30)])),
        retMiles=pick(0.5, lambda: round(rnd.uniform(0.1, 8), 1)),
        retMin=pick(0.5, lambda: rnd.randint(1, 20)),
        goalHour=rnd.choice([0, 15, 18, 20, 25, round(rnd.uniform(5, 60), 2)]),
        goalMile=rnd.choice([0, 1, 1.5, 2, round(rnd.uniform(0.2, 4), 2)]),
        taxPct=rnd.choice([0, 10, 15, 20, 25, 30, round(rnd.uniform(0, 60), 1)]),
    )
    if huge:
        o['pay'] = rnd.choice([1e7, 9999999.99, round(rnd.uniform(1e5, 1e7), 2)])
        o['miles'] = rnd.choice([100000, round(rnd.uniform(1e3, 1e5), 1), 0.001])
        o['minutes'] = rnd.choice([100000, 0.001, round(rnd.uniform(1, 1e5), 2)])
    return o


def rand_car(rnd):
    c = dict(CAR0)
    c['fuel'] = rnd.choice(['gas', 'electric'])
    c['gasPrice'] = rnd.choice([0, 3.5, 4.1, round(rnd.uniform(2, 7), 3)])
    c['mpg'] = rnd.choice([0, 28, 35, round(rnd.uniform(12, 60), 1)])
    c['kwhPrice'] = rnd.choice([0, 0.17, 0.35, round(rnd.uniform(0.08, 0.6), 3)])
    c['mikwh'] = rnd.choice([0, 3.2, 4, round(rnd.uniform(2, 5), 2)])
    c['maint'] = rnd.choice([0, 0.09, round(rnd.uniform(0, 0.3), 3)])
    c['depr'] = rnd.choice([0, 0.12, round(rnd.uniform(0, 0.4), 3)])
    c['carOther'] = rnd.choice([0, 0, 0.05, round(rnd.uniform(0, 0.5), 3)])
    c['know'] = rnd.random() < 0.25
    c['cpm'] = rnd.choice([0, 0.335, 0.5, round(rnd.uniform(0.05, 1.5), 3)])
    return c


# ---------------------------------------------------------------- source hygiene
if on('hygiene'):
  with section('source hygiene'):
    eq('no dash look-alikes', [c for c in DASHES if c in src], [])
    eq('title first', src.startswith('<title>Drive Rate</title>'), True)
    eq('no document tags', bool(re.search(r'<(html|head|body)[\s>]', src)), False)
    eq('no print', 'window.print' in src, False)
    eq('no mailto links', 'mailto:' in src, False)
    eq('no dialogs', bool(re.search(r'\b(alert|confirm|prompt)\(', src)), False)
    eq('no external scripts', re.findall(r'<script[^>]*\bsrc=', src), [])
    eq('no innerHTML', 'innerHTML' in src, False)
    eq('no eval', bool(re.search(r'\b(eval|new Function)\b', src)), False)
    eq('no network calls', bool(re.search(r'\b(fetch|XMLHttpRequest|sendBeacon|WebSocket)\b', src)), False)
    eq('no cookies', 'document.cookie' in src, False)
    eq('no placeholders', '@@' in src, False)
    hosts = set(re.findall(r'https?://([a-z0-9.\-]+)', src))
    eq('only allowed hosts', sorted(hosts - ALLOWED_HOSTS), [])
    eq('one mail span', src.count('<span class="mail"></span>'), 1)
    eq('one h1', len(re.findall(r'<h1[ >]', src)), 1)
    eq('one style block', src.count('<style>'), 1)
    eq('one script block', src.count('<script>'), 1)
    ids = re.findall(r'\bid="([^"]+)"', src)
    eq('ids are unique', sorted(set(i for i in ids if ids.count(i) > 1)), [])
    for_ids = re.findall(r'\bfor="([^"]+)"', src) + re.findall(r'aria-describedby="([^"]+)"', src) + re.findall(r'aria-labelledby="([^"]+)"', src)
    eq('every label, description and heading reference exists', sorted(set(i for i in for_ids if i not in ids)), [])
    js_ids = set(re.findall(r"\$\('([A-Za-z0-9_-]+)'\)", src))
    eq('every id the script uses exists in the markup', sorted(i for i in js_ids if i not in ids), [])
    eq('every id used with a prefix exists', sorted(i for i in ['rdHour', 'rdMile', 'vHour', 'vMile', 'gHour', 'gMile', 'fHour', 'fMile', 'pHour', 'pMile'] if i not in ids), [])
    eq('math block found once', (src.count('MATH-BLOCK-START'), src.count('MATH-BLOCK-END')), (1, 1))
    eq('math block does not touch the page', [w for w in ('document', 'window', 'localStorage', 'getElementById', '$(', 'navigator') if w in MATH], [])
    # outside links open in a new tab and say so
    anchors = re.findall(r'<a [^>]*href="(https?://[^"]+)"[^>]*>', src)
    outside = [a for a in re.findall(r'<a [^>]*>', src) if 'irs.gov' in a]
    eq('irs links open safely', [a for a in outside if 'target="_blank"' not in a or 'rel="noopener noreferrer"' not in a], [])
    eq('irs links exist in the markup or script', 'irs.gov' in src, True)
    eq('forms have no action', 'action=' in src, False)

    if STANDALONE:
        eq('built: doctype first', built.lstrip().lower().startswith('<!doctype html>'), True)
        eq('built: no dash look-alikes', [c for c in DASHES if c in built], [])
        eq('built: title', ('<title>%s</title>' % SITE_TITLE) in built, True)
        eq('built: no google fonts', 'fonts.googleapis.com' in built or 'fonts.gstatic.com' in built, False)
        eq('built: no claude.ai link', 'claude.ai' in built.lower(), False)
        eq('built: no external scripts', re.findall(r'<script[^>]*\bsrc=', built), [])
        bh = set(re.findall(r'https?://([a-z0-9.\-]+)', built))
        eq('built: only known hosts', sorted(bh - {'www.w3.org', 'sanjixysti-creator.github.io', 'www.irs.gov'}), [])
        eq('built: no print', 'window.print' in built, False)
        eq('built: no dialogs', bool(re.search(r'\b(alert|confirm|prompt)\(', built)), False)
        eq('built: noscript', '<noscript>' in built, True)
        eq('built: one style block', built.count('<style>'), 1)
        eq('built: one mailto anchor', built.count('href="mailto:'), 1)
        eq('built: privacy link', 'href="privacy.html"' in built, True)
        eq('built: canonical', ('<link rel="canonical" href="%s">' % SITE_URL) in built, True)
        eq('built: og image', ('<meta property="og:image" content="%sog.png">' % SITE_URL) in built, True)
        eq('built: viewport has no cover', 'viewport-fit=cover' in built, False)
        eq('built: carries the tested maths block byte for byte', MATH.strip() in built, True)
        eq('built: carries the script text of the fragment', re.search(r'<script>(.*)</script>', src, re.S).group(1) in built, True)
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

    # ------------------------------------------------------------ the maths block on its own
    # The block between the markers is cut out of the page and run in an empty tab, so the numbers are checked
    # without any of the page around them.
    EXPORTS = ('parseNum parseMinutes numOf nn fmtNum money money0 moneyBig neg cents hm plural pctOf ceilCents r6 pad2 localDate dayNum '
               'dateOfNum dateLabel dateShort irsRow irsRateFor irsStale carInfo meets zoneOf calcOffer calcShift byApp weekOf clampField '
               'IRS_RATES IRS_LAST_YEAR IRS_AS_OF APPS LIMITS').split()
    MATH_JS = '(() => { window.__M = (function () {' + MATH + ';return {' + ','.join('%s: %s' % (n, n) for n in EXPORTS) + '};})(); return true; })()'
    mctx = browser.new_context(timezone_id='America/Los_Angeles', locale='en-US')
    mp = mctx.new_page()
    mp.on('pageerror', lambda e: errs.append(('pageerror', str(e))))
    mp.goto('about:blank')
    math_ok = True
    try:
        mp.evaluate(MATH_JS)
    except Exception as e:
        math_ok = False
        fails.append('the maths block does not load on its own: %s' % str(e).strip().splitlines()[0][:200])

    def jsm(expr, arg=None):
        return mp.evaluate('(a) => { const M = window.__M; return ' + expr + '; }', arg)

    def undef(x):
        return None if (isinstance(x, float) and math.isnan(x)) else x

    def tight(g, w):
        """Raw maths: agreement to 1e-9 of the size of the number (at least 1e-9 absolute). None and NaN both mean 'undefined'."""
        gu = g is None or (isinstance(g, float) and math.isnan(g))
        if gu or w is None:
            return gu and w is None
        return abs(g - float(w)) <= 1e-9 * max(1.0, abs(float(w)))

    # ---- reading numbers
    if on('math') and math_ok:
      with section('math: reading numbers'):
        NUM_CASES = [
            ('12.5', 12.5), ('12', 12), ('0', 0), ('0.5', 0.5), ('.5', 0.5), (',5', 0.5), ('5.', 5), ('$6.50', 6.5), (' $ 6.50 ', 6.5),
            ('$1,234.50', 1234.5), ('1,234', 1234), ('1,234,567', 1234567), ('123,456,789', 123456789), ('12,5', 12.5), ('1,25', 1.25),
            ('1,2345', 1.2345), ('0,500', 0.5), ('1234,567', 1234.567), ('1.234,5', 1234.5), ('1.234.567,89', 1234567.89),
            ('1,234,567.89', 1234567.89), ('6.50 + 2', 6.5), ('7 dollars 50', 7), ('about 12 miles', 12), ('-3', -3), ('--3', -3), ('-0.5', -0.5),
            ('abc', None), ('', None), ('   ', None), ('$', None), ('.', None), (',', None), ('-', None), ('Infinity', None), ('1e3', 1),
            ('1.5.5', 1.5), ('00012', 12), ('10,000.5', 10000.5), ('999,999', 999999), ('0.1234567890123', 0.1234567890123),
            ('9' * 400, None), (None, None), (chr(0x663), None),
        ]
        got = [undef(g) for g in jsm('a.map(x => M.parseNum(x))', [c[0] for c in NUM_CASES])]
        for (s, want), g in zip(NUM_CASES, got):
            eq('parseNum(%r)' % (s if s is None or len(s) < 30 else s[:12] + '...'), g, want)
        # a stored number is used as it is: exponent forms must not be cut down to their first digit
        eq('numOf table', [undef(x) for x in jsm('[M.numOf(1e-7), M.numOf("1e-7"), M.numOf(1e30), M.numOf(Infinity), M.numOf(NaN), M.numOf(null), M.numOf(true), M.numOf([1]), M.numOf("12,5"), M.numOf(0), M.numOf(-3)]')],
           [1e-7, 1, 1e30, None, None, None, None, 1, 12.5, 0, -3])
        eq('nn keeps tiny and huge numbers', jsm('[M.nn(1e-7), M.nn(1e30), M.nn(-1e-7), M.nn(Infinity), M.nn(Infinity, 4)]'), [1e-7, 1e30, 0, 0, 4])
        # nn never goes below zero and falls back to the default
        eq('nn table', jsm('[M.nn("12.5"), M.nn("-3"), M.nn("abc"), M.nn("abc", 5), M.nn(null), M.nn("$1,234.50"), M.nn("0")]'), [12.5, 0, 0, 5, 0, 1234.5, 0])
        MIN_CASES = [
            ('22', None, 22), ('22', 'm', 22), ('1.5', 'h', 90), ('1,5', 'h', 90), ('30', 'h', 1800), ('0', 'h', 0), ('0', None, 0),
            ('90m', None, 90), ('90 min', None, 90), ('90 minutes', None, 90), ('1.5 hours', None, 90), ('1,5 hours', None, 90),
            ('2h', None, 120), ('2 hr', None, 120), ('2 hrs', None, 120), ('2h30', None, 150), ('2h 30m', None, 150), ('2 h 30 min', None, 150),
            ('2:30', None, 150), ('0:45', None, 45), ('2:5', None, 125), ('1 hour 15 min', None, 75), ('1 hr 5 m', None, 65), ('2H30', None, 150),
            ('2h30', 'h', 150), ('90m', 'h', 90), ('1.5', None, 1.5), ('45.5', None, 45.5), ('-5', None, -5),
            ('1h60', None, None), ('2:75', None, None), ('2:3:4', None, None), ('1:', None, None), ('abc', None, None), ('', None, None),
            (None, None, None), ('H', None, None), ('$5', None, 5),
        ]
        got = [undef(g) for g in jsm('a.map(x => M.parseMinutes(x[0], x[1]))', [[c[0], c[1]] for c in MIN_CASES])]
        for (s, plain, want), g in zip(MIN_CASES, got):
            eq('parseMinutes(%r, %r)' % (s, plain), g, want)
        lim = jsm('[M.clampField("pay", -5), M.clampField("pay", 2e7), M.clampField("pay", 12.5), M.clampField("taxPct", 75), M.clampField("taxPct", 60), M.clampField("hoursOv", 5000), M.clampField("miles", 100001), M.clampField("mpg", 5000)]')
        eq('clampField table', lim, [0, 1e7, 12.5, 60, 60, 1000, 100000, 1000])
        eq('limits cover every numeric field', sorted(jsm('Object.keys(M.LIMITS)')),
           sorted('pay tip miles minutes wait retMiles retMin gasPrice mpg kwhPrice mikwh maint depr carOther cpm goalHour goalMile taxPct hoursOv milesOv'.split()))

    # ---- showing numbers
    if on('math') and math_ok:
      with section('math: showing numbers'):
        eq('money table', jsm('[0, 1234.5, -3.456, -0.004, 0.005, 0.004, 1e6, 12345678.9, NaN, Infinity, -0.005, 999.995, 0.1 + 0.2].map(M.money)'),
           ['$0.00', '$1,234.50', '-$3.46', '$0.00', '$0.01', '$0.00', '$1,000,000.00', '$12,345,678.90', '$0.00', '$0.00', '-$0.01', '$1,000.00', '$0.30'])
        eq('money0 table', jsm('[0, 1234.56, 999.5, -1234.5, NaN, 1e7].map(M.money0)'), ['$0', '$1,235', '$1,000', '-$1,235', '$0', '$10,000,000'])
        eq('moneyBig table', jsm('[0, 999999.99, 1000000, 1234567, -1234567, 1e7, 12345678.9, 1e9, 1e12, -2500000, 5.5].map(M.moneyBig)'),
           ['$0.00', '$999,999.99', '$1M', '$1.2M', '-$1.2M', '$10M', '$12.3M', '$1B', '$1T', '-$2.5M', '$5.50'])
        eq('neg table', jsm('[2.087, -2.087, 0, 0.004, 1234.5, NaN].map(M.neg)'), ['-$2.09', '-$2.09', '$0.00', '$0.00', '-$1,234.50', '$0.00'])
        eq('cents table', jsm('[0.3671, 0.335, 0.76, 0.725, 0, 1.5, 0.04].map(M.cents)'), ['36.7', '33.5', '76', '72.5', '0', '150', '4'])
        eq('plural table', jsm('[M.plural(1, "offer", "offers"), M.plural(0, "offer", "offers"), M.plural(2, "offer", "offers"), M.plural(1234, "mile", "miles")]'),
           ['1 offer', '0 offers', '2 offers', '1,234 miles'])
        eq('fmtNum table', jsm('[M.fmtNum(1234.5678, 2), M.fmtNum(1234.5, 2, 2), M.fmtNum(NaN), M.fmtNum(0.5, 0), M.fmtNum(1e6), M.fmtNum(-3.456, 2), M.fmtNum(2, 3, 2)]'),
           ['1,234.57', '1,234.50', '0', '1', '1,000,000', '-3.46', '2.00'])
        eq('pad2', jsm('[M.pad2(0), M.pad2(7), M.pad2(10), M.pad2(31)]'), ['00', '07', '10', '31'])
        eq('r6', jsm('[M.r6(0.12345678), M.r6(1.0000004), M.r6(-0.0000004), M.r6(12.5)]'), [0.123457, 1, 0, 12.5])
        eq('ceilCents table', jsm('[M.ceilCents(2.5), M.ceilCents(2.501), M.ceilCents(2.5 + 1e-15), M.ceilCents(25.000000000000004), M.ceilCents(0), M.ceilCents(0.001), M.ceilCents(0.1 + 0.2)]'),
           [2.5, 2.51, 2.5, 25, 0, 0.01, 0.3])
        pct = jsm('[NaN, Infinity, 0, -1, 0.5, 0.8, 0.99, 0.9999, 1, 1 - 1e-12, 1.2345, 9.999, 10, 1e9].map(M.pctOf)')
        eq('pctOf table', pct, ['', '', '0%', '0%', '50%', '80%', '99%', '99%', '100%', '100%', '123%', '999%', 'over 999%', 'over 999%'])
        # hours and minutes: every whole minute, plus awkward in-between values, against the reference
        mins = list(range(0, 400)) + [1439, 1440, 6000, 59999, 60000, 100000] + [rnd_m for rnd_m in range(3000, 99000, 4111)]
        hrs = [m / 60 for m in mins]
        got = jsm('a.map(M.hm)', hrs)
        bad = ['%r -> %r want %r' % (h, g, hm_text(h)) for h, g in zip(hrs, got) if g != hm_text(h)]
        batch('hm matches the reference for every whole minute', bad, len(hrs))
        eq('hm table', jsm('[0, 0.5, 1, 1.5, 1000, NaN, 0.0001, 0.99999, 2 + 29.6 / 60].map(M.hm)'), ['0 h', '30 min', '1 h', '1 h 30 min', '1,000 h', '0 h', '0 h', '1 h', '2 h 30 min'])
        eq('format table has no dash look-alikes', [c for c in DASHES if c in ''.join(jsm('[M.money(-5), M.neg(5), M.moneyBig(-5e6), M.hm(2.5), M.pctOf(2)]'))], [])

    # ---- the car
    if on('math') and math_ok:
      with section('math: the car'):
        d = dict(CAR0)
        r = jsm('(() => { const r = M.carInfo(a); return [r.fuel, r.sum, r.cpm, r.known, r.fuelMissing]; })()', d)
        eq('default gas car', [round(r[0], 9), round(r[1], 9), round(r[2], 9), r[3], r[4]], [0.125, 0.335, 0.335, False, False])
        e = dict(d, fuel='electric')
        r = jsm('(() => { const r = M.carInfo(a); return [r.fuel, r.sum, r.cpm]; })()', e)
        eq('default electric car', [round(x, 9) for x in r], [0.053125, 0.263125, 0.263125])
        k = dict(d, know=True, cpm=0.5)
        r = jsm('(() => { const r = M.carInfo(a); return [r.sum, r.cpm, r.known, r.fuelMissing]; })()', k)
        eq('own number replaces the sum', [round(r[0], 9), r[1], r[2], r[3]], [0.335, 0.5, True, False])
        eq('own number of zero is a zero cost', jsm('M.carInfo(a).cpm', dict(d, know=True, cpm=0)), 0)
        eq('no mpg means missing fuel and zero fuel cost', jsm('(() => { const r = M.carInfo(a); return [r.fuel, r.sum, r.fuelMissing]; })()', dict(d, mpg=0)), [0, 0.21, True])
        eq('no gas price means missing fuel', jsm('(() => { const r = M.carInfo(a); return [r.fuel, r.fuelMissing]; })()', dict(d, gasPrice=0)), [0, True])
        eq('no kWh price means missing fuel', jsm('M.carInfo(a).fuelMissing', dict(d, fuel='electric', kwhPrice=0)), True)
        eq('no miles per kWh means missing fuel', jsm('M.carInfo(a).fuelMissing', dict(d, fuel='electric', mikwh=0)), True)
        eq('own number hides the fuel warning', jsm('M.carInfo(a).fuelMissing', dict(d, mpg=0, know=True, cpm=0.4)), False)
        eq('other cost is added', round(jsm('M.carInfo(a).cpm', dict(d, carOther=0.05)), 9), 0.385)
        rnd = random.Random(7)
        cars = [rand_car(rnd) for _ in range(500)]
        got = jsm('a.map(c => { const r = M.carInfo(c); return [r.fuel, r.sum, r.cpm, r.known, r.fuelMissing]; })', cars)
        bad = []
        for c, g in zip(cars, got):
            w = ref_car(c)
            if not (tight(g[0], w['fuel']) and tight(g[1], w['sum']) and tight(g[2], w['cpm']) and g[3] == bool(c['know']) and g[4] == w['fuelMissing']):
                bad.append('%r -> %r want %r' % (c, g, (float(w['fuel']), float(w['sum']), float(w['cpm']), w['fuelMissing'])))
        batch('carInfo matches the reference on random cars (gas, electric, own number, missing fields)', bad, len(cars))

    # ---- one offer
    def offer_diffs(o, cpm, g, strict_cents=True):
        w = ref_offer(o, F(cpm))
        bad = []

        def num(name, got_v, want_v):
            if not tight(got_v, want_v):
                bad.append('%s got %r want %s' % (name, got_v, None if want_v is None else float(want_v)))

        def exact(name, got_v, want_v):
            if got_v != want_v:
                bad.append('%s got %r want %r' % (name, got_v, want_v))
        num('gross', g['gross'], w['gross'])
        num('miles', g['miles'], w['miles'])
        num('minutes', g['minutes'], w['minutes'])
        num('hours', g['hours'], w['hours'])
        num('carCost', g['carCost'], w['carCost'])
        num('net', g['net'], w['net'])
        num('netPerHour', g['netPerHour'], w['nph'])
        num('grossPerMile', g['grossPerMile'], w['gpm'])
        num('netPerMile', g['netPerMile'], w['npm'])
        num('setAside', g['setAside'], w['setAside'])
        num('keep', g['keep'], w['keep'])
        num('hourRatio', g['hourRatio'], w['hourRatio'])
        num('mileRatio', g['mileRatio'], w['mileRatio'])
        num('needHour', g['needHour'], w['needHour'])
        num('needMile', g['needMile'], w['needMile'])
        exact('verdict', g['v'], w['v'])
        exact('hourZone', g['hourZone'], w['hourZone'])
        exact('mileZone', g['mileZone'], w['mileZone'])
        exact('loss', g['loss'], w['v'] == 'pass' and not (w['net'] > 0))
        exact('needHours', g['needHours'], w['needHours'])
        exact('needMiles', g['needMiles'], w['needMiles'])
        exact('havePay', g['havePay'], w['havePay'])
        exact('haveMiles', g['haveMiles'], w['haveMiles'])
        exact('haveHours', g['haveHours'], w['haveHours'])
        exact('minPayKnown', g['minPayKnown'], w['minPayKnown'])
        exact('binds', g['binds'], w['binds'])
        exact('goalHour', g['goalHour'], float(w['goalHour']) if w['goalHour'] is not None else 0)
        exact('goalMile', g['goalMile'], float(w['goalMile']) if w['goalMile'] is not None else 0)
        if w['minPay'] is None:
            if undef(g['minPay']) is not None:
                bad.append('minPay got %r want undefined' % g['minPay'])
        else:
            cap = float(w['minPay'])
            # to the cent, except where a double cannot hold the cents at all
            if not (abs(g['minPay'] - cap) < 0.00499 or abs(g['minPay'] - cap) <= 1e-9 * abs(cap)):
                bad.append('minPay got %r want %s' % (g['minPay'], cap))
            ex = max(x for x in (w['needHour'], w['needMile']) if x is not None)
            num('minPayExact', g['minPayExact'], ex)
        return bad

    OFFER_JS = 'a.map(x => M.calcOffer(x[0], x[1]))'

    def run_offers(cases):
        """cases: list of (offer dict, cpm float). Returns the page's results."""
        return jsm(OFFER_JS, [[o, c] for (o, c) in cases])

    def offers_vs_reference(label, cases):
        got = run_offers(cases)
        bad = []
        for (o, c), g in zip(cases, got):
            d = offer_diffs(o, c, g)
            if d:
                bad.append('%r cpm %r: %s' % (o, c, '; '.join(d[:3])))
        batch(label, bad, len(cases))
        return got

    if on('math') and math_ok:
      with section('math: random offers against the reference'):
        rnd = random.Random(20261002)
        cases = []
        for _ in range(700):
            o = rand_offer(rnd)
            cars_ = rand_car(rnd)
            cases.append((o, float(ref_car(cars_)['cpm'])))
        got = offers_vs_reference('700 random offers match the reference (every number, every verdict, minimum pay)', cases)
        counts = {}
        for g in got:
            counts[g['v']] = counts.get(g['v'], 0) + 1
        eq('the random offers reach every verdict', sorted(counts), ['borderline', 'empty', 'need', 'nogoals', 'pass', 'take'])
        eq('every verdict is common enough to mean something', [k for k, v in counts.items() if v < 15], [])
        eq('some random offers lose money', sum(1 for g in got if g['loss']) > 20, True)
        eq('some random offers have both goals binding differently', len(set(g['binds'] for g in got if g['binds'])) >= 3, True)
        huge = []
        for _ in range(150):
            o = rand_offer(rnd, huge=True)
            huge.append((o, float(ref_car(rand_car(rnd))['cpm'])))
        offers_vs_reference('150 huge or tiny offers match the reference', huge)
        no_car = [(rand_offer(rnd), 0.0) for _ in range(150)]
        offers_vs_reference('150 offers with a zero car cost match the reference', no_car)
        gold = [(rand_offer(rnd), 0.335) for _ in range(150)]
        for o, _c in gold:
            o['goalHour'] = 0
        offers_vs_reference('150 offers with only a mile goal match the reference', gold)
        gold = [(rand_offer(rnd), 0.335) for _ in range(150)]
        for o, _c in gold:
            o['goalMile'] = 0
        offers_vs_reference('150 offers with only an hour goal match the reference', gold)
        none = [(rand_offer(rnd), 0.335) for _ in range(50)]
        for o, _c in none:
            o['goalMile'] = 0
            o['goalHour'] = 0
        got = offers_vs_reference('50 offers with no goals match the reference', none)
        eq('no goals gives nogoals or empty only', sorted(set(g['v'] for g in got)), ['empty', 'nogoals'])

    # ---- verdict boundaries, built to land exactly on 100% and 80%
    if on('math') and math_ok:
      with section('math: verdict boundaries'):
        rnd = random.Random(80100)
        built_cases, tries = [], 0
        while len(built_cases) < 240 and tries < 400000:
            tries += 1
            gh = rnd.choice([0, 15, 18, 20, 25, 30, 12.5])
            gm = rnd.choice([0, 1, 1.25, 1.5, 1.75, 2, 2.5])
            if gh == 0 and gm == 0:
                continue
            cpm = rnd.choice([0.5, 0.25, 0.4, 0.3, 0.2, 0.1])
            miles = rnd.choice([1, 2, 2.5, 3, 4, 5, 6, 8, 10, 12.5, 15, 20])
            ret = rnd.choice([0, 0, 1, 2, 0.5])
            minutes = rnd.choice([6, 12, 15, 20, 24, 30, 45, 60, 75, 90])
            f = rnd.choice([Fraction(1), Fraction(4, 5)])
            which = rnd.choice(['hour', 'mile'])
            hours_ = Fraction(minutes, 60)
            tm = F(miles) + F(ret)
            car = tm * F(cpm)
            if which == 'hour' and gh:
                gross = F(gh) * f * hours_ + car
            elif which == 'mile' and gm:
                gross = F(gm) * f * tm
            else:
                continue
            if gross <= 0 or (gross * 100).denominator != 1:
                continue
            tip = rnd.choice([0, 0, 1, 2])
            if gross - tip <= 0:
                tip = 0
            built_cases.append(dict(goalHour=gh, goalMile=gm, cpm=cpm, miles=miles, ret=ret, minutes=minutes, f=f, which=which, gross=gross, tip=tip))
        eq('enough exact boundary cases were built', len(built_cases) >= 200, True)
        cases, labels = [], []
        for b in built_cases:
            for delta in (Fraction(0), Fraction(-1, 100), Fraction(1, 100)):
                g_ = b['gross'] + delta
                if g_ <= 0:
                    continue
                tip = b['tip'] if g_ - b['tip'] > 0 else 0
                o = dict(OFFER0, pay=float(g_ - tip), tip=float(tip), miles=float(b['miles']), retMiles=float(b['ret']), minutes=float(b['minutes']), wait=0, retMin=0,
                         goalHour=float(b['goalHour']), goalMile=float(b['goalMile']), taxPct=20)
                cases.append((o, float(b['cpm'])))
                labels.append((b, delta))
        got = offers_vs_reference('exact boundary cases and one cent either side match the reference', cases)
        # the cases really sit on the boundary: the exact one meets the goal it was built for, the one below does not
        sit_bad, sat, below = [], 0, 0
        for (b, delta), (o, c), g in zip(labels, cases, got):
            zone = g['hourZone'] if b['which'] == 'hour' else g['mileZone']
            if delta == 0:
                want_zone = 'take' if b['f'] == 1 else 'maybe'
                if zone != want_zone:
                    sit_bad.append('%r exact: zone %r want %r' % (o, zone, want_zone))
                else:
                    sat += 1
            elif delta < 0:
                want_zone = 'maybe' if b['f'] == 1 else 'pass'
                if zone != want_zone:
                    sit_bad.append('%r minus a cent: zone %r want %r' % (o, zone, want_zone))
                else:
                    below += 1
        batch('exact boundary cases: exactly on the line counts as met, one cent below does not', sit_bad, sat + below)
        eq('both sides of the line were tested', sat > 100 and below > 100, True)
        # hand-checked boundaries (worked out on paper, not by the reference)
        k = lambda **kw: dict(OFFER0, tip=0, wait=0, retMiles=0, retMin=0, taxPct=20, **kw)
        hand = [
            # (offer, cpm, verdict, hourZone, mileZone)
            (k(pay=6.00, miles=4, minutes=10, goalHour=0, goalMile=1.5), 0.335, 'take', '', 'take'),
            (k(pay=5.99, miles=4, minutes=10, goalHour=0, goalMile=1.5), 0.335, 'borderline', '', 'maybe'),
            (k(pay=4.80, miles=4, minutes=10, goalHour=0, goalMile=1.5), 0.335, 'borderline', '', 'maybe'),
            (k(pay=4.79, miles=4, minutes=10, goalHour=0, goalMile=1.5), 0.335, 'pass', '', 'pass'),
            (k(pay=25.00, miles=10, minutes=60, goalHour=20, goalMile=0), 0.5, 'take', 'take', ''),
            (k(pay=24.99, miles=10, minutes=60, goalHour=20, goalMile=0), 0.5, 'borderline', 'maybe', ''),
            (k(pay=21.00, miles=10, minutes=60, goalHour=20, goalMile=0), 0.5, 'borderline', 'maybe', ''),
            (k(pay=20.99, miles=10, minutes=60, goalHour=20, goalMile=0), 0.5, 'pass', 'pass', ''),
            (k(pay=25.00, miles=10, minutes=60, goalHour=20, goalMile=1.5), 0.5, 'take', 'take', 'take'),
            (k(pay=24.99, miles=10, minutes=60, goalHour=20, goalMile=1.5), 0.5, 'borderline', 'maybe', 'take'),
            (k(pay=30.00, miles=20, minutes=30, goalHour=20, goalMile=1.5), 0.5, 'take', 'take', 'take'),
            (k(pay=29.99, miles=20, minutes=30, goalHour=20, goalMile=1.5), 0.5, 'borderline', 'take', 'maybe'),
            (k(pay=5.01, miles=10, minutes=30, goalHour=0, goalMile=0.1), 0.5, 'take', '', 'take'),
            (k(pay=5.00, miles=10, minutes=30, goalHour=0, goalMile=0.1), 0.5, 'pass', '', 'take'),
            (k(pay=4.00, miles=10, minutes=30, goalHour=20, goalMile=1.5), 0.5, 'pass', 'pass', 'pass'),
            (k(pay=0, miles=10, minutes=30, goalHour=20, goalMile=1.5), 0.5, 'empty', 'pass', 'pass'),
            (k(pay=9, miles=10, minutes=30, goalHour=0, goalMile=0), 0.5, 'nogoals', '', ''),
            (k(pay=9, miles=10, minutes=0, goalHour=20, goalMile=0), 0.5, 'need', '', ''),
            (k(pay=9, miles=0, minutes=30, goalHour=0, goalMile=1.5), 0.5, 'need', '', ''),
            (k(pay=9, miles=0, minutes=0, goalHour=20, goalMile=1.5), 0.5, 'need', '', ''),
            (k(pay=10, miles=0, minutes=30, goalHour=20, goalMile=0), 0.0, 'take', 'take', ''),
            (k(pay=9, miles=0, minutes=30, goalHour=20, goalMile=0), 0.0, 'borderline', 'maybe', ''),
        ]
        got = run_offers([(o, c) for (o, c, *_x) in hand])
        for (o, c, v, hz, mz), g in zip(hand, got):
            eq('hand boundary pay %.2f miles %s min %s goals %s/%s: verdict' % (o['pay'], o['miles'], o['minutes'], o['goalHour'], o['goalMile']), g['v'], v)
            if v not in ('empty', 'need', 'nogoals'):
                eq('hand boundary pay %.2f miles %s min %s goals %s/%s: zones' % (o['pay'], o['miles'], o['minutes'], o['goalHour'], o['goalMile']), (g['hourZone'], g['mileZone']), (hz, mz))
        # the nine-tenths of a goal that passes: both goals have to be at 80%, not just one
        o = k(pay=13.00, miles=10, minutes=60, goalHour=20, goalMile=1.5)
        g = run_offers([(o, 0.5)])[0]
        eq('mile goal at 87% but hour goal at 40% is a pass, not borderline', (g['v'], g['hourZone'], g['mileZone']), ('pass', 'pass', 'maybe'))
        # a loss is a pass whatever the goals say, and says so
        o = k(pay=3.00, miles=10, minutes=60, goalHour=0, goalMile=0.1)
        g = run_offers([(o, 0.5)])[0]
        eq('pays less than the car costs: pass and loss', (g['v'], g['loss'], round(g['net'], 9)), ('pass', True, -2.0))
        o = k(pay=5.00, miles=10, minutes=60, goalHour=0, goalMile=0.1)
        g = run_offers([(o, 0.5)])[0]
        eq('pays exactly the car cost: pass and loss', (g['v'], g['loss']), ('pass', True))
        eq('a loss shows no tax set-aside', (undef(g['setAside']), undef(g['keep'])), (None, None))

    # ---- minimum pay
    if on('math') and math_ok:
      with section('math: minimum pay'):
        rnd = random.Random(515)
        cases = []
        while len(cases) < 500:
            o = rand_offer(rnd)
            o['tip'] = 0
            if (o['goalHour'] == 0 and o['goalMile'] == 0) or o['miles'] + o['retMiles'] == 0 or o['minutes'] + o['wait'] + o['retMin'] == 0:
                continue
            cases.append((o, float(ref_car(rand_car(rnd))['cpm'])))
        base = run_offers(cases)
        at, below_, again = [], [], []
        for (o, c), g in zip(cases, base):
            if not g['minPayKnown']:
                continue
            at.append((dict(o, pay=g['minPay']), c))
            below_.append((dict(o, pay=round(g['minPay'] - 0.01, 2)), c))
        res_at, res_below = run_offers(at), run_offers(below_)
        bad = ['%r -> %s' % (o, g['v']) for (o, c), g in zip(at, res_at) if g['v'] != 'take']
        batch('paying the minimum pay is a Take it, whichever goal sets it', bad, len(at))
        bad = ['%r -> %s' % (o, g['v']) for (o, c), g in zip(below_, res_below) if g['v'] == 'take']
        batch('paying one cent less than the minimum pay is never a Take it', bad, len(below_))
        eq('both properties were checked on many offers', len(at) > 300, True)
        # the goal named as binding really is the one: drop the other goal and the minimum stays
        bad, n = [], 0
        for (o, c), g in zip(cases, base):
            if g['binds'] == 'hour' and o['goalMile'] > 0:
                g2 = run_offers([(dict(o, goalMile=0), c)])[0]
                n += 1
                if abs(g2['minPay'] - g['minPay']) > 1e-9:
                    bad.append('%r hour: %r vs %r' % (o, g['minPay'], g2['minPay']))
            if g['binds'] == 'mile' and o['goalHour'] > 0:
                g2 = run_offers([(dict(o, goalHour=0), c)])[0]
                n += 1
                if abs(g2['minPay'] - g['minPay']) > 1e-9:
                    bad.append('%r mile: %r vs %r' % (o, g['minPay'], g2['minPay']))
        batch('removing the other goal leaves the minimum pay alone', bad, n)
        eq('hour and mile were each binding often enough', n > 100, True)
        # hand-worked: 10 mi + 60 min at 50 cents a mile, $20 an hour, $1.50 a mile
        k = lambda **kw: dict(OFFER0, pay=0, tip=0, wait=0, retMiles=0, retMin=0, taxPct=20, **kw)
        cases = [
            (k(miles=10, minutes=60, goalHour=20, goalMile=1.5), 0.5, 25.00, 'hour'),
            (k(miles=20, minutes=30, goalHour=20, goalMile=1.5), 0.5, 30.00, 'mile'),
            (k(miles=10, minutes=60, goalHour=20, goalMile=2.5), 0.5, 25.00, 'both'),
            (k(miles=10, minutes=30, goalHour=0, goalMile=0.1), 0.5, 5.01, 'cost'),
            (k(miles=10, minutes=30, goalHour=1, goalMile=0), 0.5, 5.50, 'hour'),
            (k(miles=10, minutes=30, goalHour=0.01, goalMile=0), 0.5, 5.01, 'hour'),
            (k(miles=3, minutes=7, goalHour=20, goalMile=0), 0.335, 3.34, 'hour'),
            (k(miles=1, minutes=1, goalHour=20, goalMile=0), 0.0, 0.34, 'hour'),
            (k(miles=0, minutes=60, goalHour=20, goalMile=0), 0.5, 20.00, 'hour'),
            (k(miles=10, minutes=0, goalHour=0, goalMile=1.5), 0.5, 15.00, 'mile'),
        ]
        got = run_offers([(o, c) for (o, c, _p, _b) in cases])
        for (o, c, pay, binds), g in zip(cases, got):
            eq('minimum pay %s mi %s min goals %s/%s cpm %s' % (o['miles'], o['minutes'], o['goalHour'], o['goalMile'], c), (round(g['minPay'], 6), g['binds']), (pay, binds))
        o = k(miles=10, minutes=60, goalHour=0, goalMile=0)
        g = run_offers([(o, 0.5)])[0]
        eq('no goals gives no minimum pay', (g['minPayKnown'], undef(g['minPay']), g['binds']), (False, None, ''))
        o = k(miles=0, minutes=60, goalHour=20, goalMile=1.5)
        g = run_offers([(o, 0.5)])[0]
        eq('a mile goal with no miles gives no minimum pay', (g['minPayKnown'], undef(g['minPay'])), (False, None))
        # 3 mi + 7 min at 33.5 cents: 20 * 7/60 + 3 * .335 = 2.3333 + 1.005 = 3.3383, up to 3.34
        eq('minimum pay rounds up, never down', jsm('M.calcOffer(a, 0.335).minPay', dict(k(miles=3, minutes=7, goalHour=20, goalMile=0))), 3.34)
        eq('a total that lands exactly on a cent stays there', jsm('M.calcOffer(a, 0.5).minPay', dict(k(miles=10, minutes=60, goalHour=20, goalMile=0))), 25)

    # ---- a shift
    def shift_cases(rnd, n):
        out = []
        for _ in range(n):
            ents = []
            for _j in range(rnd.choice([0, 1, 1, 2, 3, 5, 8, 12])):
                ents.append(dict(pay=round(rnd.uniform(0.5, 40), 2), miles=round(rnd.uniform(0.1, 20), 1), min=rnd.randint(1, 90),
                                 ret=rnd.choice([0, 0, round(rnd.uniform(0.1, 5), 1)]), app=rnd.choice(['', 'DoorDash', 'Uber Eats', 'Lyft']), note=''))
            hov = rnd.choice([0, 0, round(rnd.uniform(0.5, 12), 2)])
            mov = rnd.choice([0, 0, round(rnd.uniform(1, 300), 1)])
            cpm = float(ref_car(rand_car(rnd))['cpm'])
            tax = rnd.choice([0, 15, 20, 25, round(rnd.uniform(0, 60), 1)])
            rate = rnd.choice([0.725, 0.76])
            out.append((ents, hov, mov, cpm, tax, rate))
        return out

    if on('math') and math_ok:
      with section('math: shift totals'):
        rnd = random.Random(31)
        cases = shift_cases(rnd, 500)
        got = jsm('a.map(x => M.calcShift(x[0], x[1], x[2], x[3], x[4], x[5]))', [list(c) for c in cases])
        bad = []
        for (ents, hov, mov, cpm, tax, rate), g in zip(cases, got):
            w = ref_shift(ents, hov, mov, F(cpm), tax, rate)
            d = []
            for name, key in (('gross', 'gross'), ('hours', 'hours'), ('miles', 'miles'), ('carCost', 'carCost'), ('net', 'net'),
                              ('netPerHour', 'nph'), ('netPerMile', 'npm'), ('grossPerMile', 'gpm'), ('setAside', 'setAside'),
                              ('takeHome', 'takeHome'), ('deduction', 'deduction'), ('hoursAuto', 'hoursAuto'), ('milesAuto', 'milesAuto')):
                if not tight(g[name], w[key]):
                    d.append('%s got %r want %s' % (name, g[name], None if w[key] is None else float(w[key])))
            if g['n'] != w['n']:
                d.append('n')
            if g['usedHours'] != (hov > 0) or g['usedMiles'] != (mov > 0):
                d.append('used flags')
            if g['haveHours'] != (w['hours'] > 0) or g['haveMiles'] != (w['miles'] > 0):
                d.append('have flags')
            if d:
                bad.append('%d entries, hours %r, miles %r, cpm %r, tax %r: %s' % (len(ents), hov, mov, cpm, tax, '; '.join(d[:3])))
        batch('500 random shifts match the reference (totals, overrides, set-aside, deduction)', bad, len(cases))
        # hand-worked shift
        ents = [dict(pay=8, miles=3, min=20, ret=1, app='', note=''), dict(pay=12, miles=5, min=30, ret=0, app='', note='')]
        g = jsm('M.calcShift(a, 0, 0, 0.335, 20, 0.76)', ents)
        eq('hand shift: gross, hours, miles', (g['gross'], g['hours'], g['miles']), (20, 50 / 60, 9))
        near('hand shift: car cost', g['carCost'], 9 * 0.335, 1e-9)
        near('hand shift: net', g['net'], 20 - 9 * 0.335, 1e-9)
        near('hand shift: net per hour', g['netPerHour'], (20 - 9 * 0.335) / (50 / 60), 1e-9)
        near('hand shift: set aside', g['setAside'], (20 - 9 * 0.335) * 0.2, 1e-9)
        near('hand shift: take home', g['takeHome'], (20 - 9 * 0.335) * 0.8, 1e-9)
        near('hand shift: deduction', g['deduction'], 9 * 0.76, 1e-9)
        g = jsm('M.calcShift(a, 4, 30, 0.335, 20, 0.76)', ents)
        eq('hand shift with overrides', (g['hours'], g['miles'], g['usedHours'], g['usedMiles'], g['hoursAuto'], g['milesAuto']), (4, 30, True, True, 50 / 60, 9))
        g = jsm('M.calcShift(a, 0, 0, 0.335, 20, 0.76)', [])
        eq('empty shift', (g['n'], g['gross'], g['hours'], g['miles'], g['net'], undef(g['netPerHour']), undef(g['netPerMile']), g['setAside'], g['haveHours']), (0, 0, 0, 0, 0, None, None, 0, False))
        g = jsm('M.calcShift(a, 0, 0, 0.5, 20, 0.76)', [dict(pay=1, miles=10, min=30, ret=0, app='', note='')])
        eq('a losing shift has no set-aside and negative take home', (round(g['net'], 9), g['setAside'], round(g['takeHome'], 9)), (-4.0, 0, -4.0))

    # ---- by app
    def ref_byapp(entries):
        order, m = [], {}
        for e in entries:
            k_ = e.get('app') or ''
            if k_ not in m:
                m[k_] = dict(app=k_, n=0, gross=Fraction(0), mins=Fraction(0))
                order.append(k_)
            m[k_]['n'] += 1
            m[k_]['gross'] += F(e['pay'])
            m[k_]['mins'] += F(e['min'])
        rows = []
        for i, k_ in enumerate(order):
            g_ = m[k_]
            rows.append(dict(app=k_, n=g_['n'], gross=g_['gross'], mins=g_['mins'], perHour=(g_['gross'] / (g_['mins'] / 60) if g_['mins'] > 0 else None), first=i))
        rows.sort(key=lambda r_: (r_['app'] == '', -r_['gross'], r_['first']))
        return rows, len([k_ for k_ in order if k_ != ''])

    if on('math') and math_ok:
      with section('math: by app'):
        rnd = random.Random(99)
        apps_ = ['', 'DoorDash', 'Uber Eats', 'Grubhub', 'Lyft', 'Other']
        cases = []
        for _ in range(300):
            ents = [dict(pay=round(rnd.uniform(0, 30), 2), min=rnd.choice([0, 5, 10, 20, 45]), miles=1, ret=0, app=rnd.choice(apps_), note='')
                    for _j in range(rnd.randint(0, 9))]
            cases.append(ents)
        got = jsm('a.map(e => { const r = M.byApp(e); return {labelled: r.labelled, rows: r.rows.map(x => [x.app, x.n, x.gross, x.mins, x.perHour, x.first])}; })', cases)
        bad = []
        for ents, g in zip(cases, got):
            rows, lab = ref_byapp(ents)
            ok = g['labelled'] == lab and len(g['rows']) == len(rows)
            if ok:
                for (app, n, gross, mins, ph, first), w in zip(g['rows'], rows):
                    if not (app == w['app'] and n == w['n'] and tight(gross, w['gross']) and tight(mins, w['mins']) and tight(ph, w['perHour'])):
                        ok = False
            if not ok:
                bad.append('%r -> %r want %r' % (ents, g, [(w['app'], w['n']) for w in rows]))
        batch('300 random logs: by-app rows, order, per-hour and labelled count match the reference', bad, len(cases))
        e1 = [dict(pay=5, min=10, app='Lyft'), dict(pay=9, min=10, app='DoorDash'), dict(pay=9, min=20, app='Uber Eats'), dict(pay=3, min=5, app=''), dict(pay=1, min=5, app='Lyft')]
        r = jsm('(() => { const r = M.byApp(a); return [r.labelled, r.rows.map(x => x.app + ":" + x.n + ":" + x.gross)]; })()', e1)
        eq('ties on gross keep the order they first appeared in, unlabelled goes last', r, [3, ['DoorDash:1:9', 'Uber Eats:1:9', 'Lyft:2:6', ':1:3']])
        r = jsm('M.byApp(a).rows.map(x => [x.app, x.perHour])', [dict(pay=9, min=0, app='Lyft')])
        eq('no minutes gives no per-hour figure', [[x[0], undef(x[1])] for x in r], [['Lyft', None]])
        eq('one app is not a comparison', jsm('M.byApp(a).labelled', [dict(pay=9, min=10, app='Lyft'), dict(pay=9, min=10, app='Lyft'), dict(pay=1, min=1, app='')]), 1)

    # ---- dates and the week
    def ref_date_ok(s):
        import datetime
        try:
            y, m, d = [int(x) for x in s.split('-')]
            if not (2000 <= y <= 2100):
                return False
            datetime.date(y, m, d)
            return len(s) == 10
        except Exception:
            return False

    if on('math') and math_ok:
      with section('math: dates'):
        import datetime
        rnd = random.Random(5)
        ds = ['2000-01-01', '2100-12-31', '2026-10-02', '2028-02-29', '2024-02-29', '2000-02-29', '2026-12-31', '2027-01-01', '2026-06-30', '2026-07-01']
        for _ in range(500):
            ds.append(datetime.date.fromordinal(rnd.randint(datetime.date(2000, 1, 1).toordinal(), datetime.date(2100, 12, 31).toordinal())).isoformat())
        got = jsm('a.map(s => M.dayNum(s))', ds)
        base = day_num('2000-01-01')
        bad = ['%s got %r want %r' % (s, g, day_num(s) - base + got[0]) for s, g in zip(ds, got) if g - got[0] != day_num(s) - base]
        batch('dayNum differences match the calendar on 510 dates', bad, len(ds))
        rt = jsm('a.map(s => M.dateOfNum(M.dayNum(s)))', ds)
        eq('dateOfNum undoes dayNum', [s for s, r_ in zip(ds, rt) if s != r_], [])
        eq('consecutive days differ by one across a leap day, a month and a year', jsm('[M.dayNum("2028-03-01") - M.dayNum("2028-02-29"), M.dayNum("2028-02-29") - M.dayNum("2028-02-28"), M.dayNum("2027-03-01") - M.dayNum("2027-02-28"), M.dayNum("2027-01-01") - M.dayNum("2026-12-31"), M.dayNum("2026-11-01") - M.dayNum("2026-10-31")]'), [1, 1, 1, 1, 1])
        bad_dates = ['2026-02-30', '2027-02-29', '2026-13-01', '2026-00-10', '2026-04-31', '1999-12-31', '2101-01-01', '2026-1-1', '26-10-02', '2026/10/02', '', 'abc', None, '2026-10-02 ', ' 2026-10-02', '2026-10-2', '2026-10-02T00:00']
        got = [undef(g) for g in jsm('a.map(s => M.dayNum(s))', bad_dates)]
        eq('dayNum refuses dates that are not real', [s for s, g in zip(bad_dates, got) if g is not None], [])
        eq('dayNum of 1970-01-01 would be zero but is out of range', undef(jsm('M.dayNum("1970-01-01")')), None)
        eq('dateOfNum table', jsm('[M.dateOfNum(M.dayNum("2026-10-02") - 6), M.dateOfNum(M.dayNum("2026-03-01") - 1), M.dateOfNum(M.dayNum("2028-03-01") - 1)]'), ['2026-09-26', '2026-02-28', '2028-02-29'])
        lab = jsm('a.map(s => [M.dateLabel(s), M.dateLabel(s, true), M.dateShort(s)])', ['2026-10-02', '2026-07-04', '2028-02-29', '2026-12-31'])
        want = []
        for s in ['2026-10-02', '2026-07-04', '2028-02-29', '2026-12-31']:
            dd = datetime.date.fromisoformat(s)
            short = dd.strftime('%b ') + str(dd.day)
            want.append([dd.strftime('%a, ') + short, dd.strftime('%a, ') + short + ', ' + str(dd.year), short])
        eq('dateLabel and dateShort match the calendar', lab, want)
        eq('dateLabel passes through what it cannot read', jsm('[M.dateLabel("nope"), M.dateShort("nope")]'), ['nope', 'nope'])
        eq('localDate uses the local calendar day', jsm('[M.localDate(new Date(2026, 9, 2, 23, 59, 59)), M.localDate(new Date(2026, 9, 3, 0, 0, 0)), M.localDate(new Date(2026, 0, 1, 0, 0, 1)), M.localDate(new Date(2028, 1, 29, 12))]'),
           ['2026-10-02', '2026-10-03', '2026-01-01', '2028-02-29'])

      with section('math: irs rate'):
        eq('the rate list is newest first and dated', jsm('M.IRS_RATES.map(r => [r.from, r.rate])'), [['2026-07-01', 0.76], ['2026-01-01', 0.725]])
        eq('last year and as-of date', (jsm('M.IRS_LAST_YEAR'), jsm('M.IRS_AS_OF')), (2026, 'October 2, 2026'))
        days_ = [datetime.date.fromordinal(n).isoformat() for n in range(datetime.date(2025, 12, 1).toordinal(), datetime.date(2027, 2, 1).toordinal())]
        got = jsm('a.map(s => M.irsRateFor(s))', days_)
        bad = ['%s got %r want %r' % (s, g, float(ref_rate(s))) for s, g in zip(days_, got) if abs(g - float(ref_rate(s))) > 1e-12]
        batch('the rate for every day from December 2025 to January 2027 matches the table in the IRS notices', bad, len(days_))
        eq('boundary days', jsm('[M.irsRateFor("2026-06-30"), M.irsRateFor("2026-07-01"), M.irsRateFor("2026-12-31"), M.irsRateFor("2026-01-01")]'), [0.725, 0.76, 0.76, 0.725])
        eq('stale only once the calendar passes the last listed year', jsm('["2026-01-01", "2026-12-31", "2027-01-01", "2030-06-01"].map(M.irsStale)'), [False, False, True, True])

      with section('math: the week'):
        rnd = random.Random(1234)

        def rand_days(today_s, n):
            t0 = day_num(today_s)
            ds_ = []
            for _ in range(n):
                dn = t0 + rnd.randint(-12, 3)
                dt = datetime.date.fromordinal(dn).isoformat()
                ds_.append(dict(date=dt, orders=rnd.randint(0, 40), gross=round(rnd.uniform(0, 300), 2), miles=round(rnd.uniform(0, 250), 1),
                                hours=round(rnd.uniform(0, 12), 2), net=round(rnd.uniform(-20, 250), 2)))
            return ds_
        cases = []
        for today_s in ['2026-10-02', '2026-07-05', '2026-07-01', '2026-01-03', '2028-03-02', '2026-12-31', '2027-01-04']:
            for _ in range(60):
                cases.append((rand_days(today_s, rnd.randint(0, 14)), today_s, rnd.choice([0, 20, 25, 33.3])))
        got = jsm('a.map(x => { const w = M.weekOf(x[0], x[1], x[2]); return w; })', [list(c) for c in cases])
        bad = []
        for (dd, today_s, tax), g in zip(cases, got):
            w = ref_week(dd, today_s, tax)
            d = []
            for name, key in (('gross', 'gross'), ('miles', 'miles'), ('hours', 'hours'), ('net', 'net'), ('deduction', 'deduction'), ('carCost', 'carCost'),
                              ('netPerHour', 'nph'), ('netPerMile', 'npm'), ('setAside', 'setAside'), ('takeHome', 'takeHome')):
                if not tight(g[name], w[key]):
                    d.append('%s got %r want %s' % (name, g[name], None if w[key] is None else float(w[key])))
            if g['n'] != w['n'] or g['orders'] != w['orders']:
                d.append('n/orders %r/%r want %r/%r' % (g['n'], g['orders'], w['n'], w['orders']))
            t_ = day_num(today_s)
            if g['to'] != today_s or g['from'] != datetime.date.fromordinal(t_ - 6).isoformat():
                d.append('window %r %r' % (g['from'], g['to']))
            if d:
                bad.append('today %s, %d days: %s' % (today_s, len(dd), '; '.join(d[:3])))
        batch('420 random weeks match the reference (window, totals, deduction at each day\'s own rate)', bad, len(cases))
        # the window: today and six days before, nothing older, nothing in the future
        mk = lambda dt: dict(date=dt, orders=1, gross=10, miles=5, hours=1, net=7)
        week = [mk('2026-10-02'), mk('2026-09-26'), mk('2026-09-25'), mk('2026-10-03'), mk('2026-10-01')]
        g = jsm('M.weekOf(a, "2026-10-02", 20)', week)
        eq('window includes today and day minus six, leaves out day minus seven and tomorrow', (g['n'], g['from'], g['to']), (3, '2026-09-26', '2026-10-02'))
        g = jsm('M.weekOf(a, "2026-03-02", 20)', [mk('2026-02-24'), mk('2026-02-23'), mk('2026-03-02')])
        eq('window crosses a month end', (g['n'], g['from']), (2, '2026-02-24'))
        g = jsm('M.weekOf(a, "2028-03-04", 20)', [mk('2028-02-27'), mk('2028-02-26'), mk('2028-02-29')])
        eq('window crosses a leap day', (g['n'], g['from']), (2, '2028-02-27'))
        g = jsm('M.weekOf(a, "2027-01-03", 20)', [mk('2026-12-28'), mk('2026-12-27'), mk('2027-01-03')])
        eq('window crosses a year end', (g['n'], g['from']), (2, '2026-12-28'))
        g = jsm('M.weekOf(a, "2026-10-02", 20)', [])
        eq('empty week', (g['n'], g['gross'], g['net'], undef(g['netPerHour']), g['setAside']), (0, 0, 0, None, 0))
        g = jsm('M.weekOf(a, "2026-07-03", 25)', [mk('2026-06-30'), mk('2026-07-01')])
        near('deduction uses the rate for each day (5 mi at 72.5 cents, 5 mi at 76 cents)', g['deduction'], 5 * 0.725 + 5 * 0.76, 1e-9)
        g = jsm('M.weekOf(a, "2026-10-02", 20)', [dict(date='2026-10-02', orders=2, gross=10, miles=20, hours=2, net=-5)])
        eq('a losing week has no set-aside', (g['setAside'], g['takeHome'], g['net']), (0, -5, -5))

    # ---- the verdict text uses nothing the maths block cannot explain
    if on('math') and math_ok:
      with section('math: zoneOf and meets'):
        eq('meets table', jsm('[M.meets(20, 20, 1), M.meets(19.999999999, 20, 1), M.meets(19.99, 20, 1), M.meets(16, 20, 0.8), M.meets(15.99, 20, 0.8), M.meets(0.30000000000000004, 0.3, 1), M.meets(0.1 + 0.2, 0.3, 1)]'),
           [True, True, False, True, False, True, True])
        eq('zoneOf table', jsm('[M.zoneOf(20, 20), M.zoneOf(16, 20), M.zoneOf(15.99, 20), M.zoneOf(25, 20), M.zoneOf(0, 20), M.zoneOf(-5, 20)]'), ['take', 'maybe', 'pass', 'take', 'pass', 'pass'])
        eq('apps list', jsm('M.APPS'), ['DoorDash', 'Uber Eats', 'Grubhub', 'Instacart', 'Spark', 'Amazon Flex', 'Shipt', 'Uber', 'Lyft', 'Other'])

    mctx.close()

    # ============================================================ the page itself
    def plain(v):
        return format(Decimal(repr(float(v))), 'f')

    def fmt_num(x, maxd=2, mind=0):
        """What toLocaleString('en-US') shows: half away from zero on the shortest decimal, trailing zeros trimmed down to mind."""
        d = Decimal(repr(float(x)))
        q = d.copy_abs().quantize(Decimal(1).scaleb(-maxd), rounding=ROUND_HALF_UP)
        s = '{:,.{p}f}'.format(q, p=maxd)
        if '.' in s:
            whole, frac = s.split('.')
            frac = frac.rstrip('0').ljust(mind, '0')
            s = whole + ('.' + frac if frac else '')
        return ('-' if float(x) < 0 and q != 0 else '') + s

    def cpm_text(c):
        return '$' + fmt_num(c, 3, 2)

    def pct_text(ratio):
        p = math.floor(max(Fraction(0), ratio) * 100)
        return 'over 999%' if p >= 1000 else '%d%%' % p

    def parse_money_any(t):
        """'$1,234.56' is 1234.56, '-$3.40' is -3.4, '$1.2M' is 1.2e6. Anything else is None."""
        m = re.fullmatch(r'(-?)\$([0-9,]+(?:\.[0-9]+)?)([KMBT]?)', (t or '').strip())
        if not m:
            return None
        v = float(m.group(2).replace(',', '')) * {'': 1, 'K': 1e3, 'M': 1e6, 'B': 1e9, 'T': 1e12}[m.group(3)]
        return -v if m.group(1) else v

    def money_match(text, want, tol=0.0051):
        """The shown money agrees with the exact number: to the cent, or to the precision of the short form for millions and up."""
        got = parse_money_any(text)
        if want is None or got is None:
            return False
        w = float(want)
        if re.search(r'[KMBT]$', (text or '').strip()):
            return abs(got - w) <= 0.051 * abs(w) + 1
        return abs(got - w) <= tol

    SNAP_JS = '''() => {
        const $ = id => document.getElementById(id);
        const t = id => $(id).textContent.trim();
        const rows = id => [...$(id).querySelectorAll('.srow')].map(r => [r.querySelector('dt').textContent.trim(), r.querySelector('dd').textContent.trim()]);
        const tile = k => ({val: t('v' + k), goal: t('g' + k), pct: t('p' + k), z: $('rd' + k).getAttribute('data-z'), fill: $('f' + k).style.width});
        return {
            v: $('dash').getAttribute('data-v'), barV: $('bar').getAttribute('data-v'), word: t('vWord'), line: t('vLine'), barWord: t('bWord'),
            hour: tile('Hour'), mile: tile('Mile'),
            need: {hidden: $('needBox').hidden, val: t('needVal'), gap: t('needGap'), why: t('needWhy')},
            stub: rows('stub'), stubHidden: $('stub').hidden,
            bar: {hour: t('bAmtHour'), mile: t('bAmtMile')},
            logOff: $('logBtn').disabled, copyOff: $('copyBtn').disabled,
            alert: {hidden: $('offerAlert').hidden, text: t('offerAlert')},
            example: !$('exampleNote').hidden
        };
    }'''

    def snap(page):
        return page.evaluate(SNAP_JS)

    def shown(page, sel):
        """True when the element is not hidden by the page. Unlike is_visible this also works inside a closed details."""
        return page.evaluate("s => !document.querySelector(s).hidden", sel)

    SET_JS = '''(m) => {
        const fire = (el, t) => el.dispatchEvent(new Event(t, {bubbles: true}));
        document.querySelectorAll('#fuelChips button')[m.fuel === 'electric' ? 1 : 0].click();
        const k = document.getElementById('know');
        if (k.checked !== m.know) { k.checked = m.know; fire(k, 'change'); }
        for (const id in m.fields) { const el = document.getElementById(id); el.value = m.fields[id]; fire(el, 'input'); }
    }'''

    OFFER_IDS = ('pay', 'tip', 'miles', 'minutes', 'wait', 'retMiles', 'retMin', 'goalHour', 'goalMile', 'taxPct')
    CAR_IDS = ('gasPrice', 'mpg', 'kwhPrice', 'mikwh', 'maint', 'depr', 'carOther', 'cpm')

    def set_state(page, o, car):
        """Puts every offer, goal and car number into the page through its own inputs, the way typing would."""
        fields = {}
        for k in OFFER_IDS:
            fields[k] = '' if o[k] == 0 else plain(o[k])
        for k in CAR_IDS:
            fields[k] = '' if car[k] == 0 else plain(car[k])
        page.evaluate(SET_JS, {'fields': fields, 'fuel': car['fuel'], 'know': bool(car['know'])})

    WORDS = {'take': 'Take it', 'borderline': 'Borderline', 'pass': 'Pass', 'nogoals': 'No goals set', 'empty': 'Add an offer'}
    BAR_WORDS = {'take': 'Take it', 'borderline': 'Borderline', 'pass': 'Pass', 'nogoals': 'No goals', 'empty': 'Add pay'}

    def want_word(r):
        if r['v'] in WORDS:
            return WORDS[r['v']]
        return 'Add miles and minutes' if r['needHours'] and r['needMiles'] else ('Add the miles' if r['needMiles'] else 'Add the minutes')

    def want_bar_word(r):
        if r['v'] in BAR_WORDS:
            return BAR_WORDS[r['v']]
        return 'Add trip' if r['needHours'] and r['needMiles'] else ('Add miles' if r['needMiles'] else 'Add time')

    def bar_match(text, want):
        """The pinned bar shows cents under $1,000, whole dollars up to a million, and the short form above."""
        if want is None:
            return text == '-'
        w = float(want)
        if abs(w) >= 1e6:
            return money_match(text, w)
        return money_match(text, w, 0.0051 if abs(w) < 1000 else 0.5001)

    def verify_offer(page, o, car):
        """Reads everything the page shows for one offer and compares it with the reference. Returns the list of differences."""
        cpm = ref_car(car)['cpm']
        r = ref_offer(o, cpm)
        s = snap(page)
        bad = []

        def chk(name, got, want):
            if got != want:
                bad.append('%s: got %r want %r' % (name, got, want))
        chk('verdict', s['v'], r['v'])
        chk('bar verdict', s['barV'], r['v'])
        chk('verdict word', s['word'], want_word(r))
        chk('bar word', s['barWord'], want_bar_word(r))
        for k, key in (('hour', 'Hour'), ('mile', 'Mile')):
            have = r['haveHours'] if k == 'hour' else r['haveMiles']
            val = r['nph'] if k == 'hour' else r['gpm']
            goal = r['goalHour'] if k == 'hour' else r['goalMile']
            ratio = r['hourRatio'] if k == 'hour' else r['mileRatio']
            zone = r['hourZone'] if k == 'hour' else r['mileZone']
            show = r['havePay'] and have
            t = s[k]
            if show:
                if not money_match(t['val'], val):
                    bad.append('%s value: got %r want %s' % (k, t['val'], float(val)))
            else:
                chk(k + ' value', t['val'], '-')
            wz = zone if (show and goal is not None) else 'none'
            chk(k + ' zone', t['z'], wz)
            if goal is None:
                chk(k + ' goal text', t['goal'], 'No goal set')
            elif show is False and r['havePay'] and not have:
                chk(k + ' goal text', t['goal'], 'Add the minutes' if k == 'hour' else 'Add the miles')
            else:
                chk(k + ' goal text', t['goal'], 'Goal %s%s' % (usd(float(goal)), ' an hour' if k == 'hour' else ' a mile'))
            chk(k + ' percent', t['pct'], '' if wz == 'none' else pct_text(ratio) + ' of goal')
            wf = min(Fraction(5, 4), max(Fraction(0), ratio)) / Fraction(5, 4) * 100 if (wz != 'none' and ratio is not None) else Fraction(0)
            gf = float(t['fill'].rstrip('%')) if t['fill'] else -1
            if abs(gf - float(wf)) > 0.011:
                bad.append('%s meter: got %r want %.2f%%' % (k, t['fill'], float(wf)))
        # the pay-needed box
        chk('need box hidden', s['need']['hidden'], not r['minPayKnown'])
        if r['minPayKnown']:
            if not money_match(s['need']['val'], r['minPay']):
                bad.append('need value: got %r want %s' % (s['need']['val'], float(r['minPay'])))
            if r['havePay']:
                d = float(r['minPay'] - r['gross'])
                m1 = re.fullmatch(r'(\$[0-9,.]+(?:\.[0-9]+)?[KMBT]?) more than this offer pays\.', s['need']['gap'])
                m2 = re.fullmatch(r'This offer pays (\$[0-9,.]+(?:\.[0-9]+)?[KMBT]?) more than that\.', s['need']['gap'])
                if abs(d) < 0.005:
                    chk('need gap', s['need']['gap'], 'This offer pays exactly that.')
                elif d > 0:
                    if not (m1 and money_match(m1.group(1), d)):
                        bad.append('need gap: got %r want %.2f more' % (s['need']['gap'], d))
                else:
                    if not (m2 and money_match(m2.group(1), -d)):
                        bad.append('need gap: got %r want %.2f less' % (s['need']['gap'], -d))
            else:
                chk('need gap with no pay', s['need']['gap'], '')
            why = s['need']['why']
            b = r['binds']
            ok = ((b == 'hour' and why.startswith('Set by your ') and ' an hour goal: ' in why) or (b == 'mile' and why.startswith('Set by your ') and ' a mile goal: ' in why) or
                  (b == 'both' and why == 'Your two goals ask for the same pay.') or (b == 'cost' and why.startswith('Set by the car cost: the pay has to beat ')))
            if not ok:
                bad.append('need why (binds %s): got %r' % (b, why))
        # the receipt
        rows = []
        trip = []
        if r['haveMiles']:
            trip.append(fmt_num(r['miles'], 2) + ' mi')
        if r['haveHours']:
            trip.append(hm_text(r['hours']))
        extra = o['wait'] > 0 or o['retMiles'] > 0 or o['retMin'] > 0
        if trip:
            rows.append(('Trip, all in' if extra else 'Trip', ', '.join(trip), None))
        if r['havePay']:
            rows.append(('Pay plus tip' if o['tip'] > 0 else 'Pay', None, r['gross']))
            carv = float(r['carCost'])
            rows.append(('Car cost (%s mi at %s)' % (fmt_num(r['miles'], 2), cpm_text(float(cpm))), None, -carv if abs(carv) >= 0.005 else 0))
            rows.append(('Net after car cost', None, r['net']))
            if r['haveMiles']:
                rows.append(('Net per mile', None, r['npm']))
            if r['setAside'] is not None and o['taxPct'] > 0:
                rows.append(('Set aside for taxes (%s%%)' % fmt_num(o['taxPct'], 2), None, -r['setAside']))
                rows.append(('You keep', None, r['keep']))
        chk('receipt hidden', s['stubHidden'], len(rows) == 0)
        if len(s['stub']) != len(rows):
            bad.append('receipt rows: got %r want %d rows' % (s['stub'], len(rows)))
        else:
            for (lab, vv), (wl, wtext, wnum) in zip(s['stub'], rows):
                if lab != wl:
                    # a cost per mile that sits exactly between two roundings may read either way
                    ma = re.fullmatch(r'Car cost \((.+) mi at \$([0-9.]+)\)', lab)
                    mb = re.fullmatch(r'Car cost \((.+) mi at \$([0-9.]+)\)', wl)
                    if not (ma and mb and ma.group(1) == mb.group(1) and abs(float(ma.group(2)) - float(mb.group(2))) <= 0.00101):
                        bad.append('receipt label: got %r want %r' % (lab, wl))
                elif wtext is not None:
                    chk('receipt ' + wl, vv, wtext)
                elif not money_match(vv, wnum):
                    bad.append('receipt %s: got %r want %s' % (wl, vv, float(wnum)))
        # the pinned bar
        wh = r['nph'] if (r['havePay'] and r['haveHours']) else None
        wm = r['gpm'] if (r['havePay'] and r['haveMiles']) else None
        if not bar_match(s['bar']['hour'], wh):
            bad.append('bar hour: got %r want %r' % (s['bar']['hour'], None if wh is None else float(wh)))
        if not bar_match(s['bar']['mile'], wm):
            bad.append('bar mile: got %r want %r' % (s['bar']['mile'], None if wm is None else float(wm)))
        full = r['havePay'] and r['haveMiles'] and r['haveHours']
        chk('log button', s['logOff'], not full)
        chk('copy button', s['copyOff'], not full)
        warn = r['havePay'] and cpm <= 0
        chk('zero car cost alert shown', not s['alert']['hidden'], warn)
        return bad

    # ---- first paint, phone, light
    EX = dict(OFFER0, **GOALS0)
    ctx1, page = new_page(browser)
    if on('ui'):
      with section('first paint'):
          EX = dict(OFFER0, **GOALS0)
          eq('the example verifies against the reference', verify_offer(page, EX, CAR0), [])
          s = snap(page)
          eq('example verdict', (s['v'], s['word']), ('pass', 'Pass'))
          eq('example verdict line', s['line'], 'Net per hour and gross per mile are both short of your goals.')
          eq('example net per hour tile', (s['hour']['val'], s['hour']['goal'], s['hour']['pct'], s['hour']['z']), ('$8.88', 'Goal $20.00 an hour', '44% of goal', 'pass'))
          eq('example gross per mile tile', (s['mile']['val'], s['mile']['goal'], s['mile']['pct'], s['mile']['z']), ('$1.14', 'Goal $1.50 a mile', '76% of goal', 'pass'))
          eq('example need box', (s['need']['val'], s['need']['gap'], s['need']['why']),
             ('$12.25', '$5.75 more than this offer pays.', 'Set by your $20.00 an hour goal: $20.00 for 31 min, plus $1.91 for the car.'))
          eq('example receipt', s['stub'], [['Trip, all in', '5.7 mi, 31 min'], ['Pay', '$6.50'], ['Car cost (5.7 mi at $0.335)', '-$1.91'], ['Net after car cost', '$4.59'],
                                            ['Net per mile', '$0.81'], ['Set aside for taxes (20%)', '-$0.92'], ['You keep', '$3.67']])
          eq('example pinned bar', (s['bar']['hour'], s['bar']['mile'], s['barWord']), ('$8.88', '$1.14', 'Pass'))
          eq('example note shown', (s['example'], txt(page, '#exampleNote p')), (True, 'Example offer. Type over it.'))
          eq('example inputs', {i: page.input_value('#' + i) for i in OFFER_IDS + CAR_IDS},
             {'pay': '6.50', 'tip': '', 'miles': '4.2', 'minutes': '22', 'wait': '5', 'retMiles': '1.5', 'retMin': '4', 'goalHour': '20.00', 'goalMile': '1.50', 'taxPct': '20',
              'gasPrice': '3.50', 'mpg': '28', 'kwhPrice': '0.17', 'mikwh': '3.2', 'maint': '0.09', 'depr': '0.12', 'carOther': '', 'cpm': ''})
          eq('example chips', [pressed(page, g) for g in ('tipChips', 'waitChips', 'goalHourChips', 'goalMileChips', 'taxChips', 'fuelChips')],
             [['None'], ['5'], ['$20'], ['$1.50'], ['20%'], ['Gas']])
          eq('group hints', (txt(page, '#hintMore'), txt(page, '#hintGoals'), txt(page, '#hintCar')),
             ('wait 5 min, back 1.5 mi, 4 min', '$20.00/hr net, $1.50/mi gross, 20% set aside', '$0.335 a mile, gas'))
          eq('car reading', (txt(page, '#carBig'), txt(page, '#carParts')), ('$0.335 a mile', 'gas $0.125 + upkeep $0.09 + wear $0.12 + other $0.00'))
          eq('log button enabled on the example', (s['logOff'], s['copyOff']), (False, False))
          eq('nothing logged yet', (txt(page, '#tHour'), txt(page, '#tNet'), txt(page, '#tSub'), page.is_visible('#tStub')),
             ('-', '-', 'Nothing logged yet. Log an offer from the check above, or add one by hand.', False))
          eq('week starts empty', (txt(page, '#wTitle'), txt(page, '#wSub'), txt(page, '#wHour'), page.is_visible('#wStub')),
             ('Last 7 days, Sep 26 to Oct 2', 'No saved days in the last 7 days.', '-', False))
          eq('days list starts empty', txt(page, '#dayList'), 'No saved days yet. Tap Save today when your shift is over.')
          eq('entry list starts empty', page.evaluate("document.querySelectorAll('#entryList .entry').length"), 0)
          eq('today buttons disabled with nothing logged', (page.is_disabled('#todaySave'), page.is_disabled('#todayCopy'), page.is_disabled('#weekCopy')), (True, True, True))
          eq('clear log hidden with nothing logged', page.is_visible('#clearLogBtn'), False)
          eq('three groups start closed', page.evaluate("[...document.querySelectorAll('details.grp')].map(d => d.open)"), [False, False, False])
          eq('store warning hidden when storage works', page.is_visible('#storeWarn'), False)
          eq('toast hidden at first', page.is_visible('#toast'), False)
          eq('copy sheet hidden at first', page.is_visible('#sheet'), False)
          eq('support address in the footer', txt(page, '.mail'), SUPPORT)
          eq('today link and days link', page.evaluate("[...document.querySelectorAll('.jump a')].map(a => [a.textContent.trim(), a.getAttribute('href')])"),
             [['Today', '#h-today'], ['Days', '#h-days']])
          eq('the log date shows today', page.input_value('#logDate'), '2026-10-02')
          eq('save button says today', txt(page, '#todaySave'), 'Save today')

    if on('ui'):
      with section('math lines of the example'):
          page.evaluate("document.getElementById('mathBox').open = true")
          lines = page.evaluate("[...document.querySelectorAll('#mathLines p')].map(p => p.textContent.trim())")
          eq('math lines', lines, [
              'Cost per mile = fuel $0.125 + upkeep $0.09 + depreciation $0.12 + other $0.00 = $0.335',
              'Pay = $6.50 + $0.00 tip = $6.50',
              'Miles = 4.2 + 1.5 back = 5.7 mi',
              'Time = 22 + 5 wait + 4 back = 31 min (0.517 h)',
              'Car cost = 5.7 mi %s $0.335 = $1.91' % TIMES,
              'Net = $6.50 - $1.91 = $4.59',
              'Net per hour = $4.59 %s 0.517 h = $8.88' % DIVIDE,
              'Gross per mile = $6.50 %s 5.7 mi = $1.14' % DIVIDE,
              'Pay needed: $20.00 %s 0.517 h + $1.91 = $12.24 and $1.50 %s 5.7 mi = $8.55. The larger one, rounded up to the cent and kept above the car cost, is $12.25' % (TIMES, TIMES),
              'Set aside = $4.59 %s 20%% = $0.92, so you keep $3.67' % TIMES])
          eq('math text has no minus-sign or dash look-alikes', [c for c in DASHES if c in txt(page, '#mathBox')], [])
          eq('the static maths lists every verdict step', page.evaluate("[...document.querySelectorAll('#mathBox .mstatic .mline')].filter(p => /^[1-5]\\. /.test(p.textContent)).length"), 5)
          page.evaluate("document.getElementById('mathBox').open = false")

    if on('ui'):
      with section('faq'):
          eq('seven questions', page.evaluate("document.querySelectorAll('#faq details').length"), 7)
          eq('questions start closed', page.evaluate("[...document.querySelectorAll('#faq details')].filter(d => d.open).length"), 0)
          tap(page, '#faq details:nth-child(1) summary')
          eq('first question opens', page.evaluate("document.querySelector('#faq details:nth-child(1)').open"), True)
          has('first answer says what is divided', txt(page, '#faq details:nth-child(1) p'), 'Divide what is left by every hour')
          tap(page, '#faq details:nth-child(1) summary')
          eq('first question closes', page.evaluate("document.querySelector('#faq details:nth-child(1)').open"), False)
          eq('faq text has no dash look-alikes', [c for c in DASHES if c in txt(page, '#faq')], [])
          eq('faq mentions no connection to accounts', 'does not connect to any delivery or rideshare account' in page.evaluate("document.getElementById('faq').textContent"), True)
          eq('faq links to the irs gig page safely', page.evaluate("[...document.querySelectorAll('#faq a')].map(a => [a.getAttribute('href'), a.target, a.rel])"),
             [['https://www.irs.gov/businesses/small-businesses-self-employed/manage-taxes-for-your-gig-work', '_blank', 'noopener noreferrer']])
          eq('footer says not affiliated', 'not affiliated with or endorsed by any delivery or rideshare company' in txt(page, '.foot'), True)
          eq('footer says not tax advice', 'not tax or financial advice' in txt(page, '.foot'), True)
          eq('footer links', page.evaluate("[...document.querySelectorAll('.foot a')].map(a => a.getAttribute('href'))"),
             ['https://sanjixysti-creator.github.io/', 'https://sanjixysti-creator.github.io/rinse-rate/'] + (['mailto:' + SUPPORT, 'privacy.html'] if STANDALONE else []))
    ctx1.close()

    # ---- start blank
    if on('ui'):
      with section('start blank'):
          ctx2, page = new_page(browser)
          tap(page, '#exampleClear')
          s = snap(page)
          eq('offer fields are blank', {i: page.input_value('#' + i) for i in ('pay', 'tip', 'miles', 'minutes', 'wait', 'retMiles', 'retMin')},
             {'pay': '', 'tip': '', 'miles': '', 'minutes': '', 'wait': '', 'retMiles': '', 'retMin': ''})
          eq('goals, tax and car are kept', {i: page.input_value('#' + i) for i in ('goalHour', 'goalMile', 'taxPct', 'gasPrice', 'mpg', 'maint', 'depr')},
             {'goalHour': '20.00', 'goalMile': '1.50', 'taxPct': '20', 'gasPrice': '3.50', 'mpg': '28', 'maint': '0.09', 'depr': '0.12'})
          eq('example note gone', s['example'], False)
          eq('verdict is empty', (s['v'], s['word'], s['line']), ('empty', 'Add an offer', 'Type the pay, miles and minutes from the offer screen.'))
          eq('readings are dashes', (s['hour']['val'], s['mile']['val'], s['hour']['z'], s['mile']['z']), ('-', '-', 'none', 'none'))
          eq('goal lines stay', (s['hour']['goal'], s['mile']['goal']), ('Goal $20.00 an hour', 'Goal $1.50 a mile'))
          eq('no need box and no receipt', (s['need']['hidden'], s['stubHidden']), (True, True))
          eq('log and copy are disabled', (s['logOff'], s['copyOff']), (True, True))
          eq('bar shows dashes and a prompt', (s['bar']['hour'], s['bar']['mile'], s['barWord']), ('-', '-', 'Add pay'))
          eq('toast says cleared', toast(page), 'Offer cleared.')
          page.wait_for_timeout(450)
          st = stored(page)
          eq('stored: example ended, goals kept', (st['example'], st['pay'], st['miles'], st['goalHour'], st['goalMile'], st['gasPrice']), (False, 0, 0, 20, 1.5, 3.5))
          eq('verify on the blank state', verify_offer(page, dict(EX, pay=0, tip=0, miles=0, minutes=0, wait=0, retMiles=0, retMin=0), CAR0), [])
          # the same button in the section header does the same job, in one tap
          put(page, '#pay', '9')
          put(page, '#miles', '3')
          put(page, '#minutes', '12')
          tap(page, '#clearBtn')
          eq('Clear offer empties the offer in one tap', (page.input_value('#pay'), page.input_value('#miles'), page.input_value('#minutes'), vdata(page)), ('', '', '', 'empty'))
          eq('Clear offer also says so', toast(page), 'Offer cleared.')
          ctx2.close()

    if on('ui'):
      with section('editing ends the example'):
          ctx3, page = new_page(browser)
          put(page, '#pay', '7')
          eq('typing hides the example note', page.is_visible('#exampleNote'), False)
          page.wait_for_timeout(450)
          eq('stored example flag is off', stored(page)['example'], False)
          ctx3.close()
          ctx3b, page = new_page(browser)
          tap(page, '#waitChips button:nth-child(3)')
          eq('a chip also ends the example', page.is_visible('#exampleNote'), False)
          ctx3b.close()

    # ---- typing like a driver
    if on('ui'):
      with section('typing'):
          ctx4, page = new_page(browser)
          tap(page, '#exampleClear')
          # A field selects its text a moment after it gets focus, so a tap replaces the old number. A person cannot type
          # inside that moment, but a test can, so it waits.
          page.click('#pay')
          page.wait_for_timeout(60)
          page.keyboard.type('8.00')
          page.press('#pay', 'Tab')
          page.wait_for_timeout(60)
          page.keyboard.type('5.3')
          page.press('#miles', 'Tab')
          page.wait_for_timeout(60)
          page.keyboard.type('31')
          o = dict(EX, pay=8, tip=0, miles=5.3, minutes=31, wait=0, retMiles=0, retMin=0)
          eq('typed offer verifies against the reference', verify_offer(page, o, CAR0), [])
          s = snap(page)
          eq('typed offer reads', (s['v'], s['hour']['val'], s['mile']['val']), ('pass', '$12.05', '$1.51'))
          # the field keeps what was typed while focused and tidies on blur
          page.fill('#pay', '6.506')
          page.evaluate("document.getElementById('pay').blur()")
          eq('blur tidies the pay to cents', page.input_value('#pay'), '6.51')
          eq('the exact typed value is what counts', verify_offer(page, dict(o, pay=6.506), CAR0), [])
          for typed_text, want in (('$12.50 plus tip', 12.5), ('12,5', 12.5), ('abc', 0), ('-5', 0), ('1,234.56', 1234.56), ('  7  ', 7), ('0', 0), ('', 0)):
              page.fill('#pay', typed_text)
              eq('pay typed as %r reads as %r' % (typed_text, want), verify_offer(page, dict(o, pay=want), CAR0), [])
          page.fill('#pay', '99999999999')
          eq('a huge pay is held at ten million', verify_offer(page, dict(o, pay=1e7), CAR0), [])
          page.fill('#pay', '8')
          for typed_text, want in (('1:30', 90), ('2h', 120), ('1.5 hours', 90), ('45 min', 45), ('2:75', 0), ('abc', 0), ('-10', 0), ('90', 90)):
              page.fill('#minutes', typed_text)
              eq('minutes typed as %r read as %r' % (typed_text, want), verify_offer(page, dict(o, pay=8, minutes=want), CAR0), [])
          page.fill('#minutes', '31')
          for typed_text, want in (('5,3', 5.3), ('5.3 mi', 5.3), ('-2', 0), ('1.23456789', 1.23456789)):
              page.fill('#miles', typed_text)
              eq('miles typed as %r read as %r' % (typed_text, want), verify_offer(page, dict(o, pay=8, miles=want), CAR0), [])
          ctx4.close()

    # ---- the page against the reference, driven through its inputs
    if on('ui'):
      with section('page against the reference, random offers'):
          ctx5, page = new_page(browser)
          rnd = random.Random(4242)
          bad = []
          n = 0
          for i in range(180):
              o = rand_offer(rnd)
              car = rand_car(rnd)
              if i % 9 == 0:
                  o['goalHour'] = 0
              if i % 11 == 0:
                  o['goalMile'] = 0
              set_state(page, o, car)
              d = verify_offer(page, o, car)
              n += 1
              if d:
                  bad.append('%r %r -> %s' % (o, car, '; '.join(d[:3])))
          batch('180 random offers and cars shown correctly by the page (verdict, tiles, receipt, need box, bar)', bad, n)
          bad = []
          for i in range(40):
              o = rand_offer(rnd, huge=True)
              car = rand_car(rnd)
              set_state(page, o, car)
              d = verify_offer(page, o, car)
              if d:
                  bad.append('%r %r -> %s' % (o, car, '; '.join(d[:3])))
          batch('40 huge or tiny offers shown correctly by the page', bad, 40)
          ctx5.close()

    if on('ui'):
      with section('verdict wording'):
          ctx6, page = new_page(browser)
          k = lambda **kw: {**EX, **dict(pay=0, tip=0, miles=0, minutes=0, wait=0, retMiles=0, retMin=0), **kw}
          cases = [
              # (offer, word, line, bar word)
              (k(pay=25, miles=10, minutes=60, goalHour=20, goalMile=1.5), 'Take it', 'Meets both of your goals.', 'Take it'),
              (k(pay=25, miles=10, minutes=60, goalHour=20, goalMile=0), 'Take it', 'Meets your net per hour goal.', 'Take it'),
              (k(pay=25, miles=10, minutes=60, goalHour=0, goalMile=1.5), 'Take it', 'Meets your gross per mile goal.', 'Take it'),
              (k(pay=24.99, miles=10, minutes=60, goalHour=20, goalMile=1.5), 'Borderline', 'Close. Net per hour is short of your goal.', 'Borderline'),
              (k(pay=29.99, miles=20, minutes=30, goalHour=20, goalMile=1.5), 'Borderline', 'Close. Gross per mile is short of your goal.', 'Borderline'),
              (k(pay=21, miles=10, minutes=60, goalHour=20, goalMile=2.5), 'Borderline', 'Close. Net per hour and gross per mile are both short of your goals.', 'Borderline'),
              (k(pay=15, miles=10, minutes=60, goalHour=20, goalMile=1.5), 'Pass', 'Net per hour is short of your goal.', 'Pass'),
              (k(pay=13, miles=10, minutes=60, goalHour=20, goalMile=1.5), 'Pass', 'Net per hour and gross per mile are both short of your goals.', 'Pass'),
              (k(pay=3, miles=10, minutes=60, goalHour=20, goalMile=1.5), 'Pass', 'You would lose $2.00 on this offer. The car costs more than it pays.', 'Pass'),
              (k(pay=5, miles=10, minutes=60, goalHour=20, goalMile=1.5), 'Pass', 'This pays only what the car costs, so your time earns nothing.', 'Pass'),
              (k(pay=9, miles=10, minutes=60, goalHour=0, goalMile=0), 'No goals set', 'Set a goal under My goals to get a verdict. The numbers below still count.', 'No goals'),
              (k(pay=9, miles=10, minutes=0, goalHour=20, goalMile=0), 'Add the minutes', 'Your goals need the minutes to work out the verdict.', 'Add time'),
              (k(pay=9, miles=0, minutes=30, goalHour=0, goalMile=1.5), 'Add the miles', 'Your goals need the miles to work out the verdict.', 'Add miles'),
              (k(pay=9, miles=0, minutes=0, goalHour=20, goalMile=1.5), 'Add miles and minutes', 'Your goals need the miles and the minutes to work out the verdict.', 'Add trip'),
              (k(pay=0, miles=10, minutes=30, goalHour=20, goalMile=1.5), 'Add an offer', 'Type the pay to get a verdict. Below is the least this trip should pay.', 'Add pay'),
              (k(pay=0, miles=0, minutes=0, goalHour=20, goalMile=1.5), 'Add an offer', 'Type the pay, miles and minutes from the offer screen.', 'Add pay'),
          ]
          car = dict(CAR0, know=True, cpm=0.5)
          for o, word, line, barw in cases:
              set_state(page, o, car)
              s = snap(page)
              eq('wording for pay %s miles %s min %s goals %s/%s: word' % (o['pay'], o['miles'], o['minutes'], o['goalHour'], o['goalMile']), s['word'], word)
              eq('wording for pay %s miles %s min %s goals %s/%s: line' % (o['pay'], o['miles'], o['minutes'], o['goalHour'], o['goalMile']), s['line'], line)
              eq('wording for pay %s miles %s min %s goals %s/%s: bar word' % (o['pay'], o['miles'], o['minutes'], o['goalHour'], o['goalMile']), s['barWord'], barw)
              eq('verify pay %s miles %s min %s goals %s/%s' % (o['pay'], o['miles'], o['minutes'], o['goalHour'], o['goalMile']), verify_offer(page, o, car), [])
          # an offer with a goal on only one measure shows the other as not set
          set_state(page, k(pay=25, miles=10, minutes=60, goalHour=20, goalMile=0), car)
          s = snap(page)
          eq('no mile goal: tile says so, no meter and no percent', (s['mile']['goal'], s['mile']['z'], s['mile']['pct'], s['mile']['fill']), ('No goal set', 'none', '', '0%'))
          # a goal tile with the number missing asks for it
          set_state(page, k(pay=9, miles=10, minutes=0, goalHour=20, goalMile=1.5), car)
          s = snap(page)
          eq('missing minutes: the hour tile asks for them, the mile tile still reads', (s['hour']['val'], s['hour']['goal'], s['mile']['val'], s['mile']['goal']),
             ('-', 'Add the minutes', '$0.90', 'Goal $1.50 a mile'))
          ctx6.close()

    if on('ui'):
      with section('pay needed box'):
          ctx7, page = new_page(browser)
          k = lambda **kw: dict(EX, tip=0, wait=0, retMiles=0, retMin=0, **kw)
          car = dict(CAR0, know=True, cpm=0.5)
          set_state(page, k(pay=25, miles=10, minutes=60, goalHour=20, goalMile=1.5), car)
          s = snap(page)
          eq('exactly the pay needed', (s['need']['val'], s['need']['gap'], s['need']['why']),
             ('$25.00', 'This offer pays exactly that.', 'Set by your $20.00 an hour goal: $20.00 for 1 h, plus $5.00 for the car.'))
          set_state(page, k(pay=30, miles=10, minutes=60, goalHour=20, goalMile=1.5), car)
          eq('more than needed', snap(page)['need']['gap'], 'This offer pays $5.00 more than that.')
          set_state(page, k(pay=20, miles=10, minutes=60, goalHour=20, goalMile=1.5), car)
          eq('less than needed', snap(page)['need']['gap'], '$5.00 more than this offer pays.')
          set_state(page, k(pay=10, miles=20, minutes=30, goalHour=20, goalMile=1.5), car)
          s = snap(page)
          eq('the per mile goal sets it', (s['need']['val'], s['need']['why']), ('$30.00', 'Set by your $1.50 a mile goal: $1.50 for 20 mi.'))
          set_state(page, k(pay=10, miles=10, minutes=60, goalHour=20, goalMile=2.5), car)
          eq('both goals ask for the same pay', snap(page)['need']['why'], 'Your two goals ask for the same pay.')
          set_state(page, k(pay=4, miles=10, minutes=30, goalHour=0, goalMile=0.1), car)
          s = snap(page)
          eq('the car cost sets it', (s['need']['val'], s['need']['why']), ('$5.01', 'Set by the car cost: the pay has to beat $5.00 first.'))
          set_state(page, k(pay=9, miles=10, minutes=60, goalHour=0, goalMile=0), car)
          eq('no goals: no box', snap(page)['need']['hidden'], True)
          set_state(page, k(pay=9, miles=0, minutes=60, goalHour=20, goalMile=1.5), car)
          eq('a goal that cannot be worked out: no box', snap(page)['need']['hidden'], True)
          set_state(page, k(pay=0, miles=10, minutes=30, goalHour=20, goalMile=0), car)
          s = snap(page)
          eq('no pay yet: the box shows the least the trip should pay, with no gap', (s['need']['hidden'], s['need']['val'], s['need']['gap']), (False, '$15.00', ''))
          ctx7.close()

    # ---- alerts and warnings
    if on('ui'):
      with section('alerts and warnings'):
          ctx8, page = new_page(browser)
          k = lambda **kw: {**EX, **dict(pay=9, tip=0, miles=3, minutes=20, wait=0, retMiles=0, retMin=0), **kw}
          zero_msg = 'Your car cost is $0 a mile, so these numbers ignore what driving costs you. Set it under My car.'
          eq('no warnings on the example', (shown(page, '#offerAlert'), shown(page, '#carWarn')), (False, False))
          # own number ticked but left blank
          set_state(page, k(), dict(CAR0, know=True, cpm=0))
          eq('own number blank: offer alert and car warning', (txt(page, '#offerAlert'), txt(page, '#carWarn')),
             (zero_msg, 'You said you know your cost per mile, but it is blank. The car cost counts as $0.'))
          eq('own number blank: the offer still reads', verify_offer(page, k(), dict(CAR0, know=True, cpm=0)), [])
          set_state(page, k(pay=0), dict(CAR0, know=True, cpm=0))
          eq('no pay: no offer alert, but the car warning stays', (shown(page, '#offerAlert'), shown(page, '#carWarn')), (False, True))
          set_state(page, k(), dict(CAR0, know=True, cpm=0.4))
          eq('own number filled: no warnings', (shown(page, '#offerAlert'), shown(page, '#carWarn')), (False, False))
          # gas with a field missing: upkeep and wear still count, so only the car warning shows
          set_state(page, k(), dict(CAR0, mpg=0))
          eq('gas without mpg', (shown(page, '#offerAlert'), txt(page, '#carWarn')), (False, 'Add the gas price and miles per gallon. Until then fuel counts as $0.'))
          set_state(page, k(), dict(CAR0, gasPrice=0))
          eq('gas without a price', txt(page, '#carWarn'), 'Add the gas price and miles per gallon. Until then fuel counts as $0.')
          set_state(page, k(), dict(CAR0, fuel='electric', mikwh=0))
          eq('electric without miles per kWh', txt(page, '#carWarn'), 'Add the electricity price and miles per kWh. Until then fuel counts as $0.')
          set_state(page, k(), dict(CAR0, fuel='electric', kwhPrice=0))
          eq('electric without a price', txt(page, '#carWarn'), 'Add the electricity price and miles per kWh. Until then fuel counts as $0.')
          # nothing at all: every part of the car cost is zero
          set_state(page, k(), dict(CAR0, mpg=0, maint=0, depr=0, carOther=0))
          eq('car cost of zero from every part', (txt(page, '#offerAlert'), shown(page, '#carWarn')), (zero_msg, True))
          eq('the zero-cost offer reads against the reference', verify_offer(page, k(), dict(CAR0, mpg=0, maint=0, depr=0, carOther=0)), [])
          set_state(page, k(), CAR0)
          eq('back to the default car: warnings gone', (shown(page, '#offerAlert'), shown(page, '#carWarn')), (False, False))
          ctx8.close()

    if on('ui'):
      with section('car group'):
          ctx9, page = new_page(browser)
          open_all(page)
          tap(page, '#fuelChips button:nth-child(2)')
          eq('electric: fields swap', (page.is_visible('#elecFields'), page.is_visible('#gasFields')), (True, False))
          eq('electric reading', (txt(page, '#carBig'), txt(page, '#carParts'), txt(page, '#hintCar')),
             ('$0.263 a mile', 'power $0.053 + upkeep $0.09 + wear $0.12 + other $0.00', '$0.263 a mile, electric'))
          eq('electric chip pressed', pressed(page, 'fuelChips'), ['Electric'])
          eq('electric car verifies', verify_offer(page, EX, dict(CAR0, fuel='electric')), [])
          tap(page, '#fuelChips button:nth-child(1)')
          eq('gas again', (page.is_visible('#gasFields'), page.is_visible('#elecFields'), txt(page, '#carBig')), (True, False, '$0.335 a mile'))
          tap(page, '#fuelChips button:nth-child(1)')
          eq('pressing the chosen fuel again keeps it', pressed(page, 'fuelChips'), ['Gas'])
          put(page, '#gasPrice', '4.2')
          put(page, '#mpg', '35')
          eq('typed gas price and mpg', txt(page, '#carBig'), '$0.33 a mile')
          eq('typed car verifies', verify_offer(page, EX, dict(CAR0, gasPrice=4.2, mpg=35)), [])
          put(page, '#carOther', '0.05')
          eq('other cost adds', (txt(page, '#carBig'), txt(page, '#carParts')), ('$0.38 a mile', 'gas $0.12 + upkeep $0.09 + wear $0.12 + other $0.05'))
          # the own number replaces the sum and keeps the rest for later
          tap(page, '#know')
          eq('own number: its field shows, the sum fields hide', (page.is_visible('#cpmField'), page.is_visible('#sumFields')), (True, False))
          eq('own number starts blank with a warning', (page.input_value('#cpm'), page.is_visible('#carWarn')), ('', True))
          put(page, '#cpm', '0.5')
          eq('own number reading', (txt(page, '#carBig'), txt(page, '#carParts'), txt(page, '#hintCar')), ('$0.50 a mile', 'Your own number', '$0.50 a mile, your own number'))
          eq('own number verifies', verify_offer(page, EX, dict(CAR0, know=True, cpm=0.5, gasPrice=4.2, mpg=35, carOther=0.05)), [])
          tap(page, '#know')
          eq('own number off: the sum comes back with what was typed', (txt(page, '#carBig'), page.input_value('#gasPrice'), page.input_value('#mpg'), page.input_value('#carOther')),
             ('$0.38 a mile', '4.20', '35', '0.05'))
          tap(page, '#resetBtn')
          eq('reset needs a second tap', (txt(page, '#resetBtn'), page.input_value('#gasPrice')), ('Tap again to reset', '4.20'))
          tap(page, '#resetBtn')
          eq('reset brings back the car and goals', (txt(page, '#resetBtn'), page.input_value('#gasPrice'), page.input_value('#mpg'), page.input_value('#carOther'), page.input_value('#goalHour'), page.input_value('#goalMile'), page.input_value('#taxPct')),
             ('Reset car and goals', '3.50', '28', '', '20.00', '1.50', '20'))
          eq('reset says so', toast(page), 'Car and goals reset.')
          eq('reset leaves the offer alone', (page.input_value('#pay'), page.input_value('#miles'), page.input_value('#minutes')), ('6.50', '4.2', '22'))
          tap(page, '#resetBtn')
          page.wait_for_timeout(3300)
          eq('an armed reset disarms by itself', txt(page, '#resetBtn'), 'Reset car and goals')
          ctx9.close()

    if on('ui'):
      with section('irs line'):
          for now, want in (
                  ('2026-10-02T09:30:00', 'The IRS business rate is 76 cents a mile (July 1 to December 31, 2026).'),
                  ('2026-03-15T10:00:00', 'The IRS business rate is 72.5 cents a mile (January 1 to June 30, 2026).'),
                  ('2026-06-30T23:59:00', 'The IRS business rate is 72.5 cents a mile (January 1 to June 30, 2026).'),
                  ('2026-07-01T00:01:00', 'The IRS business rate is 76 cents a mile (July 1 to December 31, 2026).')):
              cx, pg = new_page(browser, now=now)
              t = txt(pg, '#carIrs')
              has('irs line on %s' % now[:10], t, want)
              has('irs line names its source and date', t, 'Source: IRS standard mileage rates, checked October 2, 2026.')
              has('irs line says it is not the cost', t, 'It is a tax figure, not your cost.')
              cx.close()
          cx, pg = new_page(browser)
          eq('irs link', pg.evaluate("[...document.querySelectorAll('#carIrs a')].map(a => [a.getAttribute('href'), a.target, a.rel])"),
             [['https://www.irs.gov/tax-professionals/standard-mileage-rates', '_blank', 'noopener noreferrer']])
          has('76 cents against the default 33.5', txt(pg, '#carIrs'), 'Yours is 42.5 cents lower.')
          set_state(pg, EX, dict(CAR0, know=True, cpm=1.0))
          has('own number above the IRS rate', txt(pg, '#carIrs'), 'Yours is 24 cents higher.')
          set_state(pg, EX, dict(CAR0, know=True, cpm=0.76))
          has('own number equal to the IRS rate', txt(pg, '#carIrs'), 'Yours is about the same.')
          cx.close()
          # a new year passes: the page says its figures are old instead of quoting them as current
          cx, pg = new_page(browser, now='2027-02-01T09:30:00')
          t = txt(pg, '#carIrs')
          eq('stale text after the new year', t.startswith('This page still lists 2026 IRS rates.'), True)
          has('stale text says to check the current figure', t, 'check the current figure before you rely on this one')
          eq('stale text has no link and no quoted rate', (pg.evaluate("document.querySelectorAll('#carIrs a').length"), 'cents a mile' in t), (0, False))
          tap(pg, '#logBtn')
          has('stale text also shows in the day note', txt(pg, '#tNote'), 'This page still lists 2026 IRS rates.')
          cx.close()

    # ---- chips
    if on('ui'):
      with section('chips'):
          ctx10, page = new_page(browser)
          open_all(page)
          tap(page, '#tipChips button:nth-child(4)')
          eq('tip chip fills the field', (page.input_value('#tip'), pressed(page, 'tipChips'), txt(page, '#hintMore')), ('3.00', ['$3'], 'tip $3.00, wait 5 min, back 1.5 mi, 4 min'))
          s = snap(page)
          eq('tip changes the receipt', (s['stub'][1], s['stub'][3]), (['Pay plus tip', '$9.50'], ['Net after car cost', '$7.59']))
          eq('tip chip verifies', verify_offer(page, dict(EX, tip=3), CAR0), [])
          put(page, '#tip', '2.5')
          eq('a tip that matches no chip presses none', pressed(page, 'tipChips'), [])
          put(page, '#tip', '5')
          eq('typing a chip value presses that chip', pressed(page, 'tipChips'), ['$5'])
          tap(page, '#tipChips button:nth-child(1)')
          eq('None clears the tip', (page.input_value('#tip'), pressed(page, 'tipChips')), ('', ['None']))
          tap(page, '#waitChips button:nth-child(5)')
          eq('wait chip', (page.input_value('#wait'), pressed(page, 'waitChips')), ('15', ['15']))
          eq('wait chip verifies', verify_offer(page, dict(EX, wait=15), CAR0), [])
          tap(page, '#waitChips button:nth-child(1)')
          eq('wait None', (page.input_value('#wait'), pressed(page, 'waitChips')), ('', ['None']))
          tap(page, '#goalHourChips button:nth-child(4)')
          eq('hour goal chip', (page.input_value('#goalHour'), pressed(page, 'goalHourChips'), txt(page, '#hintGoals')), ('25.00', ['$25'], '$25.00/hr net, $1.50/mi gross, 20% set aside'))
          eq('hour goal chip verifies', verify_offer(page, dict(EX, wait=0, goalHour=25), CAR0), [])
          tap(page, '#goalMileChips button:nth-child(4)')
          eq('mile goal chip', (page.input_value('#goalMile'), pressed(page, 'goalMileChips')), ('1.75', ['$1.75']))
          tap(page, '#taxChips button:nth-child(1)')
          eq('0 percent set aside', (page.input_value('#taxPct'), pressed(page, 'taxChips'), 'You keep' in [r[0] for r in snap(page)['stub']]), ('0', ['0%'], False))
          tap(page, '#taxChips button:nth-child(6)')
          eq('30 percent set aside', (page.input_value('#taxPct'), pressed(page, 'taxChips')), ('30', ['30%']))
          eq('tax chip verifies', verify_offer(page, dict(EX, wait=0, goalHour=25, goalMile=1.75, taxPct=30), CAR0), [])
          # a goal can be cleared: the field goes blank and no chip stays pressed
          put(page, '#goalHour', '')
          eq('blank goal: no chip pressed, hint says what is left', (pressed(page, 'goalHourChips'), txt(page, '#hintGoals')), ([], '$1.75/mi gross, 30% set aside'))
          put(page, '#goalMile', '')
          eq('both goals blank: hint says none', txt(page, '#hintGoals'), 'No goals set, 30% set aside')
          eq('both goals blank: verdict says so', (vdata(page), txt(page, '#vWord')), ('nogoals', 'No goals set'))
          eq('both goals blank: tiles still read', (txt(page, '#vHour'), txt(page, '#vMile')), ('$10.59', '$1.14'))
          eq('chip groups are labelled', page.evaluate("[...document.querySelectorAll('.chips')].map(c => c.getAttribute('aria-label') || c.getAttribute('aria-labelledby'))"),
             ['Common tips in dollars', 'Common waits in minutes', 'fuelLab', 'Common hourly goals in dollars', 'Common per mile goals in dollars', 'Common tax set-aside percentages'])
          eq('every chip says whether it is on', page.evaluate("[...document.querySelectorAll('.chip')].every(b => b.getAttribute('aria-pressed') === 'true' || b.getAttribute('aria-pressed') === 'false')"), True)
          ctx10.close()

    # ---- the optional fields
    if on('ui'):
      with section('more on this offer'):
          ctx11, page = new_page(browser)
          open_all(page)
          eq('app list', page.evaluate("[...document.querySelectorAll('#app option')].map(o => o.textContent)"),
             ['No app', 'DoorDash', 'Uber Eats', 'Grubhub', 'Instacart', 'Spark', 'Amazon Flex', 'Shipt', 'Uber', 'Lyft', 'Other'])
          page.select_option('#app', 'Lyft')
          eq('picking an app shows in the hint and ends the example', (txt(page, '#hintMore'), page.is_visible('#exampleNote')), ('wait 5 min, back 1.5 mi, 4 min, Lyft', False))
          put(page, '#retMiles', '0')
          put(page, '#retMin', '0')
          put(page, '#wait', '')
          eq('no extras: hint falls back to the prompt, app stays', txt(page, '#hintMore'), 'Lyft')
          page.select_option('#app', '')
          eq('no app and no extras', txt(page, '#hintMore'), 'Tip, wait, trip back')
          # the trip back is real time and real miles
          put(page, '#retMiles', '2')
          put(page, '#retMin', '10')
          eq('trip back verifies', verify_offer(page, dict(EX, wait=0, retMiles=2, retMin=10), CAR0), [])
          eq('trip back in the receipt label', snap(page)['stub'][0][0], 'Trip, all in')
          put(page, '#retMiles', '')
          put(page, '#retMin', '')
          eq('no extras: the trip row says Trip', snap(page)['stub'][0], ['Trip', '4.2 mi, 22 min'])
          ctx11.close()

    # ============================================================ the log, saved days and the week
    def base_state(**kw):
        st = dict(v=1, example=False, pay=0, tip=0, miles=0, minutes=0, wait=0, retMiles=0, retMin=0, app='',
                  fuel='gas', gasPrice=3.5, mpg=28, kwhPrice=0.17, mikwh=3.2, maint=0.09, depr=0.12, carOther=0, know=False, cpm=0,
                  goalHour=20, goalMile=1.5, taxPct=20, hoursOv=0, milesOv=0, logDate='', seq=0, entries=[], days=[])
        st.update(kw)
        return st

    def mk_entry(i, pay, miles, mins, ret=0, app='', note=''):
        return dict(id='e%d' % i, pay=pay, miles=miles, min=mins, ret=ret, app=app, note=note)

    def mk_day(i, date, orders, gross, miles, hours, net):
        return dict(id='d%d' % i, date=date, orders=orders, gross=gross, miles=miles, hours=hours, net=net)

    def day_text_date(date, year=True):
        import datetime
        dd = datetime.date.fromisoformat(date)
        s = dd.strftime('%a, %b ') + str(dd.day)
        return s + (', %d' % dd.year if year else '')

    ENTRY_JS = '''() => [...document.querySelectorAll('#entryList .entry')].map(e => ({
        id: e.getAttribute('data-id'), app: e.querySelector('.en-app').textContent.trim(), pay: e.querySelector('.en-pay').textContent.trim(),
        sub: e.querySelector('.en-sub').textContent.trim(), net: e.querySelector('.en-net').textContent.trim(),
        note: e.querySelector('.en-note') ? e.querySelector('.en-note').textContent.trim() : null, editing: e.classList.contains('editing'),
        buttons: [...e.querySelectorAll('.row-actions button')].map(b => b.textContent.trim())}))'''
    DAY_JS = '''() => [...document.querySelectorAll('#dayList .day')].map(e => ({
        id: e.getAttribute('data-id'), date: e.querySelector('.d-date').textContent.trim(), hour: e.querySelector('.d-hour').textContent.trim(),
        sub: e.querySelector('.d-sub').textContent.trim(), buttons: [...e.querySelectorAll('.row-actions button')].map(b => b.textContent.trim())}))'''

    def entries_of(page):
        return page.evaluate(ENTRY_JS)

    def days_of(page):
        return page.evaluate(DAY_JS)

    def add_by_hand(page, pay, miles, mins, ret='', app='', note=''):
        page.evaluate("document.getElementById('entryBox').open = true")
        put(page, '#ePay', pay)
        page.select_option('#eApp', app)
        put(page, '#eMiles', miles)
        put(page, '#eMin', mins)
        put(page, '#eRet', ret)
        put(page, '#eNote', note)
        tap(page, '#eAdd')

    def verify_shift(page, entries, hov, mov, car, tax, date):
        """Today's totals as the page shows them, against the reference."""
        cpm = ref_car(car)['cpm']
        w = ref_shift(entries, hov, mov, cpm, tax, ref_rate(date))
        t = page.evaluate('''() => { const $ = id => document.getElementById(id);
            return {hour: $('tHour').textContent.trim(), net: $('tNet').textContent.trim(), hidden: $('tStub').hidden,
                    stub: [...$('tStub').querySelectorAll('.srow')].map(r => [r.querySelector('dt').textContent.trim(), r.querySelector('dd').textContent.trim()]),
                    save: $('todaySave').disabled, copy: $('todayCopy').disabled}; }''')
        bad = []
        has_ = w['n'] > 0
        if has_ and w['hours'] > 0:
            if not money_match(t['hour'], w['nph']):
                bad.append('net per hour: got %r want %s' % (t['hour'], float(w['nph'])))
        elif t['hour'] != '-':
            bad.append('net per hour: got %r want a dash' % t['hour'])
        if has_:
            if not money_match(t['net'], w['net']):
                bad.append('net: got %r want %s' % (t['net'], float(w['net'])))
        elif t['net'] != '-':
            bad.append('net: got %r want a dash' % t['net'])
        rows = []
        if has_:
            rows.append(('Gross pay', w['gross']))
            carv = float(w['carCost'])
            rows.append(('Car cost (%s mi at %s)' % (fmt_num(w['miles'], 1), cpm_text(float(cpm))), -carv if abs(carv) >= 0.005 else 0))
            rows.append(('Net', w['net']))
            if w['miles'] > 0:
                rows.append(('Net per mile', w['npm']))
                rows.append(('Gross per mile', w['gpm']))
            if tax > 0 and w['net'] > 0:
                rows.append(('Set aside for taxes (%s%%)' % fmt_num(tax, 2), -w['setAside']))
                rows.append(('You keep', w['takeHome']))
            rows.append(('Mileage value at the IRS rate', w['deduction']))
        if t['hidden'] != (not has_):
            bad.append('receipt hidden: got %r' % t['hidden'])
        if len(t['stub']) != len(rows):
            bad.append('rows: got %r' % (t['stub'],))
        else:
            for (lab, vv), (wl, wn) in zip(t['stub'], rows):
                if lab != wl:
                    ma = re.fullmatch(r'Car cost \((.+) mi at \$([0-9.]+)\)', lab)
                    mb = re.fullmatch(r'Car cost \((.+) mi at \$([0-9.]+)\)', wl)
                    if not (ma and mb and ma.group(1) == mb.group(1) and abs(float(ma.group(2)) - float(mb.group(2))) <= 0.00101):
                        bad.append('label: got %r want %r' % (lab, wl))
                elif not money_match(vv, wn):
                    bad.append('%s: got %r want %s' % (wl, vv, float(wn)))
        if t['save'] != (not has_) or t['copy'] != (not has_):
            bad.append('buttons disabled: save %r copy %r' % (t['save'], t['copy']))
        return bad

    if on('ui'):
      with section('log: add from the check, edit, delete'):
          ctx12, page = new_page(browser)
          tap(page, '#logBtn')
          eq('one entry from the example', entries_of(page), [dict(id='e1', app='Offer', pay='$6.50', sub='4.2 mi and 1.5 mi back, 31 min', net='Net $4.59, $8.88 an hour', note=None,
                                                               editing=False, buttons=['Edit', 'Delete'])])
          eq('offer fields cleared by logging', {i: page.input_value('#' + i) for i in ('pay', 'tip', 'miles', 'minutes', 'wait', 'retMiles', 'retMin')},
             {'pay': '', 'tip': '', 'miles': '', 'minutes': '', 'wait': '', 'retMiles': '', 'retMin': ''})
          eq('goals and car kept after logging', (page.input_value('#goalHour'), page.input_value('#gasPrice')), ('20.00', '3.50'))
          eq('example note gone after logging', page.is_visible('#exampleNote'), False)
          eq('the check is empty again', (vdata(page), txt(page, '#vWord')), ('empty', 'Add an offer'))
          eq('toast after logging', toast(page), 'Logged $6.50. 1 offer today.')
          eq('today reading', (txt(page, '#tHour'), txt(page, '#tNet'), txt(page, '#tSub'), txt(page, '#todayHint')),
             ('$8.88', '$4.59', '1 offer, 31 min, 5.7 mi, 44% of your hourly goal.', 'Fri, Oct 2'))
          eq('today receipt', stub(page, '#tStub'), [['Gross pay', '$6.50'], ['Car cost (5.7 mi at $0.335)', '-$1.91'], ['Net', '$4.59'], ['Net per mile', '$0.81'], ['Gross per mile', '$1.14'],
                                                     ['Set aside for taxes (20%)', '-$0.92'], ['You keep', '$3.67'], ['Mileage value at the IRS rate', '$4.33']])
          eq('today note', txt(page, '#tNote'), 'IRS business rate of 76 cents a mile for July 1 to December 31, 2026, as listed on October 2, 2026. '
                                                'An estimate for the standard mileage method, not tax advice. Ask a tax professional what fits you.')
          eq('overrides show the automatic figures as hints', (page.get_attribute('#hoursOv', 'placeholder'), page.get_attribute('#milesOv', 'placeholder')), ('0.52', '5.7'))
          eq('today buttons enabled', (page.is_disabled('#todaySave'), page.is_disabled('#todayCopy'), page.is_visible('#clearLogBtn')), (False, False, True))
          eq('today verifies', verify_shift(page, [mk_entry(1, 6.5, 4.2, 31, 1.5)], 0, 0, CAR0, 20, '2026-10-02'), [])
          st = stored(page)
          eq('stored at once: the entry and the counter', (st['entries'], st['seq'], st['pay']), ([dict(id='e1', pay=6.5, miles=4.2, min=31, ret=1.5, app='', note='')], 1, 0))
          # a second entry by hand, minutes typed as a clock time
          add_by_hand(page, '12', '5', '1:30', app='Uber Eats', note='Lunch rush')
          es = entries_of(page)
          eq('newest entry first', [(e['id'], e['app'], e['pay']) for e in es], [('e2', 'Uber Eats', '$12.00'), ('e1', 'Offer', '$6.50')])
          eq('hand entry details', (es[0]['sub'], es[0]['net'], es[0]['note']), ('5 mi, 1 h 30 min', 'Net $10.33, $6.88 an hour', 'Lunch rush'))
          eq('toast after adding', toast(page), 'Added $12.00. 2 offers today.')
          eq('the form clears and stays open', (page.input_value('#ePay'), page.input_value('#eMin'), page.input_value('#eNote'), page.evaluate("document.getElementById('entryBox').open")), ('', '', '', True))
          eq('two entries verify', verify_shift(page, [mk_entry(1, 6.5, 4.2, 31, 1.5), mk_entry(2, 12, 5, 90)], 0, 0, CAR0, 20, '2026-10-02'), [])
          # an incomplete entry is refused
          put(page, '#ePay', '5')
          tap(page, '#eAdd')
          eq('incomplete entry refused', (toast(page), len(entries_of(page))), ('Add the pay, miles and minutes first.', 2))
          put(page, '#ePay', '')
          # edit the older entry
          tap(page, '#entryList .entry:nth-child(2) .row-actions button:nth-child(1)')
          eq('edit form is filled', (txt(page, '#entryTitle'), txt(page, '#eAdd'), page.is_visible('#eCancel'), page.input_value('#ePay'), page.input_value('#eMiles'),
                                     page.input_value('#eMin'), page.input_value('#eRet'), page.input_value('#eApp'), page.input_value('#eNote')),
             ('Edit this offer', 'Save changes', True, '6.50', '4.2', '31', '1.5', '', ''))
          eq('edited entry is marked', [e['editing'] for e in entries_of(page)], [False, True])
          eq('focus moves to the pay field', page.evaluate('document.activeElement.id'), 'ePay')
          put(page, '#ePay', '7')
          put(page, '#eRet', '')
          tap(page, '#eAdd')
          es = entries_of(page)
          eq('edit saved in place', [(e['id'], e['pay'], e['sub'], e['editing']) for e in es], [('e2', '$12.00', '5 mi, 1 h 30 min', False), ('e1', '$7.00', '4.2 mi, 31 min', False)])
          eq('edit toast and form reset', (toast(page), txt(page, '#entryTitle'), txt(page, '#eAdd'), page.is_visible('#eCancel'), page.input_value('#ePay')),
             ('Entry updated.', 'Add an offer by hand', 'Add to today', False, ''))
          eq('edit keeps the id order and the counter', (stored(page)['seq'], [e['id'] for e in stored(page)['entries']]), (2, ['e1', 'e2']))
          # cancel an edit
          tap(page, '#entryList .entry:nth-child(1) .row-actions button:nth-child(1)')
          put(page, '#ePay', '99')
          tap(page, '#eCancel')
          eq('cancel leaves the entry alone and resets the form', (entries_of(page)[0]['pay'], txt(page, '#eAdd'), page.input_value('#ePay'), page.is_visible('#eCancel')), ('$12.00', 'Add to today', '', False))
          # delete takes two taps
          tap(page, '#entryList .entry:nth-child(1) .row-actions button:nth-child(2)')
          eq('first tap only asks', (entries_of(page)[0]['buttons'], len(entries_of(page))), (['Edit', 'Tap again to delete'], 2))
          tap(page, '#entryList .entry:nth-child(1) .row-actions button:nth-child(2)')
          eq('second tap deletes the newest', ([e['id'] for e in entries_of(page)], toast(page)), (['e1'], 'Entry deleted.'))
          eq('focus lands on a button still in the list', page.evaluate("document.activeElement.closest('#entryList') !== null && document.activeElement.tagName"), 'BUTTON')
          tap(page, '#entryList .entry:nth-child(1) .row-actions button:nth-child(2)')
          tap(page, '#entryList .entry:nth-child(1) .row-actions button:nth-child(2)')
          eq('deleting the last entry empties the list and the totals', (len(entries_of(page)), txt(page, '#tHour'), txt(page, '#tNet'), page.is_visible('#clearLogBtn')), (0, '-', '-', False))
          eq('focus lands on the add form when the list is empty', page.evaluate("document.activeElement.tagName + ':' + (document.activeElement.parentElement.id || '')"), 'SUMMARY:entryBox')
          eq('an empty day verifies', verify_shift(page, [], 0, 0, CAR0, 20, '2026-10-02'), [])
          ctx12.close()

    if on('ui'):
      with section('log: an armed delete lets go by itself'):
          ctx13, page = new_page(browser, pre_state=base_state(entries=[mk_entry(1, 8, 3, 20, 1)], seq=1))
          tap(page, '#entryList .entry .row-actions button:nth-child(2)')
          page.wait_for_timeout(3300)
          eq('the label goes back and nothing was deleted', (entries_of(page)[0]['buttons'], len(entries_of(page))), (['Edit', 'Delete'], 1))
          ctx13.close()

    if on('ui'):
      with section('log: deleting the entry being edited'):
          ctx14, page = new_page(browser, pre_state=base_state(entries=[mk_entry(1, 8, 3, 20, 1), mk_entry(2, 12, 5, 30)], seq=2))
          tap(page, '#entryList .entry:nth-child(2) .row-actions button:nth-child(1)')
          eq('editing e1', txt(page, '#entryTitle'), 'Edit this offer')
          tap(page, '#entryList .entry:nth-child(2) .row-actions button:nth-child(2)')
          tap(page, '#entryList .entry:nth-child(2) .row-actions button:nth-child(2)')
          eq('the form leaves edit mode', (txt(page, '#entryTitle'), txt(page, '#eAdd'), page.is_visible('#eCancel'), page.input_value('#ePay')), ('Add an offer by hand', 'Add to today', False, ''))
          eq('the other entry is untouched', [e['id'] for e in entries_of(page)], ['e2'])
          ctx14.close()

    if on('ui'):
      with section('log: hours and miles typed over the entries'):
          ents = [mk_entry(1, 8, 3, 20, 1), mk_entry(2, 12, 5, 30)]
          ctx15, page = new_page(browser, pre_state=base_state(entries=ents, seq=2))
          eq('totals from the entries', verify_shift(page, ents, 0, 0, CAR0, 20, '2026-10-02'), [])
          eq('sub line from the entries', txt(page, '#tSub'), '2 offers, 50 min, 9 mi, 101% of your hourly goal.')
          eq('no override note yet', txt(page, '#tNote').startswith('IRS business rate'), True)
          put(page, '#hoursOv', '2:30')
          eq('hours typed as a clock time', verify_shift(page, ents, 2.5, 0, CAR0, 20, '2026-10-02'), [])
          has('note says hours were typed', txt(page, '#tNote'), 'Using the hours you typed.')
          has('sub line uses the typed hours', txt(page, '#tSub'), '2 offers, 2 h 30 min, 9 mi,')
          put(page, '#milesOv', '30')
          eq('miles typed too', verify_shift(page, ents, 2.5, 30, CAR0, 20, '2026-10-02'), [])
          has('note says both were typed', txt(page, '#tNote'), 'Using the hours and miles you typed.')
          put(page, '#hoursOv', '')
          has('note says miles only', txt(page, '#tNote'), 'Using the miles you typed.')
          eq('miles override alone verifies', verify_shift(page, ents, 0, 30, CAR0, 20, '2026-10-02'), [])
          put(page, '#hoursOv', '30')
          has('a day of more than 24 hours is questioned', txt(page, '#tNote'), 'That is more than 24 hours in one day. Check the hours.')
          put(page, '#hoursOv', '2.5')
          eq('2.5 is two and a half hours', verify_shift(page, ents, 2.5, 30, CAR0, 20, '2026-10-02'), [])
          page.wait_for_timeout(400)
          eq('overrides persist', stored(page)['hoursOv'], 2.5)
          tap(page, '#clearLogBtn')
          eq('clear log needs a second tap', (txt(page, '#clearLogBtn'), len(entries_of(page))), ('Tap again to clear', 2))
          tap(page, '#clearLogBtn')
          eq('clear log empties entries and overrides', (len(entries_of(page)), page.input_value('#hoursOv'), page.input_value('#milesOv'), toast(page)), (0, '', '', 'Log cleared.'))
          ctx15.close()

    if on('ui'):
      with section('log: random shifts against the reference'):
          rnd = random.Random(777)
          ctx16, page = new_page(browser)
          bad, n = [], 0
          for i in range(60):
              ne = rnd.choice([1, 2, 3, 5, 9])
              ents = [mk_entry(j + 1, round(rnd.uniform(0.5, 40), 2), round(rnd.uniform(0.1, 20), 1), rnd.randint(1, 90), rnd.choice([0, 0, round(rnd.uniform(0.1, 5), 1)])) for j in range(ne)]
              hov = rnd.choice([0, 0, round(rnd.uniform(0.5, 12), 2)])
              mov = rnd.choice([0, 0, round(rnd.uniform(1, 300), 1)])
              car = rand_car(rnd)
              tax = rnd.choice([0, 15, 20, 25])
              st = base_state(entries=ents, seq=len(ents), hoursOv=hov, milesOv=mov, taxPct=tax, goalHour=20,
                              **{k_: car[k_] for k_ in ('fuel', 'gasPrice', 'mpg', 'kwhPrice', 'mikwh', 'maint', 'depr', 'carOther', 'know', 'cpm')})
              cx, pg = new_page(browser, pre_state=st)
              d = verify_shift(pg, ents, hov, mov, car, tax, '2026-10-02')
              cx.close()
              n += 1
              if d:
                  bad.append('%d entries, hours %r, miles %r, tax %r: %s' % (ne, hov, mov, tax, '; '.join(d[:3])))
          batch('60 random logs shown correctly by the page (totals, receipt, set-aside, mileage value)', bad, n)
          ctx16.close()

    if on('ui'):
      with section('save today and the days list'):
          ents = [mk_entry(1, 8, 3, 20, 1), mk_entry(2, 12, 5, 30)]
          car5 = dict(CAR0, know=True, cpm=0.5)
          st0 = base_state(entries=ents, seq=2, know=True, cpm=0.5, hoursOv=2.5, milesOv=30)
          ctx17, page = new_page(browser, pre_state=st0)
          eq('save button says today', txt(page, '#todaySave'), 'Save today')
          tap(page, '#todaySave')
          eq('toast after saving', toast(page), 'Saved Fri, Oct 2.')
          eq('the log is empty after saving', (len(entries_of(page)), page.input_value('#hoursOv'), page.input_value('#milesOv'), page.is_disabled('#todaySave')), (0, '', '', True))
          ds = days_of(page)
          # 20 gross, 30 mi at 50 cents = 15.00 car, net 5.00 over 2.5 h = 2.00 an hour
          eq('one saved day', [(d['date'], d['hour'], d['sub'], d['buttons']) for d in ds],
             [('Fri, Oct 2', '$2.00 an hour', '2 offers, $20.00 gross, 2 h 30 min, 30 mi. Net $5.00.', ['Copy', 'Delete'])])
          sd = stored(page)['days']
          eq('stored day', sd, [dict(id='d3', date='2026-10-02', orders=2, gross=20, miles=30, hours=2.5, net=5)])
          eq('stored log is empty and the counter moved on', (stored(page)['entries'], stored(page)['seq'], stored(page)['hoursOv'], stored(page)['logDate']), ([], 3, 0, ''))
          eq('week shows the saved day', (txt(page, '#wHour'), txt(page, '#wNet'), txt(page, '#wTitle')), ('$2.00', '$5.00', 'Last 7 days, Sep 26 to Oct 2'))
          eq('week sub line', txt(page, '#wSub'), '1 saved day, 2 offers, 2 h 30 min, 30 mi, 10% of your hourly goal.')
          eq('week receipt', stub(page, '#wStub'), [['Gross pay', '$20.00'], ['Car cost (30 mi, as saved)', '-$15.00'], ['Net', '$5.00'], ['Net per mile', '$0.17'],
                                                    ['Set aside for taxes (20%)', '-$1.00'], ['You keep', '$4.00'], ['Mileage value at the IRS rate', '$22.80']])
          eq('week note', txt(page, '#wNote'), 'Mileage value adds each day at the IRS rate for its date. An estimate, not tax advice.')
          eq('week copy enabled', page.is_disabled('#weekCopy'), False)
          open_all(page)
          tap(page, '#know')
          put(page, '#gasPrice', '9')
          eq('changing the car leaves the saved net alone', (txt(page, '#wNet'), days_of(page)[0]['sub']), ('$5.00', '2 offers, $20.00 gross, 2 h 30 min, 30 mi. Net $5.00.'))
          ctx17.close()

          # save under another date, newest first, week window
          ents = [mk_entry(1, 10, 4, 25)]
          days0 = [mk_day(1, '2026-10-02', 3, 30, 12, 2, 20), mk_day(2, '2026-09-20', 1, 10, 4, 1, 8)]
          ctx18, page = new_page(browser, pre_state=base_state(entries=ents, seq=2, days=days0))
          put(page, '#logDate', '2026-09-28')
          eq('save button names the date', (txt(page, '#todaySave'), txt(page, '#todayHint')), ('Save as Sep 28', 'Mon, Sep 28'))
          tap(page, '#todaySave')
          eq('toast names the date', toast(page), 'Saved Mon, Sep 28.')
          eq('days stay newest first', [d['date'] for d in days_of(page)], ['Fri, Oct 2', 'Mon, Sep 28', 'Sun, Sep 20'])
          eq('the date field goes back to today after saving', (page.input_value('#logDate'), txt(page, '#todaySave')), ('2026-10-02', 'Save today'))
          eq('stored order', [d['date'] for d in stored(page)['days']], ['2026-10-02', '2026-09-28', '2026-09-20'])
          eq('week counts the day inside the window and not the one outside', (txt(page, '#wSub').split(',')[0]), '2 saved days')
          # a blank or broken date falls back to today
          add_by_hand(page, '9', '3', '15')
          put(page, '#logDate', '')
          eq('blank date means today', txt(page, '#todaySave'), 'Save today')
          tap(page, '#todaySave')
          eq('saved under today', [d['date'] for d in stored(page)['days']], ['2026-10-02', '2026-10-02', '2026-09-28', '2026-09-20'])
          eq('two saves on one day stay as two rows', len(days_of(page)), 4)
          ctx18.close()

          # the list keeps the latest 60 days
          import datetime
          d0 = datetime.date(2026, 10, 2)
          sixty = [mk_day(i + 1, (d0 - datetime.timedelta(days=i + 1)).isoformat(), 1, 10, 5, 1, 7) for i in range(60)]
          ctx19, page = new_page(browser, pre_state=base_state(entries=[mk_entry(1, 10, 4, 25)], seq=61, days=sixty))
          eq('60 days are listed', len(days_of(page)), 60)
          tap(page, '#todaySave')
          ds = stored(page)['days']
          eq('a 61st day pushes the oldest out', (len(ds), ds[0]['date'], ds[-1]['date']), (60, '2026-10-02', '2026-08-04'))
          eq('list shows 60', len(days_of(page)), 60)
          add_by_hand(page, '9', '3', '15')
          put(page, '#logDate', '2026-06-01')
          tap(page, '#todaySave')
          eq('a day older than all 60 is refused with a reason', toast(page), 'Your list keeps the latest 60 days, and that day is older than all of them. Pick a newer date.')
          eq('and nothing is lost', (len(entries_of(page)), len(stored(page)['days']), stored(page)['days'][-1]['date']), (1, 60, '2026-08-04'))
          eq('the counter does not move on a refused save', stored(page)['seq'], 63)
          put(page, '#logDate', '2026-08-06')
          tap(page, '#todaySave')
          eq('a date inside the 60 is accepted and the oldest drops', (len(stored(page)['days']), stored(page)['days'][-1]['date'], len(entries_of(page))), (60, '2026-08-05', 0))
          eq('60 days hint on the header', txt(page, '#h-days + .hint'), 'Your latest 60 days')
          ctx19.close()

    if on('ui'):
      with section('week totals and copy texts'):
          # window for today 2026-10-02 is Sep 26 to Oct 2
          days = [mk_day(1, '2026-10-03', 9, 90, 50, 5, 60), mk_day(2, '2026-10-02', 3, 41.5, 18.2, 2.25, 30.25), mk_day(3, '2026-10-01', 4, 55, 22, 3, 38),
                  mk_day(4, '2026-09-27', 2, 20, 9, 1.5, 15.5), mk_day(5, '2026-09-26', 5, 60, 31.5, 4, 40.25), mk_day(6, '2026-09-25', 7, 80, 40, 5, 50),
                  mk_day(7, '2025-12-30', 2, 20, 8, 1, 12)]
          ctx20, page = new_page(browser, pre_state=base_state(days=days, seq=7), stub=STUB_OK)
          w = ref_week(days, '2026-10-02', 20)
          eq('four of the seven days are inside the window', w['n'], 4)
          eq('week reading', (txt(page, '#wHour'), txt(page, '#wNet'), txt(page, '#wTitle')), (usd(float(w['nph'])), usd(float(w['net'])), 'Last 7 days, Sep 26 to Oct 2'))
          eq('week sub line', txt(page, '#wSub'),
             '4 saved days, 14 offers, %s, %s mi, %s of your hourly goal.' % (hm_text(w['hours']), fmt_num(w['miles'], 1), pct_text(w['nph'] / 20)))
          rows = stub(page, '#wStub')
          eq('week rows', [r[0] for r in rows], ['Gross pay', 'Car cost (%s mi, as saved)' % fmt_num(w['miles'], 1), 'Net', 'Net per mile', 'Set aside for taxes (20%)', 'You keep', 'Mileage value at the IRS rate'])
          for (lab, v), want in zip(rows, (w['gross'], -w['carCost'], w['net'], w['npm'], -w['setAside'], w['takeHome'], w['deduction'])):
              eq('week row %s' % lab, money_match(v, want), True)
          eq('the mileage value is miles at the rate of each day', money_match(rows[-1][1], sum(F(d['miles']) for d in days[1:5]) * Fraction(76, 100)), True)
          eq('days list shows all seven, newest first', [d['date'] for d in days_of(page)],
             ['Sat, Oct 3', 'Fri, Oct 2', 'Thu, Oct 1', 'Sun, Sep 27', 'Sat, Sep 26', 'Fri, Sep 25', 'Tue, Dec 30, 2025'])
          eq('a day from another year shows its year', days_of(page)[-1]['date'], 'Tue, Dec 30, 2025')
          tap(page, '#weekCopy')
          want = '\n'.join([
              'Drive Rate, last 7 days (Sep 26 to Oct 2)',
              '14 offers, %s gross over %s and %s mi' % (usd(float(w['gross'])), hm_text(w['hours']), fmt_num(w['miles'], 1)),
              'Car cost: %s' % usd(-float(w['carCost'])),
              'Net: %s (%s/hr, %s/mi)' % (usd(float(w['net'])), usd(float(w['nph'])), usd(float(w['npm']))),
              'Set aside for taxes: %s (20%%). You keep %s' % (usd(float(w['setAside'])), usd(float(w['takeHome']))),
              'Mileage value at the IRS rate: %s (an estimate, not tax advice)' % usd(float(w['deduction'])),
              'Checked with Drive Rate.'])
          page.wait_for_timeout(100)
          eq('week copy text', page.evaluate('window.__copied'), want)
          eq('week copy toast', toast(page), 'Week copied.')
          # copy one day: dated with the year, mileage at that day's own rate
          tap(page, '#dayList .day:nth-child(2) .row-actions button:nth-child(1)')
          page.wait_for_timeout(100)
          d2 = days[1]
          want = '\n'.join([
              'Drive Rate day, Fri, Oct 2, 2026',
              '3 offers, $41.50 gross over 2 h 15 min and 18.2 mi',
              'Car cost: %s' % usd(-(41.5 - 30.25)),
              'Net: $30.25 ($13.44/hr, $1.66/mi)',
              'Set aside for taxes: $6.05 (20%). You keep $24.20',
              'Mileage value at the IRS rate: %s (an estimate, not tax advice)' % usd(18.2 * 0.76),
              'Checked with Drive Rate.'])
          eq('day copy text', page.evaluate('window.__copied'), want)
          eq('day copy toast', toast(page), 'Day copied.')
          # a day from before July is valued at 72.5 cents
          ctx20.close()
          ctx20b, page = new_page(browser, pre_state=base_state(days=[mk_day(1, '2026-03-10', 2, 20, 10, 1, 12.5)], seq=1))
          tap(page, '#dayList .day .row-actions button:nth-child(1)')
          page.wait_for_timeout(100)
          has('an early-2026 day is valued at 72.5 cents', page.evaluate('window.__copied'), 'Mileage value at the IRS rate: $7.25 (an estimate, not tax advice)')
          eq('an early-2026 day lists with no year, being this year', days_of(page)[0]['date'], 'Tue, Mar 10')
          ctx20b.close()

    if on('ui'):
      with section('days: delete, copy and the empty week'):
          days = [mk_day(1, '2026-10-02', 3, 41.5, 18.2, 2.25, 30.25), mk_day(2, '2026-10-01', 4, 55, 22, 3, 38)]
          ctx21, page = new_page(browser, pre_state=base_state(days=days, seq=2))
          tap(page, '#dayList .day:nth-child(1) .row-actions button:nth-child(2)')
          eq('first tap on Delete only asks', (days_of(page)[0]['buttons'], len(days_of(page))), (['Copy', 'Tap again to delete'], 2))
          tap(page, '#dayList .day:nth-child(1) .row-actions button:nth-child(2)')
          eq('second tap deletes the day', ([d['date'] for d in days_of(page)], toast(page)), (['Thu, Oct 1'], 'Day deleted.'))
          eq('the week follows', txt(page, '#wSub').startswith('1 saved day, 4 offers'), True)
          eq('stored days follow', [d['id'] for d in stored(page)['days']], ['d2'])
          eq('focus stays in the list', page.evaluate("document.activeElement.closest('#dayList') !== null"), True)
          tap(page, '#dayList .day .row-actions button:nth-child(2)')
          tap(page, '#dayList .day .row-actions button:nth-child(2)')
          eq('list empty again', (txt(page, '#dayList'), txt(page, '#wSub'), txt(page, '#wHour'), page.is_disabled('#weekCopy')), ('No saved days yet. Tap Save today when your shift is over.', 'No saved days in the last 7 days.', '-', True))
          eq('focus moves to the Days heading when no day is left', page.evaluate('document.activeElement.id'), 'h-days')
          ctx21.close()
          # no hours saved
          ctx21b, page = new_page(browser, pre_state=base_state(days=[mk_day(1, '2026-10-02', 1, 10, 4, 0, 8)], seq=1))
          eq('a day with no hours says so and the week shows a dash', (days_of(page)[0]['hour'], txt(page, '#wHour'), txt(page, '#wNet')), ('No hours', '-', '$8.00'))
          ctx21b.close()
          # a losing week has no set-aside rows
          ctx21c, page = new_page(browser, pre_state=base_state(days=[mk_day(1, '2026-10-02', 1, 10, 40, 2, -9.5)], seq=1))
          eq('a losing week shows a negative net and no set-aside', ([r[0] for r in stub(page, '#wStub')], txt(page, '#wNet'), txt(page, '#wHour')),
             (['Gross pay', 'Car cost (40 mi, as saved)', 'Net', 'Net per mile', 'Mileage value at the IRS rate'], '-$9.50', '-$4.75'))
          ctx21c.close()

    if on('ui'):
      with section('midnight and the date'):
          ctx22, page = new_page(browser, now='2026-10-02T23:59:50')
          tap(page, '#logBtn')
          eq('before midnight', (txt(page, '#todayHint'), txt(page, '#wTitle'), page.input_value('#logDate'), txt(page, '#todaySave')),
             ('Fri, Oct 2', 'Last 7 days, Sep 26 to Oct 2', '2026-10-02', 'Save today'))
          page.evaluate("window.__setNow('2026-10-03T00:00:10')")
          page.evaluate("window.dispatchEvent(new Event('focus'))")
          eq('after midnight, on return to the page', (txt(page, '#todayHint'), txt(page, '#wTitle'), page.input_value('#logDate'), txt(page, '#todaySave')),
             ('Sat, Oct 3', 'Last 7 days, Sep 27 to Oct 3', '2026-10-03', 'Save today'))
          eq('the log stays', len(entries_of(page)), 1)
          page.evaluate("window.__setNow('2026-10-04T08:00:00')")
          page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
          eq('after the tab becomes visible', (txt(page, '#todayHint'), txt(page, '#wTitle')), ('Sun, Oct 4', 'Last 7 days, Sep 28 to Oct 4'))
          tap(page, '#todaySave')
          eq('saved under the new date', [d['date'] for d in stored(page)['days']], ['2026-10-04'])
          page.evaluate("window.__setNow('2026-10-10T08:00:00')")
          page.evaluate("window.dispatchEvent(new Event('focus'))")
          eq('six days later the saved day is still in the week', txt(page, '#wSub').startswith('1 saved day'), True)
          page.evaluate("window.__setNow('2026-10-11T08:00:00')")
          page.evaluate("window.dispatchEvent(new Event('focus'))")
          eq('seven days later it drops out', (txt(page, '#wSub'), txt(page, '#wTitle')), ('No saved days in the last 7 days.', 'Last 7 days, Oct 5 to Oct 11'))
          eq('but it stays in the list', len(days_of(page)), 1)
          ctx22.close()
          # a date the person chose does not move at midnight
          ctx23, page = new_page(browser, now='2026-10-02T23:59:50')
          tap(page, '#logBtn')
          put(page, '#logDate', '2026-09-28')
          page.evaluate("window.__setNow('2026-10-03T00:00:10')")
          page.evaluate("window.dispatchEvent(new Event('focus'))")
          eq('a chosen date stays put', (page.input_value('#logDate'), txt(page, '#todaySave')), ('2026-09-28', 'Save as Sep 28'))
          ctx23.close()
          # the timer notices midnight by itself, without any event
          ctx24, page = new_page(browser, now='2026-10-02T23:59:50')
          page.evaluate("window.__setNow('2026-10-03T00:00:10')")
          page.wait_for_timeout(31000)
          eq('the 30 second check moves the date on its own', txt(page, '#wTitle'), 'Last 7 days, Sep 27 to Oct 3')
          ctx24.close()
          # a different year: the day shows its year
          ctx25, page = new_page(browser, now='2027-01-01T08:00:00', pre_state=base_state(days=[mk_day(1, '2026-12-31', 2, 20, 10, 1, 12.5)], seq=1))
          eq('on New Year the last day of last year is still in the week and shows its year', (days_of(page)[0]['date'], txt(page, '#wSub').startswith('1 saved day')), ('Thu, Dec 31, 2026', True))
          eq('the week crosses the year', txt(page, '#wTitle'), 'Last 7 days, Dec 26 to Jan 1')
          ctx25.close()

    if on('ui'):
      with section('by app'):
          ctx26, page = new_page(browser)
          eq('hidden with no entries', page.is_visible('#appWrap'), False)
          add_by_hand(page, '9', '3', '10', app='DoorDash')
          eq('hidden with one app', page.is_visible('#appWrap'), False)
          add_by_hand(page, '9', '4', '20', app='Uber Eats')
          add_by_hand(page, '6', '2', '15', app='')
          add_by_hand(page, '10', '3', '10', app='DoorDash')
          rows = page.evaluate("[...document.querySelectorAll('#appBody tr')].map(r => [...r.children].map(c => c.textContent.trim()))")
          ref_rows, lab = ref_byapp([dict(pay=9, min=10, app='DoorDash'), dict(pay=9, min=20, app='Uber Eats'), dict(pay=6, min=15, app=''), dict(pay=10, min=10, app='DoorDash')])
          eq('two apps: the table shows up', page.is_visible('#appWrap'), True)
          eq('by-app rows', rows, [[r['app'] or 'No app', str(r['n']), usd(float(r['gross'])), usd(float(r['perHour'])) if r['perHour'] is not None else '-'] for r in ref_rows])
          eq('by-app rows by hand', rows, [['DoorDash', '2', '$19.00', '$57.00'], ['Uber Eats', '1', '$9.00', '$27.00'], ['No app', '1', '$6.00', '$24.00']])
          eq('table has headers', page.evaluate("[...document.querySelectorAll('#appWrap thead th')].map(t => t.textContent.trim())"), ['App', 'Offers', 'Gross', 'Per hour'])
          eq('table has a caption for screen readers', txt(page, '#appWrap caption'), "Today's pay by app")
          tap(page, '#entryList .entry:nth-child(1) .row-actions button:nth-child(2)')
          tap(page, '#entryList .entry:nth-child(1) .row-actions button:nth-child(2)')
          eq('still two apps after one delete', page.is_visible('#appWrap'), True)
          tap(page, '#clearLogBtn')
          tap(page, '#clearLogBtn')
          eq('hidden again once the log is cleared', page.is_visible('#appWrap'), False)
          ctx26.close()

    if on('ui'):
      with section('entry limit'):
          many = [mk_entry(i + 1, 5, 2, 10) for i in range(200)]
          ctx27, page = new_page(browser, pre_state=base_state(entries=many, seq=200))
          eq('200 entries load', len(entries_of(page)), 200)
          add_by_hand(page, '9', '3', '15')
          eq('the 201st is refused by hand', (toast(page), len(entries_of(page))), ('You can log 200 offers in a day. Save the day first.', 200))
          put(page, '#pay', '9')
          put(page, '#miles', '3')
          put(page, '#minutes', '15')
          tap(page, '#logBtn')
          eq('and by the log button, keeping the offer typed', (toast(page), len(entries_of(page)), page.input_value('#pay')), ('You can log 200 offers in a day. Save the day first.', 200, '9.00'))
          tap(page, '#todaySave')
          eq('saving makes room', (len(entries_of(page)), len(stored(page)['days']), stored(page)['days'][0]['orders']), (0, 1, 200))
          ctx27.close()

    # ============================================================ what is kept, and copying
    STATE_KEYS = sorted('v example pay tip miles minutes wait retMiles retMin app fuel gasPrice mpg kwhPrice mikwh maint depr carOther know cpm goalHour goalMile taxPct hoursOv milesOv logDate seq entries days'.split())

    if on('ui'):
      with section('persistence: round trip'):
          ctx30, page = new_page(browser)
          open_all(page)
          eq('nothing is written before the person changes something', stored(page), None)
          put(page, '#pay', '7.25')
          put(page, '#miles', '3.5')
          put(page, '#minutes', '18')
          tap(page, '#tipChips button:nth-child(3)')
          put(page, '#goalHour', '22.5')
          put(page, '#taxPct', '25')
          tap(page, '#fuelChips button:nth-child(2)')
          put(page, '#kwhPrice', '0.21')
          put(page, '#mikwh', '3.5')
          page.select_option('#app', 'Grubhub')
          page.wait_for_timeout(450)
          st = stored(page)
          eq('stored keys', sorted(st.keys()), STATE_KEYS)
          eq('stored values', (st['v'], st['example'], st['pay'], st['tip'], st['miles'], st['minutes'], st['goalHour'], st['taxPct'], st['fuel'], st['kwhPrice'], st['mikwh'], st['app']),
             (1, False, 7.25, 2, 3.5, 18, 22.5, 25, 'electric', 0.21, 3.5, 'Grubhub'))
          page.reload()
          page.wait_for_timeout(300)
          o = dict(EX, pay=7.25, tip=2, miles=3.5, minutes=18, goalHour=22.5, taxPct=25)
          car = dict(CAR0, fuel='electric', kwhPrice=0.21, mikwh=3.5)
          eq('everything comes back after a reload', verify_offer(page, o, car), [])
          eq('inputs come back', {i: page.input_value('#' + i) for i in ('pay', 'tip', 'miles', 'minutes', 'wait', 'retMiles', 'retMin', 'goalHour', 'goalMile', 'taxPct', 'kwhPrice', 'mikwh', 'app')},
             {'pay': '7.25', 'tip': '2.00', 'miles': '3.5', 'minutes': '18', 'wait': '5', 'retMiles': '1.5', 'retMin': '4', 'goalHour': '22.50', 'goalMile': '1.50', 'taxPct': '25',
              'kwhPrice': '0.21', 'mikwh': '3.5', 'app': 'Grubhub'})
          eq('chips come back', (pressed(page, 'tipChips'), pressed(page, 'fuelChips'), page.evaluate("document.getElementById('elecFields').hidden")), (['$2'], ['Electric'], False))
          eq('the example note stays gone', page.is_visible('#exampleNote'), False)
          # log, add and save a day, then reload
          tap(page, '#logBtn')
          add_by_hand(page, '12', '5', '30', app='Lyft')
          tap(page, '#todaySave')
          page.reload()
          page.wait_for_timeout(300)
          eq('the saved day comes back with both offers', [(d['date'], d['sub'].startswith('2 offers')) for d in days_of(page)], [('Fri, Oct 2', True)])
          eq('the log is empty after a saved day and a reload', len(entries_of(page)), 0)
          add_by_hand(page, '9', '3', '15')
          page.reload()
          page.wait_for_timeout(300)
          eq('a logged entry comes back', [(e['pay'], e['sub']) for e in entries_of(page)], [('$9.00', '3 mi, 15 min')])
          eq('storage holds the day and the entry', (len(stored(page)['days']), len(stored(page)['entries'])), (1, 1))
          # the page writes what it holds as soon as it is hidden, without waiting for the pause
          r = page.evaluate("""() => {
              const el = document.getElementById('pay'); el.value = '11'; el.dispatchEvent(new Event('input', {bubbles: true}));
              const before = JSON.parse(localStorage.getItem('drive-rate-v1')).pay;
              window.dispatchEvent(new Event('pagehide'));
              const after = JSON.parse(localStorage.getItem('drive-rate-v1')).pay;
              return [before, after]; }""")
          eq('typing waits a moment, leaving the page writes at once', r, [0, 11])
          ctx30.close()

    if on('ui'):
      with section('persistence: corrupt and foreign storage'):
          for label, raw, example in (('not json', '{not json', True), ('an array', '[]', True), ('null', 'null', True), ('a string', '"text"', True),
                                      ('a number', '42', True), ('a newer version', '{"v":2,"pay":5}', True), ('empty text', '', True),
                                      ('a bare version', '{"v":1}', False), ('half an object', '{"v":1,"pay":', True)):
              cx, pg = new_page(browser, raw_state=raw)
              eq('%s: the page starts' % label, (pg.is_visible('#exampleNote'), txt(pg, '#vWord')), (example, 'Pass'))
              eq('%s: the example numbers show' % label, verify_offer(pg, EX, CAR0), [])
              put(pg, '#pay', '9')
              eq('%s: typing works' % label, verify_offer(pg, dict(EX, pay=9), CAR0), [])
              pg.wait_for_timeout(350)
              eq('%s: the next save replaces it' % label, (stored(pg) or {}).get('pay'), 9)
              cx.close()

    if on('ui'):
      with section('persistence: hostile storage'):
          hostile = dict(v=1, example='yes', pay='abc', tip=-5, miles='@INF@', minutes=5e7, wait=None, retMiles=[1], retMin={'a': 1}, app='<img src=x onerror=window.__pwned=1>',
                         fuel='rocket', gasPrice='1,5', mpg=0, kwhPrice=True, mikwh='9' * 30, maint=-1, depr='0x10', carOther='@INF@', know='true', cpm=1e9,
                         goalHour=1e12, goalMile='-3', taxPct=99, hoursOv=5000, milesOv=1e9, logDate='2026-13-45', seq=-5,
                         entries=[dict(id=1, pay='9', miles=-2, min='x', ret=None, app='<b>', note='<script>window.__pwned=1</script>' + 'n' * 100),
                                  None, 5, 'str', dict(id=None, pay=5), dict(pay=5), dict(id='e5', pay=4, miles=2, min=10, ret=0, app='Lyft', note='ok'),
                                  dict(id='e6', pay=1e30, miles=1e30, min=1e30, ret=1e30, app=7, note=123)],
                         days=[dict(id='d1', date='2026-02-30', orders=1, gross=1, miles=1, hours=1, net=1), dict(id='d2', date='<b>', orders=1),
                               dict(id='d3', date='2026-10-01', orders='3', gross='abc', miles=1e9, hours=-1, net='x'), 'str', None, dict(date=20261001)])
          raw = json.dumps(hostile).replace('"@INF@"', '1e999')
          cx, pg = new_page(browser, raw_state=raw)
          eq('hostile: no script ran', pg.evaluate('window.__pwned === undefined && document.querySelectorAll("script").length'), 1)
          eq('hostile: no injected elements in the lists', pg.evaluate("document.querySelectorAll('#entryList b, #entryList script, #entryList img, #dayList b, #dayList img').length"), 0)
          ents = entries_of(pg)
          eq('hostile: only entries with an id are kept', [e['id'] for e in ents], ['e6', 'e5', '1'])
          eq('hostile: first entry shows as plain text, cleaned', (ents[2]['app'], ents[2]['pay'], ents[2]['sub'], ents[2]['note']),
             ('Offer', '$9.00', '0 mi, 0 h', ('<script>window.__pwned=1</script>' + 'n' * 100)[:80]))
          eq('hostile: huge entry values are held at the limits', (ents[0]['pay'], ents[0]['sub']), ('$10,000,000.00', '100,000 mi and 100,000 mi back, 1,666 h 40 min'))
          eq('hostile: a number as a note is kept as text', ents[0]['note'], '123')
          eq('hostile: the one good entry is intact', (ents[1]['app'], ents[1]['pay'], ents[1]['sub'], ents[1]['note']), ('Lyft', '$4.00', '2 mi, 10 min', 'ok'))
          eq('hostile: only the real day is kept', [(d['date'], d['hour']) for d in days_of(pg)], [('Thu, Oct 1', 'No hours')])
          eq('hostile: that day is cleaned', days_of(pg)[0]['sub'], '3 offers, $0.00 gross, 0 h, 100,000 mi. Net $0.00.')
          o = dict(pay=6.5, tip=0, miles=4.2, minutes=100000, wait=5, retMiles=1, retMin=4, goalHour=1e7, goalMile=0, taxPct=60)
          car = dict(fuel='gas', gasPrice=1.5, mpg=0, kwhPrice=0.17, mikwh=1000, maint=0, depr=0, carOther=0, know=False, cpm=1000)
          eq('hostile: numbers fall back or are held at their limits', verify_offer(pg, o, car), [])
          eq('hostile: the example flag is not trusted', pg.is_visible('#exampleNote'), False)
          eq('hostile: the date field is blank-safe', pg.input_value('#logDate'), '2026-10-02')
          eq('hostile: the page is still usable', (pg.is_disabled('#todaySave'), pg.is_disabled('#logBtn')), (False, False))
          pg.evaluate("document.getElementById('app').value = 'Lyft'")
          eq('hostile: the app list is safe', pg.input_value('#app'), 'Lyft')
          cx.close()
          # more entries and days than the page keeps
          many_e = [dict(id='e%d' % (1000 + i), pay=5, miles=2, min=10, ret=0, app='', note='') for i in range(300)]
          d0 = datetime.date(2026, 10, 2)
          many_d = [dict(id='d%d' % (2000 + i), date=(d0 - datetime.timedelta(days=(i * 7) % 400)).isoformat(), orders=1, gross=10, miles=5, hours=1, net=7) for i in range(100)]
          cx, pg = new_page(browser, pre_state=base_state(entries=many_e, days=many_d, seq=0))
          eq('300 stored entries show 200', len(entries_of(pg)), 200)
          ds = days_of(pg)
          eq('100 stored days show 60, newest first', len(ds), 60)
          exp_dates = sorted([(d0 - datetime.timedelta(days=(i * 7) % 400)).isoformat() for i in range(100)], reverse=True)[:60]
          eq('the newest 60 are kept, in date order', [d['date'] for d in ds], [day_text_date(x, year=not x.startswith('2026')) for x in exp_dates])
          add_by_hand(pg, '9', '3', '15')
          eq('the 200 entries are full', toast(pg), 'You can log 200 offers in a day. Save the day first.')
          cx.close()
          # ids never collide with stored ones
          cx, pg = new_page(browser, pre_state=base_state(entries=[mk_entry(5, 8, 3, 20), mk_entry(9, 12, 5, 30)], days=[mk_day(12, '2026-10-01', 2, 20, 8, 1, 14)], seq=0))
          add_by_hand(pg, '9', '3', '15')
          eq('the next id is above every stored id', [e['id'] for e in stored(pg)['entries']], ['e5', 'e9', 'e13'])
          tap(pg, '#todaySave')
          eq('and so is the next day id', [d['id'] for d in stored(pg)['days']], ['d14', 'd12'])
          cx.close()

    if on('ui'):
      with section('storage unavailable'):
          cx, pg = new_page(browser, stub=STUB_NO_STORAGE)
          eq('a warning explains that nothing will be kept', (pg.is_visible('#storeWarn'), 'will be gone when you close it' in txt(pg, '#storeWarn')), (True, True))
          eq('the example still shows', verify_offer(pg, EX, CAR0), [])
          put(pg, '#pay', '9')
          eq('typing works without storage', verify_offer(pg, dict(EX, pay=9), CAR0), [])
          tap(pg, '#logBtn')
          add_by_hand(pg, '12', '5', '30', app='Lyft')
          eq('the log works in memory', len(entries_of(pg)), 2)
          tap(pg, '#todaySave')
          eq('saving a day works in memory', (len(days_of(pg)), len(entries_of(pg))), (1, 0))
          tap(pg, '#copyBtn')
          cx.close()
          # only writing is blocked (a full disk or a strict mode): the saved state still loads
          quota = ("try { localStorage.setItem('%s', %s); } catch (e) {} Storage.prototype.setItem = function () { throw new Error('quota'); };" %
                   (STORE, json.dumps(json.dumps(base_state(entries=[mk_entry(1, 8, 3, 20)], seq=1)))))
          cx, pg = new_page(browser, stub=STUB_OK + quota)
          eq('saved state loads even though writing fails', (len(entries_of(pg)), pg.is_visible('#storeWarn')), (1, True))
          cx.close()
          # only reading is blocked
          cx, pg = new_page(browser, stub=STUB_OK + "Storage.prototype.getItem = function () { throw new Error('blocked'); };")
          eq('a blocked read falls back to the example', (pg.is_visible('#exampleNote'), pg.is_visible('#storeWarn')), (True, False))
          cx.close()

    # ---- copying
    COPY_CASES = [
        ('the example', dict(EX), CAR0, '', ['Offer: $6.50 for 5.7 mi / 31 min -> $8.88/hr net, $1.14/mi gross. Pass.',
                                            'Net $4.59 after a $1.91 car cost at $0.335 a mile (5 min waiting, 1.5 mi and 4 min back).',
                                            'Pay needed to meet my goals: $12.25.', 'Checked with Drive Rate.']),
        ('an app and a tip', dict(EX, pay=8, tip=2, miles=5.3, minutes=31, wait=0, retMiles=0, retMin=0), dict(CAR0, know=True, cpm=0.5), 'DoorDash',
         ['DoorDash offer: $10.00 for 5.3 mi / 31 min -> $14.23/hr net, $1.89/mi gross. Pass.', 'Net $7.35 after a $2.65 car cost at $0.50 a mile (includes a $2.00 tip).',
          'Pay needed to meet my goals: $12.99.', 'Checked with Drive Rate.']),
        ('a take', dict(EX, pay=25, tip=0, miles=10, minutes=60, wait=0, retMiles=0, retMin=0), dict(CAR0, know=True, cpm=0.5), '',
         ['Offer: $25.00 for 10 mi / 60 min -> $20.00/hr net, $2.50/mi gross. Take it.', 'Net $20.00 after a $5.00 car cost at $0.50 a mile.',
          'Pay needed to meet my goals: $25.00.', 'Checked with Drive Rate.']),
        ('a borderline', dict(EX, pay=24.99, tip=0, miles=10, minutes=60, wait=0, retMiles=0, retMin=0), dict(CAR0, know=True, cpm=0.5), 'Uber Eats',
         ['Uber Eats offer: $24.99 for 10 mi / 60 min -> $19.99/hr net, $2.50/mi gross. Borderline.', 'Net $19.99 after a $5.00 car cost at $0.50 a mile.',
          'Pay needed to meet my goals: $25.00.', 'Checked with Drive Rate.']),
        ('no goals', dict(EX, pay=25, tip=0, miles=10, minutes=60, wait=0, retMiles=0, retMin=0, goalHour=0, goalMile=0), dict(CAR0, know=True, cpm=0.5), '',
         ['Offer: $25.00 for 10 mi / 60 min -> $20.00/hr net, $2.50/mi gross.', 'Net $20.00 after a $5.00 car cost at $0.50 a mile.', 'Checked with Drive Rate.']),
        ('a loss', dict(EX, pay=3, tip=0, miles=10, minutes=60, wait=0, retMiles=0, retMin=0), dict(CAR0, know=True, cpm=0.5), 'Shipt',
         ['Shipt offer: $3.00 for 10 mi / 60 min -> -$2.00/hr net, $0.30/mi gross. Pass.', 'Net -$2.00 after a $5.00 car cost at $0.50 a mile.',
          'Pay needed to meet my goals: $25.00.', 'Checked with Drive Rate.']),
    ]
    if on('ui'):
      with section('copy: the offer text'):
          for label, o, car, app, lines in COPY_CASES:
              cx, pg = new_page(browser)
              open_all(pg)
              set_state(pg, o, car)
              if app:
                  pg.select_option('#app', app)
              tap(pg, '#copyBtn')
              pg.wait_for_timeout(100)
              eq('offer text for %s' % label, pg.evaluate('window.__copied'), '\n'.join(lines))
              eq('toast for %s' % label, toast(pg), 'Offer copied.')
              eq('no dash look-alikes in the text for %s' % label, [c for c in DASHES if c in (pg.evaluate('window.__copied') or '')], [])
              cx.close()
          cx, pg = new_page(browser)
          tap(pg, '#exampleClear')
          eq('copy is disabled with no offer', pg.is_disabled('#copyBtn'), True)
          cx.close()

    if on('ui'):
      with section('copy: today, and the address'):
          ents = [mk_entry(1, 8, 4, 20, 1), mk_entry(2, 12, 5, 30)]
          cx, pg = new_page(browser, pre_state=base_state(entries=ents, seq=2, know=True, cpm=0.5))
          tap(pg, '#todayCopy')
          pg.wait_for_timeout(100)
          eq('today text', pg.evaluate('window.__copied'), '\n'.join([
              'Drive Rate day, Fri, Oct 2, 2026', '2 offers, $20.00 gross over 50 min and 10 mi', 'Car cost: -$5.00', 'Net: $15.00 ($18.00/hr, $1.50/mi)',
              'Set aside for taxes: $3.00 (20%). You keep $12.00', 'Mileage value at the IRS rate: $7.60 (an estimate, not tax advice)', 'Checked with Drive Rate.']))
          eq('today toast', toast(pg), 'Summary copied.')
          put(pg, '#logDate', '2026-03-10')
          tap(pg, '#todayCopy')
          pg.wait_for_timeout(100)
          has('a day dated before July uses 72.5 cents', pg.evaluate('window.__copied'), 'Drive Rate day, Tue, Mar 10, 2026')
          has('and its mileage value', pg.evaluate('window.__copied'), 'Mileage value at the IRS rate: $7.25 (an estimate, not tax advice)')
          tap(pg, '.mail-copy')
          pg.wait_for_timeout(100)
          eq('the address copies', (pg.evaluate('window.__copied'), toast(pg)), (SUPPORT, 'Email address copied.'))
          cx.close()

    if on('ui'):
      with section('copy: the clipboard is refused or missing'):
          for label, stb in (('refused', STUB_REJECT), ('missing', STUB_NO_CLIP)):
              cx, pg = new_page(browser, stub=stb)
              tap(pg, '#copyBtn')
              pg.wait_for_timeout(150)
              want = '\n'.join(COPY_CASES[0][4])
              eq('%s: the copy sheet opens with the text' % label, (pg.is_visible('#sheet'), pg.input_value('#sheetText')), (True, want))
              eq('%s: the text is selected for the person to copy' % label, pg.evaluate("(() => { const t = document.getElementById('sheetText'); return [document.activeElement === t, t.selectionStart, t.selectionEnd, t.value.length]; })()"),
                 [True, 0, len(want), len(want)])
              eq('%s: no success toast' % label, pg.is_visible('#toast'), False)
              eq('%s: the sheet is a labelled dialog' % label, (pg.get_attribute('#sheet', 'role'), pg.get_attribute('#sheet', 'aria-label'), pg.get_attribute('#sheetText', 'aria-label')), ('dialog', 'Copy text', 'Text to copy'))
              tap(pg, '#sheetClose')
              eq('%s: Done closes it' % label, pg.is_visible('#sheet'), False)
              # the other copy buttons use the same way out
              tap(pg, '.mail-copy')
              pg.wait_for_timeout(150)
              eq('%s: the address falls back too' % label, (pg.is_visible('#sheet'), pg.input_value('#sheetText')), (True, SUPPORT))
              cx.close()
          # the old copy command works when the clipboard does not
          cx, pg = new_page(browser, stub="window.__copied = null; Object.defineProperty(navigator, 'clipboard', {configurable: true, value: undefined}); document.execCommand = function () { return true; };")
          tap(pg, '#copyBtn')
          pg.wait_for_timeout(100)
          eq('execCommand success: toast and no sheet', (toast(pg), pg.is_visible('#sheet')), ('Offer copied.', False))
          cx.close()
          # a clipboard that throws at once
          cx, pg = new_page(browser, stub="window.__copied = null; Object.defineProperty(navigator, 'clipboard', {configurable: true, value: {writeText: function () { throw new Error('nope'); }}}); document.execCommand = function () { return false; };")
          tap(pg, '#copyBtn')
          pg.wait_for_timeout(100)
          eq('a clipboard that throws falls back to the sheet', pg.is_visible('#sheet'), True)
          cx.close()

    if on('ui'):
      with section('screen reader summary'):
          cx, pg = new_page(browser)
          eq('the live region is a polite status', (pg.get_attribute('#srRead', 'role'), pg.get_attribute('#srRead', 'aria-live'), pg.get_attribute('#srRead', 'aria-atomic')), ('status', 'polite', 'true'))
          pg.wait_for_timeout(900)
          eq('example summary', txt(pg, '#srRead'),
             'Pass. Too low for your goals. Net per hour is at 44% of your $20.00 goal. Gross per mile is at 76% of your $1.50 goal. Net per hour $8.88, goal $20.00. '
             'Gross per mile $1.14, goal $1.50. Car cost $1.91, net $4.59. You keep $3.67 after setting aside 20 percent. Pay needed to meet your goals: $12.25.')
          r = pg.evaluate("""() => { const before = document.getElementById('srRead').textContent; const el = document.getElementById('pay');
              for (const v of ['2', '25', '25.', '25.0']) { el.value = v; el.dispatchEvent(new Event('input', {bubbles: true})); }
              return [before, document.getElementById('srRead').textContent]; }""")
          eq('a burst of typing does not announce every keystroke', r[0] == r[1], True)
          set_state(pg, dict(EX, pay=25, tip=0, miles=10, minutes=60, wait=0, retMiles=0, retMin=0), dict(CAR0, know=True, cpm=0.5))
          pg.wait_for_timeout(900)
          eq('take summary', txt(pg, '#srRead'),
             'Take it. Meets both of your goals. Net per hour $20.00, goal $20.00. Gross per mile $2.50, goal $1.50. Car cost $5.00, net $20.00. '
             'You keep $16.00 after setting aside 20 percent. Pay needed to meet your goals: $25.00.')
          set_state(pg, dict(EX, pay=3, tip=0, miles=10, minutes=60, wait=0, retMiles=0, retMin=0), dict(CAR0, know=True, cpm=0.5))
          pg.wait_for_timeout(900)
          eq('loss summary', txt(pg, '#srRead'),
             'Pass. You would lose $2.00 on this offer. The car costs more than it pays. Net per hour -$2.00, goal $20.00. Gross per mile $0.30, goal $1.50. '
             'Car cost $5.00, net -$2.00. Pay needed to meet your goals: $25.00.')
          tap(pg, '#clearBtn')
          pg.wait_for_timeout(900)
          eq('empty summary', txt(pg, '#srRead'), 'Add an offer. Type the pay, miles and minutes from the offer screen.')
          set_state(pg, dict(EX, pay=9, tip=0, miles=10, minutes=60, wait=0, retMiles=0, retMin=0, goalHour=0, goalMile=0), CAR0)
          pg.wait_for_timeout(900)
          has('no goals summary', txt(pg, '#srRead'), 'No goals set. Set a goal under My goals to get a verdict. The numbers below still count.')
          cx.close()

    # ============================================================ layout, colour, taps, keyboard
    WIDTHS = (320, 340, 360, 375, 390, 430, 600, 768, 899, 900, 1024, 1280, 1440, 1920)
    APP_NAMES = ['DoorDash', 'Uber Eats', 'Amazon Flex', 'Instacart', 'Other']
    BUSY = base_state(example=False, pay=14, tip=2.5, miles=5, minutes=20, wait=5, retMiles=1.5, retMin=4, app='Uber Eats', hoursOv=6.5, milesOv=64.2, seq=30,
                      entries=[mk_entry(i, 6.5 + i, 3.1 + i / 10, 14 + i, 1.2, APP_NAMES[i % 5], 'W' * 80 if i == 1 else ('Back of the mall' if i == 2 else '')) for i in range(1, 7)],
                      days=[mk_day(i, '2026-09-%02d' % (30 - i), 6 + i, 118.5 + i, 61.2, 6.5, 70.25 - i) for i in range(1, 9)])
    EXD = dict(OFFER0, **GOALS0)

    COLOR_JS = r'''
    const parse = c => { const m = /rgba?\(([^)]+)\)/.exec(c); if (!m) return null; const p = m[1].split(/[ ,\/]+/).filter(Boolean).map(parseFloat); return {r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1}; };
    const over = (f, b) => ({r: f.r * f.a + b.r * (1 - f.a), g: f.g * f.a + b.g * (1 - f.a), b: f.b * f.a + b.b * (1 - f.a), a: 1});
    const lin = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    const lum = c => 0.2126 * lin(c.r) + 0.7152 * lin(c.g) + 0.0722 * lin(c.b);
    const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
    const bgOf = el => { const layers = []; for (let e = el; e; e = e.parentElement) { const c = parse(getComputedStyle(e).backgroundColor); if (c && c.a > 0) { layers.push(c); if (c.a >= 1) break; } }
        let base = {r: 255, g: 255, b: 255, a: 1}; for (let i = layers.length - 1; i >= 0; i--) base = over(layers[i], base); return base; };
    const vis = e => e.getClientRects().length > 0;
    const round2 = x => Math.round(x * 100) / 100;
    '''
    TEXT_JS = '(sels) => {' + COLOR_JS + r'''
    const out = [];
    for (const sel of sels) {
      const els = [...document.querySelectorAll(sel)].filter(e => vis(e) && !e.disabled && ((e.textContent || '').trim() !== '' || ((e.tagName === 'INPUT' || e.tagName === 'TEXTAREA') && e.value !== '')));
      if (!els.length) { out.push([sel, null, 0, '']); continue; }
      let worst = null;
      for (const el of els) {
        const cs = getComputedStyle(el), bg = bgOf(el);
        let fg = parse(cs.color); if (fg.a < 1) fg = over(fg, bg);
        const r = ratio(fg, bg), px = parseFloat(cs.fontSize), wt = parseInt(cs.fontWeight, 10);
        const need = (px >= 24 || (px >= 18.66 && wt >= 700)) ? 3 : 4.5;
        if (worst === null || r - need < worst[1] - worst[2]) worst = [sel, round2(r), need, (el.textContent || el.value || '').trim().slice(0, 24)];
      }
      out.push(worst);
    }
    return out; }'''
    PAIR_JS = '(items) => {' + COLOR_JS + r'''
    return items.map(([name, sel, prop, bgSel]) => {
      const el = [...document.querySelectorAll(sel)].find(vis);
      if (!el) return [name, null];
      const bgEl = bgSel ? [...document.querySelectorAll(bgSel)].find(vis) : el.parentElement;
      const bg = bgOf(bgEl);
      let c = parse(getComputedStyle(el)[prop]); if (!c) return [name, null];
      if (c.a < 1) c = over(c, bg);
      return [name, round2(ratio(c, bg))];
    }); }'''
    PLACEHOLDER_JS = '() => {' + COLOR_JS + r'''
    return [...document.querySelectorAll('input, textarea')].filter(e => vis(e) && e.value === '' && e.placeholder).map(e => {
      const bg = bgOf(e); let c = parse(getComputedStyle(e, '::placeholder').color); if (c.a < 1) c = over(c, bg);
      return [e.id, round2(ratio(c, bg))]; }); }'''
    STOP_JS = '() => {' + COLOR_JS + r'''
    const e = document.activeElement;
    if (!e || e === document.body) return ['body', false, 0];
    let best = null;
    for (const el of [e, e.closest('.affix')].filter(Boolean)) {
      const cs = getComputedStyle(el);
      if (cs.outlineStyle === 'none' || !(parseFloat(cs.outlineWidth) > 0)) continue;
      const bg = bgOf(el.parentElement || el); let c = parse(cs.outlineColor); if (c.a < 1) c = over(c, bg);
      const r = ratio(c, bg); if (best === null || r > best) best = r;
    }
    const label = e.id || (e.tagName === 'SUMMARY' ? 'summary' : e.tagName === 'BUTTON' ? 'button.' + e.className : e.tagName.toLowerCase());
    return [label, best !== null, best === null ? 0 : round2(best)]; }'''
    CLIP_JS = r'''() => [...document.querySelectorAll('#dash *, #bar *, #todayDash *, #weekDash *')]
        .filter(e => e.getClientRects().length && e.clientWidth > 0 && e.scrollWidth > e.clientWidth + 1)
        .map(e => (e.id || (typeof e.className === 'string' ? e.className : '')) + ':' + (e.textContent || '').trim().slice(0, 24))'''
    TAP_JS = r'''() => [...document.querySelectorAll('button, summary, select, textarea, input:not([type=hidden]):not([type=checkbox]), .jump a, label.check')]
        .filter(e => e.getClientRects().length).map(e => { const r = e.getBoundingClientRect(); return [e.id || e.className || e.tagName, Math.round(r.width), Math.round(r.height)]; })
        .filter(x => x[2] < 40 || x[1] < 40)'''

    TEXT_SELS = ['.tagline', '.jump a', '.sec-head h2', '.sec-head .hint', '.fine', '.lab', '.g-title', '.g-hint', '.chip', '.chip[aria-pressed="true"]',
                 '.btn.ghost.sm', '.add .g-title', '.ctl', '.affix input', '.affix .pre', '.affix .suf', '.car-big', '.car-read .fine', '.car-read a', '.mline',
                 '.mstatic .lab', '.faq summary', '.faq p', '.foot p', '.foot a', '.mail', '.linkish', '.rates summary .h2', '.rates summary .hint',
                 '.entry .en-pay', '.entry .en-app', '.entry .en-sub', '.entry .en-note', '.entry .en-net', '.entry .row-actions button',
                 '.day .d-hour', '.day .d-date', '.day .d-sub', '.day .row-actions button', '.wi thead th', '.wi tbody th', '.wi td']
    DASH_SELS = ['.dash .v-word', '.dash .v-line', '.dash .r-lab', '.dash .r-val', '.dash .r-goal', '.dash .r-pct', '.dash .need-lab', '.dash .need-val',
                 '.dash .need-gap', '.dash .need-why', '.dash .srow dt', '.dash .srow dd', '.dash .srow.total dt', '.dash .srow.total dd', '.dash .srow.sub dt',
                 '.dash .btn', '.dash .btn.ghost', '.dash-sub', '.dash-note', '.m-val', '.b-lab', '.b-amt', '.b-text']

    # ---- widths: nothing sticks out, the title stays on one line, the bar and footer do not collide
    if on('layout'):
      with section('layout: widths'):
        ctx, pg = new_page(browser, pre_state=BUSY)
        open_all(pg)
        pg.evaluate("document.getElementById('sheet').hidden = false")
        for w in WIDTHS:
            o = overflow(pg, w)
            eq('no horizontal overflow at %d' % w, (o['sw'] <= o['W'], o['bad']), (True, []))
            hh = pg.evaluate("(() => { const h = document.querySelector('.masthead h1').getBoundingClientRect(); const j = document.querySelector('.jump').getBoundingClientRect(); return [Math.round(h.height), Math.abs((h.top + h.bottom) / 2 - (j.top + j.bottom) / 2) < 14]; })()")
            # Fit needs the real display font, which only the built page carries.
            eq('title beside the jump links at %d' % w, (hh[0] <= 36 or not STANDALONE, hh[1]), (True, True))
        pg.evaluate("document.getElementById('sheet').hidden = true")
        pg.set_viewport_size({'width': 320, 'height': 700})
        pg.wait_for_timeout(100)
        pg.evaluate("document.documentElement.style.scrollBehavior = 'auto'; window.scrollTo(0, document.body.scrollHeight)")
        pg.wait_for_timeout(100)
        eq('footer clear of the pinned bar', pg.evaluate("document.getElementById('bar').getBoundingClientRect().top - document.querySelector('.foot').getBoundingClientRect().bottom") >= 0, True)
        cells = pg.evaluate("[...document.querySelectorAll('#bar .b-cell')].map(c => { const r = c.getBoundingClientRect(); return [Math.round(r.left), Math.round(r.right), Math.round(r.top)]; })")
        eq('three bar cells on one row', (len(cells), len(set(c[2] for c in cells))), (3, 1))
        eq('bar cells inside the screen', all(c[0] >= 0 and c[1] <= 320 for c in cells), True)
        eq('bar sits on the bottom edge', pg.evaluate("Math.round(document.getElementById('bar').getBoundingClientRect().bottom) === innerHeight"), True)
        if STANDALONE:
            eq('bar text not clipped at 320', pg.evaluate("[...document.querySelectorAll('#bar .b-amt, #bar .b-lab')].filter(e => e.scrollWidth > e.clientWidth + 1).map(e => e.id + e.textContent)"), [])
        # a toast sits above the bar and never blocks a tap
        for w in (320, 390):
            pg.set_viewport_size({'width': w, 'height': 800})
            tap(pg, '#copyBtn')
            pg.wait_for_timeout(80)
            tb = pg.evaluate("(() => { const t = document.getElementById('toast').getBoundingClientRect(); const b = document.getElementById('bar').getBoundingClientRect(); return [Math.round(t.bottom) <= Math.round(b.top), t.left >= 0 && t.right <= innerWidth]; })()")
            eq('toast above the bar and on screen at %d' % w, tb, [True, True])
        eq('toast never takes a tap', pg.evaluate("getComputedStyle(document.getElementById('toast')).pointerEvents"), 'none')
        # landscape phone
        pg.set_viewport_size({'width': 667, 'height': 375})
        o = overflow(pg, 667)
        eq('no overflow on a landscape phone', (o['sw'] <= o['W'], o['bad']), (True, []))
        ctx.close()

    # ---- the first screen on common phone sizes
    if on('layout'):
      with section('layout: the first screen'):
        for w, h in ((320, 568), (360, 640), (375, 667), (390, 844), (430, 932)):
            ctx, pg = new_page(browser, w=w, h=h)
            m = pg.evaluate('''() => { const r = id => document.getElementById(id).getBoundingClientRect(); const bar = r('bar');
                return {inputs: Math.max(r('pay').bottom, r('miles').bottom, r('minutes').bottom), barTop: bar.top, barBottom: bar.bottom, H: innerHeight,
                        word: document.getElementById('bWord').textContent.trim(), vWordBottom: r('vWord').bottom}; }''')
            eq('%dx%d: pay, miles and minutes sit above the bar' % (w, h), m['inputs'] <= m['barTop'] or (w == 320 and not STANDALONE), True)
            eq('%dx%d: the bar is on the bottom edge and says the verdict' % (w, h), (round(m['barBottom']) == m['H'], m['word']), (True, 'Pass'))
            if h >= 800:
                eq('%dx%d: the verdict word is on the first screen' % (w, h), m['vWordBottom'] <= m['barTop'], True)
            ctx.close()

    # ---- extremes: huge, tiny and negative numbers must not break the boxes
    if on('layout'):
      with section('layout: extremes'):
        ctx, pg = new_page(browser)
        open_all(pg)
        big_car = dict(CAR0, know=True, cpm=999.999)
        EXTREMES = [
            ('huge pay', dict(EXD, pay=9999999.99, miles=0.1, minutes=1), CAR0),
            ('tiny hours', dict(EXD, pay=1000000, miles=3, minutes=0.001, wait=0, retMin=0, retMiles=0), CAR0),
            ('huge loss', dict(EXD, pay=1, miles=100000, minutes=100000), CAR0),
            ('everything at its limit', dict(EXD, pay=10000000, tip=10000000, miles=100000, minutes=100000, wait=100000, retMiles=100000, retMin=100000,
                                              goalHour=10000000, goalMile=1000, taxPct=60), big_car),
            ('six figures', dict(EXD, pay=900000, miles=2, minutes=60), CAR0),
            ('cents', dict(EXD, pay=0.01, miles=0.01, minutes=0.01, wait=0, retMin=0, retMiles=0), CAR0),
            ('a huge car cost', dict(EXD, pay=1, miles=3000, minutes=60), big_car),
            ('no goals and a huge pay', dict(EXD, pay=9999999.99, goalHour=0, goalMile=0), CAR0),
            ('needs miles', dict(EXD, pay=10000000, miles=0, minutes=0, wait=0, retMin=0, retMiles=0), CAR0),
        ]
        for label, o, car in EXTREMES:
            set_state(pg, o, car)
            for w in (320, 390, 1280):
                ov = overflow(pg, w)
                eq('%s: no horizontal overflow at %d' % (label, w), (ov['sw'] <= ov['W'], ov['bad']), (True, []))
                # Text fit needs the real fonts, which only the built page carries.
                if STANDALONE:
                    eq('%s: nothing clipped in the dash and bar at %d' % (label, w), pg.evaluate(CLIP_JS), [])
        ctx.close()
        # the same boxes with a long saved log: big totals and negative nets
        ctx, pg = new_page(browser, pre_state=base_state(example=False, seq=9, hoursOv=1000, milesOv=100000,
                                                         entries=[mk_entry(1, 9999999.99, 100000, 100000, 100000, 'Amazon Flex', 'W' * 80)],
                                                         days=[mk_day(1, '2026-09-30', 9999, 1.0e7, 100000, 1000, -1.0e7)]))
        open_all(pg)
        for w in (320, 390, 1280):
            ov = overflow(pg, w)
            eq('huge log and days: no horizontal overflow at %d' % w, (ov['sw'] <= ov['W'], ov['bad']), (True, []))
        if STANDALONE:
            for w in (320, 390, 1280):
                pg.set_viewport_size({'width': w, 'height': 800})
                pg.wait_for_timeout(80)
                eq('huge log and days: nothing clipped at %d' % w, pg.evaluate(CLIP_JS), [])
        ctx.close()

    # ---- desktop
    if on('layout'):
      with section('layout: desktop'):
        ctx, pg = new_page(browser, w=1280, h=900)
        eq('bar hidden on desktop', pg.is_visible('#bar'), False)
        pos = pg.evaluate('''() => { const R = s => document.querySelector(s).getBoundingClientRect(); const a = R('.inputs'), r = R('.results'), m = R('.more'), app = R('.app');
            return {inputsRight: a.right, resultsLeft: r.left, resultsTop: r.top, inputsTop: a.top, moreLeft: m.left, moreRight: m.right, inputsLeft: a.left, resultsW: r.width,
                    appW: app.width, moreTop: m.top, inputsBottom: a.bottom}; }''')
        eq('results to the right of the inputs', pos['resultsLeft'] > pos['inputsRight'], True)
        eq('results level with the inputs at the top', abs(pos['resultsTop'] - pos['inputsTop']) < 2, True)
        eq('more shares the inputs column', abs(pos['moreLeft'] - pos['inputsLeft']) < 1 and abs(pos['moreRight'] - pos['inputsRight']) < 1, True)
        eq('more sits under the inputs', pos['moreTop'] >= pos['inputsBottom'] - 1, True)
        eq('results column is 400 wide', round(pos['resultsW']), 400)
        eq('page content is capped at 1040', round(pos['appW']) <= 1040, True)
        eq('the whole dash fits a 900 high window without its own scrollbar', pg.evaluate("(() => { const e = document.querySelector('.results'); return e.scrollHeight <= e.clientHeight + 1; })()"), True)
        pg.evaluate("window.scrollTo(0, 900)")
        pg.wait_for_timeout(900)
        eq('results stay in view when scrolled', pg.evaluate("document.querySelector('.results').getBoundingClientRect().top") < 40, True)
        eq('the verdict word is still on screen after scrolling', pg.evaluate("(() => { const b = document.getElementById('vWord').getBoundingClientRect(); return b.top > 0 && b.bottom < innerHeight; })()"), True)
        ctx.close()
        ctx, pg = new_page(browser, w=899, h=900)
        eq('bar shows just under the breakpoint', pg.is_visible('#bar'), True)
        eq('single column just under the breakpoint', pg.evaluate("document.querySelector('.results').getBoundingClientRect().left < 20"), True)
        ctx.close()
        ctx, pg = new_page(browser, w=1440, h=900)
        o = pg.evaluate("(() => { const a = document.querySelector('.app').getBoundingClientRect(); return [Math.round(a.left), Math.round(a.right)]; })()")
        eq('wide screens centre the page', abs(o[0] - (1440 - o[1])) <= 1, True)
        ctx.close()
        ctx, pg = new_page(browser, w=1280, h=640)
        pg.evaluate('window.scrollTo(0, 400)')
        pg.wait_for_timeout(900)
        eq('short window: the dash panel fits the window', pg.evaluate("document.querySelector('.results').getBoundingClientRect().height <= window.innerHeight"), True)
        ctx.close()

    # ---- dark scheme and the data-theme switch
    if on('layout'):
      with section('layout: dark and data-theme'):
        BG = {'light': 'rgb(236, 238, 241)', 'dark': 'rgb(11, 12, 15)'}
        DASHBG = {'light': 'rgb(21, 23, 28)', 'dark': 'rgb(28, 31, 38)'}
        for scheme in ('light', 'dark'):
            ctx, pg = new_page(browser, scheme=scheme)
            eq('%s: page and dash colours' % scheme, pg.evaluate("[getComputedStyle(document.body).backgroundColor, getComputedStyle(document.getElementById('dash')).backgroundColor]"), [BG[scheme], DASHBG[scheme]])
            eq('%s: the bar matches the dash' % scheme, pg.evaluate("getComputedStyle(document.getElementById('bar')).backgroundColor"), DASHBG[scheme])
            ctx.close()
        ctx, pg = new_page(browser, scheme='dark')
        eq('dark: native controls turn dark', pg.evaluate("getComputedStyle(document.documentElement).colorScheme"), 'dark')
        pg.evaluate("document.documentElement.setAttribute('data-theme', 'light')")
        eq('data-theme light wins over a dark system', pg.evaluate("getComputedStyle(document.body).backgroundColor"), BG['light'])
        ctx.close()
        ctx, pg = new_page(browser, scheme='light')
        pg.evaluate("document.documentElement.setAttribute('data-theme', 'dark')")
        eq('data-theme dark wins over a light system', pg.evaluate("getComputedStyle(document.body).backgroundColor"), BG['dark'])
        eq('data-theme dark turns native controls dark', pg.evaluate("getComputedStyle(document.documentElement).colorScheme"), 'dark')
        ctx.close()

    # ---- contrast, in both schemes and every verdict
    VERDICT_STATES = [
        ('take', dict(EXD, pay=14, miles=5, minutes=20), CAR0),
        ('borderline', dict(EXD, pay=10, miles=4, minutes=20), CAR0),
        ('pass', dict(EXD), CAR0),
        ('nogoals', dict(EXD, goalHour=0, goalMile=0), CAR0),
        ('empty', dict(EXD, pay=0), CAR0),
        ('need', dict(EXD, pay=10, miles=0, minutes=0, wait=0, retMin=0, retMiles=0), CAR0),
    ]
    for scheme in ('light', 'dark'):
      if on('layout'):
        with section('contrast: ' + scheme):
            cx, pgc = new_page(browser, scheme=scheme, pre_state=BUSY)
            open_all(pgc)
            pgc.evaluate("document.getElementById('sheetText').value = 'Offer: $14.00 for 6.5 mi / 29 min'; document.getElementById('sheet').hidden = false")
            res = pgc.evaluate(TEXT_JS, TEXT_SELS + DASH_SELS + ['.sheet .fine', 'textarea.ctl'])
            pgc.evaluate("document.getElementById('sheet').hidden = true")
            tap(pgc, '#copyBtn')
            pgc.wait_for_timeout(60)
            res += pgc.evaluate(TEXT_JS, ['.toast'])
            eq('%s: every kind of text is readable on the busy page' % scheme, [r for r in res if r[1] is not None and r[1] < r[2]], [])
            eq('%s: the audit found its elements' % scheme, [r[0] for r in res if r[1] is None and r[0] not in ('.dash .need-lab', '.dash .need-val', '.dash .need-gap', '.dash .need-why', '.dash .r-pct', '.b-text')], [])
            eq('%s: placeholders are readable' % scheme, [r for r in pgc.evaluate(PLACEHOLDER_JS) if r[1] < 4.5], [])
            # the edit form and a copy of every alert, each in its own state
            set_state(pgc, EXD, dict(CAR0, know=True, cpm=0))
            res2 = pgc.evaluate(TEXT_JS, ['.dash .alert.warn'])
            set_state(pgc, EXD, dict(CAR0, gasPrice=0))
            res2 += pgc.evaluate(TEXT_JS, ['#carWarn'])
            eq('%s: the warnings are readable' % scheme, [r for r in res2 if r[1] is None or r[1] < r[2]], [])
            # the verdicts: words, signs, meters, tiles
            for name, o, car in VERDICT_STATES:
                set_state(pgc, o, car)
                eq('%s: state %s reached' % (scheme, name), vdata(pgc), name)
                r3 = pgc.evaluate(TEXT_JS, DASH_SELS)
                eq('%s %s: dash text readable' % (scheme, name), [r for r in r3 if r[1] is not None and r[1] < r[2]], [])
                pairs = pgc.evaluate(PAIR_JS, [['dash sign', '.dash .sign', 'color', '#dash'], ['bar sign', '.bar .sign', 'color', '#bar'],
                                               ['hour meter', '#fHour', 'backgroundColor', '#rdHour'], ['mile meter', '#fMile', 'backgroundColor', '#rdMile']])
                low = [p for p in pairs if p[1] is None or p[1] < 3.0]
                if name in ('empty', 'need', 'nogoals'):
                    low = [p for p in low if 'meter' not in p[0]]
                eq('%s %s: signs and meters at least 3:1' % (scheme, name), low, [])
            set_state(pgc, EXD, CAR0)
            pairs = pgc.evaluate(PAIR_JS, [['field border', '.affix', 'borderTopColor', None], ['select border', 'select.ctl', 'borderTopColor', None],
                                           ['date border', 'input.ctl', 'borderTopColor', None], ['chip border', '.chip:not([aria-pressed="true"])', 'borderTopColor', None],
                                           ['ghost button border', '#clearBtn', 'borderTopColor', None], ['jump link border', '.jump a', 'borderTopColor', None],
                                           ['dash ghost button border', '.dash .btn.ghost', 'borderTopColor', '#dash'], ['pressed chip fill', '.chip[aria-pressed="true"]', 'backgroundColor', None]])
            eq('%s: control edges at least 3:1' % scheme, [p for p in pairs if p[1] is None or p[1] < 3.0], [])
            cx.close()
            # the storage warning needs a browser that refuses storage
            cx, pgc = new_page(browser, stub=STUB_NO_STORAGE, scheme=scheme)
            open_all(pgc)
            r4 = pgc.evaluate(TEXT_JS, ['#storeWarn p', '#exampleNote p', '.empty'])
            eq('%s: storage warning and example note readable' % scheme, [r for r in r4 if r[1] is None or r[1] < r[2]], [])
            cx.close()

    # ---- iOS zoom guard, tap targets, cramped fields
    if on('layout'):
      with section('layout: text size and tap targets'):
        for w in (320, 390):
            ctx, pg = new_page(browser, w=w, h=800, pre_state=BUSY)
            open_all(pg)
            res = pg.evaluate("[...document.querySelectorAll('input, select, textarea')].filter(e => e.type !== 'hidden' && e.getClientRects().length).map(e => [e.tagName + '#' + e.id, parseFloat(getComputedStyle(e).fontSize)])")
            eq('%d: controls checked' % w, len(res) >= 18, True)
            eq('%d: every text control is 16px or larger' % w, [r for r in res if r[1] < 16], [])
            ctx.close()
        ctx, pg = new_page(browser, pre_state=BUSY)
        open_all(pg)
        pg.evaluate("document.querySelector('#entryList .row-actions button').click()")
        pg.evaluate("document.getElementById('sheet').hidden = false")
        eq('the edit form shows Cancel', pg.is_visible('#eCancel'), True)
        for w in (320, 340, 360, 375, 390, 430, 768, 1280):
            pg.set_viewport_size({'width': w, 'height': 800})
            pg.wait_for_timeout(100)
            eq('no undersized tap targets at %d' % w, pg.evaluate(TAP_JS), [])
        for w in (320, 390):
            pg.set_viewport_size({'width': w, 'height': 800})
            pg.wait_for_timeout(100)
            eq('no cramped number fields at %d' % w, pg.evaluate("[...document.querySelectorAll('.affix input')].filter(e => e.getClientRects().length).map(e => [e.id, Math.round(e.getBoundingClientRect().width)]).filter(x => x[1] < 56)"), [])
        ctx.close()

    # ---- keyboard
    if on('layout'):
      with section('keyboard: tab order, focus rings and keys'):
        ck, pgk = new_page(browser)
        stops = []
        for i in range(16):
            pgk.keyboard.press('Tab')
            stops.append(pgk.evaluate(STOP_JS))
        names = [s[0] for s in stops]
        eq('the first stop is the Today link', names[0], 'jumpToday')
        order = [names.index(n) for n in ('pay', 'miles', 'minutes', 'logBtn', 'copyBtn') if n in names]
        eq('tab order runs pay, miles, minutes, then the buttons under the verdict', (len(order), order == sorted(order)), (5, True))
        eq('every tab stop shows a focus ring', [n for (n, ring, c) in stops if not ring], [])
        eq('every focus ring is at least 3:1', [(n, c) for (n, ring, c) in stops if ring and c < 3.0], [])
        pgk.evaluate("document.getElementById('grpGoals').open = true; document.getElementById('grpCar').open = false")
        labels = pgk.evaluate("[...document.querySelectorAll('#goalHourChips button')].map(b => b.textContent.trim())")
        pgk.locator('#goalHourChips button').nth(1).focus()
        pgk.keyboard.press('Enter')
        eq('Enter presses a chip', pressed(pgk, 'goalHourChips'), [labels[1]])
        pgk.locator('#goalHourChips button').nth(3).focus()
        pgk.keyboard.press('Space')
        eq('Space presses a chip', pressed(pgk, 'goalHourChips'), [labels[3]])
        pgk.locator('#grpCar > summary').focus()
        pgk.keyboard.press('Enter')
        eq('Enter opens a group', pgk.evaluate("document.getElementById('grpCar').open"), True)
        pgk.keyboard.press('Enter')
        eq('Enter closes it again', pgk.evaluate("document.getElementById('grpCar').open"), False)
        pgk.evaluate("document.getElementById('entryBox').open = true")
        put(pgk, '#ePay', '9')
        put(pgk, '#eMiles', '3')
        put(pgk, '#eMin', '15')
        pgk.locator('#eMin').focus()
        pgk.keyboard.press('Enter')
        pgk.wait_for_timeout(100)
        eq('Enter in the entry form adds the entry', len(entries_of(pgk)), 1)
        ck.close()
        cs, pgs = new_page(browser, stub=STUB_REJECT)
        tap(pgs, '#copyBtn')
        pgs.wait_for_timeout(120)
        eq('the copy sheet opens when the browser refuses the clipboard', shown(pgs, '#sheet'), True)
        eq('the text in the sheet is selected and focused', pgs.evaluate("document.activeElement.id"), 'sheetText')
        pgs.keyboard.press('Escape')
        eq('Escape closes the copy sheet', shown(pgs, '#sheet'), False)
        cs.close()
        cj, pgj = new_page(browser, reduced=True)
        tap(pgj, '#jumpToday')
        pgj.wait_for_timeout(200)
        eq('the Today link goes to the Today heading', pgj.evaluate("(() => { const t = document.getElementById('h-today').getBoundingClientRect().top; return t >= 8 && t < 120; })()"), True)
        tap(pgj, '#jumpDays')
        pgj.wait_for_timeout(200)
        eq('the Days link goes to the Days heading', pgj.evaluate("(() => { const t = document.getElementById('h-days').getBoundingClientRect().top; return t >= 8 && t < 120; })()"), True)
        cj.close()

    # ---- reduced motion
    if on('layout'):
      with section('reduced motion'):
        cr, pgr = new_page(browser, reduced=True)
        d1 = pgr.evaluate("[getComputedStyle(document.querySelector('.chip')).transitionDuration, getComputedStyle(document.getElementById('fHour')).transitionDuration, getComputedStyle(document.documentElement).scrollBehavior]")
        cr.close()
        cn, pgn = new_page(browser, reduced=False)
        d2 = pgn.evaluate("[getComputedStyle(document.querySelector('.chip')).transitionDuration, getComputedStyle(document.getElementById('fHour')).transitionDuration, getComputedStyle(document.documentElement).scrollBehavior]")
        cn.close()
        eq('no transitions and no smooth scrolling when reduced motion is on', d1, ['0s', '0s', 'auto'])
        eq('short transitions and smooth scrolling otherwise', (d2[0] != '0s', d2[1] != '0s', d2[2]), (True, True, 'smooth'))

    # ============================================================ the self-hosted page: fonts, metadata, privacy page, network
    if STANDALONE and on('standalone'):
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
        eq('h1 uses the display font', pgf.evaluate("getComputedStyle(document.querySelector('.masthead h1')).fontFamily").startswith('"Big Shoulders Display"'), True)
        used = pgf.evaluate('''() => { const out = new Set(); document.querySelectorAll('body *').forEach(el => { const cs = getComputedStyle(el); if (el.getClientRects().length && el.childNodes.length)
            out.add(cs.fontFamily.split(',')[0].replace(/["']/g, '').trim() + ' ' + cs.fontWeight); }); return [...out].sort(); }''')
        have = {'Big Shoulders Display': {700, 800}, 'Public Sans': {400, 500, 600, 700}, 'IBM Plex Mono': {400, 500}}
        eq('every font weight in use has an embedded face', [u for u in used if u.rsplit(' ', 1)[0] in have and int(u.rsplit(' ', 1)[1]) not in have[u.rsplit(' ', 1)[0]]], [])
        eq('tabular digits survive the subset', pgf.evaluate('''() => {
            const w = (t) => { const s = document.createElement('span'); s.style.cssText = "font:400 16px 'Public Sans';position:absolute;visibility:hidden;white-space:pre;font-variant-numeric:tabular-nums";
                s.textContent = t; document.body.appendChild(s); const r = s.getBoundingClientRect().width; s.remove(); return r; };
            return w('1111') === w('0000') && w('1111') > 0; }'''), True)
        eq('every letter, digit and sign the big numbers and verdict words use is in the display face', pgf.evaluate('''() => {
            const w = (t, fam) => { const s = document.createElement('span'); s.style.cssText = "font:800 40px " + fam + ";position:absolute;visibility:hidden;white-space:pre";
                s.textContent = t; document.body.appendChild(s); const r = s.getBoundingClientRect().width; s.remove(); return r; };
            return [...'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789$.,-%/KMBT'].filter(c => w(c, "'Big Shoulders Display', monospace") === w(c, "monospace")); }'''), [])
        eq('multiply and divide signs render in the mono face', pgf.evaluate('''() => {
            const w = (t) => { const s = document.createElement('span'); s.style.cssText = "font:400 13px 'IBM Plex Mono';position:absolute;visibility:hidden;white-space:pre";
                s.textContent = t; document.body.appendChild(s); const r = s.getBoundingClientRect().width; s.remove(); return r; };
            return w(String.fromCharCode(215)) > 0 && w(String.fromCharCode(247)) > 0 && Math.abs(w(String.fromCharCode(215)) - w('x')) < 0.6; }'''), True)
        cf.close()

    if STANDALONE and on('standalone'):
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
        alt = pgm.get_attribute('meta[property="og:image:alt"]', 'content')
        eq('the og image alt text matches the first-visit example', [x for x in ('6.50 dollar offer', '8.88 dollars an hour', '12.25 dollars needed', 'verdict Pass') if x not in alt], [])
        eq('twitter card', pgm.get_attribute('meta[name="twitter:card"]', 'content'), 'summary_large_image')
        eq('twitter image', pgm.get_attribute('meta[name="twitter:image"]', 'content'), SITE_URL + 'og.png')
        eq('theme colors', pgm.evaluate("[...document.querySelectorAll('meta[name=theme-color]')].map(m => m.content)"), ['#ECEEF1', '#0B0C0F'])
        eq('favicon is a data uri', (pgm.get_attribute('link[rel=icon]', 'href') or '').startswith('data:image/svg+xml;base64,'), True)
        eq('apple touch icon', pgm.get_attribute('link[rel=apple-touch-icon]', 'href'), 'apple-touch-icon.png')
        eq('mailto anchor', pgm.get_attribute('a.mail', 'href'), 'mailto:' + SUPPORT)
        eq('privacy link', pgm.get_attribute('.foot a[href="privacy.html"]', 'href'), 'privacy.html')
        eq('rinse rate link', pgm.get_attribute('.foot a[href*="rinse-rate"]', 'href'), 'https://sanjixysti-creator.github.io/rinse-rate/')
        eq('home link', pgm.get_attribute('.foot a[href="https://sanjixysti-creator.github.io/"]', 'href'), 'https://sanjixysti-creator.github.io/')
        eq('maker line', 'Made by Xysti Software' in txt(pgm, '.foot'), True)
        eq('outside links open in a new tab, safely', pgm.evaluate("[...document.querySelectorAll('a[href^=\"https://www.irs.gov\"]')].filter(a => a.target !== '_blank' || a.rel !== 'noopener noreferrer').length"), 0)
        eq('no robots block', pgm.evaluate("document.querySelectorAll('meta[name=robots]').length"), 0)
        cm.close()

    for scheme in ('light', 'dark'):
      if STANDALONE and on('standalone'):
        with section('standalone: privacy page ' + scheme):
            cp, pgp = new_page(browser, scheme=scheme, url=ORIGIN + PAGE_PATH + 'privacy.html')
            eq('privacy title', pgp.title(), 'Privacy Policy - Drive Rate')
            has('privacy says no analytics', txt(pgp, 'body'), 'no analytics')
            has('privacy says what is stored', txt(pgp, 'body'), 'Your saved days: the date')
            has('privacy says the IRS rate is written into the page', txt(pgp, 'body'), 'can go out of date')
            eq('privacy mailto', pgp.get_attribute('a[href^="mailto:"]', 'href'), 'mailto:' + SUPPORT)
            eq('privacy back link', pgp.get_attribute('.back', 'href'), './')
            eq('privacy brand link', pgp.get_attribute('.brand', 'href'), './')
            eq('privacy has no dash look-alikes', [c for c in DASHES if c in txt(pgp, 'body')], [])
            for w in (320, 390, 768, 1200):
                o = overflow(pgp, w)
                eq('privacy no overflow %s %d' % (scheme, w), (o['sw'] <= o['W'], o['bad']), (True, []))
            eq('privacy body background %s' % scheme, pgp.evaluate("getComputedStyle(document.body).backgroundColor"), 'rgb(236, 238, 241)' if scheme == 'light' else 'rgb(11, 12, 15)')
            res = pgp.evaluate(TEXT_JS, ['.updated', 'p', 'li', 'a', '.back', 'h1', 'h2', '.brand span'])
            eq('privacy %s contrast' % scheme, [r for r in res if r[1] is not None and r[1] < r[2]], [])
            cp.close()

    if STANDALONE and on('standalone'):
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
