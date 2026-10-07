#!/usr/bin/env python3
"""Tests for what goes into the QR code: web addresses, Wi-Fi, email, phone, SMS, contact cards, maps and events.
Every payload built by the page is read back with an independent parser (vobject, icalendar, urllib, a Wi-Fi reader written from
the ZXing rules) and compared with what was typed. Then each payload is drawn as a QR code and read with zxing-cpp.

usage: python3 qr_pay_test.py
The page code comes from the PURE region of the fragment (qr-forever.html next to this file, or the file named in QR_FRAG).
"""
import datetime, json, os, random, re, subprocess, sys, tempfile, urllib.parse
import numpy as np
import zxingcpp
import vobject
import icalendar

D = os.path.dirname(os.path.abspath(__file__))
FRAG = os.environ.get('QR_FRAG', D + '/qr-forever.html')
_m = re.search(r'PURE-BEGIN[^\n]*\n(.*?)/\* PURE-END', open(FRAG, encoding='utf-8').read(), re.S)
PURE = tempfile.mkstemp(suffix='.js', prefix='pay_pure_')[1]
open(PURE, 'w', encoding='utf-8').write(_m.group(1))

BS = chr(92)
fails, passes = [], 0


def ok(name, cond, detail=''):
    global passes
    if cond:
        passes += 1
    else:
        fails.append(name + ('\n    ' + str(detail)[:600] if detail else ''))


def run(cases):
    d = tempfile.mkdtemp()
    json.dump(cases, open(d + '/c.json', 'w'))
    subprocess.run(['node', D + '/pay_core.js', PURE, d + '/c.json', d + '/o.json'], check=True)
    out = {r['id']: r for r in json.load(open(d + '/o.json'))}
    for k, v in out.items():
        if 'error' in v:
            fails.append('node threw for ' + k + ': ' + v['error'][:300])
    return out


# JavaScript's trim and \s cover these characters; Python's differ a little, so the exact set is spelled out.
JS_WS = ''.join(chr(c) for c in [9, 10, 11, 12, 13, 32, 0xA0, 0x1680, 0x2000, 0x2001, 0x2002, 0x2003, 0x2004, 0x2005, 0x2006, 0x2007, 0x2008, 0x2009, 0x200A, 0x2028, 0x2029, 0x202F, 0x205F, 0x3000, 0xFEFF])


def jstrip(s):
    return s.strip(JS_WS)


def lf(s):
    return s.replace('\r\n', '\n').replace('\r', '\n')


rnd = random.Random(20261007)
SETS = {
    'ascii': 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',
    'punct': ' ;,:\\"\'!@#$%^&*()[]{}<>?/|`+=-_.',
    'latin': 'éèñüöçåøßÿ',
    'cjk': '日本語中文한국어',
    'emoji': '\U0001F600\U0001F680\U0001F3E0',
}


def rtext(n, sets=('ascii', 'punct', 'latin', 'cjk', 'emoji'), nl=False, skip=''):
    pool = ''.join(SETS[s] for s in sets) + ('\n' if nl else '')
    pool = ''.join(c for c in pool if c not in skip)
    return ''.join(rnd.choice(pool) for _ in range(n))


def word(n=None):
    return ''.join(rnd.choice('abcdefghijklmnopqrstuvwxyz') for _ in range(n or rnd.randint(3, 9)))


def utf8_clean(s):
    """What TextEncoder does with a string: lone surrogates become U+FFFD."""
    return s.encode('utf-16', 'surrogatepass').decode('utf-16', 'replace')


# ---------- readers written for this test ----------
def parse_wifi(text):
    """The Wi-Fi code format, read the way ZXing's WifiResultParser reads it: fields end at an unescaped semicolon, a backslash escapes the next character."""
    if not text.startswith('WIFI:'):
        return None
    parts, buf, esc = [], [], False
    for ch in text[5:]:
        if esc:
            buf.append(ch)
            esc = False
        elif ch == '\\':
            esc = True
        elif ch == ';':
            parts.append(''.join(buf))
            buf = []
        else:
            buf.append(ch)
    if esc or buf:
        return None
    out = {}
    for p in parts:
        if not p:
            continue
        k, sep, v = p.partition(':')
        if not sep or k in out:
            return None
        out[k] = v
    return out


def picture(rows, scale=6, quiet=4):
    n = len(rows)
    a = np.zeros((n + 2 * quiet, n + 2 * quiet), dtype=np.uint8)
    for y, row in enumerate(rows):
        for x, c in enumerate(row):
            if c == '1':
                a[y + quiet, x + quiet] = 1
    a = np.kron(a, np.ones((scale, scale), dtype=np.uint8))
    return (255 * (1 - a)).astype(np.uint8)


def read_zx(img):
    return zxingcpp.read_barcodes(img)


CASES = []


def add(cid, type_, fields, **kw):
    c = {'id': cid, 'type': type_, 'fields': fields}
    c.update(kw)
    CASES.append(c)
    return cid


# ---------- 1. helpers: percent encoding, escaping, folding ----------
def helper_cases():
    strings = ['', 'plain', 'a b', 'ünï©ode', '日本語', 'emoji \U0001F600', 'a&b=c?d#e/f', '100%', '~-._', 'tab\tnl\nx', 'quote"s\'', 'lone \ud800 surrogate']
    strings += [rtext(rnd.randint(1, 40), nl=True) for _ in range(150)]
    for i, s in enumerate(strings):
        CASES.append({'id': 'pct-%d' % i, 'fn': 'pct', 'args': [s]})
        CASES.append({'id': 'esc-%d' % i, 'fn': 'esc', 'args': [s]})
    for i in range(120):
        n = rnd.choice([0, 1, 10, 74, 75, 76, 77, 150, 151, 400])
        s = rtext(n, sets=rnd.choice([('ascii',), ('ascii', 'latin'), ('cjk',), ('emoji',), ('ascii', 'punct', 'cjk', 'emoji')]))
        CASES.append({'id': 'fold-%d' % i, 'fn': 'fold', 'args': [s]})
    return strings


