"""The ``sandboxio`` command (spec/10): ``doctor``, ``reap``, ``demo``.

Stdlib ``argparse``, not a CLI framework: ``uvx sandboxio demo`` must run from the bare
distribution and core takes no new dependency (ADR-0004). ``rich`` is used for one thing
when it happens to be importable — tracebacks under ``SBX_DEBUG=1``. The library never
prints; this module is where printing lives.

Exit codes, stable across releases: ``0`` success · ``1`` a problem was found or the command
failed · ``2`` usage error · ``130`` interrupted.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import sandboxio
from sandboxio import _doctor
from sandboxio.errors import BackendNotInstalled, ConfigurationError, SandboxError
from sandboxio.models import Capability

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from sandboxio.protocols import ReapableBackend

__all__ = ["main"]

DEMO_DSN = "docker://python:3.12-slim"
DEMO_TIMEOUT = 120.0
EXIT_OK, EXIT_PROBLEM, EXIT_USAGE, EXIT_INTERRUPTED = 0, 1, 2, 130

EXAMPLES = """\
examples:
  sandboxio doctor                 what is installed, reachable and missing
  sandboxio doctor --json          paste this into a bug report; it carries no secrets
  sandboxio reap                   list every sandbox still held under sandboxio's label
  sandboxio reap --kill            remove them; --label tenant_id=acme narrows the set
  uvx sandboxio demo               create, run, stream, tear down — on local Docker
  sandboxio demo --backend fake:// the same demo against the in-process fake

