"""Frozen-app entry point (PyInstaller runs a script, not a module).

Relative imports need package context, so we import and call the package's
main() rather than executing eter/__main__.py directly.
"""
import sys

from eter.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
