// Node side of the encoder proof: reads a JSON list of cases, encodes each with the page's QR code, prints one JSON result per case.
// usage: node proof_core.js <file with the encoder code> <cases.json> <out.json> [full]
const fs = require('fs'), crypto = require('crypto');
const src = fs.readFileSync(process.argv[2], 'utf8');
const QR = new Function(src + '\nreturn QR;')();
const cases = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const full = process.argv[5] === 'full';
const out = [];
for (const c of cases) {
  let segs;
  if (c.kind === 'bytes') segs = [QR.byteSegment(Array.from(Buffer.from(c.data, 'hex')))];
  else if (c.kind === 'numeric') segs = [QR.numericSegment(c.data)];
  else if (c.kind === 'alnum') segs = [QR.alnumSegment(c.data)];
  else segs = QR.segmentsFor(c.data);
  try {
    const r = QR.encode(segs, { level: c.level, version: c.version || 0, mask: c.mask == null ? -1 : c.mask });
    const h = crypto.createHash('sha1').update(Buffer.from(r.modules)).digest('hex');
    const o = { id: c.id, version: r.version, mask: r.mask, size: r.size, sha1: h };
    if (full) o.rows = Array.from({ length: r.size }, (_, y) => Array.from(r.modules.slice(y * r.size, (y + 1) * r.size)).join(''));
    out.push(o);
  } catch (e) {
    out.push({ id: c.id, error: e.code || String(e.message) });
  }
}
fs.writeFileSync(process.argv[4], JSON.stringify(out));
