"""QR Forever browser tests, part D: layout at every width, contrast, tap targets, keyboard, fonts, metadata and the privacy page."""
import os, re, struct, time

from qr_harness import *  # noqa: F401,F403
import qr_harness as H
from qr_test import fill_form

WIDTHS = (320, 360, 390, 414, 600, 719, 720, 768, 899, 900, 1024, 1280, 1920)

CONTRAST_JS = '''() => {
    const parse = c => { const m = c.match(/rgba?\\(([^)]+)\\)/); if (!m) return null; const p = m[1].split(/[ ,\\/]+/).filter(Boolean).map(parseFloat); return {r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1}; };
    const lin = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    const lum = c => 0.2126 * lin(c.r) + 0.7152 * lin(c.g) + 0.0722 * lin(c.b);
    const over = (f, b) => ({r: f.r * f.a + b.r * (1 - f.a), g: f.g * f.a + b.g * (1 - f.a), b: f.b * f.a + b.b * (1 - f.a), a: 1});
    const bgOf = el => { const stack = []; while (el) { const c = parse(getComputedStyle(el).backgroundColor); if (c && c.a > 0) { stack.push(c); if (c.a >= 1) break; } el = el.parentElement; }
        let base = {r: 255, g: 255, b: 255, a: 1}; for (let i = stack.length - 1; i >= 0; i--) base = over(stack[i], base); return base; };
    const describe = el => el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\\s+/).join('.') : '');
    const need = cs => { const px = parseFloat(cs.fontSize), wt = parseInt(cs.fontWeight, 10); return (px >= 24 || (px >= 18.66 && wt >= 700)) ? 3 : 4.5; };
    const ratio = (f, b) => { const x = lum(f), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
    const out = []; let checked = 0;
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
        const n = walker.currentNode, t = n.textContent.trim();
        if (!t) continue;
        const el = n.parentElement;
        if (!el || el.closest('script,style,noscript,.printarea,[hidden],option,[aria-disabled="true"]')) continue;
        if (!el.getClientRects().length) continue;
        const cs = getComputedStyle(el);
        if (cs.visibility === 'hidden') continue;
        let fg = parse(cs.color); const bg = bgOf(el);
        if (fg.a < 1) fg = over(fg, bg);
        const r = ratio(fg, bg); checked++;
        if (r < need(cs)) out.push([describe(el), Math.round(r * 100) / 100, need(cs), t.slice(0, 30)]);
    }
    document.querySelectorAll('input:not([type=hidden]):not([type=checkbox]):not([type=color]), select, textarea').forEach(el => {
        if (!el.getClientRects().length) return;
        const cs = getComputedStyle(el), bg = bgOf(el);
        const r = ratio(parse(cs.color), bg); checked++;
        if (r < 4.5) out.push([describe(el), Math.round(r * 100) / 100, 4.5, 'value']);
        if (el.placeholder) {
            const pc = getComputedStyle(el, '::placeholder');
            let f = parse(pc.color); const op = parseFloat(pc.opacity); if (f.a < 1 || op < 1) f = over({r: f.r, g: f.g, b: f.b, a: f.a * (isNaN(op) ? 1 : op)}, bg);
            const r2 = ratio(f, bg); checked++;
            if (r2 < 4.5) out.push([describe(el) + '::placeholder', Math.round(r2 * 100) / 100, 4.5, el.placeholder.slice(0, 20)]);
        }
    });
    return {bad: out, checked: checked};
}'''


def open_all(page):
    page.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")


