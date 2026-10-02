import os, re, sys
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

BASE = 'https://sanjixysti-creator.github.io/rinse-quote/'
D = os.path.dirname(os.path.abspath(__file__))
CODE = re.search(r'code=([A-Z0-9\-]+)', open(D + '/pro-code.txt').read()).group(1)

px = urlparse(os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy') or '')
proxy = None
if px.hostname:
    proxy = {'server': '%s://%s:%s' % (px.scheme or 'http', px.hostname, px.port or 80)}
    if px.username:
        proxy['username'] = px.username
        proxy['password'] = px.password or ''

fails, passes, foreign = [], 0, []
def eq(name, got, want):
    global passes
    if got == want: passes += 1
    else: fails.append('%s\n    got:  %r\n    want: %r' % (name, got, want))

with sync_playwright() as p:
    try:
        b = p.chromium.launch(proxy=proxy) if proxy else p.chromium.launch()
    except Exception:
        b = p.chromium.launch(executable_path='/opt/pw-browsers/chromium-1194/chrome-linux/chrome', proxy=proxy) if proxy else p.chromium.launch(executable_path='/opt/pw-browsers/chromium-1194/chrome-linux/chrome')

    def new(hash_='', path='', scheme='light'):
        ctx = b.new_context(viewport={'width': 390, 'height': 844}, color_scheme=scheme, ignore_https_errors=True, device_scale_factor=1)
        pg = ctx.new_page()
        pg.set_default_timeout(15000)
        errs = []
        pg.on('console', lambda m: errs.append(m.text) if m.type in ('error', 'warning') else None)
        pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.on('request', lambda r: foreign.append(r.url) if not r.url.startswith(('https://sanjixysti-creator.github.io/', 'data:', 'blob:')) else None)
        pg.goto(BASE + path + hash_, wait_until='load')
        pg.wait_for_timeout(600)
        return ctx, pg, errs

    # 1. fresh visitor
    ctx, pg, errs = new()
    eq('title', pg.title(), 'Rinse Quote: Free Pressure Washing Quote Calculator')
    eq('sample total', (pg.text_content('#totalAmt') or '').strip(), '$877.50')
    eq('pro badge hidden', pg.is_visible('#proBadge'), False)
    eq('pro card shown', pg.is_visible('#proCard'), True)
    eq('secure context', pg.evaluate('window.isSecureContext'), True)
    faces = pg.evaluate('''async () => { const o = []; for (const f of [...document.fonts]) { try { await f.load(); o.push(f.status); } catch (e) { o.push('ERR'); } } return o; }''')
    eq('all 8 fonts loaded', faces, ['loaded'] * 8)
    eq('get pro link', pg.get_attribute('#getPro', 'href'), 'https://buy.stripe.com/eVqbJ15fQ5mx4Ru7txcV200')
    eq('footer maker', 'Made by Xysti Software.' in (pg.text_content('.foot') or ''), True)
    eq('privacy link resolves', pg.evaluate("new URL(document.querySelector('.foot a[href=\"privacy.html\"]').href).href"), BASE + 'privacy.html')
    og = pg.evaluate('''() => new Promise(res => { const i = new Image(); i.onload = () => res([i.naturalWidth, i.naturalHeight]); i.onerror = () => res(null); i.src = document.querySelector('meta[property="og:image"]').content; })''')
    eq('og image loads at 1200x630', og, [1200, 630])
    pg.screenshot(path=D + '/live-top.png')
    eq('no console errors (fresh)', errs, [])
    ctx.close()

    # 2. the link buyers get after paying
    ctx, pg, errs = new(hash_='#unlock-' + CODE)
    eq('unlock link: badge visible', pg.is_visible('#proBadge'), True)
    eq('unlock link: packages visible', pg.is_visible('#secPackages'), True)
    eq('unlock link: toast', (pg.text_content('#toast') or '').strip(), 'Pro unlocked on this device.')
    pg.screenshot(path=D + '/live-unlocked.png')
    pg.reload(wait_until='load'); pg.wait_for_timeout(400)
    eq('unlock persists after reload', pg.is_visible('#proBadge'), True)
    eq('no console errors (unlock)', errs, [])
    ctx.close()

    # 3. wrong code
    ctx, pg, errs = new(hash_='#unlock-RINSE-NOPE-0000')
    eq('wrong link stays locked', pg.is_visible('#proBadge'), False)
    ctx.close()

    # 4. manual code entry path
    ctx, pg, errs = new()
    pg.locator('#haveCode').evaluate('e => e.click()')
    pg.fill('#codeInput', CODE.lower())
    pg.locator('#codeForm button[type=submit], #codeForm .btn').first.evaluate('e => e.click()')
    pg.wait_for_timeout(500)
    eq('typed code unlocks (lowercase ok)', pg.is_visible('#proBadge'), True)
    ctx.close()

    # 5. privacy page, dark
    ctx, pg, errs = new(path='privacy.html', scheme='dark')
    eq('privacy title', pg.title(), 'Privacy Policy - Rinse Quote')
    eq('privacy h1', (pg.text_content('h1') or '').strip(), 'Privacy policy')
    eq('privacy dark bg', pg.evaluate('getComputedStyle(document.body).backgroundColor'), 'rgb(11, 22, 27)')
    eq('no console errors (privacy)', errs, [])
    ctx.close()
    b.close()

eq('requests only to your site', sorted(set(foreign)), [])
print('LIVE passed', passes, 'failed', len(fails))
for f in fails: print('FAIL', f)
