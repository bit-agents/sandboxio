# The registry is module state; tests reset it through its private hook.
# pyright: reportPrivateUsage=false
from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

import sandboxio
from _conforming import MinimalBackend
from sandboxio import registry
from sandboxio.errors import BackendNotFound, BackendNotInstalled


@pytest.fixture(autouse=True)
def clean_registry() -> Iterator[None]:
    registry._reset()
    yield
    registry._reset()


def test_register_then_resolve_returns_the_class() -> None:
    sandboxio.register("stub", MinimalBackend)
    assert registry.resolve("stub") is MinimalBackend
    assert "stub" in registry.available()


def test_register_accepts_a_dotted_path_and_imports_lazily(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sandboxio.register("late", "late_backend_mod:LateBackend")
    assert "late_backend_mod" not in sys.modules

    module = type(sys)("late_backend_mod")
    module.LateBackend = MinimalBackend  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "late_backend_mod", module)
    assert registry.resolve("late") is MinimalBackend


def test_registration_beats_entry_points(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry, "_entry_points", {"stub": "nowhere:Nothing"})
    sandboxio.register("stub", MinimalBackend)
    assert registry.resolve("stub") is MinimalBackend


@pytest.mark.parametrize("bad", ["", "docker://x"])
def test_register_rejects_non_identifier_names(bad: str) -> None:
    with pytest.raises(ValueError, match="bare identifier"):
        sandboxio.register(bad, MinimalBackend)


def test_register_rejects_a_target_without_a_colon() -> None:
    with pytest.raises(ValueError, match=r"pkg\.module:Class"):
        sandboxio.register("x", "just.a.module")


def test_unknown_name_raises_not_found_listing_available() -> None:
    sandboxio.register("stub", MinimalBackend)
    with pytest.raises(BackendNotFound) as info:
        registry.resolve("nope")
    assert info.value.code == "SBX_E1001"
    assert "stub" in info.value.available
    assert "stub" in info.value.hint


@pytest.mark.parametrize("name", ["docker", "e2b", "modal"])
def test_first_party_name_without_its_extra_raises_not_installed(name: str) -> None:
    with pytest.raises(BackendNotInstalled) as info:
        registry.resolve(name)
    assert info.value.code == "SBX_E1002"
    assert info.value.hint == f'uv pip install "sandboxio[{name}]"'


def test_first_party_import_failure_is_not_installed_with_cause() -> None:
    sandboxio.register("e2b", "sandboxio_missing_sdk_probe:E2BBackend")
    with pytest.raises(BackendNotInstalled) as info:
        registry.resolve("e2b")
    assert isinstance(info.value.__cause__, ModuleNotFoundError)


def test_third_party_import_failure_propagates() -> None:
    sandboxio.register("theirs", "sandboxio_missing_sdk_probe:Cls")
    with pytest.raises(ModuleNotFoundError):
        registry.resolve("theirs")


def test_missing_attribute_is_an_import_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "empty_backend_mod", type(sys)("empty_backend_mod"))
    sandboxio.register("empty", "empty_backend_mod:Missing")
    with pytest.raises(ImportError, match="no attribute 'Missing'"):
        registry.resolve("empty")


def test_entry_points_are_discovered_from_installed_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "tempy_backend.py").write_text("class TempBackend:\n    name = 'tempy'\n")
    dist = tmp_path / "tempy-0.0.dist-info"
    dist.mkdir()
    (dist / "METADATA").write_text("Metadata-Version: 2.1\nName: tempy\nVersion: 0.0\n")
    (dist / "entry_points.txt").write_text(
        f"[{registry.ENTRY_POINT_GROUP}]\ntempy = tempy_backend:TempBackend\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))  # pyright: ignore[reportUnknownMemberType]
    monkeypatch.delitem(sys.modules, "tempy_backend", raising=False)

    assert "tempy" in registry.available()
    backend = registry.resolve("tempy")
    assert backend.__name__ == "TempBackend"
    assert registry.resolve("tempy") is backend, "loaded classes are cached"


def test_entry_point_scan_happens_once(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def fake_entry_points(*, group: str) -> list[object]:
        nonlocal calls
        calls += 1
        return []

    monkeypatch.setattr("importlib.metadata.entry_points", fake_entry_points)
    registry.available()
    registry.available()
    assert calls == 1
