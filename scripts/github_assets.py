#!/usr/bin/env python3
"""Generic GitHub release client and CLI. GH_TOKEN takes precedence over GITHUB_TOKEN."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile


class ReleaseClient:
    def __init__(self, repo):
        if not re.fullmatch(r'[\w.-]+/[\w.-]+', repo):
            raise ValueError('Expected owner/repo')
        self.repo = repo
        self.env = dict(os.environ)
        self.token = self.env.get('GH_TOKEN') or self.env.get('GITHUB_TOKEN', '')
        if self.token:
            self.env['GH_TOKEN'] = self.token
        self.backend = 'gh' if shutil.which('gh') else 'curl'
        print(f'Release backend: {self.backend}', file=sys.stderr)

    def gh(self, *args):
        result = subprocess.run(['gh', 'release', *args, '-R', self.repo],
                                capture_output=True, text=True, env=self.env)
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or f'gh exited {result.returncode}')
        return result.stdout

    def curl(self, url, output=None):
        if not shutil.which('curl'):
            raise RuntimeError('curl is required for the fallback backend')
        header = ''
        if self.token:
            if '\n' in self.token or '\r' in self.token:
                raise ValueError('Invalid token: newline')
            escaped = self.token.replace('\\', '\\\\').replace('"', '\\"')
            header = f'header = "Authorization: Bearer {escaped}"\n'
        args = ['curl', '--fail', '--location', '--silent', '--show-error', '--max-time', '120',
                '--config', '-', '--url', url]
        if output is not None:
            args += ['--output', str(output)]
        result = subprocess.run(args, input=header, capture_output=True, text=True, env=self.env)
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or f'curl exited {result.returncode}')
        return result.stdout

    def release(self, tag='latest'):
        if self.backend == 'gh':
            try:
                args = ['view'] + ([] if tag == 'latest' else [tag])
                raw = self.gh(*args, '--json', 'tagName,name,publishedAt,assets')
            except RuntimeError as exc:
                print(f'gh metadata failed; falling back to curl: {exc}', file=sys.stderr)
                self.backend = 'curl'
            else:
                data = json.loads(raw)  # Parse errors must remain errors.
                if not isinstance(data, dict) or not isinstance(data.get('tagName'), str) or not isinstance(data.get('assets'), list):
                    raise ValueError('Malformed gh release metadata: expected tagName and assets')
                if any(not isinstance(a, dict) or not isinstance(a.get('name'), str) for a in data['assets']):
                    raise ValueError('Malformed gh asset metadata')
                data = {'tag_name': data['tagName'], 'name': data.get('name'),
                        'published_at': data.get('publishedAt'),
                        'assets': [{'name': a['name'], 'browser_download_url': a.get('url') or a.get('browserDownloadUrl'),
                                    'size': a.get('size')} for a in data['assets']]}
                return self.validate(data)
        suffix = 'latest' if tag == 'latest' else 'tags/' + tag
        return self.validate(json.loads(self.curl(f'https://api.github.com/repos/{self.repo}/releases/{suffix}')))

    @staticmethod
    def validate(data):
        if not isinstance(data, dict) or not isinstance(data.get('tag_name'), str) or not isinstance(data.get('assets'), list):
            raise ValueError('Malformed release metadata: expected tag_name and assets')
        for asset in data['assets']:
            if not isinstance(asset, dict) or not isinstance(asset.get('name'), str) or not isinstance(asset.get('browser_download_url'), str):
                raise ValueError('Malformed asset metadata')
            if Path(asset['name']).name != asset['name'] or asset['name'] in {'.', '..'}:
                raise ValueError('Unsafe asset filename')
        return data

    def releases(self, limit):
        if self.backend == 'gh':
            try:
                raw = self.gh('list', '--limit', str(limit), '--json', 'tagName,name,isLatest,isPrerelease,isDraft,publishedAt')
            except RuntimeError as exc:
                print(f'gh release list failed; falling back to curl: {exc}', file=sys.stderr)
                self.backend = 'curl'
            else:
                data = json.loads(raw)
                if not isinstance(data, list):
                    raise ValueError('Expected release array')
                return [[d['tagName'], d.get('publishedAt'), 'latest' if d.get('isLatest') else '',
                         'prerelease' if d.get('isPrerelease') else '', 'draft' if d.get('isDraft') else '', d.get('name')] for d in data]
        data = json.loads(self.curl(f'https://api.github.com/repos/{self.repo}/releases?per_page={min(limit, 100)}'))
        if not isinstance(data, list):
            raise ValueError('Expected release array: ' + str(data))
        return [[d['tag_name'], d.get('published_at'), '', 'prerelease' if d.get('prerelease') else '',
                 'draft' if d.get('draft') else '', d.get('name')] for d in data]

    def download(self, tag, asset, destination):
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=destination.parent) as work:
            pending = Path(work) / asset['name']
            if self.backend == 'gh':
                self.gh('download', tag, '--pattern', asset['name'], '--dir', work)
            else:
                self.curl(asset['browser_download_url'], pending)
            if not pending.is_file():
                raise RuntimeError('Download did not produce ' + asset['name'])
            os.replace(pending, destination)


def extract(path, destination):
    # Extract into staging, reject traversal, links and special files, then publish.
    with tempfile.TemporaryDirectory(dir=destination) as directory:
        stage = Path(directory)
        if tarfile.is_tarfile(path):
            with tarfile.open(path) as archive:
                for member in archive.getmembers():
                    if Path(member.name).is_absolute() or '..' in Path(member.name).parts or not (member.isfile() or member.isdir()):
                        raise ValueError('Unsafe archive member')
                archive.extractall(stage, filter='data')
        elif zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as archive:
                for member in archive.infolist():
                    if Path(member.filename).is_absolute() or '..' in Path(member.filename).parts or (member.external_attr >> 16) & 0o170000 == 0o120000:
                        raise ValueError('Unsafe archive member')
                archive.extractall(stage)
        else:
            raise ValueError('Unsupported archive')
        shutil.copytree(stage, destination, dirs_exist_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('repo')
    parser.add_argument('-t', '--tag', default='latest')
    parser.add_argument('-f', '--filter', action='append', default=[])
    parser.add_argument('-d', '--dest', type=Path, default=Path('.'))
    parser.add_argument('-x', '--extract', action='store_true')
    parser.add_argument('-a', '--all', action='store_true')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-q', '--query', action='store_true')
    group.add_argument('--query-json', action='store_true')
    group.add_argument('--releases', action='store_true')
    parser.add_argument('--limit', type=int, default=30)
    args = parser.parse_args()
    if args.limit < 1 or (args.extract and (args.query or args.query_json or args.releases)):
        parser.error('Positive --limit required; extraction cannot be combined with queries')
    patterns = [re.compile(pattern) for pattern in args.filter]
    client = ReleaseClient(args.repo)
    if args.releases:
        for row in client.releases(args.limit):
            print('\t'.join(str(v or '') for v in row))
        return
    release = client.release(args.tag)
    matches = [a for a in release['assets'] if all(p.search(a['name']) for p in patterns)]
    if not matches:
        raise RuntimeError('No matching assets for ' + release['tag_name'])
    for asset in matches if (args.all or args.query or args.query_json) else matches[:1]:
        if args.query_json:
            print(json.dumps({'tag': release['tag_name'], 'release_name': release.get('name'),
                              'published_at': release.get('published_at'), 'asset_name': asset['name'],
                              'asset_url': asset['browser_download_url'], 'asset_size': asset.get('size')}))
        elif args.query:
            print(release['tag_name'], asset['name'], asset['browser_download_url'], sep='\t')
        else:
            path = args.dest / asset['name']
            client.download(release['tag_name'], asset, path)
            if args.extract:
                extract(path, args.dest)
            print(path)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, KeyError, re.error, tarfile.TarError, zipfile.BadZipFile) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        sys.exit(1)
