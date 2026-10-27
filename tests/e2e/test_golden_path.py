"""One service from the command to its first production deployment, with a real registry, key and compose, and an
unsigned image refused. Needs Docker, cosign and `make up` first. Takes a few minutes."""

import os
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.e2e


def goldenpath(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(ROOT / ".venv" / "bin" / "goldenpath"), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=check,
        timeout=1800,
    )


@pytest.fixture(scope="module", autouse=True)
def prerequisites() -> None:
    if shutil.which("cosign") is None or not (ROOT / ".local" / "keys" / "cosign.key").exists():
        pytest.skip("run `make up` first (needs cosign and Docker)")


@pytest.fixture(scope="module")
def first_deployment() -> Iterator[subprocess.CompletedProcess[str]]:
    shutil.rmtree(ROOT / ".local" / "services" / "it-e2e", ignore_errors=True)
    shutil.rmtree(ROOT / ".local" / "remotes" / "it-e2e.git", ignore_errors=True)
    yield goldenpath("new-service", "it-e2e", "team-orders", "--release")
    compose = ROOT / ".local" / "services" / "it-e2e" / "deploy" / "compose.yaml"
    subprocess.run(
        ["docker", "compose", "-p", "it-e2e-production", "-f", str(compose), "down", "-v"],
        env={**os.environ, "IMAGE_REF": "unused"},
        capture_output=True,
        check=False,
    )


def test_a_new_service_reaches_production_in_under_thirty_minutes(first_deployment):
    seconds = int(first_deployment.stdout.split("first production deployment in ")[1].split("s")[0])
    assert seconds < 1800


def test_the_first_deployment_is_listed_with_its_commit(first_deployment):
    done = goldenpath("deployments", "it-e2e")
    assert "it-e2e-d1" in done.stdout


def test_an_unsigned_image_is_refused_at_deployment(first_deployment):
    done = goldenpath("demo-unsigned", "it-e2e", check=False)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "refused" in done.stdout
