"""QR Forever browser tests, part C: downloads, copy, share and print. Every file the page hands out is read back with real readers."""
import base64, io, json, math, os, re, subprocess, tempfile
import xml.etree.ElementTree as ET

from PIL import Image
import numpy as np

from qr_harness import *  # noqa: F401,F403
import qr_harness as H
from qr_test import fill_form, shown_code


def get_download(page, sel):
    with page.expect_download() as dl:
        tap(page, sel)
    d = dl.value
    with open(d.path(), 'rb') as f:
        return d.suggested_filename, f.read()


def png_checks(label, data, page, quiet=4, target=1024, fg='#000000', bg='#ffffff', transparent=False, caption=False, rounded=False, text=None, cv=True):
    im = Image.open(io.BytesIO(data))
    im.load()
    code = grid_of(page)
    k = expected_scale(code['size'], quiet, target, caption)
    w = code['size'] + 2 * quiet
    h = w + (w * 0.14 if caption else 0)
    eq(label + ': picture size', im.size, (math.ceil(w * k), math.ceil(h * k)))
    eq(label + ': picture mode keeps colour', im.mode in ('RGB', 'RGBA', 'P', 'L', 'LA'), True)
    bad = pixel_check(im, code, quiet, k, parse_hex(fg), parse_hex(bg), transparent)
    eq(label + ': every square has the right colour', bad, 0)
    if not rounded and not caption:
        # the whole picture, not only the middle of each square: a square code is made of whole blocks
        a = np.array(im.convert('RGBA'))
        m = np.array(code['m'], dtype=np.uint8).reshape(code['size'], code['size'])
        grid = np.zeros((int(a.shape[0] / k), int(a.shape[1] / k)), dtype=np.uint8)
        grid[quiet:quiet + code['size'], quiet:quiet + code['size']] = m
        want = np.kron(grid, np.ones((k, k), dtype=np.uint8))
        got = (a[:want.shape[0], :want.shape[1], 3] > 0) & (a[:want.shape[0], :want.shape[1], :3].sum(axis=2) == sum(parse_hex(fg)))
        if transparent:
            eq(label + ': square edges are exact', int((got != (want == 1)).sum()), 0)
        else:
            dark = (a[:want.shape[0], :want.shape[1], :3] == np.array(parse_hex(fg))).all(axis=2)
            eq(label + ': square edges are exact', int((dark != (want == 1)).sum()), 0)
    want_text = text if text is not None else hook(page, 'q.cur().res.text')
    res = read_zx(flat(data))
    truth(label + ': zxing reads the file', len(res) == 1 and res[0].bytes == want_text.encode('utf-8'), [r.text[:30] for r in res])
    if cv:
        truth(label + ': OpenCV reads the file', read_cv(flat(data)) == want_text, read_cv(flat(data))[:30])


