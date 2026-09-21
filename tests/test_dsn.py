from __future__ import annotations

import pytest

from sandboxio._dsn import ParsedDSN, parse
from sandboxio.errors import ConfigurationError


@pytest.mark.parametrize(
    ("dsn", "expected"),
    [
        ("fake://", ParsedDSN("fake", None, {})),
        ("docker://python:3.12-slim", ParsedDSN("docker", "python:3.12-slim", {})),
        (
            "e2b://code-interpreter?timeout=600",
            ParsedDSN("e2b", "code-interpreter", {"timeout": "600"}),
        ),
        ("modal://base?gpu=T4", ParsedDSN("modal", "base", {"gpu": "T4"})),
        ("my-backend://tpl/with/path", ParsedDSN("my-backend", "tpl/with/path", {})),
    ],
)
def test_grammar(dsn: str, expected: ParsedDSN) -> None:
    assert parse(dsn) == expected


@pytest.mark.parametrize(
    "dsn",
    ["docker", "Docker://x", "1abc://", "fake://x#frag", "fake://?a=1&a=2"],
)
def test_malformed_dsn_is_a_configuration_error(dsn: str) -> None:
    with pytest.raises(ConfigurationError):
        parse(dsn)


@pytest.mark.parametrize("key", ["api_key", "API_KEY", "token", "secret", "password", "apikey"])
def test_credentials_are_refused_with_the_env_var_hint(key: str) -> None:
    with pytest.raises(ConfigurationError) as info:
        parse(f"e2b://tpl?{key}=abc")
    assert "E2B_API_KEY" in info.value.hint, "the hint must name the variable, not describe it"
    assert "abc" not in str(info.value)


def test_a_backend_with_no_known_credential_variable_still_refuses_the_parameter() -> None:
    with pytest.raises(ConfigurationError) as info:
        parse("docker://img?token=abc")
    assert "environment" in info.value.hint
    assert "abc" not in str(info.value)
