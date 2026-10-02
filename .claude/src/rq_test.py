import contextlib, functools, http.server, json, os, re, struct, threading
from playwright.sync_api import sync_playwright

D = os.path.dirname(os.path.abspath(__file__))
SRC = D + '/rinse-quote.html'
OUT = D + '/rq-test.html'

# RQ_STANDALONE=/path/to/site/rinse-quote/index.html tests the self-hosted page instead of the artifact fragment.
STANDALONE = os.environ.get('RQ_STANDALONE', '')
SITE_URL = 'https://sanjixysti-creator.github.io/rinse-quote/'
SITE_TITLE = 'Rinse Quote: Free Pressure Washing Quote Calculator'

src = open(SRC, encoding='utf-8').read()
CODE = re.search(r'code=([A-Z0-9\-]+)', open(D + '/pro-code.txt').read()).group(1)
mlink = re.search(r"PRO = \{ link: '([^']*)'", src)
PRO_LINK = mlink.group(1) if mlink else ''
mprice = re.search(r"price: '([^']*)'", src)
PRO_PRICE = mprice.group(1) if mprice else ''
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
    PAGE_PATH = '/rq-test.html'
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


def new_page(browser, stub=STUB_OK, scheme='light', w=390, h=844, url_hash='', pre_state=None):
    ctx = browser.new_context(viewport={'width': w, 'height': h}, color_scheme=scheme, device_scale_factor=1)
    ctx.add_init_script(stub)
    if pre_state:
        ctx.add_init_script("try { if (!localStorage.getItem('rinse-quote-v1')) localStorage.setItem('rinse-quote-v1', %s); } catch (e) {}" % json.dumps(pre_state))
    page = ctx.new_page()
    page.set_default_timeout(4000)
    page.on('console', lambda m: errs.append((m.type, m.text)) if m.type in ('error', 'warning') else None)
    page.on('pageerror', lambda e: errs.append(('pageerror', str(e))))
    page.on('request', lambda r: ext_reqs.append(r.url) if not (r.url.startswith(ORIGIN + '/') or r.url.startswith(('data:', 'blob:'))) else None)
    page.route(re.compile(r'https://fonts\.(googleapis|gstatic)\.com/.*'), lambda r: r.abort())
    page.route('**/favicon.ico', lambda r: r.fulfill(status=204, body=''))
    page.goto(URL + url_hash)
    page.wait_for_timeout(250)
    return ctx, page


def txt(page, sel):
    return (page.text_content(sel) or '').strip()


def tap(page, sel):
    page.locator(sel).first.evaluate('e => e.click()')


def setc(loc, want=True):
    loc.evaluate('(e, w) => { if (e.checked !== w) e.click(); }', want)


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


