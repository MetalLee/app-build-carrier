# Fixed Website → APK carrier

`website-apk` is the fixed-input workflow for MetalLee/app-build-carrier. The
legacy `android-build` workflow is unchanged (including its existing AAB behavior).
Do not select the legacy workflow for fixed inputs. No business workspace is copied,
no SDK is upgraded, and the new workflow supports only APK.

## Integration release contract

Configure atoms-chat `codemagic.mobile_carriers.apk` with this repository, the
Codemagic App ID, workflow_id `website-apk`, an **authorized published protected
tag**, and that tag's exact 40-character commit SHA. Obtain the local candidate
SHA with `git rev-parse HEAD`; a local commit is not remotely fetchable. This task
does not publish a tag or change atoms-chat runtime configuration. Operations must
publish the reviewed release only after user authorization, then register its tag
and SHA. Existing inputs retain their original carrier lock.

Set `codemagic.mobile_signing_refs.apk` to `atoms_mobile_demo`. This exact reference
maps only to the workflow's Codemagic team keystore `atoms_mobile_demo`, whose key
alias must be `atoms-mobile-demo`. No arbitrary references or keystore paths from
input archives are accepted. Codemagic injects CM_KEYSTORE_PATH,
CM_KEYSTORE_PASSWORD, CM_KEY_ALIAS, CM_KEY_PASSWORD; never put these in the ZIP or
repository. The Linux image must provide Python >=3.8, Git, Android SDK/build-tools
(`ANDROID_SDK_ROOT`), Node 20 and Java 17. Android release Gradle signing uses only
these injected values. `apksigner verify` must succeed before PUT.

The existing FixedCodemagicProvider supplies all of:

| Variable | Contract |
| --- | --- |
| CODE_URL | HTTPS signed GET of the fixed ZIP; redirects rejected |
| ARTIFACT_UPLOAD_URL | HTTPS signed PUT for this task's `build-artifacts/{chat_id}/{task_id}/app.apk`; redirects rejected |
| SOURCE_SHA256 | SHA256 of exact downloaded ZIP bytes |
| TEMPLATE_SHA | `9ab7706ed762fdb92e403c30a5f2aaf2eb388ecb` |
| DEPENDENCY_LOCK_SHA256 | `1975df8ee34e8d888d2fda9b1e8e1b7f5b00c198963c09fe08fb9811a013c36d` |
| CARRIER_SHA | Exact checkout HEAD, not a floating branch |
| CHAT_ID, SUBMISSION_KEY | Required opaque task correlation values, not printed |
| TASK_ID, TARGET_ID, CONFIG_REVISION, ATTEMPT | Required positive integer task metadata |
| BUILD_TARGET | Exactly `apk` |
| SIGNING_REF | Exactly `atoms_mobile_demo` |

The producer contract is atoms-chat `7cf127e`, documented in
`docs/mobile-fixed-input.md` and `docs/mobile-build-foundation.md` and implemented in
`src/service/build/provider/fixed_codemagic.py`. There is no manifest in the ZIP:
revision/deployment/task attribution remains server-owned. The carrier verifies
archive bytes, exact shipped file set and each immutable file's SHA256 (including
the dependency lock) from the pinned template. Only container.config.json and
optional assets/icon.png are variable; the pinned template validator validates the
runtime config. ZIP traversal, duplicate entries, symlinks, extra source/native
files and oversized archives are rejected. Limits: 32 MiB compressed/uncompressed.

The clean temporary app runs `npm ci`, Expo Android prebuild with `--no-install`,
and Gradle `assembleRelease`. Only the nonempty
`android/app/build/outputs/apk/release/app-release.apk` is allowed, with no other
APK under the APK output directory. Upload uses PUT and
`Content-Type: application/octet-stream`; only HTTP 2xx succeeds. No status upload
URL is required: provider polling plus authenticated object HEAD owns completion.
An upload error exits nonzero, never a success-status side channel. Temporary input,
source and build files are removed on normal success/failure. No APK is separately
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
rejection, compile/sign/verify/upload sequencing, unique/nonempty APK enforcement,
HTTP PUT contract, redirects, failure exits and secret redaction. npm, Expo, Gradle,
apksigner and network are **doubles**, not real compilation/signing/storage evidence.

Local result: 6 tests passed, including error-path subcases; YAML parsed with
PyYAML 6.0.3. Initial PyYAML installation hit host TLS trust errors; the same wheel
was fetched through curl with TLS verification, checked against PyPI's SHA256, and
installed locally. No TLS bypass was added to the carrier.

Not executed: browser flow, Codemagic cloud build, real npm/Expo/Gradle compilation,
formal keystore signing/certificate inspection, storage PUT/HEAD or Android install.
These need the authorized remote carrier release, team signing access and an Android
device; local tests are not evidence those gates passed.
