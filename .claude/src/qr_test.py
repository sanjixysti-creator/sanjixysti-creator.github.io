#!/usr/bin/env python3
"""Browser tests for the built QR Forever page (site/qr-forever/index.html, or the file named in QR_STANDALONE).

Everything runs in Chromium against a local copy of the site with Google Fonts blocked-by-default (the built page has no outside requests).
Codes that the page draws or exports are read back with zxing-cpp and OpenCV, so a pass means a real phone-style reader can read them.
"""
import io, json, math, os, re, subprocess, sys, tempfile, time

from qr_harness import *  # noqa: F401,F403
import qr_harness as H

SAMPLES = [
    ('url', {'url': 'example.com/menu'}, 'https://example.com/menu'),
    ('text', {'text': 'Hello\nWorld'}, 'Hello\nWorld'),
    ('wifi', {'ssid': 'Home Net', 'password': 'pass1234'}, 'WIFI:T:WPA;S:Home Net;P:pass1234;;'),
    ('email', {'to': 'a@b.co', 'subject': 'Hi there', 'body': 'Line1\nLine2'}, 'mailto:a@b.co?subject=Hi%20there&body=Line1%0D%0ALine2'),
    ('phone', {'phone': '+1 (555) 123-4567'}, 'tel:+15551234567'),
    ('sms', {'phone': '+15551234567', 'message': 'Hi!'}, 'sms:+15551234567?body=Hi%21'),
    ('contact', {'first': 'Ada', 'last': 'Lovelace', 'org': 'Analytical Co', 'mobile': '+15551234567', 'email': 'ada@example.com', 'url': 'example.com'}, None),
    ('map', {'lat': '37.7749', 'lng': '-122.4194'}, 'geo:37.7749,-122.4194'),
    ('event', {'title': 'Launch party', 'start': '2026-12-31T21:00', 'end': '2027-01-01T01:00', 'where': 'HQ'}, None),
]
FILE_NAMES = {'url': 'link', 'text': 'text', 'wifi': 'wifi', 'email': 'email', 'phone': 'phone', 'sms': 'sms', 'contact': 'contact', 'map': 'map', 'event': 'event'}


def fill_form(page, type_, fields):
    pick(page, type_)
    for k, v in fields.items():
        sel = '#f-' + k
        if isinstance(v, bool):
            page.set_checked(sel, v)
        elif k == 'security' or k == 'how':
            page.select_option(sel, v)
        else:
            # an address section stays closed until opened
            page.evaluate("(s) => { const e = document.querySelector(s); const d = e && e.closest('details'); if (d) d.open = true; }", sel)
            put(page, sel, v)
    page.wait_for_timeout(60)


def shown_code(page):
    """The code on the screen, as the picture the person sees, read by zxing-cpp."""
    png = page.locator('#cv').screenshot()
    return read_zx(flat(png)), png


