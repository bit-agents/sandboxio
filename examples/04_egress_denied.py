"""Egress is denied until you say otherwise, and the opt-out is one argument.

Run: uv run --extra docker examples/04_egress_denied.py
"""

from __future__ import annotations

import anyio

import sandboxio
from sandboxio import NetworkPolicy

PROBE = """
import urllib.request

print(urllib.request.urlopen("https://example.com", timeout=5).status)
"""


def last_line(text: str) -> str:
    lines = text.strip().splitlines()
    return lines[-1] if lines else "(no output)"


async def main() -> None:
    async with await sandboxio.create() as sb:  # NetworkPolicy() — egress="deny"
        res = await sb.run_code(PROBE, timeout=30)
        print("default:", "reached the network" if res.ok else "denied")
        print("        ", last_line(res.stderr))

    # Opting out is explicit and per sandbox; it is also what the audit event records.
    async with await sandboxio.create(network=NetworkPolicy(egress="allow")) as sb:
        res = await sb.run_code(PROBE, timeout=30)
        print("allowed:", "reached the network" if res.ok else "denied")

    # A per-host allowlist — NetworkPolicy(allow=("pypi.org",)) — is a capability, not a
    # promise: Docker cannot enforce one and refuses it with SBX_E1101 rather than
    # pretending. E2B can. See docs/spec/05-security-policy.md.


if __name__ == "__main__":
    anyio.run(main)
