'use strict';
/* Loads the pure region of grime-time.html and plays it with a scripted bot.
   Usage: node grime_sim.js job <id> [speed]     one job on a fresh rig
          node grime_sim.js pace [hours]         greedy economy run (prints JSON)  */
const fs = require('fs');
const path = require('path');

function loadPure(file) {
  const s = fs.readFileSync(file || path.join(__dirname, 'grime-time.html'), 'utf8');
  const m = s.match(/PURE-BEGIN[^\n]*\n([\s\S]*?)\/\* PURE-END/);
  if (!m) throw new Error('pure region not found');
  return new Function(m[1] + '\nreturn PURE;')();
}

/* The bot's way of playing: sweep rows at a fixed speed with the widest tip that can clean what is left. */
function playJob(P, job, st, o) {
  o = o || {};
  const speed = o.speed || 900, dt = 1 / 30, seed = o.seed || 7;
  const sz = P.sceneSize(o.aspect || 0.56);
  const gw = sz.W / 10, gh = sz.H / 10;
  const rig = P.rigOf(st);
  const w = P.makeWash(job, gw, gh, seed);
  w.track = false;
  const s = P.newSprayer(rig, 'white');
  const D = P.DATA, C = D.cell, tips = D.tips.filter(t => !t.soap).sort((a, b) => b.r - a.r);
  let t = 0, guard = 0;
  const Hof = (th, k) => { let h = k ? D.kinds[k].h : (th <= D.bands[0].top ? D.bands[0].h : th <= D.bands[1].top ? D.bands[1].h : D.bands[2].h); if (k === 1 && rig.hot) h *= 0.5; return h; };
  function capable(tip) {
    const pe = tip.p * rig.pMul * (1 - rig.fall * 0.35);
    return (i) => pe > Hof(w.thick[i], w.kind[i]) * 1.3;
  }
  const limit = o.limit || 900;
  function advance(tx, ty) {
    // move the nozzle toward (tx,ty) at speed, stepping the real simulation
    for (;;) {
      const dx = tx - s.x, dy = ty - s.y, d = Math.hypot(dx, dy), step = speed * dt;
      if (d <= step) { s.x = tx; s.y = ty; P.simStep(w, s, rig, dt); t += dt; return; }
      s.x += dx / d * step; s.y += dy / d * step;
      P.simStep(w, s, rig, dt); t += dt;
      if (P.coverage(w) >= D.wash.doneAt || t > limit) return;
    }
  }
  function tap(x, y) {
    s.on = false; s.x = x; s.y = y;
    s.surf = { x, y, left: D.surface.secs };
    while (s.surf) { P.simStep(w, s, rig, dt); t += dt; }
    for (let k = 0; k < Math.ceil((D.surface.gap + 0.15) / dt); k++) { P.simStep(w, s, rig, dt); t += dt; }
  }
  // the surface cleaner goes first when owned: hex grid of taps over the area that is still dirty
  if (rig.surface && !o.noSurface) {
    const R = D.surface.r * rig.rMul, stepx = R * 1.45, stepy = R * 1.25;
    let row = 0;
    for (let y = D.surface.edge; y < w.H; y += stepy, row++) {
      for (let x = D.surface.edge + (row % 2 ? stepx / 2 : 0); x < w.W; x += stepx) {
        // skip spots where nothing is left
        let any = false;
        const cx0 = Math.max(0, Math.floor((x - R * 0.6) / C)), cx1 = Math.min(gw - 1, Math.floor((x + R * 0.6) / C));
        const cy0 = Math.max(0, Math.floor((y - R * 0.6) / C)), cy1 = Math.min(gh - 1, Math.floor((y + R * 0.6) / C));
        for (let cy = cy0; cy <= cy1 && !any; cy++) for (let cx = cx0; cx <= cx1; cx++) if (w.thick[cy * gw + cx] > 0 && !(w.kind[cy * gw + cx] && D.surface.skip.indexOf(w.kind[cy * gw + cx]) >= 0)) { any = true; break; }
        if (any) tap(Math.min(w.W - D.surface.edge, x), Math.min(w.H - D.surface.edge, y));
        if (P.coverage(w) >= D.wash.doneAt) break;
      }
      if (P.coverage(w) >= D.wash.doneAt) break;
    }
  }
  let passes = 0;
  while (P.coverage(w) < D.wash.doneAt && t < limit && guard++ < 60) {
    // tough spots first while the hand-cleaned share is low (this is what a player who wants the bonus does),
    // then the widest tip that can clean at least a quarter of what is left
    const toughMode = !o.noToughFirst && w.toughTotal > 0 && w.toughDone < w.toughTotal * 0.8;
    let pick = tips[tips.length - 1], left = 0;
    for (let i = 0; i < w.thick.length; i++) if (w.thick[i] > 0 && (!toughMode || w.tough[i])) left++;
    for (const tip of tips) {
      const cap = capable(tip); let c = 0;
      for (let i = 0; i < w.thick.length; i++) if (w.thick[i] > 0 && (!toughMode || w.tough[i]) && cap(i)) c++;
      if (c >= left * (toughMode ? 0.5 : 0.25)) { pick = tip; break; }
    }
    s.tip = pick; passes++;
    const R = D.wash.baseR * pick.r * rig.rMul, cap0 = capable(pick), spacing = R * 1.3;
    const cap = toughMode ? (i => w.tough[i] && cap0(i)) : cap0;
    s.on = true; s.hasPrev = false;
    let dir = 1, any = false;
    for (let y = spacing / 2; y < w.H + spacing / 2; y += spacing) {
      const cy0 = Math.max(0, Math.floor((y - R) / C)), cy1 = Math.min(gh - 1, Math.floor((y + R) / C));
      let xmin = 1e9, xmax = -1e9;
      for (let cy = cy0; cy <= cy1; cy++) for (let cx = 0; cx < gw; cx++) {
        const i = cy * gw + cx;
        if (w.thick[i] > 0 && cap(i)) { const xx = (cx + 0.5) * C; if (xx < xmin) xmin = xx; if (xx > xmax) xmax = xx; }
      }
      if (xmax < 0) continue;
      any = true;
      const xa = Math.max(0, xmin - R * 0.5), xb = Math.min(w.W, xmax + R * 0.5);
      const yy = Math.min(w.H - 5, y);
      if (dir > 0) { advance(xa, yy); advance(xb, yy); } else { advance(xb, yy); advance(xa, yy); }
      dir = -dir;
      if (P.coverage(w) >= D.wash.doneAt || t > limit) break;
    }
    s.on = false;
    if (!any) break;
  }
  const res = P.washResult(w);
  return { secs: t, cov: P.coverage(w), res: res, passes: passes, w: w };
}


