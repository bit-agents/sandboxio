"""Create a sandbox, run code in it, tear it down.

Run: uv run --extra docker examples/01_hello_sandbox.py
"""

from __future__ import annotations

import anyio

import sandboxio


async def main() -> None:
    # No argument means local Docker. Egress is denied and the 300 s default timeout
    # bounds the sandbox's whole life; neither has to be asked for.
    async with await sandboxio.create() as sb:
        print(f"sandbox {sb.id}, isolation tier {sb.isolation.value}")

        res = await sb.run_code("print('hello from the sandbox')")
        print(res.stdout, end="")

        res = await sb.run(["echo", "and from a command"], timeout=30)
        res.raise_for_status()  # ExecutionError (SBX_E1301) on a non-zero exit
        print(res.stdout, end="")

    # Leaving the block kills the sandbox, including when the body raised.


if __name__ == "__main__":
    anyio.run(main)
