#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Test runner for Osintgram project.
This script makes it easy to run tests with various options.
"""

import os
import sys

import pytest


def main():
    """Run the tests."""
    # Add current directory to path so tests can be found
    sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

    # Get command line arguments
    args = sys.argv[1:]

    # Default arguments if none provided
    if not args:
        args = ["-v", "tests/"]

    # Run pytest with the arguments
    exit_code = pytest.main(args)

    # Exit with pytest's exit code
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
