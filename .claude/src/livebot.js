/* Plays the live page through its test hooks: the same strategy as grime_sim.js playJob, but on the real controller. */
window.__bot = function (opts) {
  opts = opts || {};
  var g = window.__grime, P = g.PURE, D = P.DATA, G = g.G(), w = G.w, rig = G.rig, C = D.cell, gw = w.gw, gh = w.gh;
  var speed = opts.speed || 900, tickMs = 1000 / 60, step = speed / 60, limit = opts.limit || 600;
  var tips = D.tips.filter(function (t) { return !t.soap; }).sort(function (a, b) { return b.r - a.r; });
  function Hof(th, k) { var h = k ? D.kinds[k].h : (th <= D.bands[0].top ? D.bands[0].h : th <= D.bands[1].top ? D.bands[1].h : D.bands[2].h); if (k === 1 && rig.hot) h *= 0.5; return h; }
  function capable(tip) { var pe = tip.p * rig.pMul * (1 - rig.fall * 0.35); return function (i) { return pe > Hof(w.thick[i], w.kind[i]) * 1.3; }; }
  var x = w.W * 0.5, y = w.H * 0.5, ticks = 0;
  function cov() { return P.coverage(w); }
  function alive() { return G.phase === 'play' && G.w.secs < limit; }
  function move(tx, ty) {
    for (;;) {
      if (!alive()) return;
      var dx = tx - x, dy = ty - y, d = Math.hypot(dx, dy);
      if (d <= step) { x = tx; y = ty; g.pointer(x, y, true); g.advance(tickMs); ticks++; return; }
      x += dx / d * step; y += dy / d * step; g.pointer(x, y, true); g.advance(tickMs); ticks++;
      if (cov() >= D.wash.doneAt) return;
    }
  }
  function tapAt(tx, ty) {
    g.pointer(tx, ty, false); x = tx; y = ty;
    g.surface(); g.pointer(tx, ty, true); g.pointer(tx, ty, false);
    for (var k = 0; k < 90 && alive(); k++) { g.advance(tickMs); ticks++; }
  }
  if (rig.surface && !opts.noSurface) {
    var R = D.surface.r * rig.rMul, sx = R * 1.45, sy = R * 1.25, row = 0;
    for (var yy = D.surface.edge; yy < w.H && alive(); yy += sy, row++) {
      for (var xx = D.surface.edge + (row % 2 ? sx / 2 : 0); xx < w.W && alive(); xx += sx) {
        var any = false, cx0 = Math.max(0, Math.floor((xx - R * 0.6) / C)), cx1 = Math.min(gw - 1, Math.floor((xx + R * 0.6) / C)), cy0 = Math.max(0, Math.floor((yy - R * 0.6) / C)), cy1 = Math.min(gh - 1, Math.floor((yy + R * 0.6) / C));
        for (var cy = cy0; cy <= cy1 && !any; cy++) for (var cx = cx0; cx <= cx1; cx++) { var i = cy * gw + cx; if (w.thick[i] > 0 && !(w.kind[i] && D.surface.skip.indexOf(w.kind[i]) >= 0)) { any = true; break; } }
        if (any) tapAt(Math.min(w.W - D.surface.edge, xx), Math.min(w.H - D.surface.edge, yy));
        if (cov() >= D.wash.doneAt) break;
      }
      if (cov() >= D.wash.doneAt) break;
    }
    g.tip('white');
  }
  var guard = 0;
  while (alive() && cov() < D.wash.doneAt && guard++ < 60) {
    var toughMode = !opts.noToughFirst && w.toughTotal > 0 && w.toughDone < w.toughTotal * 0.8;
    var pick = tips[tips.length - 1], left = 0, i2;
    for (i2 = 0; i2 < w.thick.length; i2++) if (w.thick[i2] > 0 && (!toughMode || w.tough[i2])) left++;
    for (var t = 0; t < tips.length; t++) {
      var capT = capable(tips[t]), c = 0;
      for (i2 = 0; i2 < w.thick.length; i2++) if (w.thick[i2] > 0 && (!toughMode || w.tough[i2]) && capT(i2)) c++;
      if (c >= left * (toughMode ? 0.5 : 0.25)) { pick = tips[t]; break; }
    }
    g.tip(pick.id);
    var Rr = D.wash.baseR * pick.r * rig.rMul, cap0 = capable(pick), spacing = Rr * 1.3;
    var cap = toughMode ? function (i) { return w.tough[i] && cap0(i); } : cap0;
    var dir = 1, anyRow = false;
    for (var yy2 = spacing / 2; yy2 < w.H + spacing / 2 && alive(); yy2 += spacing) {
      var a0 = Math.max(0, Math.floor((yy2 - Rr) / C)), a1 = Math.min(gh - 1, Math.floor((yy2 + Rr) / C)), xmin = 1e9, xmax = -1e9;
      for (var cy2 = a0; cy2 <= a1; cy2++) for (var cx2 = 0; cx2 < gw; cx2++) { var j = cy2 * gw + cx2; if (w.thick[j] > 0 && cap(j)) { var xv = (cx2 + 0.5) * C; if (xv < xmin) xmin = xv; if (xv > xmax) xmax = xv; } }
      if (xmax < 0) continue;
      anyRow = true;
      var xa = Math.max(0, xmin - Rr * 0.5), xb = Math.min(w.W, xmax + Rr * 0.5), ya = Math.min(w.H - 5, yy2);
      if (dir > 0) { move(xa, ya); move(xb, ya); } else { move(xb, ya); move(xa, ya); }
      dir = -dir;
      if (cov() >= D.wash.doneAt) break;
    }
    if (!anyRow) break;
  }
  g.pointer(x, y, false);
  return { secs: w.secs, cov: cov(), phase: G.phase, ticks: ticks, tough: w.toughTotal ? w.toughDone / w.toughTotal : 1 };
};
