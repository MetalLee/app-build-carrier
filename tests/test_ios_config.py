import json
import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('version,scheme,accepted', [
    ('2.3.4', 'atoms-mobile', True),
    ('2.3.4', ['custom', 'atoms-mobile'], True),
    ('2.3.4', 'wrong', False),
    ('not-a-version', 'atoms-mobile', False),
])
def test_ipa_validates_effective_config_without_overriding_its_version(tmp_path, version, scheme, accepted):
    app = tmp_path / 'app'
    app.mkdir()
    (app / 'app.config.ts').write_text('export default {};')
    (app / 'mobile-backend.json').write_text('{"baseUrl":"https://api.example"}')
    executable = app / 'node_modules/.bin/expo'
    executable.parent.mkdir(parents=True)
    effective = {'version': version, 'scheme': scheme, 'plugins': ['expo-secure-store']}
    executable.write_text('#!/usr/bin/env node\nconsole.log(' + json.dumps(json.dumps(effective)) + ');\n')
    executable.chmod(0o755)
    script = (ROOT / 'scripts/build_ipa.sh').read_text().split('stage=configuration\n', 1)[1].split('stage=prebuild', 1)[0]
    result = subprocess.run(['bash', '-eu', '-c', script], cwd=app, capture_output=True, env={
        **os.environ, 'work_dir': str(tmp_path), 'CM_BUILD_DIR': str(ROOT),
        'BUNDLE_ID': 'com.example.app', 'BUILD_NUMBER': '1.2.3', 'APP_VERSION': '9.9.9',
    })
    assert (result.returncode == 0) == accepted, result.stderr
    if accepted:
        config = json.loads((app / 'app.json').read_text())['expo']
        assert config['version'] == version
        assert config['plugins'] == effective['plugins']
        assert config['ios'] == {'bundleIdentifier': 'com.example.app', 'buildNumber': '1.2.3'}
        assert not (app / 'app.config.ts').exists()


@pytest.mark.parametrize('mismatch,reason,expected', [
    (True, 'You already have a current Distribution certificate or a pending certificate request.', True),
    (True, 'Another conflict', False),
    (False, 'You already have a current Distribution certificate or a pending certificate request.', False),
])
def test_signing_conflict_preserves_error(tmp_path, mismatch, reason, expected):
    log = 'Did not find any Signing Certificates for given private key\n' if mismatch else ''
    log += 'POST https://api.appstoreconnect.apple.com/v1/certificates returned 409: ' + reason
    script = (ROOT / 'scripts/build_ipa.sh').read_text().split('keychain initialize\n', 1)[1].split('keychain add-certificates', 1)[0]
    result = subprocess.run(['bash', '-euo', 'pipefail', '-c',
                             'app-store-connect() { echo "$LOG" >&2; return 17; }\n' + script],
                            capture_output=True, text=True, env={**os.environ, 'LOG': log,
                            'work_dir': str(tmp_path), 'BUNDLE_ID': 'com.test.app'})
    assert result.returncode == 17
    assert log in result.stdout
    assert ('Restore the matching certificate private key' in result.stdout) == expected