# ---------------------------------------------------------------- source hygiene
with section('source hygiene'):
    eq('no em dash', '\u2014' in src, False)
    eq('title first', src.startswith('<title>Rinse Quote</title>'), True)
    eq('no document tags', bool(re.search(r'<(html|head|body)[\s>]', src)), False)
    eq('no print', 'window.print' in src, False)
    eq('no mailto links', 'mailto:' in src, False)
    eq('no dialogs', bool(re.search(r'\b(alert|confirm|prompt)\(', src)), False)
    eq('no external scripts', re.findall(r'<script[^>]*\bsrc=', src), [])
    hosts = set(re.findall(r'https?://([a-z0-9.\-]+)', src))
    eq('only allowed hosts', sorted(hosts - {'fonts.googleapis.com', 'fonts.gstatic.com', 'buy.stripe.com', 'sanjixysti-creator.github.io'}), [])
    # The site's own address may only appear as the target of a plain link to one of its pages, never in a request.
    site_urls = set(re.findall(r'https://sanjixysti-creator\.github\.io/[A-Za-z0-9\-/._]*', src))
    site_links = set(re.findall(r'<a href="(https://sanjixysti-creator\.github\.io/[A-Za-z0-9\-/._]*)"', src))
    eq('the site address is only used in plain links', sorted(site_urls - site_links), [])
    eq('links to the other tools', sorted(site_links), ['https://sanjixysti-creator.github.io/', 'https://sanjixysti-creator.github.io/rinse-mix/', 'https://sanjixysti-creator.github.io/rinse-rate/'])

    if STANDALONE:
        eq('built: doctype first', built.lstrip().lower().startswith('<!doctype html>'), True)
        eq('built: no em dash', '\u2014' in built, False)
        eq('built: title', ('<title>%s</title>' % SITE_TITLE) in built, True)
        eq('built: no google fonts', 'fonts.googleapis.com' in built or 'fonts.gstatic.com' in built, False)
        eq('built: no claude.ai link', 'claude.ai' in built.lower(), False)
        eq('built: no external scripts', re.findall(r'<script[^>]*\bsrc=', built), [])
        bh = set(re.findall(r'https?://([a-z0-9.\-]+)', built))
        eq('built: only own hosts', sorted(bh - {'www.w3.org', 'sanjixysti-creator.github.io', 'buy.stripe.com'}), [])
        eq('built: no print', 'window.print' in built, False)
        eq('built: no dialogs', bool(re.search(r'\b(alert|confirm|prompt)\(', built)), False)
        eq('built: noscript', '<noscript>' in built, True)
        eq('built: one style block', built.count('<style>'), 1)
        eq('built: two mailto anchors', built.count('href="mailto:'), 2)
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

    # ------------------------------------------------------------ 1 free user, phone, light
    ctx1, page = new_page(browser)

    with section('free: first paint'):
        page.screenshot(path=D + '/rq-phone.png', full_page=True)
        page.screenshot(path=D + '/rq-light-top.png')
        page.locator('#proCard').screenshot(path=D + '/rq-light-pro.png')
        eq('sample total', txt(page, '#totalAmt'), '$877.50')
        eq('total label', txt(page, '#totalLab'), 'Total')
        eq('bar total', txt(page, '#barAmt'), '$877.50')
        eq('sample pill', txt(page, '#ckPill'), 'On target')
        eq('sample cost', txt(page, '#ckCost'), '$395.00')
        eq('sample profit', txt(page, '#ckProfit'), '$482.50')
        eq('sample margin', txt(page, '#ckMargin'), '55%')
        eq('sample per hour', txt(page, '#ckHour'), '$140.42/hr')
        eq('sample banner visible', page.is_visible('#sampleBanner'), True)
        eq('placeholder biz class', 'is-placeholder' in (page.get_attribute('#tBiz', 'class') or ''), True)

    if STANDALONE:
        with section('standalone: fonts'):
            res = page.evaluate('''async () => {
                const out = [];
                for (const f of [...document.fonts]) {
                    try { await f.load(); out.push(f.family.replace(/["']/g, '') + ' ' + f.weight + ' ' + f.status); }
                    catch (e) { out.push(f.family + ' ' + f.weight + ' ERROR ' + e.message); }
                }
                return out;
            }''')
            eq('8 faces declared', len(res), 8)
            eq('every face loads', [r for r in res if not r.endswith(' loaded')], [])
            eq('display font ready', page.evaluate('''document.fonts.check("800 30px 'Big Shoulders Display'")'''), True)
            eq('body font ready', page.evaluate('''document.fonts.check("400 16px 'Public Sans'")'''), True)
            eq('mono font ready', page.evaluate('''document.fonts.check("500 13px 'IBM Plex Mono'")'''), True)
            eq('h1 uses display font', page.evaluate("getComputedStyle(document.querySelector('.masthead h1')).fontFamily").startswith('"Big Shoulders Display"'), True)
            eq('tabular digits survive the subset', page.evaluate('''() => {
                const w = (t) => {
                    const s = document.createElement('span');
                    s.style.cssText = "font:400 16px 'Public Sans';position:absolute;visibility:hidden;white-space:pre;font-variant-numeric:tabular-nums";
                    s.textContent = t; document.body.appendChild(s);
                    const r = s.getBoundingClientRect().width; s.remove(); return r;
                };
                return w('1111') === w('0000') && w('1111') > 0;
            }'''), True)

        with section('standalone: metadata'):
            eq('page title', page.title(), SITE_TITLE)
            eq('html lang', page.get_attribute('html', 'lang'), 'en')
            eq('canonical', page.get_attribute('link[rel=canonical]', 'href'), SITE_URL)
            eq('og:image absolute', page.get_attribute('meta[property="og:image"]', 'content'), SITE_URL + 'og.png')
            eq('og:url', page.get_attribute('meta[property="og:url"]', 'content'), SITE_URL)
            eq('og:title', page.get_attribute('meta[property="og:title"]', 'content'), SITE_TITLE)
            eq('twitter card', page.get_attribute('meta[name="twitter:card"]', 'content'), 'summary_large_image')
            eq('twitter image', page.get_attribute('meta[name="twitter:image"]', 'content'), SITE_URL + 'og.png')
            dlen = len(page.get_attribute('meta[name="description"]', 'content') or '')
            eq('description length ok', 60 <= dlen <= 200, True)
            eq('svg favicon inline', (page.get_attribute('link[rel=icon]', 'href') or '').startswith('data:image/svg+xml;base64,'), True)
            eq('touch icon path', page.get_attribute('link[rel=apple-touch-icon]', 'href'), 'apple-touch-icon.png')
            eq('two theme colors', page.locator('meta[name="theme-color"]').count(), 2)
            eq('privacy link', page.get_attribute('.foot a[href="privacy.html"]', 'href'), 'privacy.html')
            has('maker line', txt(page, '.foot'), 'Made by Xysti Software.')
            eq('mailto hrefs', page.eval_on_selector_all('a.mail', 'els => els.map(e => e.getAttribute("href"))'), ['mailto:' + SUPPORT] * 2)

    with section('free: total label spacing'):
        r = page.evaluate('''() => {
            const a = document.getElementById('totalLab').getBoundingClientRect();
            const b = document.getElementById('totalAmt').getBoundingClientRect();
            return [a.bottom, b.top];
        }''')
        eq('label clears the number', r[0] <= r[1], True)

    with section('free: copy text'):
        cp = copied(page)
        has('copy head', cp, 'Pressure washing quote')
        has('copy driveway', cp, 'Driveway & concrete, 900 sq ft: $225.00')
        has('copy house', cp, 'House wash (soft wash), 1,800 sq ft of home, 2 stories: $562.50')
        has('copy oil', cp, 'Oil & grease treatment x2: $90.00')
        has('copy total', cp, 'Total: $877.50')
        has('copy valid', cp, 'Valid until')
        eq('copy toast', toast(page), 'Quote copied. Paste it into a text or email.')
        eq('a tap under the toast reaches the page', page.evaluate("(() => { const t = document.getElementById('toast'); const r = t.getBoundingClientRect(); const e = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2); return !!e && !t.contains(e); })()"), True)
        page.evaluate('window.__copied = null')
        tap(page, '#barCopy')
        page.wait_for_timeout(80)
        has('bar copy works', read_copied(page), 'Total: $877.50')

    with section('free: locked pro'):
        eq('pro card visible', page.is_visible('#proCard'), True)
        eq('packages hidden', page.is_visible('#secPackages'), False)
        eq('saved hidden', page.is_visible('#secSaved'), False)
        eq('badge hidden', page.is_visible('#proBadge'), False)
        eq('save label', txt(page, '#saveLabel'), 'Save')
        eq('save badge visible', page.is_visible('#saveBadge'), True)
        eq('price shown', txt(page, '#proPrice'), PRO_PRICE)
        if PRO_LINK:
            eq('get pro visible', page.is_visible('#getPro'), True)
            eq('get pro href', page.get_attribute('#getPro', 'href'), PRO_LINK)
            eq('get pro target', page.get_attribute('#getPro', 'target'), '_blank')
            has('get pro rel', page.get_attribute('#getPro', 'rel'), 'noopener')
            eq('soon hidden', page.is_visible('#proSoon'), False)
        else:
            eq('get pro hidden', page.is_visible('#getPro'), False)
            eq('soon visible', page.is_visible('#proSoon'), True)
        tap(page, '#saveBtn')
        eq('locked save toast', toast(page), 'Saving quotes is part of Pro.')
        eq('code form starts hidden', page.is_visible('#codeForm'), False)
        tap(page, '#haveCode')
        eq('code form opens', page.is_visible('#codeForm'), True)
        tap(page, '#haveCode')
        eq('code form closes', page.is_visible('#codeForm'), False)

    with section('free: support email'):
        eq('support set', bool(SUPPORT), True)
        eq('two support lines', page.locator('.mail').count(), 2)
        eq('pro card support text', txt(page, '#proCard .mail'), SUPPORT)
        eq('footer support text', txt(page, '.foot .mail'), SUPPORT)
        page.evaluate('window.__copied = null')
        tap(page, '#proCard .mail-copy')
        page.wait_for_timeout(80)
        eq('support copy', read_copied(page), SUPPORT)
        eq('support toast', toast(page), 'Email copied.')
        page.evaluate('window.__copied = null')
        tap(page, '.foot .mail-copy')
        page.wait_for_timeout(80)
        eq('footer support copy', read_copied(page), SUPPORT)

    with section('free: heavy buildup'):
        L0 = page.locator('#lines .line').nth(0)
        L0.locator('label.chip', has_text='Heavy').click()
        eq('heavy total', txt(page, '#totalAmt'), '$956.25')
        L0.locator('label.chip', has_text='Normal').click()
        eq('normal again', txt(page, '#totalAmt'), '$877.50')

    with section('free: price check'):
        page.fill('#hours', '20')
        eq('losing pill', txt(page, '#ckPill'), 'Losing money')
        eq('losing suggest', txt(page, '#ckSuggest'), '$1,764.29')
        page.fill('#hours', '12')
        eq('below pill', txt(page, '#ckPill'), 'Below target')
        eq('below suggest', txt(page, '#ckSuggest'), '$1,078.57')
        has('below msg', txt(page, '#ckMsg'), 'Add $201.07 to reach your 30% margin.')
        page.fill('#hours', '6')
        eq('back on target', txt(page, '#ckPill'), 'On target')

    with section('free: blank, minimum, tax, deposit'):
        tap(page, '#startBlank')
        eq('blank total', txt(page, '#totalAmt'), '$0.00')
        eq('blank banner hidden', page.is_visible('#sampleBanner'), False)
        eq('blank note', txt(page, '#totalNote'), 'Add a surface and a size to start.')
        page.evaluate('window.__copied = null')
        tap(page, '#copyBtn')
        eq('empty copy toast', toast(page), 'Add a surface with a size first.')
        eq('empty copy copies nothing', read_copied(page), '')
        qty = page.locator('#lines .line input[id$="-qty"]').first
        qty.fill('200')
        eq('min total', txt(page, '#totalAmt'), '$150.00')
        has('min note', txt(page, '#totalNote'), 'Minimum job charge applied.')
        has('min copy', copied(page), 'Minimum service charge adjustment: $100.00')
        qty.fill('1000')
        eq('flat total', txt(page, '#totalAmt'), '$250.00')
        page.fill('#taxPct', '8.5')
        page.fill('#depositPct', '25')
        eq('tax total', txt(page, '#totalAmt'), '$271.25')
        has('tax note', txt(page, '#totalNote'), 'Includes $21.25 tax.')
        has('deposit note', txt(page, '#totalNote'), 'Deposit to book: $67.81.')
        cp = copied(page)
        has('copy subtotal', cp, 'Subtotal: $250.00')
        has('copy tax', cp, 'Tax (8.5%): $21.25')
        has('copy deposit', cp, 'Deposit to book (25%): $67.81')

    with section('free: second surface'):
        tap(page, '#addLine')
        second = page.locator('#lines .line').nth(1)
        second.locator('select').first.select_option('house')
        eq('stories shown', second.locator('.stories').is_visible(), True)
        second.locator('.stories select').select_option('3')
        second.locator('input[id$="-qty"]').fill('1000')
        eq('two surfaces total', txt(page, '#totalAmt'), '$678.13')
        has('math line', second.locator('.math').text_content(), '$0.25/sq ft × 1.50 for 3 stories')

    with section('free: custom charge'):
        tap(page, '#addExtra')
        page.locator('#extraList .extra.custom input.ctl').fill('Gate cleaning')
        page.locator('#extraList .extra.custom [id$="-price"]').fill('30')
        has('custom copy', copied(page), 'Gate cleaning: $30.00')
        eq('custom total', txt(page, '#totalAmt'), '$710.68')

    with section('free: customer and business flow to the ticket'):
        page.fill('#customer', 'Dana Whitfield')
        page.fill('#address', '18 Alder Court')
        page.click('#rates summary')
        page.fill('#business', 'Clearwater Exterior')
        has('ticket customer', txt(page, '#ticket'), 'Dana Whitfield')
        has('ticket biz', txt(page, '#ticket'), 'Clearwater Exterior')
        eq('placeholder class gone', 'is-placeholder' in (page.get_attribute('#tBiz', 'class') or ''), False)

    with section('free: persistence'):
        before = txt(page, '#totalAmt')
        page.wait_for_timeout(500)
        page.reload()
        page.wait_for_timeout(300)
        eq('persisted total', txt(page, '#totalAmt'), before)
        eq('persisted customer', page.input_value('#customer'), 'Dana Whitfield')
        eq('still locked after reload', page.is_visible('#proCard'), True)

    with section('free: no sideways scroll'):
        for w in (320, 390, 768, 1200):
            o = overflow(page, w)
            eq('free no overflow at %d' % w, (o['sw'] <= o['W'], o['bad']), (True, []))
        eq('bar hidden wide', page.is_visible('#bar'), False)
        eq('aside sticky wide', page.evaluate("getComputedStyle(document.querySelector('.aside')).position"), 'sticky')
        page.set_viewport_size({'width': 390, 'height': 844})
        eq('bar visible phone', page.is_visible('#bar'), True)

    # ------------------------------------------------------------ 2 pro user, phone, light
    ctx2, pro = new_page(browser)

    with section('pro: unlock'):
        tap(pro, '#haveCode')
        pro.fill('#codeInput', '')
        pro.press('#codeInput', 'Enter')
        eq('empty code msg', txt(pro, '#codeMsg'), 'Enter the code from your confirmation page.')
        pro.fill('#codeInput', 'RINSE-AAAA-BBBB')
        pro.press('#codeInput', 'Enter')
        pro.wait_for_timeout(200)
        eq('wrong code msg', txt(pro, '#codeMsg'), 'That code did not match. Check it and try again.')
        near = CODE[:-1] + ('9' if CODE[-1] != '9' else '8')
        pro.fill('#codeInput', near)
        pro.press('#codeInput', 'Enter')
        pro.wait_for_timeout(200)
        eq('near miss msg', txt(pro, '#codeMsg'), 'That code did not match. Check it and try again.')
        eq('still locked', pro.is_visible('#secPackages'), False)
        pro.fill('#codeInput', '  ' + CODE.lower().replace('-', ' ') + ' ')
        pro.press('#codeInput', 'Enter')
        pro.wait_for_timeout(300)
        eq('unlock toast', toast(pro), 'Pro unlocked on this device.')
        eq('badge visible', pro.is_visible('#proBadge'), True)
        eq('pro card gone', pro.is_visible('#proCard'), False)
        eq('footer support stays for pro users', pro.is_visible('.foot .mail'), True)
        eq('packages visible', pro.is_visible('#secPackages'), True)
        eq('saved visible', pro.is_visible('#secSaved'), True)
        eq('save label pro', txt(pro, '#saveLabel'), 'Save quote')
        eq('save badge gone', pro.is_visible('#saveBadge'), False)
        eq('empty saved list', txt(pro, '#savedList'), 'No saved quotes yet. Tap Save quote next to your total.')
        pro.wait_for_timeout(400)
        pro.reload()
        pro.wait_for_timeout(300)
        eq('pro persists', pro.is_visible('#proBadge'), True)
        eq('sample still 877.50', txt(pro, '#totalAmt'), '$877.50')

    with section('pro: packages'):
        pro.click('#rates summary')
        pro.fill('#business', 'Clearwater Exterior')
        pro.fill('#phone', '555-0100')
        eq('label before packages', txt(pro, '#totalLab'), 'Total')
        setc(pro.locator('#pkgOn'))
        eq('pkg body shown', pro.is_visible('#pkgBody'), True)
        eq('from label', txt(pro, '#totalLab'), 'From')
        eq('bar from label', txt(pro, '#barLab'), 'From')
        eq('from amount', txt(pro, '#totalAmt'), '$877.50')
        has('same warn better', txt(pro, '#pkgBetterWarn'), 'Better costs the same as Good.')
        eq('same warn best visible', pro.is_visible('#pkgBestWarn'), True)
        oil = pro.locator('#pkgBetterPicks .pkg-pick', has_text='Oil & grease')
        eq('oil already in good', (oil.locator('input').is_checked(), oil.locator('input').is_disabled()), (True, True))
        has('oil sub', oil.text_content(), 'Already in Good')
        setc(pro.locator('#pkgBetterPicks .pkg-pick', has_text='Rust stain').locator('input'))
        setc(pro.locator('#pkgBetterPicks .pkg-pick', has_text='Gutter').locator('input'))
        eq('better price', txt(pro, '#pkgBetterPrice'), '$1,017.50')
        eq('better warn cleared', pro.is_visible('#pkgBetterWarn'), False)
        eq('no savings line without a discount', 'Bundle savings' in txt(pro, '#tOpts'), False)

        tap(pro, '#addExtra')
        cx = pro.locator('#extraList .extra.custom')
        cx.locator('input.ctl').fill('Sealer')
        cx.locator('[id$="-price"]').fill('200')
        setc(cx.locator('input[type="checkbox"]').first, False)
        eq('sealer off in base', txt(pro, '#totalAmt'), '$877.50')
        for label in ('Trip charge', 'Sealer'):
            setc(pro.locator('#pkgBestPicks .pkg-pick', has_text=label).locator('input'))
        pro.fill('#pkgBestDisc', '10')
        eq('best price', txt(pro, '#pkgBestPrice'), '$1,118.25')
        eq('three options note', txt(pro, '#totalNote'), 'Three options: $877.50, $1,017.50, $1,118.25.')
        rb = pro.locator('#pkgBestPicks .pkg-pick', has_text='Rust stain')
        eq('rust carried into best', (rb.locator('input').is_checked(), rb.locator('input').is_disabled()), (True, True))
        has('rust carried label', rb.text_content(), 'Already in Better')

        t = txt(pro, '#tOpts')
        for needle in ('Option 1, Good', 'Option 2, Better', 'Option 3, Best', '$877.50', '$1,017.50', '$1,118.25',
                       'Everything in Good', 'Rust stain treatment', 'Gutter brightening', 'Everything in Better',
                       'Trip charge', 'Sealer', 'Bundle savings of $124.25'):
            has('ticket options ' + needle, t, needle)
        eq('ticket lines hidden', pro.is_visible('#tLines'), False)
        eq('ticket summary hidden', pro.is_visible('#tSum'), False)

        cp = copied(pro)
        for needle in ('Clearwater Exterior - 555-0100', 'Option 1, Good: $877.50', 'Option 2, Better: $1,017.50',
                       'Option 3, Best: $1,118.25', '- Driveway & concrete, 900 sq ft', '- Oil & grease treatment x2',
                       '- Everything in Good', '- Rust stain treatment', '- Gutter brightening', '- Everything in Better',
                       '- Trip charge', '- Sealer', '- Bundle savings of $124.25', 'Valid until'):
            has('copy options ' + needle, cp, needle)

        pro.fill('#pkgBestDisc', '80')
        eq('best price at the 50 percent cap', txt(pro, '#pkgBestPrice'), '$621.25')
        pro.press('#pkgBestDisc', 'Tab')
        eq('discount input clamps', pro.input_value('#pkgBestDisc'), '50')
        pro.fill('#pkgBestDisc', '10')
        eq('best price restored', txt(pro, '#pkgBestPrice'), '$1,118.25')

        pro.fill('#taxPct', '8.5')
        pro.fill('#depositPct', '25')
        eq('good with tax', txt(pro, '#totalAmt'), '$952.09')
        eq('better with tax', txt(pro, '#pkgBetterPrice'), '$1,103.99')
        eq('best with tax', txt(pro, '#pkgBestPrice'), '$1,213.30')
        cp = copied(pro)
        has('options tax note', cp, 'Prices include 8.5% sales tax.')
        has('options deposit note', cp, 'A 25% deposit books the job.')
        pro.fill('#taxPct', '0')
        pro.fill('#depositPct', '0')
        eq('good without tax', txt(pro, '#totalAmt'), '$877.50')

        pro.fill('#pkgBetterNote', 'Includes a 30 day re-wash guarantee')
        has('note on ticket', txt(pro, '#tOpts'), 'Includes a 30 day re-wash guarantee')
        has('note in copy', copied(pro), '- Includes a 30 day re-wash guarantee')

    with section('pro: saved quotes'):
        pro.fill('#customer', 'Dana Whitfield')
        pro.fill('#address', '18 Alder Court')
        tap(pro, '#saveBtn')
        eq('saved toast', toast(pro), 'Quote saved.')
        eq('one card', pro.locator('#savedList .saved').count(), 1)
        eq('save label update', txt(pro, '#saveLabel'), 'Update saved')
        dana = pro.locator('#savedList .saved', has_text='Dana Whitfield')
        eq('dana amount is the good price', txt(dana, '.sv-amt') if False else (dana.locator('.sv-amt').text_content() or '').strip(), '$877.50')
        dana.locator('select').first.select_option('sent')
        eq('waiting stat', txt(pro, '#stOpen'), '$878')
        eq('rate empty', txt(pro, '#stRate'), '-')
        pro.evaluate('window.__copied = null')
        pro.locator('#savedList .saved', has_text='Dana Whitfield').locator('button', has_text='Follow-up text').evaluate('e => e.click()')
        pro.wait_for_timeout(80)
        eq('options follow-up', read_copied(pro),
           'Hi Dana, this is Clearwater Exterior checking in on the quote for 18 Alder Court (options from $877.50). '
           'Happy to answer any questions or get you on the schedule. You can call or text me at 555-0100.')
        pro.locator('#savedList .saved', has_text='Dana Whitfield').locator('select').first.select_option('won')
        dana = pro.locator('#savedList .saved', has_text='Dana Whitfield')
        eq('choice select appears', dana.locator('select').count(), 2)
        dana.locator('select').nth(1).select_option('2')
        eq('won amount follows choice', (dana.locator('.sv-amt').text_content() or '').strip(), '$1,118.25')
        eq('won stat', txt(pro, '#stWon'), '$1,118')
        eq('waiting cleared', txt(pro, '#stOpen'), '$0')
        eq('rate all won', txt(pro, '#stRate'), '100%')

        tap(pro, '#newQuote')
        eq('new quote armed', txt(pro, '#newQuote'), 'Tap again to clear')
        tap(pro, '#newQuote')
        eq('blank toast', toast(pro), 'Blank quote ready.')
        eq('save label back', txt(pro, '#saveLabel'), 'Save quote')
        eq('blank total', txt(pro, '#totalAmt'), '$0.00')
        tap(pro, '#saveBtn')
        eq('empty save toast', toast(pro), 'Add a surface with a size first.')
        pro.fill('#customer', 'Sam Ortiz')
        pro.fill('#address', '9 Birch Lane')
        pro.locator('#lines .line input[id$="-qty"]').first.fill('500')
        eq('sam minimum job', txt(pro, '#totalAmt'), '$150.00')
        tap(pro, '#saveBtn')
        eq('two cards', pro.locator('#savedList .saved').count(), 2)
        sam = pro.locator('#savedList .saved', has_text='Sam Ortiz')
        sam.locator('select').first.select_option('lost')
        eq('rate half', txt(pro, '#stRate'), '50%')
        eq('won stat unchanged', txt(pro, '#stWon'), '$1,118')
        pro.evaluate('window.__copied = null')
        pro.locator('#savedList .saved', has_text='Sam Ortiz').locator('button', has_text='Follow-up text').evaluate('e => e.click()')
        pro.wait_for_timeout(80)
        eq('plain follow-up', read_copied(pro),
           'Hi Sam, this is Clearwater Exterior checking in on the quote for 9 Birch Lane ($150.00). '
           'Happy to answer any questions or get you on the schedule. You can call or text me at 555-0100.')

        tap(pro, '#newQuote')
        tap(pro, '#newQuote')
        pro.fill('#customer', 'Priya Nair')
        pro.locator('#lines .line input[id$="-qty"]').first.fill('1000')
        eq('priya total', txt(pro, '#totalAmt'), '$250.00')
        setc(pro.locator('#pkgOn'))
        pro.fill('#pkgBetterDisc', '50')
        eq('minimum applies after the discount', txt(pro, '#pkgBetterPrice'), '$150.00')
        has('savings counts the minimum', txt(pro, '#tOpts'), 'Bundle savings of $100.00')
        eq('better differs from good', pro.is_visible('#pkgBetterWarn'), False)
        setc(pro.locator('#pkgOn'), False)
        eq('total back to plain', txt(pro, '#totalLab'), 'Total')
        tap(pro, '#saveBtn')
        pro.locator('#savedList .saved', has_text='Priya Nair').locator('select').first.select_option('sent')
        eq('waiting priya', txt(pro, '#stOpen'), '$250')
        eq('rate still half', txt(pro, '#stRate'), '50%')
        eq('three cards', pro.locator('#savedList .saved').count(), 3)

    with section('pro: open, update, delete'):
        pro.locator('#savedList .saved', has_text='Dana Whitfield').locator('button', has_text='Open').evaluate('e => e.click()')
        pro.wait_for_timeout(120)
        eq('opened customer', pro.input_value('#customer'), 'Dana Whitfield')
        eq('opened packages on', pro.is_checked('#pkgOn'), True)
        eq('opened from label', txt(pro, '#totalLab'), 'From')
        eq('opened best price', txt(pro, '#pkgBestPrice'), '$1,118.25')
        eq('sealer pick survived reid', pro.locator('#pkgBestPicks .pkg-pick', has_text='Sealer').locator('input').is_checked(), True)
        eq('opened save label', txt(pro, '#saveLabel'), 'Update saved')
        pro.fill('#pkgBestDisc', '20')
        eq('best at twenty percent', txt(pro, '#pkgBestPrice'), '$994.00')
        tap(pro, '#saveBtn')
        eq('update toast', toast(pro), 'Saved quote updated.')
        eq('still three cards', pro.locator('#savedList .saved').count(), 3)
        dana = pro.locator('#savedList .saved', has_text='Dana Whitfield')
        eq('dana follows new choice price', (dana.locator('.sv-amt').text_content() or '').strip(), '$994.00')
        eq('won stat follows', txt(pro, '#stWon'), '$994')
        priya = pro.locator('#savedList .saved', has_text='Priya Nair')
        del_btn = priya.locator('.sv-actions button').nth(2)
        del_btn.evaluate('e => e.click()')
        eq('delete armed', (del_btn.text_content() or '').strip(), 'Tap again')
        del_btn.evaluate('e => e.click()')
        eq('two cards after delete', pro.locator('#savedList .saved').count(), 2)
        eq('waiting cleared after delete', txt(pro, '#stOpen'), '$0')

    backup = ''
    with section('pro: backup and persistence'):
        pro.evaluate('window.__copied = null')
        tap(pro, '#backupCopy')
        pro.wait_for_timeout(80)
        backup = read_copied(pro)
        data = json.loads(backup)
        eq('backup app', data['app'], 'rinse-quote')
        eq('backup count', len(data['saved']), 2)
        eq('backup toast', toast(pro), 'Backup copied. Paste it somewhere safe.')
        pro.wait_for_timeout(400)
        pro.reload()
        pro.wait_for_timeout(300)
        eq('cards persist', pro.locator('#savedList .saved').count(), 2)
        eq('stats persist', txt(pro, '#stWon'), '$994')

    with section('pro: long names and layout'):
        tap(pro, '#newQuote')
        tap(pro, '#newQuote')
        pro.fill('#customer', 'Bartholomew Featherstonehaugh-Wetherby III')
        pro.fill('#address', '1428 Elderberry Hollow Boulevard, Unit 22B, North Cheswick Heights')
        pro.locator('#lines .line input[id$="-qty"]').first.fill('800')
        tap(pro, '#addExtra')
        cx = pro.locator('#extraList .extra.custom')
        cx.locator('input.ctl').fill('Hand scrubbing of the stone retaining wall and steps')
        cx.locator('[id$="-price"]').fill('40')
        setc(pro.locator('#pkgOn'))
        setc(pro.locator('#pkgBestPicks .pkg-pick', has_text='Rust stain').locator('input'))
        pro.fill('#pkgBestDisc', '10')
        tap(pro, '#saveBtn')
        eq('three cards with long one', pro.locator('#savedList .saved').count(), 3)
        for w in (320, 390, 768, 1200):
            o = overflow(pro, w)
            eq('pro no overflow at %d' % w, (o['sw'] <= o['W'], o['bad']), (True, []))
        eq('pro bar hidden wide', pro.is_visible('#bar'), False)
        pro.set_viewport_size({'width': 390, 'height': 844})
        pro.wait_for_timeout(500)
        state_json = pro.evaluate("localStorage.getItem('rinse-quote-v1')")
        eq('state saved', bool(state_json), True)

    # ------------------------------------------------------------ 3 second device, hash unlock and restore
    ctx3, dev2 = new_page(browser, url_hash='#unlock-' + CODE)
    with section('device 2: hash unlock and restore'):
        dev2.wait_for_timeout(300)
        eq('hash unlock badge', dev2.is_visible('#proBadge'), True)
        eq('hash unlock toast', toast(dev2), 'Pro unlocked on this device.')
        tap(dev2, '#saveBtn')
        eq('local quote saved', dev2.locator('#savedList .saved').count(), 1)
        tap(dev2, '#restoreOpen')
        eq('restore box open', dev2.is_visible('#restoreBox'), True)
        dev2.fill('#restoreText', 'nope')
        tap(dev2, '#restoreGo')
        eq('bad backup msg', txt(dev2, '#restoreMsg'), 'That does not look like a backup.')
        dev2.fill('#restoreText', '{"saved": []}')
        tap(dev2, '#restoreGo')
        eq('empty backup msg', txt(dev2, '#restoreMsg'), 'No quotes found in that backup.')
        dev2.fill('#restoreText', backup)
        tap(dev2, '#restoreGo')
        eq('restored toast', toast(dev2), 'Restored 2 quotes.')
        eq('three cards after restore', dev2.locator('#savedList .saved').count(), 3)
        ids = dev2.eval_on_selector_all('#savedList .saved', 'els => els.map(e => e.id)')
        eq('ids are unique', len(set(ids)), len(ids))
        eq('restore box closed', dev2.is_visible('#restoreBox'), False)
        tap(dev2, '#restoreOpen')
        dev2.fill('#restoreText', backup)
        tap(dev2, '#restoreGo')
        eq('duplicate restore toast', toast(dev2), 'Those quotes are already here.')
        eq('still three cards', dev2.locator('#savedList .saved').count(), 3)
        eq('restored dana amount', (dev2.locator('#savedList .saved', has_text='Dana Whitfield').locator('.sv-amt').text_content() or '').strip(), '$994.00')

    ctx3b, dev3 = new_page(browser, url_hash='#unlock-RINSE-NOPE-0000')
    with section('device 3: wrong hash stays locked'):
        dev3.wait_for_timeout(300)
        eq('wrong hash locked', dev3.is_visible('#proCard'), True)
        eq('wrong hash no badge', dev3.is_visible('#proBadge'), False)
    ctx3c, dev4 = new_page(browser, url_hash='#pricing')
    with section('device 4: unrelated hash'):
        dev4.wait_for_timeout(200)
        eq('unrelated hash locked', dev4.is_visible('#proCard'), True)

    # ------------------------------------------------------------ 4 copy fallback
    ctx4, fb = new_page(browser, stub=STUB_REJECT)
    with section('copy fallback sheet'):
        tap(fb, '#copyBtn')
        fb.wait_for_timeout(150)
        eq('sheet shown', fb.is_visible('#sheet'), True)
        has('sheet text', fb.input_value('#sheetText'), 'Total: $877.50')
        tap(fb, '#sheetClose')
        eq('sheet closed', fb.is_visible('#sheet'), False)

    # ------------------------------------------------------------ 5 dark theme, pro state
    dctx, dark = new_page(browser, scheme='dark', pre_state=state_json if 'state_json' in dir() else None)
    with section('dark theme'):
        dark.add_style_tag(content='.bar,.toast{display:none!important}')
        cols = dark.evaluate('''() => ({
            bg: getComputedStyle(document.body).backgroundColor,
            ink: getComputedStyle(document.body).color,
            ticket: getComputedStyle(document.querySelector('#ticket')).backgroundColor,
            scheme: getComputedStyle(document.documentElement).colorScheme
        })''')
        eq('dark bg', cols['bg'], 'rgb(11, 22, 27)')
        eq('dark ink', cols['ink'], 'rgb(229, 238, 241)')
        eq('dark ticket', cols['ticket'], 'rgb(18, 35, 42)')
        eq('dark color-scheme', cols['scheme'], 'dark')
        eq('dark pro state loaded', dark.is_visible('#proBadge'), True)
        dark.screenshot(path=D + '/rq-dark-top.png')
        dark.locator('.total-card').screenshot(path=D + '/rq-dark-total.png')
        dark.locator('#ticket').screenshot(path=D + '/rq-dark-ticket.png')
        dark.locator('#secPackages').screenshot(path=D + '/rq-dark-pkg.png')
        dark.locator('#secSaved').screenshot(path=D + '/rq-dark-saved.png')

    # ------------------------------------------------------------ 6 standalone: privacy page, light and dark
    if STANDALONE:
        for scheme in ('light', 'dark'):
            pctx = browser.new_context(viewport={'width': 390, 'height': 844}, color_scheme=scheme, device_scale_factor=1)
            pp = pctx.new_page()
            pp.set_default_timeout(4000)
            pp.on('console', lambda m: errs.append((m.type, m.text)) if m.type in ('error', 'warning') else None)
            pp.on('pageerror', lambda e: errs.append(('pageerror', str(e))))
            pp.on('request', lambda r: ext_reqs.append(r.url) if not (r.url.startswith(ORIGIN + '/') or r.url.startswith(('data:', 'blob:'))) else None)
            resp = pp.goto(ORIGIN + PAGE_PATH + 'privacy.html')
            pp.wait_for_timeout(200)
            with section('privacy page (%s)' % scheme):
                eq('status', resp.status, 200)
                eq('title', pp.title(), 'Privacy Policy - Rinse Quote')
                eq('h1', txt(pp, 'h1'), 'Privacy policy')
                has('short version', txt(pp, 'main'), 'They are never sent to us.')
                has('updated line', txt(pp, '.updated'), 'last updated September 2026')
                eq('contact mailto', pp.get_attribute('main a[href^="mailto:"]', 'href'), 'mailto:' + SUPPORT)
                eq('back link', pp.get_attribute('.back', 'href'), './')
                eq('brand link', pp.get_attribute('.brand', 'href'), './')
                faces = pp.evaluate('''async () => {
                    const out = [];
                    for (const f of [...document.fonts]) {
                        try { await f.load(); out.push(f.family.replace(/["']/g, '') + ' ' + f.weight + ' ' + f.status); }
                        catch (e) { out.push(f.family + ' ' + f.weight + ' ERROR ' + e.message); }
                    }
                    return out;
                }''')
                eq('privacy faces declared', len(faces), 4)
                eq('privacy faces load', [r for r in faces if not r.endswith(' loaded')], [])
                eq('privacy background', pp.evaluate('getComputedStyle(document.body).backgroundColor'),
                   'rgb(232, 237, 239)' if scheme == 'light' else 'rgb(11, 22, 27)')
                eq('privacy no em dash', '\u2014' in (pp.text_content('body') or ''), False)
                eq('privacy no claude mention', 'claude' in (pp.text_content('body') or '').lower(), False)
                for w in (320, 390, 768, 1200):
                    o = overflow(pp, w)
                    eq('privacy no overflow at %d (%s)' % (w, scheme), (o['sw'] <= o['W'], o['bad']), (True, []))
                pp.set_viewport_size({'width': 390, 'height': 844})
                pp.wait_for_timeout(120)
                pp.screenshot(path=D + '/rq-privacy-%s.png' % scheme, full_page=True)
            pctx.close()
        eq('no request leaves the site', sorted(set(ext_reqs)), [])

    real_errs = list(errs) if STANDALONE else [e for e in errs if 'ERR_FAILED' not in e[1] and 'fonts.g' not in e[1]]
    eq('console errors', real_errs, [])
    browser.close()

httpd.shutdown()
print('passed', passes, 'failed', len(fails), '| PRO_LINK set:', bool(PRO_LINK))
for f in fails:
    print('FAIL', f)
