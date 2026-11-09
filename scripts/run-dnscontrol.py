#!/usr/bin/env python3
"""Forward ARGS as data, without shell expansion, using only system Python."""
import os
from pathlib import Path
import shlex
import shutil
import sys

ROOT = Path(__file__).resolve().parent.parent


def main():
    executable = os.environ.get('DNSCONTROL') or (str(ROOT / '.tools/dnscontrol') if (ROOT / '.tools/dnscontrol').exists() else 'dnscontrol')
    binary = shutil.which(executable)
    if not binary:
        print('DNSControl not found. Run make setup-tool or set DNSCONTROL.', file=sys.stderr)
        return 127
    try:
        args = shlex.split(os.environ.get('ARGS', '')) or ['--help']
    except ValueError as exc:
        print(f'Invalid ARGS: {exc}', file=sys.stderr)
        return 2
    # Replace the runner: native exit status, signals and inherited environment.
    os.execv(binary, [binary, *args])


if __name__ == '__main__':
    sys.exit(main())