/* ---------- the greedy economy bot ---------- */
function rigKey(st) { return JSON.stringify([st.up, st.gear]); }
function makePacer(P, opt) {
  opt = opt || {};
  const speed = opt.speed || 900, overhead = opt.overhead || 10, D = P.DATA;
  const cache = new Map();
  function est(job, st) {
    const k = job.id + '|' + rigKey(st);
    let r = cache.get(k);
    if (!r) { const o = playJob(P, job, st, { speed }); r = { secs: o.secs, res: o.res }; cache.set(k, r); }
    return r;
  }
  function unlocked(st) { return D.jobs.filter(j => P.jobStatus(j, st).ok); }
  function jobRate(job, st) {
    const e = est(job, st), pay = P.payout(job, e.res, st).total;
    return pay / (e.secs + overhead);
  }
  function bestJob(st) {
    const list = unlocked(st);
    // the two best paying unlocked jobs are the only serious candidates
    const top = list.slice().sort((a, b) => b.pay - a.pay).slice(0, 2);
    let best = null, br = -1;
    for (const j of top) { const r = jobRate(j, st); if (r > br) { br = r; best = j; } }
    return { job: best, rate: br };
  }
  function totalRate(st) { return bestJob(st).rate + P.crewIncome(st); }
  function candidates(st) {
    const out = [];
    D.upgrades.forEach(u => { const lv = st.up[u.id]; if (lv < u.max) out.push({ kind: 'up', id: u.id, cost: P.upgradeCost(u.id, lv) }); });
    D.gear.forEach(g => { if (!st.gear[g.id]) out.push({ kind: 'gear', id: g.id, cost: g.cost }); });
    D.crew.forEach(c => out.push({ kind: 'crew', id: c.id, cost: P.crewCost(c.id, st.crew[c.id]) }));
    return out;
  }
  function apply(st, c) {
    const n = JSON.parse(JSON.stringify(st));
    if (c.kind === 'up') n.up[c.id]++; else if (c.kind === 'gear') n.gear[c.id] = true; else n.crew[c.id]++;
    return n;
  }
  function pickPurchase(st) {
    // A person early on buys any affordable upgrade straight away, cheapest first. The rate estimates are too noisy to trust at level 1,
    // so the bot does this until 200 dollars have been earned (it was 600, which kept the bot from hiring anyone before about 350 s whatever the crew cost).
    if (st.lifetime < (opt.earlyLifetime || 200)) {
      const ups = candidates(st).filter(c => c.kind === 'up' && st.money >= c.cost).sort((a, b) => a.cost - b.cost);
      if (ups.length) return ups[0];
    }
    const base = totalRate(st);
    const all = [];
    for (const c of candidates(st)) {
      if (c.kind === 'crew') { const gain = P.crewIncome(apply(st, c)) - P.crewIncome(st); c.pb = c.cost / Math.max(1e-9, gain); }
      else { const gain = totalRate(apply(st, c)) - base; c.pb = gain > 1e-9 ? c.cost / gain : Infinity; }
      if (c.pb < Infinity) all.push(c);
    }
    if (!all.length) return null;
    all.sort((a, b) => a.pb - b.pb);
    const best = all[0];
    if (st.money >= best.cost) return best;
    // do not wait for something far away while a decent cheaper thing is affordable
    const wait = (best.cost - st.money) / Math.max(0.5, base);
    if (wait > 40) { const cheap = all.find(c => st.money >= c.cost && c.pb <= best.pb * 4); if (cheap) return cheap; }
    return best;
  }
  return { est, bestJob, totalRate, pickPurchase, apply, unlocked, jobRate };
}