def t_layout(browser):
    states = {}

    def empty(page):
        pass

    def link_open(page):
        fill_form(page, 'url', {'url': 'example.com/a-rather-long-path/that-keeps-going-and-going/and-going/and-going/forever-and-ever?with=query&and=more'})
        open_all(page)
        page.fill('#capIn', 'Scan to see the whole menu today')

    def wifi_long(page):
        fill_form(page, 'wifi', {'ssid': 'A really long network name that goes on', 'password': 'p' * 70})

    def contact_long(page):
        fill_form(page, 'contact', {'first': 'Bartholomew', 'last': 'Featherstonehaugh-Cholmondeley', 'org': 'The Extremely Long Company Name Incorporated Worldwide',
                                    'title': 'Senior Vice President of Everything', 'mobile': '+15551234567', 'work': '+15557654321', 'email': 'bartholomew.featherstonehaugh@verylongdomainname.example.com',
                                    'url': 'verylongdomainname.example.com/some/long/path', 'street': '1234 Extraordinarily Long Street Name, Suite 5678', 'city': 'Llanfairpwllgwyngyll', 'region': 'Gwynedd', 'zip': 'LL61 5UJ', 'country': 'United Kingdom'})
        open_all(page)

    def event_state(page):
        fill_form(page, 'event', {'title': 'A very long event name that needs to wrap around on a small screen', 'start': '2026-12-31T21:00', 'end': '2027-01-01T01:00', 'where': 'Somewhere with an extremely long venue name and address attached to it'})
        open_all(page)

    def alerts_state(page):
        fill_form(page, 'url', {'url': 'localhost'})
        open_all(page)
        page.fill('#fgHex', '#777777')
        page.fill('#bgHex', '#888888')
        page.fill('#quietIn', '0')

    def toolong(page):
        fill_form(page, 'text', {'text': 'x' * 5000})
        open_all(page)

    states = [('empty', empty), ('link with everything open', link_open), ('wifi long values', wifi_long), ('contact long values', contact_long),
              ('event', event_state), ('alerts', alerts_state), ('too long', toolong)]
    with section('no sideways scroll'):
        for label, fn in states:
            ctx, page = new_page(browser, w=390, h=844)
            fn(page)
            for w in WIDTHS:
                o = overflow(page, w)
                eq('no horizontal overflow at %d, %s' % (w, label), (o['sw'] <= o['W'], o['bad']), (True, []))
            ctx.close()

    with section('pinned bar'):
        ctx, page = new_page(browser, w=899, h=800)
        eq('bar shows just under the wide layout', page.is_visible('#bar'), True)
        page.set_viewport_size({'width': 900, 'height': 800})
        page.wait_for_timeout(100)
        eq('bar goes away at the wide layout', page.is_visible('#bar'), False)
        eq('desk buttons come in', (page.is_visible('#btnPng'), page.is_visible('#btnSvg'), page.is_visible('#btnPrint')), (True, True, True))
        ctx.close()
        for w in (320, 390):
            ctx, page = new_page(browser, w=w, h=700)
            open_all(page)
            page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            page.wait_for_timeout(100)
            gap = page.evaluate('''() => { const foot = document.querySelector('.foot').getBoundingClientRect(); const bar = document.getElementById('bar').getBoundingClientRect(); return Math.round(bar.top - foot.bottom); }''')
            truth('footer is clear of the pinned bar at %d' % w, gap >= 0, gap)
            cells = page.evaluate("[...document.querySelectorAll('#bar .btn')].map(c => { const r = c.getBoundingClientRect(); return [Math.round(r.left), Math.round(r.right), Math.round(r.top), Math.round(r.height)]; })")
            eq('three bar buttons in one row at %d' % w, len(set(c[2] for c in cells)), 1)
            truth('bar buttons are inside the screen at %d' % w, all(c[0] >= 0 and c[1] <= w for c in cells), cells)
            truth('bar buttons are tall enough at %d' % w, all(c[3] >= 44 for c in cells), cells)
            truth('bar words are not cut off at %d' % w, page.evaluate("[...document.querySelectorAll('#bar .btn')].every(b => b.scrollWidth <= b.clientWidth + 1)"))
            ctx.close()

    with section('wide layout'):
        ctx, page = new_page(browser, w=1280, h=900)
        fill_form(page, 'url', {'url': 'example.com'})
        pos = page.evaluate('''() => { const a = document.querySelector('.inputs').getBoundingClientRect(); const r = document.querySelector('.results').getBoundingClientRect();
            return {inputsRight: a.right, resultsLeft: r.left, resultsW: r.width, inputsTop: a.top, resultsTop: r.top}; }''')
        truth('results sit beside the form', pos['resultsLeft'] >= pos['inputsRight'] and abs(pos['resultsTop'] - pos['inputsTop']) < 60, pos)
        eq('results column is 400 wide', round(pos['resultsW']), 400)
        open_all(page)
        page.evaluate('window.scrollTo(0, 600)')
        page.wait_for_timeout(100)
        eq('results stay in view when you scroll', page.evaluate("document.querySelector('.results').getBoundingClientRect().top") < 40, True)
        eq('the code is still on screen', page.evaluate("(() => { const r = document.getElementById('cv').getBoundingClientRect(); return r.top >= 0 && r.bottom <= window.innerHeight; })()"), True)
        ctx.close()

    with section('code fits its box'):
        for w in (320, 390, 768, 1280):
            ctx, page = new_page(browser, w=w, h=900)
            fill_form(page, 'text', {'text': 'x' * 700})
            sizes = page.evaluate("(() => { const c = document.getElementById('cv').getBoundingClientRect(), s = document.getElementById('stage').getBoundingClientRect(); return [c.width, s.width, c.height]; })()")
            truth('code is inside its box at %d' % w, sizes[0] <= sizes[1] and sizes[0] > 100, sizes)
            ctx.close()


