const fs = require('node:fs');
const crypto = require('node:crypto');

// Run after Expo resolves dynamic config, before prebuild consumes app.json.
module.exports = function applyMobileIcon(expo) {
  if (!fs.existsSync('.atoms-icon.json')) return expo;
  const input = JSON.parse(fs.readFileSync('.atoms-icon.json', 'utf8'));
  const verify = (file, fingerprint, expected) => {
    if (file !== expected || !/^[a-f0-9]{64}$/.test(fingerprint)) {
      throw new Error('Invalid mobile icon input');
    }
    if (crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex') !== fingerprint) {
      throw new Error('Mobile icon fingerprint mismatch');
    }
  };
  if (input.icon) {
    verify(input.icon, input.fingerprint, '.atoms-icon.png');
    fs.accessSync('.atoms-icon-adaptive.png');
    expo.icon = './.atoms-icon.png';
    expo.ios = { ...expo.ios, icon: expo.icon };
    expo.android = { ...expo.android, icon: expo.icon,
      adaptiveIcon: { foregroundImage: './.atoms-icon-adaptive.png', backgroundColor: '#FFFFFF' } };
  }
  if (input.dark_icon) {
    verify(input.dark_icon, input.dark_fingerprint, '.atoms-icon-dark.png');
    const light = typeof expo.ios?.icon === 'string' ? expo.ios.icon : expo.ios?.icon?.light || expo.icon;
    if (!light) throw new Error('A default icon is required for the iOS dark icon');
    expo.ios = { ...expo.ios, icon: { light, dark: './.atoms-icon-dark.png' } };
  }
  if (!input.icon && !input.dark_icon) throw new Error('Invalid mobile icon input');
  return expo;
};