function pace(P, hours, opt) {
  opt = opt || {};
  const D = P.DATA, pc = makePacer(P, opt), overhead = opt.overhead || 6;
  let st = P.freshState(), clock = 0, cycleStart = 0, cycle = 1;
  st.tut = false;
  const log = [], ms = {};
  const note = (k, extra) => { const key = 'c' + cycle + '.' + k; if (!(key in ms)) { ms[key] = Math.round(clock); log.push([Math.round(clock), key, extra || '']); } };
  let jobsPlayed = 0, upgradesBought = 0;
  const maxT = hours * 3600, franchiseAt = opt.franchiseAt || 1;   // franchise at the first offer unless told otherwise
  const stats = [];
  let guard = 0;
  while (clock < maxT && guard++ < 20000) {
    // buy while something good is affordable (with the "do not wait forever" rule)
    for (let k = 0; k < 40; k++) {
      const c = pc.pickPurchase(st);
      if (!c) break;
      if (st.money >= c.cost) {
        st.money -= c.cost;
        st = pc.apply(st, c);
        upgradesBought++;
        note('buy.' + c.kind + '.' + c.id, '#' + (st.up[c.id] !== undefined ? st.up[c.id] : st.crew[c.id] || 1));
        if (c.kind === 'up') note('firstUpgrade');
        if (c.kind === 'crew') note('firstCrew');
        if (c.kind === 'gear' && c.id === 'surface') note('surfaceCleaner');
        clock += 3;
        st.money += P.crewIncome(st) * 3;
        continue;
      }
      break;
    }
    const nUnlocked = pc.unlocked(st).length;
    if (nUnlocked >= 3) note('job3Unlocked');
    if (nUnlocked >= 6) note('job6Unlocked');
    if (nUnlocked >= 8) note('job8Unlocked');
    const offer = P.franchiseOffer(st);
    if (offer.can) note('franchiseOffered', 'gain ' + offer.gain);
    if (offer.can && cycle <= franchiseAt && offer.gain >= (opt.ratio || 0) * st.fp) {
      stats.push({ cycle, secs: clock - cycleStart, lifetime: st.lifetime, gain: offer.gain, fp: st.fp + offer.gain });
      st = P.applyFranchise(st); st.savedAt = 0;
      cycle++; cycleStart = clock;
      continue;
    }
    // play the best job
    let pick;
    // if a locked job waits only for stars, prefer improving stars
    const lockedStars = D.jobs.find(j => { const s = P.jobStatus(j, st); return !s.ok && s.needGear.length === 0; });
    const list = pc.unlocked(st);
    if (lockedStars) {
      const improvable = list.filter(j => (st.stars[j.id] || 0) < 3).sort((a, b) => b.pay - a.pay);
      pick = improvable.length ? improvable[0] : pc.bestJob(st).job;
    } else pick = pc.bestJob(st).job;
    const e = pc.est(pick, st);
    const pay = P.payout(pick, e.res, st);
    const dur = e.secs + overhead;
    const earnedIdle = P.crewIncome(st) * dur;
    st.money += pay.total + earnedIdle; st.lifetime += pay.total + earnedIdle; st.earned += pay.total + earnedIdle; st.jobs++;
    const sf = P.starsFor(pick, e.res);
    st.stars[pick.id] = Math.max(st.stars[pick.id] || 0, sf.n);
    clock += dur; jobsPlayed++;
    if (opt.trace && jobsPlayed <= opt.trace) log.push([Math.round(clock), 'job', pick.id + ' secs ' + e.secs.toFixed(0) + ' pay ' + pay.total + ' money ' + Math.floor(st.money) + ' stars ' + st.stars[pick.id]]);
    note('firstJobDone');
    if (jobsPlayed % 25 === 0) log.push([Math.round(clock), 'status', 'jobs ' + jobsPlayed + ' stars ' + P.starsTotal(st) + ' life ' + P.fmtMoney(st.lifetime) + ' inc ' + P.fmtRate(P.crewIncome(st))]);
  }
  return { log, ms, stats, jobsPlayed, upgradesBought, final: { lifetime: st.lifetime, fp: st.fp, stars: P.starsTotal(st), crew: st.crew, up: st.up, gear: st.gear } };
}
module.exports = { loadPure, playJob, makePacer, pace };


