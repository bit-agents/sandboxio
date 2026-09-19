"""pytest plugin registered by entry point: the ``sbx_fake`` fixture (spec/08)."""

from __future__ import annotations

import pytest

from sandboxio.testing.fake import FakeBackend


@pytest.fixture
def sbx_fake() -> FakeBackend:
    """A fresh ``FakeBackend``: ``.sandbox`` is a ready sandbox, ``.calls`` the call log.

    >>> def test_tool(sbx_fake):  # doctest: +SKIP
    ...     sbx_fake.on_run_code(match="import pandas", returns=ExecResult(0, "2.2.1\\n", ""))
    """
    return FakeBackend()
