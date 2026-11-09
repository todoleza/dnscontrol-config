import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from test_repository import ops


class ExportTests(unittest.TestCase):
    def test_current_export_without_baseline_and_failed_generation_retention(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'bind_zones').mkdir()
            destination = root / 'bind_zones/example.test.zone'
            def zone(address):
                return '$TTL 300\n@ IN SOA ns.example.test. hostmaster.example.test. 1 3600 600 604800 300\n@ IN NS ns.example.test.\nwww IN A ' + address + '\n'
            destination.write_text(zone('192.0.2.1'))
            def render(binary, output):
                (output / destination.name).write_text(zone('192.0.2.2'))
            with patch.object(ops, 'ROOT', root), patch.object(ops, 'BASELINE', root / 'nonexistent-reference'), \
                 patch.object(sys, 'argv', ['dns-ops', 'export', '--dnscontrol', sys.executable]), \
                 patch.object(ops, 'run_dns', return_value='v5.8.0'), \
                 patch.object(ops, 'read_ir', return_value={'domains': [{'name': 'example.test'}]}):
                with patch.object(ops, 'export_bind', side_effect=render):
                    ops.main()
                    self.assertIn('192.0.2.2', destination.read_text())
                    before = destination.stat().st_mtime_ns
                    ops.main()
                    self.assertEqual(before, destination.stat().st_mtime_ns)
                previous = destination.read_bytes()
                with patch.object(ops, 'export_bind', side_effect=RuntimeError('invalid configuration')):
                    with self.assertRaises(RuntimeError): ops.main()
                self.assertEqual(previous, destination.read_bytes())
                def invalid(binary, output):
                    (output / destination.name).write_text('invalid zone content')
                with patch.object(ops, 'export_bind', side_effect=invalid):
                    with self.assertRaises(Exception): ops.main()
                self.assertEqual(previous, destination.read_bytes())
