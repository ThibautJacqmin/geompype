"""Setuptools entry point; project metadata is maintained in pyproject.toml.

Install with ``python -m pip install .`` or build with ``python -m build``.
This shim supports tooling that still expects a setup.py entry point.
"""

from setuptools import setup

if __name__ == "__main__":
    setup()