def t_accessibility(browser):
    for scheme in ('light', 'dark'):
        with section('contrast ' + scheme):
            ctx, page = new_page(browser, scheme=scheme, w=390, h=844)
            total = 0
            bad = []

            def audit(label):
                nonlocal total
                # colours are read at rest: let any 0.12 s fade (a tab that was just chosen, the toast) finish first
                page.evaluate("() => Promise.all(document.getAnimations().map(a => a.finished.catch(() => null)))")
                page.wait_for_timeout(30)
                r = page.evaluate(CONTRAST_JS)
                total += r['checked']
                bad.extend([[label] + b for b in r['bad']])
            audit('sample')
            open_all(page)
            audit('sample, everything open')
            fill_form(page, 'url', {'url': 'example.com'})
            audit('link ready')
            fill_form(page, 'wifi', {'ssid': 'Net', 'password': 'short'})
            audit('wifi with a warning')
            page.focus('#f-hidden')
            fill_form(page, 'wifi', {'password': ''})
            page.focus('#f-hidden')
            audit('wifi with an error')
            fill_form(page, 'url', {'url': 'localhost'})
            put(page, '#fgHex', '#777777')
            put(page, '#bgHex', '#888888')
            put(page, '#quietIn', '0')
            audit('colour and border warnings')
            put(page, '#fgHex', '#ffffff')
            put(page, '#bgHex', '#000000')
            audit('light on dark')
            page.check('#transChk')
            audit('transparent')
            page.uncheck('#transChk')
            fill_form(page, 'text', {'text': 'x' * 5000})
            audit('too long')
            tap(page, '#btnPng')
            audit('with a toast')
            eq('%s contrast is strong enough everywhere (%d texts)' % (scheme, total), bad, [])
            truth('%s contrast audit looked at plenty of text' % scheme, total > 250, total)
            ctx.close()

    with section('tap targets'):
        ctx, page = new_page(browser, w=390, h=844, mobile=True)
        open_all(page)
        fill_form(page, 'wifi', {'ssid': 'Net', 'password': 'abcd1234'})
        small = page.evaluate('''() => [...document.querySelectorAll('button, summary, select, textarea, label.check, input:not([type=hidden]):not([type=checkbox])')]
            .filter(e => e.getClientRects().length && !e.closest('.printarea'))
            .map(e => { const r = e.getBoundingClientRect(); return [(e.id || e.className || e.tagName) + ' ' + (e.textContent || '').trim().slice(0, 14), Math.round(r.width), Math.round(r.height)]; })
            .filter(x => x[2] < 40 || x[1] < 40)''')
        eq('no undersized tap targets', small, [])
        fill_form(page, 'contact', {'first': 'A'})
        small2 = page.evaluate('''() => [...document.querySelectorAll('#fields button, #fields summary, #fields select, #fields input:not([type=checkbox]), #fields textarea, #fields label.check')]
            .filter(e => e.getClientRects().length).map(e => { const r = e.getBoundingClientRect(); return [e.id || e.tagName, Math.round(r.width), Math.round(r.height)]; }).filter(x => x[2] < 40)''')
        eq('no undersized form controls on the contact form', small2, [])
        for t in ('event', 'email', 'map', 'sms'):
            pick(page, t)
            s3 = page.evaluate('''() => [...document.querySelectorAll('#fields input:not([type=checkbox]), #fields select, #fields textarea, #fields label.check')]
                .filter(e => e.getClientRects().length).map(e => { const r = e.getBoundingClientRect(); return [e.id || e.tagName, Math.round(r.width), Math.round(r.height)]; }).filter(x => x[2] < 40)''')
            eq('no undersized form controls on ' + t, s3, [])
        ctx.close()

    with section('ios zoom guard'):
        ctx, page = new_page(browser, w=390, h=844)
        open_all(page)
        res = page.evaluate('''() => [...document.querySelectorAll('input, select, textarea')].filter(el => el.type !== 'hidden' && el.type !== 'checkbox' && el.type !== 'color')
            .map(el => [el.tagName + '#' + el.id, parseFloat(getComputedStyle(el).fontSize)])''')
        eq('the text controls on the Link tab', [r[0] for r in res], ['INPUT#f-url', 'SELECT#sizeSel', 'INPUT#quietIn', 'INPUT#fgHex', 'INPUT#bgHex', 'INPUT#capIn', 'SELECT#printSel'])
        eq('every text control is 16px or larger', [r for r in res if r[1] < 16], [])
        for t in ('wifi', 'contact', 'event', 'map', 'sms', 'email', 'text'):
            pick(page, t)
            res = page.evaluate('''() => [...document.querySelectorAll('#fields input, #fields select, #fields textarea')].filter(el => el.type !== 'checkbox').map(el => [el.id, parseFloat(getComputedStyle(el).fontSize)])''')
            eq('16px or larger on ' + t, [r for r in res if r[1] < 16], [])
        ctx.close()

    with section('names and structure'):
        ctx, page = new_page(browser, w=390, h=844)
        open_all(page)
        for t in ('url', 'text', 'wifi', 'email', 'phone', 'sms', 'contact', 'map', 'event'):
            pick(page, t)
            open_all(page)
            unnamed = page.evaluate('''() => [...document.querySelectorAll('input, select, textarea, button')].filter(el => el.getClientRects().length || el.closest('details'))
                .filter(el => { const n = (el.labels && el.labels.length) || el.getAttribute('aria-label') || (el.tagName === 'BUTTON' && el.textContent.trim()); return !n; })
                .map(el => el.tagName + '#' + el.id + '.' + el.className)''')
            eq('every control has a name on ' + t, unnamed, [])
            dup = page.evaluate("(() => { const ids = [...document.querySelectorAll('[id]')].map(e => e.id); return ids.filter((x, i) => ids.indexOf(x) !== i); })()")
            eq('no repeated ids on ' + t, dup, [])
        eq('headings in order', page.evaluate("[...document.querySelectorAll('h1, h2, h3')].map(h => h.tagName)"), ['H1', 'H2', 'H2', 'H2', 'H2', 'H2'])
        eq('svg pictures are hidden from readers', page.evaluate("[...document.querySelectorAll('svg')].every(s => s.getAttribute('aria-hidden') === 'true')"), True)
        eq('the code picture has a role and a name', (page.get_attribute('#cv', 'role'), bool(page.get_attribute('#cv', 'aria-label'))), ('img', True))
        eq('status is a polite live region', (page.get_attribute('#live', 'role'), page.get_attribute('#live', 'aria-live')), ('status', 'polite'))
        eq('toast is a polite live region', (page.get_attribute('#toast', 'role'), page.get_attribute('#toast', 'aria-live')), ('status', 'polite'))
        eq('print area is hidden from readers', page.get_attribute('#printArea', 'aria-hidden'), 'true')
        eq('buttons are real buttons', page.evaluate("[...document.querySelectorAll('.btn, .tab, .chip, .swatch')].every(b => b.tagName === 'BUTTON' && b.type === 'button')"), True)
        ctx.close()

    with section('live region only speaks when something changes'):
        ctx, page = new_page(browser, w=1280, h=900)
        fill_form(page, 'url', {'url': 'example.com'})
        page.evaluate("""() => { window.__mut = 0; new MutationObserver(m => { window.__mut += m.length; }).observe(document.getElementById('live'), {childList: true, characterData: true, subtree: true}); }""")
        page.focus('#f-url')
        page.keyboard.press('End')
        page.keyboard.type('/menu')
        page.keyboard.type('/today')
        page.wait_for_timeout(200)
        eq('typing more of the same address does not rewrite the status', page.evaluate('window.__mut'), 0)
        ctx.close()

    with section('keyboard'):
        ctx, page = new_page(browser, w=1280, h=900)
        # the first stops, in order
        seq = []
        page.focus('#tab-url')
        for _ in range(6):
            page.keyboard.press('Tab')
            seq.append(page.evaluate("document.activeElement.id || document.activeElement.tagName"))
        eq('tab order after the tabs', seq[:2], ['f-url', 'SUMMARY'])
        # a full flow with the keyboard only
        page.focus('#tab-wifi')
        page.keyboard.press('Enter')
        page.keyboard.press('Space')
        eq('the tab is chosen', page.get_attribute('#tab-wifi', 'aria-selected'), 'true')
        page.keyboard.press('Tab')
        page.keyboard.type('Cafe')
        page.keyboard.press('Tab')
        page.keyboard.type('espresso99')
        page.keyboard.press('Tab')
        page.keyboard.press('Enter')   # Show / Hide
        eq('enter works on the show button', page.get_attribute('#f-password', 'type'), 'text')
        eq('typed with the keyboard', cur_text(page), 'WIFI:T:WPA;S:Cafe;P:espresso99;;')
        page.focus('#btnPng')
        with page.expect_download() as dl:
            page.keyboard.press('Enter')
        eq('enter downloads', dl.value.suggested_filename, 'qr-wifi.png')
        # focus rings
        page.focus('#tab-url')
        missing = []
        for i in range(60):
            page.keyboard.press('Tab')
            info = page.evaluate('''() => { const e = document.activeElement; if (!e || e === document.body) return null; const cs = getComputedStyle(e);
                const r = e.getBoundingClientRect();
                return [e.id || e.tagName + '.' + e.className, cs.outlineStyle, parseFloat(cs.outlineWidth), r.width > 0]; }''')
            if info is None:
                break
            if info[3] and (info[1] == 'none' or info[2] < 2):
                missing.append(info)
        eq('every stop has a visible focus ring', missing, [])
        ctx.close()

    with section('reduced motion'):
        ctx = browser.new_context(viewport={'width': 390, 'height': 844}, reduced_motion='reduce')
        page = ctx.new_page()
        page.goto(URL)
        page.wait_for_timeout(200)
        durs = page.evaluate("[...document.querySelectorAll('.btn, .chip, .tab, .swatch')].map(e => getComputedStyle(e).transitionDuration)")
        eq('no transitions with reduced motion', sorted(set(durs)), ['0s'])
        ctx.close()
        ctx = browser.new_context(viewport={'width': 390, 'height': 844}, reduced_motion='no-preference')
        page = ctx.new_page()
        page.goto(URL)
        page.wait_for_timeout(200)
        durs = page.evaluate("[...document.querySelectorAll('.btn, .chip, .tab, .swatch')].map(e => getComputedStyle(e).transitionDuration)")
        flat_durs = sorted({d.strip() for v in durs for d in v.split(',')})
        eq('short transitions otherwise', flat_durs, ['0.12s'])
        ctx.close()

    with section('colour scheme'):
        ctx, page = new_page(browser, scheme='dark')
        eq('dark body background', page.evaluate("getComputedStyle(document.body).backgroundColor"), 'rgb(9, 19, 14)')
        page.evaluate("document.documentElement.setAttribute('data-theme', 'light')")
        eq('data-theme light wins over dark OS', page.evaluate("getComputedStyle(document.body).backgroundColor"), 'rgb(232, 240, 234)')
        ctx.close()
        ctx, page = new_page(browser, scheme='light')
        eq('light body background', page.evaluate("getComputedStyle(document.body).backgroundColor"), 'rgb(232, 240, 234)')
        page.evaluate("document.documentElement.setAttribute('data-theme', 'dark')")
        eq('data-theme dark wins over light OS', page.evaluate("getComputedStyle(document.body).backgroundColor"), 'rgb(9, 19, 14)')
        ctx.close()


