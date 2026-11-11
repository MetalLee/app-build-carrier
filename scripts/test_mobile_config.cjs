const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const validate = require('./validate_mobile_config.cjs');

test('native callback is checked against resolved config only when backend is enabled', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'mobile-config-'));
  try {
    validate({}, root);
    fs.writeFileSync(path.join(root, 'mobile-backend.json'), 'null');
    validate({}, root);
    fs.writeFileSync(path.join(root, 'mobile-backend.json'), JSON.stringify({baseUrl: 'https://api.example'}));
    for (const scheme of [undefined, 'other', ['other']]) {
      assert.throws(() => validate({scheme}, root), /registered atoms-mobile/);
    }
    validate({scheme: 'atoms-mobile'}, root);
    validate({scheme: ['other', 'atoms-mobile']}, root);
  } finally {
    fs.rmSync(root, {recursive: true, force: true});
  }
});
