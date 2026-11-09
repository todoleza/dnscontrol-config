# Optional conveniences. All native DNSControl commands and flags remain usable.
DNSCONTROL ?= $(if $(wildcard .tools/dnscontrol),.tools/dnscontrol,dnscontrol)
CREDS ?= creds.json
PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)

.DEFAULT_GOAL := help
.PHONY: help check check-baseline refresh-baseline export preview setup setup-tool setup-venv update-tool update-venv doctor dnscontrol
SYSTEM_PYTHON ?= python3
# Freeze the raw value: Make must not expand dollar expressions inside ARGS.
override ARGS := $(value ARGS)
export ARGS DNSCONTROL DNSCONTROL_TAG

help:
	@echo 'make setup                 Prepare local DNSControl and validation environment'
	@echo 'make setup-tool / setup-venv   Prepare one component (preserve installed tool)'
	@echo 'make update-tool / update-venv Explicit updates; DNSCONTROL_TAG selects a release'
	@echo 'make doctor                Offline prerequisite/version inspection'
	@echo "make dnscontrol ARGS='check'   Forward native arguments without a shell"
	@echo 'Direct use: dnscontrol check; dnscontrol preview --providers cloudns --domains example.test --no-populate'
	@echo 'make check                 Validate current configuration, exports and tests'
	@echo 'make check-baseline        Compare against the historical reviewed reference'
	@echo 'make refresh-baseline      Accept current IR and matching exports as the reference'
	@echo 'make export                Validate and update tracked local BIND exports'
	@echo 'make preview PROVIDER=... ZONE=...  Scoped native DNSControl preview'
	@echo 'make refresh-hcloud        Refresh shared HCloud endpoints and DNS input (read-only CLI)'
	@echo 'Overrides: DNSCONTROL=/path/to/dnscontrol PYTHON=/path/to/python CREDS=/path/to/creds.json'

check check-baseline refresh-baseline:
	@"$(PYTHON)" -c 'import dns.zone' 2>/dev/null || { echo "Validation dependencies missing. Run make setup-venv or set PYTHON." >&2; exit 2; }
	"$(PYTHON)" scripts/dns-ops.py $@ --dnscontrol "$(DNSCONTROL)"

export:
	@"$(PYTHON)" -c 'import dns.zone' 2>/dev/null || { echo "Validation dependencies missing. Run make setup-venv or set PYTHON." >&2; exit 2; }
	"$(PYTHON)" scripts/dns-ops.py export --dnscontrol "$(DNSCONTROL)"

preview:
	@command -v "$(DNSCONTROL)" >/dev/null || { echo "DNSControl missing. Run make setup-tool or set DNSCONTROL." >&2; exit 127; }
	@test -n "$(PROVIDER)" -a -n "$(ZONE)" || { echo 'Set PROVIDER and ZONE, or invoke dnscontrol directly with its native flags.' >&2; exit 2; }
	"$(DNSCONTROL)" preview --creds "$(CREDS)" --providers "$(PROVIDER)" --domains "$(ZONE)" --no-populate


setup: setup-tool setup-venv

setup-tool update-tool setup-venv update-venv doctor:
	"$(SYSTEM_PYTHON)" scripts/tool-setup.py $@

dnscontrol:
	"$(SYSTEM_PYTHON)" scripts/run-dnscontrol.py

.PHONY: refresh-hcloud
refresh-hcloud:
	"$(PYTHON)" scripts/refresh-hcloud.py
