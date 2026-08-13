#!/usr/bin/env python3
"""Run one pytest lane and force process termination after pytest returns.

Some high-value integration tests create library/runtime resources whose non-daemon cleanup can
outlive pytest's completed result in this sandbox. CI lanes are isolated processes anyway, so after
pytest has returned its authoritative exit code we flush output and exit immediately.
"""
from __future__ import annotations

import os
import sys

import pytest


def main() -> None:
    code = int(pytest.main(sys.argv[1:]))
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)


if __name__ == "__main__":
    main()
