"""A LangGraph agent whose only tool runs model-written Python in a sandbox.

Run: uv add "sandboxio[docker,langgraph]" langgraph langchain-anthropic
     ANTHROPIC_API_KEY=... uv run examples/05_langgraph_agent.py

Without the key the example still builds the tool and calls it, which is the half
sandboxio owns. `langgraph` and `langchain-anthropic` are yours, not dependencies of
sandboxio — the `langgraph` extra pulls in `langchain-core` alone.
"""

from __future__ import annotations

import os

import anyio

import sandboxio
from sandboxio.integrations.langgraph import make_code_tool

QUESTION = "How many seconds are in three weeks? Compute it in the sandbox."


async def main() -> None:
    async with await sandboxio.create("docker://python:3.12-slim") as sb:
        # A native langchain_core BaseTool. It cannot widen the sandbox's policy:
        # deny-by-default egress, the timeout and the caps come from `create()` above.
        run_python = make_code_tool(sb)
        answer = await run_python.ainvoke({"code": "print(3 * 7 * 24 * 60 * 60)"})
        print(f"tool {run_python.name!r} ->", answer)

        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("agent: skipped — set ANTHROPIC_API_KEY to run the graph")
            return

        # Neither package is a sandboxio dependency; they are the ones you already use.
        from langchain_anthropic import ChatAnthropic
        from langgraph.prebuilt import create_react_agent

        model = ChatAnthropic(model="claude-sonnet-5")
        agent = create_react_agent(model, tools=[run_python])
        result = await agent.ainvoke({"messages": [("user", QUESTION)]})
        print("agent:", result["messages"][-1].content)


if __name__ == "__main__":
    anyio.run(main)
