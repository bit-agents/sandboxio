from __future__ import annotations

import dataclasses
import itertools
import operator

import pytest

from sandboxio import (
    Capability,
    ConfigurationError,
    ExecResult,
    ExecutionError,
    FileInfo,
    IsolationTier,
    Meter,
    NetworkPolicy,
    OutputChunk,
    Resources,
    RichOutput,
)

VALUE_OBJECTS = [
    Resources(memory_mb=1),
    NetworkPolicy(allow=("a",)),
    ExecResult(0, "", ""),
    RichOutput("text/plain", "x"),
    Meter(1, "fake"),
    OutputChunk("stdout", b"x"),
    FileInfo("/a", 1, False),
]


@pytest.mark.parametrize("obj", VALUE_OBJECTS, ids=lambda o: type(o).__name__)
def test_value_objects_are_frozen_with_value_equality(obj: object) -> None:
    assert dataclasses.is_dataclass(obj)
    copy = dataclasses.replace(obj)  # type: ignore[type-var]
    assert copy == obj
    assert copy is not obj
    field = dataclasses.fields(obj)[0].name
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(obj, field, None)


def test_defaults_are_secure() -> None:
    assert NetworkPolicy() == NetworkPolicy(egress="deny", allow=(), ingress_ports=())
    assert Resources() == Resources(None, None, None, None)


# --- IsolationTier ----------------------------------------------------------------------------


def test_every_tier_has_a_rank() -> None:
    ranks = [tier.rank for tier in IsolationTier]  # KeyError here means an unranked member
    assert len(set(ranks)) == len(IsolationTier)


def test_ranks_are_spaced_for_insertion() -> None:
    ranks = sorted(tier.rank for tier in IsolationTier)
    assert ranks[0] == 0
    assert all(b - a >= 10 for a, b in itertools.pairwise(ranks))


def test_ordering_follows_escape_resistance() -> None:
    assert (
        IsolationTier.UNKNOWN
        < IsolationTier.CONTAINER
        < IsolationTier.GVISOR
        < IsolationTier.MICROVM
    )
    assert IsolationTier.MICROVM >= IsolationTier.MICROVM
    assert not IsolationTier.CONTAINER > IsolationTier.GVISOR


def test_satisfies_is_at_least() -> None:
    assert IsolationTier.MICROVM.satisfies(IsolationTier.CONTAINER)
    assert IsolationTier.GVISOR.satisfies(IsolationTier.GVISOR)
    assert not IsolationTier.CONTAINER.satisfies(IsolationTier.MICROVM)


@pytest.mark.parametrize(
    "minimum", [t for t in IsolationTier if t is not IsolationTier.UNKNOWN]
)
def test_unknown_satisfies_nothing(minimum: IsolationTier) -> None:
    assert not IsolationTier.UNKNOWN.satisfies(minimum)


def test_requiring_unknown_is_a_configuration_error() -> None:
    with pytest.raises(ConfigurationError) as info:
        IsolationTier.MICROVM.satisfies(IsolationTier.UNKNOWN)
    assert info.value.code == "SBX_E1000"


@pytest.mark.parametrize("op", [operator.add, operator.sub])
def test_tiers_have_no_arithmetic(op: object) -> None:
    with pytest.raises(TypeError):
        op(IsolationTier.MICROVM, 1)  # type: ignore[operator]


def test_tier_values_are_strings_for_serialization() -> None:
    assert IsolationTier("microvm") is IsolationTier.MICROVM


# --- Capability -------------------------------------------------------------------------------


def test_capabilities_combine_and_test_as_flags() -> None:
    caps = Capability.RUN_CODE | Capability.FILESYSTEM
    assert Capability.RUN_CODE in caps
    assert Capability.GPU not in caps
    assert Capability(0) not in [Capability.RUN_CODE]


def test_spec_capability_members_exist() -> None:
    names = {c.name for c in Capability}
    assert names >= {
        "RUN_COMMAND", "RUN_CODE", "STATEFUL_CODE", "STREAMING", "FILESYSTEM",
        "UPLOAD_DOWNLOAD", "PTY", "PAUSE_RESUME", "SNAPSHOT_FORK", "GPU", "LSP", "GIT",
        "NETWORK_POLICY", "TUNNELS", "COST_REPORTING",
    }  # fmt: skip


# --- ExecResult -------------------------------------------------------------------------------


def test_ok_and_raise_for_status() -> None:
    assert ExecResult(0, "out", "").ok
    ExecResult(0, "", "").raise_for_status()
    failed = ExecResult(2, "", "boom")
    assert not failed.ok
    with pytest.raises(ExecutionError) as info:
        failed.raise_for_status()
    assert info.value.result is failed
    assert info.value.code == "SBX_E1301"


def test_positional_construction_matches_the_spec_examples() -> None:
    assert ExecResult(0, "2.2.1\n", "") == ExecResult(exit_code=0, stdout="2.2.1\n", stderr="")


def test_streamed_result_carries_no_buffered_output() -> None:
    assert ExecResult(0, "", "", streamed=True).streamed
    with pytest.raises(ValueError, match="streamed"):
        ExecResult(0, "leftover", "", streamed=True)


def test_results_default_to_none_not_empty() -> None:
    assert ExecResult(0, "", "").results is None