if (require.main === module) {
  const P = loadPure();
  const cmd = process.argv[2];
  if (cmd === 'pace') {
    const hours = +process.argv[3] || 2, t0 = Date.now();
    const r = pace(P, hours, { franchiseAt: +process.argv[4] || 1, trace: +process.argv[5] || 0, ratio: +process.env.RATIO || 0 });
    r.log.forEach(l => console.log(String(l[0]).padStart(6), l[1], l[2]));
    console.log(JSON.stringify(r.stats), 'jobs', r.jobsPlayed, 'buys', r.upgradesBought, 'wall', ((Date.now() - t0) / 1000).toFixed(1) + 's');
  }
  if (cmd === 'table') {
    const rigs = [['p0a0', {}], ['p1a0', { pressure: 1 }], ['p2a1', { pressure: 2, area: 1 }], ['p3a2', { pressure: 3, area: 2 }], ['p4a3t', { pressure: 4, area: 3 }],
      ['p5a4s', { pressure: 5, area: 4, surface: 1 }], ['p7a6s', { pressure: 7, area: 6, reach: 4, surface: 1 }], ['p10a10s', { pressure: 10, area: 10, reach: 8, surface: 1 }]];
    console.log('job'.padEnd(9) + rigs.map(r => r[0].padStart(8)).join(''));
    for (const j of P.DATA.jobs) {
      let line = j.id.padEnd(9);
      for (const [name, cfg] of rigs) {
        const st = P.freshState();
        for (const k in cfg) { if (k in st.up) st.up[k] = cfg[k]; else st.gear[k] = true; }
        const r = playJob(P, j, st, { speed: +process.argv[3] || 900, limit: 400 });
        line += (r.secs.toFixed(0) + (r.res.tough >= 0.7 ? '*' : ' ')).padStart(8);
      }
      console.log(line);
    }
  }
  if (cmd === 'job') {
    const job = P.DATA.jobs.find(j => j.id === process.argv[3]);
    const st = P.freshState();
    (process.argv[5] || '').split(',').filter(Boolean).forEach(kv => { const [k, v] = kv.split('='); if (k in st.up) st.up[k] = +v; else if (k in st.gear) st.gear[k] = true; });
    const r = playJob(P, job, st, { speed: +process.argv[4] || 900 });
    console.log(job.id, 'secs', r.secs.toFixed(1), 'cov', r.cov.toFixed(3), 'passes', r.passes, 'flow', r.res.flow.toFixed(2), 'tough', r.res.tough.toFixed(2), 'total0', r.w.total0, 'toughN', r.w.toughTotal);
  }
}
