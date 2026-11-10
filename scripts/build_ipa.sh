#!/usr/bin/env bash
set -euo pipefail
set +x
: "${CODE_URL:?}" "${ARTIFACT_UPLOAD_URL:?}" "${STATUS_UPLOAD_URL:?}"
: "${BUNDLE_ID:?}" "${APP_VERSION:?}" "${BUILD_NUMBER:?}"
: "${APP_STORE_CONNECT_PRIVATE_KEY:?}" "${CERTIFICATE_PRIVATE_KEY:?}"
work_dir=$(mktemp -d)
status=failed
stage=source
artifact_size=0
finish() {
  exit_code=$?
  trap - EXIT
  export IPA_STATUS="$status" IPA_STAGE="$stage" IPA_SIZE="$artifact_size" IPA_LOG="$work_dir/build.log"
  python3 - <<'PY' > "$work_dir/status.json"
import json, os, pathlib, re
log = pathlib.Path(os.environ["IPA_LOG"])
detail = log.read_text(errors="replace") if log.exists() else ""
for name in ("APP_STORE_CONNECT_PRIVATE_KEY", "CERTIFICATE_PRIVATE_KEY", "APP_STORE_CONNECT_ISSUER_ID", "APP_STORE_CONNECT_KEY_IDENTIFIER", "CODE_URL", "ARTIFACT_UPLOAD_URL", "STATUS_UPLOAD_URL"):
    for value in [os.environ.get(name, ""), *os.environ.get(name, "").splitlines()]:
        if value:
            detail = detail.replace(value, "[redacted]")
detail = re.sub(r"\x1b\[[0-9;]*m", "", detail)
errors = [line for line in detail.splitlines() if re.search(r"\berror:|Error:|❌", line)]
detail = ("\n".join(errors[:20])[:2000] + "\n" + detail[-2000:])[-4000:]
json.dump({"status": os.environ["IPA_STATUS"], "error": "" if os.environ["IPA_STATUS"] == "success" else "iOS build failed at " + os.environ["IPA_STAGE"] + "\n" + detail, "artifact_size": int(os.environ["IPA_SIZE"])}, __import__('sys').stdout)
PY
  curl --fail --silent --show-error -X PUT -H 'Content-Type: application/json' --data-binary "@$work_dir/status.json" "$STATUS_UPLOAD_URL" || exit_code=1
  keychain delete >/dev/null 2>&1 || true
  rm -rf "$work_dir"
  exit "$exit_code"
}
trap finish EXIT
# Keep only a bounded, redacted diagnostic in the status response; never export this raw log.
exec > "$work_dir/build.log" 2>&1
curl --fail --silent --show-error --location "$CODE_URL" -o "$work_dir/source.zip"
mkdir "$work_dir/app"
python3 - "$work_dir/source.zip" "$work_dir/app" <<'PY'
import pathlib, sys, zipfile
root = pathlib.Path(sys.argv[2]).resolve()
with zipfile.ZipFile(sys.argv[1]) as source:
    for member in source.infolist():
        if not (root / member.filename).resolve().is_relative_to(root):
            raise ValueError('Invalid source archive path')
    source.extractall(root)
PY
cd "$work_dir/app"
stage=dependencies
if [ -f pnpm-lock.yaml ]; then
  corepack pnpm install --frozen-lockfile
elif [ -f package-lock.json ]; then
  npm ci
elif [ -f yarn.lock ]; then
  corepack yarn install --frozen-lockfile
else
  echo 'A dependency lockfile is required for signed builds' >&2
  exit 1
fi
stage=configuration
./node_modules/.bin/expo config --json > "$work_dir/expo.json"
node - "$work_dir/expo.json" "$CM_BUILD_DIR/scripts/apply_mobile_icon.cjs" <<'JS'
const fs = require('node:fs');
const expo = require(process.argv[3])(JSON.parse(fs.readFileSync(process.argv[2], 'utf8')));
expo.version = process.env.APP_VERSION;
expo.ios = { ...expo.ios, bundleIdentifier: process.env.BUNDLE_ID, buildNumber: process.env.BUILD_NUMBER };
fs.writeFileSync('app.json', JSON.stringify({ expo }));
for (const name of ['app.config.js', 'app.config.ts']) fs.rmSync(name, { force: true });
JS
stage=prebuild
./node_modules/.bin/expo prebuild --platform ios --no-install
(cd ios && pod install)
stage=signing
keychain initialize
app-store-connect fetch-signing-files "$BUNDLE_ID" --type IOS_APP_STORE --create
keychain add-certificates
xcode-project use-profiles
stage=archive
workspace=$(find ios -maxdepth 1 -name '*.xcworkspace' -type d -print -quit)
test -n "$workspace"
scheme=$(basename "$workspace" .xcworkspace)
# Generated names such as Expo can collide with dependency modules and schemes.
node <<'JS'
const fs = require('node:fs');
const { IOSConfig } = require('expo/config-plugins');
const project = IOSConfig.XcodeUtils.getPbxproj(process.cwd());
const { target } = project.getTarget('com.apple.product-type.application');
for (const [, config] of IOSConfig.XcodeUtils.getBuildConfigurationsForListId(project, target.buildConfigurationList)) {
  config.buildSettings.PRODUCT_MODULE_NAME = 'AtomsApplication';
}
fs.writeFileSync(project.filepath, project.writeSync());
JS
if [ "$scheme" != AtomsApplication ]; then
  mv "ios/$scheme.xcodeproj/xcshareddata/xcschemes/$scheme.xcscheme" \
    "ios/$scheme.xcodeproj/xcshareddata/xcschemes/AtomsApplication.xcscheme"
fi
scheme=AtomsApplication
xcode-project build-ipa --workspace "$workspace" --scheme "$scheme"
stage=upload
artifact=$(find build/ios/ipa -maxdepth 1 -name '*.ipa' -type f -print -quit)
test -n "$artifact"
artifact_size=$(stat -f%z "$artifact")
test "$artifact_size" -gt 0
curl --fail --silent --show-error -X PUT -H 'Content-Type: application/octet-stream' -H 'x-amz-acl: private' --upload-file "$artifact" "$ARTIFACT_UPLOAD_URL"
status=success
