"""An OpenAI Agents SDK agent whose only tool runs model-written Python in a sandbox.

Run: uv add "sandboxio[docker,openai-agents]"
     OPENAI_API_KEY=... uv run examples/06_openai_agents.py

Without the key the example still builds the tool, which is the half sandboxio owns.
"""

from __future__ import annotations

import os

import anyio

import sandboxio
from sandboxio.integrations.openai_agents import make_code_tool

QUESTION = "How many seconds are in three weeks? Compute it in the sandbox."


async def main() -> None:
    async with await sandboxio.create("docker://python:3.12-slim") as sb:
        # A native agents.FunctionTool. One sandbox shared by every call; pass
        # `sandboxio.create` instead of `sb` to get a fresh one per call.
        run_python = make_code_tool(sb)
        params = list(run_python.params_json_schema["properties"])
        print(f"tool {run_python.name!r} takes", params)

        if not os.environ.get("OPENAI_API_KEY"):
            print("agent: skipped — set OPENAI_API_KEY to run it")
            return

        from agents import Agent, Runner

        agent = Agent(
            name="analyst",
            instructions="Answer with numbers you computed in the sandbox, never from memory.",
            tools=[run_python],
        )
        result = await Runner.run(agent, QUESTION)
        print("agent:", result.final_output)


if __name__ == "__main__":
    anyio.run(main)
