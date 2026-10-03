#!/usr/bin/env python3
"""Grime Time: the full test suite. One file, one pass count.

    python3 grime_test.py                                                     # the fragment (grime-time.html), the same embedded fonts as the built page
    GRIME_STANDALONE=$PWD/site/grime-time/index.html python3 grime_test.py    # the BUILT page (adds metadata, privacy, image and font checks)
    GRIME_SECTIONS=math,pace python3 grime_test.py                            # only some sections while developing

Sections: hygiene builder meta math wash pace shop save storage keyboard input share env play layout contrast journey
Needs python3 with playwright and Pillow, node (the pure economy and wash code runs in Node), and a Chromium that Playwright can start.
Run it as the only browser process: the machine has two shared cores and several timings are real.

What it covers
  hygiene   source files: no forbidden dash characters, ASCII only, no outside scripts or hosts, no network, cookie or dialog calls, test hooks gated
  builder   the builder refuses stray dashes, placeholders, outside links, wrong h1 counts, scripts and forbidden calls
  meta      built page only: title, description, canonical, share tags, icons, images, privacy page, footer links, fonts, alt text against the image
  math      the economy against an independent exact reference (fractions): costs, crew income, offline credit, franchise points, payout, stars,
            unlocks, number formatting, save codes, hash and noise functions
  wash      the wash core: fixed seed determinism (Node and browser agree), invariants, tip hardness, soap, scuffs, surface cleaner
  pace      the pacing bot's first job, first upgrade, first crew, six jobs, surface cleaner and Franchise times stay inside the agreed ranges
  shop save storage keyboard input share env play   the page itself, through real clicks, keys, pointer and touch events
  layout contrast journey   widths, tap sizes, contrast in both schemes, and a short journey with real pointer strokes only
"""
import atexit
import base64
import contextlib
import functools
import html as htmllib
import http.server
import io
import json
import math
import os
import pathlib
import random
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from fractions import Fraction

from PIL import Image, ImageStat
from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
SRC = HERE / 'grime-time.html'
STANDALONE = os.path.abspath(os.environ['GRIME_STANDALONE']) if os.environ.get('GRIME_STANDALONE') else ''
SECTIONS = set(x for x in os.environ.get('GRIME_SECTIONS', '').split(',') if x)
STORE = 'grime-time-v1'
SITE_URL = 'https://sanjixysti-creator.github.io/grime-time/'
ALLOWED_HOSTS = {'sanjixysti-creator.github.io', 'docs.github.com'}
FONT_HOSTS = {'fonts.googleapis.com', 'fonts.gstatic.com'}   # only the fragment names these (link tags the builder replaces)

# Dash look-alikes are checked for without typing them, so this file stays free of them too.
EM, EN, MINUS = chr(0x2014), chr(0x2013), chr(0x2212)
DASHES = EM + EN + MINUS


def on(*names):
    return not SECTIONS or any(n in SECTIONS for n in names)


# ------------------------------------------------------------------ counters
passes = 0
fails = []
ERRS = []        # console errors and warnings from every page
EXT_REQS = []    # requests that left the test server
DIALOGS = []     # alert, confirm or prompt opened by any page
COOKIES = []     # cookies seen when a context was closed
LIVE = []        # browser contexts that are still open (a section that fails midway must not leak them)


def ok(name, cond, detail=''):
    global passes
    if cond:
        passes += 1
    else:
        msg = name + (('\n      ' + str(detail)[:700]) if detail != '' else '')
        fails.append(msg)
        print('  FAIL', msg, flush=True)


def eq(name, got, want):
    ok(name, got == want, 'got %r, want %r' % (got, want))


def has(name, text, needle):
    ok(name, needle in (text or ''), 'missing %r in %r' % (needle, (text or '')[:300]))


def near(name, got, want, tol=1e-9):
    ok(name, got is not None and want is not None and abs(got - want) <= tol, 'got %r want %r tol %r' % (got, want, tol))


def batch(name, bad, count):
    """One check per case: `count` cases were compared, `bad` holds the differences."""
    global passes
    if bad:
        msg = '%s: %d of %d cases differ, first: %s' % (name, len(bad), count, ' | '.join(str(b) for b in bad[:3]))
        fails.append(msg)
        print('  FAIL', msg, flush=True)
    else:
        passes += count


@contextlib.contextmanager
def section(name):
    t0, p0, f0 = time.time(), passes, len(fails)
    try:
        yield
    except Exception as e:
        first = (str(e).strip().splitlines() or [''])[0][:300]
        msg = '%s: EXCEPTION %s: %s' % (name, type(e).__name__, first)
        fails.append(msg)
        print('  FAIL', msg, flush=True)
        traceback.print_exc(file=sys.stdout)
    finally:
        for c in list(LIVE):
            close(c)
    print('%-10s %6d checks %4d failed %7.1fs' % (name, passes - p0, len(fails) - f0, time.time() - t0), flush=True)


# ------------------------------------------------------------------ what is served
TMP = pathlib.Path(tempfile.mkdtemp(prefix='grime-test-'))
atexit.register(lambda: shutil.rmtree(TMP, ignore_errors=True))
SRC_TEXT = SRC.read_text(encoding='utf-8')

if STANDALONE:
    BUILT = pathlib.Path(STANDALONE)
    SITE_DIR = BUILT.parent
    SERVE = SITE_DIR.parent
    PAGE_PATH = '/' + SITE_DIR.name + '/'
    BLANK_PATH = PAGE_PATH + 'privacy.html'     # a same-origin page with no game code: tests edit saved progress from here
    CODE_FILE = BUILT
    BUILT_TEXT = BUILT.read_text(encoding='utf-8')
else:
    BUILT = None
    BUILT_TEXT = ''
    from build_site import SKELETON_CSS, APP_FONTS, font_faces
    SERVE = TMP
    PAGE_PATH = '/grime-test.html'
    BLANK_PATH = '/blank.html'
    CODE_FILE = SRC
    (TMP / 'grime-test.html').write_text(
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<style>' + SKELETON_CSS + '\n' + font_faces(APP_FONTS) + '</style></head><body>' + SRC_TEXT + '</body></html>', encoding='utf-8')
    (TMP / 'blank.html').write_text('<!doctype html><html><head><meta charset="utf-8"><title>blank</title></head><body>blank</body></html>', encoding='utf-8')


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


HTTPD = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(SERVE)))
PORT = HTTPD.server_address[1]
threading.Thread(target=HTTPD.serve_forever, daemon=True).start()
ORIGIN = 'http://127.0.0.1:%d' % PORT


def png_size(path):
    with open(path, 'rb') as f:
        head = f.read(24)
    if head[:8] != b'\x89PNG\r\n\x1a\n':
        return None
    return struct.unpack('>II', head[16:24])


# ------------------------------------------------------------------ browser and pages
class Box:
    p = None
    b = None


BOX = Box()


def browser():
    if BOX.b is None or not BOX.b.is_connected():
        if BOX.p is None:
            BOX.p = sync_playwright().start()
        try:
            BOX.b = BOX.p.chromium.launch()
        except Exception:
            BOX.b = BOX.p.chromium.launch(executable_path='/opt/pw-browsers/chromium-1194/chrome-linux/chrome')
    return BOX.b


def shutdown_browser():
    try:
        if BOX.b is not None:
            BOX.b.close()
    except Exception:
        pass
    try:
        if BOX.p is not None:
            BOX.p.stop()
    except Exception:
        pass


atexit.register(shutdown_browser)

FONT_ROUTE = re.compile(r'https://fonts\.(googleapis|gstatic)\.com/.*')


def watch(pg, logs, tag=''):
    def on_console(m):
        if m.type in ('error', 'warning'):
            if not STANDALONE and 'ERR_FAILED' in m.text:
                return   # the fragment names Google Fonts, the suite blocks them
            logs.append((m.type, m.text))
            ERRS.append((tag, m.type, m.text))
    pg.on('console', on_console)
    pg.on('pageerror', lambda e: (logs.append(('pageerror', str(e))), ERRS.append((tag, 'pageerror', str(e)))))

    def on_request(r):
        u = r.url
        if u.startswith(ORIGIN + '/') or u.startswith(('data:', 'blob:', 'about:')):
            return
        host = re.sub(r'^https?://([^/:]+).*$', r'\1', u)
        if not STANDALONE and host in FONT_HOSTS:
            return
        EXT_REQS.append(u)
    pg.on('request', on_request)

    def on_dialog(d):
        DIALOGS.append((d.type, d.message))
        d.dismiss()
    pg.on('dialog', on_dialog)
    if not STANDALONE:
        pg.route(FONT_ROUTE, lambda r: r.abort())
    pg.route('**/favicon.ico', lambda r: r.fulfill(status=204, body=''))


def new_page(w=390, h=844, scheme='light', dpr=2, touch=True, hash='#test', init=None, path=None, reduced=False, downloads=False, tag='', wait=400, pre=None):
    ctx = browser().new_context(viewport={'width': w, 'height': h}, device_scale_factor=dpr, color_scheme=scheme, is_mobile=touch, has_touch=touch,
                                reduced_motion='reduce' if reduced else 'no-preference', accept_downloads=downloads)
    for s in (init or ()):
        ctx.add_init_script(s)
    LIVE.append(ctx)
    pg = ctx.new_page()
    pg.set_default_timeout(10000)
    logs = []
    watch(pg, logs, tag or ('%dx%d %s' % (w, h, scheme)))
    if pre:
        pre(pg)
    pg.goto(ORIGIN + (path or PAGE_PATH) + hash)
    if wait:
        pg.wait_for_timeout(wait)
    return ctx, pg, logs


def close(ctx):
    try:
        COOKIES.extend(ctx.cookies())
    except Exception:
        pass
    try:
        ctx.close()
    except Exception:
        pass
    if ctx in LIVE:
        LIVE.remove(ctx)


def st(pg):
    return pg.evaluate('()=>JSON.parse(JSON.stringify(window.__grime.state()))')


def pure(pg, expr):
    return pg.evaluate('(e)=>{const P=window.__grime.PURE;return eval(e)}', expr)


def gev(pg, expr):
    return pg.evaluate('()=>' + expr)


def saved(pg):
    raw = pg.evaluate("(k)=>localStorage.getItem(k)", STORE)
    return json.loads(raw) if raw else {}


def edit_save(pg, patch, hash='#test'):
    """Leave the game (its pagehide handler saves), edit the saved JSON on a same-origin page that has no game code, return to the game."""
    pg.goto(ORIGIN + BLANK_PATH)
    d = json.loads(pg.evaluate("(k)=>localStorage.getItem(k)", STORE))
    patch(d)
    pg.evaluate("(a)=>localStorage.setItem(a[0], a[1])", [STORE, json.dumps(d)])
    pg.goto(ORIGIN + PAGE_PATH + hash)
    pg.wait_for_timeout(500)
    return d


def put_raw(pg, raw, hash='#test'):
    pg.goto(ORIGIN + BLANK_PATH)
    pg.evaluate("(a)=>{localStorage.removeItem(a[0] + '-backup');localStorage.setItem(a[0], a[1])}", [STORE, raw])
    pg.goto(ORIGIN + PAGE_PATH + hash)
    pg.wait_for_timeout(500)


# ------------------------------------------------------------------ node: the pure economy and wash code
NODE = shutil.which('node')
DRIVER = TMP / 'grime_node_driver.js'
DRIVER.write_text(r'''
'use strict';
const fs = require('fs');
const sim = require(process.env.GRIME_SIM);
const file = process.argv[2], mode = process.argv[3];
const P = sim.loadPure(file);
const D = P.DATA;
let raw = '';
try { raw = fs.readFileSync(0, 'utf8'); } catch (e) { raw = ''; }
const req = raw.trim() ? JSON.parse(raw) : null;
const NUMS = { 'Infinity': Infinity, '-Infinity': -Infinity, 'NaN': NaN };
function fix(v) {
  if (typeof v === 'string' && v.indexOf('$num:') === 0) return NUMS[v.slice(5)];
  if (Array.isArray(v)) return v.map(fix);
  if (v && typeof v === 'object') {
    if (typeof v.$job === 'string') return P.byId(D.jobs, v.$job);
    const o = {};
    for (const k in v) o[k] = fix(v[k]);
    return o;
  }
  return v;
}
function out(v) {
  process.stdout.write(JSON.stringify(v, function (k, x) { return (typeof x === 'number' && !isFinite(x)) ? '$num:' + String(x) : x; }));
}
function fnv(arr) {
  const u = new Uint8Array(arr.buffer, arr.byteOffset, arr.byteLength);
  let h = 2166136261;
  for (let i = 0; i < u.length; i++) { h ^= u[i]; h = Math.imul(h, 16777619) >>> 0; }
  return h.toString(16);
}
function rigFor(q) {
  const s = P.freshState();
  for (const k in (q.up || {})) s.up[k] = q.up[k];
  for (const k in (q.gear || {})) s.gear[k] = q.gear[k];
  return P.rigOf(s);
}
function stats(w, s) {
  return { left: w.left, total0: w.total0, units: w.units, flowSum: w.flowSum, flowUnits: w.flowUnits, secs: w.secs, toughDone: w.toughDone,
           toughTotal: w.toughTotal, scuffN: w.scuffN, foamN: w.foamN, tank: s.tank, mult: s.mult, cov: P.coverage(w), hThick: fnv(w.thick), res: P.washResult(w) };
}
function runScript(q) {
  const job = P.byId(D.jobs, q.job), rig = rigFor(q), w = P.makeWash(job, q.gw, q.gh, q.seed >>> 0);
  w.track = false;
  const s = P.newSprayer(rig, 'white');
  for (const p of q.steps) {
    if (p[3]) s.tip = P.byId(D.tips, p[3]);
    s.x = p[0]; s.y = p[1]; s.on = !!p[2];
    P.simStep(w, s, rig, 1 / 60);
  }
  return stats(w, s);
}
function snake(W, H, R, speed) {
  const pts = [], sp = speed / 60;
  let dir = 1;
  for (let y = R / 2; y < H + R / 2; y += R * 1.3) {
    const yy = Math.min(H - 5, y);
    if (dir > 0) { for (let x = 0; x <= W; x += sp) pts.push([x, yy]); } else { for (let x = W; x >= 0; x -= sp) pts.push([x, yy]); }
    dir = -dir;
  }
  return pts;
}
function synthJob(film, o) {
  o = o || {};
  return { id: 'synthetic', name: 'Synthetic', pay: 1, par: 1, stars: 0, gear: [], delicate: !!o.delicate,
           recipe: { region: 'full', film: [film, film], specials: o.specials || [] } };
}
function invariantRun(jobId, seed, cfg) {
  const job = P.byId(D.jobs, jobId), rig = rigFor(cfg);
  const sz = P.sceneSize(0.56), gw = sz.W / D.cell, gh = sz.H / D.cell;
  const w = P.makeWash(job, gw, gh, seed >>> 0);
  w.track = false;
  const s = P.newSprayer(rig, 'white');
  let sum0 = 0;
  for (let i = 0; i < w.thick.length; i++) sum0 += w.thick[i];
  const prev = Float32Array.from(w.thick), bad = {};
  const flag = function (k, d) { if (!(k in bad)) bad[k] = String(d); };
  let n = 0;
  function check() {
    let cnt = 0, up = false, live = 0, fbad = false;
    for (let i = 0; i < w.thick.length; i++) {
      const t = w.thick[i];
      if (t > 0) cnt++;
      if (t > prev[i] + 1e-6) up = true;
      prev[i] = t;
      const f = w.foam[i];
      if (f > 0) live++;
      if (f < 0 || f > 1 + 1e-6) fbad = true;
    }
    if (cnt !== w.left) flag('left counts the cells that still have grime', cnt + ' vs ' + w.left);
    if (up) flag('grime thickness never grows', 'grew');
    if (fbad) flag('foam stays between 0 and 1', 'out of range');
    if (live !== w.foamN) flag('foam counter matches the foam cells', live + ' vs ' + w.foamN);
    if (w.toughDone > w.toughTotal) flag('tough spots cleaned never exceed the tough spots', w.toughDone + ' > ' + w.toughTotal);
  }
  for (const id of cfg.tips) {
    s.tip = P.byId(D.tips, id);
    const R = D.wash.baseR * s.tip.r * rig.rMul;
    for (const p of snake(w.W, w.H, R, 900)) {
      s.x = p[0]; s.y = p[1]; s.on = true;
      P.simStep(w, s, rig, 1 / 60);
      n++;
      if (s.mult < 1 - 1e-9 || s.mult > rig.flowCap + 1e-9) flag('flow multiplier stays between 1 and its cap', s.mult);
      if (s.tank < -1e-9 || s.tank > rig.tankMax + 1e-9) flag('tank stays between empty and full', s.tank);
      const cov = P.coverage(w);
      if (cov < -1e-12 || cov > 1 + 1e-12) flag('coverage stays between 0 and 1', cov);
      if (n % 25 === 0) check();
    }
    s.on = false;
    for (let k = 0; k < 90; k++) P.simStep(w, s, rig, 1 / 60);
    check();
  }
  let sum1 = 0;
  for (let i = 0; i < w.thick.length; i++) sum1 += w.thick[i];
  const removed = sum0 - sum1, done = w.total0 - w.left;
  if (Math.abs(removed - w.units) > 1e-5 * sum0 + D.eps * done + 1) flag('grime units removed match the thickness that disappeared', removed + ' vs ' + w.units);
  if (w.units < 0) flag('units are never negative', w.units);
  if (w.secs < n / 60 - 1e-6 || w.secs > (n + 90 * cfg.tips.length) / 60 + 1e-6) flag('wash clock counts the fixed steps', w.secs);
  return { bad: bad, steps: n, cov: P.coverage(w), left: w.left };
}
function phys() {
  const res = [];
  const add = function (name, ok, detail) { res.push([name, !!ok, detail === undefined ? '' : String(detail)]); };
  function spray(w, s, rig, id, x, y, secs) {
    s.tip = P.byId(D.tips, id); s.x = x; s.y = y; s.on = true; s.hasPrev = false;
    const n = Math.round(secs * 60);
    for (let i = 0; i < n; i++) P.simStep(w, s, rig, 1 / 60);
    s.on = false;
  }
  const mk = function (film, o, gw) { const w = P.makeWash(synthJob(film, o), gw || 30, gw || 30, 1); w.track = false; return w; };
  let rig = rigFor({}), w = mk(200), s = P.newSprayer(rig, 'white'), l0 = w.left;
  spray(w, s, rig, 'white', w.W / 2, w.H / 2, 3);
  add('a white tip cannot clean caked grime on a plain rig', w.left === l0, l0 + ' -> ' + w.left);
  spray(w, s, rig, 'red', w.W / 2, w.H / 2, 3);
  add('the red tip cleans caked grime', w.left < l0, l0 + ' -> ' + w.left);
  w = mk(100); s = P.newSprayer(rig, 'white'); l0 = w.left;
  spray(w, s, rig, 'soap', w.W / 2, w.H / 2, 2);
  add('soap never removes grime', w.left === l0, l0 + ' -> ' + w.left);
  add('soap lays foam', w.foamN > 0, w.foamN);
  w = mk(100); s = P.newSprayer(rig, 'white'); l0 = w.left;
  spray(w, s, rig, 'white', w.W / 2, w.H / 2, 2);
  add('without foam the white tip cannot clean the grime layer', w.left === l0, l0 + ' -> ' + w.left);
  w = mk(100); s = P.newSprayer(rig, 'white');
  spray(w, s, rig, 'soap', w.W / 2, w.H / 2, 1.2);
  spray(w, s, rig, 'white', w.W / 2, w.H / 2, 0.5);
  add('foam lets the white tip clean the grime layer', w.left < l0, l0 + ' -> ' + w.left);
  for (const delicate of [true, false]) {
    w = mk(30, { delicate: delicate }); s = P.newSprayer(rig, 'white');
    spray(w, s, rig, 'red', w.W / 2, w.H / 2, 4);
    add('the red tip ' + (delicate ? 'scuffs' : 'does not scuff') + ' a ' + (delicate ? 'delicate' : 'plain') + ' job', delicate ? w.scuffN > 0 : w.scuffN === 0, 'scuffN ' + w.scuffN);
    if (delicate) add('scuffs cost pay through the penalty', P.washResult(w).penalty > 0 && P.washResult(w).penalty <= D.wash.scuffMax, P.washResult(w).penalty);
  }
  w = mk(40); s = P.newSprayer(rig, 'white');
  const steps = 600;
  s.tip = P.byId(D.tips, 'white'); s.x = w.W / 2; s.y = w.H / 2; s.on = true;
  for (let i = 0; i < steps; i++) P.simStep(w, s, rig, 1 / 60);
  add('the tank drains by the tip water rate', Math.abs(s.tank - (rig.tankMax - steps / 60 * s.tip.water * D.wash.tankDrain)) < 1e-6, s.tank);
  s.on = false;
  const t1 = s.tank;
  for (let i = 0; i < 60; i++) P.simStep(w, s, rig, 1 / 60);
  add('an idle tank refills at its own rate', Math.abs(s.tank - Math.min(rig.tankMax, t1 + rig.tankMax * D.wash.tankRefill)) < 1e-6, s.tank);
  const specials = [{ k: 'oil', n: 1, r: [4, 4], t: [100, 100], x: [0.5, 0.5], y: [0.5, 0.5] }];
  const rigS = rigFor({ up: { pressure: 3 }, gear: { surface: true } });
  w = P.makeWash(synthJob(40, { specials: specials }), 40, 40, 1); w.track = false;
  const t0 = Float32Array.from(w.thick), S = D.surface;
  for (let i = 0; i < 42; i++) P.discStamp(w, w.W / 2, w.H / 2, 1 / 60, rigS, S.r * rigS.rMul);
  let wrong = 0, kept = 0;
  for (let cy = 0; cy < w.gh; cy++) for (let cx = 0; cx < w.gw; cx++) {
    const i = cy * w.gw + cx;
    if (!(t0[i] > 0)) continue;
    const px = (cx + 0.5) * D.cell, py = (cy + 0.5) * D.cell;
    const edge = px < S.edge || px > w.W - S.edge || py < S.edge || py > w.H - S.edge;
    const skip = w.kind[i] && S.skip.indexOf(w.kind[i]) >= 0;
    const expectLeft = edge || skip;
    if (expectLeft) kept++;
    if ((w.thick[i] > 0) !== !!expectLeft) wrong++;
  }
  add('the surface cleaner skips stains and the edge strip and cleans the rest', wrong === 0 && kept > 0 && w.left === kept, 'wrong ' + wrong + ' kept ' + kept + ' left ' + w.left);
  w = mk(100); s = P.newSprayer(rig, 'white');
  P.tidyTo(w, 1);
  add('the tidy sweep clears every speck', w.left === 0 && P.coverage(w) === 1, w.left);
  const path = snake(1000, 1780, 70, 900).slice(0, 700);
  const weak = P.freshState(), strong = P.freshState();
  strong.up.pressure = 6;
  const run = function (rg) {
    const ww = P.makeWash(P.byId(D.jobs, 'patio'), 100, 178, 5); ww.track = false;
    const sp = P.newSprayer(rg, 'white');
    for (const p of path) { sp.x = p[0]; sp.y = p[1]; sp.on = true; P.simStep(ww, sp, rg, 1 / 60); }
    return ww.left;
  };
  const a = run(P.rigOf(weak)), b = run(P.rigOf(strong));
  add('more pressure never cleans less on the same path', b <= a, a + ' vs ' + b);
  return res;
}

if (mode === 'rpc') {
  out(req.map(function (c) {
    try { return { r: P[c[0]].apply(null, fix(c[1])) }; } catch (e) { return { e: String((e && e.message) || e) }; }
  }));
} else if (mode === 'data') {
  out({ DATA: D, SAVE_VERSION: P.SAVE_VERSION, keys: Object.keys(P).sort() });
} else if (mode === 'grid') {
  out(req.map(function (q) {
    const job = P.byId(D.jobs, q.job), g = P.makeGrid(job, q.gw, q.gh, q.seed >>> 0);
    let sum = 0;
    const kinds = [0, 0, 0, 0, 0, 0];
    for (let i = 0; i < g.thick.length; i++) { sum += g.thick[i]; kinds[g.kind[i]]++; }
    return { job: q.job, seed: q.seed, total: g.total, tough: g.toughTotal, hThick: fnv(g.thick), hKind: fnv(g.kind), hTough: fnv(g.tough), sum: sum, kinds: kinds };
  }));
} else if (mode === 'prng') {
  out(req.map(function (seed) {
    const f = P.mulberry32(seed), a = [];
    for (let i = 0; i < 64; i++) a.push(f());
    return a;
  }));
} else if (mode === 'run') {
  out(req.map(runScript));
} else if (mode === 'inv') {
  out(req.map(function (q) { return invariantRun(q.job, q.seed, q); }));
} else if (mode === 'phys') {
  out(phys());
} else if (mode === 'pace') {
  const r = sim.pace(P, req.hours, { franchiseAt: req.franchiseAt });
  out({ ms: r.ms, stats: r.stats, jobs: r.jobsPlayed });
} else {
  throw new Error('unknown mode ' + mode);
}
''', encoding='utf-8')


def node(mode, req=None, timeout=400):
    if not NODE:
        raise RuntimeError('node is not installed: the pure economy and wash code runs in Node')
    r = subprocess.run([NODE, str(DRIVER), str(CODE_FILE), mode], input=json.dumps(req) if req is not None else '', capture_output=True,
                       text=True, timeout=timeout, env=dict(os.environ, GRIME_SIM=str(HERE / 'grime_sim.js')))
    if r.returncode != 0:
        raise RuntimeError('node %s failed: %s' % (mode, (r.stderr or r.stdout)[-600:]))

    def undo(v):
        if isinstance(v, str) and v.startswith('$num:'):
            return float(v[5:])
        if isinstance(v, list):
            return [undo(x) for x in v]
        if isinstance(v, dict):
            return {k: undo(x) for k, x in v.items()}
        return v
    return undo(json.loads(r.stdout))


def rpc(calls):
    """calls: [(function name, [args])]. Returns the list of results from the page's own pure code (exceptions become {'e': ...})."""
    res = node('rpc', [[c[0], c[1]] for c in calls])
    out = []
    for c, r in zip(calls, res):
        if 'e' in r:
            raise RuntimeError('%s%r raised %s' % (c[0], tuple(c[1])[:3], r['e']))
        out.append(r['r'])
    return out


