# DNSControl deployment template

This repository is an anonymized, reusable adaptation of a real DNSControl
deployment. Its structure and workflows grew from managing live DNS across
multiple providers, shared infrastructure and generated inventory.

Domains, addresses and account identifiers have been replaced, and the example
configuration has been reduced for readability. It demonstrates the deployment's
patterns rather than reproducing its complete topology.

The default configuration uses local BIND output only; no tokens or remote
services are needed to evaluate or export it. DNSControl writes forward DNS;
reverse DNS and server provisioning are separate responsibilities.

## Contents

- [Start offline](#start-offline)
- [Example tour and layout](#example-tour-and-layout)
- [Commands](#commands)
- [Edit and review](#edit-and-review)
- [Live providers](#live-providers)
- [HCloud refresh](#hcloud-refresh)
- [MikroTik allowlist source](#mikrotik-allowlist-source)
- [Recipes](#recipes)
- [Troubleshooting and synchronization](#troubleshooting-and-synchronization)

## Start offline

Prerequisites: Python 3 with venv/pip, GNU Make for the optional wrappers, and
DNSControl. Tool installation needs GitHub access via gh or curl. Setup supports
Linux/macOS on amd64/arm64; validation installs pinned Python requirements.

```bash
make setup
make doctor
make export
make check
make check-baseline
```

Setup explicitly downloads a local tool and prepares `.venv`; checks never install
anything. Expect six managed example zones. No credentials file is required for
these offline export/check commands. With tools already installed, evaluation,
export and fixture refresh need no network. Native inspection also works:

```bash
.tools/dnscontrol check
.tools/dnscontrol print-ir
```

## Example tour and layout

| Zone | Demonstrates |
| --- | --- |
| example.test | Shared endpoints, CAA, verification placeholder, Proton mail and delegations |
| lab.example.test | Managed child, nameserver/glue, resolver arrays and SimpleLogin subdomain |
| dyn.example.test | Narrow preservation of externally maintained client A records |
| monitor.example.test | DNS source for downstream MikroTik allowlisting |
| infrastructure.test | HCloud generated hosts, service alias and a DNS role endpoint |
| parked.test | Minimal hosting and deny-sending mail policy |

`dnsconfig.js` loads snapshots and addresses, then nonrecursive `require_glob`
phases: `lib/`, `zones/`, `services/`. Helpers define reusable factories; zones
own their D declarations; services extend zones after all declarations exist.
Adding a direct JS child needs no manifest edit. Nested files do not load.
Run commands from the repository root. Imports in glob-loaded files use
root-relative paths such as `require("data/allowlist-sources.json")`.

`data/` contains explicit inputs, `bind_zones/` contains local generated exports,
`tests/fixtures/` contains fictional inputs, and `tests/baseline/` is the optional
accepted comparison reference. Tool binaries, environments, credentials and
`build/` review artifacts are ignored. Snapshot evaluation never refreshes APIs.

## Commands

| Make target | Purpose / direct equivalent |
| --- | --- |
| help | List supported wrappers |
| setup | setup-tool and setup-venv |
| setup-tool / update-tool | `python3 scripts/tool-setup.py setup-tool` / `update-tool` |
| setup-venv / update-venv | Same script with the corresponding action |
| doctor | `python3 scripts/tool-setup.py doctor` (offline inspection) |
| export | `.venv/bin/python scripts/dns-ops.py export` |
| check | Same script with `check`: current config, exports and tests |
| check-baseline | Same script: optional historical comparison |
| refresh-baseline | Same script: accept current IR and matching exports |
| preview | Scoped native preview; set PROVIDER and ZONE |
| dnscontrol | Forward native arguments via ARGS |
| refresh-hcloud | `python3 scripts/refresh-hcloud.py` |

Setup preserves installed tools; updates are explicit. `DNSCONTROL_TAG=vX.Y.Z`
selects a release during tool update. Wrappers prefer `.tools/dnscontrol` and
`.venv/bin/python`, then PATH tools. Override DNSCONTROL, PYTHON, SYSTEM_PYTHON
or CREDS when needed. ARGS is parsed as arguments without shell evaluation:

```bash
make dnscontrol ARGS='check'
make preview PROVIDER=cloudns ZONE=example.test
```

## Edit and review

Edit inputs, run `make export`, inspect the diff, then run `make check`.
Export validates and writes local BIND files without remote credentials; it
preserves files whose semantic content is unchanged. It is different from a
native BIND push, which depends on your credentials and directory configuration.

The baseline audit is optional and can fail after intended changes. After
reviewing matching current exports, `make refresh-baseline` accepts the new
reference. It is not required before native preview or push.

## Live providers

Replace example domains and identifiers with your own. Copy creds.example.json
to ignored creds.json and populate the environment variables it references.
Provider tokens do not belong in tracked configuration.

Remote provider declarations are commented in dnsconfig.js. Uncomment only those
you use; add their assignment inside the chosen zone, for example:

```js
// In dnsconfig.js:
// var DSP_CLOUDNS = NewDnsProvider("cloudns");
// Inside D(...), alongside local export:
// DnsProvider(DSP_CLOUDNS),
```

The equivalent declarations exist for cloudflare, desec and hetzner. Credentials
use CLOUDFLARE_API_TOKEN, CLOUDNS_SUB_AUTH_ID/CLOUDNS_AUTH_PASSWORD, DESEC_TOKEN,
DESEC_IOT_TOKEN and HCLOUD_TOKEN. deSEC credential profiles can share nameserver
data without sharing tokens. HCloud inventory and Hetzner DNS permissions may
require different accounts/tokens; check your intended scope.

```bash
.tools/dnscontrol preview --providers cloudns --domains example.test --no-populate
.tools/dnscontrol push --providers cloudns --domains example.test --no-populate
```

Use your real zone in these commands. Preview proposes changes; push applies
them. DNSControl may initialize declared providers before applying filters, so
unused declarations should remain commented. Provider nameserver arrays in
`data/provider-nameservers.json` support offline exports; review them when
changing providers. Bunny and Cloudflare entries are fictional `.example`
placeholders: replace them with the nameservers assigned to your zone before
using those sets. The ClouDNS pns61–pns64 set is retained. Native flags and direct CLI use remain available.

## HCloud refresh

The shipped fixture has two servers, distinct host publication selectors, an
IPv6 service suffix and an alias. Refresh it without authentication:

```bash
python3 scripts/refresh-hcloud.py --servers-json tests/fixtures/hcloud-servers.json --output build/hcloud-review.json
```

Omit --output to adopt it. For live inventory use an installed, authenticated
HCloud CLI and `--zone YOUR_ZONE`; the command invokes `hcloud server list -o json`.
Configure stable server IDs and named role suffixes in data/hcloud-config.json.
The atomic snapshot contains both hosts and records. Shared endpoints derive
from inventory independently of publication labels; zones choose families/TTLs.

Labels use `dns.<zone>/host`, `host.records` (A, AAAA, A_AAAA), `ttl`, `priority`
and `publish=false`. Services use `<group>.name`, `.ipv4*=auto|address`,
`.ipv6*=auto|suffix`, `.cname*=alias-owner`, `.ttl`, `.priority`, `.publish`.
Encode suffix colons as hyphens, e.g. 1-2. Missing TTL inherits the zone consumer's
explicit generated-record default. Group TTL/priority overrides host values.

Conflicts are resolved per owner across complete source packages. Identical
packages deduplicate; different packages need a unique highest priority. Ties
fail; prioritized winners warn about suppressed sources. CNAME cannot coexist
with address records in a package. No refresh changes remote DNS or labels.

Missing configured servers, invalid inputs or an empty generated result abort
and retain the snapshot. Removed publishing labels can remove some generated
records; there is no partial-count-drop guard. Review diffs and native preview.

## MikroTik allowlist source

`nodes.monitor.example.test` publishes A and AAAA records from the fictional,
reviewed `data/allowlist-sources.json` snapshot. Its purpose is to supply source
addresses for a downstream MikroTik firewall address list and subsequent
allowlisting.

Replace the documentation addresses with your intended sources, review the data
diff, export and check, then preview and push your real zone. No API or automatic
refresh is provided for this example. Consumers must handle both families and
refresh their resolved address lists when DNS changes; publishing these records
does not configure the router or install firewall rules. Removing an address
from the snapshot removes it from generated DNS, but the downstream router must
also expire or reconcile its cached/list entries. The shipped values are example
addresses and should not be installed as real allowlist rules.

## Recipes

Add a zone as a direct zones/*.js file using D(name, REG_NONE, ...). Put its
parent delegation in the parent zone; use NAMESERVER for child apex NS and add
glue when necessary. Keep DS records explicit and use real child DNSSEC material.

Add a shared endpoint in data/addresses.js, or derive it from HCLOUD.hosts.
Use ADDRESS_RECORDS(name, endpoint, ttl) for scalar/array families. Omit a family
to omit its records; do not substitute CNAMEs merely to deduplicate IP values.

Add coordinated publication in services/*.js with separate D_EXTEND calls.
The photos example preserves 600-second TTLs in both consumers. Mail helpers
accept optional TTLs; SPF options include a label and TTL. Keep DMARC, CAA,
verification and policy specific to the zone.

Generated inputs use GENERATED_RECORDS(records, defaultTtl), supporting A, AAAA
and CNAME with explicit record overrides. Keep input refresh explicit. An IGNORE
rule preserves external records rather than populating them in the snapshot;
keep patterns narrow and verify their effect with the intended provider.

## Troubleshooting and synchronization

Missing binary/dependency: run doctor and explicit setup actions, or override
paths. Missing snapshot: restore it or run the documented fixture refresh.
Export mismatch: regenerate and inspect current outputs before accepting any
baseline. Missing provider token despite filters: check uncommented provider
declarations. Fixture refresh IDs missing: align bindings with your inventory.

This publish branch starts from a single fictional snapshot with no parent
commits. The source template branch remains separate and retains its ancestry.
Keep reusable fixes and fictional tests in focused commits and cherry-pick them
between branches. Configuration and docs remain branch-specific; avoid whole-
branch merges. This template does not publish itself or provision infrastructure.

## License

[MIT](LICENSE).
