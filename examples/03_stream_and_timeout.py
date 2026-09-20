"""Read output while it is produced, and let the timeout stop a runaway command.

Run: uv run --extra docker examples/03_stream_and_timeout.py
"""

from __future__ import annotations

import anyio

import sandboxio


async def main() -> None:
    async with await sandboxio.create("docker://python:3.12-slim") as sb:
        # Entering the block starts the process; leaving it kills the process if it
        # is still running, so an abandoned stream cannot outlive the caller.
        cmd = ["sh", "-c", "echo start; sleep 1; echo done"]
        async with sb.stream(cmd, timeout=30) as proc:
            async for chunk in proc:
                print(f"  [{chunk.stream}] {chunk.data.decode()}", end="")
            res = await proc.wait()
        print(f"exit {res.exit_code}, streamed={res.streamed}")

        # A sandbox timeout is always SandboxTimeout, never the builtin TimeoutError,
        # so `except TimeoutError` in your own code cannot swallow it by accident.
        try:
            await sb.run(["sleep", "999"], timeout=1)
        except sandboxio.SandboxTimeout as exc:
            print(f"timed out with {exc.code}")


if __name__ == "__main__":
    anyio.run(main)
