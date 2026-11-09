import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_repository import ROOT, BINARY


class NameserverTests(unittest.TestCase):
    def test_canonical_sets(self):
        data = json.loads((ROOT / 'data/provider-nameservers.json').read_text())
        self.assertNotIn('desec_iot', data)
        self.assertEqual(data['desec'], ['ns1.desec.io.', 'ns2.desec.org.'])
        self.assertEqual(data['he'], [f'ns{i}.he.net.' for i in range(1, 6)])
        self.assertEqual(data['cloudflare'], ['ns1.cloudflare.example.', 'ns2.cloudflare.example.'])
        self.assertEqual(data['bunny'], ['ns1.bunny.example.', 'ns2.bunny.example.'])

    def test_export_profile_resolution_and_participation(self):
        # Exercise the actual adapter against a small DSL-result fixture.
        adapter = (ROOT / 'scripts/export-bind.js').read_text().replace('require("../dnsconfig.js");', '').replace('conf.', 'fixtureConfig.')
        data = (ROOT / 'data/provider-nameservers.json').read_text()
        for profile, count, expected in [('desec', -1, 2), ('desec_iot', -1, 2),
                                          ('desec_iot', 1, 1), ('unknown', 0, 0), ('unknown', -1, None)]:
            with self.subTest(profile=profile, count=count), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'fixture.js'
                fixture = ('var PROVIDER_NAMESERVERS = ' + data + ';\n'
                           'var observed = [];\n'
                           'function MAKE_NAMESERVERS(names) { return names; }\n'
                           'function D_EXTEND(name, names) { observed = names; }\n'
                           'var fixtureConfig = {dns_providers:[], domains:[{name:"example.test", dnsProviders:'
                           + json.dumps({profile: count}) + '}]};\n' + adapter)
                if expected is not None:
                    fixture += f'\nif (observed.length !== {expected}) throw "Incorrect nameserver count";\n'
                    if expected:
                        fixture += 'if (observed[0] !== "ns1.desec.io.") throw "Incorrect set";\n'
                path.write_text(fixture)
                result = subprocess.run([BINARY, 'check', '--config', str(path)], cwd=ROOT, capture_output=True, text=True)
                if expected is None:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn('profile unknown (set unknown)', result.stdout + result.stderr)
                else:
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
