import math
#!/usr/bin/env python3

import argparse
import ipaddress
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

FALSE_VALUES = {"false", "0", "no", "off"}
RESERVED_GROUPS = {"host", "ttl", "priority", "publish"}


def unwrap(value):
    if isinstance(value, dict):
        if set(value.keys()) == {"__ansible_unsafe"}:
            return value["__ansible_unsafe"]
        return {k: unwrap(v) for k, v in value.items()}
    if isinstance(value, list):
        return [unwrap(v) for v in value]
    return value


def is_false(value):
    return str(value).strip().lower() in FALSE_VALUES


def parse_int(value, what):
    try:
        return int(str(value), 10)
    except Exception as exc:
        raise ValueError(f"{what}: expected integer, got {value!r}") from exc


def normalize_owner(owner, zone):
    owner = str(owner).strip().lower()
    zone = zone.rstrip(".").lower()

    if not owner:
        raise ValueError("empty owner name")
    if owner == "@":
        raise ValueError("@ cannot be stored as an HCloud label value; keep apex records static in dnsconfig.js")
    if owner.endswith("."):
        owner = owner[:-1]
    suffix = "." + zone
    if owner == zone:
        raise ValueError(f"{zone}: apex records must stay static in dnsconfig.js")
    if owner.endswith(suffix):
        owner = owner[: -len(suffix)]
    if not owner:
        raise ValueError(f"{zone}: apex records must stay static in dnsconfig.js")
    return owner


def fqdn(owner, zone):
    owner = normalize_owner(owner, zone)
    return f"{owner}.{zone}."


def suffix_to_ipv6(network, mask, suffix):
    network = ipaddress.IPv6Network(f"{network}/{mask}", strict=False)
    suffix = str(suffix).strip().replace("-", ":")
    suffix_addr = ipaddress.IPv6Address("::" + suffix)
    if int(suffix_addr) >= network.num_addresses:
        raise ValueError("IPv6 suffix outside network")
    return str(ipaddress.IPv6Address(int(network.network_address) | int(suffix_addr)))


def add_record(records, *, zone, owner, rtype, value, ttl, source, priority):
    owner = normalize_owner(owner, zone)
    value = str(value).strip()

    if rtype == "CNAME":
        value = fqdn(value, zone)

    record = {
        "zone": zone,
        "name": owner,
        "type": rtype,
        "value": value,
        "source": source,
        "priority": priority,
    }
    if ttl is not None:
        record["ttl"] = ttl
    records.append(record)


def source_package_signature(rrsets):
    sig = []
    for rr in rrsets:
        sig.append((rr["type"], rr.get("ttl"), tuple(sorted(rr["values"]))))
    return tuple(sorted(sig))


def resolve_conflicts(raw_records):
    """Return final RRsets. Abort on unresolved conflicts."""

    # First aggregate multiple values from the same source into one RRSet.
    by_source_rrset = {}
    for r in raw_records:
        key = (r["zone"], r["name"], r["type"], r["source"])
        entry = by_source_rrset.setdefault(key, {
            "zone": r["zone"],
            "name": r["name"],
            "type": r["type"],
            "ttl": r.get("ttl"),
            "source": r["source"],
            "priority": r["priority"],
            "values": set(),
        })

        if entry["ttl"] != r.get("ttl"):
            raise RuntimeError(f"same RRSet has inconsistent TTLs: {entry} vs {r}")
        if entry["priority"] != r["priority"]:
            raise RuntimeError(f"same RRSet has inconsistent priorities: {entry} vs {r}")

        entry["values"].add(r["value"])

    rrsets = []
    for entry in by_source_rrset.values():
        values = sorted(entry["values"])
        if entry["type"] == "CNAME" and len(values) != 1:
            raise RuntimeError(f"CNAME RRSet has multiple values: {entry}")
        entry["values"] = values
        rrsets.append(entry)

    # Then decide ownership per zone+owner. One source owns one owner name.
    by_owner = defaultdict(list)
    for rr in rrsets:
        by_owner[(rr["zone"], rr["name"])].append(rr)

    final = []

    for (zone, owner), owner_rrsets in sorted(by_owner.items()):
        packages = defaultdict(list)
        for rr in owner_rrsets:
            packages[rr["source"]].append(rr)

        # If only one source owns this name, it may publish A+AAAA together.
        if len(packages) == 1:
            source_rrsets = next(iter(packages.values()))
            types = {rr["type"] for rr in source_rrsets}
            if "CNAME" in types and len(types) > 1:
                raise RuntimeError(f"{owner}.{zone}: one source emits CNAME together with other types")
            final.extend(source_rrsets)
            continue

        package_list = []
        for source, source_rrsets in packages.items():
            priorities = {rr["priority"] for rr in source_rrsets}
            if len(priorities) != 1:
                raise RuntimeError(f"{owner}.{zone}: source {source} has mixed priorities")
            priority = next(iter(priorities))
            package_list.append({
                "source": source,
                "priority": priority,
                "rrsets": source_rrsets,
                "signature": source_package_signature(source_rrsets),
            })

        # Identical packages are harmless duplicates.
        signatures = {pkg["signature"] for pkg in package_list}
        if len(signatures) == 1:
            final.extend(package_list[0]["rrsets"])
            continue

        # Need priority to choose an owner.
        if all(pkg["priority"] is None for pkg in package_list):
            detail = "\n".join(f"  - {pkg['source']} priority=<none>" for pkg in package_list)
            raise RuntimeError(f"{owner}.{zone}: conflict without priority:\n{detail}")

        def priority_value(pkg):
            return -math.inf if pkg["priority"] is None else pkg["priority"]

        max_prio = max(priority_value(pkg) for pkg in package_list)
        winners = [pkg for pkg in package_list if priority_value(pkg) == max_prio]

        if len(winners) != 1:
            detail = "\n".join(f"  - {pkg['source']} priority={pkg['priority']}" for pkg in winners)
            raise RuntimeError(f"{owner}.{zone}: conflict with equal highest priority:\n{detail}")

        winner = winners[0]
        suppressed = [pkg for pkg in package_list if pkg is not winner]
        print(
            f"WARN: {owner}.{zone}: conflict resolved by priority; "
            f"winner={winner['source']} priority={winner['priority']} "
            f"suppressed={','.join(pkg['source'] for pkg in suppressed)}",
            file=sys.stderr,
        )
        final.extend(winner["rrsets"])

    output = []
    for rr in sorted(final, key=lambda r: (r["name"], r["type"], r.get("ttl"), r["values"])):
        output.append({
            "name": rr["name"],
            "type": rr["type"],
            "values": rr["values"],
            "ttl": rr.get("ttl"),
        })

    for record in output:
        if record.get("ttl") is None:
            record.pop("ttl", None)
    return output