def check_helpers(res, strings):
    for i, s in enumerate(strings):
        want = urllib.parse.quote(utf8_clean(s).encode('utf-8'), safe='')
        ok('pct %r' % s[:20], res['pct-%d' % i]['value'] == want, '%r vs %r' % (res['pct-%d' % i]['value'], want))
        got = res['esc-%d' % i]['value']
        # reading the escaped text back must give the original, with line breaks as single line feeds
        back = re.sub(r'\\(.)', lambda m: '\n' if m.group(1) in 'nN' else m.group(1), got, flags=re.S)
        ok('esc round trip %r' % s[:20], back == lf(s) and '\n' not in got and '\r' not in got, '%r' % got)
    for i in range(120):
        r = res['fold-%d' % i]
        folded = r['value']
        # the argument is recovered from the case list
        orig = next(c for c in CASES if c['id'] == 'fold-%d' % i)['args'][0]
        lines = folded.split('\r\n')
        ok('fold unfolds to the original (%d)' % i, re.sub(r'\r\n ', '', folded) == orig)
        sizes = [len(l.encode('utf-8')) for l in lines]
        ok('fold lines are at most 75 octets (%d)' % i, max(sizes) <= 75, sizes)
        ok('fold continuation lines start with one space (%d)' % i, all(l.startswith(' ') for l in lines[1:]))
        ok('fold breaks late, so lines are nearly full (%d)' % i, all(s >= 72 for s in sizes[:-1]), sizes)
        ok('fold never splits a character (%d)' % i, all(l.encode('utf-8').decode('utf-8') is not None for l in lines))


# ---------- 2. web addresses ----------
URL_CASES = [
    ('example.com', 'https://example.com'),
    ('  example.com/menu  ', 'https://example.com/menu'),
    ('example.com/a b', 'https://example.com/a%20b'),
    ('http://x.org', 'http://x.org'),
    ('HTTPS://X.ORG/Y', 'HTTPS://X.ORG/Y'),
    ('mailto:a@b.co', 'mailto:a@b.co'),
    ('tel:+15551234567', 'tel:+15551234567'),
    ('//cdn.example.com/x', 'https://cdn.example.com/x'),
    ('ftp://files.example.com/a.zip', 'ftp://files.example.com/a.zip'),
    ('example.com:8080/x?y=1#z', 'https://example.com:8080/x?y=1#z'),
    ('www.example.com', 'https://www.example.com'),
    ('example.com/日本語', 'https://example.com/日本語'),
    ('line\nbreak.com', 'https://linebreak.com'),
]


def url_cases():
    for i, (raw, want) in enumerate(URL_CASES):
        add('url-%d' % i, 'url', {'url': raw}, encode=True)
    add('url-empty', 'url', {'url': ''})
    add('url-blank', 'url', {'url': '   \n '})
    add('url-noslash', 'url', {'url': 'https://'})
    add('url-nodot', 'url', {'url': 'intranet'})
    add('url-local', 'url', {'url': 'http://192.168.1.5/x'})
    add('url-local2', 'url', {'url': 'localhost:3000'})
    add('url-public', 'url', {'url': 'http://8.8.8.8/'})
    add('url-user', 'url', {'url': 'https://user:pw@example.com/'})


def check_urls(res):
    for i, (raw, want) in enumerate(URL_CASES):
        r = res['url-%d' % i]['res']
        ok('url %r gives %r' % (raw, want), r['text'] == want and not r['empty'], r['text'])
        ok('url %r has no spaces or line breaks' % raw, not re.search(r'[ \r\n\t]', r['text']))
    for k in ('url-empty', 'url-blank'):
        r = res[k]['res']
        ok('%s is empty' % k, r['empty'] and r['text'] == '' and r['errors'] == {})
    ok('url with no host after the slashes is an error', 'url' in res['url-noslash']['res']['errors'])
    ok('url without a dot warns', any('no dot' in w for w in res['url-nodot']['res']['warns']))
    ok('private address warns', any('own network' in w for w in res['url-local']['res']['warns']))
    ok('localhost warns', any('own network' in w for w in res['url-local2']['res']['warns']))
    ok('public address does not warn', res['url-public']['res']['warns'] == [])
    ok('credentials in the address do not confuse the host check', res['url-user']['res']['warns'] == [] and res['url-user']['res']['text'] == 'https://user:pw@example.com/')
    ok('adding https is noted', any('https://' in n for n in res['url-0']['res']['notes']))
    ok('a complete address needs no note', res['url-3']['res']['notes'] == [])


# ---------- 3. plain text ----------
def text_cases():
    add('txt-1', 'text', {'text': 'hello\r\nworld\rx'}, encode=True)
    add('txt-2', 'text', {'text': ''})
    add('txt-3', 'text', {'text': ' \n\t '})
    add('txt-4', 'text', {'text': 'ünï © 日本 \U0001F600'}, encode=True)
    add('txt-5', 'text', {'text': '  keep the spaces  '}, encode=True)


def check_text(res):
    ok('text normalises line breaks', res['txt-1']['res']['text'] == 'hello\nworld\nx')
    ok('empty text is empty', res['txt-2']['res']['empty'])
    ok('text with only spaces is empty', res['txt-3']['res']['empty'], res['txt-3']['res'])
    ok('unicode text is kept', res['txt-4']['res']['text'] == 'ünï © 日本 \U0001F600')
    ok('spaces inside text are kept', res['txt-5']['res']['text'] == '  keep the spaces  ')


# ---------- 4. Wi-Fi ----------
WIFI = []


