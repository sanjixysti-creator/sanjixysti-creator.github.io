// Node side of the payload tests: runs Pay (and friends) from the page's pure region on a list of cases.
// usage: node pay_core.js <file with the pure code> <cases.json> <out.json>
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
const M = new Function(src + '\nreturn {QR:QR, Pay:Pay, Tone:Tone, Draw:Draw};')();
const cases = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const out = [];
function rowsOf(code) {
  return Array.from({ length: code.size }, (_, y) => Array.from(code.modules.slice(y * code.size, (y + 1) * code.size)).join(''));
}
for (const c of cases) {
  try {
    if (c.fn) {
      const f = M.Pay[c.fn] || M.Tone[c.fn] || M.Draw[c.fn] || M.QR[c.fn];
      out.push({ id: c.id, value: f.apply(null, c.args) });
    } else {
      const r = M.Pay.build(c.type, c.fields);
      const o = { id: c.id, res: r };
      if (c.encode && !r.empty && Object.keys(r.errors).length === 0) {
        try {
          const code = M.QR.encode(M.QR.segmentsFor(r.text), { level: c.level || 'M' });
          o.version = code.version; o.size = code.size; o.rows = rowsOf(code);
          o.utf8 = Buffer.from(M.QR.utf8(r.text)).toString('hex');
        } catch (e) { o.encodeError = e.code || String(e.message); }
      }
      out.push(o);
    }
  } catch (e) { out.push({ id: c.id, error: String((e && e.stack) || e) }); }
}
fs.writeFileSync(process.argv[4], JSON.stringify(out));
