#!/usr/bin/env python3
"""Refresh HCloud DNS records and shared endpoints without writing provider DNS."""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import tempfile
from hcloud_records import collect_records, resolve_conflicts

ROOT = Path(__file__).resolve().parent.parent


def generate(servers, config, zone="infrastructure.test"):
    if not isinstance(servers, list) or not servers:
        raise ValueError('expected a nonempty server array')
    inventory, by_id = {}, {}
    for server in servers:
        ident = server['id']
        if ident in by_id:
            raise ValueError('duplicate server ID')
        public = server['public_net']
        v4 = (public.get('ipv4') or {}).get('ip') or None
        prefix = (public.get('ipv6') or {}).get('ip')
        network = ipaddress.IPv6Network(prefix) if prefix else None
        if v4 and ipaddress.ip_address(v4).version != 4:
            raise ValueError('invalid IPv4')
        hv = {'hcloud_labels': server['labels'], 'hcloud_ipv4': v4,
              'hcloud_ipv6': str(network.network_address + 1) if network else None,
              'hcloud_ipv6_network': str(network.network_address) if network else None,
              'hcloud_ipv6_network_mask': network.prefixlen if network else None}
        by_id[ident] = (hv, network)
        inventory[str(ident)] = hv
    hosts = {}
    for name, binding in config.items():
        hv, network = by_id[binding['server_id']]
        endpoint = {key: hv['hcloud_' + key] for key in ('ipv4', 'ipv6') if hv['hcloud_' + key]}
        for role, settings in binding.get('roles', {}).items():
            value = {}
            if settings.get('ipv4'):
                if not hv['hcloud_ipv4']:
                    raise ValueError(f'{name}.{role}: IPv4 required')
                value['ipv4'] = hv['hcloud_ipv4']
            suffix = int(ipaddress.IPv6Address('::' + settings['ipv6_suffix']))
            if network is None or suffix >= network.num_addresses:
                raise ValueError(f'{name}.{role}: suffix outside network')
            value['ipv6'] = str(network.network_address + suffix)
            endpoint[role] = value
        hosts[name] = endpoint
    records = resolve_conflicts(collect_records({'_meta': {'hostvars': inventory}}, zone=zone, namespace='dns.' + zone + '/' , default_ttl=None))
    if not records:
        raise ValueError('empty generated DNS records')
    return {'hosts': hosts, 'records': records}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--zone', default='infrastructure.test')
    parser.add_argument('--servers-json', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'data/hcloud-dns.json')
    args = parser.parse_args()
    pending = None
    try:
        servers = json.loads(args.servers_json.read_text() if args.servers_json else subprocess.check_output(['hcloud', 'server', 'list', '-o', 'json'], text=True))
        result = generate(servers, json.loads((ROOT / 'data/hcloud-config.json').read_text()), zone=args.zone)
        content = json.dumps(result, indent=2, sort_keys=True) + '\n'
        if not args.output.exists() or args.output.read_text() != content:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode='w', dir=args.output.parent, delete=False) as stream:
                pending = Path(stream.name)
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            pending.chmod(0o644)
            os.replace(pending, args.output)
        print(f'HCloud: {len(result["hosts"])} hosts, {len(result["records"])} RRsets; {args.output}')
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        parser.exit(1, f'HCloud refresh failed ({type(exc).__name__}); previous snapshot retained.\n')
    finally:
        if pending and pending.exists():
            pending.unlink()


if __name__ == '__main__':
    main()
