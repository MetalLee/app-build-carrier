# Fixed Website → Android carrier

`website-apk` is the backward-compatible fixed-input workflow for both targets; its ID stays unchanged. It is the workflow for MetalLee/app-build-carrier. The
legacy `android-build` workflow is unchanged (including its existing AAB behavior).
Do not select the legacy workflow for fixed inputs. No business workspace is copied,
no SDK is upgraded, and the fixed workflow supports only `apk` and `aab` (no iOS).

## Integration release contract

Configure atoms-chat `codemagic.mobile_carriers.apk` and
`codemagic.mobile_carriers.aab` with this repository, the
Codemagic App ID, workflow_id `website-apk`, an **authorized published protected
tag**, and that tag's exact 40-character commit SHA. Obtain the local candidate
SHA with `git rev-parse HEAD`; a local commit is not remotely fetchable. This task
does not publish a tag or change atoms-chat runtime configuration. Operations must
publish the reviewed release only after user authorization, then register its tag
and SHA. Existing inputs retain their original carrier lock.

Set both `codemagic.mobile_signing_refs.apk` and
`codemagic.mobile_signing_refs.aab` to `atoms_mobile_demo`. This exact reference
maps only to the workflow's Codemagic team keystore `atoms_mobile_demo`, whose key
alias must be `atoms-mobile-demo`. No arbitrary references or keystore paths from
input archives are accepted. Codemagic injects CM_KEYSTORE_PATH,
CM_KEYSTORE_PASSWORD, CM_KEY_ALIAS, CM_KEY_PASSWORD; never put these in the ZIP or
repository. The Linux image must provide Python >=3.8, Git, Android SDK/build-tools
(`ANDROID_SDK_ROOT`), Node 20 and Java 17. Android release Gradle signing uses only
these injected values. `apksigner verify --print-certs` must succeed and its sole signer must match
the injected keystore alias certificate before APK PUT. AAB uses Java 17
`jarsigner -verify -strict` with that keystore and alias, requires `jar verified.`,
and checks bundle config/base manifest entries before PUT; apksigner is never used
for AAB. Self-signed certificates are trusted only via the selected keystore.

**Demo limitation:** this release authorizes only the team demo reference/alias,
not production per-project keys. A reference/alias alone is not a pinned certificate
fingerprint: Codemagic administrators must protect the actual keystore binding.
For production, provision the project’s existing upload/release key in Codemagic,
then release a reviewed carrier/YAML reference+alias mapping and matching server
configuration. Never silently substitute a demo/debug key or rotate an existing
application’s key. No new key platform or automatic rotation is implemented.

The existing FixedCodemagicProvider supplies all of:

| Variable | Contract |
| --- | --- |
| CODE_URL | HTTPS signed GET of the fixed ZIP; redirects rejected |
| ARTIFACT_UPLOAD_URL | HTTPS signed PUT for this task's `build-artifacts/{chat_id}/{task_id}/app.{apk|aab}` matching BUILD_TARGET; redirects rejected |
| SOURCE_SHA256 | SHA256 of exact downloaded ZIP bytes |
| TEMPLATE_SHA | `6e29ad7e3ae124b3411f60d9e540f98021faaaf6` |
| DEPENDENCY_LOCK_SHA256 | `3cb4f87e8f8bdd6fcd00214377793ddf97c333c17af3d15952b089b32431f454` |
| CARRIER_SHA | Exact checkout HEAD, not a floating branch |
| CHAT_ID, SUBMISSION_KEY | Required opaque task correlation values, not printed |
| TASK_ID, TARGET_ID, CONFIG_REVISION, ATTEMPT | Required positive integer task metadata |
| BUILD_TARGET | Exactly `apk` or `aab`; same `website-apk` workflow |
| SIGNING_REF | Exactly `atoms_mobile_demo` |

The producer contract is atoms-chat `7cf127e`, documented in
`docs/mobile-fixed-input.md` and `docs/mobile-build-foundation.md` and implemented in
`src/service/build/provider/fixed_codemagic.py`. There is no manifest in the ZIP:
revision/deployment/task attribution remains server-owned. The carrier verifies
archive bytes, exact shipped file set and each immutable file's SHA256 (including
the dependency lock) from the pinned template. Only container.config.json and
optional assets/icon.png and assets/splash.png are variable;
assets/default-splash.png is mandatory and hash-locked; the pinned template validator validates the
runtime config. ZIP traversal, duplicate entries, symlinks, extra source/native
files and oversized archives are rejected. Limits: 32 MiB compressed/uncompressed.

The clean temporary app runs `npm ci`, Expo Android prebuild with `--no-install`,
and Gradle `assembleRelease` for APK or `bundleRelease` for AAB. Only the nonempty
`android/app/build/outputs/apk/release/app-release.apk` or
`android/app/build/outputs/bundle/release/app-release.aab` respectively is allowed,
with no other file of the target extension under its output directory. Upload uses PUT and
`Content-Type: application/octet-stream`; only HTTP 2xx succeeds. No status upload
URL is required: provider polling plus authenticated object HEAD owns completion.
An upload error exits nonzero, never a success-status side channel. Temporary input,
source and build files are removed on normal success/failure. No APK/AAB is separately
published as a Codemagic artifact by this workflow.

Logs expose bounded stage failures/success only, not subprocess output, exceptions,
signed URLs or signing material. npm/Expo receive neither signed URLs nor keystore
variables. The CI service still holds submitted environment values: restrict access
to that service. Existing server task/result metrics remain the observability owner;
carrier stage logs do not prove metric ingestion or Android installation.

## Reproduce local checks

```sh
python3 -m venv .venv-check
.venv-check/bin/pip install PyYAML==6.0.3
MOBILE_TEMPLATE_REPOSITORY=/absolute/path/to/mgx_template \
  .venv-check/bin/python -m unittest discover -s tests -v
git diff --check
```

Tests read real Git objects at the pinned template SHA. They validate YAML,
checkout/template/lock/signing mismatch rejection, archive checksum and unsafe ZIP
rejection, compile/sign/verify/upload sequencing, unique/nonempty APK/AAB enforcement, missing output and wrong signer rejection,
HTTP PUT contract, redirects, failure exits and secret redaction. npm, Expo, Gradle,
apksigner, keytool, jarsigner and network are **doubles**, not real compilation/signing/storage evidence.

Local result for this increment: 7 tests passed, including both targets and failure
subcases; YAML parsed with PyYAML 6.0.3. Template hashes are read from the accepted
Git commit (not the template checkout HEAD). The system Java launcher has no JDK,
so real JAR/APK signature verification was unavailable locally.

Not executed: Codemagic cloud build, real npm/Expo/Gradle compilation, real signing,
storage PUT/HEAD, device install or appearance verification. No push/tag/deployment
was performed; the release must be published with separate authorization before
remote use. This local result is not cloud-build or device acceptance.

## Producer migration

The server must assemble from the exact new template commit above, with the new
lock digest and `scripts/template-files.json` output set. CLI remains
`node scripts/assemble.mjs CONFIG NEW_DIRECTORY [ICON_PNG|""] [SPLASH_PNG]`.
Authorized, validated PNG downloads remain server-owned; the carrier downloads no
appearance URLs. New config fields are `theme_color`, `splash_background_color`,
`splash_image_url` and `android_version_code` (1..2100000000). Missing values retain
template defaults. Existing fixed inputs must keep their original template/carrier
locks; do not relabel old ZIPs with the new template SHA. APK and AAB use the same
application ID/versionCode/key for a given config revision. VersionCode allocation,
permissions, idempotent submission and result ownership stay in atoms-chat.
