"""Step 3 exit criterion: a deliberately broken adapter fails the suite (ADR-0007).

Each broken fake is run through the real suite in a pytester session; the test asserts
that the *specific* requirement it violates is what fails.
"""

from __future__ import annotations

import pytest

BROKEN = """
from __future__ import annotations

from typing import Any, ClassVar

import anyio

from sandboxio._record import Redactor
from sandboxio.errors import ExecutionTimeout
from sandboxio.models import ExecResult
from sandboxio.protocols import AsyncSandbox, Backend
from sandboxio.testing.fake import FakeBackend, FakeSandbox
from sandboxio.testing.suite import BackendContractSuite


class _Base(BackendContractSuite):
    allowlist_supported = True
    settle = 0.0

    async def wait_until_busy(self, sb: AsyncSandbox) -> None:
        with anyio.fail_after(5):
            while self.backend.live_processes() == 0:
                await anyio.sleep(0)

    async def assert_no_orphans(self, sb: AsyncSandbox) -> None:
        assert self.backend.live_processes() == 0


# --- 1. swallows the timeout and reports success -------------------------------------------


class SwallowingSandbox(FakeSandbox):
    async def run(self, cmd, *, timeout=None, env=None):
        try:
            return await super().run(cmd, timeout=timeout, env=env)
        except ExecutionTimeout:
            return ExecResult(0, "", "")


class SwallowsTimeout(FakeBackend):
    sandbox_class = SwallowingSandbox


class TestSwallowsTimeout(_Base):
    backend: ClassVar[Any] = SwallowsTimeout()


# --- 2. declares NETWORK_POLICY but never enforces it --------------------------------------


class PretendPolicySandbox(FakeSandbox):
    def __init__(self, backend, **kwargs):
        super().__init__(backend, **kwargs)
        from sandboxio.models import NetworkPolicy
        self.network = NetworkPolicy(egress="allow")  # ignores what the caller asked for


class FakesNetworkPolicy(FakeBackend):
    sandbox_class = PretendPolicySandbox


class TestFakesNetworkPolicy(_Base):
    backend: ClassVar[Any] = FakesNetworkPolicy()


# --- 3. leaks secrets into repr and the audit sink -----------------------------------------


class LeakySandbox(FakeSandbox):
    def __init__(self, backend, **kwargs):
        super().__init__(backend, **kwargs)
        self._redact = Redactor(None, None)

    def __repr__(self) -> str:
        return f"<LeakySandbox {self.id} env={self._env}>"


class LeaksSecrets(FakeBackend):
    sandbox_class = LeakySandbox


from sandboxio.audit import AuditConfig
from sandboxio.testing.suite import RecordingSink

_sink = RecordingSink()


class TestLeaksSecrets(_Base):
    backend: ClassVar[Any] = LeaksSecrets(audit=AuditConfig(sinks=(_sink,)))
    audit_sink: ClassVar[Any] = _sink
"""

EXPECTED_FAILURES = {
    "TestSwallowsTimeout": {
        "test_run_timeout_raises_execution_timeout_and_does_not_hang",
        "test_run_timeout_none_inherits_the_sandbox_timeout",
    },
    "TestFakesNetworkPolicy": {
        "test_deny_actually_denies",
        "test_allowlist_permits_only_listed_hosts",
    },
    "TestLeaksSecrets": {"test_repr_is_informative_and_safe", "test_secrets_reach_no_sink"},
}


@pytest.mark.wheel  # slow-ish: a nested pytest session
def test_broken_fakes_fail_exactly_where_they_are_broken(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(test_broken=BROKEN)
    result = pytester.runpytest("-q", "-rfE", "-p", "no:cacheprovider", "--allow-unix-socket")
    failed_lines = [line for line in result.outlines if line.startswith(("FAILED", "ERROR"))]
    failed = {(line.split("::")[1], line.split("::")[2].split("[")[0]) for line in failed_lines}
    for cls, tests in EXPECTED_FAILURES.items():
        for test in tests:
            assert (cls, test) in failed, f"{cls}.{test} passed against a broken adapter"
    unexpected = {f for f in failed if f[1] not in EXPECTED_FAILURES[f[0]]}
    assert not unexpected, f"broken fakes failed unrelated requirements: {sorted(unexpected)}"
