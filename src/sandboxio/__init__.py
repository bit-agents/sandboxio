"""One secure Python API for running AI-agent code in any sandbox.

Nothing is imported eagerly here: no adapter, no provider SDK, no logging setup, no
network (ADR-0004, ADR-0012). The public surface arrives in build-order step 2.
"""

from __future__ import annotations

__version__ = "0.0.0"

__all__ = ["__version__"]
