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
    'rinse-rate/': 'Rinse Rate: Pressure Washing Job Profit Calculator',
    'drive-rate/': 'Drive Rate: Is This Delivery Offer Worth It? Free Calculator',
    'gpu-check/': 'Used GPU Check: Free Risk and Price Checker',
    'grime-time/': 'Grime Time: Free Pressure Washing Game, Idle and Satisfying',
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
                'rinse-rate/index.html', 'rinse-rate/privacy.html', 'rinse-rate/og.png', 'rinse-rate/apple-touch-icon.png',
                'drive-rate/index.html', 'drive-rate/privacy.html', 'drive-rate/og.png', 'drive-rate/apple-touch-icon.png',
                'grime-time/index.html', 'grime-time/privacy.html', 'grime-time/og.png', 'grime-time/apple-touch-icon.png',
                'gpu-check/index.html', 'gpu-check/privacy.html', '404.html', 'sitemap.xml', 'robots.txt'):
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
    eq('no notes text leaks into any page', any('Notes for Claude' in pg.request.get(ROOT + u).text() for u in ('', 'tuner/', 'rinse-quote/', 'rinse-mix/', 'rinse-rate/', 'drive-rate/', 'gpu-check/', 'grime-time/')), False)
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
        eq('hub rows (%s)' % scheme, pg.eval_on_selector_all('.row h3 a', 'els => els.map(e => e.textContent.trim())'), ['Rinse Quote', 'Rinse Mix', 'Rinse Rate', 'Drive Rate', 'Used GPU Check', 'Tuner for YouTube', 'Grime Time'])
        og = pg.evaluate('''() => new Promise(res => { const i = new Image(); i.onload = () => res([i.naturalWidth, i.naturalHeight]); i.onerror = () => res(null); i.src = document.querySelector('meta[property="og:image"]').content; })''')
        eq('hub share image loads at 1200x630 (%s)' % scheme, og, [1200, 630])
        eq('hub canonical', pg.get_attribute('link[rel=canonical]', 'href'), ROOT)
        eq('hub no sideways scroll (%s)' % scheme, pg.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth'), True)
        pg.screenshot(path=D + '/live-hub-%s.png' % scheme, full_page=(scheme == 'light'))
        ctx.close()

    # 4. click through from the hub to every tool and back by the site's own links
    for i, path in enumerate(['rinse-quote/', 'rinse-mix/', 'rinse-rate/', 'drive-rate/', 'gpu-check/', 'tuner/', 'grime-time/']):
        title = TITLES[path]
        ctx, pg = new('')
        pg.locator('.row h3 a').nth(i).click()
        pg.wait_for_url(ROOT + path)
        eq('hub opens %s' % path, pg.title(), title)
        ctx.close()
    for path in ('rinse-quote/', 'rinse-mix/', 'rinse-rate/', 'drive-rate/', 'gpu-check/', 'grime-time/'):
        ctx, pg = new(path)
        pg.locator('.foot a[href="https://sanjixysti-creator.github.io/"]').click()
        pg.wait_for_url(ROOT)
        eq('%s links back to the hub' % path, pg.title(), TITLES[''])
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

    # 6. Rinse Rate works end to end from the live site, with real typing
    ctx, pg = new('rinse-rate/')
    eq('rate opens on its example job', (pg.inner_text('#payNum'), pg.inner_text('#needText')),
       ('$36.71', 'To earn $50.00 an hour on this job, charge $359.'))
    pg.click('#exampleClear')
    pg.fill('#price', '450'); pg.fill('#onsite', '4'); pg.fill('#chem', '20')
    pg.wait_for_timeout(200)
    eq('rate reads a typed job', (pg.inner_text('#payNum'), pg.inner_text('#vProfit'), pg.inner_text('#vMargin'), pg.inner_text('#vHours')),
       ('$87.91', '$351.65', '78.1%', '4 h'))
    eq('rate has no sideways scroll', pg.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth'), True)
    pg.screenshot(path=D + '/live-rate.png')
    ctx.close()
    ctx, pg = new('rinse-rate/', scheme='dark')
    pg.screenshot(path=D + '/live-rate-dark.png')
    og = pg.evaluate('''() => new Promise(res => { const i = new Image(); i.onload = () => res([i.naturalWidth, i.naturalHeight]); i.onerror = () => res(null); i.src = document.querySelector('meta[property="og:image"]').content; })''')
    eq('rate share image loads at 1200x630', og, [1200, 630])
    eq('rate canonical', pg.get_attribute('link[rel=canonical]', 'href'), ROOT + 'rinse-rate/')
    ctx.close()

    # 6b. Drive Rate works end to end from the live site, with real typing
    ctx, pg = new('drive-rate/')
    eq('drive opens on its example offer', (pg.text_content('#vWord').strip(), pg.inner_text('#vHour'), pg.inner_text('#needVal')),
       ('Pass', '$8.88', '$12.25'))
    pg.click('#exampleClear')
    pg.wait_for_timeout(150)
    eq('drive starts blank', pg.text_content('#vWord').strip(), 'Add an offer')
    pg.fill('#pay', '12'); pg.fill('#miles', '3'); pg.fill('#minutes', '20')
    pg.wait_for_timeout(250)
    eq('drive reads a typed offer', (pg.text_content('#vWord').strip(), pg.inner_text('#vHour'), pg.inner_text('#vMile'), pg.inner_text('#needVal')),
       ('Take it', '$32.99', '$4.00', '$7.68'))
    eq('drive has no sideways scroll', pg.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth'), True)
    pg.screenshot(path=D + '/live-drive.png')
    ctx.close()
    ctx, pg = new('drive-rate/', scheme='dark')
    pg.screenshot(path=D + '/live-drive-dark.png')
    og = pg.evaluate('''() => new Promise(res => { const i = new Image(); i.onload = () => res([i.naturalWidth, i.naturalHeight]); i.onerror = () => res(null); i.src = document.querySelector('meta[property="og:image"]').content; })''')
    eq('drive share image loads at 1200x630', og, [1200, 630])
    eq('drive canonical', pg.get_attribute('link[rel=canonical]', 'href'), ROOT + 'drive-rate/')
    ctx.close()

    # 6c. Grime Time works from the live site with real mouse strokes (a normal visit has no test hooks)
    ctx, pg = new('grime-time/')
    pg.wait_for_timeout(1000)
    eq('grime opens on the tutorial driveway', (pg.evaluate("() => !document.getElementById('wash').hidden"), pg.inner_text('#wName').lower(), pg.inner_text('#wPct').strip(), pg.evaluate('() => typeof window.__grime')),
       (True, 'oil stained driveway', '0%', 'undefined'))
    box = pg.locator('#cFx').bounding_box()
    gx0, gx1 = box['x'] + box['width'] * 0.12, box['x'] + box['width'] * 0.88
    for row in range(6):
        gy = box['y'] + box['height'] * (0.30 + 0.07 * row)
        ga, gb = (gx0, gx1) if row % 2 == 0 else (gx1, gx0)
        pg.mouse.move(ga, gy)
        if row == 0:
            pg.mouse.down()
        for k in range(1, 25):
            pg.mouse.move(ga + (gb - ga) * k / 24, gy)
            pg.wait_for_timeout(10)
    pg.mouse.up()
    eq('grime real mouse strokes clean the driveway', int(re.search(r'\d+', pg.inner_text('#wPct')).group(0)) > 3, True)
    eq('grime has no sideways scroll', pg.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth'), True)
    pg.screenshot(path=D + '/live-grime.png')
    ctx.close()
    ctx, pg = new('grime-time/', scheme='dark')
    pg.screenshot(path=D + '/live-grime-dark.png')
    og = pg.evaluate('''() => new Promise(res => { const i = new Image(); i.onload = () => res([i.naturalWidth, i.naturalHeight]); i.onerror = () => res(null); i.src = document.querySelector('meta[property="og:image"]').content; })''')
    eq('grime share image loads at 1200x630', og, [1200, 630])
    eq('grime canonical', pg.get_attribute('link[rel=canonical]', 'href'), ROOT + 'grime-time/')
    ctx.close()
    ctx, pg = new('grime-time/privacy.html')
    eq('grime privacy page opens', pg.title(), 'Privacy Policy - Grime Time')
    ctx.close()

    # 7. the sitemap lists it, and a missing address still gets the not-found page
    ctx, pg = new('')
    eq('sitemap lists rinse-rate, drive-rate and grime-time', [ROOT + 'rinse-rate/' in pg.request.get(ROOT + 'sitemap.xml?x=1').text(), ROOT + 'drive-rate/' in pg.request.get(ROOT + 'sitemap.xml?x=2').text(), ROOT + 'grime-time/' in pg.request.get(ROOT + 'sitemap.xml?x=3').text()], [True, True, True])
    r = pg.request.get(ROOT + 'no/such/page/at/this/depth')
    eq('a missing address answers 404 with the page', (r.status, 'Nothing here.' in r.text()), (404, True))
    ctx.close()
    b.close()

eq('no console errors on any live page', errs, [])
eq('only this site was contacted', sorted(set(foreign)), [])
print('LIVE passed', passes, 'failed', len(fails))
for f in fails: print('FAIL', f)
