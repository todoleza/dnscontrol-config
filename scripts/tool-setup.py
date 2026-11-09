#!/usr/bin/env python3
"""Explicit local tool/environment preparation; never called implicitly."""
import argparse
import hashlib
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile

from github_assets import ReleaseClient

ROOT = Path(__file__).resolve().parent.parent


def install_tool(update=False, tag='latest', root=ROOT, client=None):
    target = root / '.tools/dnscontrol'
    if target.exists() and not update:
        print('Local DNSControl already present; preserved. Use make update-tool to change it.')
        return
    system = {'Linux': 'linux', 'Darwin': 'darwin'}.get(platform.system())
    arch = {'x86_64': 'amd64', 'AMD64': 'amd64', 'aarch64': 'arm64', 'arm64': 'arm64'}.get(platform.machine())
    if not system or not arch:
        raise RuntimeError(f'Unsupported platform: {platform.system()}/{platform.machine()}')
    client = client or ReleaseClient('DNSControl/dnscontrol')
    release = client.release(tag)
    resolved = release['tag_name']
    suffix = f'_{system}_{arch}.tar.gz'
    archives = [a for a in release['assets'] if a['name'].endswith(suffix)]
    sums = [a for a in release['assets'] if a['name'] == 'checksums.txt']
    if len(archives) != 1 or len(sums) != 1:
        raise RuntimeError('Expected exactly one platform archive and checksums.txt')
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent, prefix='setup-') as work:
        work = Path(work)
        archive, checksums = work / archives[0]['name'], work / 'checksums.txt'
        client.download(resolved, archives[0], archive)
        client.download(resolved, sums[0], checksums)
        expected = [line.split()[0] for line in checksums.read_text().splitlines()
                    if len(line.split()) == 2 and line.split()[1].lstrip('*') == archive.name]
        if len(expected) != 1 or hashlib.sha256(archive.read_bytes()).hexdigest() != expected[0]:
            raise RuntimeError('Archive checksum mismatch or missing checksum; previous binary retained')
        pending = work / 'dnscontrol'
        with tarfile.open(archive) as package:
            members = [m for m in package.getmembers() if Path(m.name).name == 'dnscontrol' and m.isfile()]
            if len(members) != 1:
                raise RuntimeError('Expected exactly one executable in archive')
            with package.extractfile(members[0]) as source, pending.open('wb') as output:
                shutil.copyfileobj(source, output)
        pending.chmod(0o755)
        version = subprocess.check_output([str(pending), 'version'], text=True).strip()
        if version.lstrip('v') != resolved.lstrip('v'):
            raise RuntimeError(f'Executable version {version} differs from release {resolved}')
        os.replace(pending, target)
    print(f'Installed {resolved} into {target}')


def setup_venv(root=ROOT):
    directory = root / '.venv'
    if not directory.exists():
        subprocess.run([sys.executable, '-m', 'venv', str(directory)], check=True)
    python = directory / 'bin/python'
    if not python.is_file():
        raise RuntimeError('Existing .venv is incomplete; move it aside and run make setup-venv')
    subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(root / 'requirements-dev.txt')], check=True)


def doctor():
    print('Python:', sys.version.split()[0])
    for name in ['make', 'gh', 'curl']:
        print(f'{name}: {shutil.which(name) or "not found"}')
    binary = ROOT / '.tools/dnscontrol'
    if binary.is_file():
        print('Local DNSControl:', subprocess.check_output([str(binary), 'version'], text=True).strip())
    else:
        print('Local DNSControl missing: run make setup-tool')
    path_binary = shutil.which('dnscontrol')
    if path_binary:
        print('PATH DNSControl:', path_binary, subprocess.check_output([path_binary, 'version'], text=True).strip())
    else:
        print('PATH DNSControl: not found (local binary or DNSCONTROL override can be used)')
    python = ROOT / '.venv/bin/python'
    if not python.is_file():
        print('Validation environment missing: run make setup-venv')
    elif subprocess.run([str(python), '-c', 'import dns.zone'], capture_output=True).returncode:
        print('Validation dependencies missing: run make setup-venv')
    else:
        print('Validation environment:', subprocess.check_output(
            [str(python), '-c', 'import importlib.metadata; print("dnspython " + importlib.metadata.version("dnspython"))'],
            text=True).strip())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['setup-tool', 'update-tool', 'setup-venv', 'update-venv', 'doctor'])
    parser.add_argument('--tag', default=os.environ.get('DNSCONTROL_TAG') or 'latest')
    args = parser.parse_args()
    if args.action.endswith('tool'):
        install_tool(args.action == 'update-tool', args.tag)
    elif args.action.endswith('venv'):
        setup_venv()
    else:
        doctor()


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError, tarfile.TarError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        sys.exit(1)
