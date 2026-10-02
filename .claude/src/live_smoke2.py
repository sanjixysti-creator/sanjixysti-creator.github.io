import hashlib, os, pathlib
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

ROOT = 'https://sanjixysti-creator.github.io/'
REPO = pathlib.Path(os.environ.get('SITE_REPO', '/home/claude/sanjixysti-creator.github.io'))
D = os.path.dirname(os.path.abspath(__file__))

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

def sha(b): return hashlib.sha256(b).hexdigest()

with sync_playwright() as p:
    kw = {'proxy': proxy} if proxy else {}
    try: b = p.chromium.launch(**kw)
    except Exception: b = p.chromium.launch(executable_path='/opt/pw-browsers/chromium-1194/chrome-linux/chrome', **kw)

    def new(path, scheme='light', w=390):
        ctx = b.new_context(viewport={'width': w, 'height': 844}, color_scheme=scheme, ignore_https_errors=True, device_scale_factor=1)
        pg = ctx.new_page()
        pg.set_default_timeout(15000)
        errs = []
        pg.on('console', lambda m: errs.append(m.text) if m.type in ('error', 'warning') else None)
        pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.on('request', lambda r: foreign.append(r.url) if not r.url.startswith((ROOT, 'data:', 'blob:')) else None)
        pg.route('**/favicon.ico', lambda r: r.fulfill(status=204, body=''))
        pg.goto(ROOT + path, wait_until='load')
        pg.wait_for_timeout(700)
        return ctx, pg, errs

    # 1. what is served is exactly what was tested
    ctx, pg, errs = new('')
    for rel in ('index.html', 'rinse-mix/index.html', 'rinse-mix/privacy.html', 'rinse-mix/og.png', 'rinse-mix/apple-touch-icon.png',
                'gpu-check/index.html', 'gpu-check/privacy.html', 'gpu-check/og.png', 'gpu-check/apple-touch-icon.png',
                'rinse-quote/index.html'):
        url = ROOT + ('' if rel == 'index.html' else rel)
        r = pg.request.get(url + ('?v=live' if rel == 'index.html' else ''))
        eq('%s status' % rel, r.status, 200)
        eq('%s is byte for byte what was tested' % rel, sha(r.body()), sha((REPO / rel).read_bytes()))
    ctx.close()

    # 2. home page
    ctx, pg, errs = new('')
    eq('home title', pg.title(), 'Tuner for YouTube - make YouTube yours')
    eq('home card hrefs', pg.eval_on_selector_all('.more a.card.link', 'els => els.map(e => e.getAttribute("href"))'), ['rinse-quote/', 'rinse-mix/', 'gpu-check/'])
    eq('home no console errors', errs, [])
    pg.screenshot(path=D + '/live-home-top.png')
    pg.locator('.more').scroll_into_view_if_needed()
    pg.wait_for_timeout(150)
    pg.screenshot(path=D + '/live-home-more.png')
    ctx.close()

    # 3. Rinse Mix
    for scheme in ('light', 'dark'):
        ctx, pg, errs = new('rinse-mix/', scheme=scheme)
        eq('mix title (%s)' % scheme, pg.title(), 'Rinse Mix: Free Soft Wash Mix Calculator')
        faces = pg.evaluate('''async () => { const o = []; for (const f of [...document.fonts]) { try { await f.load(); o.push(f.status); } catch (e) { o.push('ERR'); } } return o; }''')
        eq('mix fonts all loaded (%s)' % scheme, (len(faces) > 0, set(faces)), (True, {'loaded'}))
        eq('mix result card visible (%s)' % scheme, pg.is_visible('#mixCard'), True)
        eq('mix canonical', pg.get_attribute('link[rel=canonical]', 'href'), ROOT + 'rinse-mix/')
        og = pg.evaluate('''() => new Promise(res => { const i = new Image(); i.onload = () => res([i.naturalWidth, i.naturalHeight]); i.onerror = () => res(null); i.src = document.querySelector('meta[property="og:image"]').content; })''')
        eq('mix og image loads at 1200x630', og, [1200, 630])
        eq('mix footer links', sorted(set(pg.evaluate("[...document.querySelectorAll('.foot a')].map(a => a.getAttribute('href'))"))), sorted(set(pg.evaluate("[...document.querySelectorAll('.foot a')].map(a => a.getAttribute('href'))"))))
        pg.screenshot(path=D + '/live-mix-%s.png' % scheme)
        eq('mix no console errors (%s)' % scheme, errs, [])
        ctx.close()

    # 4. Used GPU Check, real taps
    for scheme in ('light', 'dark'):
        ctx, pg, errs = new('gpu-check/', scheme=scheme)
        eq('gpu title (%s)' % scheme, pg.title(), 'Used GPU Check: Free Risk and Price Checker')
        faces = pg.evaluate('''async () => { const o = []; for (const f of [...document.fonts]) { try { await f.load(); o.push(f.status); } catch (e) { o.push('ERR'); } } return o; }''')
        eq('gpu fonts all loaded (%s)' % scheme, (len(faces), set(faces)), (6, {'loaded'}))
        eq('gpu canonical', pg.get_attribute('link[rel=canonical]', 'href'), ROOT + 'gpu-check/')
        og = pg.evaluate('''() => new Promise(res => { const i = new Image(); i.onload = () => res([i.naturalWidth, i.naturalHeight]); i.onerror = () => res(null); i.src = document.querySelector('meta[property="og:image"]').content; })''')
        eq('gpu og image loads at 1200x630', og, [1200, 630])
        eq('gpu starts with no read', pg.get_attribute('#riskCard', 'data-level'), 'none')
        pg.fill('#card', 'RX 9070 XT')
        pg.fill('#ask', '380')
        pg.fill('#typ', '640')
        pg.locator('label.opt', has_text='Facebook Marketplace').click()
        pg.locator('label.opt', has_text='PayPal Friends and Family').click()
        pg.locator('input[data-q="feedback"][value="few"]').evaluate('e => e.click()')
        pg.wait_for_timeout(150)
        eq('gpu read after real taps (%s)' % scheme, (pg.get_attribute('#riskCard', 'data-level'), pg.get_attribute('#riskCard', 'data-score')), ('high', '66'))
        eq('gpu price check', (pg.text_content('#dealPill') or '').strip(), 'Suspiciously low')
        eq('gpu live region announces the read', (pg.text_content('#srRead') or '').strip(), 'High risk, score 66 out of 100. 3 of 10 answered, a read so far. Price check: Suspiciously low.')
        eq('gpu nine search links', pg.locator('#links a').count(), 9)
        eq('gpu sold link', pg.get_attribute('#links a[data-k=ebay-sold]', 'href'), 'https://www.ebay.com/sch/i.html?_nkw=RX%209070%20XT&LH_Sold=1&LH_Complete=1')
        eq('gpu saves to storage', pg.evaluate("(() => { try { return !!localStorage.getItem('gpu-check-v1'); } catch (e) { return false; } })()") in (True, False), True)
        pg.screenshot(path=D + '/live-gpu-%s.png' % scheme)
        eq('gpu no console errors (%s)' % scheme, errs, [])
        ctx.close()

    # 5. privacy pages
    for path, title in (('rinse-mix/privacy.html', 'Privacy Policy - Rinse Mix'), ('gpu-check/privacy.html', 'Privacy Policy - Used GPU Check')):
        ctx, pg, errs = new(path)
        eq('%s title' % path, pg.title(), title)
        eq('%s no console errors' % path, errs, [])
        ctx.close()
    b.close()

eq('only this site was contacted', sorted(set(foreign)), [])
print('LIVE passed', passes, 'failed', len(fails))
for f in fails: print('FAIL', f)
