import json
import os
from pathlib import Path
import subprocess
import shutil
import tempfile
import unittest

import yaml

WORKFLOW = yaml.safe_load((Path(__file__).resolve().parents[1] / 'codemagic.yaml').read_text())['workflows']['android-build']


class MobileBuildTests(unittest.TestCase):
    def test_pnpm_lock_is_frozen_and_npm_projects_still_work(self):
        script = next(s['script'] for s in WORKFLOW['scripts'] if s['name'] == 'Install dependencies')
        for lock, expected in [('pnpm-lock.yaml', 'corepack pnpm install --frozen-lockfile'),
                               ('package-lock.json', 'npm ci'), (None, 'npm install')]:
            with self.subTest(lock=lock), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                if lock:
                    (root / lock).touch()
                for command in ('corepack', 'npm'):
                    f = root / command
                    f.write_text('#!/bin/sh\nprintf "%s %s\\n" "$(basename "$0")" "$*"\n')
                    f.chmod(0o755)
                output = subprocess.check_output(['bash', '-eu', '-c', script], env={**os.environ,
                    'CM_BUILD_DIR': tmp, 'PATH': tmp + os.pathsep + os.environ['PATH']}, text=True)
                self.assertEqual(output.strip(), expected)

    def test_project_identity_and_native_configuration_are_preserved(self):
        script = next(s['script'] for s in WORKFLOW['scripts'] if s['name'] == 'Prepare Expo config')
        packages = []
        for chat_id in ('a' * 32, 'b' * 32):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                config = {'expo': {'slug': 'new-project', 'scheme': 'atoms-mobile', 'plugins': ['expo-secure-store']}}
                (root / 'app.json').write_text(json.dumps(config))
                # Model Expo CLI's resolved config while exercising the real carrier script.
                executable = root / 'node_modules/.bin/expo'
                executable.parent.mkdir(parents=True)
                executable.write_text("#!/usr/bin/env node\nconsole.log(JSON.stringify(require(process.cwd() + '/app.json').expo));\n")
                executable.chmod(0o755)
                (root / 'scripts').mkdir()
                shutil.copyfile(Path(__file__).resolve().parents[1] / 'scripts/apply_mobile_icon.cjs',
                                root / 'scripts/apply_mobile_icon.cjs')
                shutil.copyfile(Path(__file__).resolve().parents[1] / 'scripts/validate_mobile_config.cjs',
                                root / 'scripts/validate_mobile_config.cjs')
                backend = b'{"environment":"PROD","baseUrl":"https://app.example.com"}'
                (root / 'mobile-backend.json').write_bytes(backend)
                env = {**os.environ, 'CM_BUILD_DIR': tmp, 'CHAT_ID': chat_id}
                subprocess.run(['bash', '-eu', '-c', script], env=env, check=True, capture_output=True)
                actual = json.loads((root / 'app.json').read_text())['expo']
                packages.append(actual['android']['package'])
                self.assertEqual(actual['scheme'], 'atoms-mobile')
                self.assertEqual(actual['plugins'], ['expo-secure-store'])
                self.assertEqual((root / 'mobile-backend.json').read_bytes(), backend)
                actual['android']['package'] = 'ai.fuzhi.existing'
                (root / 'app.json').write_text(json.dumps({'expo': actual}))
                subprocess.run(['bash', '-eu', '-c', script], env=env, check=True, capture_output=True)
                self.assertEqual(json.loads((root / 'app.json').read_text())['expo']['android']['package'], 'ai.fuzhi.existing')
        self.assertNotEqual(*packages)
