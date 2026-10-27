"""Run a generated service's own pipeline on this machine: the same make targets its workflow runs, each one timed.

The workflow in a generated repository calls `make lint`, `make test`, `make image`, `make sign`, `make attest`,
`make verify` and `make deploy`; this runs them in that order against a local registry, a local key and local compose.
"""

from __future__ import annotations

import os
import subprocess
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path


class StepFailedError(RuntimeError):
    """A pipeline step exited non-zero; the message carries what it printed."""

    def __init__(self, step: str, output: str) -> None:
        """Keep the step's name and its output."""
        super().__init__(f"{step} failed:\n{output.strip()[-1500:]}")
        self.step = step
        self.output = output


@dataclass(frozen=True, slots=True)
class StepResult:
    """One timed step."""

    name: str
    seconds: float
    output: str


def _run(
    argv: Sequence[str], cwd: Path, env: Mapping[str, str], timeout: float = 900
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        list(argv), cwd=cwd, env={**os.environ, **env}, capture_output=True, text=True, timeout=timeout, check=False
    )


def run_steps(
    directory: Path, steps: Sequence[str], env: Mapping[str, str], variables: Mapping[str, Sequence[str]] | None = None
) -> list[StepResult]:
    """Run `make <step>` for each step in order; stop at the first failure with `StepFailedError`.

    `variables` maps a step to `NAME=value` arguments for that step only."""
    results = []
    for step in steps:
        started = time.monotonic()
        done = _run(["make", "--no-print-directory", step, *(variables or {}).get(step, ())], directory, env)
        output = done.stdout + done.stderr
        if done.returncode != 0:
            raise StepFailedError(step, output)
        results.append(StepResult(step, time.monotonic() - started, output))
    return results


def try_deploy(directory: Path, name: str, image: str, deployment: str, env: Mapping[str, str]) -> tuple[int, str]:
    """Call the template's deploy script directly. Returns its exit status and output (the script verifies first)."""
    done = _run(["scripts/deploy.sh", name, image, deployment, ""], directory, env)
    return done.returncode, done.stdout + done.stderr


def build_unsigned_image(directory: Path, registry: str, name: str, tag: str, env: Mapping[str, str]) -> str:
    """Build and push an image by hand, the way someone bypassing the pipeline would. Returns `registry/name@digest`."""
    reference = f"{registry}/{name}:{tag}"
    built = _run(["docker", "build", "-q", "-t", reference, "."], directory, env)
    if built.returncode != 0:
        raise StepFailedError("docker build", built.stdout + built.stderr)
    pushed = _run(["docker", "push", reference], directory, env)
    if pushed.returncode != 0:
        raise StepFailedError("docker push", pushed.stdout + pushed.stderr)
    digest = next(part for line in pushed.stdout.splitlines() for part in line.split() if part.startswith("sha256:"))
    return f"{registry}/{name}@{digest}"