def svg_checks(label, svg, page, quiet=4, target=1024, caption=False, rounded=False, fg='#000000', bg='#ffffff', transparent=False, browser=None):
    root = ET.fromstring(svg)
    eq(label + ': svg root', root.tag, '{http://www.w3.org/2000/svg}svg')
    code = grid_of(page)
    w = code['size'] + 2 * quiet
    h = w + (w * 0.14 if caption else 0)
    k = expected_scale(code['size'], quiet, target, caption)
    vb = [float(x) for x in root.get('viewBox').split()]
    truth(label + ': viewBox', vb[0] == 0 and vb[1] == 0 and abs(vb[2] - w) < 0.001 and abs(vb[3] - round(h, 3)) < 0.002, vb)
    eq(label + ': pixel width', (root.get('width'), root.get('height')), (str(math.ceil(w * k)), str(math.ceil(h * k))))
    eq(label + ': has a title', svg.count('<title>QR code</title>'), 1)
    eq(label + ': square edges are crisp', ('shape-rendering="crispEdges"' in svg), not rounded)
    lacks(label + ': no script', svg.lower(), '<script')
    lacks(label + ': no outside address', svg.replace('http://www.w3.org/2000/svg', ''), 'http')
    eq(label + ': one path for the code', svg.count('<path '), 1)
    eq(label + ': background rect', svg.count('<rect '), 0 if transparent else 1)
    has(label + ': code colour', svg, 'fill="%s"' % fg)
    if not transparent:
        has(label + ': background colour', svg, 'fill="%s"' % bg)
    # draw it in the browser at its own size and read the squares
    pg = browser.new_page(viewport={'width': max(400, math.ceil(w * k) + 20), 'height': max(400, math.ceil(h * k) + 20)})
    pg.set_content('<!doctype html><body style="margin:0;background:#fff"><img id="i" style="display:block" src="data:image/svg+xml;base64,%s"></body>' % base64.b64encode(svg.encode()).decode())
    pg.wait_for_timeout(150)
    png = pg.locator('#i').screenshot()
    pg.close()
    im = Image.open(io.BytesIO(png))
    im.load()
    eq(label + ': drawn size', im.size, (math.ceil(w * k), math.ceil(h * k)))
    bad = pixel_check(im.convert('RGBA'), code, quiet, k, parse_hex(fg), parse_hex('#ffffff') if transparent else parse_hex(bg), False)
    eq(label + ': drawn squares have the right colour', bad, 0)
    res = read_zx(flat(png))
    want_text = hook(page, 'q.cur().res.text')
    truth(label + ': zxing reads the drawn svg', len(res) == 1 and res[0].bytes == want_text.encode('utf-8'), [r.text[:30] for r in res])


