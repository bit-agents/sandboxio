"""The parts of FakeBackend users touch directly (spec/08), beyond the contract suite."""

from __future__ import annotations

import pytest

from sandboxio import Capability, NetworkPolicy
from sandboxio.errors import CapabilityNotSupported, ExecutionTimeout, PathNotFound
from sandboxio.models import ExecResult
from sandboxio.testing import FakeBackend, RecordedCall

pytestmark = pytest.mark.anyio


async def test_sbx_fake_fixture_matches_the_spec_snippet(sbx_fake: FakeBackend) -> None:
    sbx_fake.on_run_code(match="import pandas", returns=ExecResult(0, "2.2.1\n", ""))
    sb = sbx_fake.sandbox
    result = await sb.run_code("import pandas; print(pandas.__version__)")
    assert "2.2.1" in result.stdout
    assert sbx_fake.calls[0].network == NetworkPolicy(egress="deny")  # == not is (Q13)
    assert sbx_fake.calls[0].op == "create"


async def test_calls_record_every_operation(sbx_fake: FakeBackend) -> None:
    sb = sbx_fake.sandbox
    await sb.run("echo one two")
    await sb.files.write("/work/a", b"x")
    ops = [c.op for c in sbx_fake.calls]
    assert ops == ["create", "run", "file_write"]
    assert sbx_fake.calls[1] == RecordedCall(
        "run", sandbox_id=sb.id, cmd=("echo", "one", "two"), timeout=None
    )


async def test_string_commands_are_split_shell_style(sbx_fake: FakeBackend) -> None:
    res = await sbx_fake.sandbox.run("echo 'a b' c")
    assert res.stdout == "a b c\n"


async def test_unknown_commands_exit_127(sbx_fake: FakeBackend) -> None:
    res = await sbx_fake.sandbox.run(["frobnicate"])
    assert res.exit_code == 127
    assert "frobnicate" in res.stderr


async def test_scripted_exception_and_delay(sbx_fake: FakeBackend) -> None:
    sbx_fake.on_run(match="boom", returns=PathNotFound("/x"))
    with pytest.raises(PathNotFound):
        await sbx_fake.sandbox.run(["boom"])
    sbx_fake.on_run(match="slow", delay=10)
    with pytest.raises(ExecutionTimeout):
        await sbx_fake.sandbox.run(["slow"], timeout=1)


async def test_run_code_recognises_print_literals_without_executing(
    sbx_fake: FakeBackend,
) -> None:
    sb = sbx_fake.sandbox
    assert (await sb.run_code("print('a', 1)\nprint('b')")).stdout == "a 1\nb\n"
    assert (await sb.run_code("import os; os.system('rm -rf /')")).stdout == ""
    assert (
        await sb.run_code("x = 2 * 21\nprint('x is', x)", context_id="c")
    ).stdout == "x is 42\n"
    assert (await sb.run_code("print(x)", context_id="c")).stdout == "42\n"
    assert (await sb.run_code("print(x)")).exit_code == 1  # one-shot: no context, no x


async def test_native_exposes_internals(sbx_fake: FakeBackend) -> None:
    sb = sbx_fake.sandbox
    await sb.files.write("/work/f", b"1")
    assert sb.native.files == {"/work/f": b"1"}


async def test_capabilities_are_configurable() -> None:
    fake = FakeBackend(capabilities=Capability.RUN_COMMAND | Capability.NETWORK_POLICY)
    async with await fake.create() as sb:
        with pytest.raises(CapabilityNotSupported):
            _ = sb.files