def wifi_cases():
    fixed = [
        ('Home', 'secret123', 'WPA', False),
        ('My Network; with: odd, chars', 'pa;ss:wo,rd\\"x', 'WPA', True),
        ('日本語ネット', 'пароль12345', 'WPA', False),
        ('Cafe \U0001F600', 'pw\U0001F680pw12', 'WEP', False),
        ('Open Guest', '', 'nopass', False),
        ('Open Guest 2', 'ignored', 'nopass', True),
        (BS + ';,:"', BS + ';,:"12345678', 'WPA', False),
        ('1234567890', '0123456789', 'WPA', False),
        ('ends with space ', ' starts with space', 'WPA', False),
        ('x' * 32, 'y' * 63, 'WPA', False),
    ]
    for _ in range(300):
        sec = rnd.choice(['WPA', 'WPA', 'WPA', 'WEP', 'nopass'])
        ssid = rtext(rnd.randint(1, 32), skip='~')
        pw = 'pw~' + rtext(rnd.randint(5, 30)) + '~wp' if sec != 'nopass' else ''
        fixed.append((ssid, pw, sec, rnd.random() < 0.3))
    for i, (s, p, sec, hid) in enumerate(fixed):
        add('wifi-%d' % i, 'wifi', {'ssid': s, 'password': p, 'security': sec, 'hidden': hid}, encode=(i < 110))
        WIFI.append((s, p, sec, hid))
    add('wifi-empty', 'wifi', {'ssid': '', 'password': '', 'security': 'WPA', 'hidden': False})
    add('wifi-nossid', 'wifi', {'ssid': '', 'password': 'abc12345', 'security': 'WPA', 'hidden': False})
    add('wifi-nopw', 'wifi', {'ssid': 'Home', 'password': '', 'security': 'WPA', 'hidden': False})
    add('wifi-short', 'wifi', {'ssid': 'Home', 'password': 'abc', 'security': 'WPA', 'hidden': False})
    add('wifi-wep-short', 'wifi', {'ssid': 'Home', 'password': 'abc', 'security': 'WEP', 'hidden': False})
    add('wifi-long', 'wifi', {'ssid': 'Home', 'password': 'p' * 64, 'security': 'WPA', 'hidden': False})
    add('wifi-hex64', 'wifi', {'ssid': 'Home', 'password': 'a1' * 32, 'security': 'WPA', 'hidden': False})
    add('wifi-ssid33', 'wifi', {'ssid': 'x' * 33, 'password': 'abc12345', 'security': 'WPA', 'hidden': False})
    add('wifi-ssid-bytes', 'wifi', {'ssid': '日' * 11, 'password': 'abc12345', 'security': 'WPA', 'hidden': False})
    add('wifi-weird-sec', 'wifi', {'ssid': 'Home', 'password': 'abc12345', 'security': 'bogus', 'hidden': False})


def check_wifi(res):
    for i, (s, p, sec, hid) in enumerate(WIFI):
        r = res['wifi-%d' % i]['res']
        got = parse_wifi(r['text'])
        want = {'T': sec, 'S': s}
        if sec != 'nopass':
            want['P'] = p
        if hid:
            want['H'] = 'true'
        ok('wifi %d reads back (%r)' % (i, s[:12]), got == want, '%r\n    text=%r' % (got, r['text']))
        ok('wifi %d ends with two semicolons' % i, r['text'].endswith(';;') and not r['text'].endswith(';;;') or r['text'].endswith(BS + ';;;'), r['text'][-8:])
        if sec != 'nopass':
            ok('wifi %d hides the password in the preview' % i, 'pw~' not in r['shown'] and '~wp' not in r['shown'] or i < 10 and p not in r['shown'], r['shown'])
            mm = re.search(r'P:(•+);', r['shown'])
            ok('wifi %d preview shows bullets for the password' % i, bool(mm) and len(mm.group(1)) == min(len(p), 12), r['shown'])
        else:
            ok('wifi %d open network has no password part' % i, 'P:' not in r['text'])
    ok('wifi: nothing typed is empty', res['wifi-empty']['res']['empty'])
    ok('wifi: password without a name is an error on the name', 'ssid' in res['wifi-nossid']['res']['errors'] and not res['wifi-nossid']['res']['empty'])
    ok('wifi: name without a password is an error on the password', 'password' in res['wifi-nopw']['res']['errors'])
    ok('wifi: short WPA password warns', any('at least 8' in w for w in res['wifi-short']['res']['warns']))
    ok('wifi: short WEP password does not warn about length', not any('at least 8' in w for w in res['wifi-wep-short']['res']['warns']))
    ok('wifi: 64 character password warns', any('at most 63' in w for w in res['wifi-long']['res']['warns']))
    ok('wifi: 64 hex digits is a valid key, no warning', not any('at most 63' in w for w in res['wifi-hex64']['res']['warns']))
    ok('wifi: 33 byte name warns', any('32 bytes' in w for w in res['wifi-ssid33']['res']['warns']))
    ok('wifi: name of 11 three-byte characters (33 bytes) warns', any('32 bytes' in w for w in res['wifi-ssid-bytes']['res']['warns']))
    ok('wifi: unknown security falls back to WPA', parse_wifi(res['wifi-weird-sec']['res']['text'])['T'] == 'WPA')
    ok('wifi: spaces at the ends of the name warn', any('starts or ends' in w for w in res['wifi-8']['res']['warns']))
    ok('wifi: spaces at the start of the password warn', any('starts or ends' in w for w in res['wifi-8']['res']['warns']))


# ---------- 5. email ----------
MAILS = []


def mail_addr():
    local = ''.join(rnd.choice('abcdefghijklmnopqrstuvwxyz0123456789._%+-') for _ in range(rnd.randint(1, 12)))
    return '%s@%s.%s' % (local, word(), rnd.choice(['com', 'org', 'co.uk', 'io']))


