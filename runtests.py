#!/usr/bin/env python
"""Run the test suite.

    python -m runtests              # or: python runtests.py
    coverage run -m runtests        # for CI's coverage workflow
"""

import sys

import pytest

if __name__ == "__main__":
    sys.exit(pytest.main(["tests", "-v"]))
