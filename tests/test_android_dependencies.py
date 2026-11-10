import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest


class AndroidDependenciesTests(unittest.TestCase):
    def test_install_uses_project_lock_and_does_not_fallback_after_failure(self):
        workflow = (Path(__file__).resolve().parents[1] / 'codemagic.yaml').read_text()
        block = workflow.split('      - name: Install dependencies\n        script: |\n', 1)[1]
        script = textwrap.dedent(block.split('\n      - name:', 1)[0])
        for locked, status, expected in [(True, 0, 'corepack pnpm install --frozen-lockfile'),
                                         (True, 1, 'corepack pnpm install --frozen-lockfile'),
                                         (False, 0, 'npm install')]:
            with self.subTest(locked=locked, status=status), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                if locked:
                    (root / 'pnpm-lock.yaml').touch()
                for command in ['corepack', 'npm']:
                    executable = root / command
                    executable.write_text(f'#!/bin/sh\necho "{command} $*" >> "$CM_BUILD_DIR/calls"\nexit {status}\n')
                    executable.chmod(0o755)
                result = subprocess.run(['bash', '-c', script], env={**os.environ,
                    'CM_BUILD_DIR': directory, 'PATH': f'{directory}:{os.environ["PATH"]}'})
                self.assertEqual(result.returncode, status)
                self.assertEqual((root / 'calls').read_text().strip(), expected)


if __name__ == '__main__':
    unittest.main()