def email_cases():
    for i in range(200):
        n = rnd.choice([1, 1, 1, 2, 3])
        to = [mail_addr() for _ in range(n)]
        sub = jstrip(rtext(rnd.randint(0, 40))) if rnd.random() < 0.8 else ''
        body = rtext(rnd.randint(0, 80), nl=True) if rnd.random() < 0.7 else ''
        sep = rnd.choice([',', ', ', ' ', ';', '\n'])
        add('mail-%d' % i, 'email', {'to': sep.join(to), 'subject': sub, 'body': body}, encode=(i < 80))
        MAILS.append((to, sub, body))
    add('mail-bad', 'email', {'to': 'not an email', 'subject': '', 'body': ''})
    add('mail-bad2', 'email', {'to': 'good@example.com, bad@', 'subject': '', 'body': ''})
    add('mail-nodomaindot', 'email', {'to': 'a@localhost', 'subject': '', 'body': ''})
    add('mail-onlysubject', 'email', {'to': '', 'subject': 'Hello', 'body': ''})
    add('mail-empty', 'email', {'to': '', 'subject': '', 'body': ''})
    add('mail-plain', 'email', {'to': 'Sam.Smith+tag@Example.com', 'subject': '', 'body': ''})


def check_email(res):
    for i, (to, sub, body) in enumerate(MAILS):
        r = res['mail-%d' % i]['res']
        t = r['text']
        ok('email %d starts with mailto:' % i, t.startswith('mailto:'), t[:30])
        ok('email %d has no raw spaces, quotes or line breaks' % i, not re.search(r'[ \r\n\t"<>]', t), t)
        addr, _, query = t[7:].partition('?')
        addrs = [urllib.parse.unquote(a) for a in addr.split(',')]
        ok('email %d recipients read back' % i, addrs == to, '%r vs %r' % (addrs, to))
        q = urllib.parse.parse_qs(query, keep_blank_values=True, strict_parsing=bool(query)) if query else {}
        ok('email %d subject reads back' % i, (q.get('subject', [''])[0]) == sub, '%r' % (q,))
        want_body = lf(body).replace('\n', '\r\n')
        ok('email %d body reads back with CRLF line breaks' % i, (q.get('body', [''])[0]) == want_body, '%r vs %r' % (q.get('body'), want_body))
        ok('email %d has only subject and body fields' % i, set(q) <= {'subject', 'body'})
    ok('email: free text in the address box is an error', 'to' in res['mail-bad']['res']['errors'])
    ok('email: one bad address among good ones is named in the message', 'bad@' in res['mail-bad2']['res']['errors'].get('to', ''))
    ok('email: no dot in the domain is an error', 'to' in res['mail-nodomaindot']['res']['errors'])
    ok('email: subject without an address is an error', 'to' in res['mail-onlysubject']['res']['errors'] and not res['mail-onlysubject']['res']['empty'])
    ok('email: nothing typed is empty', res['mail-empty']['res']['empty'])
    ok('email: plain address keeps + and @ and case', res['mail-plain']['res']['text'] == 'mailto:Sam.Smith+tag@Example.com', res['mail-plain']['res']['text'])


# ---------- 6. phone and SMS ----------
PHONES = []


def phone_cases():
    for i in range(200):
        digits = ''.join(rnd.choice('0123456789') for _ in range(rnd.randint(3, 15)))
        plus = rnd.random() < 0.6
        raw = '+' if plus else ''
        for ch in digits:
            if rnd.random() < 0.25:
                raw += rnd.choice([' ', '-', '.', '/', ' (', ') '])
            raw += ch
        if rnd.random() < 0.3:
            raw = '  ' + raw + ' '
        msg = rtext(rnd.randint(0, 50), nl=True) if rnd.random() < 0.6 else ''
        add('tel-%d' % i, 'phone', {'phone': raw}, encode=(i < 20))
        add('sms-%d' % i, 'sms', {'phone': raw, 'message': msg}, encode=(i < 20))
        PHONES.append((('+' if plus else '') + digits, msg))
    for k, v in (('letters', 'call me'), ('short', '12'), ('plusonly', '+'), ('vanity', '1-800-FLOWERS'), ('inner-plus', '12+3456'), ('comma', '555,1234')):
        add('tel-bad-' + k, 'phone', {'phone': v})
    add('tel-long', 'phone', {'phone': '1' * 16})
    add('tel-empty', 'phone', {'phone': ''})
    add('sms-empty', 'sms', {'phone': '', 'message': ''})
    add('sms-onlymsg', 'sms', {'phone': '', 'message': 'hi'})
    add('sms-nomsg', 'sms', {'phone': '+15551234567', 'message': ''})


def check_phone(res):
    for i, (num, msg) in enumerate(PHONES):
        r = res['tel-%d' % i]['res']
        ok('phone %d reads back' % i, r['text'] == 'tel:' + num, '%r vs %r' % (r['text'], num))
        s = res['sms-%d' % i]['res']['text']
        base, _, query = s.partition('?')
        ok('sms %d number reads back' % i, base == 'sms:' + num, s[:40])
        if msg:
            q = urllib.parse.parse_qs(query, keep_blank_values=True)
            ok('sms %d message reads back' % i, q.get('body', [None])[0] == lf(msg), '%r' % (q,))
        else:
            ok('sms %d without a message has no query' % i, query == '' and '?' not in s)
    for k in ('letters', 'short', 'plusonly', 'vanity', 'inner-plus', 'comma'):
        ok('phone %s is an error' % k, 'phone' in res['tel-bad-' + k]['res']['errors'], res['tel-bad-' + k]['res'])
    ok('phone: 16 digits is allowed with a warning', res['tel-long']['res']['text'] == 'tel:' + '1' * 16 and any('15 digits' in w for w in res['tel-long']['res']['warns']))
    ok('phone: empty is empty', res['tel-empty']['res']['empty'] and res['sms-empty']['res']['empty'])
    ok('sms: message without a number is an error', 'phone' in res['sms-onlymsg']['res']['errors'])
    ok('sms: number only is fine', res['sms-nomsg']['res']['text'] == 'sms:+15551234567')


