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

test('new consumer schemes match installed config, independent of backend owner', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'native-consumer-'));
  const previous = process.env.CHAT_ID;
  try {
    fs.writeFileSync(path.join(root, 'mobile-backend.json'), JSON.stringify({ projectId: 'shared-owner' }));
    for (const consumer of ['app-a', 'app-b']) {
      process.env.CHAT_ID = consumer;
      const scheme = 'atoms-' + require('node:crypto').createHash('sha256').update(consumer).digest('hex').slice(0, 24);
      const extra = { nativeAuthVersion: 2, nativeAuthConsumerId: consumer };
      fs.writeFileSync(path.join(root, "app.json"), JSON.stringify({ expo: { scheme, extra } }));
      validate({ scheme, extra }, root);
      for (const invalid of ['atoms-mobile', ['atoms-mobile', scheme], 'atoms-other']) {
        assert.throws(() => validate({ scheme: invalid, extra }, root), /platform Native auth identity/);
      }
      assert.throws(() => validate({ scheme, extra: { ...extra, nativeAuthConsumerId: 'other' } }, root), /platform Native auth identity/);
      assert.throws(() => validate({ scheme, extra: { ...extra, nativeAuthConsumerId: '%NATIVE_AUTH_CONSUMER_ID%' } }, root), /platform Native auth identity/);
    }
  } finally {
    if (previous === undefined) delete process.env.CHAT_ID; else process.env.CHAT_ID = previous;
    fs.rmSync(root, { recursive: true, force: true });
  }
});


test('dynamic config cannot switch legacy and consumer protocols or swap consumers', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'native-protocol-'));
  try {
    fs.writeFileSync(path.join(root, 'mobile-backend.json'), '{"projectId":"owner"}');
    const consumer = { scheme: 'atoms-' + require('node:crypto').createHash('sha256').update('app-a').digest('hex').slice(0, 24),
      extra: { nativeAuthVersion: 2, nativeAuthConsumerId: 'app-a' } };
    const legacy = { scheme: 'atoms-mobile' };
    for (const [original, effective] of [[legacy, consumer], [consumer, legacy],
        [consumer, { ...consumer, extra: { ...consumer.extra, nativeAuthConsumerId: 'app-b' } }]]) {
      fs.writeFileSync(path.join(root, 'app.json'), JSON.stringify({ expo: original }));
      assert.throws(() => validate(effective, root), /preserve the platform Native auth identity/);
    }
    fs.unlinkSync(path.join(root, 'app.json'));
    assert.throws(() => validate(consumer, root), /preserve the platform Native auth identity/);
    validate(legacy, root);
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
});
