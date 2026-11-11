const fs = require('node:fs');

module.exports = function validateMobileConfig(expo, root = process.cwd()) {
  const path = require('node:path').join(root, 'mobile-backend.json');
  const backend = fs.existsSync(path) ? JSON.parse(fs.readFileSync(path, 'utf8')) : null;
  const schemes = Array.isArray(expo.scheme) ? expo.scheme : [expo.scheme];
  if (backend && !schemes.includes('atoms-mobile')) {
    throw new Error('Mobile native callback must match the registered atoms-mobile scheme');
  }
};
