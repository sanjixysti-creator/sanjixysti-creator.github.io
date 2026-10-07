#!/usr/bin/env python3
"""Proof for the QR encoder inside the page: every size, level and mask is compared with segno (an independent
implementation), then the pictures are decoded with zxing-cpp and OpenCV.

usage: python3 qr_proof.py [matrix|decode|all]
The encoder code is read from the fragment (the PURE region), or from QR_SRC if that variable names a file.
"""
import hashlib, json, os, random, re, subprocess, sys, tempfile
import cv2, numpy as np, zxingcpp
import segno
from segno import consts

D = os.path.dirname(os.path.abspath(__file__))
SRC = os.environ.get('QR_SRC', '')

# segno quirk: when the bit stream is already a whole number of bytes after the terminator it still adds one extra
# all-zero byte (write_padding_bits pads 8 bits instead of 0). ISO/IEC 18004 section 7.4.10 and ZXing add nothing there,
# so this proof runs segno with that one function corrected. Every other step is segno's own code.
from segno import encoder as _segno_encoder


def _write_padding_bits(buff, version, length):
    if version not in (consts.VERSION_M1, consts.VERSION_M3) and length % 8:
        buff.extend([0] * (8 - (length % 8)))


_segno_encoder.write_padding_bits = _write_padding_bits
MODE = sys.argv[1] if len(sys.argv) > 1 else 'all'
LVL = 'LMQH'
ERR_CONST = {'L': consts.ERROR_LEVEL_L, 'M': consts.ERROR_LEVEL_M, 'Q': consts.ERROR_LEVEL_Q, 'H': consts.ERROR_LEVEL_H}

fails, passes = [], 0


def ok(name, cond, detail=''):
    global passes
    if cond:
        passes += 1
    else:
        fails.append(name + ('\n    ' + detail if detail else ''))


def encoder_file():
    if SRC:
        return SRC
    frag = open(D + '/qr-forever.html', encoding='utf-8').read()
    m = re.search(r'PURE-BEGIN[^\n]*\n(.*?)/\* PURE-END', frag, re.S)
    path = tempfile.mkstemp(suffix='.js', prefix='qr_pure_')[1]
    open(path, 'w', encoding='utf-8').write(m.group(1))
    return path


ENC = encoder_file()


def run_node(cases, full=False):
    d = tempfile.mkdtemp()
    cf, of = d + '/cases.json', d + '/out.json'
    json.dump(cases, open(cf, 'w'))
    subprocess.run(['node', D + '/proof_core.js', ENC, cf, of] + (['full'] if full else []), check=True)
    return {r['id']: r for r in json.load(open(of))}


def sha(matrix):
    h = hashlib.sha1()
    for row in matrix:
        h.update(bytes(row))
    return h.hexdigest()