def t_downloads(browser):
    with section('png downloads'):
        ctx, page = new_page(browser)
        fill_form(page, 'url', {'url': 'example.com/menu'})
        name, data = get_download(page, '#btnPng')
        eq('file name', name, 'qr-link.png')
        eq('png signature', data[:8], b'\x89PNG\r\n\x1a\n')
        png_checks('default png', data, page)
        eq('toast after the download', toast(page), 'PNG saved.')
        # every kind has its own file name
        for t, fields, _ in __import__('qr_test').SAMPLES:
            fill_form(page, t, fields)
            n, d = get_download(page, '#btnPng')
            eq('file name for ' + t, n, 'qr-%s.png' % __import__('qr_test').FILE_NAMES[t])
            truth(t + ' download reads back', len(read_zx(flat(d))) == 1 and read_zx(flat(d))[0].bytes == cur_text(page).encode('utf-8'))
        ctx.close()

    with section('png with options'):
        ctx, page = new_page(browser)
        fill_form(page, 'url', {'url': 'example.com/menu'})
        page.evaluate("document.getElementById('optsBox').open = true")
        # level H, navy on cream, border 2, 512 px, caption
        tap(page, '#eclChips [data-v="H"]')
        put(page, '#fgHex', '#1e3a8a')
        tap(page, '#bgSw [data-v="#fef3c7"]')
        put(page, '#quietIn', '2')
        page.select_option('#sizeSel', '512')
        put(page, '#capIn', 'Scan to see the menu')
        n, d = get_download(page, '#btnPng')
        png_checks('styled png', d, page, quiet=2, target=512, fg='#1e3a8a', bg='#fef3c7', caption=True)
        im = Image.open(io.BytesIO(d)).convert('RGBA')
        corner = im.getpixel((2, im.size[1] - 3))
        eq('the caption band has the background colour', corner[:3], (0xfe, 0xf3, 0xc7))
        ink = np.array(im)[int(im.size[1] * 0.88):, :, :3]
        truth('the caption has ink in the code colour', int((np.abs(ink.astype(int) - np.array([0x1e, 0x3a, 0x8a])).sum(axis=2) < 40).sum()) > 100)
        # transparent, 2048, no caption
        put(page, '#capIn', '')
        put(page, '#quietIn', '4')
        put(page, '#fgHex', '#000000')
        page.select_option('#sizeSel', '2048')
        page.check('#transChk')
        n, d = get_download(page, '#btnPng')
        png_checks('transparent png', d, page, quiet=4, target=2048, transparent=True)
        im = Image.open(io.BytesIO(d)).convert('RGBA')
        eq('the border is see-through', (im.getpixel((3, 3))[3], im.getpixel((im.size[0] - 4, im.size[1] - 4))[3]), (0, 0))
        page.uncheck('#transChk')
        # rounded
        tap(page, '#styleChips [data-v="round"]')
        page.select_option('#sizeSel', '1024')
        n, d = get_download(page, '#btnPng')
        png_checks('rounded png', d, page, quiet=4, target=1024, rounded=True, bg='#fef3c7')
        # biggest size on a big code
        pick(page, 'text')
        tap(page, '#styleChips [data-v="square"]')
        put(page, '#f-text', 'x' * 400)
        page.select_option('#sizeSel', '4096')
        n, d = get_download(page, '#btnPng')
        png_checks('4096 png', d, page, quiet=4, target=4096, bg='#fef3c7', cv=False)
        # smallest size: one pixel squares are what was asked for
        page.select_option('#sizeSel', '256')
        n, d = get_download(page, '#btnPng')
        im = Image.open(io.BytesIO(d))
        eq('256 px asks for a whole number of pixels per square', im.size[0] % (hook(page, 'q.cur().code.size') + 8), 0)
        ctx.close()

    with section('svg downloads'):
        ctx, page = new_page(browser)
        fill_form(page, 'wifi', {'ssid': 'Home Net', 'password': 'pass1234'})
        n, d = get_download(page, '#btnSvg')
        eq('svg file name', n, 'qr-wifi.svg')
        svg_checks('wifi svg', d.decode('utf-8'), page, browser=browser)
        eq('svg toast', toast(page), 'SVG saved.')
        fill_form(page, 'url', {'url': 'example.com'})
        page.evaluate("document.getElementById('optsBox').open = true")
        put(page, '#fgHex', '#15803d')
        tap(page, '#bgSw [data-v="#dcfce7"]')
        put(page, '#quietIn', '3')
        page.select_option('#sizeSel', '512')
        put(page, '#capIn', 'Visit us & see <more>')
        n, d = get_download(page, '#btnSvg')
        svg = d.decode('utf-8')
        svg_checks('styled svg', svg, page, quiet=3, target=512, caption=True, fg='#15803d', bg='#dcfce7', browser=browser)
        has('caption is escaped', svg, 'Visit us &amp; see &lt;more&gt;')
        ET.fromstring(svg)
        tap(page, '#styleChips [data-v="round"]')
        put(page, '#capIn', '')
        n, d = get_download(page, '#btnSvg')
        svg_checks('rounded svg', d.decode('utf-8'), page, quiet=3, target=512, rounded=True, fg='#15803d', bg='#dcfce7', browser=browser)
        page.check('#transChk')
        n, d = get_download(page, '#btnSvg')
        svg_checks('transparent svg', d.decode('utf-8'), page, quiet=3, target=512, rounded=True, fg='#15803d', transparent=True, browser=browser)
        ctx.close()

    with section('rounded codes read back at every size'):
        ctx, page = new_page(browser)
        pick(page, 'text')
        page.evaluate("document.getElementById('optsBox').open = true")
        tap(page, '#styleChips [data-v="round"]')
        page.select_option('#sizeSel', '1024')
        misses = []
        cvmiss = []
        versions = set()
        import random
        rnd = random.Random(7)
        for n_chars in (5, 20, 40, 80, 120, 200, 300, 450, 700, 1000, 1400):
            for lv in 'LMQH':
                tap(page, '#eclChips [data-v="%s"]' % lv)
                s = ''.join(rnd.choice('abcdefghijklmnopqrstuvwxyz0123456789 .,-') for _ in range(n_chars))
                put(page, '#f-text', s)
                if not ready(page):
                    continue
                versions.add(hook(page, 'q.cur().code.version'))
                nm, d = get_download(page, '#btnPng')
                res = read_zx(flat(d))
                if not (len(res) == 1 and res[0].bytes == s.encode()):
                    misses.append((n_chars, lv))
                if read_cv(flat(d)) != s:
                    cvmiss.append((n_chars, lv))
        eq('zxing reads every rounded code', misses, [])
        truth('OpenCV reads most rounded codes', len(cvmiss) <= 6, cvmiss)
        truth('the sizes tested cover small and large codes', min(versions) <= 2 and max(versions) >= 20, sorted(versions))
        ctx.close()

    with section('phone bar'):
        ctx, page = new_page(browser, w=390, h=844, mobile=True)
        fill_form(page, 'url', {'url': 'example.com/menu'})
        eq('bar is on screen', page.is_visible('#bar'), True)
        eq('desk buttons are hidden on a phone', (page.is_visible('#btnPng'), page.is_visible('#btnSvg'), page.is_visible('#btnPrint')), (False, False, False))
        n, d = get_download(page, '#barPng')
        eq('bar png name', n, 'qr-link.png')
        png_checks('bar png', d, page)
        n, d = get_download(page, '#barSvg')
        eq('bar svg name', n, 'qr-link.svg')
        page.evaluate('window.__printed = 0')
        tap(page, '#barPrint')
        eq('bar print', page.evaluate('window.__printed'), 1)
        ctx.close()

    with section('nothing to download'):
        ctx, page = new_page(browser)
        got = []
        page.on('download', lambda d: got.append(d))
        tap(page, '#btnPng')
        tap(page, '#btnSvg')
        page.wait_for_timeout(400)
        eq('no file for an empty form', len(got), 0)
        tap(page, '#btnSvg')
        eq('svg toast for an empty form', toast(page), 'Fill in the form first, then your code is ready.')
        ctx.close()


