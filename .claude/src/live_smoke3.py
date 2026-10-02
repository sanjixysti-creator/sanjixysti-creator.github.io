import hashlib, os, pathlib, re, subprocess
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

fails, passes, foreign, errs = [], 0, [], []
def eq(name, got, want):
    global passes
    if got == want: passes += 1
    else: fails.append('%s\n    got:  %r\n    want: %r' % (name, got, want))
def sha(b): return hashlib.sha256(b).hexdigest()

TITLES = {
    '': 'Xysti Software: Small Free Tools for Specific Jobs',
    'tuner/': 'Tuner for YouTube - make YouTube yours',
    'rinse-quote/': 'Rinse Quote: Free Pressure Washing Quote Calculator',
    'rinse-mix/': 'Rinse Mix: Free Soft Wash Mix Calculator',
    'gpu-check/': 'Used GPU Check: Free Risk and Price Checker',
}

with sync_playwright() as p:
    kw = {'proxy': proxy} if proxy else {}
    try: b = p.chromium.launch(**kw)
    except Exception: b = p.chromium.launch(executable_path='/opt/pw-browsers/chromium-1194/chrome-linux/chrome', **kw)

    def new(path='', scheme='light', w=390):
        ctx = b.new_context(viewport={'width': w, 'height': 844}, color_scheme=scheme, ignore_https_errors=True, device_scale_factor=1)
        pg = ctx.new_page()
        pg.set_default_timeout(15000)
        pg.on('console', lambda m: errs.append((path, m.text)) if m.type in ('error', 'warning') else None)
        pg.on('pageerror', lambda e: errs.append((path, str(e))))
        pg.on('request', lambda r: foreign.append(r.url) if not r.url.startswith((ROOT, 'data:', 'blob:')) else None)
        pg.route('**/favicon.ico', lambda r: r.fulfill(status=204, body=''))
        pg.goto(ROOT + path + ('?live=1' if path == '' else ''), wait_until='load')
        pg.wait_for_timeout(600)
        return ctx, pg

    # 1. served bytes equal the files that were tested
    ctx, pg = new('')
    for rel in ('index.html', 'og.png', 'apple-touch-icon.png', 'tuner/index.html', 'privacy.html',
                'rinse-quote/index.html', 'rinse-quote/privacy.html', 'rinse-mix/index.html', 'rinse-mix/privacy.html',
                'gpu-check/index.html', 'gpu-check/privacy.html'):
        url = ROOT + ('?v=bytes' if rel == 'index.html' else rel)
        r = pg.request.get(url)
        eq('%s status' % rel, r.status, 200)
        eq('%s is byte for byte what was tested' % rel, sha(r.body()), sha((REPO / rel).read_bytes()))
    # the policy the store listing points at is what it was before today
    old = subprocess.check_output(['git', '-C', str(REPO), 'show', 'a720c88:privacy.html'])
    eq('privacy.html unchanged since before the move', sha(pg.request.get(ROOT + 'privacy.html').body()), sha(old))
    # the hidden notes are not served anywhere
    for u in ('.claude/CLAUDE.md', 'claude/CLAUDE.md', 'CLAUDE.md', '.claude/', '.claude'):
        eq('%s is not public' % u, pg.request.get(ROOT + u + '?x=1').status, 404)
    eq('no notes text leaks into any page', any('Notes for Claude' in pg.request.get(ROOT + u).text() for u in ('', 'tuner/', 'rinse-quote/', 'rinse-mix/', 'gpu-check/')), False)
    ctx.close()

    # 2. each page loads cleanly
    for path, title in TITLES.items():
        for scheme in ('light', 'dark'):
            ctx, pg = new(path, scheme=scheme)
            eq('%s title (%s)' % (path or '/', scheme), pg.title(), title)
            ctx.close()

    # 3. the hub, as a visitor sees it
    for scheme in ('light', 'dark'):
        ctx, pg = new('', scheme=scheme)
        faces = pg.evaluate('''async () => { const o = []; for (const f of [...document.fonts]) { try { await f.load(); o.push(f.status); } catch (e) { o.push('ERR'); } } return o; }''')
        eq('hub fonts loaded (%s)' % scheme, faces, ['loaded'] * 3)
        eq('hub rows (%s)' % scheme, pg.eval_on_selector_all('.row h3 a', 'els => els.map(e => e.textContent.trim())'), ['Rinse Quote', 'Rinse Mix', 'Used GPU Check', 'Tuner for YouTube'])
        og = pg.evaluate('''() => new Promise(res => { const i = new Image(); i.onload = () => res([i.naturalWidth, i.naturalHeight]); i.onerror = () => res(null); i.src = document.querySelector('meta[property="og:image"]').content; })''')
        eq('hub share image loads at 1200x630 (%s)' % scheme, og, [1200, 630])
        eq('hub canonical', pg.get_attribute('link[rel=canonical]', 'href'), ROOT)
        eq('hub no sideways scroll (%s)' % scheme, pg.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth'), True)
        pg.screenshot(path=D + '/live-hub-%s.png' % scheme, full_page=(scheme == 'light'))
        ctx.close()

    # 4. click through from the hub to every tool and back by the site's own links
    for i, path in enumerate(['rinse-quote/', 'rinse-mix/', 'gpu-check/', 'tuner/']):
        title = TITLES[path]
        ctx, pg = new('')
        pg.locator('.row h3 a').nth(i).click()
        pg.wait_for_url(ROOT + path)
        eq('hub opens %s' % path, pg.title(), title)
        ctx.close()
    ctx, pg = new('tuner/')
    pg.locator('header nav a', has_text='All tools').click()
    pg.wait_for_url(ROOT)
    eq('Tuner links back to the hub', pg.title(), TITLES[''])
    pg.goto(ROOT + 'tuner/')
    pg.locator('header nav a', has_text='Privacy').click()
    pg.wait_for_url(ROOT + 'privacy.html')
    eq('Tuner privacy link opens the policy', pg.title(), 'Privacy policy - Tuner for YouTube')
    ctx.close()

    # 5. the GPU checker still works end to end from the live site
    ctx, pg = new('gpu-check/')
    pg.fill('#card', 'RX 9070 XT'); pg.fill('#ask', '380'); pg.fill('#typ', '640')
    pg.locator('label.opt', has_text='Facebook Marketplace').click()
    pg.locator('label.opt', has_text='PayPal Friends and Family').click()
    pg.locator('input[data-q="feedback"][value="few"]').evaluate('e => e.click()')
    pg.wait_for_timeout(150)
    eq('gpu read after real taps', (pg.get_attribute('#riskCard', 'data-level'), pg.get_attribute('#riskCard', 'data-score')), ('high', '66'))
    ctx.close()
    b.close()

eq('no console errors on any live page', errs, [])
eq('only this site was contacted', sorted(set(foreign)), [])
print('LIVE passed', passes, 'failed', len(fails))
for f in fails: print('FAIL', f)
