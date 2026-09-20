"""The ``sandboxio`` command (spec/10): doctor, reap, demo, and their exit codes."""

# The registry is module state; tests reset it through its private hook.
# pyright: reportPrivateUsage=false
from __future__ import annotations

import json
import re
from collections.abc import Iterator

import pytest

from _helpers import REPO_ROOT, run_python
from sandboxio import _doctor, cli, registry
from sandboxio.models import ExecResult
from sandboxio.testing.fake import FakeBackend

ANSI = re.compile(r"\x1b\[[0-9;]*m")


@pytest.fixture(autouse=True)
def _no_color(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.delenv("SBX_DEBUG", raising=False)


@pytest.fixture(autouse=True)
def clean_registry() -> Iterator[None]:
    registry._reset()
    yield
    registry._reset()


@pytest.fixture
def fake() -> FakeBackend:
    fake = FakeBackend()
    registry.register("fake", lambda: fake)
    return fake


def run(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    code = cli.main(argv)
    out, err = capsys.readouterr()
    return code, out, err


# --- doctor ---------------------------------------------------------------------------------


@pytest.fixture
def offline_docker(monkeypatch: pytest.MonkeyPatch) -> None:
    def down() -> str:
        raise ConnectionError("no daemon")

    monkeypatch.setattr(_doctor, "_docker_ping", down)


def test_doctor_json_names_credentials_and_never_prints_values(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], offline_docker: None
) -> None:
    secret = "e2b_" + "s3cr3t" * 4
    monkeypatch.setenv("E2B_API_KEY", secret)
    monkeypatch.setenv("SBX_DEBUG", "0")
    monkeypatch.setenv("DOCKER_HOST", "unix:///tmp/very-private.sock")
    code, out, err = run(["doctor", "--json"], capsys)
    payload = json.loads(out)
    assert secret not in out and "very-private" not in out and err == ""
    assert payload["env"] == ["SBX_DEBUG"]
    by_name = {b["name"]: b for b in payload["backends"]}
    assert {"docker", "e2b", "fake"} <= set(by_name)
    e2b = by_name["e2b"]
    if e2b["installed"]:
        assert e2b["credentials"] == {"E2B_API_KEY": True}
        assert e2b["reachable"] is None, "doctor never calls the E2B API"
        assert e2b["isolation"] == "microvm"
    docker = by_name["docker"]
    if docker["installed"]:
        assert docker["reachable"] is False
        assert docker["problems"][0]["hint"].startswith("Start Docker")
        assert code == cli.EXIT_PROBLEM
    assert payload["ok"] == (code == 0)


def test_doctor_human_output_is_the_same_payload(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], offline_docker: None
) -> None:
    monkeypatch.delenv("E2B_API_KEY", raising=False)
    _, human, _ = run(["doctor"], capsys)
    _, machine, _ = run(["doctor", "--json"], capsys)
    payload = json.loads(machine)
    assert not ANSI.search(human), "NO_COLOR must strip every escape"
    for backend in payload["backends"]:
        assert backend["name"] in human
        for problem in backend["problems"]:
            assert problem["what"] in human and problem["hint"] in human
    assert "problems found" in human or "healthy" in human


def test_doctor_is_programmatic_and_frozen() -> None:
    report = _doctor.doctor()
    assert [b.name for b in report.backends][:3] == ["docker", "e2b", "fake"]
    with pytest.raises(AttributeError):
        report.python = "x"  # type: ignore[misc]
    assert json.dumps(report.as_dict())  # JSON-ready without a default hook


# --- reap -----------------------------------------------------------------------------------


async def _leave_running(fake: FakeBackend, tenant: str) -> str:
    sb = await fake.create(metadata={"tenant_id": tenant})
    return sb.id


def test_reap_lists_by_default_and_kills_only_with_the_flag(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str]
) -> None:
    import anyio

    a = anyio.run(_leave_running, fake, "acme")
    b = anyio.run(_leave_running, fake, "other")
    code, out, _ = run(["reap", "--backend", "fake", "--json"], capsys)
    payload = json.loads(out)
    assert code == 0 and payload["kill"] is False
    assert {row["sandbox_id"] for row in payload["sandboxes"]} == {a, b}
    assert payload["backends"]["fake"] == "2 found"
    assert fake.live_sandboxes() == 2, "a dry run kills nothing"

    code, out, _ = run(["reap", "--backend", "fake", "--label", "tenant_id=acme"], capsys)
    assert code == 0 and a in out and b not in out and "dry run" in out

    code, out, _ = run(
        ["reap", "--backend", "fake", "--label", "tenant_id=acme", "--kill", "--json"], capsys
    )
    payload = json.loads(out)
    assert code == 0 and payload["sandboxes"] == [
        {
            "backend": "fake",
            "sandbox_id": a,
            "state": "running",
            "created_at": None,
            "labels": {"tenant_id": "acme"},
            "killed": True,
        }
    ]
    assert fake.live_sandboxes() == 1


