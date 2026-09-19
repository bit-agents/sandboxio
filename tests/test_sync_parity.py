"""ADR-0022: every public async member has a sync twin with the same signature."""

from __future__ import annotations

import inspect
from typing import Any

import pytest

from sandboxio import api, sync
from sandboxio.protocols import AsyncFileSystem, AsyncSandbox, Process

RENAMES = {"__aenter__": "__enter__", "__aexit__": "__exit__", "__aiter__": "__iter__"}
TYPE_MAP = {
    "AsyncSandbox": "Sandbox",
    "AsyncFileSystem": "FileSystem",
    "AsyncIterator[OutputChunk]": "Iterator[OutputChunk]",
}
PAIRS = [
    (AsyncSandbox, sync.Sandbox),
    (AsyncFileSystem, sync.FileSystem),
    (Process, sync.Process),
]


def _public_members(proto: type) -> list[str]:
    names = [n for n in vars(proto) if not n.startswith("_") or n in RENAMES]
    names += [n for n in getattr(proto, "__annotations__", {}) if n not in names]
    return sorted(names)


def _normalise(sig: inspect.Signature) -> str:
    text = str(sig)
    for old, new in TYPE_MAP.items():
        text = text.replace(old, new)
    return text


@pytest.mark.parametrize(("proto", "facade"), PAIRS, ids=lambda c: c.__name__)
def test_every_async_member_has_a_sync_twin(proto: type, facade: type) -> None:
    for name in _public_members(proto):
        twin = RENAMES.get(name, name)
        assert hasattr(facade, twin), f"{facade.__name__} lacks {twin!r}"
        async_member: Any = inspect.getattr_static(proto, name, None)
        sync_member: Any = inspect.getattr_static(facade, twin)
        if isinstance(async_member, property):
            assert isinstance(sync_member, property), f"{twin} must be a property"
            continue
        if not callable(async_member):
            continue  # a plain attribute, e.g. `id`; presence is enough
        assert callable(sync_member) and not inspect.iscoroutinefunction(sync_member), twin
        assert _normalise(inspect.signature(async_member)) == _normalise(
            inspect.signature(sync_member)
        ), f"{proto.__name__}.{name} and {facade.__name__}.{twin} differ"


@pytest.mark.parametrize(
    ("async_fn", "sync_fn"),
    [(api.create, sync.create_sync), (api.connect, sync.connect_sync)],
    ids=["create", "connect"],
)
def test_module_level_entry_points_match(async_fn: Any, sync_fn: Any) -> None:
    assert _normalise(inspect.signature(async_fn)) == _normalise(inspect.signature(sync_fn))