import build_grime as BG                      # the builder: constants, problems_for(), check_meta(), build_index(), build_privacy()
from build_site import APP_FONTS, PRIVACY_FONTS


# ================================================================== hygiene: the source files
FORBIDDEN_CALLS = [r'\bfetch\(', r'XMLHttpRequest', r'sendBeacon', r'WebSocket', r'EventSource', r'importScripts', r'document\.cookie',
                   r'\balert\(', r'\bconfirm\(', r'\bprompt\(', r'\beval\(', r'new Function', r'document\.write', r'navigator\.geolocation',
                   r'indexedDB', r'serviceWorker', r'sessionStorage']
DELIVERABLES = ['grime-time.html', 'build_grime.py', 'build_images_grime.py', 'grime_test.py', 'grime_sim.js', 'livebot.js', 'grime-time-notes.md']


def urls_in(text):
    text = text.replace('http://www.w3.org/2000/svg', '')
    return set(re.findall(r'https?://[^\s"\'<>)]+', text))


def host_of(u):
    return re.sub(r'^https?://([^/:]+).*$', r'\1', u)


def pure_region(text):
    m = re.search(r'PURE-BEGIN[^\n]*\n(.*?)/\* PURE-END', text, re.S)
    return m.group(1) if m else None


def t_hygiene():
    files = [HERE / n for n in DELIVERABLES if (HERE / n).exists()]
    if STANDALONE:
        files += [BUILT, BUILT.parent / 'privacy.html']
    for p in files:
        txt = p.read_text(encoding='utf-8')
        bad = [(i, c) for i, c in enumerate(txt) if c in DASHES]
        ok('no em dash, en dash or minus sign in ' + p.name, not bad, bad[:3])
        odd = [(i, ord(c)) for i, c in enumerate(txt) if ord(c) > 126 or (ord(c) < 32 and c not in '\n\r\t')]
        ok('only plain ASCII in ' + p.name, not odd, odd[:3])
    # the fragment
    src = SRC_TEXT
    eq('fragment: one style block', src.count('<style>'), 1)
    eq('fragment: one script block', len(re.findall(r'<script\b', src)), 1)
    ok('fragment: no external script, @import, frame, object or embed', not re.search(r'<script[^>]*\bsrc=|@import|<iframe|<object|<embed', src))
    hosts = {host_of(u) for u in urls_in(src)}
    ok('fragment: only allowed hosts are named (the font links are replaced by the builder)', hosts <= ALLOWED_HOSTS | FONT_HOSTS, hosts - ALLOWED_HOSTS - FONT_HOSTS)
    for pat in FORBIDDEN_CALLS:
        ok('fragment: no ' + pat, not re.search(pat, src))
    ok('fragment: no claude.ai link anywhere', 'claude.ai' not in src.lower())
    ok('fragment: no payment or unlock code content in a free game', not re.search(r'stripe|paypal|pro-code|unlock code', src, re.I))
    eq('fragment: exactly one h1', len(re.findall(r'<h1[ >]', src)), 1)
    ok('fragment: one inline script that is an IIFE in strict mode', re.search(r"<script>\s*\(function \(\) \{\s*'use strict';", src) is not None)
    ok('fragment: dark scheme is designed (prefers-color-scheme: dark)', 'prefers-color-scheme: dark' in src)
    ok('fragment: reduced motion is honoured (prefers-reduced-motion)', 'prefers-reduced-motion' in src)
    ok('fragment: live region for announcements', 'aria-live="polite"' in src and 'id="srRead"' in src)
    ok('fragment: no inline event handler attributes', not re.search(r'\son(click|load|error|pointer\w+|key\w+|touch\w+)=', src))
    # the pure region (no DOM, no clock, no randomness: Node and the tests rely on that)
    pr = pure_region(src)
    ok('fragment: pure region markers exist', pr is not None)
    if pr is not None:
        for tok in ('document', 'window', 'localStorage', 'navigator', 'Math.random', 'Date', 'performance', 'requestAnimationFrame', 'setTimeout', 'setInterval'):
            ok('pure region does not use ' + tok, tok not in pr)
    # test hooks exist only behind the #test address
    ok('test hooks are created only when TEST is true', re.search(r'if \(TEST\) exposeTestHooks\(\)', src) is not None and src.count('window.__grime = {') == 1)
    ok('TEST is exactly the address hash #test', "location.hash === '#test'" in src)
    calls = [m.start() for m in re.finditer(r'localStorage\.(getItem|setItem|removeItem)', src)]
    ok('every storage call sits inside a try block', calls and all('try {' in src[max(0, i - 90):i] for i in calls), len(calls))
    ok('the portal hooks exist and do nothing', 'function portalBreak(reason) { return reason; }' in src and 'function portalRewarded() { return false; }' in src and 'id="rewardBtn"' in src)
    m2 = re.search(r"var SUPPORT = '([^']+)';", src)
    ok('the support address is the house one', m2 is not None and m2.group(1) == 'fireseabrook2566@gmail.com', m2 and m2.group(1))
    if STANDALONE:
        t = BUILT_TEXT
        pb = BG.problems_for('index.html', t, 'index')
        ok('built page: builder finds nothing to refuse', pb == [], pb)
        hosts = {host_of(u) for u in urls_in(t)}
        ok('built page: only this site and the GitHub privacy statement are named', hosts <= ALLOWED_HOSTS, hosts - ALLOWED_HOSTS)
        ok('built page: no font service is contacted (fonts are embedded)', 'fonts.googleapis.com' not in t and 'fonts.gstatic.com' not in t)
        eq('built page: font faces are embedded as data', t.count('@font-face'), len(APP_FONTS))
        eq('built page: every font face is a data URI', t.count('url(data:font/woff2;base64,'), len(APP_FONTS))
        eq('built page: one script block', len(re.findall(r'<script\b', t)), 1)
        eq('built page: one style block', t.count('<style>'), 1)
        ok('built page: no claude.ai link anywhere', 'claude.ai' not in t.lower())
        ok('built page: size stays reasonable (under 450 KB)', len(t.encode('utf-8')) < 450 * 1024, len(t.encode('utf-8')))
        ok('built page: the pure game code is identical to the fragment', pure_region(t) == pr)


# ================================================================== builder: what it refuses
def probs(text, kind='index'):
    return BG.problems_for('x.html', text, kind)


def t_builder():
    base_index = '<!doctype html><html lang="en"><head><title>t</title></head><body><h1>Grime Time</h1><p>fine</p><script>var a = 1;</script></body></html>'
    base_priv = '<!doctype html><html lang="en"><head><title>t</title></head><body><h1>Privacy</h1><p>fine</p></body></html>'
    eq('builder: a clean page has no problems', probs(base_index), [])
    eq('builder: a clean privacy page has no problems', probs(base_priv, 'privacy'), [])
    cases = []
    for ch, name in ((EM, 'an em dash'), (EN, 'an en dash'), (MINUS, 'a minus sign')):
        cases.append(('refuses ' + name, base_index.replace('fine', 'a ' + ch + ' b'), 'dash character'))
    cases += [
        ('refuses an unreplaced placeholder', base_index.replace('fine', '@@TILE@@'), 'unreplaced placeholder'),
        ('refuses a link to another site', base_index.replace('fine', '<a href="https://example.com/x">x</a>'), 'outside address'),
        ('refuses a look alike host', base_index.replace('fine', '<a href="https://sanjixysti-creator.github.io.evil.com/">x</a>'), 'outside address'),
        ('refuses a plain http link to this site', base_index.replace('fine', '<a href="http://sanjixysti-creator.github.io/">x</a>'), 'outside address'),
        ('refuses a claude.ai link', base_index.replace('fine', '<a href="https://claude.ai/artifact/x">x</a>'), 'outside address'),
        ('refuses a page with no h1', base_index.replace('<h1>Grime Time</h1>', ''), 'h1'),
        ('refuses a page with two h1', base_index.replace('<h1>Grime Time</h1>', '<h1>A</h1><h1 class="x">B</h1>'), 'h1'),
        ('refuses a second script', base_index.replace('</body>', '<script>var b = 2;</script></body>'), 'one script'),
        ('refuses a page with no script', base_index.replace('<script>var a = 1;</script>', ''), 'one script'),
        ('refuses an external script', base_index.replace('<script>', '<script src="x.js">'), 'external script'),
        ('refuses an external stylesheet', base_index.replace('<title>', '<link rel="stylesheet" href="x.css"><title>'), 'external'),
        ('refuses an @import', base_index.replace('fine', '@import url(x)'), 'external'),
        ('refuses a frame', base_index.replace('fine', '<iframe src="x"></iframe>'), 'external'),
    ]
    for pat, snippet in (('fetch(', 'fetch("x")'), ('XMLHttpRequest', 'new XMLHttpRequest()'), ('sendBeacon', 'navigator.sendBeacon("x")'),
                         ('WebSocket', 'new WebSocket("x")'), ('EventSource', 'new EventSource("x")'), ('importScripts', 'importScripts("x")'),
                         ('document.cookie', 'document.cookie = "a=1"'), ('alert(', 'alert("x")'), ('confirm(', 'confirm("x")'), ('prompt(', 'prompt("x")')):
        cases.append(('refuses ' + pat, base_index.replace('var a = 1;', snippet), 'forbidden call'))
    bad = []
    for name, text, want in cases:
        got = probs(text)
        if not any(want in g for g in got):
            bad.append('%s -> %r' % (name, got))
    batch('builder: every bad input is refused with its own message', bad, len(cases))
    ok('builder: a script on the privacy page is refused', any('must not have scripts' in g for g in probs(base_priv.replace('</body>', '<script>1</script></body>'), 'privacy')))
    good = ['https://sanjixysti-creator.github.io/', 'https://sanjixysti-creator.github.io/rinse-quote/', 'https://docs.github.com/site-policy/privacy-policies/github-general-privacy-statement']
    for u in good:
        eq('builder: allows ' + u, probs(base_index.replace('fine', '<a href="%s">x</a>' % u)), [])
    eq('builder: allows the svg namespace name (it is never fetched)', probs(base_index.replace('fine', '<svg xmlns="http://www.w3.org/2000/svg"></svg>')), [])
    # the length rules, with the constants swapped one at a time
    keep = (BG.TITLE, BG.DESC, BG.OG_DESC, BG.OG_ALT)
    try:
        eq('builder: the real text passes check_meta', BG.check_meta(), [])
        BG.TITLE = 'x' * 59
        eq('builder: a 59 character title is fine', BG.check_meta(), [])
        BG.TITLE = 'x' * 60
        ok('builder: a 60 character title is refused', any('title' in m for m in BG.check_meta()))
        BG.TITLE = keep[0]
        for n, good_len in ((60, False), (61, True), (160, True), (161, False)):
            BG.DESC = 'x' * n
            refused = any(m.startswith('description length') for m in BG.check_meta())
            eq('builder: a %d character description is %s' % (n, 'fine' if good_len else 'refused'), refused, not good_len)
        BG.DESC = keep[1]
        BG.OG_DESC = 'x' * 20
        ok('builder: a short og description is refused', any('og description' in m for m in BG.check_meta()))
        BG.OG_DESC = keep[2]
        BG.OG_ALT = 'x' * 10
        ok('builder: a short og alt text is refused', any('alt' in m for m in BG.check_meta()))
        BG.OG_ALT = 'x' * 500
        ok('builder: a very long og alt text is refused', any('alt' in m for m in BG.check_meta()))
    finally:
        BG.TITLE, BG.DESC, BG.OG_DESC, BG.OG_ALT = keep
    eq('builder: constants are restored', BG.check_meta(), [])
    ok('builder: the title is under 60 characters', len(BG.TITLE) < 60, len(BG.TITLE))
    ok('builder: the description is 61 to 160 characters', 60 < len(BG.DESC) <= 160, len(BG.DESC))
    ok('builder: no dash characters in any builder text', not any(c in (BG.TITLE + BG.DESC + BG.OG_DESC + BG.OG_ALT) for c in DASHES))
    tile = BG.hub_tile()
    ok('builder: the hub tile is the brand ground plus the same art as the favicon',
       tile[0] == '#A21CAF' and tile[1] == BG.MARK_ON_BRAND and tile[1].startswith('<g transform="translate(1.9 2.1) scale(.9)">'))
    ok('builder: the tile art stays inside the 40 x 40 box', all(0 <= float(n) <= 40 for n in re.findall(r'(?:cx|cy)="([\d.]+)"', tile[1])))
    fav = base64.b64decode(BG.favicon_data_uri().split(',', 1)[1]).decode('ascii')
    ok('builder: the favicon is the tile on a rounded brand square',
       fav.startswith('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40">') and 'rx="9"' in fav and 'fill="#A21CAF"' in fav and BG.MARK_ON_BRAND in fav)
    if STANDALONE:
        # the built files are exactly what the builder makes from the fragment right now (nothing stale, nothing hand edited)
        fresh = BG.build_index()
        ok('builder: index.html on disk equals a fresh build of the fragment', fresh == BUILT_TEXT, 'sizes %d vs %d' % (len(fresh), len(BUILT_TEXT)))
        support = re.search(r"var SUPPORT = '([^']+)';", fresh).group(1)
        priv = (BUILT.parent / 'privacy.html').read_text(encoding='utf-8')
        fresh_priv = BG.build_privacy(support)
        ok('builder: privacy.html on disk equals a fresh build', fresh_priv == priv, 'sizes %d vs %d' % (len(fresh_priv), len(priv)))


# ================================================================== meta: built page, privacy page, images
def tags(text, name):
    out = []
    for m in re.finditer(r'<%s\b([^>]*)>' % name, text):
        out.append(dict((a, htmllib.unescape(v)) for a, v in re.findall(r'([a-zA-Z:-]+)="([^"]*)"', m.group(1))))
    return out


def lum_of(im, box):
    return ImageStat.Stat(im.crop(box).convert('L')).mean[0]


def white_count(im, box, thr):
    from PIL import ImageChops
    r, g, b = im.crop(box).convert('RGB').split()
    low = ImageChops.darker(ImageChops.darker(r, g), b)
    return sum(low.histogram()[thr:])


def t_meta():
    if not STANDALONE:
        return
    t = BUILT_TEXT
    head = t.split('</head>')[0]
    M, L = tags(head, 'meta'), tags(head, 'link')

    def meta(key, media=None):
        for d in M:
            if (d.get('name') == key or d.get('property') == key) and (media is None or d.get('media') == media):
                return d.get('content')
        return None
    title = htmllib.unescape(re.search(r'<title>(.*?)</title>', head, re.S).group(1))
    eq('meta: title is the builder title', title, BG.TITLE)
    ok('meta: title is under 60 characters', len(title) < 60, len(title))
    ok('meta: title names the game and says what it is', 'Grime Time' in title and 'pressure washing' in title.lower() and 'free' in title.lower())
    d = meta('description')
    eq('meta: description is the builder description', d, BG.DESC)
    ok('meta: description is 61 to 160 characters', d is not None and 60 < len(d) <= 160, len(d or ''))
    eq('meta: canonical address', [x.get('href') for x in L if x.get('rel') == 'canonical'], [SITE_URL])
    eq('meta: theme colour in light', meta('theme-color', '(prefers-color-scheme: light)'), '#F5F1F9')
    eq('meta: theme colour in dark', meta('theme-color', '(prefers-color-scheme: dark)'), '#120A1D')
    vp = meta('viewport')
    ok('meta: viewport allows zoom', vp is not None and 'width=device-width' in vp and 'user-scalable' not in vp and 'maximum-scale' not in vp, vp)
    ok('meta: html lang is en', '<html lang="en">' in t)
    for key, want in (('og:type', 'website'), ('og:site_name', 'Grime Time'), ('og:title', BG.TITLE), ('og:description', BG.OG_DESC), ('og:url', SITE_URL),
                      ('og:image', SITE_URL + 'og.png'), ('og:image:type', 'image/png'), ('og:image:width', '1200'), ('og:image:height', '630'),
                      ('og:image:alt', BG.OG_ALT), ('twitter:card', 'summary_large_image'), ('twitter:title', BG.TITLE), ('twitter:description', BG.OG_DESC),
                      ('twitter:image', SITE_URL + 'og.png'), ('twitter:image:alt', BG.OG_ALT)):
        eq('meta: ' + key, meta(key), want)
    ok('meta: og description is 61 to 200 characters', 60 < len(BG.OG_DESC) <= 200)
    icons = [x for x in L if x.get('rel') == 'icon']
    ok('meta: an inline svg favicon', len(icons) == 1 and icons[0].get('href', '').startswith('data:image/svg+xml;base64,'))
    if icons:
        svg = base64.b64decode(icons[0]['href'].split(',', 1)[1]).decode('ascii')
        ok('meta: the favicon is the hub tile art on the brand ground', BG.MARK_ON_BRAND in svg and 'fill="#A21CAF"' in svg)
    eq('meta: apple touch icon link', [x.get('href') for x in L if x.get('rel') == 'apple-touch-icon'], ['apple-touch-icon.png'])
    # the images
    og, ti = BUILT.parent / 'og.png', BUILT.parent / 'apple-touch-icon.png'
    ok('images: og.png exists', og.exists())
    ok('images: apple-touch-icon.png exists', ti.exists())
    if og.exists():
        eq('images: og.png is 1200 x 630', png_size(og), (1200, 630))
        ok('images: og.png is under 450 KB', og.stat().st_size < 450 * 1024, og.stat().st_size)
        im = Image.open(og).convert('RGB')
        ok('images: og.png is not blank', ImageStat.Stat(im.convert('L')).stddev[0] > 30)
        ok('images: og.png has the name in white on the left', white_count(im, (60, 215, 540, 330), 240) > 5000, white_count(im, (60, 215, 540, 330), 240))
        ok('images: og.png has the tagline and the pill on the left', white_count(im, (60, 350, 420, 440), 230) > 1500 and white_count(im, (60, 460, 500, 520), 240) > 5000)
        ok('images: og.png shows the spray flare and sparkles in the screenshot', white_count(im, (860, 250, 1020, 420), 248) > 80, white_count(im, (860, 250, 1020, 420), 248))
        ok('images: og.png shows a half clean surface (clean side brighter than the grimy side)', lum_of(im, (650, 200, 760, 440)) > lum_of(im, (1040, 200, 1150, 440)) + 8)
        px = im.getpixel((10, 10))
        ok('images: og.png sits on the brand colour', 120 < px[0] < 210 and px[1] < 60 and 130 < px[2] < 230, px)
    if ti.exists():
        eq('images: apple-touch-icon.png is 180 x 180', png_size(ti), (180, 180))
        ok('images: apple-touch-icon.png is under 40 KB', ti.stat().st_size < 40 * 1024, ti.stat().st_size)
        ic = Image.open(ti).convert('RGB')
        ok('images: the touch icon has a white spray fan on a fuchsia ground', white_count(ic, (60, 10, 170, 110), 240) > 400 and ic.getpixel((5, 5))[1] < 60, white_count(ic, (60, 10, 170, 110), 240))
    # landmarks, footer links, noscript
    eq('landmarks: one h1', len(re.findall(r'<h1[ >]', t)), 1)
    eq('landmarks: one header, one main, one footer', (t.count('<header'), t.count('<main'), t.count('<footer')), (1, 1, 1))
    ok('landmarks: a noscript message', '<noscript>' in t and 'needs JavaScript' in t)
    for u in ('https://sanjixysti-creator.github.io/', 'https://sanjixysti-creator.github.io/rinse-quote/'):
        ok('footer links to ' + u, 'href="%s"' % u in t)
    ok('footer: privacy link and maker line', 'Made by Xysti Software. <a href="privacy.html">Privacy</a>' in t)
    ok('footer: support mailto link', 'href="mailto:fireseabrook2566@gmail.com"' in t)
    ok('footer: the Copy button still exists', 'class="linkish mail-copy"' in t)
    # privacy page text
    pv = (BUILT.parent / 'privacy.html').read_text(encoding='utf-8')
    low = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', pv).lower())
    eq('privacy: one h1', len(re.findall(r'<h1[ >]', pv)), 1)
    ok('privacy: no scripts', '<script' not in pv)
    for phrase in ('saved only in this browser', 'nothing is sent anywhere', 'no cookies', 'no ads', 'the sound is made by the page itself', 'no analytics', 'local storage',
                   'export save', 'github pages', 'last updated'):
        has('privacy says: ' + phrase, low, phrase)
    ok('privacy: links back to the game', 'href="./"' in pv)
    ok('privacy: canonical address', '<link rel="canonical" href="%sprivacy.html">' % SITE_URL in pv)
    ok('privacy: contact is the support mailto', 'mailto:fireseabrook2566@gmail.com' in pv)
    eq('privacy: the font faces are embedded', pv.count('url(data:font/woff2;base64,'), len(PRIVACY_FONTS))
    ok('privacy: title names the game', '<title>Privacy Policy - Grime Time</title>' in pv)
    # the page really renders: fonts loaded, no overflow, contrast, both schemes, phone and desktop
    for (w, h, scheme) in ((320, 568, 'light'), (320, 568, 'dark'), (1280, 800, 'light'), (1280, 800, 'dark')):
        ctx, pg, logs = new_page(w, h, scheme, 1, w < 700, hash='', path=BLANK_PATH, tag='privacy %dx%d %s' % (w, h, scheme))
        pg.add_script_tag(content=CONTRAST_JS)
        pg.evaluate('document.fonts.ready')
        over = pg.evaluate('()=>document.documentElement.scrollWidth-innerWidth')
        ok('privacy %dx%d %s: no horizontal overflow' % (w, h, scheme), over <= 0, over)
        fonts = pg.evaluate("()=>[...document.fonts].filter(f=>f.status==='loaded').map(f=>f.family.replace(/['\"]/g,''))")
        ok('privacy %dx%d %s: embedded fonts load' % (w, h, scheme), 'Big Shoulders Display' in fonts and 'Public Sans' in fonts, fonts)
        rows = pg.evaluate("()=>window.__contrast('body','rgb(255,255,255)')")
        low_rows = [r for r in rows if r['cr'] < r['need']]
        ok('privacy %dx%d %s: text contrast (%d elements)' % (w, h, scheme, len(rows)), len(rows) > 20 and not low_rows, low_rows[:3])
        ok('privacy %dx%d %s: console clean' % (w, h, scheme), not logs, logs)
        close(ctx)
    # alt text against what the game really shows at the moment the picture was taken
    import build_images_grime as BI
    ctx, pg, logs = new_page(BI.PANEL_VIEWPORT[0], BI.PANEL_VIEWPORT[1], 'light', 1, False, tag='og scene')
    pg.evaluate('document.fonts.ready')
    pg.evaluate(BI.STATE)
    pg.evaluate('(j)=>window.__grime.start(j)', BI.JOB)
    pg.wait_for_timeout(500)
    pg.evaluate(BI.WASH_A)
    pg.wait_for_timeout(300)
    pg.evaluate(BI.WASH_B)
    facts = pg.evaluate(BI.FACTS)
    ok('og scene: console clean', not logs, logs)
    close(ctx)
    alt = BG.OG_ALT.lower()
    job_name = [j for j in pure_data()['jobs'] if j['id'] == BI.JOB][0]['name']
    eq('alt text: the scene job is named as the game names it', facts['job'], job_name)
    has('alt text names the job in the picture', alt, facts['job'].lower())
    has('alt text names the spray colour in the picture', alt, facts['tip'] + ' spray')
    pct = int(re.search(r'\d+', facts['pct']).group(0))
    ok('alt text: the picture is mid wash (about half clean)', 40 <= pct <= 60, facts['pct'])
    has('alt text says about half washed', alt, 'about half washed')
    has('alt text carries the tagline printed on the picture', BG.OG_ALT, 'Blast the grime. Build the business.')
    has('og description matches the pill on the picture', BG.OG_DESC.lower(), 'free pressure washing game')
    ok('alt text mentions what shows: clean pavers, grime, sparkles', all(w in alt for w in ('clean pavers', 'grime', 'sparkles')))


# ================================================================== math: the economy against an independent exact reference
_DATA = {}


def pure_data():
    if not _DATA:
        _DATA.update(node('data')['DATA'])
    return _DATA


def F(x):
    """Exact decimal value of a number written in the data table (0.12 means 12/100, not the nearest binary double)."""
    return Fraction(repr(x)) if isinstance(x, float) else Fraction(x)


def X(x):
    """Exact value of a double the page really holds."""
    return Fraction(x)


def floor_f(v):
    return v.numerator // v.denominator