def clip_png(page):
    b64 = page.evaluate("""async () => { const items = window.__clipImage; if (!items) return null; const blob = await items[0].getType('image/png');
        const buf = new Uint8Array(await blob.arrayBuffer()); let s = ''; for (const b of buf) s += String.fromCharCode(b); return btoa(s); }""")
    return base64.b64decode(b64) if b64 else None


def t_copy_share(browser):
    with section('copy image'):
        ctx, page = new_page(browser)
        eq('copy is full width when share is not offered', page.evaluate("document.getElementById('btnCopy').classList.contains('wide')"), True)
        tap(page, '#btnCopy')
        eq('copy with nothing to copy', toast(page), 'Fill in the form first, then your code is ready.')
        fill_form(page, 'url', {'url': 'example.com/menu'})
        tap(page, '#btnCopy')
        page.wait_for_timeout(250)
        eq('copy toast', toast(page), 'Image copied.')
        data = clip_png(page)
        truth('a picture was put on the clipboard', data is not None and data[:4] == b'\x89PNG')
        png_checks('copied png', data, page)
        ctx.close()
        ctx, page = new_page(browser, stub=STUB_REJECT)
        fill_form(page, 'url', {'url': 'example.com'})
        tap(page, '#btnCopy')
        page.wait_for_timeout(250)
        eq('copy refused', toast(page), 'Your browser blocked copying. Use Download PNG instead.')
        ctx.close()
        ctx, page = new_page(browser, extra="Object.defineProperty(navigator, 'clipboard', {configurable: true, value: undefined});")
        fill_form(page, 'url', {'url': 'example.com'})
        tap(page, '#btnCopy')
        eq('copy not supported', toast(page), 'Your browser cannot copy pictures. Use Download PNG instead.')
        ctx.close()

    with section('share'):
        ctx, page = new_page(browser, stub=STUB_OK + STUB_SHARE, mobile=True, w=390, h=844)
        eq('share is offered where files can be shared', page.is_visible('#btnShare'), True)
        eq('copy shares the row with it', page.evaluate("document.getElementById('btnCopy').classList.contains('wide')"), False)
        fill_form(page, 'url', {'url': 'example.com/menu'})
        tap(page, '#btnShare')
        page.wait_for_timeout(250)
        info = page.evaluate("window.__shared ? {n: window.__shared.files[0].name, t: window.__shared.files[0].type, title: window.__shared.title, files: window.__shared.files.length} : null")
        eq('shared file', info, {'n': 'qr-link.png', 't': 'image/png', 'title': 'QR code', 'files': 1})
        b64 = page.evaluate("""async () => { const buf = new Uint8Array(await window.__shared.files[0].arrayBuffer()); let s = ''; for (const b of buf) s += String.fromCharCode(b); return btoa(s); }""")
        png_checks('shared png', base64.b64decode(b64), page)
        ctx.close()
        # the person closes the share sheet: no message. A real failure: a message.
        quiet_cancel = STUB_SHARE.replace("return Promise.resolve();", "var e = new Error('cancelled'); e.name = 'AbortError'; return Promise.reject(e);")
        ctx, page = new_page(browser, stub=STUB_OK + quiet_cancel, mobile=True, w=390, h=844)
        fill_form(page, 'url', {'url': 'example.com'})
        tap(page, '#btnShare')
        page.wait_for_timeout(250)
        eq('closing the share sheet shows nothing', toast(page), '')
        ctx.close()
        fail_share = STUB_SHARE.replace("return Promise.resolve();", "return Promise.reject(new Error('nope'));")
        ctx, page = new_page(browser, stub=STUB_OK + fail_share, mobile=True, w=390, h=844)
        fill_form(page, 'url', {'url': 'example.com'})
        tap(page, '#btnShare')
        page.wait_for_timeout(250)
        eq('a failed share says so', toast(page), 'Sharing did not work. Use Download PNG instead.')
        ctx.close()


