const fs = require('node:fs');

module.exports = function validateMobileConfig(expo, root = process.cwd()) {
  const path = require('node:path').join(root, 'mobile-backend.json');
  const backend = fs.existsSync(path) ? JSON.parse(fs.readFileSync(path, 'utf8')) : null;
  const schemes = Array.isArray(expo.scheme) ? expo.scheme : [expo.scheme];
  const appPath = require('node:path').join(root, 'app.json');
  const original = fs.existsSync(appPath) ? JSON.parse(fs.readFileSync(appPath, 'utf8')).expo : undefined;
  const native = expo.extra;
  const isConsumer = native?.nativeAuthVersion === 2;
  if (isConsumer !== (original?.extra?.nativeAuthVersion === 2) || (isConsumer && (
      native.nativeAuthConsumerId !== original.extra.nativeAuthConsumerId ||
      expo.scheme !== original.scheme))) {
    throw new Error('Dynamic Expo config must preserve the platform Native auth identity');
  }
  if (isConsumer) {
    const consumer = native.nativeAuthConsumerId;
    if (typeof consumer !== 'string' || !/^[A-Za-z0-9_-]{1,128}$/.test(consumer) ||
        (process.env.CHAT_ID && consumer !== process.env.CHAT_ID)) {
      throw new Error('Invalid Native consumer identity');
    }
    const scheme = 'atoms-' + require('node:crypto').createHash('sha256').update(consumer).digest('hex').slice(0, 24);
    if (schemes.length !== 1 || schemes[0] !== scheme) {
      throw new Error('Mobile native callback must match the consumer project');
    }
  } else if (backend && !schemes.includes('atoms-mobile')) {
    throw new Error('Mobile native callback must match the registered atoms-mobile scheme');
  }
};