def test_reap_reports_uninstalled_backends_instead_of_failing(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(registry, "_entry_points", {})
    code, out, _ = run(["reap", "--backend", "docker", "--backend", "e2b", "--json"], capsys)
    assert code == 0
    assert json.loads(out)["backends"] == {"docker": "not installed", "e2b": "not installed"}


def test_reap_rejects_a_malformed_label(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as info:
        cli.main(["reap", "--backend", "fake", "--label", "nonsense"])
    assert info.value.code == cli.EXIT_USAGE


# --- demo -----------------------------------------------------------------------------------


def test_demo_runs_against_the_fake_and_proves_egress_is_denied(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = run(["demo", "--backend", "fake://", "--json"], capsys)
    payload = json.loads(out)
    assert code == 0 and err == "", out
    assert [s["step"] for s in payload["steps"]] == [
        "create",
        "run_code",
        "stream",
        "egress",
        "teardown",
    ]
    assert all(s["ok"] for s in payload["steps"])
    assert "tick 1 / tick 2 / tick 3" in payload["steps"][2]["detail"]
    assert payload["isolation"] == "container"
    assert fake.live_sandboxes() == 0, "the demo tears down what it made"


def test_demo_fails_loudly_if_egress_is_not_denied(
    fake: FakeBackend, capsys: pytest.CaptureFixture[str]
) -> None:
    fake.on_run_code(match="urllib", returns=ExecResult(0, "reached the network\n", ""))
    code, out, _ = run(["demo", "--backend", "fake://"], capsys)
    assert code == cli.EXIT_PROBLEM
    assert "REACHED THE NETWORK" in out and "demo failed" in out


def test_demo_without_the_docker_extra_prints_the_install_command(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(registry, "_entry_points", {})
    code, out, _ = run(["demo"], capsys)
    assert code == cli.EXIT_PROBLEM
    assert 'uv pip install "sandboxio[docker]"' in out
    assert 'uvx --from "sandboxio[docker]" sandboxio demo' in out
    code, out, _ = run(["demo", "--json"], capsys)
    assert json.loads(out)["error"]["code"] == "SBX_E1002"


# --- entry point ----------------------------------------------------------------------------


def test_sandbox_errors_render_code_fix_docs_and_exit_1(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(registry, "_entry_points", {})
    code, out, err = run(["demo", "--backend", "nope://"], capsys)
    assert code == cli.EXIT_PROBLEM
    assert "[SBX_E1001]" in err and "Fix:" in err and "Docs:" in err
    assert "SBX_E1001" not in out, "errors go to stderr; stdout stays clean for pipes"


def test_sbx_debug_reraises_for_a_full_traceback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SBX_DEBUG", "1")
    monkeypatch.setattr(registry, "_entry_points", {})
    from sandboxio.errors import BackendNotFound

    with pytest.raises(BackendNotFound):
        cli.main(["demo", "--backend", "nope://"])


def test_help_carries_examples_and_exit_codes() -> None:
    text = cli.build_parser().format_help()
    assert "uvx sandboxio demo" in text and "exit codes" in text
    assert "sbx " not in text, "the alias is never documented (ADR-0014)"


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    import sandboxio

    with pytest.raises(SystemExit) as info:
        cli.main(["--version"])
    assert info.value.code == 0
    assert capsys.readouterr().out.strip() == f"sandboxio {sandboxio.__version__}"


def test_no_command_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as info:
        cli.main([])
    assert info.value.code == cli.EXIT_USAGE


def test_python_dash_m_is_the_same_command() -> None:
    proc = run_python("-m", "sandboxio", "--help")
    assert proc.returncode == 0 and "doctor" in proc.stdout


def test_color_respects_no_color_and_non_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    class Tty:
        def isatty(self) -> bool:
            return True

    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    assert cli.color_allowed(Tty())
    assert not cli.color_allowed(object())
    monkeypatch.setenv("NO_COLOR", "1")
    assert not cli.color_allowed(Tty())
    monkeypatch.delenv("NO_COLOR")
    monkeypatch.setenv("TERM", "dumb")
    assert not cli.color_allowed(Tty())


def test_console_scripts_are_declared() -> None:
    text = (REPO_ROOT / "pyproject.toml").read_text()
    assert 'sandboxio = "sandboxio.cli:main"' in text and 'sbx = "sandboxio.cli:main"' in text


def test_cli_is_not_imported_by_import_sandboxio() -> None:
    proc = run_python("-c", "import sys, sandboxio; print('sandboxio.cli' in sys.modules)")
    assert proc.stdout.strip() == "False"