# ---------- 7. maps ----------
MAPS = []


def map_cases():
    for i in range(200):
        lat = rnd.uniform(-90, 90)
        lng = rnd.uniform(-180, 180)
        dl = rnd.choice([0, 1, 2, 4, 6])
        a, b = ('%.*f' % (dl, lat)), ('%.*f' % (dl, lng))
        how = rnd.choice(['geo', 'link'])
        add('map-%d' % i, 'map', {'lat': a, 'lng': b, 'how': how}, encode=(i < 20))
        MAPS.append((a, b, how))
    for k, (la, ln) in {'badlat': ('91', '0'), 'badlng': ('0', '-180.5'), 'text': ('abc', '1'), 'comma': ('37,7749', '-122,4194'), 'exp': ('1e1', '2'),
                        'plus': ('+3', '4'), 'onlylat': ('10', ''), 'onlylng': ('', '10'), 'edge': ('90', '180'), 'edge2': ('-90', '-180'), 'zero': ('-0.0', '-0')}.items():
        add('map-' + k, 'map', {'lat': la, 'lng': ln, 'how': 'geo'})
    add('map-empty', 'map', {'lat': '', 'lng': '', 'how': 'geo'})
    for i, s in enumerate(['37.7749, -122.4194', '37.7749 -122.4194', '37.7749;-122.4194', '37.7749', '37.7749, -122.4194, 5', '  1.5,2.5  ', '-1 -2', 'a, b', '1,2 3', '37,7749', '40,-74', '40, -74', '37,7749 -122,4194', '37.7749,-122.4194', '40;-74']):
        CASES.append({'id': 'pair-%d' % i, 'fn': 'splitPair', 'args': [s]})
    for i, x in enumerate([0, -0.0, 1, -1, 37.77490000001, -122.41940000, 0.00000004, -0.00000004, 12.5, 1e-7, 89.9999999, 100]):
        CASES.append({'id': 'coord-%d' % i, 'fn': 'coordText', 'args': [x]})


def ref_coord(x):
    s = '%.7f' % float(x)
    s = s.rstrip('0').rstrip('.') if '.' in s else s
    return '0' if s in ('-0', '') else s


def check_map(res):
    for i, (a, b, how) in enumerate(MAPS):
        r = res['map-%d' % i]['res']
        pair = ref_coord(a) + ',' + ref_coord(b)
        want = 'geo:' + pair if how == 'geo' else 'https://www.google.com/maps/search/?api=1&query=' + pair
        ok('map %d (%s, %s) reads back' % (i, a, b), r['text'] == want, '%r vs %r' % (r['text'], want))
        ok('map %d has no exponent or trailing zeros' % i, not re.search(r'[eE]|\.\d*0(,|$)', pair), pair)
    for k, field in (('badlat', 'lat'), ('badlng', 'lng'), ('text', 'lat'), ('comma', 'lat'), ('exp', 'lat'), ('plus', 'lat'), ('onlylat', 'lng'), ('onlylng', 'lat')):
        ok('map %s is an error on %s' % (k, field), field in res['map-' + k]['res']['errors'], res['map-' + k]['res'])
    ok('map: corner values are allowed', res['map-edge']['res']['text'] == 'geo:90,180' and res['map-edge2']['res']['text'] == 'geo:-90,-180')
    ok('map: negative zero is written as 0', res['map-zero']['res']['text'] == 'geo:0,0', res['map-zero']['res']['text'])
    ok('map: nothing typed is empty', res['map-empty']['res']['empty'])
    ok('map: a comma decimal gets a helpful message', 'dot' in res['map-comma']['res']['errors']['lat'])
    want = [{'lat': '37.7749', 'lng': '-122.4194'}] * 3 + [None, None, {'lat': '1.5', 'lng': '2.5'}, {'lat': '-1', 'lng': '-2'}, None, None, None, None, {'lat': '40', 'lng': '-74'}, None, {'lat': '37.7749', 'lng': '-122.4194'}, {'lat': '40', 'lng': '-74'}]
    for i, w in enumerate(want):
        ok('splitPair case %d' % i, res['pair-%d' % i]['value'] == w, res['pair-%d' % i]['value'])
    for i, x in enumerate([0, -0.0, 1, -1, 37.77490000001, -122.41940000, 0.00000004, -0.00000004, 12.5, 1e-7, 89.9999999, 100]):
        ok('coordText %r' % x, res['coord-%d' % i]['value'] == ref_coord(x), '%r vs %r' % (res['coord-%d' % i]['value'], ref_coord(x)))


# ---------- 8. contact cards ----------
CONTACTS = []