def bits_for(mode, n):
    if mode == 'numeric':
        return 10 * (n // 3) + (0, 4, 7)[n % 3]
    if mode == 'alnum':
        return 11 * (n // 2) + 6 * (n % 2)
    return 8 * n


COUNT = {'numeric': (10, 12, 14), 'alnum': (9, 11, 13), 'byte': (8, 16, 16)}
ALNUM = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:'


def cap_bits(ver, lvl):
    return consts.SYMBOL_CAPACITY[ver][ERR_CONST[lvl]]


def max_count(mode, ver, lvl):
    """Most characters (or bytes) of one mode a version holds, worked out from segno's capacity table."""
    cb = COUNT[mode][0 if ver <= 9 else 1 if ver <= 26 else 2]
    n = 0
    while 4 + cb + bits_for(mode, n + 1) <= cap_bits(ver, lvl) and n + 1 < (1 << cb):
        n += 1
    return n


def segno_make(c, rnd=None):
    kw = dict(error=c['level'], version=c.get('version') or None, mask=c.get('mask'), boost_error=False, micro=False)
    if c['kind'] == 'bytes':
        return segno.make(bytes.fromhex(c['data']), mode='byte', **kw)
    if c['kind'] == 'numeric':
        return segno.make(c['data'], mode='numeric', **kw)
    if c['kind'] == 'alnum':
        return segno.make(c['data'], mode='alphanumeric', **kw)
    if any(ord(ch) > 127 for ch in c['data']) and not all(ord(ch) < 256 for ch in c['data']):
        # no kanji mode in the page: text outside Latin-1 is written as UTF-8 bytes
        return segno.make(c['data'], mode='byte', encoding='utf-8', **kw)
    return segno.make(c['data'], encoding='utf-8', **kw)


def compare(cases, label, require_same_choice=True):
    res = run_node(cases)
    bad = 0
    for c in cases:
        r = res[c['id']]
        try:
            q = segno_make(c)
        except Exception as e:
            ok('%s %s: segno refused (%s) but the page said %r' % (label, c['id'], type(e).__name__, r), 'error' in r)
            continue
        if 'error' in r:
            ok('%s %s: page refused (%s) but segno encoded it' % (label, c['id'], r['error']), False)
            bad += 1
            continue
        same = (r['version'] == q.version and r['mask'] == q.mask and sha(q.matrix) == r['sha1'])
        if not same and bad < 12:
            bad += 1
        ok('%s %s: matrix equals segno (page v%s m%s, segno v%s m%s)' % (label, c['id'], r['version'], r['mask'], q.version, q.mask), same)
    return res


def matrix_tests():
    rnd = random.Random(20261007)
    # 0. the tables, against segno's own
    tables = subprocess.run(['node', '-e', "const QR=new Function(require('fs').readFileSync(%r,'utf8')+'\\nreturn QR;')();console.log(JSON.stringify(QR.tables))" % ENC], capture_output=True, text=True, check=True).stdout
    t = json.loads(tables)
    for li, lv in enumerate(LVL):
        for v in range(1, 41):
            ec = consts.ECC[v][ERR_CONST[lv]]
            nb = sum(e.num_blocks for e in ec)
            ecc = ec[0].num_total - ec[0].num_data
            ok('table blocks %s v%d' % (lv, v), t['blocks'][li][v] == nb, 'got %s want %s' % (t['blocks'][li][v], nb))
            ok('table ecc per block %s v%d' % (lv, v), t['ecc'][li][v] == ecc, 'got %s want %s' % (t['ecc'][li][v], ecc))

    # 1. every version x level x mask, byte mode, data filling the code
    cases = []
    for v in range(1, 41):
        for lv in LVL:
            n = max_count('byte', v, lv)
            data = bytes(rnd.randrange(256) for _ in range(n)).hex()
            for m in range(8):
                cases.append({'id': 'full-%s%d-m%d' % (lv, v, m), 'kind': 'bytes', 'data': data, 'level': lv, 'version': v, 'mask': m})
    compare(cases, 'full byte')

    # 2. numeric and alphanumeric filling every version and level
    cases = []
    for v in range(1, 41):
        for lv in LVL:
            n = max_count('numeric', v, lv)
            cases.append({'id': 'num-%s%d' % (lv, v), 'kind': 'numeric', 'data': ''.join(rnd.choice('0123456789') for _ in range(n)), 'level': lv, 'version': v, 'mask': rnd.randrange(8)})
            n = max_count('alnum', v, lv)
            cases.append({'id': 'aln-%s%d' % (lv, v), 'kind': 'alnum', 'data': ''.join(rnd.choice(ALNUM) for _ in range(n)), 'level': lv, 'version': v, 'mask': rnd.randrange(8)})
    compare(cases, 'full numeric/alnum')

    # 3. short and medium data inside bigger versions (padding bytes, short blocks)
    cases = []
    for v in range(1, 41):
        for lv in LVL:
            top = max_count('byte', v, lv)
            for n in sorted({0, 1, 2, max(0, top // 3), max(0, top // 2), max(0, top - 1)}):
                cases.append({'id': 'pad-%s%d-n%d' % (lv, v, n), 'kind': 'bytes', 'data': bytes(rnd.randrange(256) for _ in range(n)).hex(), 'level': lv, 'version': v, 'mask': rnd.randrange(8)})
    compare(cases, 'padding')

    # 4. automatic version and mask, random text of several kinds
    cases = []
    alphabets = [
        ('digits', '0123456789'), ('upper', ALNUM), ('lower', 'abcdefghijklmnopqrstuvwxyz'),
        ('url', 'abcdefghijklmnopqrstuvwxyz0123456789/:.-_?=&%#'), ('latin', 'abc deéüñß'),
        ('emoji', 'a\U0001F600\U0001F4A1 b'), ('cjk', '日本語文字'), ('mixed', 'Hello, 世界! 123'),
    ]
    k = 0
    for name, alpha in alphabets:
        for lv in LVL:
            for n in (1, 5, 17, 40, 120, 300, 700):
                text = ''.join(rnd.choice(alpha) for _ in range(n))
                cases.append({'id': 'auto-%s-%s-%d-%d' % (name, lv, n, k), 'kind': 'text', 'data': text, 'level': lv, 'version': 0, 'mask': None})
                k += 1
    compare(cases, 'auto')

    # 5. the exact edge where one more character needs the next version
    cases = []
    for lv in LVL:
        for mode, alpha, kind in (('byte', None, 'bytes'), ('numeric', '0123456789', 'numeric'), ('alnum', ALNUM, 'alnum')):
            for v in range(1, 40):
                n = max_count(mode, v, lv)
                for nn in (n, n + 1):
                    if kind == 'bytes':
                        data = bytes(rnd.randrange(256) for _ in range(nn)).hex()
                    else:
                        data = ''.join(rnd.choice(alpha) for _ in range(nn))
                    cases.append({'id': 'edge-%s-%s-v%d-n%d' % (lv, mode, v, nn), 'kind': kind, 'data': data, 'level': lv, 'version': 0, 'mask': rnd.randrange(8)})
    compare(cases, 'edge')

    # 6. too long
    for lv in LVL:
        n = max_count('byte', 40, lv)
        cases = [{'id': 'over-%s' % lv, 'kind': 'bytes', 'data': bytes(n + 1).hex(), 'level': lv, 'version': 0, 'mask': 0},
                 {'id': 'exact-%s' % lv, 'kind': 'bytes', 'data': bytes(n).hex(), 'level': lv, 'version': 0, 'mask': 0}]
        res = run_node(cases)
        ok('too long at v40 %s is refused' % lv, res['over-%s' % lv].get('error') == 'TOO_LONG', str(res['over-%s' % lv]))
        ok('exactly full at v40 %s fits' % lv, res['exact-%s' % lv].get('version') == 40, str(res['exact-%s' % lv]))


# ---------------------------------------------------------------- decoding with two independent readers
def picture(rows, scale=6, quiet=4):
    a = np.array([[int(ch) for ch in r] for r in rows], dtype=np.uint8)
    a = np.pad(a, quiet)
    a = np.kron(a, np.ones((scale, scale), dtype=np.uint8))
    return (255 - a * 255).astype(np.uint8)


def read_zx(img):
    return zxingcpp.read_barcodes(img, formats=zxingcpp.BarcodeFormat.QRCode)


def read_cv(img, aruco=False):
    d = cv2.QRCodeDetectorAruco() if aruco else cv2.QRCodeDetector()
    try:
        return d.detectAndDecode(img)[0]
    except Exception:
        return ''


def decode_tests():
    rnd = random.Random(7102026)
    # A. every version and level, data filling the code, read by zxing-cpp (bytes, level, count)
    cases, datas = [], {}
    for v in range(1, 41):
        for lv in LVL:
            n = max_count('byte', v, lv)
            data = bytes(rnd.randrange(256) for _ in range(n))
            cid = 'dz-%s%d' % (lv, v)
            datas[cid] = (data, lv, v)
            cases.append({'id': cid, 'kind': 'bytes', 'data': data.hex(), 'level': lv, 'version': v, 'mask': rnd.randrange(8)})
    res = run_node(cases, full=True)
    for c in cases:
        data, lv, v = datas[c['id']]
        rs = read_zx(picture(res[c['id']]['rows'], 4))
        good = len(rs) == 1 and rs[0].bytes == data and rs[0].ec_level == lv
        ok('zxing reads v%d %s full of random bytes (level and bytes)' % (v, lv), good, 'got %s' % ([(r.ec_level, len(r.bytes)) for r in rs],))

    # B. all 8 masks for a spread of sizes
    cases, datas = [], {}
    for v in (1, 2, 6, 7, 10, 14, 21, 27, 32, 39, 40):
        for lv in LVL:
            n = max(1, max_count('byte', v, lv) // 2)
            text = ''.join(rnd.choice('abcdefghijklmnopqrstuvwxyz0123456789 .,/:-_') for _ in range(n))
            for m in range(8):
                cid = 'mk-%s%d-%d' % (lv, v, m)
                datas[cid] = text
                cases.append({'id': cid, 'kind': 'text', 'data': text, 'level': lv, 'version': v, 'mask': m})
    res = run_node(cases, full=True)
    for c in cases:
        rs = read_zx(picture(res[c['id']]['rows'], 4))
        ok('zxing reads %s (mask %d, half full)' % (c['id'], c['mask']), len(rs) == 1 and rs[0].text == datas[c['id']])

    # C. OpenCV, both of its readers: text at several fill levels, every version
    cases, datas = [], {}
    for v in range(1, 41):
        for lv in 'LMQH':
            n = max(1, max_count('byte', v, lv) * 3 // 4)
            text = ''.join(rnd.choice('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .,/:-_?=&') for _ in range(n))
            cid = 'cv-%s%d' % (lv, v)
            datas[cid] = text
            cases.append({'id': cid, 'kind': 'text', 'data': text, 'level': lv, 'version': v, 'mask': rnd.randrange(8)})
    res = run_node(cases, full=True)
    miss = {'std': [], 'aruco': []}
    for c in cases:
        img = picture(res[c['id']]['rows'], 6)
        for name, flag in (('std', False), ('aruco', True)):
            if read_cv(img, flag) != datas[c['id']]:
                miss[name].append(c['id'])
    # OpenCV is a second opinion and a weaker reader than zxing-cpp (its classic detector often misses codes of middle versions that
    # are identical to the ones segno draws). The Aruco based reader has to read nearly all of them.
    for name in miss:
        print('OpenCV %s did not read %d of %d codes: %s' % (name, len(miss[name]), len(cases), miss[name][:20]))
    ok('OpenCV (aruco reader) reads at least 156 of 160 codes', len(miss['aruco']) <= 4, str(miss['aruco']))
    ok('OpenCV (classic reader) reads at least 100 of 160 codes', len(miss['std']) <= 60, str(len(miss['std'])))

    # D. error correction really corrects: flip random modules (not the three corners) and read again
    for lv, frac in (('L', 0.002), ('M', 0.005), ('Q', 0.008), ('H', 0.010)):
        for v in (3, 8, 15, 25):
            n = max_count('byte', v, lv) * 2 // 3
            text = ''.join(rnd.choice('abcdefghijklmnopqrstuvwxyz0123456789') for _ in range(n))
            r = run_node([{'id': 'ec', 'kind': 'text', 'data': text, 'level': lv, 'version': v, 'mask': rnd.randrange(8)}], full=True)['ec']
            rows = [list(row) for row in r['rows']]
            size = r['size']
            flips = 0
            tries = 0
            target = int(size * size * frac)
            while flips < target and tries < 100000:
                tries += 1
                x, y = rnd.randrange(size), rnd.randrange(size)
                if (x < 9 and y < 9) or (x >= size - 8 and y < 9) or (x < 9 and y >= size - 8):
                    continue
                rows[y][x] = '1' if rows[y][x] == '0' else '0'
                flips += 1
            rs = read_zx(picture([''.join(row) for row in rows], 6))
            ok('zxing repairs %d flipped modules in v%d %s' % (flips, v, lv), len(rs) == 1 and rs[0].text == text)

    # A reader that never fails would prove nothing: with a third of the modules wrecked, even level H must fail.
    r = run_node([{'id': 'ec', 'kind': 'text', 'data': 'wrecked beyond repair 0123456789', 'level': 'H', 'version': 4, 'mask': 2}], full=True)['ec']
    rows = [list(row) for row in r['rows']]
    for _ in range(int(r['size'] ** 2 * 0.33)):
        x, y = rnd.randrange(9, r['size'] - 8), rnd.randrange(9, r['size'] - 8)
        rows[y][x] = '1' if rows[y][x] == '0' else '0'
    ok('zxing cannot read a code with a third of its modules flipped', len(read_zx(picture([''.join(row) for row in rows], 6))) == 0)

    # E. text that is not ASCII: UTF-8 bytes in byte mode
    samples = ['café crème', '日本語のテキスト', 'Привет, мир', 'emoji \U0001F600\U0001F680 ok', 'مرحبا', 'tab\tand\nnewline', '', 'a' * 1000]
    for text in samples:
        if not text:
            continue
        for lv in LVL:
            r = run_node([{'id': 'u', 'kind': 'text', 'data': text, 'level': lv, 'version': 0, 'mask': None}], full=True)['u']
            rs = read_zx(picture(r['rows'], 5))
            ok('zxing reads %r at %s' % (text[:12], lv), len(rs) == 1 and rs[0].bytes == text.encode('utf-8'))


if __name__ == '__main__':
    if MODE in ('matrix', 'all'):
        matrix_tests()
    if MODE in ('decode', 'all'):
        decode_tests()
    print('passed %d, failed %d' % (passes, len(fails)))
    for f in fails[:40]:
        print('FAIL', f)
    sys.exit(1 if fails else 0)
