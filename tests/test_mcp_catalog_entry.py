"""The Docker MCP Catalog entry, gated against the four mistakes the first one shipped with.

`docker/mcp/` is the source the registry pull request is copied from, so a defect here
reaches the catalog rather than CI (docker/mcp-registry#5258).
"""

from __future__ import annotations

import json
import re
from typing import Any, cast

import yaml

from _helpers import REPO_ROOT, run_python

ENTRY = REPO_ROOT / "docker" / "mcp" / "server.yaml"
TOOLS = REPO_ROOT / "docker" / "mcp" / "tools.json"
SHA1 = re.compile(r"^[a-f0-9]{40}$")


def _entry() -> dict[str, Any]:
    return cast("dict[str, Any]", yaml.safe_load(ENTRY.read_text(encoding="utf-8")))


def test_the_tool_list_is_generated_and_current() -> None:
    proc = run_python(str(REPO_ROOT / "scripts" / "gen_mcp_tools.py"), "--check")
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_every_tool_carries_an_input_schema() -> None:
    tools = json.loads(TOOLS.read_text(encoding="utf-8"))
    assert tools, "the tool list is empty"
    for tool in tools:
        assert set(tool) == {"name", "description", "inputSchema"}, tool.get("name")
        assert tool["inputSchema"]["type"] == "object", tool["name"]


def test_the_audited_revision_is_pinned() -> None:
    # The registry refuses a local server without one: it is the revision a human reviews.
    commit = _entry()["source"].get("commit", "")
    assert SHA1.match(commit), (
        f"source.commit must be a 40-character lowercase SHA1, got {commit!r}"
    )


def test_the_title_is_capitalised() -> None:
    # The registry's own rule, and the one place the lowercase project name may not be used.
    title = _entry()["about"]["title"]
    assert all(word[0].isupper() for word in title.split()), title
    assert "MCP" not in title and "Server" not in title, title


def test_the_entry_points_at_the_published_image() -> None:
    assert _entry()["image"] == "ghcr.io/bit-agents/sandboxio-mcp"