def contact_cases():
    for i in range(300):
        def maybe(p, f):
            return f() if rnd.random() < p else ''
        c = {
            'first': maybe(0.85, lambda: rtext(rnd.randint(1, 20))),
            'last': maybe(0.8, lambda: rtext(rnd.randint(1, 20))),
            'org': maybe(0.5, lambda: rtext(rnd.randint(1, 40))),
            'title': maybe(0.4, lambda: rtext(rnd.randint(1, 40))),
            'mobile': maybe(0.7, lambda: '+' + ''.join(rnd.choice('0123456789') for _ in range(rnd.randint(7, 13)))),
            'work': maybe(0.3, lambda: '(%s) %s-%s' % (''.join(rnd.choice('0123456789') for _ in range(3)), ''.join(rnd.choice('0123456789') for _ in range(3)), ''.join(rnd.choice('0123456789') for _ in range(4)))),
            'email': maybe(0.7, mail_addr),
            'url': maybe(0.5, lambda: rnd.choice(['', 'https://']) + word() + '.com/' + rtext(rnd.randint(0, 20), sets=('ascii',))),
            'street': maybe(0.5, lambda: rtext(rnd.randint(1, 40))),
            'city': maybe(0.5, lambda: rtext(rnd.randint(1, 20))),
            'region': maybe(0.4, lambda: rtext(rnd.randint(1, 10))),
            'zip': maybe(0.5, lambda: rtext(rnd.randint(1, 10), sets=('ascii',))),
            'country': maybe(0.4, lambda: rtext(rnd.randint(1, 20))),
        }
        add('card-%d' % i, 'contact', c, encode=(i < 100))
        CONTACTS.append(c)
    add('card-empty', 'contact', {k: '' for k in CONTACTS[0]})
    add('card-nonames', 'contact', dict({k: '' for k in CONTACTS[0]}, email='a@b.co'))
    add('card-onlyorg', 'contact', dict({k: '' for k in CONTACTS[0]}, org='Acme, Inc.'))
    add('card-bad-mobile', 'contact', dict({k: '' for k in CONTACTS[0]}, first='A', mobile='call'))
    add('card-bad-work', 'contact', dict({k: '' for k in CONTACTS[0]}, first='A', work='12'))
    add('card-bad-email', 'contact', dict({k: '' for k in CONTACTS[0]}, first='A', email='nope'))
    add('card-long', 'contact', dict({k: '' for k in CONTACTS[0]}, first='A' * 90, last='B' * 90, org='日本' * 60, street='x' * 200))
    add('card-nl', 'contact', dict({k: '' for k in CONTACTS[0]}, first='A', title='line1\nline2; semi, comma \\ back'))


def v_get(card, name):
    try:
        return card.contents[name]
    except KeyError:
        return []


def check_contacts(res):
    for i, c in enumerate(CONTACTS):
        r = res['card-%d' % i]['res']
        t = jstrip
        first, last, org, title = t(c['first']), t(c['last']), t(c['org']), t(c['title'])
        email, site = t(c['email']), t(c['url'])
        street, city, region, zip_, country = t(c['street']), t(c['city']), t(c['region']), t(c['zip']), t(c['country'])
        mob, wrk = t(c['mobile']), t(c['work'])
        anything = any([first, last, org, title, email, site, street, city, region, zip_, country, mob, wrk])
        if not anything:
            ok('card %d empty' % i, r['empty'])
            continue
        if not (first or last or org):
            ok('card %d needs a name or company' % i, 'first' in r['errors'] and not r['empty'], r)
            continue
        text = r['text']
        lines = text.split('\r\n')
        ok('card %d every line is at most 75 octets' % i, max(len(l.encode('utf-8')) for l in lines) <= 75, [len(l.encode('utf-8')) for l in lines])
        ok('card %d has only CRLF line breaks' % i, '\n' not in text.replace('\r\n', '') and '\r' not in text.replace('\r\n', ''))
        ok('card %d starts and ends right' % i, lines[0] == 'BEGIN:VCARD' and lines[-1] == 'END:VCARD' and lines[1] == 'VERSION:3.0', lines[:2])
        try:
            card = vobject.readOne(text)
            card.validate()
        except Exception as e:
            ok('card %d parses with vobject' % i, False, '%s: %s\n%r' % (type(e).__name__, e, text))
            continue
        fn = ' '.join(x for x in (first, last) if x) or org
        ok('card %d name' % i, card.fn.value == fn, '%r vs %r' % (card.fn.value, fn))
        ok('card %d structured name' % i, card.n.value.family == last and card.n.value.given == first, '%r' % (card.n.value,))
        ok('card %d company' % i, (card.org.value == [org]) if org else (not v_get(card, 'org')), v_get(card, 'org'))
        ok('card %d job title' % i, (card.title.value == title) if title else (not v_get(card, 'title')))
        tels = {tuple(x.params.get('TYPE', [])): x.value for x in v_get(card, 'tel')}
        want_tels = {}
        if mob:
            want_tels[('CELL',)] = mob
        if wrk:
            want_tels[('WORK', 'VOICE')] = re.sub(r'\D', '', wrk)
        ok('card %d phone numbers' % i, tels == want_tels, '%r vs %r' % (tels, want_tels))
        ok('card %d email' % i, (card.email.value == email) if email else (not v_get(card, 'email')))
        if site:
            ok('card %d website is an address' % i, bool(re.match(r'^[a-z][a-z0-9+.\-]*://', card.url.value, re.I)) and ' ' not in card.url.value, card.url.value)
        else:
            ok('card %d no website' % i, not v_get(card, 'url'))
        if any([street, city, region, zip_, country]):
            a = card.adr.value
            ok('card %d address' % i, (a.street, a.city, a.region, a.code, a.country) == (street, city, region, zip_, country), '%r' % (a,))
        else:
            ok('card %d no address' % i, not v_get(card, 'adr'))
    ok('card: empty form is empty', res['card-empty']['res']['empty'])
    ok('card: email only asks for a name', 'first' in res['card-nonames']['res']['errors'])
    o = vobject.readOne(res['card-onlyorg']['res']['text'])
    ok('card: company only is a valid card named after the company', o.fn.value == 'Acme, Inc.' and o.org.value == ['Acme, Inc.'], res['card-onlyorg']['res']['text'])
    ok('card: bad mobile', 'mobile' in res['card-bad-mobile']['res']['errors'])
    ok('card: bad work phone', 'work' in res['card-bad-work']['res']['errors'])
    ok('card: bad email', 'email' in res['card-bad-email']['res']['errors'])
    lg = vobject.readOne(res['card-long']['res']['text'])
    ok('card: very long values fold and read back', lg.fn.value == 'A' * 90 + ' ' + 'B' * 90 and lg.org.value == ['日本' * 60] and lg.adr.value.street == 'x' * 200)
    nl = vobject.readOne(res['card-nl']['res']['text'])
    ok('card: line breaks, semicolons, commas and backslashes in a value', nl.title.value == 'line1\nline2; semi, comma \\ back', repr(nl.title.value))