def run(browser):
    # ------------------------------------------------------------ 1 load and structure
    with section('load'):
        ctx, page = new_page(browser)
        eq('document title', page.title(), SITE_TITLE)
        eq('lang', page.evaluate('document.documentElement.lang'), 'en')
        eq('one h1', page.evaluate("document.querySelectorAll('h1').length"), 1)
        eq('h1 text', txt(page, 'h1'), 'QR Forever')
        eq('one main landmark', page.evaluate("document.querySelectorAll('main').length"), 1)
        eq('first tab is selected', page.get_attribute('#tab-url', 'aria-selected'), 'true')
        eq('test hook is on with #test', page.evaluate('typeof window.__qr'), 'object')
        eq('starts on the sample', page.is_visible('#sampleTag'), True)
        eq('sample status', status(page), 'Fill in the form and your code appears here. This is a sample.')
        eq('buttons start disabled', page.evaluate("['btnPng','btnSvg','btnPrint','btnCopy','barPng','barSvg','barPrint'].every(i => document.getElementById(i).getAttribute('aria-disabled') === 'true')"), True)
        eq('desktop focuses the first box', page.evaluate("document.activeElement && document.activeElement.id"), 'f-url')
        eq('sample canvas is drawn', page.evaluate("(() => { const c = document.getElementById('cv'); return c.width > 100 && c.height > 100; })()"), True)
        eq('sample label', page.get_attribute('#cv', 'aria-label'), 'Sample QR code. Fill in the form to make yours.')
        eq('sample is not offered as a download', page.is_visible('#btnShare'), False)
        ctx.close()
        ctx2, page2 = new_page(browser, url=URL_PLAIN)
        eq('no test hook without #test', page2.evaluate('typeof window.__qr'), 'undefined')
        ctx2.close()

    # ------------------------------------------------------------ 2 tabs
    with section('tabs'):
        ctx, page = new_page(browser)
        names = page.evaluate("[...document.querySelectorAll('#tabs .tab')].map(t => t.textContent)")
        eq('nine kinds in order', names, ['Link', 'Text', 'Wi-Fi', 'Email', 'Phone', 'SMS', 'Contact', 'Map', 'Event'])
        eq('tablist role', page.get_attribute('#tabs', 'role'), 'tablist')
        eq('every tab has role tab', page.evaluate("[...document.querySelectorAll('#tabs .tab')].every(t => t.getAttribute('role') === 'tab')"), True)
        eq('only one tab is in the tab order', page.evaluate("[...document.querySelectorAll('#tabs .tab')].filter(t => t.tabIndex === 0).length"), 1)
        page.click('#tab-wifi')   # a real mouse click, not a script click: only a pointer click moves into the form
        eq('clicking selects', page.get_attribute('#tab-wifi', 'aria-selected'), 'true')
        eq('the old one is deselected', page.get_attribute('#tab-url', 'aria-selected'), 'false')
        eq('panel is labelled by the tab', page.get_attribute('#panel', 'aria-labelledby'), 'tab-wifi')
        eq('wifi fields appear', page.evaluate("[...document.querySelectorAll('#fields [data-field]')].map(e => e.getAttribute('data-field'))"), ['ssid', 'password', 'security', 'hidden'])
        eq('mouse click puts the cursor in the first box', page.evaluate('document.activeElement.id'), 'f-ssid')
        page.focus('#tab-text')
        page.keyboard.press('Enter')
        eq('Enter on a tab chooses it and stays on the tab', (page.get_attribute('#tab-text', 'aria-selected'), page.evaluate('document.activeElement.id')), ('true', 'tab-text'))
        page.keyboard.press('Space')
        eq('Space on the tab does not type into the form', (page.evaluate('document.activeElement.id'), page.input_value('#f-text')), ('tab-text', ''))
        page.focus('#tab-wifi')
        page.keyboard.press('ArrowRight')
        eq('arrow right moves on', (page.get_attribute('#tab-email', 'aria-selected'), page.evaluate('document.activeElement.id')), ('true', 'tab-email'))
        page.keyboard.press('ArrowLeft')
        page.keyboard.press('ArrowLeft')
        eq('arrow left twice goes back two', page.evaluate('document.activeElement.id'), 'tab-text')
        page.keyboard.press('ArrowLeft')
        eq('arrow left reaches the first', page.evaluate('document.activeElement.id'), 'tab-url')
        page.keyboard.press('ArrowLeft')
        eq('arrow left wraps to the last', page.evaluate('document.activeElement.id'), 'tab-event')
        page.keyboard.press('Home')
        eq('home goes to the first', page.evaluate('document.activeElement.id'), 'tab-url')
        page.keyboard.press('End')
        eq('end goes to the last', (page.evaluate('document.activeElement.id'), page.get_attribute('#tab-event', 'aria-selected')), ('tab-event', 'true'))
        eq('event fields', page.evaluate("[...document.querySelectorAll('#fields [data-field]')].map(e => e.getAttribute('data-field'))"), ['title', 'allday', 'start', 'end', 'where', 'details'])
        for t, fields in (('url', ['url']), ('text', ['text']), ('email', ['to', 'subject', 'body']), ('phone', ['phone']), ('sms', ['phone', 'message']),
                          ('map', ['lat', 'lng', 'how']),
                          ('contact', ['first', 'last', 'org', 'title', 'mobile', 'work', 'email', 'url', 'street', 'city', 'region', 'zip', 'country'])):
            pick(page, t)
            eq('fields of ' + t, page.evaluate("[...document.querySelectorAll('#fields [data-field]')].map(e => e.getAttribute('data-field'))"), fields)
        ctx.close()

    # ------------------------------------------------------------ 3 every kind makes a code that reads back
    with section('every kind'):
        ctx, page = new_page(browser)
        for type_, fields, want in SAMPLES:
            fill_form(page, type_, fields)
            eq(type_ + ': ready', ready(page), True)
            text = cur_text(page)
            if want is not None:
                eq(type_ + ': payload', text, want)
            if type_ == 'contact':
                truth('contact payload is a card', text.startswith('BEGIN:VCARD\r\nVERSION:3.0') and 'FN:Ada Lovelace' in text and 'TEL;TYPE=CELL:+15551234567' in text, text)
            if type_ == 'event':
                truth('event payload is an event', 'SUMMARY:Launch party' in text and 'DTSTART:20261231T210000' in text and 'DTEND:20270101T010000' in text and 'LOCATION:HQ' in text, text)
            res, png = shown_code(page)
            truth(type_ + ': the picture on screen reads back', len(res) == 1 and res[0].bytes == text.encode('utf-8'), [(r.text[:40]) for r in res])
            eq(type_ + ': status says ready', status(page), 'Ready. Download it, print it or copy it.')
            eq(type_ + ': sample tag is gone', page.is_visible('#sampleTag'), False)
            eq(type_ + ': buttons are on', page.evaluate("['btnPng','btnSvg','btnPrint','btnCopy','barPng','barSvg','barPrint'].every(i => !document.getElementById(i).hasAttribute('aria-disabled'))"), True)
            eq(type_ + ': what is inside shows the text', txt(page, '#insideText') if type_ != 'wifi' else 'skip', text.strip() if type_ != 'wifi' else 'skip')
            eq(type_ + ': what is inside has the facts', bool(re.match(r'^Version \d+, \d+ x \d+ squares, error correction M, pattern \d\. \d+ bytes\.$', txt(page, '#detailLine'))), True)
            eq(type_ + ': size hint', bool(re.match(r'^\d+ x \d+ squares$', txt(page, '#sizeHint'))), True)
        # back to empty
        pick(page, 'url')
        page.fill('#f-url', '')
        eq('empty again is a sample', (page.is_visible('#sampleTag'), ready(page)), (True, False))
        ctx.close()


def main():
    with sync_playwright() as p:
        browser = launch(p)
        try:
            only = os.environ.get('QR_ONLY', '')
            import qr_test_b, qr_test_c, qr_test_d
            for fn in (run, qr_test_b.t_fields, qr_test_b.t_options, qr_test_b.t_storage, qr_test_c.t_downloads, qr_test_c.t_copy_share, qr_test_c.t_print,
                       qr_test_d.t_layout, qr_test_d.t_accessibility, qr_test_d.t_site, qr_test_d.t_perf):
                if only and only not in fn.__name__:
                    continue
                fn(browser)
        finally:
            browser.close()
    bad_errs = [e for e in H.errs]
    truth('no console errors or warnings', not bad_errs, bad_errs[:5])
    truth('no outside requests', not H.ext_reqs, H.ext_reqs[:5])
    print('passed %d, failed %d' % (H.passes, len(H.fails)))
    for f in H.fails[:60]:
        print('FAIL', f)
    sys.exit(1 if H.fails else 0)


if __name__ == '__main__':
    main()
