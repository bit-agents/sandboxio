#!/usr/bin/env python3
"""Render docker/mcp/tools.json from the MCP server, or --check that it is current.

The first hand-written copy invented its own shape and would have been rejected by the
registry; the tool list is never written by hand again.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import anyio

from sandboxio.mcp import build_server

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docker" / "mcp" / "tools.json"


async def _tools() -> list[dict[str, object]]:
    server = build_server("fake://")
    return [
        {
            "name": t.name,
            "description": (t.description or "").strip(),
            "inputSchema": t.input_schema,
        }
        for t in await server.list_tools()
    ]


def render() -> str:
    return json.dumps(anyio.run(_tools), indent=2) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the file is stale")
    args = parser.parse_args()

    rendered = render()
    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != rendered:
            print(
                f"{OUT.relative_to(ROOT)} is stale; run scripts/gen_mcp_tools.py",
                file=sys.stderr,
            )
            return 1
        print(f"{OUT.relative_to(ROOT)} is current")
        return 0

    OUT.write_text(rendered, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