def collect_records(inv, *, zone, namespace, default_ttl):
    hostvars = inv.get("_meta", {}).get("hostvars", {})
    records = []

    for inventory_name, hv in sorted(hostvars.items()):
        labels = hv.get("hcloud_labels") or {}

        dns_labels = {}
        for key, value in labels.items():
            if key.startswith(namespace):
                dns_labels[key[len(namespace):]] = str(value)

        if not dns_labels:
            continue

        if is_false(dns_labels.get("publish", "true")):
            continue

        host_ttl = None
        if "ttl" in dns_labels:
            host_ttl = parse_int(dns_labels["ttl"], f"{inventory_name}: ttl")
        host_priority = None
        if "priority" in dns_labels:
            host_priority = parse_int(dns_labels["priority"], f"{inventory_name}: priority")

        host_records = dns_labels.get("host.records", "A_AAAA")
        if host_records not in {"A", "AAAA", "A_AAAA"}:
            raise ValueError(f"{inventory_name}: host.records must be A, AAAA or A_AAAA, got {host_records!r}")
        host_types = set(host_records.split("_"))
        host_owner = dns_labels.get("host")
        if host_owner:
            source = f"{inventory_name}:host"
            ipv4 = hv.get("hcloud_ipv4")
            ipv6 = hv.get("hcloud_ipv6")

            if ipv4 and "A" in host_types:
                add_record(records, zone=zone, owner=host_owner, rtype="A", value=ipv4,
                           ttl=host_ttl, source=source, priority=host_priority)
            if ipv6 and "AAAA" in host_types:
                add_record(records, zone=zone, owner=host_owner, rtype="AAAA", value=ipv6,
                           ttl=host_ttl, source=source, priority=host_priority)

        groups = defaultdict(dict)
        for stem, value in dns_labels.items():
            if stem == "host.records":
                continue
            if "." not in stem:
                continue
            group, field = stem.split(".", 1)
            if group in RESERVED_GROUPS:
                raise RuntimeError(f"{inventory_name}: {group!r} is a reserved group name")
            groups[group][field] = value

        for group, fields in sorted(groups.items()):
            if is_false(fields.get("publish", "true")):
                continue

            owner = fields.get("name")
            if not owner:
                record_fields = [key for key in fields if key.startswith(("ipv4", "ipv6", "cname"))]
                if record_fields:
                    raise RuntimeError(f"{inventory_name}:{group}: record fields present but {group}.name is missing")
                continue

            ttl = host_ttl
            if "ttl" in fields:
                ttl = parse_int(fields["ttl"], f"{inventory_name}:{group}: ttl")
            priority = host_priority
            if "priority" in fields:
                priority = parse_int(fields["priority"], f"{inventory_name}:{group}: priority")

            source = f"{inventory_name}:{group}"

            for field, value in sorted(fields.items()):
                if field.startswith("ipv4"):
                    if value == "auto":
                        ipv4 = hv.get("hcloud_ipv4")
                        if not ipv4:
                            raise RuntimeError(f"{inventory_name}:{group}.{field}: auto requested but server has no hcloud_ipv4")
                        value = ipv4
                    add_record(records, zone=zone, owner=owner, rtype="A", value=value,
                               ttl=ttl, source=source, priority=priority)
                elif field.startswith("ipv6"):
                    if value == "auto":
                        ipv6 = hv.get("hcloud_ipv6")
                        if not ipv6:
                            raise RuntimeError(f"{inventory_name}:{group}.{field}: auto requested but server has no hcloud_ipv6")
                        value = ipv6
                    else:
                        network = hv.get("hcloud_ipv6_network")
                        mask = hv.get("hcloud_ipv6_network_mask", "64")
                        if not network:
                            raise RuntimeError(f"{inventory_name}:{group}.{field}: suffix requested but server has no hcloud_ipv6_network")
                        value = suffix_to_ipv6(network, mask, value)
                    add_record(records, zone=zone, owner=owner, rtype="AAAA", value=value,
                               ttl=ttl, source=source, priority=priority)
                elif field.startswith("cname"):
                    add_record(records, zone=zone, owner=value, rtype="CNAME", value=owner,
                               ttl=ttl, source=source, priority=priority)

    return records


