"""The same work on two backends. Only the DSN changes.

Run: uv run --extra docker examples/02_swap_backends.py
     E2B_API_KEY=... uv run --all-extras examples/02_swap_backends.py
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import anyio

import sandboxio

if TYPE_CHECKING:
    from sandboxio.protocols import AsyncSandbox


async def build_report(sb: AsyncSandbox) -> str:
    """Nothing in here knows which provider it got — that is the whole point."""
    await sb.files.write("/work/report.txt", "sandboxio\n")
    res = await sb.run(["cat", "/work/report.txt"], timeout=30)
    res.raise_for_status()
    return res.stdout.strip()


async def main() -> None:
    async with await sandboxio.create("docker://python:3.12-slim") as sb:
        print("docker:", await build_report(sb))

    if not os.environ.get("E2B_API_KEY"):
        print("e2b:    skipped — set E2B_API_KEY to run this half")
        return

    async with await sandboxio.create("e2b://code-interpreter-v1") as sb:
        print("e2b:   ", await build_report(sb))


if __name__ == "__main__":
    anyio.run(main)