def t_site(browser):
    with section('fonts'):
        ctx, page = new_page(browser)
        res = page.evaluate('''async () => { const out = []; for (const f of [...document.fonts]) { try { await f.load(); out.push(f.family.replace(/["']/g, '') + ' ' + f.weight + ' ' + f.status); }
            catch (e) { out.push(f.family + ' ' + f.weight + ' ERROR ' + e.message); } } return out; }''')
        eq('8 faces declared', len(res), 8)
        eq('every face loads', [r for r in res if not r.endswith(' loaded')], [])
        eq('display font ready', page.evaluate('''document.fonts.check("800 30px 'Big Shoulders Display'")'''), True)
        eq('body font ready', page.evaluate('''document.fonts.check("400 16px 'Public Sans'")'''), True)
        eq('caption font ready', page.evaluate('''document.fonts.check("700 20px 'Public Sans'")'''), True)
        eq('mono font ready', page.evaluate('''document.fonts.check("400 13px 'IBM Plex Mono'")'''), True)
        eq('h1 uses the display font', page.evaluate("getComputedStyle(document.querySelector('.masthead h1')).fontFamily").startswith('"Big Shoulders Display"'), True)
        eq('the bullet glyph is in the mono font', page.evaluate('''() => { const w = (t) => { const s = document.createElement('span');
            s.style.cssText = "font:400 13px 'IBM Plex Mono';position:absolute;visibility:hidden;white-space:pre"; s.textContent = t; document.body.appendChild(s);
            const r = s.getBoundingClientRect().width; s.remove(); return r; }; return Math.abs(w('\\u2022') - w('x')) < 0.6 && w('\\u2022') > 0; }'''), True)
        ctx.close()

    with section('metadata'):
        ctx, page = new_page(browser)
        eq('lang', page.evaluate('document.documentElement.lang'), 'en')
        eq('description length', 60 < len(page.get_attribute('meta[name=description]', 'content')) <= 160, True)
        eq('canonical', page.get_attribute('link[rel=canonical]', 'href'), SITE_URL)
        eq('og:title', page.get_attribute('meta[property="og:title"]', 'content'), SITE_TITLE)
        eq('og:image', page.get_attribute('meta[property="og:image"]', 'content'), SITE_URL + 'og.png')
        eq('og:image size', (page.get_attribute('meta[property="og:image:width"]', 'content'), page.get_attribute('meta[property="og:image:height"]', 'content')), ('1200', '630'))
        eq('twitter card', page.get_attribute('meta[name="twitter:card"]', 'content'), 'summary_large_image')
        eq('theme colors', page.evaluate("[...document.querySelectorAll('meta[name=theme-color]')].map(m => m.content)"), ['#E8F0EA', '#09130E'])
        eq('favicon is a data uri', (page.get_attribute('link[rel=icon]', 'href') or '').startswith('data:image/svg+xml;base64,'), True)
        eq('apple touch icon', page.get_attribute('link[rel=apple-touch-icon]', 'href'), 'apple-touch-icon.png')
        eq('mailto anchor', page.get_attribute('a.mail', 'href'), 'mailto:' + SUPPORT)
        eq('mail address is shown', txt(page, 'a.mail'), SUPPORT)
        eq('privacy link', page.get_attribute('.foot a[href="privacy.html"]', 'href'), 'privacy.html')
        eq('home link', page.get_attribute('.foot a[href="https://sanjixysti-creator.github.io/"]', 'href'), 'https://sanjixysti-creator.github.io/')
        eq('drive rate link', page.get_attribute('.foot a[href*="drive-rate"]', 'href'), 'https://sanjixysti-creator.github.io/drive-rate/')
        has('maker line', txt(page, '.foot'), 'Made by Xysti Software')
        has('trademark line', txt(page, '.foot'), 'QR Code is a registered trademark of DENSO WAVE INCORPORATED.')
        tap(page, '.mail-copy')
        page.wait_for_timeout(100)
        eq('copy the address', (page.evaluate('window.__copied'), toast(page)), (SUPPORT, 'Email address copied.'))
        ctx.close()
        ctx, page = new_page(browser, stub=STUB_REJECT)
        tap(page, '.mail-copy')
        page.wait_for_timeout(150)
        eq('copy refused says so', toast(page), 'Your browser blocked copying. Select the text and copy it yourself.')
        ctx.close()

    with section('faq'):
        ctx, page = new_page(browser)
        qs = page.evaluate("[...document.querySelectorAll('#faq summary')].map(s => s.textContent.trim())")
        eq('eight questions', len(qs), 8)
        eq('all closed at the start', page.evaluate("[...document.querySelectorAll('#faq details')].filter(d => d.open).length"), 0)
        tap(page, '#faq details:nth-child(1) summary')
        eq('one opens', page.evaluate("document.querySelector('#faq details:nth-child(1)').open"), True)
        tap(page, '#faq details:nth-child(1) summary')
        eq('and closes', page.evaluate("document.querySelector('#faq details:nth-child(1)').open"), False)
        eq('summaries are tall enough to tap', page.evaluate("[...document.querySelectorAll('#faq summary')].every(s => s.getBoundingClientRect().height >= 44)"), True)
        ctx.close()

    for scheme in ('light', 'dark'):
        with section('privacy ' + scheme):
            ctx, page = new_page(browser, scheme=scheme, url=ORIGIN + PAGE_PATH + 'privacy.html')
            eq('privacy title', page.title(), 'Privacy Policy - QR Forever')
            eq('one h1', page.evaluate("document.querySelectorAll('h1').length"), 1)
            has('says no analytics', txt(page, 'body'), 'no analytics')
            has('says what stays on the device', txt(page, 'body'), 'Wi-Fi password is never kept')
            has('says anyone can read a code', txt(page, 'body'), 'anyone who scans or photographs the code can read it')
            eq('privacy mailto', page.get_attribute('a[href^="mailto:"]', 'href'), 'mailto:' + SUPPORT)
            eq('privacy back link', page.get_attribute('.back', 'href'), './')
            eq('no scripts', page.evaluate("document.querySelectorAll('script').length"), 0)
            eq('privacy body background', page.evaluate("getComputedStyle(document.body).backgroundColor"), 'rgb(232, 240, 234)' if scheme == 'light' else 'rgb(9, 19, 14)')
            for w in (320, 390, 768, 1200):
                o = overflow(page, w)
                eq('privacy no overflow %s %d' % (scheme, w), (o['sw'] <= o['W'], o['bad']), (True, []))
            r = page.evaluate(CONTRAST_JS)
            eq('privacy contrast %s' % scheme, r['bad'], [])
            ctx.close()

    with section('noscript'):
        ctx = browser.new_context(java_script_enabled=False)
        page = ctx.new_page()
        page.goto(URL_PLAIN)
        has('message without scripts', page.inner_text('body'), 'QR Forever needs JavaScript.')
        ctx.close()

    with section('images'):
        folder = H.SITE_DIR
        for name, size in (('og.png', (1200, 630)), ('apple-touch-icon.png', (180, 180))):
            path = folder + '/' + name
            truth(name + ' exists', os.path.exists(path), path)
            if os.path.exists(path):
                with open(path, 'rb') as f:
                    head = f.read(24)
                eq(name + ' is a png of the right size', (head[:8] == b'\x89PNG\r\n\x1a\n', struct.unpack('>II', head[16:24])), (True, size))
        if os.path.exists(folder + '/og.png'):
            truth('og.png is a sensible size', os.path.getsize(folder + '/og.png') < 450 * 1024, os.path.getsize(folder + '/og.png'))
        eq('the folder holds only the four files', sorted(os.listdir(folder)), ['apple-touch-icon.png', 'index.html', 'og.png', 'privacy.html'])