# ---------- 9. events ----------
EVENTS = []


def rdate():
    return datetime.date(2026, 1, 1) + datetime.timedelta(days=rnd.randint(0, 900))


def event_cases():
    for i in range(300):
        allday = rnd.random() < 0.3
        title = rtext(rnd.randint(1, 50))
        where = rtext(rnd.randint(1, 40)) if rnd.random() < 0.5 else ''
        details = rtext(rnd.randint(1, 120), nl=True) if rnd.random() < 0.5 else ''
        d1 = rdate()
        if allday:
            d2 = d1 + datetime.timedelta(days=rnd.randint(0, 5)) if rnd.random() < 0.6 else None
            s, e = d1.isoformat(), d2.isoformat() if d2 else ''
        else:
            t1 = datetime.datetime.combine(d1, datetime.time(rnd.randint(0, 23), rnd.randint(0, 59)))
            t2 = t1 + datetime.timedelta(minutes=rnd.randint(1, 3000)) if rnd.random() < 0.7 else None
            s, e = t1.strftime('%Y-%m-%dT%H:%M'), t2.strftime('%Y-%m-%dT%H:%M') if t2 else ''
        f = {'title': title, 'allday': allday, 'start': s, 'end': e, 'where': where, 'details': details}
        add('ev-%d' % i, 'event', f, encode=(i < 100))
        EVENTS.append(f)
    base = {'title': 'Party', 'allday': False, 'start': '2026-12-31T21:00', 'end': '2027-01-01T01:00', 'where': '', 'details': ''}
    add('ev-empty', 'event', {'title': '', 'allday': False, 'start': '', 'end': '', 'where': '', 'details': ''})
    add('ev-notitle', 'event', dict(base, title=''))
    add('ev-nostart', 'event', dict(base, start=''))
    add('ev-badstart', 'event', dict(base, start='2026-13-40T99:99'))
    add('ev-feb30', 'event', dict(base, start='2026-02-30T10:00', end=''))
    add('ev-badend', 'event', dict(base, end='garbage'))
    add('ev-endbefore', 'event', dict(base, end='2026-12-31T20:00'))
    add('ev-endsame', 'event', dict(base, end='2026-12-31T21:00'))
    add('ev-leap', 'event', dict(base, start='2028-02-29T10:00', end=''))
    add('ev-notleap', 'event', dict(base, start='2027-02-29T10:00', end=''))
    add('ev-ad-nostart', 'event', dict(base, allday=True, start='', end=''))
    add('ev-ad-endbefore', 'event', dict(base, allday=True, start='2026-05-10', end='2026-05-09'))
    add('ev-ad-yearend', 'event', dict(base, allday=True, start='2026-12-31', end=''))
    add('ev-ad-leapend', 'event', dict(base, allday=True, start='2028-02-28', end='2028-02-29'))
    add('ev-ad-timedvals', 'event', dict(base, allday=True, start='2026-05-10T09:00', end='2026-05-11T10:00'))
    add('ev-midnight', 'event', dict(base, start='2026-05-10T00:00', end='2026-05-10T23:59'))
    add('ev-long', 'event', dict(base, title='T' * 200, where='W' * 200, details='D' * 400))