exit codes: 0 success · 1 problem found or command failed · 2 usage error
"""


@dataclass
class Console:
    """Where output goes and whether it may be coloured. ``--json`` writes one document."""

    as_json: bool = False
    color: bool = False

    def emit(self, payload: dict[str, Any], render: Callable[[dict[str, Any]], str]) -> None:
        text = json.dumps(payload, indent=2, default=str) if self.as_json else render(payload)
        sys.stdout.write(text.rstrip("\n") + "\n")

    def line(self, text: str = "") -> None:
        if not self.as_json:  # human mode streams progress; JSON mode is one document
            sys.stdout.write(text + "\n")
            sys.stdout.flush()

    def ok(self, text: str) -> str:
        return self._style(text, "32")

    def bad(self, text: str) -> str:
        return self._style(text, "31")

    def dim(self, text: str) -> str:
        return self._style(text, "2")

    def _style(self, text: str, code: str) -> str:
        return f"\x1b[{code}m{text}\x1b[0m" if self.color else text


def color_allowed(stream: Any = None) -> bool:
    """``NO_COLOR`` wins; otherwise colour only on a TTY that is not ``TERM=dumb``."""
    stream = sys.stdout if stream is None else stream
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("TERM", "") == "dumb":
        return False
    return bool(getattr(stream, "isatty", lambda: False)())


# --- doctor ---------------------------------------------------------------------------------


def cmd_doctor(args: argparse.Namespace, console: Console) -> int:
    report = _doctor.doctor()
    console.emit(report.as_dict(), lambda p: render_doctor(p, console))
    return EXIT_OK if report.ok else EXIT_PROBLEM


def render_doctor(p: dict[str, Any], console: Console) -> str:
    lines = [f"sandboxio {p['sandboxio']} · Python {p['python']} · {p['platform']}"]
    lines.append(f"env: {', '.join(p['env']) if p['env'] else 'no SBX_* variables set'}")
    lines.append("")
    for b in p["backends"]:
        mark = console.ok("✓") if not b["problems"] else console.bad("✗")
        if not b["installed"]:
            lines.append(f"{console.dim('·')} {b['name']:<8} not installed → {b['install']}")
            continue
        parts = [f"{d} {v}" for d, v in b["packages"].items()] or ["built in"]
        if b["credentials"]:
            creds = ", ".join(
                f"{k} {'set' if v else 'unset'}" for k, v in b["credentials"].items()
            )
            parts.append(creds)
        if b["reachable"] is not None:
            parts.append("reachable" if b["reachable"] else "unreachable")
        if b["isolation"]:
            parts.append(f"tier {b['isolation']}")
        lines.append(f"{mark} {b['name']:<8} {' · '.join(parts)}")
        for problem in b["problems"]:
            lines.append(f"    {console.bad(problem['what'])}")
            lines.append(f"    Fix: {problem['hint']}")
    lines.append("")
    lines.append(
        "all installed backends healthy" if p["ok"] else "problems found; fixes are above"
    )
    return "\n".join(lines)


# --- reap -----------------------------------------------------------------------------------


def _parse_labels(raw: list[str]) -> dict[str, str]:
    labels: dict[str, str] = {}
    for item in raw:
        key, sep, value = item.partition("=")
        if not sep or not key:
            raise argparse.ArgumentTypeError(f"--label expects key=value, got {item!r}")
        labels[key] = value
    return labels


def _reapable(name: str) -> ReapableBackend | None:
    """The backend if it is installed and can list its sandboxes; None if not installed."""
    from sandboxio import registry

    try:
        factory = registry.resolve(name)
    except BackendNotInstalled:
        return None
    backend: Any = factory()
    if not hasattr(backend, "list_managed"):
        raise ConfigurationError(
            f"backend {name!r} cannot list its sandboxes.",
            hint="Implement list_managed()/kill_managed() (spec/02, ReapableBackend).",
        )
    reapable: ReapableBackend = backend
    return reapable


async def _reap(names: list[str], labels: dict[str, str], kill: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {"kill": kill, "labels": labels, "backends": {}, "sandboxes": []}
    for name in names:
        backend = _reapable(name)
        if backend is None:
            payload["backends"][name] = "not installed"
            continue
        try:
            found = await backend.list_managed(labels=labels or None)
        except SandboxError as exc:
            payload["backends"][name] = f"list failed: [{exc.code}] {exc.message}"
            continue
        payload["backends"][name] = f"{len(found)} found"
        for sb in found:
            row: dict[str, Any] = {
                "backend": sb.backend,
                "sandbox_id": sb.sandbox_id,
                "state": sb.state,
                "created_at": sb.created_at.isoformat() if sb.created_at else None,
                "labels": sb.labels,
            }
            if kill:
                try:
                    row["killed"] = await backend.kill_managed(sb.sandbox_id)
                except SandboxError as exc:
                    row["killed"] = False
                    row["error"] = f"[{exc.code}] {exc.message}"
            payload["sandboxes"].append(row)
    return payload


def cmd_reap(args: argparse.Namespace, console: Console) -> int:
    import anyio

    names: list[str] = args.backend or ["docker", "e2b"]
    labels = _parse_labels(args.label or [])
    payload = anyio.run(_reap, names, labels, bool(args.kill))
    console.emit(payload, lambda p: render_reap(p, console))
    failed = any(row.get("killed") is False for row in payload["sandboxes"])
    return EXIT_PROBLEM if failed else EXIT_OK


def render_reap(p: dict[str, Any], console: Console) -> str:
    lines = [f"{name}: {status}" for name, status in p["backends"].items()]
    if p["sandboxes"]:
        lines.append("")
        lines.append(f"{'BACKEND':<8} {'ID':<22} {'STATE':<8} {'CREATED':<26} LABELS")
        for row in p["sandboxes"]:
            labels = " ".join(f"{k}={v}" for k, v in row["labels"].items()) or "-"
            tail = ""
            if "killed" in row:
                tail = (
                    console.ok("  killed")
                    if row["killed"]
                    else console.bad(f"  NOT killed {row.get('error', '')}")
                )
            lines.append(
                f"{row['backend']:<8} {row['sandbox_id']:<22} {row['state']:<8} "
                f"{row['created_at'] or '-':<26} {labels}{tail}"
            )
        if not p["kill"]:
            lines.append("")
            lines.append("dry run — re-run with --kill to remove them")
    return "\n".join(lines)


# --- demo -----------------------------------------------------------------------------------

DEMO_CODE = (
    "import sys, platform\n"
    "print('hello from', platform.python_implementation(), sys.version.split()[0])"
)
DEMO_STREAM = ["sh", "-c", "echo tick 1; sleep 0.3; echo tick 2; sleep 0.3; echo tick 3"]
DEMO_EGRESS = (
    "import urllib.request\n"
    "urllib.request.urlopen('http://example.com/', timeout=3)\n"
    "print('reached the network')"
)


def _step(name: str, started: float, ok: bool, detail: str) -> dict[str, Any]:
    return {
        "step": name,
        "ok": ok,
        "ms": int((time.perf_counter() - started) * 1000),
        "detail": detail,
    }


def render_step(step: dict[str, Any], console: Console) -> str:
    mark = console.ok("✓") if step["ok"] else console.bad("✗")
    took = console.dim(f"{step['ms']:>6} ms")
    return f"{mark} {step['step']:<9} {took}  {step['detail']}"


async def _demo(dsn: str, console: Console) -> dict[str, Any]:
    payload: dict[str, Any] = {"backend": dsn, "steps": [], "ok": False}
    steps: list[dict[str, Any]] = payload["steps"]

    def done(step: dict[str, Any]) -> None:
        steps.append(step)
        console.line(render_step(step, console))

    t = time.perf_counter()
    sb = await sandboxio.create(dsn, timeout=DEMO_TIMEOUT, metadata={"sandboxio_demo": "1"})
    payload["sandbox"] = repr(sb)
    payload["isolation"] = sb.isolation.value
    done(_step("create", t, True, f"{sb!r}"))
    async with sb:
        t = time.perf_counter()
        res = await sb.run_code(DEMO_CODE)
        done(_step("run_code", t, res.ok, res.stdout.strip() or res.stderr.strip()))

        if Capability.STREAMING in sb.capabilities:
            t = time.perf_counter()
            chunks: list[str] = []
            async with sb.stream(DEMO_STREAM) as proc:
                async for chunk in proc:
                    chunks.append(chunk.data.decode(errors="replace").strip())
                    console.line(f"  {console.dim('stream')}  {chunks[-1]}")
                streamed = await proc.wait()
            done(_step("stream", t, streamed.ok, f"{len(chunks)} chunks: {' / '.join(chunks)}"))

        t = time.perf_counter()
        res = await sb.run_code(DEMO_EGRESS)
        denied = not res.ok
        done(
            _step(
                "egress",
                t,
                denied,
                "denied by default — nothing left the sandbox"
                if denied
                else "REACHED THE NETWORK: deny-by-default did not apply; report this",
            )
        )
        t = time.perf_counter()
    done(_step("teardown", t, True, "sandbox killed on context exit"))
    payload["ok"] = all(s["ok"] for s in steps)
    return payload


def cmd_demo(args: argparse.Namespace, console: Console) -> int:
    import anyio

    dsn: str = args.backend
    console.line(f"sandboxio demo on {dsn}  {console.dim('(deny-egress, 120 s lifetime)')}")
    try:
        payload = anyio.run(_demo, dsn, console)
    except BackendNotInstalled as exc:
        # `uvx sandboxio demo` on the bare distribution lands here; name the next command.
        payload = {
            "backend": dsn,
            "ok": False,
            "error": {
                "code": exc.code,
                "message": exc.message,
                "hint": exc.hint,
                "uvx": f'uvx --from "{exc.extra}" sandboxio demo',
            },
        }
        console.emit(payload, lambda p: render_not_installed(p, console))
        return EXIT_PROBLEM
    console.emit(payload, lambda p: render_demo(p, console))
    return EXIT_OK if payload["ok"] else EXIT_PROBLEM


def render_not_installed(p: dict[str, Any], console: Console) -> str:
    return (
        f"{console.bad(p['error']['message'])}\n"
        f"  Fix:  {p['error']['hint']}\n"
        f"        or, without installing: {p['error']['uvx']}"
    )


def render_demo(p: dict[str, Any], console: Console) -> str:
    # Steps were already streamed line by line; close with the verdict.
    total = sum(s["ms"] for s in p["steps"])
    tier = p.get("isolation", "?")
    note = " — a shared kernel: trusted, dev and CI code only" if tier == "container" else ""
    verdict = console.ok("demo passed") if p["ok"] else console.bad("demo failed")
    return f"\n{verdict} in {total} ms · isolation tier {tier}{note}"


# --- entry point ----------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sandboxio",
        description="One secure Python API for running AI-agent code in any sandbox.",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version", action="version", version=f"sandboxio {sandboxio.__version__}"
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="command")

    doctor = sub.add_parser(
        "doctor",
        help="per-backend availability, credentials (names only), reachability, versions",
        description="Diagnose the environment. Names credential variables, never values.",
    )
    doctor.add_argument("--json", action="store_true", help="machine-readable, paste-friendly")
    doctor.set_defaults(func=cmd_doctor)

    reap = sub.add_parser(
        "reap",
        help="list (and with --kill remove) sandboxes still held under sandboxio's label",
        description=(
            "Dry run by default. Docker: every io.sandboxio.managed container, running or "
            "stopped. E2B: every sandbox with sandboxio_managed=true."
        ),
    )
    reap.add_argument(
        "--backend", action="append", metavar="NAME", help="docker, e2b, … (default: both)"
    )
    reap.add_argument(
        "--label",
        action="append",
        metavar="KEY=VALUE",
        help="only sandboxes with this metadata",
    )
    reap.add_argument("--kill", action="store_true", help="actually remove what is listed")
    reap.add_argument("--json", action="store_true")
    reap.set_defaults(func=cmd_reap)

    demo = sub.add_parser(
        "demo",
        help="create a sandbox, run code, stream output, prove egress is denied, tear down",
        description="Zero-config demo. Needs Docker; the first run pulls ~130 MB of image.",
    )
    demo.add_argument("--backend", default=DEMO_DSN, metavar="DSN", help=f"default {DEMO_DSN}")
    demo.add_argument("--json", action="store_true")
    demo.set_defaults(func=cmd_demo)
    return parser


def _debug() -> bool:
    return os.environ.get("SBX_DEBUG", "").lower() in ("1", "true", "yes", "on")


def _install_rich_tracebacks() -> None:
    try:
        from rich.traceback import install
    except ImportError:
        return
    install(show_locals=False, suppress=[argparse])


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI; returns the exit code. ``python -m sandboxio`` and ``sandboxio`` call this.

    >>> main(["doctor", "--json"])  # doctest: +SKIP
    0
    """
    if _debug():
        _install_rich_tracebacks()
    parser = build_parser()
    args = parser.parse_args(argv)
    console = Console(as_json=bool(getattr(args, "json", False)), color=color_allowed())
    try:
        return int(args.func(args, console))
    except KeyboardInterrupt:
        return EXIT_INTERRUPTED
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))
    except SandboxError as exc:
        if _debug():
            raise
        if console.as_json:
            sys.stdout.write(
                json.dumps(
                    {
                        "ok": False,
                        "error": {"code": exc.code, "message": exc.message, "hint": exc.hint},
                    }
                )
                + "\n"
            )
        else:
            sys.stderr.write(f"{exc}\n")
        return EXIT_PROBLEM
    except Exception as exc:
        if _debug():
            raise
        sys.stderr.write(
            f"error: {type(exc).__name__}: {exc}\nset SBX_DEBUG=1 for the traceback\n"
        )
        return EXIT_PROBLEM
