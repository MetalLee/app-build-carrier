const fs = require('node:fs');
const crypto = require('node:crypto');

// Run after Expo resolves dynamic config, before prebuild consumes app.json.
module.exports = function applyMobileIcon(expo) {
  if (!fs.existsSync('.atoms-icon.json')) return expo;
  const input = JSON.parse(fs.readFileSync('.atoms-icon.json', 'utf8'));
  if (input.icon !== '.atoms-icon.png' || !/^[a-f0-9]{64}$/.test(input.fingerprint)) {
    throw new Error('Invalid mobile icon input');
  }
  const image = fs.readFileSync(input.icon);
  if (crypto.createHash('sha256').update(image).digest('hex') !== input.fingerprint) {
    throw new Error('Mobile icon fingerprint mismatch');
  }
  fs.accessSync('.atoms-icon-adaptive.png');
  expo.icon = './.atoms-icon.png';
  expo.ios = { ...expo.ios, icon: expo.icon };
  expo.android = { ...expo.android, icon: expo.icon,
    adaptiveIcon: { foregroundImage: './.atoms-icon-adaptive.png', backgroundColor: '#FFFFFF' } };
  return expo;
};
