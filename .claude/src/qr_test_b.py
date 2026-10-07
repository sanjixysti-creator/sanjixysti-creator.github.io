"""QR Forever browser tests, part B: the forms, the style options and what the page keeps on the device."""
import json, math, re

from qr_harness import *  # noqa: F401,F403
import qr_harness as H
from qr_test import fill_form, shown_code

BULLET = chr(0x2022)


def E(s):
    """Write a backslash as a percent sign, so the expected strings stay readable."""
    return s.replace('%', chr(92))


def lum(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def ratio(a, b):
    x, y = lum(a), lum(b)
    return (max(x, y) + 0.05) / (min(x, y) + 0.05)


def stored(page):
    return page.evaluate("localStorage.getItem('%s')" % H.STORE)


def t_fields(browser):
    with section('errors and hints'):
        ctx, page = new_page(browser)
        pick(page, 'email')
        put(page, '#f-to', 'not an email')
        eq('no error while still typing in the box', page.is_visible('#m-to'), False)
        page.focus('#f-subject')
        eq('error once the box is left', page.is_visible('#m-to'), True)
        has('error words', txt(page, '#m-to'), 'does not look like an email address: not')
        eq('aria-invalid is set', page.get_attribute('#f-to', 'aria-invalid'), 'true')
        has('box is described by its message', page.get_attribute('#f-to', 'aria-describedby'), 'm-to')
        eq('status while the form has an error', status(page), 'Finish the form and your code appears here.')
        eq('the sample stays up', page.is_visible('#sampleTag'), True)
        put(page, '#f-to', 'a@b.co')
        eq('fixing clears the error', (page.is_visible('#m-to'), page.get_attribute('#f-to', 'aria-invalid')), (False, None))
        eq('now it is ready', ready(page), True)
        # a tap on a download button with an unfinished form shows what is missing
        put(page, '#f-to', '')
        put(page, '#f-subject', 'Hello')
        tap(page, '#btnPng')
        eq('toast for an unfinished form', toast(page), 'Finish the form first, then your code is ready.')
        eq('the missing box is marked', page.is_visible('#m-to'), True)
        has('required message', txt(page, '#m-to'), 'Enter an email address.')
        ctx.close()

    with section('empty download'):
        ctx, page = new_page(browser)
        tap(page, '#btnPng')
        eq('toast for an empty form', toast(page), 'Fill in the form first, then your code is ready.')
        ctx.close()

    with section('wifi form'):
        ctx, page = new_page(browser)
        fill_form(page, 'wifi', {'ssid': 'Home Net', 'password': 'pass1234'})
        eq('password box is hidden text', page.get_attribute('#f-password', 'type'), 'password')
        eq('show button reads Show', (txt(page, '[data-show="password"]'), page.get_attribute('[data-show="password"]', 'aria-pressed')), ('Show', 'false'))
        tap(page, '[data-show="password"]')
        eq('shown after the tap', (page.get_attribute('#f-password', 'type'), txt(page, '[data-show="password"]'), page.get_attribute('[data-show="password"]', 'aria-pressed')), ('text', 'Hide', 'true'))
        tap(page, '[data-show="password"]')
        eq('hidden again', page.get_attribute('#f-password', 'type'), 'password')
        inside = txt(page, '#insideText')
        lacks('preview does not show the password', inside, 'pass1234')
        eq('preview shows bullets for it', inside, 'WIFI:T:WPA;S:Home Net;P:' + BULLET * 8 + ';;')
        lacks('the picture label does not hold the password', page.get_attribute('#cv', 'aria-label') or '', 'pass1234')
        has('picture label names the network', page.get_attribute('#cv', 'aria-label'), 'Home Net')
        eq('wifi sign button is offered', (page.is_visible('#btnSign'), page.is_visible('#signRow')), (True, False))
        page.evaluate("document.getElementById('optsBox').open = true")
        eq('sign option is offered', page.is_visible('#signRow'), True)
        # hidden network
        page.check('#f-hidden')
        eq('hidden network flag', cur_text(page), 'WIFI:T:WPA;S:Home Net;P:pass1234;H:true;;')
        # an open network needs no password
        page.select_option('#f-security', 'nopass')
        eq('password row disappears', page.is_visible('#f-password'), False)
        eq('open network payload', cur_text(page), 'WIFI:T:nopass;S:Home Net;H:true;;')
        eq('open network preview', txt(page, '#insideText'), 'WIFI:T:nopass;S:Home Net;H:true;;')
        page.select_option('#f-security', 'WEP')
        eq('password row returns', page.is_visible('#f-password'), True)
        eq('WEP payload', cur_text(page), 'WIFI:T:WEP;S:Home Net;P:pass1234;H:true;;')
        page.select_option('#f-security', 'WPA')
        put(page, '#f-password', 'short')
        has('short password warns', txt(page, '#alerts'), 'WPA passwords have at least 8 characters.')
        # special characters
        put(page, '#f-ssid', 'My;Net:"1"')
        put(page, '#f-password', 'a\\b,c;d:e"f12')
        eq('special characters are escaped', cur_text(page), E('WIFI:T:WPA;S:My%;Net%:%"1%";P:a%%b%,c%;d%:e%"f12;H:true;;'))
        res, _ = shown_code(page)
        truth('special characters read back', len(res) == 1 and res[0].text == cur_text(page), [r.text for r in res])
        # no name, no code
        put(page, '#f-ssid', '')
        eq('no network name means no code', ready(page), False)
        page.focus('#f-hidden')
        has('name is asked for', txt(page, '#m-ssid'), 'Enter the network name.')
        ctx.close()

    with section('map form'):
        ctx, page = new_page(browser)
        pick(page, 'map')
        # typing a pair character by character must not be cut in half
        page.focus('#f-lat')
        page.keyboard.type('37.7749, -122.4194')
        eq('typed pair stays in one box while typing', (page.input_value('#f-lat'), page.input_value('#f-lng')), ('37.7749, -122.4194', ''))
        page.focus('#f-lng')
        eq('leaving the box splits it', (page.input_value('#f-lat'), page.input_value('#f-lng')), ('37.7749', '-122.4194'))
        eq('map payload', cur_text(page), 'geo:37.7749,-122.4194')
        # a paste splits at once
        page.evaluate("""() => { const e = document.getElementById('f-lat'); e.focus(); e.value = '51.5072 -0.1276';
            e.dispatchEvent(new InputEvent('input', {bubbles: true, inputType: 'insertFromPaste'})); }""")
        eq('paste splits at once', (page.input_value('#f-lat'), page.input_value('#f-lng')), ('51.5072', '-0.1276'))
        # a link instead
        page.select_option('#f-how', 'link')
        eq('maps link payload', cur_text(page), 'https://www.google.com/maps/search/?api=1&query=51.5072,-0.1276')
        put(page, '#f-lat', '95')
        page.focus('#f-lng')
        has('latitude error', txt(page, '#m-lat'), 'Latitude is a number from -90 to 90')
        put(page, '#f-lat', '37,7749')
        page.focus('#f-lng')
        has('comma decimal help', txt(page, '#m-lat'), 'Use a dot for decimals')
        ctx.close()

    with section('event form'):
        ctx, page = new_page(browser)
        pick(page, 'event')
        put(page, '#f-title', 'Party')
        put(page, '#f-start', '2026-12-31T21:00')
        put(page, '#f-end', '2027-01-01T01:00')
        eq('timed event', cur_text(page), 'BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nSUMMARY:Party\r\nDTSTART:20261231T210000\r\nDTEND:20270101T010000\r\nEND:VEVENT\r\nEND:VCALENDAR')
        page.check('#f-allday')
        eq('inputs become date inputs', (page.get_attribute('#f-start', 'type'), page.get_attribute('#f-end', 'type')), ('date', 'date'))
        eq('values keep their day', (page.input_value('#f-start'), page.input_value('#f-end')), ('2026-12-31', '2027-01-01'))
        eq('all day payload', cur_text(page), 'BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nSUMMARY:Party\r\nDTSTART;VALUE=DATE:20261231\r\nDTEND;VALUE=DATE:20270102\r\nEND:VEVENT\r\nEND:VCALENDAR')
        page.uncheck('#f-allday')
        eq('inputs become time inputs again', (page.get_attribute('#f-start', 'type'), page.get_attribute('#f-end', 'type')), ('datetime-local', 'datetime-local'))
        eq('times get a start of day', (page.input_value('#f-start'), page.input_value('#f-end')), ('2026-12-31T09:00', '2027-01-01T10:00'))
        put(page, '#f-end', '2026-12-30T10:00')
        page.focus('#f-title')
        has('end before start', txt(page, '#m-end'), 'The end has to be after the start.')
        eq('no code while that is wrong', ready(page), False)
        put(page, '#f-end', '')
        eq('no end is fine', ready(page), True)
        put(page, '#f-where', 'City Hall, Main St; Room 2')
        put(page, '#f-details', 'Bring snacks\nand a coat')
        t = cur_text(page)
        has('place is escaped', t, E('LOCATION:City Hall%, Main St%; Room 2'))
        has('details line break is escaped', t, E('DESCRIPTION:Bring snacks%nand a coat'))
        ctx.close()

    with section('contact form'):
        ctx, page = new_page(browser)
        pick(page, 'contact')
        eq('address starts closed', page.evaluate("document.querySelector('#fields details.sub').open"), False)
        put(page, '#f-org', 'Acme')
        eq('company alone is enough', ready(page), True)
        put(page, '#f-org', '')
        page.focus('#f-last')
        page.focus('#f-first')
        eq('no name asks for one', ready(page), False)
        put(page, '#f-first', 'Ada')
        page.evaluate("document.querySelector('#fields details.sub').open = true")
        put(page, '#f-street', '1 Main St')
        put(page, '#f-city', 'Springfield')
        pick(page, 'text')
        put(page, '#f-text', 'x')
        pick(page, 'contact')
        eq('values are kept when you come back', (page.input_value('#f-first'), page.input_value('#f-street')), ('Ada', '1 Main St'))
        eq('address opens by itself when it has content', page.evaluate("document.querySelector('#fields details.sub').open"), True)
        eq('card payload has the address', 'ADR;TYPE=WORK:;;1 Main St;Springfield;;;' in cur_text(page), True)
        pick(page, 'text')
        eq('the other tab kept its text too', page.input_value('#f-text'), 'x')
        ctx.close()

    with section('long text'):
        ctx, page = new_page(browser)
        pick(page, 'text')
        put(page, '#f-text', 'a' * 5000)
        eq('too long status', status(page), 'Too long for a QR code at level M: about 5,000 characters, and the most it holds is about 2,331. Shorten it or choose a lower level.')
        eq('too long class', page.evaluate("document.getElementById('status').classList.contains('is-bad')"), True)
        eq('no code for it', (ready(page), page.is_visible('#sampleTag')), (False, True))
        tap(page, '#btnPng')
        eq('toast for too long', toast(page), 'That is too long for a QR code at this level. Shorten it, or pick a lower error correction level.')
        put(page, '#f-text', 'a' * 2900)
        eq('2900 characters is too long at M', ready(page), False)
        page.evaluate("document.getElementById('optsBox').open = true")
        tap(page, '#eclChips [data-v="L"]')
        eq('2900 characters fits at L', (ready(page), hook(page, 'q.cur().code.version')), (True, 40))
        res, _ = shown_code(page)
        truth('a version 40 code reads back', len(res) == 1 and res[0].bytes == b'a' * 2900, [len(r.bytes) for r in res])
        put(page, '#f-text', 'a' * 2953)
        eq('2953 is the most at L', ready(page), True)
        put(page, '#f-text', 'a' * 2954)
        eq('2954 is one too many at L', ready(page), False)
        ctx.close()

    with section('unicode and edge text'):
        ctx, page = new_page(browser)
        pick(page, 'text')
        for s in ['caf\u00e9 cr\u00e8me', '\u65e5\u672c\u8a9e\u306e\u30c6\u30ad\u30b9\u30c8', 'emoji \U0001F600\U0001F680', '\u0645\u0631\u062d\u0628\u0627 \u0628\u0627\u0644\u0639\u0627\u0644\u0645', 'HTTPS://EXAMPLE.COM', '0123456789', 'tab\there']:
            put(page, '#f-text', s)
            res, _ = shown_code(page)
            truth('reads back: %r' % s[:14], len(res) == 1 and res[0].bytes == s.encode('utf-8'), [r.text[:20] for r in res])
        ctx.close()


def t_options(browser):
    with section('options'):
        ctx, page = new_page(browser)
        fill_form(page, 'url', {'url': 'example.com'})
        eq('options start closed', page.evaluate("document.getElementById('optsBox').open"), False)
        page.evaluate("document.getElementById('optsBox').open = true")
        for lv, pct in (('L', '7%'), ('M', '15%'), ('Q', '25%'), ('H', '30%')):
            tap(page, '#eclChips [data-v="%s"]' % lv)
            eq('level ' + lv, hook(page, 'q.cur().code.level'), lv)
            eq('level %s is pressed' % lv, page.evaluate("[...document.querySelectorAll('#eclChips button')].filter(b => b.getAttribute('aria-pressed') === 'true').map(b => b.dataset.v)"), [lv])
            has('level %s help' % lv, txt(page, '#eclHelp'), pct)
        tap(page, '#eclChips [data-v="M"]')
        # download size
        for target in (256, 512, 1024, 2048, 4096):
            page.select_option('#sizeSel', str(target))
            size = hook(page, 'q.cur().code.size')
            k = expected_scale(size, 4, target)
            w = (size + 8) * k
            eq('size %d info' % target, txt(page, '#sizeInfo'), 'Your PNG will be %d x %d px, with each square %d px wide. SVG is not limited by size.' % (w, w, k))
        page.select_option('#sizeSel', '1024')
        # a dense code at a small size gets a warning, and it goes away when the size grows
        pick(page, 'text')
        put(page, '#f-text', 'x' * 1500)
        page.select_option('#sizeSel', '256')
        has('tiny squares are flagged', txt(page, '#sizeInfo'), 'Squares this small can be hard to read. Choose a larger size.')
        has('and the size is still stated', txt(page, '#sizeInfo'), 'each square 1 px wide')
        page.select_option('#sizeSel', '1024')
        lacks('a bigger size clears the flag', txt(page, '#sizeInfo'), 'hard to read')
        pick(page, 'url')
        put(page, '#f-url', 'example.com')
        # white border
        put(page, '#quietIn', '0')
        eq('border 0', hook(page, 'q.state().quiet'), 0)
        has('border 0 warns', txt(page, '#alerts'), 'A white border of less than 2 squares stops many phones reading the code. Use 4 if you can.')
        has('border info', txt(page, '#quietInfo'), 'Scanners like a clear border of 4 squares.')
        put(page, '#quietIn', '9')
        eq('9 is refused', hook(page, 'q.state().quiet'), 0)
        put(page, '#quietIn', '-1')
        eq('-1 is refused', hook(page, 'q.state().quiet'), 0)
        put(page, '#quietIn', '8')
        eq('8 is allowed', hook(page, 'q.state().quiet'), 8)
        put(page, '#quietIn', '')
        eq('blank keeps the last', hook(page, 'q.state().quiet'), 8)
        page.focus('#capIn')
        eq('blank box is filled in when left', page.input_value('#quietIn'), '8')
        put(page, '#quietIn', '4')
        has('standard border info', txt(page, '#quietInfo'), 'The standard border is 4 squares wide.')
        ctx.close()

    with section('colours'):
        ctx, page = new_page(browser)
        fill_form(page, 'url', {'url': 'example.com'})
        page.evaluate("document.getElementById('optsBox').open = true")
        put(page, '#fgHex', '1E3A8A')
        eq('hex without a hash is accepted', hook(page, 'q.state().fg'), '#1e3a8a')
        eq('colour picker follows', page.input_value('#fgIn'), '#1e3a8a')
        put(page, '#fgHex', 'zzz')
        eq('nonsense is ignored', hook(page, 'q.state().fg'), '#1e3a8a')
        page.focus('#bgHex')
        eq('box shows the real colour once left', page.input_value('#fgHex'), '#1e3a8a')
        tap(page, '#bgSw [data-v="#fef3c7"]')
        eq('swatch sets the background', hook(page, 'q.state().bg'), '#fef3c7')
        eq('swatch is pressed', page.get_attribute('#bgSw [data-v="#fef3c7"]', 'aria-pressed'), 'true')
        want = ratio('#1e3a8a', '#fef3c7')
        has('contrast shown', txt(page, '#colorInfo'), 'Contrast between the two colours: %.1f to 1.' % want)
        page.evaluate("(() => { const i = document.getElementById('fgIn'); i.value = '#7f1d1d'; i.dispatchEvent(new Event('input', {bubbles: true})); })()")
        eq('colour picker input works', hook(page, 'q.state().fg'), '#7f1d1d')
        res, _ = shown_code(page)
        truth('a coloured code reads back', len(res) == 1 and res[0].text == 'https://example.com', [r.text for r in res])
        # colours too close
        put(page, '#fgHex', '#777777')
        put(page, '#bgHex', '#888888')
        has('too close warning', txt(page, '#alerts'), 'The colours are too close')
        # light on dark
        put(page, '#fgHex', '#ffffff')
        put(page, '#bgHex', '#000000')
        has('inverted note', txt(page, '#alerts'), 'A light code on a dark background is read by most new phones, but some older scanners cannot read it.')
        res, _ = shown_code(page)
        truth('a light on dark code is still read by zxing', len(res) == 1 and res[0].text == 'https://example.com', [r.text for r in res])
        # transparent
        tap(page, '#bgSw [data-v="#ffffff"]')
        page.check('#transChk')
        eq('transparent turns the background box off', (page.is_disabled('#bgHex'), page.is_disabled('#bgIn')), (True, True))
        eq('tile shows the chequer', 'checks' in (page.get_attribute('#tile', 'class') or ''), True)
        has('transparent note', txt(page, '#alerts'), 'The background is transparent, so put the code on a plain light surface.')
        page.uncheck('#transChk')
        eq('opaque again', (page.is_disabled('#bgHex'), 'checks' in (page.get_attribute('#tile', 'class') or '')), (False, False))
        ctx.close()

    with section('shape and caption'):
        ctx, page = new_page(browser)
        fill_form(page, 'url', {'url': 'example.com'})
        page.evaluate("document.getElementById('optsBox').open = true")
        eq('square is the start', (page.get_attribute('#styleChips [data-v="square"]', 'aria-pressed'), 'sq' in (page.get_attribute('#tile', 'class') or '').split()), ('true', True))
        tap(page, '#styleChips [data-v="round"]')
        eq('rounded is chosen', (hook(page, 'q.state().style'), 'sq' in (page.get_attribute('#tile', 'class') or '').split()), ('round', False))
        res, _ = shown_code(page)
        truth('a rounded code reads back', len(res) == 1 and res[0].text == 'https://example.com', [r.text for r in res])
        w0, h0 = page.evaluate("[document.getElementById('cv').width, document.getElementById('cv').height]")
        put(page, '#capIn', 'Scan to see the menu')
        w1, h1 = page.evaluate("[document.getElementById('cv').width, document.getElementById('cv').height]")
        truth('a caption adds a band under the code', w0 == h0 and h1 > w1 and abs(h1 / w1 - 1.14) < 0.03, (w0, h0, w1, h1))
        res, _ = shown_code(page)
        truth('a code with a caption reads back', len(res) == 1 and res[0].text == 'https://example.com', [r.text for r in res])
        eq('caption limit', page.get_attribute('#capIn', 'maxlength'), '40')
        put(page, '#capIn', '')
        w2, h2 = page.evaluate("[document.getElementById('cv').width, document.getElementById('cv').height]")
        eq('no caption, no band', (w2, h2), (w0, h0))
        ctx.close()

    with section('printed size'):
        ctx, page = new_page(browser)
        fill_form(page, 'url', {'url': 'example.com'})
        page.evaluate("document.getElementById('optsBox').open = true")
        size = hook(page, 'q.cur().code.size')
        page.select_option('#printSel', '100')
        eq('printed size info', txt(page, '#printInfo'), 'Each square will print about %s mm wide.' % (round(100 / (size + 8) * 100) / 100))
        pick(page, 'text')
        put(page, '#f-text', 'x' * 900)
        page.select_option('#printSel', '40')
        has('small print warning', txt(page, '#printInfo'), 'That is small for phones to read.')
        ctx.close()

    with section('reset'):
        ctx, page = new_page(browser)
        fill_form(page, 'url', {'url': 'example.com'})
        page.evaluate("document.getElementById('optsBox').open = true")
        tap(page, '#eclChips [data-v="H"]')
        put(page, '#fgHex', '#1e3a8a')
        page.select_option('#sizeSel', '2048')
        put(page, '#capIn', 'Hello')
        tap(page, '#styleChips [data-v="round"]')
        tap(page, '#resetBtn')
        st = hook(page, '(() => { const s = q.state(); return [s.ecl, s.size, s.quiet, s.fg, s.bg, s.transparent, s.style, s.caption, s.printMm]; })()')
        eq('style and size are back to the start', st, ['M', 1024, 4, '#000000', '#ffffff', False, 'square', '', 75])
        eq('reset keeps what you typed', page.input_value('#f-url'), 'example.com')
        eq('reset toast', toast(page), 'Style and size are back to the start.')
        ctx.close()


def pre(**kw):
    d = {'v': 1}
    d.update(kw)
    return json.dumps(d)


def t_storage(browser):
    with section('nothing typed is kept by default'):
        ctx, page = new_page(browser)
        fill_form(page, 'url', {'url': 'private-example-site.com/secret-path'})
        fill_form(page, 'wifi', {'ssid': 'SecretNetworkName', 'password': 'SecretPassword99'})
        page.evaluate("document.getElementById('optsBox').open = true")
        tap(page, '#eclChips [data-v="H"]')
        put(page, '#capIn', 'My caption text')
        page.wait_for_timeout(500)
        raw = stored(page)
        truth('settings are kept', raw is not None and '"ecl":"H"' in raw, raw)
        lacks('the web address is not kept', raw or '', 'private-example')
        lacks('the network name is not kept', raw or '', 'SecretNetworkName')
        lacks('the password is not kept', raw or '', 'SecretPassword99')
        lacks('the caption is not kept', raw or '', 'My caption')
        eq('remember is off', json.loads(raw)['remember'], False)
        eq('no entries key', 'data' in json.loads(raw), False)
        ctx.close()

    with section('settings survive a reload'):
        ctx, page = new_page(browser)
        fill_form(page, 'wifi', {'ssid': 'Net', 'password': 'abcd1234'})
        page.evaluate("document.getElementById('optsBox').open = true")
        tap(page, '#eclChips [data-v="Q"]')
        page.select_option('#sizeSel', '2048')
        put(page, '#fgHex', '#1e3a8a')
        tap(page, '#bgSw [data-v="#e0f2fe"]')
        tap(page, '#styleChips [data-v="round"]')
        put(page, '#quietIn', '6')
        page.select_option('#printSel', '100')
        page.wait_for_timeout(400)
        page.reload()
        page.wait_for_timeout(300)
        st = hook(page, '(() => { const s = q.state(); return [s.type, s.ecl, s.size, s.quiet, s.fg, s.bg, s.style, s.printMm]; })()')
        eq('settings come back', st, ['wifi', 'Q', 2048, 6, '#1e3a8a', '#e0f2fe', 'round', 100])
        eq('typed text does not', (page.input_value('#f-ssid'), page.input_value('#f-password')), ('', ''))
        ctx.close()

    with section('remember what I type'):
        ctx, page = new_page(browser)
        page.evaluate("document.getElementById('optsBox').open = true")
        eq('remember is off at the start', page.is_checked('#remChk'), False)
        page.check('#remChk')
        eq('toast when turned on', toast(page), 'Your entries will be kept on this device.')
        fill_form(page, 'url', {'url': 'kept-example.com/page'})
        fill_form(page, 'wifi', {'ssid': 'KeptNet', 'password': 'NeverStoreMe99'})
        fill_form(page, 'contact', {'first': 'Kept', 'last': 'Person', 'street': '9 Kept Rd'})
        put(page, '#capIn', 'kept caption')
        page.wait_for_timeout(500)
        raw = stored(page)
        has('the address is kept', raw, 'kept-example.com/page')
        has('the network name is kept', raw, 'KeptNet')
        has('the contact is kept', raw, 'Kept Rd')
        has('the caption is kept', raw, 'kept caption')
        lacks('but never the password', raw, 'NeverStoreMe99')
        page.reload()
        page.wait_for_timeout(300)
        eq('remember stays on', page.evaluate("document.getElementById('optsBox').open || true") and page.is_checked('#remChk'), True)
        eq('came back on the contact tab', hook(page, 'q.state().type'), 'contact')
        eq('contact is filled in', (page.input_value('#f-first'), page.input_value('#f-street')), ('Kept', '9 Kept Rd'))
        pick(page, 'url')
        eq('address is filled in', page.input_value('#f-url'), 'kept-example.com/page')
        pick(page, 'wifi')
        eq('network name is filled in, password is not', (page.input_value('#f-ssid'), page.input_value('#f-password')), ('KeptNet', ''))
        eq('caption is filled in', page.input_value('#capIn'), 'kept caption')
        # off again
        page.evaluate("document.getElementById('optsBox').open = true")
        page.uncheck('#remChk')
        eq('toast when turned off', toast(page), 'Your entries will not be kept.')
        raw2 = stored(page)
        lacks('turning it off clears the address', raw2, 'kept-example.com')
        lacks('turning it off clears the contact', raw2, 'Kept Rd')
        lacks('turning it off clears the caption', raw2, 'kept caption')
        ctx.close()

    with section('odd storage'):
        for label, state in (('broken json', '{not json'), ('wrong version', pre(v=2, ecl='H')), ('null', 'null'), ('a number', '7'), ('an array', '[1,2]')):
            ctx, page = new_page(browser, pre_state=state)
            eq(label + ': starts clean', hook(page, '(() => { const s = q.state(); return [s.type, s.ecl, s.size]; })()'), ['url', 'M', 1024])
            eq(label + ': works', (fill_form(page, 'url', {'url': 'example.com'}), ready(page))[1], True)
            ctx.close()
        evil = pre(type='__proto__', ecl=['L'], size=99999, quiet=50, fg='red;background:url(x)', bg=['#ff0000'], style='hax', printMm=1, transparent='yes',
                   remember=True, signPass=1, data={'url': {'url': 'javascript:alert(1)'}, '__proto__': {'x': 1}, 'wifi': {'ssid': 'Net', 'password': 'LEAK', 'security': 'WEP', 'hidden': 'true'}})
        ctx, page = new_page(browser, pre_state=evil)
        st = hook(page, '(() => { const s = q.state(); return [s.type, s.ecl, s.size, s.quiet, s.fg, s.bg, s.style, s.printMm, s.transparent, s.signPass]; })()')
        eq('odd values fall back to safe ones', st, ['url', 'M', 1024, 8, '#000000', '#ff0000', 'square', 75, False, False])
        eq('a stored address is just text', page.input_value('#f-url'), 'javascript:alert(1)')
        pick(page, 'wifi')
        eq('a stored password is ignored', (page.input_value('#f-ssid'), page.input_value('#f-password'), page.input_value('#f-security'), page.is_checked('#f-hidden')), ('Net', '', 'WEP', False))
        ctx.close()

    with section('storage that throws'):
        blocked = "Storage.prototype.getItem = function () { throw new Error('denied'); }; Storage.prototype.setItem = function () { throw new Error('denied'); };"
        ctx, page = new_page(browser, extra=blocked)
        fill_form(page, 'url', {'url': 'example.com'})
        eq('works without storage', ready(page), True)
        page.evaluate("document.getElementById('optsBox').open = true")
        tap(page, '#eclChips [data-v="H"]')
        page.check('#remChk')
        eq('still works after changes', hook(page, 'q.cur().code.level'), 'H')
        ctx.close()
        gone = "Object.defineProperty(window, 'localStorage', {configurable: true, get: function () { throw new DOMException('denied', 'SecurityError'); }});"
        ctx, page = new_page(browser, extra=gone)
        fill_form(page, 'url', {'url': 'example.com'})
        eq('works with no localStorage at all', ready(page), True)
        ctx.close()
