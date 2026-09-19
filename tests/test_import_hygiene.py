"""The gate that turns red when an eager import sneaks in (ADR-0004, ADR-0012)."""

from __future__ import annotations

import importlib
import json
import sys

from _helpers import run_python, stdout_of

# The declared base dependencies and nothing else. Every adapter, every provider SDK and
# every convenience library must stay out of `import sandboxio`.
ALLOWED_THIRD_PARTY = frozenset({"sandboxio", "anyio", "sniffio", "typing_extensions", "idna"})

BASELINE = "import sys, json; base = set(sys.modules); print(json.dumps(sorted(base)))"
MEASURE = (
    "import sys, json; base = set(sys.modules); import sandboxio; "
    "print(json.dumps(sorted(set(sys.modules) - base)))"
)


def _top_level_imports() -> set[str]:
    stdout_of("-c", BASELINE)  # same flags, so json/encodings cancel out of the diff
    added: list[str] = json.loads(stdout_of("-c", MEASURE))
    return {name.split(".")[0] for name in added if not name.startswith("_")}


def test_import_pulls_in_nothing_beyond_the_base_dependencies() -> None:
    unexpected = _top_level_imports() - ALLOWED_THIRD_PARTY - sys.stdlib_module_names
    assert not unexpected, (
        f"`import sandboxio` eagerly imported {sorted(unexpected)}. "
        "Adapters and provider SDKs are imported on first use, not at import time."
    )


def test_no_socket_at_import() -> None:
    for name in [m for m in sys.modules if m == "sandboxio" or m.startswith("sandboxio.")]:
        del sys.modules[name]
    importlib.import_module("sandboxio")  # pytest-socket fails this if a socket is opened


def test_import_is_silent() -> None:
    proc = run_python("-c", "import sandboxio")
    assert proc.returncode == 0
    assert (proc.stdout, proc.stderr) == ("", "")


def test_import_configures_no_logging_handlers() -> None:
    out = stdout_of(
        "-c",
        "import logging, sandboxio; "
        "print(logging.getLogger('sandboxio').handlers, logging.root.handlers)",
    )
    assert out.strip() == "[] []"
