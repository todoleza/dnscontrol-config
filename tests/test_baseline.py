import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from test_repository import ops


class BaselineTests(unittest.TestCase):
    def test_refresh_and_current_check(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = root / 'reference'
            zones = root / 'bind_zones'
            zones.mkdir()
            zone = '$TTL 300\n@ IN SOA ns.example.test. hostmaster.example.test. 1 3600 600 604800 300\n@ IN NS ns.example.test.\nwww IN A 192.0.2.1\n'
            name = 'example.test.zone'
            (zones / name).write_text(zone)
            def render(binary, output):
                (output / name).write_text(zone)
            ir = {'domains': [{'name': 'example.test'}]}
            with patch.object(ops, 'ROOT', root), patch.object(ops, 'BASELINE', baseline), patch.object(ops, 'run_dns', return_value='v5.8.0'), patch.object(ops, 'read_ir', return_value=ir), patch.object(ops, 'export_bind', side_effect=render), patch.object(ops.subprocess, 'run'):
                with patch.object(sys, 'argv', ['ops', 'check', '--dnscontrol', sys.executable]):
                    ops.main()  # No reference required.
                (baseline / 'bind_zones').mkdir(parents=True)
                (baseline / 'bind_zones/stale.zone').write_text('old')
                (baseline / 'README.md').write_text('preserve')
                with patch.object(sys, 'argv', ['ops', 'refresh-baseline', '--dnscontrol', sys.executable]):
                    ops.main()
                    self.assertEqual(json.loads((baseline / 'config-ir.json').read_text()), ir)
                    self.assertFalse((baseline / 'bind_zones/stale.zone').exists())
                    self.assertEqual((baseline / 'README.md').read_text(), 'preserve')
                    previous = (baseline / 'config-ir.json').read_bytes()
                    (zones / name).write_text(zone.replace('192.0.2.1', '192.0.2.2'))
                    with self.assertRaises(RuntimeError):
                        ops.main()
                    self.assertEqual((baseline / 'config-ir.json').read_bytes(), previous)
