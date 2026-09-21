"""The hand-written maps behind two hints, checked against what the adapters declare.

A hint naming the wrong backends is the bug it was meant to fix, so the maps are gated
rather than trusted (spec/04 hint quality).
"""

from __future__ import annotations

import pytest

from sandboxio._dsn import CREDENTIAL_ENV
from sandboxio.errors import CAPABILITY_PROVIDERS
from sandboxio.models import Capability
from sandboxio.testing.fake import DEFAULT_CAPABILITIES


def _label(cap: Capability) -> str:
    return cap.name or str(cap)


def _installed() -> dict[str, Capability]:
    declared: dict[str, Capability] = {"fake": DEFAULT_CAPABILITIES}
    for name, module in (("docker", "sandboxio_docker"), ("e2b", "sandboxio_e2b")):
        backend = pytest.importorskip(f"{module}._backend")
        declared[name] = backend.CAPABILITIES
    return declared


def test_every_key_is_a_real_capability() -> None:
    unknown = set(CAPABILITY_PROVIDERS) - {_label(c) for c in Capability}
    assert not unknown, f"CAPABILITY_PROVIDERS names capabilities that do not exist: {unknown}"


def test_the_provider_map_matches_what_the_backends_declare() -> None:
    declared = _installed()
    actual = {
        _label(cap): tuple(sorted(n for n, caps in declared.items() if cap in caps))
        for cap in Capability
    }
    listed = {
        name: tuple(sorted(n for n in CAPABILITY_PROVIDERS.get(name, ()) if n in declared))
        for name in actual
    }
    drifted = {
        name: (listed[name], actual[name]) for name in actual if listed[name] != actual[name]
    }
    assert not drifted, (
        f"CAPABILITY_PROVIDERS drifted — {{capability: (listed, actual)}}: {drifted}"
    )


def test_the_credential_env_map_matches_the_adapter() -> None:
    backend = pytest.importorskip("sandboxio_e2b._backend")
    assert CREDENTIAL_ENV["e2b"] == backend.API_KEY_ENV