def t_perf(browser):
    with section('speed'):
        ctx, page = new_page(browser)
        pick(page, 'text')
        put(page, '#f-text', 'x' * 2900)
        page.evaluate("document.getElementById('optsBox').open = true")
        tap(page, '#eclChips [data-v="L"]')
        ms = page.evaluate("""() => { const q = window.__qr; const t = performance.now(); for (let i = 0; i < 5; i++) q.update(); return (performance.now() - t) / 5; }""")
        truth('a version 40 code updates in under 250 ms (%.0f ms)' % ms, ms < 250, ms)
        pick(page, 'url')
        put(page, '#f-url', 'example.com/menu')
        ms2 = page.evaluate("""() => { const q = window.__qr; const t = performance.now(); for (let i = 0; i < 20; i++) q.update(); return (performance.now() - t) / 20; }""")
        truth('a typical link updates in under 25 ms (%.1f ms)' % ms2, ms2 < 25, ms2)
        # typing quickly keeps up and ends on the right code
        page.focus('#f-url')
        page.keyboard.press('Control+A')
        page.keyboard.type('https://example.com/a/long/path/with/many/parts/and/more?query=string&more=1', delay=2)
        eq('fast typing ends on the right code', cur_text(page), 'https://example.com/a/long/path/with/many/parts/and/more?query=string&more=1')
        ctx.close()
