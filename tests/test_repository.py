import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

ROOT = Path(__file__).resolve().parent.parent
BINARY = str(Path(shutil.which(os.environ.get('DNSCONTROL', str(ROOT / '.tools/dnscontrol') if (ROOT / '.tools/dnscontrol').exists() else 'dnscontrol')) or 'dnscontrol').resolve())


def load_script(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ops = load_script('dns_ops', 'scripts/dns-ops.py')


class ConfigurationTests(unittest.TestCase):
    def test_lab_shared_endpoints_and_publication(self):
        zones = {z['name']: z for z in ops.read_ir(BINARY)['domains']}
        for domain in ['example.test', 'lab.example.test']:
            photos = [r for r in zones[domain]['records'] if r['name'] == 'photos']
            self.assertEqual({r['ttl'] for r in photos}, {600})
            self.assertEqual({r['target'] for r in photos}, {'192.0.2.10', '2001:db8:1::1'})
        records = zones['infrastructure.test']['records']
        self.assertEqual({r['type'] for r in records if r['name'] == 'worker'}, {'AAAA'})
        self.assertTrue(any(r['name'] == 'portal' and r['type'] == 'CNAME' for r in records))
        self.assertTrue(zones['dyn.example.test'].get('unmanaged'))
        self.assertTrue(any(r['name'] == 'lab' and r['type'] == 'NS' for r in zones['example.test']['records']))

    def test_allowlist_dns_matches_reviewed_source(self):
        sources = json.loads((ROOT / 'data/allowlist-sources.json').read_text())
        zone = next(z for z in ops.read_ir(BINARY)['domains'] if z['name'] == 'monitor.example.test')
        for family, kind in [('ipv4', 'A'), ('ipv6', 'AAAA')]:
            self.assertEqual({r['target'] for r in zone['records'] if r['name'] == 'nodes' and r['type'] == kind}, set(sources[family]))

    def test_helpers_keep_record_semantics_and_do_not_leak_globals(self):
        ir = ops.read_ir(BINARY, 'tests/fixtures/helpers.js')
        zones = {zone['name']: zone for zone in ir['domains']}
        first, second = zones['helpers.example']['records'], zones['second.example']['records']
        self.assertEqual({(r['type'], r['ttl']) for r in first if r['name'] == 'dual'},
                         {('A', 600), ('AAAA', 600)})
        self.assertEqual({(r['type'], r['ttl']) for r in first if r['name'] == 'v4'}, {('A', 60)})
        self.assertEqual({(r['type'], r['ttl']) for r in first if r['name'] == 'v6'}, {('AAAA', 120)})
        self.assertEqual([r['target'] for r in first if r['name'] == 'sl' and r['type'] == 'TXT'],
                         ['v=spf1 include:simplelogin.co ~all'])
        self.assertEqual([r['target'] for r in first if r['name'] == '@' and r['type'] == 'TXT'],
                         ['v=spf1 include:_spf.protonmail.ch mx ~all'])
        self.assertEqual(len([r for r in first if r['name'].endswith('._domainkey.sl')]), 3)
        self.assertEqual(len([r for r in second if r['name'] == '@' and r['type'] == 'MX']), 2)
        self.assertEqual([r['target'] for r in second if r['name'] == '_dmarc' and r['type'] == 'TXT'],
                         ['v=DMARC1; p=reject; sp=reject; adkim=s; aspf=s;'])
        self.assertEqual(len([r for r in first if r['type'] == 'DS']), 1)

    def test_explicit_template_ttls_arrays_and_generated_defaults(self):
        ir = ops.read_ir(BINARY, 'tests/fixtures/helpers.js')
        records = {zone['name']: zone['records'] for zone in ir['domains']}
        first, second = records['helpers.example'], records['second.example']
        self.assertEqual(len([r for r in first if r['name'] == 'many']), 3)
        self.assertEqual({r['ttl'] for r in first if r['name'] == 'many'}, {180})
        self.assertFalse(any(r['name'] == 'empty' for r in first))
        self.assertEqual(len([r for r in first if r['name'] == 'generated']), 2)
        for name, ttl in [('generated', 240), ('generated-v6', 90), ('generated-alias', 60)]:
            self.assertEqual({r['ttl'] for r in first if r['name'] == name}, {ttl})
        self.assertEqual({r['ttl'] for r in first if r['name'] == 'custom' or r['name'].endswith('.custom')}, {120})
        self.assertEqual({r['ttl'] for r in first if 'custom-disabled' in r['name']}, {180})
        self.assertEqual({r['ttl'] for r in second}, {3600})

    def test_glob_discovery_phase_order_and_nonrecursive_boundaries(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            shutil.copyfile(ROOT / 'dnsconfig.js', directory / 'dnsconfig.js')
            for name in ['lib', 'zones', 'services', 'data']:
                shutil.copytree(ROOT / name, directory / name)
            (directory / 'lib/zz-fixture.js').write_text(
                'function DISCOVERED_RECORDS() { return ADDRESS_RECORDS("auto", {ipv4:"192.0.2.100"}, 75); }')
            (directory / 'zones/zz-fixture.js').write_text(
                'D("discovery.example", REG_NONE, DnsProvider(DNS_BIND), DISCOVERED_RECORDS(), END);')
            # An early-sorting service still runs after the late-sorting zone.
            (directory / 'services/00-fixture.js').write_text(
                'D_EXTEND("discovery.example", TXT("service", "loaded", TTL(90)), END);')
            for name in ['lib', 'zones', 'services', 'other']:
                nested = directory / name / 'nested'
                nested.mkdir(parents=True)
                (nested / 'poison.js').write_text('throw "Nested or archived JS must not load";')
            (directory / 'zones/not-javascript.txt').write_text('throw "Not JavaScript";')
            for config in ['dnsconfig.js', str(directory / 'dnsconfig.js')]:
                with self.subTest(config=config):
                    result = subprocess.run([BINARY, 'print-ir', '--config', config], cwd=directory,
                                            text=True, capture_output=True, check=True)
                    zones = {zone['name']: zone for zone in json.loads(result.stdout)['domains']}
                    discovered = zones.pop('discovery.example')['records']
                    self.assertEqual({(r['name'], r['ttl']) for r in discovered}, {('auto', 75), ('service', 90)})
                    original = ops.read_ir(BINARY)
                    self.assertEqual(ops.canonical(list(zones.values())), ops.canonical(original['domains']))

    def test_archived_javascript_is_not_loaded(self):
        before = ops.read_ir(BINARY)
        with tempfile.TemporaryDirectory(dir=ROOT) as archive, tempfile.NamedTemporaryFile(mode='w', suffix='.js', dir=archive) as poison:
            poison.write('throw "Archive must not load";\n')
            poison.flush()
            ir = ops.read_ir(BINARY)
        ops.compare_ir(before, ir)

    def test_missing_consumed_inputs_fail_clearly(self):
        for missing in ['hcloud-dns.json', 'provider-nameservers.json']:
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as directory:
                directory = Path(directory)
                shutil.copyfile(ROOT / 'dnsconfig.js', directory / 'dnsconfig.js')
                for name in ['lib', 'zones', 'services']:
                    shutil.copytree(ROOT / name, directory / name)
                shutil.copytree(ROOT / 'data', directory / 'data', ignore=shutil.ignore_patterns(missing))
                result = subprocess.run([BINARY, 'check', '--config', 'dnsconfig.js'],
                                        cwd=directory, text=True, capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(missing, result.stdout + result.stderr)

    def test_zone_comparison_ignores_serial_but_detects_ttl_and_data_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'example.zone'
            template = ('$TTL 300\n@ IN SOA ns.example. hostmaster.example. {} 3600 600 604800 300\n'
                        '@ IN NS ns.example.\nwww {} IN A {}\n')
            path.write_text(template.format(1, 300, '192.0.2.1'))
            expected = ops.read_zone(path)
            path.write_text('; a different comment\n' + template.format(2, 300, '192.0.2.1'))
            self.assertEqual(expected, ops.read_zone(path))
            path.write_text(template.format(2, 600, '192.0.2.1'))
            self.assertNotEqual(expected, ops.read_zone(path))
            path.write_text(template.format(2, 300, '192.0.2.2'))
            self.assertNotEqual(expected, ops.read_zone(path))

    def test_v5_schema_comparison_preserves_values_and_metadata(self):
        legacy = {'domains': [{'name': 'example', 'meta': {'dnscontrol_nameraw': 'example', 'ns_ttl': '3600'},
                              'records': [{'name': '@', 'type': 'MX', 'ttl': 300,
                                           'mxpreference': 10, 'target': 'mail.example.'}]}]}
        modern = {'domains': [{'name': 'example', 'meta': {'ns_ttl': '3600'},
                              'records': [{'name': '@', 'type': 'MX', 'ttl': 300, 'typenum': 15,
                                           'rdata': {'Preference': 10, 'Mx': 'mail.example.'}}]}]}
        ops.compare_ir(legacy, modern)
        for field, value in [('Mx', 'other.example.'), ('Preference', 20)]:
            changed = json.loads(json.dumps(modern))
            changed['domains'][0]['records'][0]['rdata'][field] = value
            with self.assertRaises(RuntimeError):
                ops.compare_ir(legacy, changed)
        modern['domains'][0]['meta']['ns_ttl'] = '600'
        with self.assertRaises(RuntimeError):
            ops.compare_ir(legacy, modern)
        with self.assertRaises(RuntimeError):
            ops.portable_ir({'name': '@', 'type': 'MX', 'ttl': 300, 'rdata': {'NewField': 'unknown'}})
        self.assertEqual(ops.portable_ir({'records': None}), {'records': []})

    def test_ir_comparison_detects_provider_and_ignore_changes(self):
        reference = {'domains': [{'name': 'example', 'dnsProviders': {'cloudns': 0},
                                  'unmanaged': [{'label_pattern': 'dynamic', 'rType_pattern': 'A'}]}]}
        for changed in [
            {'domains': [{'name': 'example', 'dnsProviders': {'cloudns': -1},
                          'unmanaged': reference['domains'][0]['unmanaged']}]},
            {'domains': [{'name': 'example', 'dnsProviders': {'cloudns': 0}, 'unmanaged': []}]},
        ]:
            with self.assertRaises(RuntimeError):
                ops.compare_ir(reference, changed)
