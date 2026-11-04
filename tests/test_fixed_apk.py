import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

spec = importlib.util.spec_from_file_location('carrier', Path(__file__).resolve().parents[1] / 'scripts/build_fixed_apk.py')
carrier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(carrier)


class CarrierTests(unittest.TestCase):
    def test_bundled_assets_cannot_escape_or_replace_template(self):
        self.files['container.config.json'] = b'{"bundled_web":true}'
        self.files['web/index.html'] = b'<html>Offline</html>'
        self.files['web/assets/app.js'] = b'console.log("offline")'
        archive = self.root / 'bundled.zip'
        payload = self.archive(self.files)
        archive.write_bytes(payload)
        carrier.extract(archive, self.root / 'valid', hashlib.sha256(payload).hexdigest())
        self.assertEqual((self.root / 'valid/web/index.html').read_bytes(), self.files['web/index.html'])
        for name in ['web/../../app.config.js', 'web/.env', 'web//bad', 'web/../secret']:
            with self.subTest(name=name):
                payload = self.archive({**self.files, name: b'unsafe'})
                archive.write_bytes(payload)
                with self.assertRaises(ValueError):
                    carrier.extract(archive, self.root / 'invalid', hashlib.sha256(payload).hexdigest())

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        repo = os.environ['MOBILE_TEMPLATE_REPOSITORY']
        self.files = {name: subprocess.check_output(['git', '-C', repo, 'show',
                      carrier.TEMPLATE_SHA + ':templates/expo-webview-container/' + name]) for name in carrier.FILES}
        self.files['container.config.json'] = b'{}'
        self.zip = self.archive(self.files)
        key = self.root / 'keystore'
        key.touch()
        self.env = dict(CODE_URL='https://example.com/input?secret=URL_SECRET',
                        ARTIFACT_UPLOAD_URL='https://example.com/output?secret=PUT_SECRET',
                        SOURCE_SHA256=hashlib.sha256(self.zip).hexdigest(),
                        TEMPLATE_SHA=carrier.TEMPLATE_SHA,
                        DEPENDENCY_LOCK_SHA256=carrier.FILES['package-lock.json'],
                        CARRIER_SHA=subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode().strip(),
                        CHAT_ID='project', TASK_ID='1', TARGET_ID='2', CONFIG_REVISION='1',
                        BUILD_TARGET='apk', ATTEMPT='1', SUBMISSION_KEY='submission',
                        SIGNING_REF='atoms_mobile_demo', CM_KEY_ALIAS='atoms-mobile-demo',
                        CM_KEYSTORE_PATH=str(key), CM_KEYSTORE_PASSWORD='KEY_SECRET', CM_KEY_PASSWORD='KEY_SECRET',
                        ANDROID_SDK_ROOT=str(self.root / 'sdk'))
        verifier = self.root / 'sdk/build-tools/35.0.0/apksigner'
        verifier.parent.mkdir(parents=True)
        verifier.touch()

    def archive(self, files):
        out = io.BytesIO()
        with zipfile.ZipFile(out, 'w') as archive:
            for name, content in files.items():
                archive.writestr(name, content)
        return out.getvalue()

    def test_contract(self):
        carrier.validate(self.env)
        carrier.validate(dict(self.env, BUILD_TARGET='aab'))
        for key, value in [('CARRIER_SHA', '0' * 40), ('SOURCE_SHA256', 'bad'),
                           ('TEMPLATE_SHA', '0' * 40), ('DEPENDENCY_LOCK_SHA256', '0' * 64),
                           ('SIGNING_REF', 'foreign'), ('CM_KEY_ALIAS', 'foreign'),
                           ('BUILD_TARGET', 'ipa'), ('ATTEMPT', '0'),
                           ('CODE_URL', 'http://example.com')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                carrier.validate(dict(self.env, **{key: value}))

    def test_pinned_archive(self):
        archive = self.root / 'input.zip'
        archive.write_bytes(self.zip)
        carrier.extract(archive, self.root / 'ok', self.env['SOURCE_SHA256'])
        with self.assertRaises(ValueError):
            carrier.extract(archive, self.root / 'bad', '0' * 64)
        for name in ['../escape', '/escape', 'android/build.gradle', 'package-lock.json', 'App.tsx']:
            with self.subTest(name=name):
                data = self.archive(dict(self.files, **{name: b'bad'}))
                archive.write_bytes(data)
                with self.assertRaises(ValueError):
                    carrier.extract(archive, self.root / 'bad', hashlib.sha256(data).hexdigest())

    def test_optional_appearance_assets(self):
        archive = self.root / 'input.zip'
        for assets in ({}, {'assets/icon.png': b'icon'}, {'assets/splash.png': b'splash'},
                       {'assets/icon.png': b'icon', 'assets/splash.png': b'splash'}):
            data = self.archive(dict(self.files, **assets))
            archive.write_bytes(data)
            carrier.extract(archive, self.root / 'appearance', hashlib.sha256(data).hexdigest())
        files = dict(self.files)
        del files['assets/default-splash.png']
        data = self.archive(files)
        archive.write_bytes(data)
        with self.assertRaises(ValueError):
            carrier.extract(archive, self.root / 'missing', hashlib.sha256(data).hexdigest())

    def test_symlink_and_duplicate(self):
        for duplicate in [False, True]:
            out = io.BytesIO()
            with zipfile.ZipFile(out, 'w') as archive:
                for name, content in self.files.items():
                    info = zipfile.ZipInfo(name)
                    info.external_attr = (0o120777 if name == 'App.tsx' and not duplicate else 0o100644) << 16
                    archive.writestr(info, content)
                if duplicate:
                    archive.writestr('App.tsx', b'duplicate')
            path = self.root / 'bad.zip'
            path.write_bytes(out.getvalue())
            with self.assertRaises(ValueError):
                carrier.extract(path, self.root / 'bad', hashlib.sha256(out.getvalue()).hexdigest())

    def test_pipeline_and_failures_are_redacted(self):
        for target in ('apk', 'aab'):
            for failure in [None, 'npm', './node_modules/.bin/expo', './gradlew', 'apksigner', 'upload', 'download', 'checksum', 'extra-apk', 'empty-apk', 'missing', 'wrong-signer', 'unsigned', 'bad-bundle']:
                commands, uploads = [], []

                def run(args, cwd, env=None):
                    if args[0] == 'git':
                        return self.env['CARRIER_SHA'].encode()
                    commands.append(args)
                    self.assertNotIn('CODE_URL', env)
                    self.assertNotIn('ARTIFACT_UPLOAD_URL', env)
                    if args[0] not in ('./gradlew', 'jarsigner', 'keytool'):
                        self.assertNotIn('CM_KEY_PASSWORD', env)
                    if args[0] == failure or (failure == 'apksigner' and args[0].endswith('/apksigner')):
                        raise RuntimeError('URL_SECRET KEY_SECRET PUT_SECRET')
                    cwd = Path(cwd)
                    if args[0].endswith('/expo'):
                        path = cwd / 'android/app/build.gradle'
                        path.parent.mkdir(parents=True)
                        path.touch()
                    if args[0] == './gradlew':
                        self.assertIn('signingConfig signingConfigs.release', (cwd / 'app/build.gradle').read_text())
                        path = cwd / ('app/build/outputs/' + ('apk' if target == 'apk' else 'bundle') + '/release/app-release.' + target)
                        path.parent.mkdir(parents=True)
                        self.assertEqual(args[-1], 'assembleRelease' if target == 'apk' else 'bundleRelease')
                        if failure == 'missing':
                            return b''
                        if target == 'aab' and failure != 'empty-apk':
                            path.write_bytes(self.archive({'BundleConfig.pb': b'config', 'base/manifest/AndroidManifest.xml': b'manifest'} if failure != 'bad-bundle' else {}))
                        else:
                            path.write_bytes(b'' if failure == 'empty-apk' else b'simulated APK')
                        if failure == 'extra-apk':
                            path.with_name('other.' + target).write_bytes(b'extra')
                    if args[0] == 'keytool':
                        return b'certificate'
                    if args[0].endswith('/apksigner'):
                        if failure == 'unsigned':
                            raise RuntimeError('KEY_SECRET')
                        return ('Signer #1 certificate SHA-256 digest: ' + hashlib.sha256(b'wrong' if failure == 'wrong-signer' else b'certificate').hexdigest()).encode()
                    if args[0] == 'jarsigner':
                        self.assertIn('-strict', args)
                        self.assertEqual(args[-1], 'atoms-mobile-demo')
                        if failure in ('wrong-signer', 'apksigner'):
                            raise RuntimeError('KEY_SECRET')
                        return b'jar is unsigned.' if failure == 'unsigned' else b'jar verified.'
                    return b''

                def transfer(url, destination=None, artifact=None):
                    if destination:
                        if failure == 'download':
                            raise RuntimeError('URL_SECRET')
                        destination.write_bytes(b'corrupt' if failure == 'checksum' else self.zip)
                    else:
                        if failure == 'upload':
                            raise RuntimeError('PUT_SECRET')
                        uploads.append(artifact.read_bytes())

                output = io.StringIO()
                with patch.object(carrier, 'run', side_effect=run), patch.object(carrier, 'transfer', side_effect=transfer), contextlib.redirect_stdout(output):
                    result = carrier.build(dict(self.env, BUILD_TARGET=target))
                self.assertEqual(result, int(failure is not None and not (failure == 'bad-bundle' and target == 'apk')))
                self.assertEqual(len(uploads), int(failure is None or (failure == 'bad-bundle' and target == 'apk')))
                for secret in ['URL_SECRET', 'KEY_SECRET', 'PUT_SECRET']:
                    self.assertNotIn(secret, output.getvalue())
                if failure not in ('download', 'checksum'):
                    self.assertEqual(commands[0], ['npm', 'ci', '--no-audit', '--no-fund'])
                else:
                    self.assertEqual(commands, [])
    def test_put_contract_and_failure(self):
        artifact = self.root / 'app.apk'
        artifact.write_bytes(b'apk')
        response = unittest.mock.MagicMock()
        response.__enter__.return_value.status = 200
        opener = unittest.mock.Mock()
        opener.open.return_value = response
        with patch.object(carrier.urllib.request, 'build_opener', return_value=opener):
            carrier.transfer(self.env['ARTIFACT_UPLOAD_URL'], artifact=artifact)
            request = opener.open.call_args.args[0]
            self.assertEqual(request.method, 'PUT')
            self.assertEqual(request.get_header('Content-type'), 'application/octet-stream')
            self.assertEqual(request.data, b'apk')
            response.__enter__.return_value.status = 403
            with self.assertRaises(ValueError):
                carrier.transfer(self.env['ARTIFACT_UPLOAD_URL'], artifact=artifact)
        with self.assertRaises(ValueError):
            carrier.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://other')

    def test_workflow(self):
        import yaml
        workflows = yaml.safe_load((carrier.ROOT / 'codemagic.yaml').read_text())['workflows']
        fixed = workflows['website-apk']
        self.assertEqual(fixed['environment']['android_signing'], ['atoms_mobile_demo'])
        self.assertIn('python3 scripts/build_fixed_apk.py', fixed['scripts'][0]['script'])
        self.assertNotIn('publishing', fixed)
        self.assertIn('android-build', workflows)


if __name__ == '__main__':
    unittest.main()
