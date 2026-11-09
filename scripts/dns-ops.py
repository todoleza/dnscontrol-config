#!/usr/bin/env python3
"""Optional repo checks and local BIND export; DNSControl itself remains the CLI."""
import argparse
import difflib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / 'tests/baseline'


def run_dns(binary, *args):
    result = subprocess.run([binary, *args], cwd=ROOT, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError((result.stdout + result.stderr).strip())
    return result.stdout


def read_ir(binary, config='dnsconfig.js'):
    return portable_ir(json.loads(run_dns(binary, 'print-ir', '--config', config)))


def portable_ir(value):
    """Normalize v4/v5 serialization, retaining records and operational settings.

    The original v4 reference stays untouched. BIND wire-data comparisons remain
    independent of this adapter, including TXT chunks and DNSSEC record content.
    """
    if isinstance(value, list):
        return [portable_ir(item) for item in value]
    if not isinstance(value, dict):
        return value
    if 'type' in value and 'rdata' in value:
        record = {k: v for k, v in value.items()
                  if k not in {'rdata', 'typenum', 'comparablev3', 'name_unicode'}}
        fields = value['rdata']
        kind = value['type']
        layouts = {
            'A': {'Addr': 'target'}, 'AAAA': {'Addr': 'target'},
            'CNAME': {'Target': 'target'}, 'NS': {'Ns': 'target'},
            'MX': {'Preference': 'mxpreference', 'Mx': 'target'},
            'CAA': {'Flag': 'caaflag', 'Tag': 'caatag', 'Value': 'target'},
            'SRV': {'Priority': 'srvpriority', 'Weight': 'srvweight', 'Port': 'srvport', 'Target': 'target'},
            'DS': {'KeyTag': 'dskeytag', 'Algorithm': 'dsalgorithm', 'DigestType': 'dsdigesttype', 'Digest': 'dsdigest'},
            'TLSA': {'Usage': 'tlsausage', 'Selector': 'tlsaselector', 'MatchingType': 'tlsamatchingtype', 'Certificate': 'target'},
            'SSHFP': {'Algorithm': 'sshfpalgorithm', 'Type': 'sshfpfingerprint', 'FingerPrint': 'target'},
        }
        if kind == 'TXT':
            if set(fields) != {'Txt'}:
                raise RuntimeError(f'Unexpected TXT schema: {sorted(fields)}')
            record['target'] = ''.join(fields['Txt'])
        else:
            layout = layouts.get(kind)
            if layout is None or set(fields) - set(layout):
                raise RuntimeError(f'Unsupported v5 IR schema for {kind}: {sorted(fields)}')
            for source, target in layout.items():
                field = fields.get(source)
                if field is not None and field != 0:
                    record[target] = field
            if kind == 'DS':
                record['target'] = ''
        value = record
    is_record = 'type' in value and 'ttl' in value and 'name' in value
    result = {}
    for key, item in value.items():
        if key in {'dnscontrol_nameraw', 'dnscontrol_nameunicode', 'dnscontrol_uniquename'}:
            continue  # Derived labels removed from domain metadata in v5.
        if is_record and key in {'fields', 'comparable', 'zonfefilepartial', 'name_raw', 'name_unicode'}:
            continue  # v4 derived representations; legacy scalar fields remain.
        if is_record and (key == 'dsdigest' or (key == 'target' and value['type'] in {'TLSA', 'SSHFP'})):
            item = item.lower()
        result[key] = [] if key == 'records' and item is None else portable_ir(item)
    return result


def canonical(value):
    """Ignore source locations and ordering, preserving every other IR field."""
    if isinstance(value, dict):
        value = portable_ir(value)
        return {k: canonical(v) for k, v in sorted(value.items()) if k != 'filepos'}
    if isinstance(value, list):
        return sorted((canonical(v) for v in value), key=lambda v: json.dumps(v, sort_keys=True))
    return value


def compare_ir(reference, current):
    old = json.dumps(canonical(reference), indent=2, sort_keys=True).splitlines()
    new = json.dumps(canonical(current), indent=2, sort_keys=True).splitlines()
    if old != new:
        diff = '\n'.join(difflib.unified_diff(old, new, fromfile='baseline IR', tofile='current IR'))
        raise RuntimeError('Configuration differs from the reviewed baseline:\n' + diff)


def read_zone(path):
    try:
        import dns.zone
        import dns.rdatatype
    except ImportError as exc:
        raise RuntimeError('Validation dependencies missing: run make setup-venv or set PYTHON') from exc
    zone = dns.zone.from_file(str(path), origin=path.stem, relativize=False,
                             check_origin=False, allow_include=False)
    records = set()
    for owner, node in zone.nodes.items():
        for rrset in node.rdatasets:
            for record in rrset:
                if rrset.rdtype == dns.rdatatype.SOA:
                    record = record.replace(serial=0)
                records.add((owner.canonicalize().to_text(), rrset.rdtype, rrset.ttl,
                             record.to_digestable(origin=zone.origin).hex()))
    return records


def compare_zones(reference, current):
    expected = {p.name: p for p in reference.glob('*.zone')}
    actual = {p.name: p for p in current.glob('*.zone')}
    if expected.keys() != actual.keys():
        raise RuntimeError(f'Zone inventory differs: missing={sorted(expected.keys()-actual.keys())}; '
                           f'extra={sorted(actual.keys()-expected.keys())}')
    for name in sorted(expected):
        old, new = read_zone(expected[name]), read_zone(actual[name])
        if old != new:
            raise RuntimeError(f'{name}: records differ; removed={sorted(old-new)}; added={sorted(new-old)}')


def export_bind(binary, directory):
    """Project into BIND only: no live credentials or remote providers are loaded.

    Provider NS assignments are an explicit local snapshot. Direct DNSControl
    preview/push continues to obtain nameservers from the actual providers.
    """
    with tempfile.TemporaryDirectory(prefix='dnscontrol-bind-') as work:
        work = Path(work)
        (work / 'creds.json').write_text(json.dumps({
            'none': {'TYPE': 'NONE'},
            'bind': {'TYPE': 'BIND', 'directory': str(directory)},
        }))
        run_dns(binary, 'push', '--config', 'scripts/export-bind.js', '--providers', 'bind',
                '--no-populate', '--creds', str(work / 'creds.json'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['check', 'check-baseline', 'refresh-baseline', 'export', 'candidate'])
    parser.add_argument('--dnscontrol', default=os.environ.get('DNSCONTROL', str(ROOT / '.tools/dnscontrol') if (ROOT / '.tools/dnscontrol').exists() else 'dnscontrol'))
    args = parser.parse_args()
    binary = shutil.which(args.dnscontrol)
    if not binary:
        raise RuntimeError(f'DNSControl not found: {args.dnscontrol}; run make setup-tool or set DNSCONTROL')
    binary = str(Path(binary).resolve())
    version = run_dns(binary, 'version').strip()
    if version.lstrip('v') != '5.8.0':
        print(f'Note: validated DNSControl release is v5.8.0; running {version}', file=sys.stderr)
    run_dns(binary, 'check')
    ir = read_ir(binary)
    if args.command == 'check-baseline':
        compare_ir(json.loads((BASELINE / 'config-ir.json').read_text()), ir)
    with tempfile.TemporaryDirectory(prefix='dnscontrol-zones-') as directory:
        directory = Path(directory)
        export_bind(binary, directory)
        if args.command == 'candidate':
            destination = ROOT / 'build/candidate-bind_zones'
            destination.mkdir(parents=True, exist_ok=True)
            expected = {p.name for p in directory.glob('*.zone')}
            stale = {p.name for p in destination.glob('*.zone')} - expected
            if stale:
                raise RuntimeError(f'Stale candidate files present: {sorted(stale)}; move the previous candidate directory aside')
            for path in directory.glob('*.zone'):
                shutil.copyfile(path, destination / path.name)
            print(f'Candidate exports written to {destination}; reviewed baseline and current exports unchanged.')
            return
        # Parse the entire generated set before publishing any output.
        for path in directory.glob('*.zone'):
            read_zone(path)
        updated = 0
        unchanged = 0
        if args.command == 'refresh-baseline':
            # Require reviewed local exports to match before accepting either reference.
            compare_zones(directory, ROOT / 'bind_zones')
            BASELINE.mkdir(parents=True, exist_ok=True)
            zones = BASELINE / 'bind_zones'
            zones.mkdir(exist_ok=True)
            expected = {path.name for path in directory.glob('*.zone')}
            # Stage the complete validated payload before replacing reference files.
            with tempfile.TemporaryDirectory(dir=BASELINE, prefix='.refresh-') as staging:
                staging = Path(staging)
                (staging / 'config-ir.json').write_text(json.dumps(ir, indent=2, sort_keys=True) + '\n')
                for path in directory.glob('*.zone'):
                    shutil.copyfile(path, staging / path.name)
                for name in sorted(expected):
                    os.replace(staging / name, zones / name)
                os.replace(staging / 'config-ir.json', BASELINE / 'config-ir.json')
            for path in zones.glob('*.zone'):
                if path.name not in expected:
                    path.unlink()
        elif args.command in ('check', 'check-baseline'):
            compare_zones(directory, ROOT / 'bind_zones')
            if args.command == 'check-baseline':
                compare_zones(BASELINE / 'bind_zones', directory)
            subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'],
                           cwd=ROOT, env={**os.environ, 'DNSCONTROL': binary}, check=True)
        else:
            # Validate the complete candidate set before replacing any output.
            for path in sorted(directory.glob('*.zone')):
                destination = ROOT / 'bind_zones' / path.name
                if destination.exists() and read_zone(destination) == read_zone(path):
                    unchanged += 1
                    continue  # Avoid comment/serial-only churn on repeated export.
                pending = destination.with_suffix('.zone.tmp')
                shutil.copyfile(path, pending)
                os.replace(pending, destination)
                updated += 1
    if args.command == "export":
        print(f"export: {updated + unchanged} zones generated; {updated} updated, {unchanged} unchanged.")
    elif args.command == "refresh-baseline":
        print("refresh-baseline: accepted current IR and zone exports; review and commit tests/baseline.")
    elif args.command == "check":
        print("check: current configuration, local exports and tests pass.")
    else:
        print(f'check-baseline: {len(ir["domains"])} zones match the historical records and ownership settings.')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        sys.exit(1)
