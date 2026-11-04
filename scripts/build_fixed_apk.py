"""Consume only the server-assembled, pinned Expo container; never a business workspace."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_SHA = '6e29ad7e3ae124b3411f60d9e540f98021faaaf6'
FILES = json.loads((ROOT / 'scripts/template-files.json').read_text())
SIGNING_REF = 'atoms_mobile_demo'


def require(condition):
    if not condition:
        raise ValueError('fixed input rejected')


def run(args, cwd, env=None):
    # Build tools can echo environment/config on failure; never relay their output.
    return subprocess.run(args, cwd=cwd, env=env, check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def validate(env):
    for key in ('CODE_URL', 'ARTIFACT_UPLOAD_URL', 'SOURCE_SHA256', 'TEMPLATE_SHA',
                'DEPENDENCY_LOCK_SHA256', 'CARRIER_SHA', 'CHAT_ID', 'TASK_ID',
                'TARGET_ID', 'CONFIG_REVISION', 'BUILD_TARGET', 'ATTEMPT',
                'SUBMISSION_KEY', 'SIGNING_REF', 'CM_KEYSTORE_PATH',
                'CM_KEYSTORE_PASSWORD', 'CM_KEY_ALIAS', 'CM_KEY_PASSWORD'):
        require(bool(env.get(key)))
    require(env['BUILD_TARGET'] == 'apk')
    require(env['SIGNING_REF'] == SIGNING_REF and env['CM_KEY_ALIAS'] == 'atoms-mobile-demo')
    require(Path(env['CM_KEYSTORE_PATH']).is_file())
    require(env['TEMPLATE_SHA'] == TEMPLATE_SHA)
    require(env['DEPENDENCY_LOCK_SHA256'] == FILES['package-lock.json'])
    require(re.fullmatch('[a-f0-9]{64}', env['SOURCE_SHA256']))
    require(re.fullmatch('[a-f0-9]{40}', env['CARRIER_SHA']))
    require(run(['git', 'rev-parse', 'HEAD'], ROOT).decode().strip() == env['CARRIER_SHA'])
    for key in ('TASK_ID', 'TARGET_ID', 'CONFIG_REVISION', 'ATTEMPT'):
        require(re.fullmatch('[1-9][0-9]*', env[key]))
    for key in ('CODE_URL', 'ARTIFACT_UPLOAD_URL'):
        url = urllib.parse.urlsplit(env[key])
        require(url.scheme == 'https' and url.hostname and not url.username and not url.password and not url.fragment)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('redirect rejected')


def transfer(url, destination=None, artifact=None):
    opener = urllib.request.build_opener(NoRedirect())
    if artifact is None:
        request = urllib.request.Request(url)
    else:
        request = urllib.request.Request(url, data=artifact.read_bytes(), method='PUT',
                                         headers={'Content-Type': 'application/octet-stream'})
    with opener.open(request, timeout=300) as response:
        require(200 <= response.status < 300)
        if destination is not None:
            with destination.open('wb') as output:
                total = 0
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    require(total <= 32 * 1024 * 1024)
                    output.write(chunk)


def extract(archive, destination, digest):
    require(hashlib.sha256(archive.read_bytes()).hexdigest() == digest)
    with zipfile.ZipFile(archive) as source:
        entries = source.infolist()
        names = [entry.filename for entry in entries]
        required = set(FILES) | {'container.config.json'}
        require(required <= set(names) <= required | {'assets/icon.png', 'assets/splash.png'})
        require(len(names) == len(set(names)))
        require(sum(entry.file_size for entry in entries) <= 32 * 1024 * 1024)
        for entry in entries:
            mode = entry.external_attr >> 16
            require(stat.S_IFMT(mode) in (0, stat.S_IFREG))
            content = source.read(entry)
            if entry.filename in FILES:
                require(hashlib.sha256(content).hexdigest() == FILES[entry.filename])
            target = destination / entry.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)


SIGNING = '''
android {
    signingConfigs {
        release {
            storeFile file(System.getenv('CM_KEYSTORE_PATH'))
            storePassword System.getenv('CM_KEYSTORE_PASSWORD')
            keyAlias System.getenv('CM_KEY_ALIAS')
            keyPassword System.getenv('CM_KEY_PASSWORD')
        }
    }
    buildTypes { release { signingConfig signingConfigs.release } }
}
'''


def build(env):
    stage = 'validation'
    try:
        validate(env)
        with tempfile.TemporaryDirectory(prefix='fixed-apk-') as temporary:
            root = Path(temporary)
            archive, app = root / 'input.zip', root / 'app'
            stage = 'download'
            transfer(env['CODE_URL'], destination=archive)
            stage = 'input verification'
            extract(archive, app, env['SOURCE_SHA256'])
            # No signed URLs or keystore secrets in npm/Expo subprocess environments.
            public_env = {k: v for k, v in env.items() if k not in
                          {'CODE_URL', 'ARTIFACT_UPLOAD_URL'} and not k.startswith('CM_KEY')}
            stage = 'dependencies'
            run(['npm', 'ci', '--no-audit', '--no-fund'], app, public_env)
            stage = 'prebuild'
            run(['node', '--input-type=module', '-e',
                 "import {validateConfig} from './src/policy.mjs'; import fs from 'node:fs'; validateConfig(JSON.parse(fs.readFileSync('container.config.json')));"], app, public_env)
            run(['./node_modules/.bin/expo', 'prebuild', '--platform', 'android', '--no-install'], app, public_env)
            stage = 'signing and compilation'
            with (app / 'android/app/build.gradle').open('a') as gradle:
                gradle.write(SIGNING)
            signing_env = dict(public_env)
            signing_env.update({k: env[k] for k in ('CM_KEYSTORE_PATH', 'CM_KEYSTORE_PASSWORD', 'CM_KEY_ALIAS', 'CM_KEY_PASSWORD')})
            run(['./gradlew', '--no-daemon', 'assembleRelease'], app / 'android', signing_env)
            outputs = list((app / 'android/app/build/outputs/apk').rglob('*.apk'))
            artifact = app / 'android/app/build/outputs/apk/release/app-release.apk'
            require(outputs == [artifact] and artifact.stat().st_size > 0)
            tools = Path(env['ANDROID_SDK_ROOT']) / 'build-tools'
            verifier = sorted(tools.glob('*/apksigner'), key=lambda p: tuple(int(n) for n in p.parent.name.split('.')))[-1]
            run([str(verifier), 'verify', '--verbose', str(artifact)], app, public_env)
            stage = 'upload'
            transfer(env['ARTIFACT_UPLOAD_URL'], artifact=artifact)
        print('fixed APK uploaded')
        return 0
    except Exception:
        # Deliberately bounded diagnostics: exceptions may contain presigned URLs/secrets.
        print('fixed APK failed: ' + stage)
        return 1


if __name__ == '__main__':
    raise SystemExit(build(dict(os.environ)))