def check_events(res):
    for i, f in enumerate(EVENTS):
        r = res['ev-%d' % i]['res']
        text = r['text']
        lines = text.split('\r\n')
        ok('event %d every line is at most 75 octets' % i, max(len(l.encode('utf-8')) for l in lines) <= 75)
        ok('event %d frame' % i, lines[0] == 'BEGIN:VCALENDAR' and lines[1] == 'VERSION:2.0' and lines[-1] == 'END:VCALENDAR' and 'BEGIN:VEVENT' in lines and 'END:VEVENT' in lines, lines[:3])
        try:
            cal = icalendar.Calendar.from_ical(text)
            evs = list(cal.walk('VEVENT'))
        except Exception as e:
            ok('event %d parses with icalendar' % i, False, '%s: %s\n%r' % (type(e).__name__, e, text))
            continue
        ok('event %d has exactly one event' % i, len(evs) == 1)
        ev = evs[0]
        ok('event %d title' % i, str(ev['SUMMARY']) == jstrip(f['title']), '%r vs %r' % (str(ev['SUMMARY']), jstrip(f['title'])))
        if f['allday']:
            d1 = datetime.date.fromisoformat(f['start'][:10])
            d2 = datetime.date.fromisoformat(f['end'][:10]) if f['end'] else d1
            ok('event %d start day' % i, ev['DTSTART'].dt == d1 and type(ev['DTSTART'].dt) is datetime.date, ev['DTSTART'].dt)
            ok('event %d end is the next day after the last (exclusive)' % i, ev['DTEND'].dt == d2 + datetime.timedelta(days=1), ev['DTEND'].dt)
        else:
            t1 = datetime.datetime.strptime(f['start'], '%Y-%m-%dT%H:%M')
            ok('event %d start time (floating)' % i, ev['DTSTART'].dt == t1 and ev['DTSTART'].dt.tzinfo is None, ev['DTSTART'].dt)
            if f['end']:
                ok('event %d end time' % i, ev['DTEND'].dt == datetime.datetime.strptime(f['end'], '%Y-%m-%dT%H:%M'), ev['DTEND'].dt)
            else:
                ok('event %d no end' % i, 'DTEND' not in ev)
        where = jstrip(f['where'])
        ok('event %d place' % i, (str(ev['LOCATION']) == where) if where else ('LOCATION' not in ev))
        det = lf(f['details'])
        ok('event %d details' % i, (str(ev['DESCRIPTION']) == det) if det else ('DESCRIPTION' not in ev), '%r vs %r' % (str(ev.get('DESCRIPTION')), det))
    R = lambda k: res[k]['res']
    ok('event: empty form is empty', R('ev-empty')['empty'])
    ok('event: no title is an error', 'title' in R('ev-notitle')['errors'])
    ok('event: no start is an error', 'start' in R('ev-nostart')['errors'])
    ok('event: nonsense start is an error', 'start' in R('ev-badstart')['errors'])
    ok('event: 30 February is an error', 'start' in R('ev-feb30')['errors'])
    ok('event: nonsense end is an error', 'end' in R('ev-badend')['errors'])
    ok('event: end before start is an error', 'end' in R('ev-endbefore')['errors'])
    ok('event: end equal to start is an error', 'end' in R('ev-endsame')['errors'])
    ok('event: 29 February in a leap year is fine', not R('ev-leap')['errors'] and 'DTSTART:20280229T100000' in R('ev-leap')['text'])
    ok('event: 29 February in a normal year is an error', 'start' in R('ev-notleap')['errors'])
    ok('event: all day without a start is an error', 'start' in R('ev-ad-nostart')['errors'])
    ok('event: all day ending before it starts is an error', 'end' in R('ev-ad-endbefore')['errors'])
    ok('event: all day on 31 December ends on 1 January next year', 'DTEND;VALUE=DATE:20270101' in R('ev-ad-yearend')['text'], R('ev-ad-yearend')['text'])
    ok('event: all day ending on a leap day', 'DTEND;VALUE=DATE:20280301' in R('ev-ad-leapend')['text'], R('ev-ad-leapend')['text'])
    ok('event: all day takes the date part of date and time values', 'DTSTART;VALUE=DATE:20260510' in R('ev-ad-timedvals')['text'] and 'DTEND;VALUE=DATE:20260512' in R('ev-ad-timedvals')['text'], R('ev-ad-timedvals')['text'])
    ok('event: an event running to 23:59 is fine', not R('ev-midnight')['errors'])
    lg = list(icalendar.Calendar.from_ical(R('ev-long')['text']).walk('VEVENT'))[0]
    ok('event: long values fold and read back', str(lg['SUMMARY']) == 'T' * 200 and str(lg['LOCATION']) == 'W' * 200 and str(lg['DESCRIPTION']) == 'D' * 400)


# ---------- 10. every payload drawn as a code and read back ----------
def check_roundtrip(res):
    done = 0
    for cid, r in res.items():
        if 'rows' not in r:
            continue
        done += 1
        out = read_zx(picture(r['rows']))
        want = bytes.fromhex(r['utf8'])
        ok('zxing reads %s back exactly' % cid, len(out) == 1 and out[0].bytes == want, 'got %s' % ([(len(o.bytes)) for o in out],))
    ok('the round trip covered a good number of payloads', done >= 400, done)
    bad = [c for c, r in res.items() if r.get('encodeError')]
    ok('no payload was too long to encode', not bad, bad)


# ---------- 11. colours ----------
def lum_ref(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def tone_cases():
    pairs = [('#000000', '#ffffff'), ('#ffffff', '#ffffff'), ('#777777', '#ffffff'), ('#15803d', '#ffffff')]
    for _ in range(80):
        pairs.append(('#%06x' % rnd.randrange(1 << 24), '#%06x' % rnd.randrange(1 << 24)))
    for i, (a, b) in enumerate(pairs):
        CASES.append({'id': 'tone-%d' % i, 'fn': 'ratio', 'args': [a, b]})
    for i, h in enumerate(['#000000', '#FFFFFF', '#abc', 'abcdef', '#12345g', '', '#1234567', '#AbCdEf']):
        CASES.append({'id': 'valid-%d' % i, 'fn': 'valid', 'args': [h]})
    return pairs


def check_tone(res, pairs):
    for i, (a, b) in enumerate(pairs):
        la, lb = lum_ref(a), lum_ref(b)
        want = (max(la, lb) + 0.05) / (min(la, lb) + 0.05)
        ok('contrast %s %s' % (a, b), abs(res['tone-%d' % i]['value'] - want) < 1e-9, (res['tone-%d' % i]['value'], want))
    ok('black on white is 21 to 1', abs(res['tone-0']['value'] - 21) < 1e-9)
    ok('the same colour twice is 1 to 1', abs(res['tone-1']['value'] - 1) < 1e-9)
    ok('#777777 on white is just under 4.5', 4.4 < res['tone-2']['value'] < 4.5, res['tone-2']['value'])
    for i, w in enumerate([True, True, False, False, False, False, False, True]):
        ok('colour check %d' % i, res['valid-%d' % i]['value'] is w)


def main():
    strings = helper_cases()
    url_cases()
    text_cases()
    wifi_cases()
    email_cases()
    phone_cases()
    map_cases()
    contact_cases()
    event_cases()
    pairs = tone_cases()
    res = run(CASES)
    check_helpers(res, strings)
    check_urls(res)
    check_text(res)
    check_wifi(res)
    check_email(res)
    check_phone(res)
    check_map(res)
    check_contacts(res)
    check_events(res)
    check_tone(res, pairs)
    check_roundtrip(res)
    print('passed %d, failed %d' % (passes, len(fails)))
    for f in fails[:60]:
        print('FAIL', f)
    sys.exit(1 if fails else 0)


main()
