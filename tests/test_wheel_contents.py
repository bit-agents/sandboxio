"""Wheel contents: a base install must pull no adapter code (ADR-0004, H10)."""

from __future__ import annotations

import shutil
import subprocess
import zipfile
from email import message_from_string
from pathlib import Path

import pytest

from _helpers import REPO_ROOT

BASE_DEPENDENCIES = {"anyio", "typing-extensions"}
ADAPTER_MARKERS = ("docker", "e2b", "modal", "adapters/")

pytestmark = [
    pytest.mark.wheel,
    pytest.mark.skipif(shutil.which("uv") is None, reason="needs `uv` on PATH"),
]


@pytest.fixture(scope="module")
def wheels(tmp_path_factory: pytest.TempPathFactory) -> dict[str, zipfile.ZipFile]:
    out = tmp_path_factory.mktemp("dist")
    subprocess.run(
        ["uv", "build", "--all-packages", "--wheel", "--out-dir", str(out)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    built = {p.name.split("-")[0]: zipfile.ZipFile(p) for p in out.glob("*.whl")}
    assert set(built) == {"sandboxio", "sandboxio_docker", "sandboxio_e2b"}, sorted(built)
    return built


@pytest.fixture(scope="module")
def wheel(wheels: dict[str, zipfile.ZipFile]) -> zipfile.ZipFile:
    return wheels["sandboxio"]


def _metadata(wheel: zipfile.ZipFile) -> list[str]:
    name = next(n for n in wheel.namelist() if n.endswith(".dist-info/METADATA"))
    parsed = message_from_string(wheel.read(name).decode())
    return parsed.get_all("Requires-Dist") or []


def test_ships_py_typed(wheel: zipfile.ZipFile) -> None:
    assert "sandboxio/py.typed" in wheel.namelist()


def test_ships_only_the_sandboxio_package(wheel: zipfile.ZipFile) -> None:
    tops = {Path(n).parts[0] for n in wheel.namelist()}
    assert {t for t in tops if not t.endswith(".dist-info")} == {"sandboxio"}


def test_base_install_contains_no_adapter_code(wheel: zipfile.ZipFile) -> None:
    leaked = [
        n for n in wheel.namelist() if any(marker in n.lower() for marker in ADAPTER_MARKERS)
    ]
    assert not leaked, f"adapter code in the base wheel: {leaked}"


def test_base_dependencies_are_only_the_two(wheel: zipfile.ZipFile) -> None:
    unconditional = {
        req.split()[0].split(">")[0].split("=")[0].split("[")[0].strip()
        for req in _metadata(wheel)
        if ";" not in req  # extras carry an `extra == "..."` marker
    }
    assert unconditional == BASE_DEPENDENCIES, "a new base dependency needs an ADR (ADR-0004)"


def test_console_scripts_ship_in_the_base_wheel(wheel: zipfile.ZipFile) -> None:
    entry_points = next(n for n in wheel.namelist() if n.endswith("entry_points.txt"))
    text = wheel.read(entry_points).decode()
    assert "sandboxio = sandboxio.cli:main" in text and "sbx = sandboxio.cli:main" in text


def test_license_files_ship(wheel: zipfile.ZipFile) -> None:
    names = {Path(n).name for n in wheel.namelist() if ".dist-info/licenses/" in n}
    assert {"LICENSE", "LICENSE-DOCS"} <= names


def test_docker_adapter_ships_as_its_own_distribution(
    wheels: dict[str, zipfile.ZipFile],
) -> None:
    docker_wheel = wheels["sandboxio_docker"]
    names = docker_wheel.namelist()
    assert "sandboxio_docker/py.typed" in names
    assert {Path(n).parts[0] for n in names if not n.endswith((".dist-info",))} >= {
        "sandboxio_docker"
    }
    entry_points = next(n for n in names if n.endswith("entry_points.txt"))
    assert "docker = sandboxio_docker:DockerBackend" in docker_wheel.read(entry_points).decode()
    deps = {r.split(">")[0].split(";")[0].strip() for r in _metadata(docker_wheel)}
    assert deps == {"sandboxio", "docker"}


def test_e2b_adapter_ships_as_its_own_distribution(wheels: dict[str, zipfile.ZipFile]) -> None:
    e2b_wheel = wheels["sandboxio_e2b"]
    names = e2b_wheel.namelist()
    assert "sandboxio_e2b/py.typed" in names
    entry_points = next(n for n in names if n.endswith("entry_points.txt"))
    assert "e2b = sandboxio_e2b:E2BBackend" in e2b_wheel.read(entry_points).decode()
    deps = {r.split(">")[0].split(";")[0].strip() for r in _metadata(e2b_wheel)}
    assert deps == {"sandboxio", "e2b-code-interpreter"}
