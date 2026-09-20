"""``sandboxio.doctor()`` (spec/10): what is installed, reachable and missing, per backend.

Credential variables are reported by **name** only, never by value, and nothing here makes a
provider API call that costs money. The report is what a bug report asks for.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

__all__ = ["BackendReport", "DoctorReport", "Problem", "doctor"]

FIRST_PARTY = ("docker", "e2b", "fake")
_EXTRA = {"docker": "sandboxio[docker]", "e2b": "sandboxio[e2b]"}
_ENV_PREFIX = "SBX_"


@dataclass(frozen=True, slots=True)
class Problem:
    """One failing check and the exact fix."""

    what: str
    hint: str


@dataclass(frozen=True, slots=True)
class BackendReport:
    """One backend's row in the report. ``credentials`` maps variable names to set/unset."""

    name: str
    installed: bool
    install: str | None
    packages: tuple[tuple[str, str], ...]
    credentials: tuple[tuple[str, bool], ...]
    reachable: bool | None
    isolation: str | None
    problems: tuple[Problem, ...]

    @property
    def ok(self) -> bool:
        return not self.problems

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "installed": self.installed,
            "install": self.install,
            "packages": dict(self.packages),
            "credentials": dict(self.credentials),
            "reachable": self.reachable,
            "isolation": self.isolation,
            "problems": [{"what": p.what, "hint": p.hint} for p in self.problems],
        }


@dataclass(frozen=True, slots=True)
class DoctorReport:
    """The whole diagnosis. ``ok`` is True when every installed backend has no problem.

    >>> report = doctor()
    >>> [b.name for b in report.backends][:3]
    ['docker', 'e2b', 'fake']
    """

    sandboxio: str
    python: str
    platform: str
    env: tuple[str, ...]
    backends: tuple[BackendReport, ...]

    @property
    def ok(self) -> bool:
        return all(b.ok for b in self.backends if b.installed)

    def as_dict(self) -> dict[str, Any]:
        return {
            "sandboxio": self.sandboxio,
            "python": self.python,
            "platform": self.platform,
            "env": list(self.env),
            "ok": self.ok,
            "backends": [b.as_dict() for b in self.backends],
        }


def doctor() -> DoctorReport:
    """Diagnose the environment. Safe to call anywhere; no secrets, no paid calls.

    >>> doctor().ok  # doctest: +SKIP
    True
    """
    import platform

    from sandboxio import __version__, registry

    env = tuple(sorted(k for k in os.environ if k.startswith(_ENV_PREFIX)))
    names = [*FIRST_PARTY, *(n for n in registry.available() if n not in FIRST_PARTY)]
    return DoctorReport(
        sandboxio=__version__,
        python=platform.python_version(),
        platform=f"{platform.system()} {platform.machine()}",
        env=env,
        backends=tuple(_probe(name) for name in names),
    )


def _version(distribution: str) -> str | None:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version(distribution)
    except PackageNotFoundError:
        return None


def _packages(*distributions: str) -> tuple[tuple[str, str], ...]:
    found = ((d, _version(d)) for d in distributions)
    return tuple((d, v) for d, v in found if v is not None)


def _installed(module: str) -> bool:
    from importlib.util import find_spec

    try:
        return find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def _probe(name: str) -> BackendReport:
    if name == "docker":
        return _probe_docker()
    if name == "e2b":
        return _probe_e2b()
    if name == "fake":
        return BackendReport(
            name="fake",
            installed=True,
            install=None,
            packages=(),
            credentials=(),
            reachable=True,
            isolation="container (reports it; isolates nothing — tests only)",
            problems=(),
        )
    return _probe_third_party(name)


def _missing(name: str) -> BackendReport:
    extra = _EXTRA[name]
    return BackendReport(
        name=name,
        installed=False,
        install=f'uv pip install "{extra}"',
        packages=(),
        credentials=(),
        reachable=None,
        isolation=None,
        problems=(),
    )


def _probe_docker() -> BackendReport:
    if not _installed("sandboxio_docker"):
        return _missing("docker")
    from sandboxio_docker import DockerBackend

    problems: list[Problem] = []
    engine: str | None
    try:
        engine = _docker_ping()
    except Exception as exc:
        engine = None
        problems.append(
            Problem(
                f"Docker daemon not reachable ({type(exc).__name__})",
                "Start Docker (Desktop, OrbStack, colima) or point DOCKER_HOST at a daemon.",
            )
        )
    reachable = engine is not None
    packages = _packages("sandboxio-docker", "docker")
    if engine:
        packages += (("docker-engine", engine),)
    return BackendReport(
        name="docker",
        installed=True,
        install=None,
        packages=packages,
        credentials=(("DOCKER_HOST", "DOCKER_HOST" in os.environ),),
        reachable=reachable,
        isolation=DockerBackend.isolation.value,
        problems=tuple(problems),
    )


def _docker_ping() -> str:
    """Engine version, or raise. Local daemon only; never a paid call."""
    import docker

    client = docker.from_env(timeout=5)
    try:
        client.ping()
        version: Any = client.version()
        return str(version.get("Version", ""))
    finally:
        client.close()


def _probe_e2b() -> BackendReport:
    if not _installed("sandboxio_e2b"):
        return _missing("e2b")
    from sandboxio_e2b._backend import API_KEY_ENV, E2BBackend

    has_key = bool(os.environ.get(API_KEY_ENV))
    problems = (
        ()
        if has_key
        else (
            Problem(
                f"{API_KEY_ENV} is not set",
                f"export {API_KEY_ENV}=...  (create a key in the E2B dashboard)",
            ),
        )
    )
    return BackendReport(
        name="e2b",
        installed=True,
        install=None,
        packages=_packages("sandboxio-e2b", "e2b-code-interpreter", "e2b"),
        credentials=((API_KEY_ENV, has_key),),
        reachable=None,  # deliberately not probed: it would be an API call
        isolation=E2BBackend.isolation.value,
        problems=problems,
    )


def _probe_third_party(name: str) -> BackendReport:
    from sandboxio import registry

    problems: list[Problem] = []
    isolation: str | None = None
    try:
        factory: Any = registry.resolve(name)
        tier = getattr(factory, "isolation", None)
        isolation = getattr(tier, "value", None)
    except Exception as exc:
        problems.append(
            Problem(
                f"backend {name!r} is registered but does not load ({type(exc).__name__})",
                "Reinstall the distribution that provides it, or unregister it.",
            )
        )
    return BackendReport(
        name=name,
        installed=True,
        install=None,
        packages=(),
        credentials=(),
        reachable=None,
        isolation=isolation,
        problems=tuple(problems),
    )
