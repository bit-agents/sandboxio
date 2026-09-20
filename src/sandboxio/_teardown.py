"""Shielded, bounded teardown shared by every adapter (ADR-0020). Internal."""

from __future__ import annotations

import os
import warnings
from typing import TYPE_CHECKING

import anyio

from sandboxio.errors import OrphanedSandboxWarning

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping

DEFAULT_TEARDOWN_GRACE = 5.0
_ENV = "SBX_TEARDOWN_GRACE"


def teardown_grace() -> float:
    """Seconds a kill may take before we give up and warn. ``SBX_TEARDOWN_GRACE`` overrides."""
    raw = os.environ.get(_ENV)
    if raw is None:
        return DEFAULT_TEARDOWN_GRACE
    try:
        value = float(raw)
    except ValueError:
        value = -1.0
    if value < 0:
        warnings.warn(
            f"{_ENV}={raw!r} is not a non-negative number; using {DEFAULT_TEARDOWN_GRACE}s",
            OrphanedSandboxWarning,
            stacklevel=2,
        )
        return DEFAULT_TEARDOWN_GRACE
    return value


async def shielded_kill(
    kill: Callable[[], Awaitable[None]],
    *,
    sandbox_id: str,
    backend: str,
    labels: Mapping[str, str] | None = None,
) -> bool:
    """Run ``kill`` where cancellation cannot reach it, for at most the grace period.

    Returns False and emits ``OrphanedSandboxWarning`` if the grace expired or ``kill``
    raised. A failed teardown never replaces the exception the caller's block raised.
    """
    failure: BaseException | None = None
    with anyio.move_on_after(teardown_grace(), shield=True) as scope:
        try:
            await kill()
        except Exception as exc:
            failure = exc
    if not scope.cancelled_caught and failure is None:
        return True
    tags = " ".join(f"{k}={v}" for k, v in (labels or {}).items())
    reason = "exceeded the grace period" if failure is None else f"failed: {failure!r}"
    warnings.warn(
        f"teardown of sandbox {sandbox_id} on {backend} {reason}; "
        f"it may still be running. labels: {tags or 'none'}",
        OrphanedSandboxWarning,
        stacklevel=2,
    )
    return False