def ceil_f(v):
    return -((-v.numerator) // v.denominator)


def clampf(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)


def rclose(got, want, tol=1e-12):
    if isinstance(got, bool) or not isinstance(got, (int, float)) or got != got or got in (float('inf'), float('-inf')):
        return False
    return abs(Fraction(got) - want) <= Fraction(tol) * max(Fraction(1), abs(want))


EPS_COST = Fraction(1, 10 ** 9)     # the page's costAt takes 1e-9 off before rounding up, so double dust never adds a dollar to an exact price


def r_cost(base, growth, n):
    """The exact price: ceil(base * growth^n - 1e-9) with the growth as written in the data table."""
    return ceil_f(F(base) * F(growth) ** n - EPS_COST)


def cost_range(base, growth, n):
    """Every price a correct double evaluation may show. The page stores 1.15 as the nearest double and multiplies in doubles, so a price near 1e13 can sit
    one dollar either side of the exact one. The width is the relative rounding error (n + 5) * 1e-16; for prices under a billion it is a few billionths of a dollar."""
    x = F(base) * F(growth) ** n
    w = Fraction(n + 5, 10 ** 16)
    return ceil_f(x * (1 - w) - EPS_COST), ceil_f(x * (1 + w) - EPS_COST)


def in_range(got, lo, hi):
    if isinstance(got, bool) or not isinstance(got, (int, float)) or got != got or abs(got) == float('inf'):
        return False
    return lo <= Fraction(got) <= hi


FLOW_REF = 2     # the flow multiplier at which the tip bonus is full (a constant in the page, not in the data table)
M32 = 0xFFFFFFFF
SUF = ['', 'K', 'M', 'B', 'T', 'Qa', 'Qi']


def trim0(s):
    return s.rstrip('0').rstrip('.') if '.' in s else s


def ref_big(v):
    if v < 0:
        return '-' + ref_big(-v)
    if v < 1000:
        return str(floor_f(v))
    if v >= 10 ** 21:
        e = len(str(floor_f(v))) - 1
        q = floor_f(v / Fraction(10) ** (e - 2))
        return trim0('%d.%02d' % (q // 100, q % 100)) + 'e' + str(e)
    tier = 1
    while tier < 6 and v >= Fraction(1000) ** (tier + 1):
        tier += 1
    x = v / Fraction(1000) ** tier
    dec = 2 if x < 10 else (1 if x < 100 else 0)
    qq = floor_f(v / Fraction(10) ** (3 * tier - dec))
    s = str(qq // 10 ** dec) + (('.' + str(qq % 10 ** dec).zfill(dec)) if dec else '')
    return trim0(s) + SUF[tier]


def ref_money(v):
    return '-$' + ref_big(-v) if v < 0 else '$' + ref_big(v)


def ref_rate(v):
    if v < 0:
        v = Fraction(0)
    if v < 1000:
        q = floor_f(v * 10)
        return '$' + trim0('%d.%d' % (q // 10, q % 10)) + '/s'
    return '$' + ref_big(v) + '/s'


def ref_dur(sec):
    if sec != sec or sec < 0:
        sec = 0
    sec = int(math.floor(sec))
    if sec < 60:
        return '%d s' % sec
    m, s = sec // 60, sec % 60
    if sec < 3600:
        return '%d min' % m + (' %d s' % s if s else '')
    h, mm = sec // 3600, (sec % 3600) // 60
    return '%d h' % h + (' %d min' % mm if mm else '')


def accept(fn, v):
    """Strings a correct page may show: the exact one, and the neighbours when a double lands a hair either side of a rounding boundary."""
    eps = Fraction(1, 10 ** 9)
    return {fn(v), fn(v * (1 - eps)), fn(v * (1 + eps))}


def py_mulberry32(a):
    a &= M32

    def nxt():
        nonlocal a
        a = (a + 0x6D2B79F5) & M32
        t = a
        t = ((t ^ (t >> 15)) * (t | 1)) & M32
        t = t ^ ((t + (((t ^ (t >> 7)) * (t | 61)) & M32)) & M32)
        return ((t ^ (t >> 14)) & M32) / 4294967296.0
    return nxt


def imul(a, b):
    return (a * b) & M32


def py_hash2(x, y, s):
    h = (imul(x & M32, 374761393) + imul(y & M32, 668265263) + imul(s & M32, 1013904223)) & M32
    h = imul(h ^ (h >> 13), 1274126177)
    h ^= h >> 16
    return (h & M32) / 4294967296.0


def py_vnoise(x, y, s):
    xi, yi = math.floor(x), math.floor(y)
    fx, fy = x - xi, y - yi
    fx = fx * fx * (3 - 2 * fx)
    fy = fy * fy * (3 - 2 * fy)
    a, b, c, d = py_hash2(xi, yi, s), py_hash2(xi + 1, yi, s), py_hash2(xi, yi + 1, s), py_hash2(xi + 1, yi + 1, s)
    return a + (b - a) * fx + (c - a) * fy + (a - b - c + d) * fx * fy


def py_fbm(x, y, s, octs):
    v, amp, tot, f = 0.0, 0.5, 0.0, 1
    for o in range(octs):
        v += amp * py_vnoise(x * f, y * f, s + o * 101)
        tot += amp
        amp *= 0.5
        f *= 2
    return v / tot


def t_math():
    D = pure_data()
    rng = random.Random(20261002)
    W = D['wash']
    FR = D['franchise']
    # ---- balance snapshot: the numbers the pacing was agreed on. Change them on purpose, together with the pacing ranges below.
    eq('snapshot: jobs', [j['id'] for j in D['jobs']], ['driveway', 'patio', 'fence', 'wall', 'deck', 'garage', 'siding', 'car'])
    eq('snapshot: job pay', [j['pay'] for j in D['jobs']], [28, 70, 100, 250, 420, 950, 2100, 4800])
    eq('snapshot: star gates', [j['stars'] for j in D['jobs']], [0, 2, 4, 7, 10, 13, 16, 19])
    eq('snapshot: job par times', [j['par'] for j in D['jobs']], [40, 60, 75, 90, 100, 110, 125, 130])
    eq('snapshot: delicate jobs', [j['id'] for j in D['jobs'] if j['delicate']], ['fence', 'deck', 'siding', 'car'])
    eq('snapshot: gear needed by jobs', {j['id']: j['gear'] for j in D['jobs'] if j['gear']}, {'siding': ['pole'], 'car': ['soap']})
    eq('snapshot: gear costs', [(g['id'], g['cost']) for g in D['gear']], [('soap', 350), ('hot', 2400), ('pole', 3800), ('surface', 6500)])
    eq('snapshot: upgrades', [(u['id'], u['max'], u['base'], u['growth'], u['per']) for u in D['upgrades']],
       [('pressure', 10, 30, 1.9, 0.18), ('area', 10, 48, 1.85, 0.1), ('tank', 8, 90, 1.95, 0.35), ('reach', 8, 130, 2.05, 0.05), ('flow', 5, 220, 2.2, 0.1)])
    eq('snapshot: crew', [(c['id'], c['base'], c['inc']) for c in D['crew']],
       [('apprentice', 120, 0.4), ('tech', 1100, 2.4), ('foreman', 13000, 16), ('manager', 160000, 105), ('boss', 2100000, 720), ('director', 28000000, 4800)])
    eq('snapshot: crew growth and milestones', (D['crewGrowth'], D['crewMilestones']), (1.15, [10, 25, 50, 100, 200]))
    eq('snapshot: trucks', D['trucks'], {'base': 5000, 'growth': 2.2, 'max': 8})
    eq('snapshot: offline pay', D['offline'], {'baseHours': 4, 'perTruck': 1, 'maxHours': 12, 'efficiency': 1})
    eq('snapshot: franchise', (FR['fpDiv'], FR['minGain'], FR['minGainStep'], FR['perPoint']), (50000, 8, 0, 0.12))
    eq('snapshot: rig colours', [(c['id'], c['fp']) for c in FR['colors']], [('sun', 0), ('teal', 6), ('flame', 15), ('violet', 30), ('chrome', 60), ('gold', 120)])
    eq('snapshot: hardness bands', [(b['id'], b['top'], b['h']) for b in D['bands']], [('film', 70, 18), ('grime', 160, 42), ('caked', 255, 82)])
    eq('snapshot: special kinds', [(k['id'], k['h']) for k in D['kinds']], [('none', 0), ('oil', 62), ('moss', 44), ('graffiti', 78), ('bird', 30), ('mildew', 36)])
    eq('snapshot: tips', [(t['id'], t['deg'], t['p'], t['r']) for t in D['tips']],
       [('red', 0, 135, 0.24), ('yellow', 15, 68, 0.46), ('green', 25, 44, 0.72), ('white', 40, 28, 1), ('soap', 65, 12, 1.05)])
    eq('snapshot: a job is done at 96 percent, star two needs 70 percent by hand', (W['doneAt'], D['stars']['toughNeeded']), (0.96, 0.7))
    eq('snapshot: pay shares and scuff limits', (W['cleanShare'], W['tipShare'], W['scuffEach'], W['scuffMax']), (0.25, 0.4, 0.004, 0.35))

    # ---- cost curves
    calls, refs = [], []
    for u in D['upgrades']:
        for n in range(0, u['max'] + 3):
            calls.append(('upgradeCost', [u['id'], n]))
            refs.append(cost_range(u['base'], u['growth'], n))
    for c in D['crew']:
        for n in list(range(0, 260)) + [300, 400, 500, 750, 1000]:
            calls.append(('crewCost', [c['id'], n]))
            refs.append(cost_range(c['base'], D['crewGrowth'], n))
    for n in range(0, D['trucks']['max'] + 3):
        calls.append(('truckCost', [n]))
        refs.append(cost_range(D['trucks']['base'], D['trucks']['growth'], n))
    got = rpc(calls)
    batch('math: upgrade, crew and truck cost curves equal the exact ceil(base * growth^n) (only double rounding above a trillion may differ)',
          ['%s%s: %r vs %r' % (c[0], c[1], g, r) for c, g, r in zip(calls, got, refs) if not in_range(g, *r)], len(calls))
    ok('math: below a million dollars every price is exact (no tolerance used)', all(r[0] == r[1] for r in refs if r[1] < 10 ** 6) and sum(1 for r in refs if r[1] < 10 ** 6) > 100)
    ok('math: a price that sits on a whole dollar stays there (120 x 1.15 is 138, not 139)', rpc([('crewCost', ['apprentice', 1])])[0] == 138)
    for u in D['upgrades']:
        costs = [r_cost(u['base'], u['growth'], n) for n in range(u['max'] + 1)]
        ok('math: %s costs rise at every level' % u['id'], all(a < b for a, b in zip(costs, costs[1:])))
    for c in D['crew']:
        costs = [r_cost(c['base'], D['crewGrowth'], n) for n in range(120)]
        ok('math: %s costs rise with every hire' % c['id'], all(a < b for a, b in zip(costs, costs[1:])))
    ok('math: the first hire of each crew tier costs its base', all(r_cost(c['base'], D['crewGrowth'], 0) == c['base'] for c in D['crew']))
    # bulk buying
    calls, refs = [], []
    for _ in range(300):
        c = rng.choice(D['crew'])
        owned = rng.choice([0, 0, 1, 5, 9, 10, 24, 25, 49, 50, 99, 100, 199, 200]) + rng.randint(0, 3)
        k = rng.randint(0, 40)
        calls.append(('crewCostMany', [c['id'], owned, k]))
        rs = [cost_range(c['base'], D['crewGrowth'], owned + i) for i in range(k)]
        w = Fraction(k + 2, 10 ** 16)          # adding k doubles one after the other
        lo, hi = sum(r[0] for r in rs), sum(r[1] for r in rs)
        refs.append((floor_f(lo * (1 - w)), ceil_f(hi * (1 + w))))
    got = rpc(calls)
    batch('math: buying k hires costs the sum of the single costs', ['%s: %r vs %r' % (c[1], g, r) for c, g, r in zip(calls, got, refs) if not in_range(g, *r)], len(calls))
    calls, refs = [], []
    for _ in range(300):
        c = rng.choice(D['crew'])
        owned = rng.choice([0, 0, 1, 5, 9, 10, 24, 25, 49, 50, 99, 100, 199, 200]) + rng.randint(0, 3)
        money = rng.choice([0, 1, int(10 ** rng.uniform(0, 12)), int(10 ** rng.uniform(0, 12)), rng.randint(0, 5000)])
        k, t = 0, 0
        while k < 1000:
            cost = r_cost(c['base'], D['crewGrowth'], owned + k)
            if t + cost > money:
                break
            t += cost
            k += 1
        calls.append(('crewAfford', [c['id'], owned, money]))
        refs.append(k)
    got = rpc(calls)
    batch('math: "buy max" counts exactly the hires the cash can pay for', ['%s: %r vs %r' % (c[1], g, r) for c, g, r in zip(calls, got, refs) if g != r], len(calls))

    # ---- crew income, milestones, franchise multiplier
    def r_ms(n):
        return sum(1 for m in D['crewMilestones'] if n >= m)

    def r_mult(fp):
        return 1 + F(FR['perPoint']) * max(0, fp)

    def r_tier(c, n, fp):
        return F(n) * F(c['inc']) * 2 ** r_ms(n) * r_mult(fp)

    def r_income(crew, fp):
        return sum((r_tier(c, crew.get(c['id'], 0), fp) for c in D['crew']), Fraction(0))
    calls, refs = [], []
    counts = [0, 0, 1, 2, 7, 9, 10, 11, 24, 25, 26, 49, 50, 51, 99, 100, 101, 199, 200, 201, 500, 100000]
    for _ in range(400):
        crew = {c['id']: rng.choice(counts) for c in D['crew']}
        fp = rng.choice([0, 0, 1, 2, 7, 8, 25, 100, 1000])
        s = {'crew': crew, 'fp': fp}
        calls.append(('crewIncome', [s]))
        refs.append(r_income(crew, fp))
        calls.append(('crewRawIncome', [s]))
        refs.append(r_income(crew, 0))
        c = rng.choice(D['crew'])
        calls.append(('tierIncome', [s, c['id']]))
        refs.append(r_tier(c, crew[c['id']], fp))
    got = rpc(calls)
    batch('math: crew income, raw income and tier income equal the exact sum with doubling milestones and the franchise bonus',
          ['%s: %r vs %s' % (c[0], g, float(r)) for c, g, r in zip(calls, got, refs) if not rclose(g, r)], len(calls))
    calls = [('milestoneCount', [n]) for n in range(0, 260)] + [('nextMilestone', [n]) for n in range(0, 260)] + [('franchiseMult', [fp]) for fp in range(0, 200)]
    got = rpc(calls)
    bad = []
    for c, g in zip(calls, got):
        if c[0] == 'milestoneCount':
            want = r_ms(c[1][0])
        elif c[0] == 'nextMilestone':
            want = next((m for m in D['crewMilestones'] if c[1][0] < m), 0)
        else:
            want = r_mult(c[1][0])
        if not (g == want if c[0] != 'franchiseMult' else rclose(g, want)):
            bad.append('%s%s: %r vs %r' % (c[0], c[1], g, want))
    batch('math: milestone counts, next milestones and the franchise multiplier', bad, len(calls))
    got = rpc([('franchiseMult', [-5]), ('franchiseMult', [None]), ('tierIncome', [{'crew': {}, 'fp': 3}, 'tech'])])
    eq('math: a negative or missing franchise level counts as zero', got, [1, 1, 0])

    # ---- offline credit: cap, trucks, backwards clock, nonsense
    def r_off(s, now):
        last = s['savedAt']
        fin = isinstance(now, (int, float)) and now == now and abs(now) != float('inf')
        if not (last > 0) or not fin or now < last:
            return {'secs': 0, 'raw': 0, 'capped': False, 'earned': 0, 'backwards': bool(fin and last > 0 and now < last)}
        raw = Fraction(int(now) - int(last), 1000) if float(now).is_integer() else (X(now) - X(last)) / 1000
        cap = min(F(D['offline']['maxHours']), F(D['offline']['baseHours']) + F(D['offline']['perTruck']) * max(0, s['trucks'])) * 3600
        secs = min(raw, cap)
        return {'secs': secs, 'raw': raw, 'capped': raw > cap, 'earned': secs * r_income(s['crew'], s['fp']) * F(D['offline']['efficiency']), 'backwards': False}
    calls, refs = [], []
    base_t = 1790000000000
    for _ in range(700):
        crew = {c['id']: rng.choice(counts[:-1]) for c in D['crew']}
        s = {'crew': crew, 'fp': rng.choice([0, 0, 3, 8, 40]), 'trucks': rng.choice([0, 0, 1, 2, 4, 7, 8, 9, 20]), 'savedAt': base_t + rng.randint(0, 10 ** 9)}
        cap_ms = min(12, 4 + max(0, s['trucks'])) * 3600 * 1000
        delta = rng.choice([-5000, -1, 0, 1, 999, 59999, 60000, 60001, int(10 ** rng.uniform(3, 9)), cap_ms - 1, cap_ms, cap_ms + 1, cap_ms * 2, cap_ms * 50, 10 ** 12])
        now = s['savedAt'] + delta
        calls.append(('offlineCredit', [s, now]))
        refs.append(r_off(s, now))
    for s_at in (0, -1, None):
        for now in (base_t, '$num:NaN', '$num:Infinity'):
            s = {'crew': {'apprentice': 50}, 'fp': 0, 'trucks': 0, 'savedAt': s_at}
            calls.append(('offlineCredit', [s, now]))
            refs.append(r_off({'crew': s['crew'], 'fp': 0, 'trucks': 0, 'savedAt': s_at if s_at is not None else 0}, float('nan') if now == '$num:NaN' else (float('inf') if now == '$num:Infinity' else now)))
    s = {'crew': {'apprentice': 50}, 'fp': 0, 'trucks': 0, 'savedAt': base_t}
    for now in ('$num:NaN', '$num:Infinity'):
        calls.append(('offlineCredit', [s, now]))
        refs.append(r_off(s, float('nan') if now == '$num:NaN' else float('inf')))
    got = rpc(calls)
    bad = []
    for c, g, r in zip(calls, got, refs):
        good = (g['capped'] == r['capped'] and g['backwards'] == r['backwards'] and rclose(g['secs'], Fraction(r['secs'])) and rclose(g['raw'], Fraction(r['raw']))
                and rclose(g['earned'], Fraction(r['earned']), 1e-12))
        if not good:
            bad.append('%s now %r: %r vs %r' % (c[1][0]['savedAt'], c[1][1], g, {k: (float(v) if isinstance(v, Fraction) else v) for k, v in r.items()}))
    batch('math: offline credit equals the exact time capped at 4 h plus 1 h a truck (max 12 h) times income; a clock that went backwards pays nothing', bad, len(calls))
    offs = rpc([('offlineCapSec', [{'trucks': n}]) for n in range(-2, 14)])
    eq('math: the away cap in seconds for 0 to 8 trucks and beyond', offs, [min(12, 4 + max(0, n)) * 3600 for n in range(-2, 14)])
    one = rpc([('offlineCredit', [{'crew': {'apprentice': 10}, 'fp': 0, 'trucks': 0, 'savedAt': 1000}, 1000 + 3600 * 1000])])[0]
    near('math: one hour with ten apprentices at 4 dollars a second pays 14400 dollars... (10 x 0.4 x 2 doubling = 8 a second)', one['earned'], 8 * 3600, 1e-6)
    back = rpc([('offlineCredit', [{'crew': {'apprentice': 10}, 'fp': 0, 'trucks': 0, 'savedAt': 2000}, 1000])])[0]
    ok('math: a backwards clock is flagged and pays exactly nothing', back['backwards'] is True and back['earned'] == 0 and back['secs'] == 0)

    # ---- franchise
    def r_gain(lifetime):
        return math.isqrt(floor_f(X(max(0, lifetime)) / FR['fpDiv']))
    lifes = [0, 1, 49999, 50000, 99999, 199999, 200000, 449999, 450000, 3217628.35, 4.2e6, 5e7, 1e9, 1e12]
    for k in list(range(1, 300)) + [1000, 5000, 20000, 100000]:
        lifes += [FR['fpDiv'] * k * k - 1, FR['fpDiv'] * k * k, FR['fpDiv'] * k * k + 1]
    lifes += [10 ** rng.uniform(0, 15) for _ in range(300)]
    got = rpc([('fpGain', [x]) for x in lifes])
    batch('math: Franchise points are floor(sqrt(lifetime / 50000)), exactly, including every perfect square boundary', ['%r: %r vs %r' % (x, g, r_gain(x)) for x, g in zip(lifes, got) if g != r_gain(x)], len(lifes))
    big = [1e18, 1e21, 1e24, 1e27, 1e30, 3.7e29]
    got = rpc([('fpGain', [x]) for x in big])
    batch('math: Franchise points for huge lifetimes are within 1 of the exact value', ['%r' % x for x, g in zip(big, got) if abs(g - r_gain(x)) > 1], len(big))
    calls = []
    states = []
    for _ in range(300):
        s = {'lifetime': rng.choice([0, 49999, 400000, 1e6, 3.2e6, 1e8, 5e9]) + rng.randint(0, 5000), 'fp': rng.choice([0, 3, 8, 25]), 'cycles': rng.choice([0, 1, 2, 9])}
        states.append(s)
        calls.append(('franchiseOffer', [s]))
        calls.append(('franchiseNeed', [s]))
    got = rpc(calls)
    bad = []
    for i, s in enumerate(states):
        gain = r_gain(s['lifetime'])
        need = FR['minGain'] + FR['minGainStep'] * s['cycles']
        want = {'gain': gain, 'need': need, 'can': gain >= need, 'total': s['fp'] + gain}
        if got[2 * i] != want or got[2 * i + 1] != need:
            bad.append('%r: %r vs %r' % (s, got[2 * i], want))
    batch('math: the Franchise offer (gain, need, can, total) and the points needed', bad, len(states))
    fresh = rpc([('freshState', [])])[0]
    exp_fresh = {'v': 1, 'money': 0, 'lifetime': 0, 'earned': 0, 'stars': {}, 'up': {u['id']: 0 for u in D['upgrades']}, 'gear': {g['id']: False for g in D['gear']},
                 'crew': {c['id']: 0 for c in D['crew']}, 'trucks': 0, 'fp': 0, 'cycles': 0, 'color': 'sun', 'savedAt': 0, 'tut': False, 'jobs': 0, 'set': {'sound': True, 'calm': False}}
    eq('math: a fresh game has exactly these fields', fresh, exp_fresh)
    calls, refs = [], []
    for _ in range(200):
        s = json.loads(json.dumps(exp_fresh))
        s.update(money=round(rng.uniform(0, 1e7), 2), lifetime=rng.choice([1e5, 3.2e6, 8e7]) + rng.randint(0, 99999), earned=rng.randint(0, 10 ** 9), fp=rng.choice([0, 5, 9, 30]),
                 cycles=rng.choice([0, 1, 4]), color=rng.choice(['sun', 'teal']), savedAt=base_t + rng.randint(0, 10 ** 6), jobs=rng.randint(0, 500), tut=rng.choice([True, False]))
        s['stars'] = {j['id']: rng.randint(1, 3) for j in D['jobs'] if rng.random() < 0.7}
        s['up'] = {u['id']: rng.randint(0, u['max']) for u in D['upgrades']}
        s['gear'] = {g['id']: rng.random() < 0.5 for g in D['gear']}
        s['crew'] = {c['id']: rng.randint(0, 60) for c in D['crew']}
        s['trucks'] = rng.randint(0, 8)
        s['set'] = {'sound': rng.choice([True, False]), 'calm': rng.choice([True, False])}
        want = json.loads(json.dumps(exp_fresh))
        want.update(stars=dict(s['stars']), fp=s['fp'] + r_gain(s['lifetime']), cycles=s['cycles'] + 1, color=s['color'], earned=s['earned'], jobs=s['jobs'], tut=True,
                    set=dict(s['set']), savedAt=s['savedAt'])
        calls.append(('applyFranchise', [s]))
        refs.append(want)
    got = rpc(calls)
    batch('math: a Franchise resets cash, rig, gear, crew and trucks and keeps stars, points, colour, history and settings', ['%r vs %r' % (g, r) for g, r in zip(got, refs) if g != r], len(calls))
    cols = rpc([('rigColors', [fp]) for fp in (0, 5, 6, 14, 15, 29, 30, 59, 60, 119, 120, 500)])
    eq('math: rig colours unlock at 0, 6, 15, 30, 60 and 120 points', [len(c) for c in cols], [1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6])

    # ---- payout and stars
    def r_payout(job, res, fp):
        return ref_payout(D, job, res, fp)
    calls, refs = [], []
    for _ in range(900):
        job = rng.choice(D['jobs'])
        fp = rng.choice([0, 0, 1, 2, 5, 8, 16, 40, 250])
        res = {'tough': round(rng.uniform(-0.2, 1.3), 3), 'flow': round(rng.uniform(0.8, 3.0), 3), 'penalty': round(rng.uniform(-0.1, 0.6), 3), 'secs': round(rng.uniform(5, 400), 2)}
        if rng.random() < 0.2:
            res.update(tough=rng.choice([0, 1, 0.7, 0.5]), flow=rng.choice([1, 2, 1.5]), penalty=rng.choice([0, 0.35, 0.004]))
        calls.append(('payout', [{'$job': job['id']}, res, {'fp': fp}]))
        refs.append(r_payout(job, res, fp))
    got = rpc(calls)
    batch('math: job pay (base, cleanliness bonus, flow tips, damage, total) equals the exact floor arithmetic', ['%s: %r vs %r' % (c[1][1], g, r) for c, g, r in zip(calls, got, refs) if g != r], len(calls))
    ok('math: a perfect run pays base + 25 percent + 40 percent', r_payout(D['jobs'][0], {'tough': 1, 'flow': 2, 'penalty': 0}, 0)['total'] == 28 + 7 + 11)
    calls, refs = [], []
    for _ in range(500):
        job = rng.choice(D['jobs'])
        res = {'tough': rng.choice([0, 0.69, 0.699, 0.7, 0.701, 1, round(rng.uniform(0, 1), 3)]), 'penalty': rng.choice([0, 0, 0.004, 0.008, -0.1]),
               'secs': rng.choice([job['par'] - 1, job['par'], job['par'] + 0.001, job['par'] + 5, round(rng.uniform(1, 400), 2)])}
        b = res['tough'] >= D['stars']['toughNeeded'] and res['penalty'] <= 0
        c = res['secs'] <= job['par']
        calls.append(('starsFor', [{'$job': job['id']}, res]))
        refs.append({'a': True, 'b': b, 'c': c, 'n': 1 + int(b) + int(c)})
    got = rpc(calls)
    batch('math: stars (finish, tough spots by hand with no scuffs, under par time)', ['%s: %r vs %r' % (c[1][1], g, r) for c, g, r in zip(calls, got, refs) if g != r], len(calls))

    # ---- unlocks
    calls, refs = [], []
    for _ in range(500):
        stars = {j['id']: rng.choice([0, 1, 2, 3, 3, 5, -1, 2.9]) for j in D['jobs'] if rng.random() < 0.8}
        if rng.random() < 0.3:
            stars['nope'] = 3
        gear = {g['id']: rng.random() < 0.5 for g in D['gear']}
        s = {'stars': stars, 'gear': gear}
        total = sum(min(max(math.floor(v), 0), 3) for k, v in stars.items() if k in {j['id'] for j in D['jobs']})
        calls.append(('starsTotal', [s]))
        refs.append(total)
        job = rng.choice(D['jobs'])
        calls.append(('jobStatus', [{'$job': job['id']}, s]))
        need_gear = [g for g in job['gear'] if not gear.get(g)]
        need_stars = max(0, job['stars'] - total)
        refs.append({'ok': need_stars == 0 and not need_gear, 'needStars': need_stars, 'needGear': need_gear})
    got = rpc(calls)
    batch('math: star totals and what each job still needs (stars and gear)', ['%s: %r vs %r' % (c[0], g, r) for c, g, r in zip(calls, got, refs) if g != r], len(calls))

    # ---- the rig
    def r_rig(s):
        def lv(i):
            u = [u for u in D['upgrades'] if u['id'] == i][0]
            return min(max(math.floor(s['up'].get(i, 0) or 0), 0), u['max'])

        def per(i):
            return F([u for u in D['upgrades'] if u['id'] == i][0]['per'])
        return {'pMul': 1 + per('pressure') * lv('pressure'), 'rMul': 1 + per('area') * lv('area'), 'fall': max(Fraction(1, 10), F(W['fall']) - Fraction(3, 100) * lv('reach')),
                'tankMax': 40 * (1 + per('tank') * lv('tank')), 'flowCap': Fraction(3, 2) + per('flow') * lv('flow'), 'flowGain': Fraction(12, 100) + Fraction(3, 100) * lv('flow')}
    calls, refs = [], []
    for _ in range(400):
        s = {'up': {u['id']: rng.choice([0, 1, u['max'], u['max'] + 5, -3, 2.7, rng.randint(0, u['max'])]) for u in D['upgrades']}, 'gear': {g['id']: rng.random() < 0.5 for g in D['gear']}}
        calls.append(('rigOf', [s]))
        refs.append((r_rig(s), s['gear']))
    got = rpc(calls)
    bad = []
    for c, g, (r, gear) in zip(calls, got, refs):
        if not all(rclose(g[k], v) for k, v in r.items()) or any(g[k] != bool(gear.get(k)) for k in ('soap', 'hot', 'pole', 'surface')):
            bad.append('%r: %r' % (c[1][0]['up'], g))
    batch('math: the rig (pressure, spot size, reach, tank, flow cap, flow gain, gear) from the upgrade levels, clamped to the maximum', bad, len(calls))

    # ---- number formatting
    big_hand = [0, 0.5, 1, 9.99, 999, 999.99, 1000, 1001, 1234, 1999.99, 9999, 9999.99, 10000, 12345, 99999, 99999.99, 100000, 123456, 999999, 999999.99, 1e6, 1.5e6, 12345678,
                99999999, 1e9, 1.234e9, 1e12, 1e15, 1e18, 999e18, 9.99e20, 1e21, 1.23456e21, 9.99e21, 1.5e24, 1e30, 1e100, 1e300, -5, -999, -1234.5, -2.5e6]
    big_rand = [x for x in (rng.uniform(1, 10) * 10 ** rng.uniform(-1, 24) for _ in range(900))]
    xs = big_hand + big_rand
    got = rpc([('fmtBig', [x]) for x in xs] + [('fmtMoney', [x]) for x in xs] + [('fmtRate', [x]) for x in xs])
    n = len(xs)
    bad = []
    for i, x in enumerate(xs):
        v = X(x)
        if got[i] not in accept(ref_big, v):
            bad.append('fmtBig(%r) = %r, want %r' % (x, got[i], ref_big(v)))
        if got[n + i] not in accept(ref_money, v):
            bad.append('fmtMoney(%r) = %r, want %r' % (x, got[n + i], ref_money(v)))
        if got[2 * n + i] not in accept(ref_rate, v):
            bad.append('fmtRate(%r) = %r, want %r' % (x, got[2 * n + i], ref_rate(v)))
    batch('math: money, big number and per second formats equal the exact rule (3 significant digits rounded down, K M B T Qa Qi, 1e21 and up as 1.23e21)', bad, 3 * n)
    odd = rpc([('fmtBig', ['$num:NaN']), ('fmtBig', ['$num:Infinity']), ('fmtBig', ['$num:-Infinity']), ('fmtMoney', ['$num:NaN']), ('fmtMoney', ['$num:Infinity']), ('fmtRate', ['$num:NaN']),
               ('fmtRate', ['$num:Infinity']), ('fmtRate', [-4]), ('fmtBig', ['12']), ('fmtBig', [None]), ('fmtDur', ['$num:NaN']), ('fmtDur', [None])])
    eq('math: formats never show NaN or Infinity', odd, ['0', '0', '0', '$0', '$0', '$0/s', '$0/s', '$0/s', '12', '0', '0 s', '0 s'])
    ok('math: no format ever prints a minus sign character or the word NaN', all((MINUS not in s and 'NaN' not in s and 'Infinity' not in s) for s in got))
    secs = [0, 1, 59, 59.9, 60, 61, 119, 3599, 3599.9, 3600, 3601, 3660, 7199, 86399.5, 86400, 90061, 1e6, -5] + [rng.uniform(0, 10 ** rng.uniform(0, 7)) for _ in range(400)]
    got = rpc([('fmtDur', [x]) for x in secs])
    batch('math: durations read as s, min and h exactly', ['%r: %r vs %r' % (x, g, ref_dur(x)) for x, g in zip(secs, got) if g != ref_dur(x)], len(secs))

    # ---- scene size and the wash result
    asp = [None, 0, 0.45, 0.449, 0.5, 0.56, 0.75, 1, 1.0001, 1.6, 2.1, 2.5, 0.3] + [round(rng.uniform(0.3, 2.6), 3) for _ in range(300)]
    got = rpc([('sceneSize', [a]) for a in asp])

    def r_scene(a):
        a = a if a else 0.5
        r = min(max(a, 0.45), 2.1)
        if r >= 1:
            return {'W': int(math.floor(1000 * r / 10 + 0.5) * 10), 'H': 1000}
        return {'W': 1000, 'H': int(math.floor(1000 / r / 10 + 0.5) * 10)}
    batch('math: the scene is 1000 wide on portrait and 1000 high on landscape, in whole cells', ['%r: %r vs %r' % (a, g, r_scene(a)) for a, g in zip(asp, got) if g != r_scene(a)], len(asp))
    calls, refs = [], []
    for _ in range(300):
        tt = rng.choice([0, 1, 50, 530])
        w = {'toughTotal': tt, 'toughDone': rng.randint(0, tt) if tt else 0, 'flowUnits': rng.choice([0, 1.5, 1000, 54321.5]), 'scuffN': rng.choice([0, 1, 5, 87, 88, 200, 1000]), 'secs': rng.uniform(1, 300)}
        w['flowSum'] = w['flowUnits'] * rng.uniform(1, 2.5)
        calls.append(('washResult', [w]))
        refs.append({'tough': Fraction(w['toughDone'], w['toughTotal']) if tt else Fraction(1),
                     'flow': (X(w['flowSum']) / X(w['flowUnits'])) if w['flowUnits'] > 0 else Fraction(1),
                     'penalty': min(F(W['scuffMax']), w['scuffN'] * F(W['scuffEach'])), 'secs': X(w['secs'])})
    got = rpc(calls)
    batch('math: the wash result (tough share, average flow, scuff penalty capped at 35 percent)', ['%r vs %r' % (g, {k: float(v) for k, v in r.items()}) for g, r in zip(got, refs)
                                                                                                if not all(rclose(g[k], v) for k, v in r.items())], len(calls))

    # ---- hash, noise and the random generator: an independent port of each
    seeds = [0, 1, 7, 42, 12345, 2 ** 31, 2 ** 32 - 1, 20261002] + [rng.randint(0, 2 ** 32 - 1) for _ in range(40)]
    got = node('prng', seeds)
    bad = []
    for sd, g in zip(seeds, got):
        f = py_mulberry32(sd)
        ref = [f() for _ in range(64)]
        if g != ref:
            bad.append('seed %d' % sd)
    batch('math: the random generator (mulberry32) matches an independent port for 64 values from each of %d seeds' % len(seeds), bad, len(seeds))
    ok('math: the generator output is spread over 0 to 1', all(0 <= v < 1 for g in got for v in g) and 0.4 < sum(v for g in got for v in g) / (64 * len(got)) < 0.6)
    pts = [(rng.randint(-1000, 100000), rng.randint(-1000, 100000), rng.randint(-5, 100000)) for _ in range(300)] + [(0, 0, 0), (-1, -1, -1), (2 ** 20, 7, 255)]
    got = rpc([('hash2', list(p)) for p in pts])
    batch('math: the cell hash matches an independent port', ['%r: %r vs %r' % (p, g, py_hash2(*p)) for p, g in zip(pts, got) if g != py_hash2(*p)], len(pts))
    pts = [(rng.uniform(-50, 600), rng.uniform(-50, 600), rng.randint(0, 5000)) for _ in range(300)]
    got = rpc([('vnoise', list(p)) for p in pts])
    batch('math: value noise matches an independent port', ['%r: %r vs %r' % (p, g, py_vnoise(*p)) for p, g in zip(pts, got) if g != py_vnoise(*p)], len(pts))
    pts = [(rng.uniform(-50, 200), rng.uniform(-50, 200), rng.randint(0, 5000), rng.randint(1, 4)) for _ in range(200)]
    got = rpc([('fbm', list(p)) for p in pts])
    batch('math: layered noise matches an independent port', ['%r: %r vs %r' % (p, g, py_fbm(*p)) for p, g in zip(pts, got) if g != py_fbm(*p)], len(pts))
    got = rpc([('smooth', [0, 1, x]) for x in (-1, 0, 0.25, 0.5, 1, 2)] + [('clamp', [x, 0, 1]) for x in (-1, 0, 0.5, 1, 7)])
    eq('math: smoothstep and clamp at their edges', got, [0, 0, 0.15625, 0.5, 1, 1, 0, 0, 0.5, 1, 1])

    # ---- save codes and the sanitiser
    states = []
    for _ in range(150):
        s = json.loads(json.dumps(exp_fresh))
        s.update(money=round(rng.uniform(0, 1e12), 3), lifetime=round(rng.uniform(0, 1e13), 3), fp=rng.choice([0, 8, 40, 130]), cycles=rng.randint(0, 5), jobs=rng.randint(0, 900),
                 tut=rng.choice([True, False]), savedAt=base_t + rng.randint(0, 10 ** 8))
        s['earned'] = max(s['lifetime'], round(rng.uniform(0, 2e13), 3))
        s['stars'] = {j['id']: rng.randint(1, 3) for j in D['jobs'] if rng.random() < 0.6}
        s['up'] = {u['id']: rng.randint(0, u['max']) for u in D['upgrades']}
        s['gear'] = {g['id']: rng.random() < 0.5 for g in D['gear']}
        s['crew'] = {c['id']: rng.randint(0, 3000) for c in D['crew']}
        s['trucks'] = rng.randint(0, 8)
        s['color'] = rng.choice([c['id'] for c in FR['colors'] if s['fp'] >= c['fp']])
        s['set'] = {'sound': rng.choice([True, False]), 'calm': rng.choice([True, False])}
        states.append(s)
    codes = rpc([('exportCode', [s]) for s in states])
    ok('save: codes look like GT1.payload.checksum with URL safe characters', all(re.fullmatch(r'GT1\.[A-Za-z0-9_-]+\.[a-z0-9]+', c) for c in codes))
    back = rpc([('importCode', [c]) for c in codes])
    batch('save: every valid state survives export then import unchanged', ['%r' % (b,) for s, b in zip(states, back) if not (b['ok'] and b['state'] == s)], len(states))
    tam = []
    for c in codes[:100]:
        i = rng.randint(4, len(c) - 1)
        repl = 'A' if c[i] != 'A' else 'B'
        if c[i] == '.':
            continue
        tam.append(c[:i] + repl + c[i + 1:])
    tam += [c[:-3] for c in codes[:20]] + ['GT2' + c[3:] for c in codes[:5]] + ['', 'hello', 'GT1..', 'GT1.abc.', 'GT1.!!.zz', ' '.join('x')]
    back = rpc([('importCode', [c]) for c in tam])
    batch('save: edited, cut off or foreign codes are refused with a message', ['%r' % (c[:30],) for c, b in zip(tam, back) if b['ok'] or not b.get('error')], len(tam))
    spaced = rpc([('importCode', ['  ' + codes[0][:30] + '\n' + codes[0][30:] + '  \t'])])[0]
    ok('save: spaces and line breaks added by a messenger are ignored', spaced['ok'] and spaced['state'] == states[0])
    bad_in = [None, 5, 'x', [], True, {'v': 99}, {'v': 2}, {'v': 1.5}, {'v': 0}, {'v': -1}, {'v': 'abc'}, {'v': None}, {'v': []}]
    got = rpc([('sanitize', [x]) for x in bad_in])
    eq('save: things that are not saves, or are from a newer version, are refused', [g is None for g in got], [True] * len(bad_in))
    good_in = [{}, {'v': 1}, {'v': '1'}, {'v': True}, {'money': 5}]
    got = rpc([('sanitize', [x]) for x in good_in])
    eq('save: an old save with no version, or version 1 written as text, is read', [g is not None for g in got], [True] * len(good_in))
    hostile = {'v': 1, 'money': -5, 'lifetime': 1e40, 'earned': 3, 'stars': {'driveway': 99, 'patio': -2, 'fence': 2.9, 'nope': 3, 'wall': 'x'}, 'up': {'pressure': 99, 'area': -5, 'tank': 2.7, 'reach': 'abc'},
               'gear': {'soap': 'yes', 'hot': True, 'pole': 1}, 'crew': {'apprentice': 1e9, 'tech': -4, 'foreman': 7.9}, 'trucks': 99, 'fp': 1e12, 'cycles': -1, 'jobs': 5.5, 'tut': 1, 'color': 'violet',
               'savedAt': 1e18, 'set': {'sound': 0, 'calm': 'true'}, 'extra': {'a': 1}}
    s = rpc([('sanitize', [hostile])])[0]
    want = json.loads(json.dumps(exp_fresh))
    want.update(money=0, lifetime=1e30, earned=1e30, stars={'driveway': 3, 'fence': 2}, up={'pressure': 10, 'area': 0, 'tank': 2, 'reach': 0, 'flow': 0}, gear={'soap': False, 'hot': True, 'pole': False, 'surface': False},
                crew={'apprentice': 100000, 'tech': 0, 'foreman': 7, 'manager': 0, 'boss': 0, 'director': 0}, trucks=8, fp=10 ** 9, cycles=0, jobs=5, tut=False, color='violet', savedAt=4102444800000,
                set={'sound': True, 'calm': False})
    eq('save: hostile values are clamped, coerced or dropped, unknown keys vanish', s, want)
    h2 = dict(hostile, fp=29)
    eq('save: a locked rig colour falls back to the first', rpc([('sanitize', [h2])])[0]['color'], 'sun')
    h3 = rpc([('sanitize', [{'set': {'sound': False, 'calm': True}, 'tut': True}])])[0]
    ok('save: sound off, calm on and the tutorial flag are read back only from exact values', h3['set'] == {'sound': False, 'calm': True} and h3['tut'] is True)
    junk_pool = [None, True, False, 0, 1, -1, 3, 2.5, 1e12, 1e40, -1e40, '', 'abc', '12', [], {}, [1], {'a': 1}]
    cases = []
    for _ in range(300):
        o = {}
        for k in ('v', 'money', 'lifetime', 'earned', 'stars', 'up', 'gear', 'crew', 'trucks', 'fp', 'cycles', 'jobs', 'tut', 'color', 'savedAt', 'set', 'zzz'):
            if rng.random() < 0.7:
                o[k] = rng.choice(junk_pool)
        o['v'] = rng.choice([1, 1, None, '1']) if rng.random() < 0.8 else o.get('v', 1)
        cases.append(o)
    got = rpc([('sanitize', [o]) for o in cases])
    names = {j['id'] for j in D['jobs']}
    bad = []
    for o, s in zip(cases, got):
        if s is None:
            continue
        good = (set(s) == set(exp_fresh) and 0 <= s['money'] <= 1e30 and 0 <= s['lifetime'] <= 1e30 and s['earned'] >= s['lifetime'] and s['earned'] <= 1e30
                and all(k in names and 1 <= v <= 3 for k, v in s['stars'].items())
                and all(0 <= s['up'][u['id']] <= u['max'] and float(s['up'][u['id']]).is_integer() for u in D['upgrades'])
                and all(isinstance(s['gear'][g['id']], bool) for g in D['gear'])
                and all(0 <= s['crew'][c['id']] <= 100000 and float(s['crew'][c['id']]).is_integer() for c in D['crew'])
                and 0 <= s['trucks'] <= D['trucks']['max'] and 0 <= s['fp'] <= 1e9 and s['cycles'] >= 0 and s['jobs'] >= 0 and isinstance(s['tut'], bool)
                and any(c['id'] == s['color'] and s['fp'] >= c['fp'] for c in FR['colors']) and 0 <= s['savedAt'] <= 4102444800000
                and set(s['set']) == {'sound', 'calm'} and isinstance(s['set']['sound'], bool) and isinstance(s['set']['calm'], bool) and s['v'] == 1)
        if not good:
            bad.append('%r -> %r' % (o, s))
    batch('save: whatever is in storage, the sanitised state is always in range, whole numbers, known jobs and colours only', bad, len(cases))
    again = rpc([('sanitize', [s]) for s in got if s is not None])
    batch('save: sanitising a sanitised state changes nothing', ['%r' % (a,) for a, b in zip(again, [s for s in got if s is not None]) if a != b], len(again))
    p = rpc([('parseSave', ['{not json']), ('parseSave', ['']), ('parseSave', ['null']), ('parseSave', ['[]']), ('parseSave', [json.dumps(exp_fresh)])])
    eq('save: unreadable text is refused, a good save is read', [x is None for x in p], [True, True, True, True, False])
    ser = rpc([('serialize', [dict(exp_fresh, v=7)])])[0]
    ok('save: the saved text always carries the current version', json.loads(ser)['v'] == 1)


# ================================================================== wash core: determinism, invariants, physics
def snake_path(W, H, R, y_to, tip, speed=900.0, gap=20):
    """A snake of spray rows from the top down to y_to, then a short lift. Steps are [x, y, down, tip or None]."""
    pts, sp, d, y, first = [], speed / 60.0, 1, R / 2.0, True
    while y < y_to:
        yy = min(H - 5.0, y)
        xs = []
        x = 0.0 if d > 0 else float(W)
        while 0 <= x <= W:
            xs.append(x)
            x += d * sp
        for x in xs:
            pts.append([round(x, 3), round(yy, 3), 1, tip if first else None])
            first = False
        d = -d
        y += R * 1.3
    for _ in range(gap):
        pts.append([pts[-1][0], pts[-1][1], 0, None])
    return pts


RUN_JS = """(q)=>{
  const g = window.__grime, G = g.G(), w = G.w;
  w.secs = 0; G.acc = 0;
  for (const p of q.steps) { if (p[3]) g.tip(p[3]); g.pointer(p[0], p[1], !!p[2]); g.advance(1000 / 60); }
  const s = G.s, u = new Uint8Array(w.thick.buffer, w.thick.byteOffset, w.thick.byteLength);
  let h = 2166136261;
  for (let i = 0; i < u.length; i++) { h ^= u[i]; h = Math.imul(h, 16777619) >>> 0; }
  const out = { left: w.left, total0: w.total0, units: w.units, flowSum: w.flowSum, flowUnits: w.flowUnits, secs: w.secs, toughDone: w.toughDone, toughTotal: w.toughTotal,
                scuffN: w.scuffN, foamN: w.foamN, tank: s.tank, mult: s.mult, cov: g.PURE.coverage(w), hThick: h.toString(16), res: g.PURE.washResult(w), phase: G.phase };
  g.pointer(0, 0, false);
  return out;
}"""

GRID_JS = """(qs)=>{
  const P = window.__grime.PURE;
  const fnv = (arr) => { const u = new Uint8Array(arr.buffer, arr.byteOffset, arr.byteLength); let h = 2166136261; for (let i = 0; i < u.length; i++) { h ^= u[i]; h = Math.imul(h, 16777619) >>> 0; } return h.toString(16); };
  return qs.map(q => { const g = P.makeGrid(P.byId(P.DATA.jobs, q.job), q.gw, q.gh, q.seed >>> 0);
    return { job: q.job, seed: q.seed, total: g.total, tough: g.toughTotal, hThick: fnv(g.thick), hKind: fnv(g.kind), hTough: fnv(g.tough) }; });
}"""


def t_wash():
    D = pure_data()
    shapes = ((100, 178), (178, 100))
    reqs = [{'job': j['id'], 'gw': gw, 'gh': gh, 'seed': s} for j in D['jobs'] for s in (1, 7, 12345) for (gw, gh) in shapes]
    a, b = node('grid', reqs), node('grid', reqs)
    eq('wash: the same seed gives the same grime in two separate runs (%d grids)' % len(reqs), a, b)
    by = {}
    for r, q in zip(a, reqs):
        by.setdefault((q['job'], q['gw']), []).append(r)
    ok('wash: different seeds give different grime for every job', all(len({x['hThick'] for x in v}) == 3 for v in by.values()), [k for k, v in by.items() if len({x['hThick'] for x in v}) != 3])
    kinds = {k['id']: i for i, k in enumerate(D['kinds'])}
    bad = []
    for r, q in zip(a, reqs):
        job = [j for j in D['jobs'] if j['id'] == q['job']][0]
        want = {kinds[sp['k']] for sp in job['recipe'].get('specials', [])}
        have = {i for i in range(1, 6) if r['kinds'][i] > 0}
        if have != want:
            bad.append('%s seed %d: kinds %r vs %r' % (q['job'], q['seed'], sorted(have), sorted(want)))
        if not (3000 < r['total'] <= q['gw'] * q['gh']) or not (0.005 < r['tough'] / r['total'] < 0.7):
            bad.append('%s seed %d: total %d tough %d' % (q['job'], q['seed'], r['total'], r['tough']))
    batch('wash: every job lays the stains its recipe names, a sensible area and a minority of tough spots', bad, len(a))
    # the page's own copy of the code makes the same grids (Node and Chromium agree bit for bit)
    ctx, pg, logs = new_page(390, 844, 'light', 1, True, tag='wash grids')
    got = pg.evaluate(GRID_JS, reqs)
    keys = ('job', 'seed', 'total', 'tough', 'hThick', 'hKind', 'hTough')
    bad = ['%s seed %s' % (g['job'], g['seed']) for g, r in zip(got, a) if any(g[k] != r[k] for k in keys)]
    batch('wash: the browser and Node build identical grids for all jobs and seeds', bad, len(reqs))
    ok('wash: console clean (grids)', not logs, logs)
    # scripted washes with a fixed seed: the page and the pure code agree on every number
    rig = {'up': {'pressure': 4, 'area': 3, 'tank': 2, 'reach': 1, 'flow': 2}, 'gear': {'soap': True, 'hot': True}}
    for job_id, tips in (('patio', ('white', 'green', 'yellow')), ('wall', ('green', 'red')), ('deck', ('white', 'red', 'soap', 'white'))):
        pg.evaluate("(r)=>{window.__grime.seed=77;window.__grime.setState({tut:true,stars:ALL_STARS,up:r.up,gear:r.gear})}".replace('ALL_STARS', json.dumps(ALL_STARS)), rig)
        pg.evaluate("()=>{const b=document.getElementById('leaveBtn');if(window.__grime.G()){b.click();b.click()}}")     # leave the last job (two taps), a new job cannot start inside one
        ok('wash: no job is open before %s starts' % job_id, pg.evaluate('()=>window.__grime.G()') is None)
        pg.evaluate('(j)=>window.__grime.start(j)', job_id)
        pg.wait_for_timeout(250)
        ok('wash: %s is the open job' % job_id, pg.evaluate('()=>window.__grime.G().job.id') == job_id)
        dims = pg.evaluate('()=>{const w=window.__grime.G().w;return [w.W,w.H,w.gw,w.gh]}')
        W, H, gw, gh = dims
        steps = []
        for k, tip in enumerate(tips):
            R = D['wash']['baseR'] * [t for t in D['tips'] if t['id'] == tip][0]['r'] * (1 + 0.1 * rig['up']['area'])
            steps += snake_path(W, H, R, H * (0.12 + 0.08 * k), tip, 900.0 if tip != 'red' else 500.0)
        if job_id == 'deck':      # linger with the red tip on boards that are already clean: that is what scuffs a delicate surface
            cx, cy = W * 0.5, H * 0.08
            steps += [[cx, cy, 1, 'red']] + [[cx, cy, 1, None]] * 230 + [[cx, cy, 0, None]] * 5
        q = {'job': job_id, 'seed': 77, 'gw': gw, 'gh': gh, 'up': rig['up'], 'gear': rig['gear'], 'steps': steps}
        n1, n2 = node('run', [q, q])
        eq('wash: %s scripted wash is identical in two Node runs (%d steps)' % (job_id, len(steps)), n1, n2)
        ok('wash: %s scripted wash stops short of the finish so the comparison is fair (%.0f percent)' % (job_id, 100 * n1['cov']), 0.05 < n1['cov'] < 0.95, n1['cov'])
        br = pg.evaluate(RUN_JS, q)
        ok('wash: %s page is still in play after the script' % job_id, br['phase'] == 'play', br['phase'])
        bad = [k for k in ('left', 'total0', 'toughDone', 'toughTotal', 'scuffN', 'foamN', 'hThick') if br[k] != n1[k]]
        bad += [k for k in ('units', 'flowSum', 'flowUnits', 'secs', 'tank', 'mult', 'cov') if not rclose(br[k], X(n1[k]), 1e-9)]
        bad += ['res.' + k for k in ('tough', 'flow', 'penalty') if not rclose(br['res'][k], X(n1['res'][k]), 1e-9)]
        ok('wash: %s page and pure code agree on every number after the same strokes' % job_id, not bad, '%s: page %r node %r' % (bad, {k: br[k] for k in bad if k in br}, {k: n1[k] for k in bad if k in n1}))
        if job_id == 'deck':
            ok('wash: the red tip scuffed the delicate deck in both', br['scuffN'] > 0 and n1['scuffN'] == br['scuffN'], (br['scuffN'], n1['scuffN']))
            ok('wash: the scuffs become a damage penalty in the wash result', br['res']['penalty'] > 0)
    ok('wash: console clean (scripted washes)', not logs, logs)
    close(ctx)
    # invariants over long washes with every tip
    reqs = [{'job': j, 'seed': 11, 'up': {'pressure': 4, 'area': 3, 'tank': 2, 'flow': 2}, 'gear': {'soap': True, 'hot': True}, 'tips': ['soap', 'white', 'green', 'yellow', 'red']}
            for j in ('driveway', 'patio', 'fence', 'wall', 'deck', 'garage', 'siding', 'car')]
    reqs.append({'job': 'patio', 'seed': 5, 'up': {}, 'gear': {}, 'tips': ['white', 'green']})
    res = node('inv', reqs)
    names = ['left counts the cells that still have grime', 'grime thickness never grows', 'foam stays between 0 and 1', 'foam counter matches the foam cells',
             'tough spots cleaned never exceed the tough spots', 'flow multiplier stays between 1 and its cap', 'tank stays between empty and full', 'coverage stays between 0 and 1',
             'grime units removed match the thickness that disappeared', 'units are never negative', 'wash clock counts the fixed steps']
    for q, r in zip(reqs, res):
        ok('wash invariants on %s: ran %d steps and %d percent clean' % (q['job'], r['steps'], round(100 * r['cov'])), r['steps'] > 1000 and r['cov'] > 0.2)
        for nme in names:
            ok('wash invariant on %s: %s' % (q['job'], nme), nme not in r['bad'], r['bad'].get(nme))
    for nme, good, detail in node('phys'):
        ok('wash physics: ' + nme, good, detail)


# ================================================================== pace: the sim's milestone times stay inside the agreed ranges
PACE_RANGES = [('c1.firstJobDone', 15, 40), ('c1.firstUpgrade', 15, 60), ('c1.job3Unlocked', 90, 150), ('c1.firstCrew', 180, 330), ('c1.job6Unlocked', 600, 1000),
               ('c1.job8Unlocked', 800, 1300), ('c1.surfaceCleaner', 800, 1200), ('c1.franchiseOffered', 3600, 5400)]


def t_pace():
    D = pure_data()
    r = node('pace', {'hours': 2, 'franchiseAt': 1})
    ms = r['ms']
    for key, lo, hi in PACE_RANGES:
        ok('pace: %s at %s s is inside %d to %d' % (key, ms.get(key), lo, hi), key in ms and lo <= ms[key] <= hi, ms.get(key))
    ok('pace: the first Franchise offer gives at least the minimum points', r['stats'] and r['stats'][0]['gain'] >= D['franchise']['minGain'], r['stats'])
    c1 = r['stats'][0]['secs'] if r['stats'] else 0
    c2 = ms.get('c2.franchiseOffered', 0) - ms.get('c1.franchiseOffered', 0)
    ok('pace: the second cycle (%d s) takes at most 75 percent of the first (%d s)' % (c2, c1), 0 < c2 <= 0.75 * c1, (c1, c2))
    ok('pace: cycle two reaches the surface cleaner and a first hire quickly (jobs stay unlocked)', 0 < ms.get('c2.surfaceCleaner', 0) - ms['c1.franchiseOffered'] < 900 and 0 < ms.get('c2.firstCrew', 0) - ms['c1.franchiseOffered'] < 900)
    ok('pace: the order of milestones is the order a player meets them', ms['c1.firstJobDone'] <= ms['c1.firstUpgrade'] < ms['c1.job3Unlocked'] < ms['c1.firstCrew'] < ms['c1.job6Unlocked'] < ms['c1.job8Unlocked'] < ms['c1.franchiseOffered'])
    ok('pace: the bot played a plausible number of jobs in two hours', 60 < r['jobs'] < 600, r['jobs'])


# ================================================================== page helpers shared by the browser sections
CONTRAST_JS = r'''
/* Computed contrast audit: for each visible text element, colour against the composited background of its ancestors.
   Elements with a canvas behind them (no opaque ancestor inside the overlay) fall back to the given stage colour. */
(function () {
  function parse(c) { var m = /rgba?\(([^)]+)\)/.exec(c); if (!m) return [0, 0, 0, 0]; var p = m[1].split(/[ ,\/]+/).filter(Boolean).map(parseFloat); return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; }
  function over(top, bot) { var a = top[3] + bot[3] * (1 - top[3]); if (a <= 0) return [0, 0, 0, 0]; return [(top[0] * top[3] + bot[0] * bot[3] * (1 - top[3])) / a, (top[1] * top[3] + bot[1] * bot[3] * (1 - top[3])) / a, (top[2] * top[3] + bot[2] * bot[3] * (1 - top[3])) / a, a]; }
  function lum(c) { function f(v) { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); } return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); }
  function ratio(a, b) { var l1 = lum(a), l2 = lum(b); if (l1 < l2) { var t = l1; l1 = l2; l2 = t; } return (l1 + 0.05) / (l2 + 0.05); }
  window.__contrast = function (rootSel, stageHex) {
    var root = document.querySelector(rootSel) || document.body, out = [], stage = parse(stageHex || 'rgb(21,12,34)');
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null), n;
    var seen = new Set();
    while ((n = walker.nextNode())) {
      var el = n.parentElement, txt = (n.nodeValue || '').trim();
      if (!txt || !el || seen.has(el)) continue;
      var cs = getComputedStyle(el);
      if (cs.visibility === 'hidden' || cs.display === 'none') continue;
      var r = el.getBoundingClientRect();
      if (r.width < 1 || r.height < 1) continue;
      if (el.closest('[hidden]')) continue;
      var tag = el.tagName; if (tag === 'SCRIPT' || tag === 'STYLE') continue;
      seen.add(el);
      var op = 1, e = el, layers = [];
      while (e && e !== document.documentElement) {
        var c = getComputedStyle(e); op *= parseFloat(c.opacity);
        var bg = parse(c.backgroundColor); if (bg[3] > 0) layers.push(bg);
        if (bg[3] >= 1) break;
        e = e.parentElement;
      }
      var base = (e && e !== document.documentElement && parse(getComputedStyle(e).backgroundColor)[3] >= 1) ? null : (document.getElementById('wash') && document.getElementById('wash').contains(el) ? stage : parse(getComputedStyle(document.body).backgroundColor));
      var comp = base || layers.pop();
      for (var i = layers.length - 1; i >= 0; i--) comp = over(layers[i], comp);
      var fg = parse(cs.color); fg[3] *= op;
      var fgc = over(fg, comp);
      var size = parseFloat(cs.fontSize), bold = parseInt(cs.fontWeight, 10) >= 700, large = size >= 24 || (size >= 18.66 && bold);
      var cr = ratio(fgc, comp);
      out.push({ t: txt.slice(0, 28), cr: Math.round(cr * 100) / 100, need: large ? 3 : 4.5, el: (el.id || el.className || el.tagName).toString().slice(0, 30), fs: size });
    }
    return out;
  };
})();
'''

AUDIT_JS = """()=>{
  const out = {over: document.documentElement.scrollWidth - innerWidth, small: [], clipped: [], n: 0};
  const vis = e => { const r = e.getBoundingClientRect(); const cs = getComputedStyle(e); return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none'; };
  let root = document.getElementById('wash').hidden ? document.getElementById('app') : document.getElementById('wash');
  const modal = [...document.querySelectorAll('.modal, #result, #setModal')].find(m => !m.hidden && vis(m));
  if (modal) root = modal;
  root.querySelectorAll('button, [role=button], a, input, textarea, [role=tab], .sw').forEach(e => {
    if (!vis(e)) return;
    const r = e.getBoundingClientRect(); out.n++;
    const lab = (e.id || e.getAttribute('data-key') || e.getAttribute('data-tip') || e.className || e.tagName).toString().slice(0, 24);
    if (Math.min(r.width, r.height) < 39.5 && e.tagName !== 'A') out.small.push(lab + ' ' + Math.round(r.width) + 'x' + Math.round(r.height));
    if (r.right > innerWidth + 0.5 || r.left < -0.5 || r.bottom > innerHeight + 0.5 || r.top < -0.5) { if (!e.closest('.tabpanel, #tab-jobs, #tab-rig, #tab-crew, #tab-fran, .app, footer')) out.clipped.push(lab + ' ' + Math.round(r.left) + ',' + Math.round(r.top) + ',' + Math.round(r.right) + ',' + Math.round(r.bottom)); }
  });
  return out;
}"""

MAP_JS = "()=>{const G=window.__grime.G();return {l:G.left,t:G.top,ox:G.ox,oy:G.oy,sc:G.sc,W:G.w.W,H:G.w.H}}"


def to_client(m, x, y):
    """Scene units to page pixels (the wash controller's own mapping, read back from the page)."""
    return m['l'] + m['ox'] + x * m['sc'], m['t'] + m['oy'] + y * m['sc']


def now_ms():
    return int(time.time() * 1000)


ALL_STARS = {'driveway': 3, 'patio': 3, 'fence': 3, 'wall': 3, 'deck': 3, 'garage': 3, 'siding': 3, 'car': 3}
ALL_GEAR = {'soap': True, 'hot': True, 'pole': True, 'surface': True}


# ================================================================== shop: rig, gear, crew, trucks, franchise and settings, all by real clicks
def zeros(D):
    return ({u['id']: 0 for u in D['upgrades']}, {g['id']: False for g in D['gear']}, {c['id']: 0 for c in D['crew']})


BUY_JS = """(sel)=>{const g=window.__grime, b=document.querySelector(sel), cp=()=>JSON.parse(JSON.stringify(g.state()));
  const s0=cp(); b.click(); return [s0, cp()];}"""


def buy_exact(pg, sel):
    """Click a buy button from inside the page and read the state before and after in the same turn, so no income tick can land in between."""
    return pg.evaluate(BUY_JS, sel)


def rich(pg, **kw):
    """Plenty of cash and the tutorial done, plus whatever else is given (the whole of each patch value replaces the saved one)."""
    d = {'tut': True, 'money': 1e15, 'lifetime': 1e15}
    d.update(kw)
    pg.evaluate('(d)=>window.__grime.setState(d)', d)


def t_shop():
    D = pure_data()
    UP0, GEAR0, CREW0 = zeros(D)
    ctx, pg, logs = new_page(390, 844, 'light', 2, True, tag='shop')
    pg.click('#tb-rig')
    # ---- every upgrade: one click buys one level at the exact price, and the button says what it does
    for u in D['upgrades']:
        rich(pg, up=UP0)
        s0 = st(pg)
        cost = pure(pg, 'P.upgradeCost(%s, 0)' % json.dumps(u['id']))
        sel = '[data-key="up-%s"]' % u['id']
        label, txt = pg.get_attribute(sel, 'aria-label'), pg.inner_text(sel)
        pg.click(sel)
        s1 = st(pg)
        ok('shop: one click buys %s level 1 at its exact price' % u['id'], s1['up'][u['id']] == 1 and abs((s0['money'] - s1['money']) - cost) < 1e-6, (s0['money'], s1['money'], cost))
        ok('shop: the %s button shows the price and the level it buys' % u['id'], ref_money(F(cost)) in txt and 'Level 1' in txt, txt)
        ok('shop: the %s button has a spoken label with level and price' % u['id'], 'level 1' in label.lower() and ('%s dollars' % format(int(cost), ',')) in label, label)
        ok('shop: the %s row now reads level 1 of %d' % (u['id'], u['max']), ('%s 1/%d' % (u['name'], u['max'])).lower() in pg.inner_text('#upList').lower(), pg.inner_text('#upList')[:200])
    rich(pg, up=UP0)
    bad = []
    mx = D['upgrades'][0]['max']
    for lv in range(mx):
        before = st(pg)['money']
        pg.click('[data-key="up-pressure"]')
        paid = before - st(pg)['money']
        want = pure(pg, 'P.upgradeCost("pressure", %d)' % lv)
        if abs(paid - want) > 1e-6:
            bad.append((lv, paid, want))
    ok('shop: pressure is bought level by level to the maximum, each at its own price', not bad and st(pg)['up']['pressure'] == mx, bad)
    ok('shop: at the maximum the buy button is gone and the row says Max level', pg.query_selector('[data-key="up-pressure"]') is None and 'Max level' in pg.inner_text('#upList'))
    # ---- gear: each piece once, exact price
    for g in D['gear']:
        rich(pg, gear=GEAR0)
        s0 = st(pg)
        pg.click('[data-key="gear-%s"]' % g['id'])
        s1 = st(pg)
        ok('shop: %s is bought for exactly %s' % (g['id'], g['cost']), s1['gear'][g['id']] is True and abs(s0['money'] - s1['money'] - g['cost']) < 1e-6, (s0['money'], s1['money']))
        ok('shop: bought %s shows as Owned with no buy button' % g['id'], pg.query_selector('[data-key="gear-%s"]' % g['id']) is None and 'Owned' in pg.inner_text('#gearList'))
    rich(pg, money=0, lifetime=0, gear=GEAR0)
    ok('shop: a button you cannot afford is marked disabled', pg.get_attribute('[data-key="gear-pole"]', 'aria-disabled') == 'true')
    pg.click('[data-key="gear-pole"]', force=True)
    ok('shop: tapping it says there is not enough cash and buys nothing', 'Not enough cash' in pg.inner_text('#toast') and st(pg)['gear']['pole'] is not True, pg.inner_text('#toast'))
    # ---- crew: one of each tier, then x10 and max
    pg.click('#tb-crew')
    rich(pg, crew=CREW0)
    for k, c in enumerate(D['crew']):
        cost = pure(pg, 'P.crewCostMany(%s, 0, 1)' % json.dumps(c['id']))
        sel = '[data-key="crew-%s"]' % c['id']
        if k == 0:
            s0 = st(pg)
            pg.click(sel)       # a real click while there is no crew yet, so no income can blur the price
            s1 = st(pg)
        else:
            s0, s1 = buy_exact(pg, sel)
        ok('shop: hiring one %s costs its base price' % c['id'], s1['crew'][c['id']] == 1 and abs(s0['money'] - s1['money'] - cost) <= 1e-6 * max(1, cost) and cost == c['base'], (s0['money'], s1['money'], cost))
    rate = pure(pg, 'P.crewIncome(window.__grime.state())')
    ok('shop: the crew page shows the income per second in the shared money format', pg.inner_text('#cRate') in accept(ref_rate, X(rate)), (pg.inner_text('#cRate'), rate))
    ok('shop: the stat bar shows the same income', pg.inner_text('#sRate') in accept(ref_rate, X(rate)), pg.inner_text('#sRate'))
    pg.click('[data-key="mul-10"]')
    ok('shop: the x10 choice is marked pressed', pg.get_attribute('[data-key="mul-10"]', 'aria-pressed') == 'true' and pg.get_attribute('[data-key="mul-1"]', 'aria-pressed') == 'false')
    a1, a2 = buy_exact(pg, '[data-key="crew-apprentice"]')
    cc10 = pure(pg, 'P.crewCostMany("apprentice", 1, 10)')
    ok('shop: x10 hires ten at the sum of ten prices', a2['crew']['apprentice'] == 11 and abs(a1['money'] - a2['money'] - cc10) <= 1e-6 * cc10, (a1['money'], a2['money'], cc10))
    ok('shop: eleven apprentices earn the first doubling (ten owned)', abs(pure(pg, 'P.tierIncome(window.__grime.state(), "apprentice")') - 11 * D['crew'][0]['inc'] * 2 * (1 + D['franchise']['perPoint'] * a2['fp'])) < 1e-9)
    pg.click('[data-key="mul-max"]')
    rich(pg, money=5e6, lifetime=5e6)
    before = st(pg)
    want_k = pure(pg, 'P.crewAfford("apprentice", %d, %r)' % (before['crew']['apprentice'], before['money']))
    before, a3 = buy_exact(pg, '[data-key="crew-apprentice"]')
    ok('shop: max hires exactly as many as the cash pays for', a3['crew']['apprentice'] - before['crew']['apprentice'] == want_k and want_k > 5, (a3['crew']['apprentice'], before['crew']['apprentice'], want_k))
    ok('shop: after max the cash left is less than the next price', 0 <= a3['money'] < pure(pg, 'P.crewCost("apprentice", %d)' % a3['crew']['apprentice']), a3['money'])
    pg.click('[data-key="mul-1"]')
    rich(pg, money=0, lifetime=0)
    pg.click('[data-key="crew-tech"]', force=True)
    ok('shop: a hire you cannot afford says so and hires nobody', 'Not enough cash' in pg.inner_text('#toast') and st(pg)['crew']['tech'] == 1)
    # ---- trucks: eight of them, each at its price, the away cap grows an hour each
    rich(pg, trucks=0)
    bad = []
    for n in range(D['trucks']['max']):
        before, after = buy_exact(pg, '[data-key="truck"]')
        want = pure(pg, 'P.truckCost(%d)' % n)
        cap_txt = pg.inner_text('#cCap')
        if after['trucks'] != n + 1 or abs(before['money'] - after['money'] - want) > 1e-6 * want or cap_txt != ref_dur(min(12, 4 + n + 1) * 3600):
            bad.append((n, after['trucks'], before['money'] - after['money'], want, cap_txt))
    ok('shop: eight trucks at their prices, the away cap reads 5 h up to 12 h', not bad and st(pg)['trucks'] == D['trucks']['max'], bad)
    ok('shop: at the maximum the truck button is gone and the row says Max', pg.query_selector('[data-key="truck"]') is None and 'Max' in pg.inner_text('#truckList'))
    # ---- franchise: not ready, ready, two taps, what it resets and keeps
    rich(pg, money=0, lifetime=100, crew=dict(CREW0, apprentice=3))
    pg.click('#tb-fran')
    ok('shop: franchise is marked not ready at first', pg.get_attribute('[data-key="franchise"]', 'aria-disabled') == 'true' and 'not ready' in pg.inner_text('[data-key="franchise"]').lower())
    pg.click('[data-key="franchise"]', force=True)
    ok('shop: tapping it says how much more to earn', 'Not ready yet' in pg.inner_text('#toast'), pg.inner_text('#toast'))
    pg.evaluate('()=>window.__grime.setState({lifetime:5e7, stars:{driveway:3,patio:2}, color:"sun", set:{sound:true,calm:true}})')
    fb = pg.query_selector('[data-key="franchise"]')
    ok('shop: franchise is ready after earning enough', fb.get_attribute('aria-disabled') != 'true', fb.inner_text())
    pre = st(pg)
    gain = pure(pg, 'P.franchiseOffer(%s).gain' % json.dumps(pre))
    ok('shop: the button names the points it gives', ('+%d points' % gain) in fb.inner_text(), fb.inner_text())
    pg.click('[data-key="franchise"]')
    ok('shop: the first tap only asks to confirm', st(pg)['cycles'] == 0 and 'tap again' in pg.inner_text('[data-key="franchise"]').lower(), pg.inner_text('[data-key="franchise"]'))
    pg.click('[data-key="franchise"]')
    post = st(pg)
    ok('shop: franchise resets cash, rig, gear, crew and trucks', post['money'] == 0 and sum(post['up'].values()) == 0 and not any(post['gear'].values()) and sum(post['crew'].values()) == 0 and post['trucks'] == 0, post)
    ok('shop: franchise keeps stars, adds the points once, counts the cycle', post['stars'] == pre['stars'] and post['fp'] == pre['fp'] + gain and post['cycles'] == pre['cycles'] + 1, (post['fp'], gain))
    ok('shop: franchise keeps the settings and the tutorial flag', post['set'] == pre['set'] and post['tut'] is True)
    ok('shop: franchise lands on the Jobs tab, no job starts', pg.get_attribute('#tb-jobs', 'aria-selected') == 'true' and pg.evaluate('()=>window.__grime.G()') is None)
    fp_now = post['fp']
    pg.click('#tb-fran')
    ok('shop: the points and the multiplier are shown', ('(x%.2f)' % (1 + D['franchise']['perPoint'] * fp_now)) in pg.inner_text('#franPanel'), pg.inner_text('#franPanel')[:200])
    pg.click('[data-key="col-teal"]')
    ok('shop: a rig colour that is unlocked can be chosen', st(pg)['color'] == 'teal' and pg.get_attribute('[data-key="col-teal"]', 'aria-pressed') == 'true')
    ok('shop: a locked rig colour cannot be chosen', pg.query_selector('[data-key="col-gold"]').is_disabled() and 'unlocks at 120 points' in pg.get_attribute('[data-key="col-gold"]', 'aria-label'))
    pg.evaluate('(c)=>window.__grime.setState({crew:c})', dict(CREW0, apprentice=10))
    inc = pure(pg, 'P.crewIncome(%s)' % json.dumps(st(pg)))
    base = pure(pg, 'P.crewIncome(Object.assign(%s,{fp:0}))' % json.dumps(st(pg)))
    ok('shop: the franchise bonus applies to the crew income', abs(inc / base - (1 + D['franchise']['perPoint'] * fp_now)) < 1e-9, (inc, base))
    # the dots on the tabs say where something can be bought
    pg.evaluate('()=>window.__grime.setState({money:1e9})')
    pg.click('#tb-jobs')
    pg.wait_for_timeout(600)
    ok('shop: a dot on the Rig and Crew tabs shows there is something to buy', pg.query_selector('#tb-rig .dot') is not None and pg.query_selector('#tb-crew .dot') is not None, pg.inner_html('#tb-rig'))
    pg.click('#tb-rig')
    pg.wait_for_timeout(600)
    ok('shop: opening the tab takes its dot away', pg.query_selector('#tb-rig .dot') is None)
    ok('shop: console clean', not logs, logs)
    close(ctx)

    # ---- settings: sound, calm mode, save code out and in, reset
    ctx, pg, logs = new_page(390, 844, 'light', 2, True, tag='settings')
    pg.evaluate('()=>window.__grime.setState({money:1234,lifetime:5000,stars:{driveway:3}, up:{pressure:2,area:1,tank:0,reach:0,flow:0}})')
    pg.click('#setBtn')
    ok('settings: the button opens the settings dialog', pg.is_visible('#setModal'))
    ok('settings: the board behind it is inert while it is open', pg.evaluate('()=>document.getElementById("app").inert===true'))
    pg.click('#togSound')
    ok('settings: the sound switch turns sound off and keeps it', st(pg)['set']['sound'] is False and pg.get_attribute('#togSound', 'aria-pressed') == 'false' and pg.inner_text('#togSound') == 'Off')
    ok('settings: the header sound button follows the switch', pg.get_attribute('#muteBtn', 'aria-pressed') == 'true' and 'Sound off' in pg.get_attribute('#muteBtn', 'aria-label'))
    pg.click('#togCalm')
    ok('settings: calm mode switches on and sets the page class', st(pg)['set']['calm'] is True and pg.evaluate('()=>document.documentElement.classList.contains("calm")'))
    pg.click('#expBtn')
    code = pg.input_value('#saveText')
    ok('settings: export puts a GT1 code in the box', re.fullmatch(r'GT1\.[A-Za-z0-9_-]+\.[a-z0-9]+', code) is not None, code[:20])
    imp = rpc([('importCode', [code])])[0]
    live = st(pg)
    ok('settings: the code holds the live state (read back by the pure importer)', imp['ok'] and all(imp['state'][k] == live[k] for k in ('money', 'lifetime', 'stars', 'up', 'gear', 'crew', 'trucks', 'fp', 'color', 'set')), imp)
    pg.fill('#saveText', code[:-1] + ('0' if code[-1] != '0' else '1'))
    pg.click('#impBtn')
    ok('settings: an edited code is refused as damaged', 'damaged' in pg.inner_text('#saveMsg').lower(), pg.inner_text('#saveMsg'))
    pg.evaluate('()=>window.__grime.setState({money:5})')
    pg.fill('#saveText', code)
    pg.click('#impBtn')
    ok('settings: import asks for a second tap before replacing progress', 'again' in pg.inner_text('#impBtn').lower() and st(pg)['money'] == 5)
    pg.click('#impBtn')
    s = st(pg)
    ok('settings: the second tap restores cash, stars and rig from the code', abs(s['money'] - 1234) < 1e-6 and s['stars'].get('driveway') == 3 and s['up']['pressure'] == 2 and s['set']['sound'] is False and s['set']['calm'] is True, s)
    pg.click('#resetBtn')
    ok('settings: the first reset tap keeps everything', st(pg)['up']['pressure'] == 2 and 'again' in pg.inner_text('#resetBtn').lower())
    pg.click('#resetBtn')
    s = st(pg)
    ok('settings: the second reset tap wipes the game', s['money'] == 0 and s['up']['pressure'] == 0 and s['stars'] == {} and s['fp'] == 0 and s['crew']['apprentice'] == 0, s)
    ok('settings: reset closes settings and starts the tutorial job', not pg.is_visible('#setModal') and pg.evaluate('()=>window.__grime.G()&&window.__grime.G().job.id') == 'driveway')
    ok('settings: console clean', not logs, logs)
    close(ctx)


# ================================================================== save: reload, time away, a clock that jumps, damaged saves
def t_save():
    D = pure_data()
    UP0, GEAR0, CREW0 = zeros(D)
    ctx, pg, logs = new_page(390, 844, 'light', 2, True, tag='save')
    start = {'money': 777, 'lifetime': 900, 'earned': 900, 'stars': {'driveway': 2}, 'up': {'pressure': 3, 'area': 2, 'tank': 1, 'reach': 0, 'flow': 1},
             'gear': dict(GEAR0, soap=True), 'crew': dict(CREW0, apprentice=5, tech=2), 'trucks': 1, 'tut': True, 'color': 'sun'}
    pg.evaluate('(d)=>window.__grime.setState(d)', start)
    pg.evaluate('()=>window.__grime.save()')
    pg.reload()
    pg.wait_for_timeout(500)
    s = st(pg)
    ok('save: a reload keeps cash, rig, gear, crew, trucks and stars', abs(s['money'] - 777) < 5 and s['up'] == start['up'] and s['crew'] == start['crew'] and s['trucks'] == 1 and s['gear'] == start['gear'] and s['stars'] == start['stars'], s)
    ok('save: the stored text is JSON with the current version and the same fields', saved(pg).get('v') == 1 and set(saved(pg)) == set(s))
    ok('save: no welcome back panel right after a reload', not pg.is_visible('#backNote'))
    inc = pure(pg, 'P.crewIncome(%s)' % json.dumps(s))

    def ago(h):
        return lambda d: d.__setitem__('savedAt', now_ms() - int(h * 3600 * 1000))
    d = edit_save(pg, ago(3))
    s2 = st(pg)
    gained = s2['money'] - d['money']
    ok('save: three hours away shows the welcome back panel', pg.is_visible('#backNote'))
    txt = pg.inner_text('#backText')
    ok('save: the panel says three hours and the money earned in the shared format', '3 hours' in txt and fmt_near(txt, gained), txt)
    ok('save: the credit is the crew income times the time away (within a minute of rounding)', abs(gained - inc * 10800) <= inc * 60 + 1e-6, (gained, inc * 10800))
    ok('save: lifetime and earned grow by the same credit as the money', abs((s2['lifetime'] - d['lifetime']) - gained) < 1e-6 and abs((s2['earned'] - d['earned']) - gained) < 1e-6, (s2['lifetime'] - d['lifetime'], s2['earned'] - d['earned'], gained))
    pg.click('#backOk')
    ok('save: the panel can be dismissed', not pg.is_visible('#backNote'))
    d = edit_save(pg, ago(30))
    s3 = st(pg)
    gained = s3['money'] - d['money']
    ok('save: thirty hours away is capped at five hours with one truck', abs(gained - inc * 5 * 3600) <= inc * 60 + 1e-6, (gained, inc * 18000))
    ok('save: the panel says the cap was hit', 'cap' in pg.inner_text('#backText').lower(), pg.inner_text('#backText'))
    d = edit_save(pg, ago(-5))
    s4 = st(pg)
    ok('save: a clock set backwards gives nothing and shows no panel', abs(s4['money'] - d['money']) < 5 and not pg.is_visible('#backNote'), (s4['money'], d['money']))
    d = edit_save(pg, lambda d: d.__setitem__('savedAt', now_ms() - 30 * 1000))
    ok('save: under a minute away shows no panel', not pg.is_visible('#backNote'))
    d = edit_save(pg, lambda d: d.update(crew=dict(CREW0), savedAt=now_ms() - 5 * 3600 * 1000))
    ok('save: no crew means nothing earned and no panel', not pg.is_visible('#backNote') and abs(st(pg)['money'] - d['money']) < 1e-6)
    d = edit_save(pg, lambda d: d.update(crew=dict(CREW0, tech=1), trucks=0, savedAt=now_ms() - 20 * 3600 * 1000))
    ok('save: with no truck the cap is four hours', abs((st(pg)['money'] - d['money']) - D['crew'][1]['inc'] * 4 * 3600) <= D['crew'][1]['inc'] * 60 + 1e-6, (st(pg)['money'], d['money']))
    ok('save: console clean (reload and time away)', not logs, logs)
    close(ctx)

    # ---- the crew pays while the page is open
    ctx, pg, logs = new_page(390, 844, 'light', 2, True, tag='income tick')
    pg.evaluate('(d)=>window.__grime.setState(d)', {'tut': True, 'money': 0, 'lifetime': 0, 'earned': 0, 'crew': dict(CREW0, apprentice=60), 'trucks': 0})
    inc = pure(pg, 'P.crewIncome(window.__grime.state())')
    a = pg.evaluate('()=>[Date.now(), window.__grime.state().money]')
    pg.wait_for_timeout(2600)
    b = pg.evaluate('()=>[Date.now(), window.__grime.state().money]')
    el = (b[0] - a[0]) / 1000.0
    gained = b[1] - a[1]
    ok('save: the crew pays its income every second while the page is open (%.0f/s over %.1f s)' % (inc, el), inc * (el - 0.8) <= gained <= inc * (el + 0.3), (gained, inc * el))
    close(ctx)

    # ---- the clock jumps while the page is open (laptop lid shut, tab asleep)
    ctx, pg, logs = new_page(390, 844, 'light', 2, True, tag='clock jump', pre=lambda p: p.clock.install())
    pg.evaluate('(d)=>window.__grime.setState(d)', {'tut': True, 'money': 0, 'lifetime': 0, 'earned': 0, 'crew': dict(CREW0, apprentice=10), 'trucks': 0})
    inc = pure(pg, 'P.crewIncome(window.__grime.state())')
    m0 = st(pg)['money']
    pg.clock.fast_forward('03:00:00')
    pg.wait_for_timeout(600)
    gained = st(pg)['money'] - m0
    ok('save: three hours pass in one jump and the crew pays three hours', 10800 * inc <= gained <= 10800 * inc + 3 * inc, (gained, 10800 * inc))
    ok('save: and the welcome back panel appears with the time in words', pg.is_visible('#backNote') and '3 hours' in pg.inner_text('#backText'), pg.inner_text('#backText'))
    pg.click('#backOk')
    m1 = st(pg)['money']
    pg.clock.fast_forward('30:00:00')
    pg.wait_for_timeout(600)
    gained = st(pg)['money'] - m1
    ok('save: thirty hours in one jump are capped at four hours without trucks', 14400 * inc <= gained <= 14400 * inc + 3 * inc, (gained, 14400 * inc))
    ok('save: the panel says the cap was hit', 'cap' in pg.inner_text('#backText').lower(), pg.inner_text('#backText'))
    m2 = st(pg)['money']
    now = pg.evaluate('()=>Date.now()')
    pg.clock.set_system_time((now - 3600 * 1000) / 1000.0)      # the Python API takes seconds
    pg.wait_for_timeout(700)
    gained = st(pg)['money'] - m2
    ok('save: the clock set back one hour pays nothing for the lost hour', 0 <= gained <= 3 * inc, (gained, inc))
    ok('save: console clean (clock jumps)', not logs, logs)
    close(ctx)

    # ---- damaged saves
    ctx, pg, logs = new_page(390, 844, 'light', 2, True, tag='damaged saves')
    put_raw(pg, '{not json at all')
    s = st(pg)
    ok('damaged save: the game starts fresh', s['money'] == 0 and s['fp'] == 0 and sum(s['up'].values()) == 0 and s['stars'] == {})
    ok('damaged save: the unreadable text is kept under the backup key', pg.evaluate("(k)=>localStorage.getItem(k)", STORE + '-backup') == '{not json at all')
    ok('damaged save: the board still shows the jobs', pg.is_visible('#tab-jobs') and len(pg.query_selector_all('#jobList > *')) == len(D['jobs']), len(pg.query_selector_all('#jobList > *')))
    put_raw(pg, json.dumps({'v': 1, 'money': 'abc', 'up': 'x', 'crew': [1, 2], 'stars': {'driveway': 99, 'zzz': 3}, 'fp': -5, 'color': 'nope', 'set': 5, 'trucks': 99999}))
    s = st(pg)
    ok('damaged save: wrong shapes are cleaned up, not trusted', s['money'] == 0 and s['fp'] == 0 and s['stars'] == {'driveway': 3} and s['trucks'] == D['trucks']['max'] and s['color'] == 'sun' and s['set'] == {'sound': True, 'calm': False}, s)
    put_raw(pg, json.dumps({'v': 99, 'money': 5000, 'lifetime': 5000}))
    ok('damaged save: a save from a newer version does not break the page and starts fresh', pg.is_visible('#board') and st(pg)['money'] == 0)
    ok('damaged save: that save is also kept under the backup key', json.loads(pg.evaluate("(k)=>localStorage.getItem(k)", STORE + '-backup'))['v'] == 99)
    put_raw(pg, json.dumps({'v': 1, 'money': 1e40, 'lifetime': -3, 'crew': {'apprentice': 'lots', 'tech': -4}, 'up': {'pressure': 1e9}, 'tut': 'yes'}))
    s = st(pg)
    ok('damaged save: huge, negative and text values are clamped', s['money'] == 1e30 and s['lifetime'] == 0 and sum(s['crew'].values()) == 0 and s['up']['pressure'] == 10 and s['tut'] is False, s)
    ok('damaged save: console clean', not logs, logs)
    close(ctx)


def fmt_near(text, amount):
    """The panel's money text is one of the formats of the amount (the amount moves a little with the clock)."""
    m = re.search(r'earned (\$[0-9.]+[A-Za-z]*) in', text)
    if not m:
        return False
    x = X(amount)
    return any(m.group(1) in accept(ref_money, x * f) for f in (Fraction(1), Fraction(1001, 1000), Fraction(999, 1000)))


# ================================================================== storage that fails: the game must still play
BLOCK_GET = """(function(){var t=function(){throw new DOMException('blocked','SecurityError')};try{Object.defineProperty(window,'localStorage',{get:t,configurable:true})}catch(e){}})();"""
BLOCK_SET = """(function(){Storage.prototype.setItem=function(){throw new DOMException('full','QuotaExceededError')}})();"""


def t_storage():
    D = pure_data()
    ctx, pg, logs = new_page(390, 844, 'light', 2, True, hash='', init=[BLOCK_GET], tag='storage blocked, first visit')
    pg.wait_for_timeout(500)
    ok('blocked storage: the first visit still opens the tutorial job', pg.is_visible('#wash') and pg.is_visible('#wTut'))
    ok('blocked storage: no error on first visit', not logs, logs)
    close(ctx)
    ctx, pg, logs = new_page(390, 844, 'light', 2, True, init=[BLOCK_GET], tag='storage blocked')
    pg.evaluate('()=>window.__grime.grant(5000)')
    pg.click('#tb-rig')
    pg.click('[data-key="up-pressure"]')
    ok('blocked storage: buying still works', st(pg)['up']['pressure'] == 1)
    pg.click('#setBtn')
    pg.click('#expBtn')
    ok('blocked storage: the save code can still be made', pg.input_value('#saveText').startswith('GT1.'))
    pg.click('#setClose')
    pg.evaluate('()=>window.__grime.save()')
    pg.evaluate("()=>{document.dispatchEvent(new Event('visibilitychange'));window.dispatchEvent(new Event('pagehide'))}")
    ok('blocked storage: saving and leaving do not throw', not logs, logs)
    close(ctx)
    ctx, pg, logs = new_page(390, 844, 'light', 2, True, init=[BLOCK_SET], tag='storage full')
    pg.evaluate('()=>window.__grime.grant(5000)')
    pg.click('#tb-rig')
    pg.click('[data-key="up-pressure"]')
    pg.evaluate('()=>window.__grime.save()')
    pg.evaluate("()=>window.dispatchEvent(new Event('pagehide'))")
    ok('full storage: the game keeps working', st(pg)['up']['pressure'] == 1)
    ok('full storage: no error is thrown', not logs, logs)
    close(ctx)
    # no storage at all is not the same as a throwing one: a page where the property is missing
    ctx, pg, logs = new_page(390, 844, 'light', 2, True, init=["(function(){try{Object.defineProperty(window,'localStorage',{value:undefined,configurable:true})}catch(e){}})();"], tag='storage missing')
    pg.evaluate('()=>window.__grime.grant(5000)')
    pg.click('#tb-rig')
    pg.click('[data-key="up-pressure"]')
    ok('missing storage: the game plays and no error is thrown', st(pg)['up']['pressure'] == 1 and not logs, logs)
    close(ctx)


# ================================================================== keyboard: aim, spray, tips, pause, result dialog, settings dialog
def aim(pg):
    return pg.evaluate('()=>[window.__grime.inp.x, window.__grime.inp.y]')


def active_id(pg):
    return pg.evaluate('()=>document.activeElement&&document.activeElement.id')


def t_keyboard():
    D = pure_data()
    ctx, pg, logs = new_page(1280, 800, 'light', 1, False, tag='keyboard')
    pg.evaluate('()=>window.__grime.setState({tut:true,up:{pressure:6,area:6,tank:6,reach:0,flow:0}})')
    pg.evaluate('()=>window.__grime.start("driveway")')
    pg.wait_for_timeout(300)
    left0 = gev(pg, 'window.__grime.G().w.left')
    x0, y0 = aim(pg)
    pg.keyboard.down('ArrowRight')
    pg.keyboard.down(' ')
    pg.wait_for_timeout(1500)
    pg.keyboard.up(' ')
    pg.keyboard.up('ArrowRight')
    x1, y1 = aim(pg)
    left1 = gev(pg, 'window.__grime.G().w.left')
    ok('keyboard: the right arrow moves the aim right', x1 > x0 + 200 and abs(y1 - y0) < 1, (x0, x1))
    ok('keyboard: the space bar sprays and removes grime', left1 < left0, (left0, left1))
    pg.keyboard.down('a')
    pg.wait_for_timeout(500)
    pg.keyboard.up('a')
    x2, _ = aim(pg)
    pg.keyboard.down('w')
    pg.wait_for_timeout(400)
    pg.keyboard.up('w')
    ok('keyboard: A moves left and W moves up like the arrows', x2 < x1 and aim(pg)[1] < y1, (x1, x2, aim(pg)[1], y1))
    lo = aim(pg)
    pg.keyboard.down('ArrowLeft')
    pg.keyboard.down('ArrowUp')
    pg.wait_for_timeout(2500)
    pg.keyboard.up('ArrowLeft')
    pg.keyboard.up('ArrowUp')
    ok('keyboard: the aim stops at the edge of the scene', aim(pg) == [0, 0], aim(pg))
    for k, tip in enumerate(D['tips'][:4]):
        pg.keyboard.press(str(k + 1))
        ok('keyboard: key %d picks the %s tip' % (k + 1, tip['id']), gev(pg, 'window.__grime.G().s.tip.id') == tip['id'] and pg.get_attribute('.tipbtn[data-tip="%s"]' % tip['id'], 'aria-pressed') == 'true')
    pg.keyboard.press('5')
    ok('keyboard: the soap key needs the soap tip first and says so', 'Soap tip' in pg.inner_text('#toast') and gev(pg, 'window.__grime.G().s.tip.id') == 'white', pg.inner_text('#toast'))
    pg.keyboard.press('6')
    ok('keyboard: the disc key does nothing without the surface cleaner', gev(pg, 'window.__grime.G().surfMode') is False)
    pg.evaluate('()=>window.__grime.setState({gear:{soap:true,hot:false,pole:false,surface:true}})')
    pg.keyboard.press('5')
    ok('keyboard: with the soap tip owned the soap key selects it', gev(pg, 'window.__grime.G().s.tip.id') == 'soap')
    pg.keyboard.press('6')
    ok('keyboard: with the surface cleaner owned the 6 key selects the disc', gev(pg, 'window.__grime.G().surfMode') is True)
    pg.keyboard.press('4')
    ok('keyboard: picking a tip again leaves the disc', gev(pg, 'window.__grime.G().surfMode') is False and gev(pg, 'window.__grime.G().s.tip.id') == 'white')
    pg.keyboard.press('Escape')
    pg.wait_for_timeout(200)
    ok('keyboard: Escape pauses and shows the pause panel', pg.is_visible('#wPause') and gev(pg, 'window.__grime.G().paused'))
    ok('keyboard: focus moves to the Resume button', active_id(pg) == 'resumeBtn', active_id(pg))
    xp = aim(pg)
    pg.keyboard.down('ArrowRight')
    pg.wait_for_timeout(300)
    pg.keyboard.up('ArrowRight')
    ok('keyboard: the aim does not move while paused', aim(pg) == xp)
    pg.keyboard.press('Enter')
    pg.wait_for_timeout(200)
    ok('keyboard: Enter on Resume continues', not gev(pg, 'window.__grime.G().paused') and not pg.is_visible('#wPause'))
    pg.keyboard.press('p')
    ok('keyboard: P pauses', gev(pg, 'window.__grime.G().paused'))
    pg.keyboard.press('p')
    ok('keyboard: P resumes', not gev(pg, 'window.__grime.G().paused'))
    ok('keyboard: console clean (aim, spray, pause)', not logs, logs)
    # the result dialog
    pg.evaluate('()=>window.__grime.finish()')
    pg.wait_for_timeout(2600)
    ok('keyboard: the result dialog appears when the job is done', pg.is_visible('#result'))
    ok('keyboard: focus is inside the result dialog', pg.evaluate('()=>document.getElementById("result").contains(document.activeElement)'))
    inside = []
    for _ in range(10):
        pg.keyboard.press('Tab')
        inside.append(pg.evaluate('()=>document.getElementById("result").contains(document.activeElement)'))
    ok('keyboard: Tab never leaves the result dialog', all(inside), inside)
    inside = []
    for _ in range(10):
        pg.keyboard.press('Shift+Tab')
        inside.append(pg.evaluate('()=>document.getElementById("result").contains(document.activeElement)'))
    ok('keyboard: Shift+Tab never leaves it either', all(inside), inside)
    pg.wait_for_timeout(1400)
    pg.focus('#ba')
    ok('keyboard: the before and after picture is a labelled slider', pg.get_attribute('#ba', 'role') == 'slider' and bool(pg.get_attribute('#ba', 'aria-label')))
    v0 = int(pg.get_attribute('#ba', 'aria-valuenow'))
    pg.keyboard.press('ArrowRight')
    v1 = int(pg.get_attribute('#ba', 'aria-valuenow'))
    pg.keyboard.press('End')
    v2 = int(pg.get_attribute('#ba', 'aria-valuenow'))
    pg.keyboard.press('Home')
    v3 = int(pg.get_attribute('#ba', 'aria-valuenow'))
    pg.keyboard.press('ArrowLeft')
    v4 = int(pg.get_attribute('#ba', 'aria-valuenow'))
    ok('keyboard: arrows move the slider by 5, End and Home go to the ends, it never passes them', (v1, v2, v3, v4) == (v0 + 5, 100, 0, 0), (v0, v1, v2, v3, v4))
    ok('keyboard: the slider says in words what it shows', pg.get_attribute('#ba', 'aria-valuetext') == 'Mostly after')
    pg.keyboard.press('Escape')
    pg.wait_for_timeout(300)
    ok('keyboard: Escape on the result goes to the shop', not pg.is_visible('#result') and not pg.is_visible('#wash') and pg.get_attribute('#tb-rig', 'aria-selected') == 'true' and active_id(pg) == 'tb-rig', active_id(pg))
    ok('keyboard: console clean (result dialog)', not logs, logs)
    # the tabs by arrow keys
    pg.focus('#tb-rig')
    pg.keyboard.press('ArrowRight')
    ok('keyboard: the right arrow moves to the next tab and focuses it', pg.get_attribute('#tb-crew', 'aria-selected') == 'true' and active_id(pg) == 'tb-crew')
    pg.keyboard.press('End')
    ok('keyboard: End goes to the last tab', pg.get_attribute('#tb-fran', 'aria-selected') == 'true')
    pg.keyboard.press('ArrowRight')
    ok('keyboard: the tabs wrap around', pg.get_attribute('#tb-jobs', 'aria-selected') == 'true')
    pg.keyboard.press('Home')
    pg.keyboard.press('ArrowLeft')
    ok('keyboard: the left arrow wraps to the last tab', pg.get_attribute('#tb-fran', 'aria-selected') == 'true')
    close(ctx)

    # ---- settings dialog: focus stays inside, Escape closes, focus goes back
    ctx, pg, logs = new_page(1280, 800, 'light', 1, False, tag='keyboard settings')
    pg.focus('#setBtn')
    pg.keyboard.press('Enter')
    ok('keyboard: Enter on the settings button opens it', pg.is_visible('#setModal'))
    inside = []
    for _ in range(14):
        pg.keyboard.press('Tab')
        inside.append(pg.evaluate('()=>document.getElementById("setModal").contains(document.activeElement)'))
    ok('keyboard: Tab stays inside the settings dialog', all(inside), inside)
    pg.keyboard.press('Escape')
    ok('keyboard: Escape closes settings and focus goes back to the settings button', not pg.is_visible('#setModal') and active_id(pg) == 'setBtn', active_id(pg))
    ok('keyboard: the board is live again after the dialog closes', pg.evaluate('()=>document.getElementById("app").inert===false'))
    ok('keyboard: console clean (settings)', not logs, logs)
    close(ctx)

    # ---- pause and leave on a phone: the leave button needs two taps
    ctx, pg, logs = new_page(390, 844, 'light', 2, True, tag='pause leave')
    pg.evaluate('()=>window.__grime.setState({tut:true})')
    pg.evaluate('()=>window.__grime.start("driveway")')
    pg.wait_for_timeout(300)
    pg.click('#pauseBtn')
    ok('pause: the pause button pauses and shows the panel', pg.is_visible('#wPause') and gev(pg, 'window.__grime.G().paused'))
    t0 = pg.evaluate('()=>window.__grime.G().w.secs')
    pg.wait_for_timeout(500)
    ok('pause: the wash clock stands still while paused', pg.evaluate('()=>window.__grime.G().w.secs') == t0)
    pg.click('#leaveBtn')
    ok('pause: the first tap on Leave only asks again', pg.is_visible('#wash') and 'again' in pg.inner_text('#leaveBtn').lower(), pg.inner_text('#leaveBtn'))
    pg.click('#leaveBtn')
    pg.wait_for_timeout(300)
    ok('pause: the second tap returns to the board', not pg.is_visible('#wash') and pg.is_visible('#board') and pg.evaluate('()=>window.__grime.G()') is None)
    ok('pause: nothing was paid for a job that was left', st(pg)['money'] == 0 and st(pg)['jobs'] == 0)
    pg.evaluate('()=>window.__grime.start("driveway")')
    pg.wait_for_timeout(300)
    ok('pause: a new job can be started after leaving', pg.is_visible('#wash') and gev(pg, 'window.__grime.G().phase') == 'play')
    ok('pause: console clean', not logs, logs)
    close(ctx)


# ================================================================== input: real mouse, real touch, first visit, save code box
RIG_MID = {'pressure': 6, 'area': 6, 'tank': 8, 'reach': 0, 'flow': 0}


def t_input():
    # ---- mouse: hover only aims, press and drag washes the job to the end
    ctx, pg, logs = new_page(1280, 800, 'light', 1, False, tag='mouse')
    pg.evaluate("(r)=>window.__grime.setState({tut:true,up:r,gear:{soap:true,hot:true,pole:true,surface:false}})", RIG_MID)
    pg.evaluate("()=>window.__grime.start('driveway')")
    pg.wait_for_timeout(300)
    m = pg.evaluate(MAP_JS)
    m0 = st(pg)['money']
    left0 = gev(pg, 'window.__grime.G().w.left')
    x, y = to_client(m, m['W'] * 0.5, m['H'] * 0.5)
    pg.mouse.move(x, y)
    pg.wait_for_timeout(200)
    ok('mouse: hovering shows the aim and sprays nothing', gev(pg, 'window.__grime.G().w.left') == left0 and gev(pg, 'window.__grime.inp.aim') is True)
    t0 = time.time()
    row = 0
    done = False
    while time.time() - t0 < 60 and not done:
        yy = m['H'] * (0.04 + 0.05 * (row % 19))
        xa, xb = (0.02, 0.98) if row % 2 == 0 else (0.98, 0.02)
        ax, ay = to_client(m, m['W'] * xa, yy)
        bx, by = to_client(m, m['W'] * xb, yy)
        pg.mouse.move(ax, ay)
        pg.mouse.down()
        for k in range(1, 21):
            pg.mouse.move(ax + (bx - ax) * k / 20, ay + (by - ay) * k / 20)
            pg.wait_for_timeout(12)
        pg.mouse.up()
        row += 1
        done = gev(pg, 'window.__grime.G().phase') in ('tidy', 'done')
    pg.wait_for_timeout(2500)
    ok('mouse: press and drag washes the job to done (%d rows, %.0f s)' % (row, time.time() - t0), gev(pg, 'window.__grime.G().phase') == 'done', gev(pg, 'window.__grime.G().phase'))
    ok('mouse: the result dialog is shown', pg.is_visible('#result'))
    s = st(pg)
    ok('mouse: the job paid and the first star is earned', s['money'] > m0 and s['stars'].get('driveway', 0) >= 1 and s['jobs'] == 1, (m0, s['money'], s['stars']))
    ok('mouse: the result rows list base pay and the total', 'Base pay' in pg.inner_text('#rRows') and 'Total' in pg.inner_text('#rRows'))
    total_txt = pg.evaluate("()=>[...document.querySelectorAll('#rRows .r-row.total dd')].map(e=>e.textContent)")
    ok('mouse: the total in the result equals the money gained', len(total_txt) == 1 and total_txt[0] in accept(ref_money, X(s['money'] - m0)), (total_txt, s['money'] - m0))
    ok('mouse: console clean', not logs, logs)
    close(ctx)

    # ---- touch: the spray sits above the finger, the bottom edge is reachable, a second finger is ignored
    ctx, pg, logs = new_page(390, 844, 'light', 2, True, tag='touch')
    pg.evaluate("(r)=>window.__grime.setState({tut:true,up:r})", RIG_MID)
    pg.evaluate("()=>window.__grime.start('driveway')")
    pg.wait_for_timeout(300)
    m = pg.evaluate(MAP_JS)
    cdp = ctx.new_cdp_session(pg)

    def touch(kind, x, y):
        pts = [] if kind == 'touchEnd' else [{'x': x, 'y': y, 'id': 1}]
        cdp.send('Input.dispatchTouchEvent', {'type': kind, 'touchPoints': pts})
    left0 = gev(pg, 'window.__grime.G().w.left')
    cx, cy = to_client(m, m['W'] * 0.5, m['H'] * 0.45)
    touch('touchStart', cx, cy)
    pg.wait_for_timeout(60)
    iy = gev(pg, 'window.__grime.inp.y')
    gy = m['t'] + m['oy'] + iy * m['sc']
    ok('touch: the spray lands about 56 px above the finger', abs((cy - gy) - 56) < 6, (cy, gy))
    for k in range(1, 41):
        touch('touchMove', cx + 120 * (k / 40.0), cy)
        pg.wait_for_timeout(14)
    touch('touchEnd', 0, 0)
    ok('touch: dragging removes grime', gev(pg, 'window.__grime.G().w.left') < left0, (left0, gev(pg, 'window.__grime.G().w.left')))
    ok('touch: the spray stops when the finger lifts', gev(pg, '!window.__grime.inp.down'))
    bx_, by_ = to_client(m, m['W'] * 0.5, m['H'] * 0.995)
    touch('touchStart', bx_, by_)
    pg.wait_for_timeout(60)
    ok('touch: the lift fades near the bottom so the bottom edge is reachable', gev(pg, 'window.__grime.inp.y') > m['H'] * 0.93, (gev(pg, 'window.__grime.inp.y'), m['H']))
    touch('touchEnd', 0, 0)
    touch('touchStart', cx, cy)
    pg.wait_for_timeout(40)
    cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': cx, 'y': cy, 'id': 1}, {'x': cx + 80, 'y': cy + 40, 'id': 2}]})
    pg.wait_for_timeout(40)
    ok('touch: a second finger does not break the aim', gev(pg, 'window.__grime.inp.down') is True)
    touch('touchEnd', 0, 0)
    pg.wait_for_timeout(100)
    ok('touch: nothing scrolls the page while washing (the wash view is locked)', pg.evaluate('()=>document.documentElement.classList.contains("locked") && window.scrollY===0'))
    ok('touch: console clean', not logs, logs)
    close(ctx)

    # ---- first visit, no hooks: the tutorial job opens by itself and a real press moves it on
    ctx, pg, logs = new_page(390, 844, 'light', 2, True, hash='', wait=900, tag='first visit')
    ok('first visit: the wash view opens with the tutorial card', pg.is_visible('#wash') and pg.is_visible('#wTut'))
    ok('first visit: the card says to drag', pg.inner_text('#wTutB').lower() == 'drag to spray' and 'wipe' in pg.inner_text('#wTutS').lower(), (pg.inner_text('#wTutB'), pg.inner_text('#wTutS')))
    ok('first visit: the test hooks do not exist without #test', pg.evaluate('()=>typeof window.__grime') == 'undefined')
    r = pg.evaluate("()=>{const e=document.getElementById('cFx').getBoundingClientRect();return [e.left+e.width*0.3,e.top+e.height*0.4]}")
    pg.mouse.move(r[0], r[1])
    pg.mouse.down()
    pg.mouse.move(r[0] + 60, r[1] + 5, steps=6)
    pg.wait_for_timeout(200)
    ok('first visit: pressing moves the card on to Keep moving', pg.inner_text('#wTutB').lower() == 'keep moving', pg.inner_text('#wTutB'))
    pg.mouse.up()
    ok('first visit: the progress was not saved before the job is done', not saved(pg).get('tut'))
    ok('first visit: console clean', not logs, logs)
    close(ctx)

    # ---- the save code box: empty, junk, huge, wrong version, spaces
    ctx, pg, logs = new_page(390, 844, 'light', 2, True, tag='import junk')
    pg.evaluate('()=>window.__grime.setState({money:4321,lifetime:4321,up:{pressure:4,area:0,tank:0,reach:0,flow:0}})')
    pg.click('#setBtn')
    pg.click('#expBtn')
    code = pg.input_value('#saveText')
    pg.fill('#saveText', '')
    pg.click('#impBtn')
    ok('import: an empty box asks for a code', 'Paste a save code' in pg.inner_text('#saveMsg'), pg.inner_text('#saveMsg'))
    pg.fill('#saveText', 'hello there')
    pg.click('#impBtn')
    ok('import: text that is not a code is refused', 'does not look like' in pg.inner_text('#saveMsg'), pg.inner_text('#saveMsg'))
    pg.fill('#saveText', 'GT2' + code[3:])
    pg.click('#impBtn')
    ok('import: a code with another version prefix is refused', 'does not look like' in pg.inner_text('#saveMsg'))
    pg.fill('#saveText', 'GT1.' + 'A' * 2000000 + '.zz')
    t1 = time.time()
    pg.click('#impBtn')
    ok('import: a two megabyte box is refused quickly', 'damaged' in pg.inner_text('#saveMsg').lower() and time.time() - t1 < 5, time.time() - t1)
    pg.fill('#saveText', code[:40])
    pg.click('#impBtn')
    ok('import: a cut off code is refused', 'does not look like' in pg.inner_text('#saveMsg') or 'damaged' in pg.inner_text('#saveMsg').lower(), pg.inner_text('#saveMsg'))
    ok('import: none of that changed the game', st(pg)['money'] == 4321 or abs(st(pg)['money'] - 4321) < 1, st(pg)['money'])
    spaced = '  ' + code[:25] + '\n' + code[25:50] + ' \t' + code[50:] + '  \n'
    pg.fill('#saveText', spaced)
    pg.click('#impBtn')
    ok('import: spaces and line breaks added by a messenger are ignored (the code is accepted)', 'again' in pg.inner_text('#impBtn').lower() and 'good' in pg.inner_text('#saveMsg').lower(), pg.inner_text('#saveMsg'))
    pg.wait_for_timeout(4300)
    ok('import: the armed button disarms itself after a few seconds', 'again' not in pg.inner_text('#impBtn').lower(), pg.inner_text('#impBtn'))
    # the copy sheet when the clipboard refuses
    pg.evaluate("()=>{Object.defineProperty(navigator,'clipboard',{value:{writeText:function(){return Promise.reject(new Error('no'))}},configurable:true})}")
    pg.click('#expBtn')
    pg.wait_for_timeout(400)
    sheet = pg.is_visible('#sheet') and pg.input_value('#sheetText') == pg.input_value('#saveText')
    ok('import: if the clipboard refuses, the code is shown to copy by hand (or the copy still worked)', sheet or 'copied' in pg.inner_text('#toast'), (pg.is_visible('#sheet'), pg.inner_text('#toast')))
    ok('import: console clean', not logs, logs)
    close(ctx)


# ================================================================== share: a whole job by keyboard, the picture, Web Share
def t_share():
    ctx, pg, logs = new_page(1280, 800, 'light', 1, False, hash='', path=BLANK_PATH, downloads=True, tag='keyboard job and share')
    state = {'v': 1, 'money': 0, 'lifetime': 0, 'earned': 0, 'stars': {}, 'up': {'pressure': 10, 'area': 10, 'tank': 4, 'reach': 0, 'flow': 0}, 'gear': {}, 'crew': {},
             'trucks': 0, 'fp': 0, 'cycles': 0, 'color': 'sun', 'savedAt': now_ms(), 'tut': True, 'jobs': 0, 'set': {'sound': True, 'calm': False}}
    pg.evaluate("(a)=>localStorage.setItem(a[0], a[1])", [STORE, json.dumps(state)])
    pg.goto(ORIGIN + PAGE_PATH)
    pg.wait_for_timeout(700)
    found = False
    for _ in range(40):
        pg.keyboard.press('Tab')
        if pg.evaluate("()=>document.activeElement&&document.activeElement.getAttribute('data-key')") == 'job-driveway':
            found = True
            break
    ok('share: Tab reaches the first job card', found)
    ok('share: the focus ring is visible on the job card', pg.evaluate("()=>{const s=getComputedStyle(document.activeElement);return s.outlineStyle!=='none'&&parseFloat(s.outlineWidth)>=2}"))
    pg.keyboard.press('Enter')
    pg.wait_for_timeout(1200)
    ok('share: Enter starts the job', pg.is_visible('#wash'))
    pg.keyboard.down('ArrowLeft')
    pg.keyboard.down('ArrowUp')
    pg.wait_for_timeout(3600)
    pg.keyboard.up('ArrowLeft')
    pg.keyboard.up('ArrowUp')
    pg.keyboard.press('4')
    pg.keyboard.down(' ')
    t0, d, rows, done, vd = time.time(), 'ArrowRight', 0, False, 'ArrowDown'
    while time.time() - t0 < 150 and not done:
        pg.keyboard.down(d)
        t1 = time.time()
        while time.time() - t1 < 3.2:
            pg.wait_for_timeout(120)
            if pg.is_visible('#result'):
                done = True
                break
        pg.keyboard.up(d)
        if done:
            break
        pg.keyboard.down(vd)
        pg.wait_for_timeout(130)
        pg.keyboard.up(vd)
        d = 'ArrowLeft' if d == 'ArrowRight' else 'ArrowRight'
        rows += 1
        if rows % 10 == 0:
            vd = 'ArrowUp' if vd == 'ArrowDown' else 'ArrowDown'
    pg.keyboard.up(' ')
    pg.wait_for_timeout(3000)
    ok('share: a whole job can be finished with the keyboard only (%d rows, %.0f s)' % (rows, time.time() - t0), pg.is_visible('#result'), pg.inner_text('#wPct'))
    ok('share: focus moved into the result dialog', pg.evaluate("()=>document.getElementById('result').contains(document.activeElement)"))
    ok('share: the result is announced in the live region', 'Job complete' in pg.inner_text('#srRead'), pg.inner_text('#srRead'))
    sv = saved(pg)
    ok('share: the pay and the star were saved', sv.get('money', 0) > 0 and sv['stars'].get('driveway', 0) >= 1 and sv.get('jobs') == 1, sv)
    for _ in range(8):
        if active_id(pg) == 'rShare':
            break
        pg.keyboard.press('Tab')
    ok('share: the Share button is reachable by Tab', active_id(pg) == 'rShare')
    with pg.expect_download(timeout=15000) as dl:
        pg.keyboard.press('Enter')
    d1 = dl.value
    path = str(TMP / 'share_image.png')
    d1.save_as(path)
    im = Image.open(path).convert('RGB')
    ok('share: the picture is a PNG named grime-time.png', d1.suggested_filename == 'grime-time.png' and Image.open(path).format == 'PNG', d1.suggested_filename)
    ok('share: the picture is 1080 x 1350', im.size == (1080, 1350), im.size)
    ok('share: the picture is not blank', ImageStat.Stat(im.convert('L')).stddev[0] > 25)
    p0, p1 = im.getpixel((6, 6)), im.getpixel((1073, 1343))
    ok('share: the picture has the purple gradient of the game (corners)', abs(p0[0] - 74) < 14 and abs(p0[1] - 20) < 14 and abs(p0[2] - 87) < 14 and p1[0] < 40 and p1[1] < 30 and p1[2] < 50, (p0, p1))
    raw = im.crop((200, 1060, 880, 1200)).tobytes()
    yellow = sum(1 for i in range(0, len(raw), 3) if raw[i] > 220 and raw[i + 1] > 170 and raw[i + 2] < 120)
    ok('share: the pay is printed large in yellow', yellow > 3000, yellow)
    ok('share: the toast says where the picture went', 'Picture saved' in pg.inner_text('#toast'), pg.inner_text('#toast'))
    # Web Share with a file where the browser allows it
    pg.evaluate("()=>{window.__shared=null;navigator.canShare=function(d){return !!(d&&d.files&&d.files.length)};navigator.share=function(d){window.__shared={n:d.files.length,type:d.files[0].type,name:d.files[0].name,title:d.title,text:d.text};return Promise.resolve()}}")
    pg.click('#rShare')
    pg.wait_for_timeout(1800)
    sh = pg.evaluate("()=>window.__shared")
    ok('share: Web Share is used with the PNG file when the browser supports it', sh and sh['n'] == 1 and sh['type'] == 'image/png' and sh['name'] == 'grime-time.png' and sh['title'] == 'Grime Time', sh)
    ok('share: the shared text names the job, the pay and the address', sh and 'Driveway' in sh['text'] and '$' in sh['text'] and 'https://sanjixysti-creator.github.io/grime-time/' in sh['text'], sh)
    pg.evaluate("()=>{navigator.share=function(){var e=new Error('x');e.name='AbortError';return Promise.reject(e)}}")
    pg.wait_for_timeout(3400)
    pg.click('#rShare')
    pg.wait_for_timeout(1500)
    ok('share: cancelling the share sheet shows no error', not pg.is_visible('#toast') or 'could not' not in pg.inner_text('#toast').lower())
    pg.evaluate("()=>{navigator.share=function(){var e=new Error('boom');e.name='NotAllowedError';return Promise.reject(e)}}")
    with pg.expect_download(timeout=8000) as dl3:
        pg.click('#rShare')
    ok('share: a share that fails falls back to saving the picture', dl3.value.suggested_filename == 'grime-time.png')
    pg.evaluate("()=>{navigator.canShare=function(){return false}}")
    with pg.expect_download(timeout=8000) as dl4:
        pg.click('#rShare')
    ok('share: a browser that cannot share files gets the download', dl4.value.suggested_filename == 'grime-time.png')
    pg.evaluate("()=>{navigator.canShare=undefined;navigator.share=undefined}")
    with pg.expect_download(timeout=8000) as dl5:
        pg.click('#rShare')
    ok('share: a browser with no Web Share at all gets the download', dl5.value.suggested_filename == 'grime-time.png')
    ok('share: console clean (keyboard job and share)', not logs, logs)
    close(ctx)


# ================================================================== env: what the page does around the game (hooks, sound, motion, tabs, network)
AC_SPY = """(function(){var n=0,A=window.AudioContext||window.webkitAudioContext;window.__acN=function(){return n};
  if(!A)return;function W(){n++;return new A()}W.prototype=A.prototype;window.AudioContext=W;window.webkitAudioContext=W;})();"""
NO_AUDIO = """(function(){window.AudioContext=undefined;window.webkitAudioContext=undefined;})();"""
BAD_AUDIO = """(function(){var f=function(){throw new Error('audio is not allowed here')};window.AudioContext=f;window.webkitAudioContext=f;})();"""


def real_press(pg, fx=0.3, fy=0.4, dx=60):
    """A real mouse press and short drag inside the wash canvas, then release."""
    r = pg.evaluate("()=>{const e=document.getElementById('cFx').getBoundingClientRect();return [e.left+e.width*%r,e.top+e.height*%r]}" % (fx, fy))
    pg.mouse.move(r[0], r[1])
    pg.mouse.down()
    pg.mouse.move(r[0] + dx, r[1] + 5, steps=8)
    pg.wait_for_timeout(150)
    pg.mouse.up()


def t_env():
    D = pure_data()
    # ---- the test hooks exist only at exactly #test
    for suffix, path in (('', None), ('#Test', None), ('#TEST', None), ('#test2', None), ('#testing', None), ('#test/', None), ('#debug', None), ('', PAGE_PATH + '?test')):
        ctx, pg, logs = new_page(390, 844, 'light', 1, True, hash=suffix, path=path, wait=250, tag='hooks off %s' % (suffix or path))
        ok('hooks: nothing is exposed at %r' % (suffix or (path or '')[-6:]), pg.evaluate('()=>typeof window.__grime') == 'undefined' and pg.evaluate("()=>['__grime','__test','__bot','__debug','grime'].filter(k=>k in window)") == [])
        ok('hooks: the page still starts at %r' % (suffix or (path or '')[-6:]), pg.is_visible('#wash') or pg.is_visible('#board'))
        close(ctx)
    ctx, pg, logs = new_page(390, 844, 'light', 1, True, hash='#test', wait=250, tag='hooks on')
    ok('hooks: #test exposes them', pg.evaluate('()=>typeof window.__grime') == 'object' and pg.evaluate('()=>typeof window.__grime.state') == 'function')
    ok('hooks: with #test the first visit does not start the tutorial job by itself', pg.evaluate('()=>window.__grime.G()') is None and not pg.is_visible('#wash'))
    close(ctx)

    # ---- sound: no audio object before the first press, one after, none when audio is missing or throws
    ctx, pg, logs = new_page(390, 844, 'light', 2, True, hash='', init=[AC_SPY], wait=900, tag='audio spy')
    ok('sound: no AudioContext is created before the first press (first visit)', pg.evaluate('()=>window.__acN()') == 0 and pg.is_visible('#wash'))
    real_press(pg)
    ok('sound: the first real press creates exactly one AudioContext', pg.evaluate('()=>window.__acN()') == 1, pg.evaluate('()=>window.__acN()'))
    pg.keyboard.press('Escape')
    pg.click('#resumeBtn')
    real_press(pg, 0.5, 0.6)
    ok('sound: pressing again and pausing reuse that one context', pg.evaluate('()=>window.__acN()') == 1, pg.evaluate('()=>window.__acN()'))
    pg.keyboard.press('Escape')
    pg.click('#leaveBtn')
    pg.click('#leaveBtn')
    pg.wait_for_timeout(300)
    ok('sound: leaving the first job returns to the board', not pg.is_visible('#wash') and pg.is_visible('#board'))
    pg.click('#muteBtn')
    ok('sound: the mute button mutes and the choice is saved', saved(pg).get('set', {}).get('sound') is False and pg.get_attribute('#muteBtn', 'aria-pressed') == 'true' and 'Sound off' in pg.get_attribute('#muteBtn', 'aria-label'))
    pg.click('#muteBtn')
    ok('sound: unmuting reuses the same context and is saved', saved(pg).get('set', {}).get('sound') is True and pg.evaluate('()=>window.__acN()') == 1 and pg.get_attribute('#muteBtn', 'aria-pressed') == 'false')
    ok('sound: console clean (audio spy)', not logs, logs)
    close(ctx)
    for name, init in (('missing', NO_AUDIO), ('throwing', BAD_AUDIO)):
        ctx, pg, logs = new_page(390, 844, 'light', 1, True, init=[init], tag='audio ' + name)
        pg.evaluate('()=>window.__grime.setState({tut:true,up:{pressure:6,area:6,tank:6,reach:0,flow:0}})')
        pg.evaluate("()=>window.__grime.start('driveway')")
        pg.wait_for_timeout(300)
        left0 = gev(pg, 'window.__grime.G().w.left')
        real_press(pg, 0.2, 0.4, 150)
        ok('sound %s: the game still plays (grime comes off)' % name, gev(pg, 'window.__grime.G().w.left') < left0, (left0, gev(pg, 'window.__grime.G().w.left')))
        pg.click('#pauseBtn')
        pg.click('#resumeBtn')
        pg.click('#pauseBtn')
        pg.keyboard.press('Escape')
        ok('sound %s: buttons keep working and no error is raised' % name, not logs, logs)
        close(ctx)

    # ---- motion: reduced motion and calm mode stop the pulsing hint and the picture sweep
    for label, kw in (('reduced motion', dict(reduced=True)), ('normal motion', dict(reduced=False))):
        ctx, pg, logs = new_page(390, 844, 'light', 1, True, tag=label, **kw)
        pg.evaluate("()=>window.__grime.setState({tut:true})")
        pg.evaluate("()=>window.__grime.start('driveway')")
        pg.wait_for_timeout(300)
        name = pg.evaluate("()=>{const b=document.querySelector('.tipbtn[data-tip=\"red\"]');b.classList.add('pulse');return getComputedStyle(b).animationName}")
        want_none = label == 'reduced motion'
        ok('motion (%s): the pulsing tip hint %s' % (label, 'is switched off' if want_none else 'animates'), (name == 'none') == want_none, name)
        if want_none:
            ok('motion (reduced): the media query tells the page', pg.evaluate("()=>matchMedia('(prefers-reduced-motion: reduce)').matches"))
        pg.evaluate("()=>window.__grime.finish()")
        pg.wait_for_selector('#result', state='visible', timeout=8000)
        v0 = pg.get_attribute('#ba', 'aria-valuenow')
        pg.wait_for_timeout(1700)
        v1 = pg.get_attribute('#ba', 'aria-valuenow')
        if want_none:
            ok('motion (reduced): the before and after slider opens at the middle and does not sweep', v0 == v1 == '50', (v0, v1))
        else:
            ok('motion (normal): the before and after slider sweeps from the before side and settles at 46', v0 != v1 and v1 == '46', (v0, v1))
        ok('motion (%s): console clean' % label, not logs, logs)
        close(ctx)
    ctx, pg, logs = new_page(390, 844, 'light', 1, True, tag='calm class')
    pg.evaluate("()=>window.__grime.setState({tut:true,set:{sound:true,calm:true}})")
    pg.evaluate("()=>window.__grime.start('driveway')")
    pg.wait_for_timeout(300)
    name = pg.evaluate("()=>{const b=document.querySelector('.tipbtn[data-tip=\"red\"]');b.classList.add('pulse');return getComputedStyle(b).animationName}")
    ok('motion: calm mode also switches the pulsing hint off', name == 'none', name)
    close(ctx)

    # ---- leaving the tab: the game pauses and saves, a blurred window lets go of the keys
    ctx, pg, logs = new_page(1280, 800, 'light', 1, False, tag='hidden tab')
    pg.evaluate("()=>window.__grime.setState({tut:true,money:321,lifetime:321})")
    pg.evaluate("()=>window.__grime.start('driveway')")
    pg.wait_for_timeout(300)
    pg.keyboard.down('ArrowRight')
    pg.keyboard.down(' ')
    pg.wait_for_timeout(200)
    ok('tab: a key held down is a spray in progress', gev(pg, 'window.__grime.inp.space') is True and gev(pg, 'window.__grime.inp.kr') == 1)
    pg.evaluate("()=>window.dispatchEvent(new Event('blur'))")
    ok('tab: the window losing focus lets go of the keys', gev(pg, 'window.__grime.inp.space') is False and gev(pg, 'window.__grime.inp.kr') == 0)
    pg.keyboard.up(' ')
    pg.keyboard.up('ArrowRight')
    pg.evaluate("()=>window.__grime.setState({money:654})")
    pg.evaluate("()=>{Object.defineProperty(document,'hidden',{get:function(){return true},configurable:true});document.dispatchEvent(new Event('visibilitychange'))}")
    pg.wait_for_timeout(100)
    ok('tab: hiding the tab pauses the job', gev(pg, 'window.__grime.G().paused') is True and pg.is_visible('#wPause'))
    ok('tab: and saves the game at that moment', saved(pg).get('money') == 654, saved(pg).get('money'))
    pg.evaluate("()=>{Object.defineProperty(document,'hidden',{get:function(){return false},configurable:true});document.dispatchEvent(new Event('visibilitychange'))}")
    pg.wait_for_timeout(200)
    ok('tab: coming back leaves the job paused for the player to resume', gev(pg, 'window.__grime.G().paused') is True)
    pg.click('#resumeBtn')
    ok('tab: Resume carries on', gev(pg, 'window.__grime.G().paused') is False)
    ok('tab: console clean', not logs, logs)
    close(ctx)

    # ---- no network at all: the game needs nothing from outside once it is loaded
    ctx, pg, logs = new_page(390, 844, 'light', 1, True, tag='offline')
    ctx.set_offline(True)
    pg.evaluate("()=>window.__grime.setState({tut:true,money:5000,lifetime:5000})")
    pg.click('#tb-rig')
    pg.click('[data-key="up-pressure"]')
    pg.evaluate("()=>window.__grime.start('driveway')")
    pg.wait_for_timeout(300)
    real_press(pg, 0.2, 0.4, 150)
    pg.evaluate("()=>window.__grime.finish()")
    pg.wait_for_timeout(2300)
    ok('offline: a job can be bought for, played and finished with the network off', pg.is_visible('#result') and st(pg)['up']['pressure'] == 1 and st(pg)['jobs'] == 1)
    ok('offline: console clean (nothing tried to load)', not logs, logs)
    ok('offline: no cookie, and the page has not made one', pg.evaluate('()=>document.cookie') == '')
    close(ctx)

    # ---- the page says what to do when JavaScript is off (built page only: the builder adds that message)
    if STANDALONE:
        ctx = browser().new_context(viewport={'width': 390, 'height': 844}, java_script_enabled=False)
        LIVE.append(ctx)
        pg = ctx.new_page()
        logs = []
        watch(pg, logs, 'no javascript')
        pg.goto(ORIGIN + PAGE_PATH)
        pg.wait_for_timeout(300)
        body = pg.inner_text('body')
        ok('no JavaScript: the page asks for it in words', 'needs JavaScript' in body, body[:200])
        ok('no JavaScript: the title and the how to play text are still there', 'grime time' in body.lower() and 'how to play' in body.lower(), body[:300])
        ok('no JavaScript: nothing overflows sideways', pg.evaluate('()=>document.documentElement.scrollWidth<=innerWidth'))
        close(ctx)


# ================================================================== play: a bot plays all eight jobs on the live page through the test hooks
BOT_JS = (HERE / 'livebot.js').read_text(encoding='utf-8') if (HERE / 'livebot.js').exists() else None


def ref_payout(D, job, res, fp):
    """Pay by the written rules, in exact arithmetic: base x franchise bonus, +25 percent by tough share, +40 percent by flow, minus scuff damage (floors)."""
    W, FR = D['wash'], D['franchise']
    mult = 1 + F(FR['perPoint']) * max(0, fp)
    base = floor_f(F(job['pay']) * mult)
    tough = clampf(F(res['tough']), Fraction(0), Fraction(1))
    clean = floor_f(base * F(W['cleanShare']) * tough)
    tips = floor_f(base * F(W['tipShare']) * clampf((F(res['flow']) - 1) / (F(FLOW_REF) - 1), Fraction(0), Fraction(1)))
    damage = floor_f((base + clean + tips) * clampf(F(res['penalty']), Fraction(0), F(W['scuffMax'])))
    return {'base': base, 'clean': clean, 'tips': tips, 'damage': damage, 'total': base + clean + tips - damage}


def t_play():
    D = pure_data()
    ok('play: the bot script livebot.js is next to the suite', BOT_JS is not None)
    if BOT_JS is None:
        return
    ctx, pg, logs = new_page(390, 844, 'light', 1, True, tag='bot')
    pg.add_script_tag(content=BOT_JS)
    pg.evaluate("""()=>{const g=window.__grime,s=g.state();s.up={pressure:4,area:3,tank:3,reach:1,flow:1};s.gear={soap:true,hot:true,pole:true,surface:false};s.tut=true;g.renderAll();}""")
    pg.evaluate("()=>window.__grime.start('wall')")
    ok('play: a locked job cannot be started (the wall needs 7 stars)', pg.evaluate('()=>window.__grime.G()') is None and not pg.is_visible('#wash'))
    locked = pg.evaluate("()=>[...document.querySelectorAll('#jobList .job.locked')].map(e=>e.textContent)")
    ok('play: seven of the eight job cards are locked and the next one says what it needs', len(locked) == 7 and 'Earn 2 more stars' in locked[0], locked[:2])
    tot_before = 0
    stars_seen = []
    for k, job in enumerate(D['jobs']):
        t0 = time.time()
        before = st(pg)
        if pg.evaluate('()=>window.__grime.G()') is None:
            pg.evaluate('(id)=>window.__grime.start(id)', job['id'])
        ok('play: %s is open' % job['id'], pg.evaluate('()=>window.__grime.G().job.id') == job['id'] and pg.inner_text('#wName').lower() == job['name'].lower(), pg.inner_text('#wName'))
        r = pg.evaluate("()=>window.__bot({limit:400})")
        pg.evaluate("()=>window.__grime.advance(1500)")
        pg.wait_for_timeout(1000)
        info = pg.evaluate("()=>{const G=window.__grime.G(),s=window.__grime.state();return {phase:G.phase,pay:G.pay,stars:[G.stars.a,G.stars.b,G.stars.c],n:G.stars.n,money:s.money,saved:s.stars,res:G.res,jobs:s.jobs}}")
        ok('play: %s is washed to done in %.0f game seconds (par %d)' % (job['id'], r['secs'], job['par']), info['phase'] == 'done' and r['cov'] >= 0.96, (info['phase'], r))
        want = ref_payout(D, job, info['res'], before['fp'])
        ok('play: %s pay breakdown equals the written rules for what was washed' % job['id'], info['pay'] == {k2: int(v) for k2, v in want.items()}, (info['pay'], {k2: int(v) for k2, v in want.items()}))
        ok('play: %s money gained is the total paid, once' % job['id'], abs((info['money'] - before['money']) - info['pay']['total']) < 1e-6, (info['money'] - before['money'], info['pay']['total']))
        ok('play: %s earned three stars (all through the bot: finish, tough spots by hand, under par)' % job['id'], info['stars'] == [True, True, True] and info['saved'].get(job['id']) == 3, info['stars'])
        ok('play: %s result dialog shows the pay and three stars' % job['id'], pg.is_visible('#result') and pg.get_attribute('#rStars', 'aria-label') == '3 of 3 stars' and pg.inner_text('#rTitle').lower() == 'job complete')
        total_txt = pg.evaluate("()=>[...document.querySelectorAll('#rRows .r-row.total dd')].map(e=>e.textContent)")
        ok('play: %s result total reads as the pay' % job['id'], total_txt == [ref_money(Fraction(info['pay']['total']))], total_txt)
        ok('play: %s was counted as one more job done' % job['id'], info['jobs'] == before['jobs'] + 1)
        if k == 0:
            pg.click('#rNext')
            pg.wait_for_timeout(500)
            ok('play: Next job opens the next unlocked job', pg.evaluate('()=>window.__grime.G().job.id') == D['jobs'][1]['id'] and pg.is_visible('#wash'), pg.inner_text('#wName'))
        else:
            pg.click('#rShop')
            pg.wait_for_timeout(150)
    s = st(pg)
    ok('play: eight jobs, 24 stars, and the unlock chain opened every card without help', s['stars'] == {j['id']: 3 for j in D['jobs']} and not pg.query_selector('#jobList .job.locked'), s['stars'])
    ok('play: the stat bar shows 24/24 stars', pg.inner_text('#sStars').strip() == '24/24', pg.inner_text('#sStars'))
    ok('play: console clean (eight jobs by bot)', not logs, logs)
    close(ctx)
    # the surface cleaner on the live page: the bot taps it across the job
    ctx, pg, logs = new_page(390, 844, 'light', 1, True, tag='bot disc')
    pg.add_script_tag(content=BOT_JS)
    pg.evaluate("""()=>{const g=window.__grime,s=g.state();s.up={pressure:4,area:3,tank:3,reach:1,flow:1};s.gear={soap:true,hot:true,pole:true,surface:true};s.tut=true;s.stars={driveway:3,patio:3,fence:3,wall:3,deck:3,garage:3,siding:3,car:3};g.renderAll();}""")
    for jid in ('patio', 'deck'):
        before = st(pg)
        pg.evaluate('(id)=>window.__grime.start(id)', jid)
        ok('play: the disc button is in the tip row when the surface cleaner is owned (%s)' % jid, pg.query_selector('.tipbtn.surf') is not None)
        r = pg.evaluate("()=>window.__bot({limit:400})")
        pg.evaluate("()=>window.__grime.advance(1500)")
        pg.wait_for_timeout(1000)
        info = pg.evaluate("()=>{const G=window.__grime.G(),s=window.__grime.state();return {phase:G.phase,pay:G.pay,money:s.money,n:G.stars.n}}")
        ok('play: %s with the surface cleaner is done and paid once (%.0f game seconds)' % (jid, r['secs']), info['phase'] == 'done' and abs(info['money'] - before['money'] - info['pay']['total']) < 1e-6 and info['n'] >= 2, (info, r))
        pg.click('#rShop')
        pg.wait_for_timeout(150)
    ok('play: console clean (surface cleaner)', not logs, logs)
    close(ctx)


# ================================================================== layout: every size, nothing overflows, every tap target is big enough
LAYOUT_SIZES = [(320, 568), (320, 480), (360, 640), (375, 667), (390, 844), (430, 932), (600, 900), (768, 1024), (1024, 768), (1280, 800), (1440, 900), (1920, 1080),
                (568, 320), (667, 375), (740, 360), (844, 390), (932, 430), (1024, 600)]
LAYOUT_DARK = {(320, 568), (390, 844), (844, 390), (1280, 800)}
LAYOUT_RESULT = {(320, 568), (320, 480), (390, 844), (768, 1024), (1280, 800), (568, 320), (667, 375), (844, 390)}

SPILL_JS = """()=>{
  const out = [];
  const vis = e => { const r = e.getBoundingClientRect(); const cs = getComputedStyle(e); return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none'; };
  let root = document.getElementById('wash').hidden ? document.getElementById('app') : document.getElementById('wash');
  const modal = [...document.querySelectorAll('.modal, #result, #setModal')].find(m => !m.hidden && vis(m));
  if (modal) root = modal;
  root.querySelectorAll('button, [role=button], [role=tab], .job, .stat, .tipbtn, h1, h2, h3, dt, dd, label').forEach(e => {
    if (!vis(e) || getComputedStyle(e).display === 'inline') return;
    if (e.scrollWidth > e.clientWidth + 1.5) out.push((e.id || e.getAttribute('data-key') || e.className || e.tagName).toString().slice(0, 24) + ' ' + e.scrollWidth + '>' + e.clientWidth);
  });
  return out;
}"""

FIT_JS = "()=>{const G=window.__grime.G();return {sw:G.sw,sh:G.sh,cw:G.cssW,ch:G.cssH,W:G.w.W,H:G.w.H}}"


# A dialog may be taller than a short screen: it scrolls inside itself. Then every control must sit inside the scrollable area (nothing cut off above or beside it).
REACH_JS = """()=>{
  const vis = e => { const r = e.getBoundingClientRect(); const cs = getComputedStyle(e); return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none'; };
  const modal = [...document.querySelectorAll('.modal, #result, #setModal')].find(m => !m.hidden && vis(m));
  if (!modal) return null;
  const bad = [], mr = modal.getBoundingClientRect();
  const scrolls = modal.scrollHeight > modal.clientHeight + 1 && ['auto', 'scroll'].indexOf(getComputedStyle(modal).overflowY) >= 0;
  modal.querySelectorAll('button, [role=button], a, input, textarea, [role=tab]').forEach(e => {
    if (!vis(e)) return;
    const r = e.getBoundingClientRect(), top = r.top - mr.top + modal.scrollTop, bottom = top + r.height;
    const inside = r.left >= -0.5 && r.right <= innerWidth + 0.5 && top >= -0.5 && bottom <= modal.scrollHeight + 0.5 && r.height <= innerHeight;
    const below = r.bottom > innerHeight + 0.5 || r.top < -0.5;
    if (!inside || (below && !scrolls)) bad.push((e.id || e.className || e.tagName).toString().slice(0, 24) + ' ' + Math.round(r.left) + ',' + Math.round(r.top) + ',' + Math.round(r.right) + ',' + Math.round(r.bottom));
  });
  return bad;
}"""


def layout_audit(pg):
    a = pg.evaluate(AUDIT_JS)
    reach = pg.evaluate(REACH_JS)
    if reach is not None:
        a['clipped'] = reach
    a['spill'] = pg.evaluate(SPILL_JS)
    return a


def layout_states(pg, with_result):
    res = {}
    for tab in ('jobs', 'rig', 'crew', 'fran'):
        pg.click('#tb-' + tab)
        res['tab ' + tab] = layout_audit(pg)
    pg.click('#setBtn')
    res['settings'] = layout_audit(pg)
    pg.click('#setClose')
    pg.evaluate("()=>window.__grime.start('garage')")
    pg.wait_for_timeout(350)
    res['wash'] = layout_audit(pg)
    fit = pg.evaluate(FIT_JS)
    pg.evaluate("()=>window.__grime.pause()")
    pg.wait_for_timeout(100)
    res['pause'] = layout_audit(pg)
    pg.evaluate("()=>window.__grime.pause()")
    if with_result:
        pg.evaluate("()=>{window.__grime.finish();window.__grime.advance(1200)}")
        pg.wait_for_selector('#result', state='visible', timeout=6000)
        pg.wait_for_timeout(150)
        res['result'] = layout_audit(pg)
    return res, fit


def t_layout():
    seen = 0
    for (w, h) in LAYOUT_SIZES:
        for scheme in ('light', 'dark'):
            if scheme == 'dark' and (w, h) not in LAYOUT_DARK:
                continue
            tag = '%dx%d %s' % (w, h, scheme)
            ctx, pg, logs = new_page(w, h, scheme, 1, w < 700, tag='layout ' + tag, wait=300)
            rich(pg, stars=ALL_STARS, gear=ALL_GEAR, money=123456, lifetime=123456)
            res, fit = layout_states(pg, (w, h) in LAYOUT_RESULT and scheme == 'light')
            seen += len(res)
            over = ['%s %s' % (k, a['over']) for k, a in res.items() if a['over'] > 0]
            small = ['%s: %s' % (k, ', '.join(a['small'][:4])) for k, a in res.items() if a['small']]
            clipped = ['%s: %s' % (k, ', '.join(a['clipped'][:4])) for k, a in res.items() if a['clipped']]
            spill = ['%s: %s' % (k, ', '.join(a['spill'][:4])) for k, a in res.items() if a['spill']]
            ok('layout %s: no sideways overflow in any tab, dialog or the wash view' % tag, not over, over)
            ok('layout %s: every tap target is at least 40 px on its short side' % tag, not small, small)
            ok('layout %s: nothing in the wash view or a dialog sits outside the screen' % tag, not clipped, clipped)
            ok('layout %s: no label is wider than its own box' % tag, not spill, spill)
            sc = min(fit['sw'] / fit['W'], fit['sh'] / fit['H'])
            snug = max(fit['cw'] / fit['sw'], fit['ch'] / fit['sh'])
            ok('layout %s: the scene fills the stage on one side and fits on the other' % tag,
               snug > 0.98 and fit['cw'] <= fit['sw'] + 0.5 and fit['ch'] <= fit['sh'] + 0.5 and abs(sc * fit['W'] - fit['cw']) < 0.5, fit)
            ok('layout %s: the scene is big enough to play (at least 150 px on its short side, area at least 20 percent of the screen)' % tag,
               min(fit['cw'], fit['ch']) >= 150 and fit['cw'] * fit['ch'] >= 0.20 * w * h, [round(fit['cw']), round(fit['ch']), w, h])
            ok('layout %s: console clean' % tag, not logs, logs)
            close(ctx)
    ok('layout: %d states were audited in all (4 tabs, settings, wash, pause, and the result on some sizes)' % seen, seen >= 150, seen)


# ================================================================== contrast: computed text contrast in both schemes, every state
CONTRAST_SETUP = {'tut': True, 'stars': {'driveway': 3, 'patio': 2, 'fence': 1}, 'gear': {'soap': True, 'hot': False, 'pole': False, 'surface': False},
                  'up': {'pressure': 2, 'area': 1, 'tank': 0, 'reach': 0, 'flow': 0}, 'money': 900, 'lifetime': 1500, 'crew': {'apprentice': 3}, 'fp': 3}
CONTRAST_COMBOS = [(390, 844, 'light'), (390, 844, 'dark'), (320, 568, 'light'), (320, 568, 'dark')]
STAGE_DARK = 'rgb(21,12,34)'


def t_contrast():
    total = 0
    states = 0
    for (w, h, scheme) in CONTRAST_COMBOS:
        tag = '%dx%d %s' % (w, h, scheme)
        ctx, pg, logs = new_page(w, h, scheme, 1, True, tag='contrast ' + tag, wait=300)
        pg.evaluate(CONTRAST_JS)
        ok('contrast %s: the audit script is in the page' % tag, pg.evaluate("()=>typeof window.__contrast") == 'function')
        pg.evaluate('(d)=>window.__grime.setState(d)', CONTRAST_SETUP)

        def audit(sel, label, stage=STAGE_DARK, minimum=1):
            nonlocal total, states
            r = pg.evaluate("(a)=>window.__contrast(a[0],a[1])", [sel, stage])
            low = ['%s %s need %s %r %s %spx' % (label, x['cr'], x['need'], x['t'], x['el'], x['fs']) for x in r if x['cr'] < x['need']]
            total += len(r)
            states += 1
            ok('contrast %s %s: %d text elements, none under the minimum ratio (4.5, or 3 for large text)' % (tag, label, len(r)), not low and len(r) >= minimum, low[:5] or ('only %d elements audited' % len(r)))

        pg.evaluate("()=>{document.getElementById('backText').textContent='Welcome back! Your crew earned $1.2K in 3 hours while you were away.';document.getElementById('backNote').hidden=false}")
        for tab in ('jobs', 'rig', 'crew', 'fran'):
            pg.click('#tb-' + tab)
            pg.wait_for_timeout(250)
            audit('body', 'board ' + tab, minimum=15)
        pg.evaluate("()=>window.__grime.toast('Not enough cash yet.')")
        audit('#toast', 'toast')
        pg.click('#setBtn')
        audit('#setModal', 'settings', minimum=8)
        pg.click('#setClose')
        pg.evaluate("()=>{document.getElementById('sheetText').value='x';document.getElementById('sheet').hidden=false}")
        audit('#sheet', 'save code box', minimum=2)
        pg.evaluate("()=>{document.getElementById('sheet').hidden=true}")
        pg.evaluate("()=>window.__grime.start('driveway')")
        pg.wait_for_timeout(300)
        pg.evaluate("()=>{const e=document.getElementById('wHint');e.textContent='Switch to the yellow tip for tough spots.';e.hidden=false;"
                    "const t=document.getElementById('wTut');document.getElementById('wTutB').textContent='Drag to spray';"
                    "document.getElementById('wTutS').textContent='Press and drag across the dirt.';t.hidden=false}")
        audit('#wash', 'wash view', minimum=8)
        audit('#wash', 'wash view over a white scene', stage='rgb(255,255,255)', minimum=8)
        pg.evaluate("()=>window.__grime.pause()")
        pg.wait_for_timeout(100)
        audit('#wPause', 'pause panel', minimum=3)
        pg.evaluate("()=>window.__grime.pause()")
        pg.evaluate("()=>{window.__grime.finish();window.__grime.advance(1200)}")
        pg.wait_for_selector('#result', state='visible', timeout=6000)
        pg.wait_for_timeout(200)
        audit('#result', 'result', minimum=8)
        ok('contrast %s: console clean' % tag, not logs, logs)
        close(ctx)
    if STANDALONE:
        for scheme in ('light', 'dark'):
            ctx, pg, logs = new_page(390, 844, scheme, 1, True, hash='', path=BLANK_PATH, tag='contrast privacy ' + scheme, wait=300)
            pg.evaluate(CONTRAST_JS)
            r = pg.evaluate("()=>window.__contrast('body','rgb(255,255,255)')")
            low = ['%s %s need %s' % (x['t'], x['cr'], x['need']) for x in r if x['cr'] < x['need']]
            ok('contrast privacy page %s: %d text elements, none under the minimum ratio' % (scheme, len(r)), not low and len(r) >= 15, low[:5] or len(r))
            total += len(r)
            close(ctx)
    print('  contrast: %d text elements audited in %d states' % (total, states))
    ok('contrast: %d text elements audited in %d states' % (total, states), total >= 600 and states >= 40, (total, states))


# ================================================================== journey: a first visit with real pointer strokes only, no test hooks
RP_DIRT = """(gw)=>{
  const c=document.getElementById('cDirt'), r=c.getBoundingClientRect();
  const gh=Math.max(4,Math.round(gw*c.height/c.width));
  const s=document.createElement('canvas'); s.width=gw; s.height=gh; const sx=s.getContext('2d');
  sx.imageSmoothingEnabled=true; sx.imageSmoothingQuality='high'; sx.drawImage(c,0,0,gw,gh);
  const d=sx.getImageData(0,0,gw,gh).data, a=[]; for(let i=0;i<gw*gh;i++){ a.push(d[i*4+3]); }
  const f=document.getElementById('cFx').getBoundingClientRect();
  return {gw:gw,gh:gh,a:a,l:r.left,t:r.top,w:r.width,h:r.height,vis:f.top+f.height};
}"""
RP_TANK = "()=>{const m=getComputedStyle(document.getElementById('wTank')).transform;const mm=/matrix\\(([^,]+)/.exec(m);return mm?parseFloat(mm[1]):1}"
RP_SPACING = {'white': 0.055, 'green': 0.045, 'yellow': 0.03, 'red': 0.014}
RP_SPEED = {'white': 1.0, 'green': 1.0, 'yellow': 0.8, 'red': 0.55}


def rp_pct(pg):
    m = re.search(r'(\d+)', pg.inner_text('#wPct'))
    return int(m.group(1)) if m else 0


def rp_scrub(pg, spacing, speed, max_secs, thresh=28, gw=36):
    """One vision guided pass with the real mouse: look at the dirt canvas (what a player sees), then stroke rows only over the dirty parts."""
    m = pg.evaluate(RP_DIRT, gw)
    gw, gh, a = m['gw'], m['gh'], m['a']
    L, T, W, H = m['l'], m['t'], m['w'], min(m['h'], m['vis'] - m['t'] - 3)
    cw, ch = W / gw, m['h'] / gh
    step = max(3.0, spacing * m['h'])
    rows = {}
    for cy in range(gh):
        xs = [cx for cx in range(gw) if a[cy * gw + cx] > thresh]
        if xs:
            rows[cy] = (min(xs), max(xs))
    if not rows:
        return 0.0, 0, False
    bands = []
    y = 0.0
    while y < H:
        lo, hi = y, y + step
        xs0, xs1 = None, None
        for cy, (x0, x1) in rows.items():
            cyc = (cy + 0.5) * ch
            if lo - ch / 2 <= cyc < hi + ch / 2:
                xs0 = x0 if xs0 is None else min(xs0, x0)
                xs1 = x1 if xs1 is None else max(xs1, x1)
        if xs0 is not None:
            bands.append((T + min(H - 1, y + step / 2), L + max(0, xs0 - 0.5) * cw, L + min(gw, xs1 + 1.5) * cw))
        y += step
    t_start = time.time()
    pressed = False
    d = 1
    last_y = None
    n = 0
    finished = False
    for (yy, xa, xb) in bands:
        if time.time() - t_start > max_secs:
            break
        if d < 0:
            xa, xb = xb, xa
        if (not pressed) or last_y is None or abs(yy - last_y) > step * 3.5:
            if pressed:
                pg.mouse.up()
                pressed = False
            pg.mouse.move(xa, yy)
            pg.mouse.down()
            pressed = True
        else:
            pg.mouse.move(xa, yy)
        last_y = yy
        x = xa
        direction = 1 if xb >= xa else -1
        lastt = time.time()
        while (direction > 0 and x < xb) or (direction < 0 and x > xb):
            now = time.time()
            dt = now - lastt
            lastt = now
            x += direction * speed * dt
            pg.mouse.move(min(max(x, min(xa, xb)), max(xa, xb)), yy)
            n += 1
            if n % 20 == 0:
                if pg.is_visible('#result'):
                    finished = True
                    break
                if pg.evaluate(RP_TANK) < 0.06:   # the tank is dry: let go, wait for it to refill, press again
                    pg.mouse.up()
                    pressed = False
                    pg.wait_for_timeout(1500)
                    pg.mouse.move(x, yy)
                    pg.mouse.down()
                    pressed = True
            time.sleep(0.005)
        if finished:
            break
        d = -d
    if pressed:
        pg.mouse.up()
    return time.time() - t_start, len(bands), finished


def rp_play(pg, max_secs=240, speed=520):
    """Plays the open wash view to the end with real strokes, moving to a narrower tip whenever a pass stops making progress."""
    t0 = time.time()
    order = ['white', 'green', 'yellow', 'red']
    idx, stall, passes = 0, 0, 0
    last_pct = rp_pct(pg)
    while time.time() - t0 < max_secs and not pg.is_visible('#result'):
        tip = order[idx]
        if pg.get_attribute('.tipbtn[data-tip="%s"]' % tip, 'aria-pressed') != 'true':
            pg.click('.tipbtn[data-tip="%s"]' % tip)
        secs, rows, fin = rp_scrub(pg, RP_SPACING[tip], speed * RP_SPEED[tip], max_secs - (time.time() - t0))
        passes += 1
        p = rp_pct(pg)
        if fin:
            break
        if p - last_pct < 2:
            stall += 1
            if stall >= 1 and idx < len(order) - 1:
                idx += 1
                stall = 0
        else:
            stall = 0
        last_pct = p
    t1 = time.time()
    while time.time() - t1 < 8 and not pg.is_visible('#result'):
        pg.wait_for_timeout(100)
    return time.time() - t0, passes, pg.is_visible('#result')


def t_journey():
    D = pure_data()
    ctx, pg, logs = new_page(390, 844, 'light', 2, False, hash='', wait=1500, tag='journey')
    ok('journey: the plain address has no test hooks', pg.evaluate("()=>typeof window.__grime") == 'undefined')
    ok('journey: a first visit opens the wash view with the tutorial card', pg.is_visible('#wash') and pg.is_visible('#wTut'))
    eq('journey: the tutorial starts by saying what to do', pg.inner_text('#wTutB').lower(), 'drag to spray')
    ok('journey: the board behind the wash view cannot be reached (inert) while a job is open', pg.evaluate("()=>document.getElementById('app').inert === true"))
    # one short press and drag with the real mouse moves the tutorial on
    r = pg.evaluate("()=>{const r=document.getElementById('cDirt').getBoundingClientRect();return [r.left,r.top,r.width,r.height]}")
    x0, y0 = r[0] + r[2] * 0.25, r[1] + r[3] * 0.3
    pg.mouse.move(x0, y0)
    pg.mouse.down()
    for k in range(1, 25):
        pg.mouse.move(x0 + k * r[2] * 0.02, y0)
        pg.wait_for_timeout(16)
    ok('journey: pressing and dragging makes the spray show and moves the tutorial on', pg.inner_text('#wTutB').lower() == 'keep moving', pg.inner_text('#wTutB'))
    pg.mouse.up()
    secs, passes, fin = rp_play(pg, 170, 520)
    ok('journey: the tutorial job is finished by real strokes alone (%.0f s, %d passes)' % (secs, passes), fin)
    if not fin:
        close(ctx)
        return
    stars1 = int(re.search(r'(\d) of 3', pg.get_attribute('#rStars', 'aria-label')).group(1))
    rows = pg.inner_text('#rRows')
    has('journey: the result lists the base pay', rows, 'Base pay')
    has('journey: the result lists the total', rows, 'Total')
    pay1 = float(re.search(r'Total\s*\$([\d,.]+)', rows).group(1).replace(',', ''))
    sv = saved(pg)
    ok('journey: the pay was added to the saved money', abs(sv['money'] - pay1) < 1.01 and pay1 > 0, (sv['money'], pay1))
    ok('journey: the tutorial flag and the stars were saved', sv.get('tut') is True and sv['stars'].get('driveway') == stars1 and stars1 >= 1, sv.get('stars'))
    ok('journey: the first job paid what the design says (base pay of the first job, at most the cleanliness and flow bonuses on top)',
       D['jobs'][0]['pay'] <= pay1 <= D['jobs'][0]['pay'] * 2, (D['jobs'][0]['pay'], pay1))
    pg.click('#rShop')
    pg.wait_for_timeout(300)
    ok('journey: Shop leads to the Rig tab', pg.get_attribute('#tb-rig', 'aria-selected') == 'true' and not pg.is_visible('#wash'))
    m0 = saved(pg)['money']
    bt = pg.query_selector('[data-key="up-pressure"]')
    ok('journey: the first upgrade can be bought right after the first job', bt is not None and bt.get_attribute('aria-disabled') != 'true', m0)
    bt.click()
    sv = saved(pg)
    ok('journey: the first upgrade was bought with a real click', sv['up']['pressure'] == 1 and sv['money'] < m0, sv['up'])
    pg.click('#tb-jobs')
    pat = pg.query_selector('button.job[data-key="job-patio"]')
    ok('journey: the second job is open on the board', pat is not None and pat.get_attribute('aria-disabled') != 'true')
    pat.click()
    pg.wait_for_timeout(900)
    ok('journey: the second job opens the wash view without a tutorial card', pg.is_visible('#wash') and not pg.is_visible('#wTut'))
    p0 = rp_pct(pg)
    secs2, rows2, fin2 = rp_scrub(pg, RP_SPACING['white'], 520, 6)
    p1 = rp_pct(pg)
    ok('journey: six seconds of real strokes clean part of the patio (%d percent to %d percent)' % (p0, p1), p1 > p0 + 3, (p0, p1))
    pg.keyboard.press('Escape')
    pg.wait_for_timeout(200)
    ok('journey: Escape pauses the job', pg.is_visible('#wPause'))
    money_mid = saved(pg)['money']
    pg.click('#leaveBtn')
    ok('journey: the first tap on Leave only asks to confirm', pg.is_visible('#wash'))
    pg.click('#leaveBtn')
    pg.wait_for_timeout(300)
    ok('journey: the second tap leaves the job and shows the board', not pg.is_visible('#wash') and pg.is_visible('#tb-jobs'))
    sv = saved(pg)
    ok('journey: leaving a job early costs nothing and pays nothing', abs(sv['money'] - money_mid) < 0.5 and sv['stars'].get('patio', 0) == 0, (money_mid, sv['money'], sv['stars']))
    before = saved(pg)
    pg.reload()
    pg.wait_for_timeout(900)
    after = saved(pg)
    ok('journey: a reload keeps the money, the upgrade, the stars and the tutorial flag',
       after['up']['pressure'] == 1 and after['stars'] == before['stars'] and after.get('tut') is True and after['money'] >= before['money'] - 0.5, (before, after))
    ok('journey: no wash view starts again after the reload (the tutorial is done)', not pg.is_visible('#wash'))
    ok('journey: the stat bar shows the saved money', pg.inner_text('#sMoney').strip() != '' and pg.inner_text('#sMoney').strip() != '$0', pg.inner_text('#sMoney'))
    ok('journey: console clean for the whole journey', not logs, logs)
    ok('journey: no cookie was set', pg.evaluate('()=>document.cookie') == '')
    close(ctx)


# @@UI@@


# ================================================================== run wide checks: everything every page did
def t_final():
    ok('run: no console error, warning or page error from any page', not ERRS, ERRS[:4])
    ok('run: no request left the test server (no outside host, no font service, no analytics)', not EXT_REQS, EXT_REQS[:4])
    ok('run: no alert, confirm or prompt was ever opened', not DIALOGS, DIALOGS[:3])
    ok('run: no cookie was ever set', not COOKIES, [c.get('name') for c in COOKIES][:4])


ORDER = ['hygiene', 'builder', 'meta', 'math', 'wash', 'pace', 'shop', 'save', 'storage', 'keyboard', 'input', 'share', 'env', 'play', 'layout', 'contrast', 'journey']


def main():
    t0 = time.time()
    print('Grime Time suite on %s' % (('the BUILT page ' + STANDALONE) if STANDALONE else 'the FRAGMENT grime-time.html (Google Fonts blocked, the same embedded fonts as the built page)'), flush=True)
    if not NODE:
        print('node is missing: the math, wash and pace sections cannot run')
    ran = 0
    for name in ORDER:
        if not on(name):
            continue
        fn = globals().get('t_' + name)
        if fn is None:
            fails.append('section %s is not defined' % name)
            print('  FAIL section %s is not defined' % name)
            continue
        ran += 1
        with section(name):
            fn()
    if ran:
        with section('final'):
            t_final()
    shutdown_browser()
    print()
    print('PASS %d FAIL %d  (%s, %.0f s)' % (passes, len(fails), 'built page' if STANDALONE else 'fragment', time.time() - t0))
    for f in fails:
        print(' -', f.splitlines()[0][:240])
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
