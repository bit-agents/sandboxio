"""DSN parsing (spec/07): ``<backend>://[<template>][?<param>=<value>&…]``.

A thin front end that produces the same typed values as the object API, never a second
configuration path. Scalars only; anything structured is object-only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlsplit

from sandboxio.errors import ConfigurationError

_SCHEME = re.compile(r"^[a-z][a-z0-9_-]*$")
_CREDENTIAL_PARAM = re.compile(r"(?i)(token|secret|password|passwd|api[_-]?key|credential)")


@dataclass(frozen=True, slots=True)
class ParsedDSN:
    backend: str
    template: str | None
    params: dict[str, str]


def parse(dsn: str) -> ParsedDSN:
    """Split a DSN into backend, template and scalar params. Credentials are refused.

    >>> parse("e2b://code-interpreter?timeout=600")
    ParsedDSN(backend='e2b', template='code-interpreter', params={'timeout': '600'})
    """
    if "://" not in dsn:
        raise ConfigurationError(
            f"{dsn!r} is not a DSN.",
            hint="Write `<backend>://[<template>][?param=value]`, e.g. `docker://python:3.12-slim`.",
        )
    scheme, _, rest = dsn.partition("://")
    if not _SCHEME.match(scheme):
        raise ConfigurationError(
            f"{scheme!r} is not a valid backend name.",
            hint="Backend names are lowercase identifiers, e.g. `docker`, `e2b`, `fake`.",
        )
    parts = urlsplit(f"x://{rest}" if rest else "x://")
    template = (parts.netloc + parts.path) or None
    if parts.fragment:
        raise ConfigurationError(f"DSN {dsn!r} has a fragment; the grammar has none.")

    params: dict[str, str] = {}
    for key, value in parse_qsl(
        parts.query, keep_blank_values=True, strict_parsing=bool(parts.query)
    ):
        if _CREDENTIAL_PARAM.search(key):
            raise ConfigurationError(
                f"DSN parameter {key!r} looks like a credential; those never go in a DSN.",
                hint=f"Unset {key!r}; export the {scheme} provider's own environment variable.",
            )
        if key in params:
            raise ConfigurationError(f"DSN parameter {key!r} is repeated.")
        params[key] = value
    return ParsedDSN(scheme, template, params)
