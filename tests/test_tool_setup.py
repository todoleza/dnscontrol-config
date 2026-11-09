import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import hashlib

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from github_assets import ReleaseClient
spec = importlib.util.spec_from_file_location('setup_tool', ROOT / 'scripts/tool-setup.py')
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


class InstallerTests(unittest.TestCase):
    def test_install_failure_preserves_previous_and_setup_does_not_query(self):
        for failure in ['checksum', 'version', 'missing', 'ambiguous', 'download']:
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / '.tools').mkdir()
                binary = root / '.tools/dnscontrol'
                binary.write_bytes(b'previous executable')
                content = b'#!/bin/sh\necho v1.0.0\n'
                data = io.BytesIO()
                with tarfile.open(fileobj=data, mode='w:gz') as package:
                    member = tarfile.TarInfo('dnscontrol')
                    member.size = len(content)
                    package.addfile(member, io.BytesIO(content))
                archive = data.getvalue()
                name = 'dnscontrol_1.0.0_linux_amd64.tar.gz'
                class Client:
                    calls = 0
                    def release(self, tag):
                        self.calls += 1
                        assets = [{'name': name}, {'name': 'checksums.txt'}]
                        if failure == 'missing': assets = []
                        if failure == 'ambiguous': assets.append({'name': 'second_linux_amd64.tar.gz'})
                        return {'tag_name': 'v2.0.0' if failure == 'version' else 'v1.0.0', 'assets': assets}
                    def download(self, tag, asset, path):
                        if failure == 'download': raise RuntimeError('download failed')
                        if asset['name'] == name: path.write_bytes(archive)
                        else: path.write_text(('bad' if failure == 'checksum' else hashlib.sha256(archive).hexdigest()) + '  ' + name + '\n')
                client = Client()
                setup.install_tool(root=root, client=client)
                self.assertEqual(client.calls, 0)
                with patch.object(setup.platform, 'system', return_value='Linux'), patch.object(setup.platform, 'machine', return_value='x86_64'):
                    with self.assertRaises(RuntimeError): setup.install_tool(update=True, root=root, client=client)
                self.assertEqual(binary.read_bytes(), b'previous executable')
                if failure == 'download':
                    # The same fixture provides a successful verified installation.
                    failure = 'success'
                    setup.install_tool(update=True, root=root, client=client)
                    self.assertEqual(subprocess.check_output([str(binary), 'version'], text=True).strip(), 'v1.0.0')

    def test_backends_and_release_array_errors(self):
        with patch.dict(os.environ, {'GH_TOKEN': 'preferred', 'GITHUB_TOKEN': 'other'}), patch('github_assets.shutil.which', return_value='/bin/fixture'):
            client = ReleaseClient('owner/repo')
            self.assertEqual(client.env['GH_TOKEN'], 'preferred')
        with patch.object(client, 'gh', side_effect=RuntimeError('authentication failed')), patch.object(client, 'curl', return_value='[{"tag_name":"v1"}]'):
            self.assertEqual(client.releases(1)[0][0], 'v1')
            self.assertEqual(client.backend, 'curl')
        with patch.object(client, 'curl', return_value='{"message":"Bad credentials"}'):
            with self.assertRaises(ValueError): client.releases(1)
        with patch.object(client, 'curl', return_value='not json'):
            with self.assertRaises(ValueError): client.release()
        with patch.object(client, 'curl', side_effect=RuntimeError('HTTP 401')):
            with self.assertRaisesRegex(RuntimeError, '401'): client.release()
        client.backend = 'gh'
        with tempfile.TemporaryDirectory() as directory:
            def fake_gh(*args):
                self.assertIn('download', args)
                Path(args[args.index('--dir') + 1], 'fixture').write_text('ok')
            with patch.object(client, 'gh', side_effect=fake_gh):
                output = Path(directory) / 'fixture'
                client.download('v1', {'name': 'fixture'}, output)
                self.assertEqual(output.read_text(), 'ok')


class RunnerTests(unittest.TestCase):
    def test_forwarding_environment_exit_and_no_shell_expansion(self):
        with tempfile.TemporaryDirectory() as directory:
            stub = Path(directory) / 'dnscontrol'
            stub.write_text('#!' + sys.executable + '\nimport os,sys,json\nprint(json.dumps([sys.argv[1:],os.environ["FIXTURE_ENV"]]))\nsys.exit(7)\n')
            stub.chmod(0o755)
            raw = 'check --value "two words" \'$HOME\' \'$(touch forbidden)\''
            result = subprocess.run(['make', '--no-print-directory', 'dnscontrol', 'DNSCONTROL=' + str(stub), 'ARGS=' + raw], cwd=ROOT,
                                    env={**os.environ, 'FIXTURE_ENV': 'inherited'}, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)  # Make reports recipe status separately.
            args, value = json.loads(result.stdout.splitlines()[-1])
            self.assertEqual(args, ['check', '--value', 'two words', '$HOME', '$(touch forbidden)'])
            self.assertEqual(value, 'inherited')
            direct = subprocess.run([sys.executable, 'scripts/run-dnscontrol.py'], cwd=ROOT,
                                    env={**os.environ, 'DNSCONTROL': str(stub), 'ARGS': '', 'FIXTURE_ENV': 'ok'}, capture_output=True, text=True)
            self.assertEqual(direct.returncode, 7)
            self.assertEqual(json.loads(direct.stdout)[0], ['--help'])

    def test_missing_binary_does_not_set_up_and_interrupt_is_native(self):
        result = subprocess.run([sys.executable, 'scripts/run-dnscontrol.py'], cwd=ROOT,
                                env={**os.environ, 'DNSCONTROL': '/missing/fixture'}, capture_output=True, text=True)
        self.assertEqual(result.returncode, 127)
        self.assertIn('make setup-tool', result.stderr)
        with tempfile.TemporaryDirectory() as directory:
            stub = Path(directory) / 'signal-stub'
            stub.write_text('#!' + sys.executable + '\nimport os,signal\nos.kill(os.getpid(),signal.SIGINT)\n')
            stub.chmod(0o755)
            result = subprocess.run([sys.executable, 'scripts/run-dnscontrol.py'], cwd=ROOT,
                                    env={**os.environ, 'DNSCONTROL': str(stub)}, capture_output=True)
            self.assertIn(result.returncode, [-signal.SIGINT, 130])


class ExplicitOnlyTests(unittest.TestCase):
    def test_missing_prerequisites_never_trigger_network_or_setup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copyfile(ROOT / 'Makefile', root / 'Makefile')
            shutil.copytree(ROOT / 'scripts', root / 'scripts')
            spies = root / 'spies'
            spies.mkdir()
            for name in ['gh', 'curl']:
                path = spies / name
                path.write_text('#!/bin/sh\necho invoked >> "' + str(root / 'network.log') + '"\nexit 99\n')
                path.chmod(0o755)
            env = {**os.environ, 'PATH': str(spies) + os.pathsep + os.environ['PATH']}
            for target in ['help', 'doctor', 'dnscontrol', 'check', 'export', 'preview']:
                result = subprocess.run(['make', target, 'DNSCONTROL=/missing/fixture',
                                         'PYTHON=/missing/python', 'PROVIDER=cloudns', 'ZONE=example.test'],
                                        cwd=root, env=env, capture_output=True, text=True)
                if target in ['help', 'doctor']:
                    self.assertEqual(result.returncode, 0, result.stderr)
                else:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn('setup-', result.stdout + result.stderr)
            self.assertFalse((root / 'network.log').exists())
            self.assertFalse((root / '.tools').exists())
            self.assertFalse((root / '.venv').exists())