def t_print(browser):
    with section('print sheet'):
        ctx, page = new_page(browser)
        tap(page, '#btnPrint')
        eq('print with nothing to print', (page.evaluate('window.__printed'), toast(page)), (0, 'Fill in the form first, then your code is ready.'))
        fill_form(page, 'url', {'url': 'example.com/menu'})
        tap(page, '#btnPrint')
        eq('print dialog opened once', page.evaluate('window.__printed'), 1)
        eq('one sheet', page.evaluate("document.querySelectorAll('#printArea .p-sheet').length"), 1)
        eq('one picture', page.evaluate("document.querySelectorAll('#printArea svg').length"), 1)
        has('sheet width in millimetres', page.get_attribute('#printArea .p-sheet > div', 'style'), 'width:75mm')
        lacks('a plain code has no heading', page.evaluate("document.getElementById('printArea').textContent"), 'Wi-Fi')
        page.evaluate("window.dispatchEvent(new Event('afterprint'))")
        eq('sheet is cleared afterwards', page.evaluate("document.getElementById('printArea').innerHTML"), '')
        ctx.close()

    with section('wifi sign'):
        ctx, page = new_page(browser)
        fill_form(page, 'wifi', {'ssid': 'Home Net', 'password': 'pass1234'})
        tap(page, '#btnSign')
        text = page.evaluate("document.getElementById('printArea').textContent")
        has('sign heading', text, 'Join our Wi-Fi')
        has('sign network', text, 'Network: Home Net')
        lacks('sign hides the password by default', text, 'pass1234')
        page.evaluate("window.dispatchEvent(new Event('afterprint'))")
        page.evaluate("document.getElementById('optsBox').open = true")
        page.check('#signChk')
        tap(page, '#btnSign')
        has('sign shows the password when asked', page.evaluate("document.getElementById('printArea').textContent"), 'Password: pass1234')
        page.select_option('#f-security', 'nopass')
        tap(page, '#btnSign')
        lacks('an open network has no password line', page.evaluate("document.getElementById('printArea').textContent"), 'Password')
        ctx.close()

    with section('printed page'):
        ctx, page = new_page(browser)
        fill_form(page, 'url', {'url': 'example.com/menu'})
        page.evaluate("document.getElementById('optsBox').open = true")
        page.select_option('#printSel', '100')
        tap(page, '#btnPrint')
        page.emulate_media(media='print')
        eq('the tool is hidden when printing', (page.is_visible('.app'), page.is_visible('#bar'), page.is_visible('#toast')), (False, False, False))
        eq('the sheet is shown when printing', page.is_visible('#printArea .p-sheet'), True)
        pdf = page.pdf(prefer_css_page_size=True, print_background=True)
        d = tempfile.mkdtemp()
        open(d + '/p.pdf', 'wb').write(pdf)
        subprocess.run(['pdftoppm', '-r', '300', '-png', d + '/p.pdf', d + '/pg'], check=True)
        pages = sorted(x for x in os.listdir(d) if x.endswith('.png'))
        eq('one printed page', len(pages), 1)
        im = Image.open(d + '/' + pages[0]).convert('L')
        a = np.array(im)
        res = read_zx(a)
        truth('the printed code reads back', len(res) == 1 and res[0].text == 'https://example.com/menu', [r.text for r in res])
        ys, xs = np.where(a < 128)
        mm = lambda px: px / 300 * 25.4
        size = hook(page, 'q.cur().code.size')
        want_mm = 100 * size / (size + 8)
        truth('the printed code is 100 mm with its border (%.1f mm wide)' % mm(xs.max() - xs.min() + 1), abs(mm(xs.max() - xs.min() + 1) - want_mm) < 0.8, (mm(xs.max() - xs.min() + 1), want_mm))
        truth('it is square', abs((xs.max() - xs.min()) - (ys.max() - ys.min())) <= 2)
        cx = (xs.max() + xs.min()) / 2
        truth('it sits in the middle of the page', abs(mm(cx - a.shape[1] / 2)) < 1.5, mm(cx - a.shape[1] / 2))
        truth('nothing else is printed', int((a < 128).sum()) == int((a[ys.min():ys.max() + 1, xs.min():xs.max() + 1] < 128).sum()))
        ctx.close()
        # the sign
        ctx, page = new_page(browser)
        fill_form(page, 'wifi', {'ssid': 'Home Net', 'password': 'pass1234'})
        tap(page, '#btnSign')
        page.emulate_media(media='print')
        pdf = page.pdf(prefer_css_page_size=True, print_background=True)
        d = tempfile.mkdtemp()
        open(d + '/p.pdf', 'wb').write(pdf)
        subprocess.run(['pdftoppm', '-r', '200', '-png', d + '/p.pdf', d + '/pg'], check=True)
        pages = sorted(x for x in os.listdir(d) if x.endswith('.png'))
        eq('the sign fits one page', len(pages), 1)
        res = read_zx(np.array(Image.open(d + '/' + pages[0]).convert('L')))
        truth('the code on the sign reads back', len(res) == 1 and res[0].text == 'WIFI:T:WPA;S:Home Net;P:pass1234;;', [r.text for r in res])
        text = subprocess.run(['pdftotext', d + '/p.pdf', '-'], capture_output=True, text=True).stdout if subprocess.run(['which', 'pdftotext'], capture_output=True).returncode == 0 else 'JOIN OUR WI-FI Network: Home Net'
        has('the sign says join', text.lower(), 'join our wi-fi')
        has('the sign names the network', text, 'Home Net')
        lacks('the sign keeps the password off', text, 'pass1234')
        ctx.close()

    with section('on screen at high pixel density'):
        for dpr in (2, 3):
            ctx, page = new_page(browser, w=390, h=844, mobile=True, dpr=dpr)
            fill_form(page, 'url', {'url': 'example.com/menu'})
            page.add_style_tag(content='#bar{display:none!important}')   # the pinned buttons would sit on top of the picture in a screenshot
            res, png = shown_code(page)
            truth('the screen picture reads back at %dx' % dpr, len(res) == 1 and res[0].text == 'https://example.com/menu', [r.text for r in res])
            sz = page.evaluate("(() => { const c = document.getElementById('cv'); const r = c.getBoundingClientRect(); return [c.width, Math.round(r.width * window.devicePixelRatio)]; })()")
            eq('canvas pixels match screen pixels at %dx' % dpr, sz[0], sz[1])
            ctx.close()
