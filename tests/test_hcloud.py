import importlib.util
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1] / 'scripts/hcloud_records.py'
spec = importlib.util.spec_from_file_location('hcloud_inventory', PATH)
hcloud = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hcloud)


class HCloudLabelsTests(unittest.TestCase):
    def collect(self, extra):
        labels = {'dns.example.test/host': 'hc1'}
        labels.update({'dns.example.test/' + k: v for k, v in extra.items()})
        return hcloud.collect_records({'_meta': {'hostvars': {'hc1': {
            'hcloud_labels': labels, 'hcloud_ipv4': '192.0.2.1',
            'hcloud_ipv6': '2001:db8::1',
        }}}}, zone='example.test', namespace='dns.example.test/', default_ttl=None)

    def test_host_record_selection(self):
        for selector, expected in [('A', ['A']), ('AAAA', ['AAAA']),
                                   ('A_AAAA', ['A', 'AAAA']), (None, ['A', 'AAAA'])]:
            with self.subTest(selector=selector):
                labels = {} if selector is None else {'host.records': selector}
                self.assertEqual([r['type'] for r in self.collect(labels)], expected)

    def test_invalid_selector_and_reserved_group(self):
        with self.assertRaisesRegex(ValueError, 'host.records must be'):
            self.collect({'host.records': 'TXT'})
        with self.assertRaisesRegex(RuntimeError, 'reserved group name'):
            self.collect({'host.ipv4': 'auto'})
