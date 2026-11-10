const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const apply = require('./apply_mobile_icon.cjs');
const cwd = process.cwd();
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'carrier-icon-'));
try {
  process.chdir(dir);
  assert.deepEqual(apply({ icon: 'original.png' }), { icon: 'original.png' });
  const image = Buffer.from('fixed image bytes');
  fs.writeFileSync('.atoms-icon.png', image);
  fs.writeFileSync('.atoms-icon-adaptive.png', image);
  fs.writeFileSync('.atoms-icon.json', JSON.stringify({ icon: '.atoms-icon.png', fingerprint: crypto.createHash('sha256').update(image).digest('hex') }));
  const result = apply({ extra: { keep: true }, ios: { bundleIdentifier: 'keep', icon: { dark: 'old' } }, android: { package: 'keep', adaptiveIcon: { monochromeImage: 'old', backgroundImage: 'old' } } });
  assert.equal(result.icon, './.atoms-icon.png');
  assert.equal(result.ios.icon, result.icon);
  assert.equal(result.ios.bundleIdentifier, 'keep');
  assert.equal(result.android.package, 'keep');
  assert.deepEqual(result.extra, { keep: true });
  assert.deepEqual(result.android.adaptiveIcon, { foregroundImage: './.atoms-icon-adaptive.png', backgroundColor: '#FFFFFF' });
  fs.writeFileSync('.atoms-icon.png', 'changed');
  assert.throws(() => apply({}), /fingerprint mismatch/);
  console.log('carrier icon tests passed');
} finally {
  process.chdir(cwd);
  fs.rmSync(dir, { recursive: true, force: true });
}
