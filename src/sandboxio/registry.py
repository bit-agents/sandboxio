"""Backend resolution: explicit registrations first, then the ``sandboxio.backends``
entry-point group, scanned lazily and cached (spec/07, ADR-0004).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sandboxio.errors import BackendNotFound, BackendNotInstalled

if TYPE_CHECKING:
    from sandboxio.protocols import Backend

__all__ = ["ENTRY_POINT_GROUP", "available", "register", "resolve"]

ENTRY_POINT_GROUP = "sandboxio.backends"

# First-party backends and the extra that installs each. A name here that fails to load
# is "not installed", not "not found".
_FIRST_PARTY_EXTRAS: dict[str, str] = {
    "docker": "sandboxio[docker]",
    "e2b": "sandboxio[e2b]",
    "modal": "sandboxio[modal]",
}

_registered: dict[str, str | type[Backend]] = {}
_loaded: dict[str, type[Backend]] = {}
_entry_points: dict[str, str] | None = None


def register(name: str, target: str | type[Backend]) -> None:
    """Register a backend at runtime; takes precedence over entry points.

    >>> register("mine", "my_pkg.sandbox:MyBackend")
    """
    if not name or "://" in name:
        raise ValueError(f"backend name must be a bare identifier, got {name!r}")
    if isinstance(target, str) and ":" not in target:
        raise ValueError(f"target must look like 'pkg.module:Class', got {target!r}")
    _registered[name] = target
    _loaded.pop(name, None)


def available() -> tuple[str, ...]:
    """Backend names that can be resolved: registrations plus discovered entry points."""
    return tuple(sorted({*_registered, *_scan_entry_points()}))


def resolve(name: str) -> type[Backend]:
    """Load the backend class for ``name``, importing its module on first use only."""
    if name in _loaded:
        return _loaded[name]

    target = _registered.get(name) or _scan_entry_points().get(name)
    if target is None:
        if name in _FIRST_PARTY_EXTRAS:
            raise BackendNotInstalled(name, extra=_FIRST_PARTY_EXTRAS[name])
        raise BackendNotFound(name, available=available())

    try:
        backend = target if not isinstance(target, str) else _load(target)
    except ModuleNotFoundError as exc:
        if name in _FIRST_PARTY_EXTRAS:
            raise BackendNotInstalled(name, extra=_FIRST_PARTY_EXTRAS[name]) from exc
        raise
    _loaded[name] = backend
    return backend


def _load(target: str) -> type[Backend]:
    import importlib

    module_name, _, attr = target.partition(":")
    module = importlib.import_module(module_name)
    try:
        return getattr(module, attr)  # type: ignore[no-any-return]
    except AttributeError as exc:
        raise ImportError(f"{module_name!r} has no attribute {attr!r}") from exc


def _scan_entry_points() -> dict[str, str]:
    global _entry_points
    if _entry_points is None:
        from importlib.metadata import entry_points

        _entry_points = {ep.name: ep.value for ep in entry_points(group=ENTRY_POINT_GROUP)}
    return _entry_points


def _reset() -> None:  # pyright: ignore[reportUnusedFunction] — tests call it
    """Forget registrations and caches. For tests."""
    global _entry_points
    _registered.clear()
    _loaded.clear()
    _entry_points = None
