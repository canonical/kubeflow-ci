# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Subprocess wrapper for tox commands with per-env timeouts.

Spec §7.3 timeouts:
    - tox -e pack             : 30 min
    - tox -e export-to-docker : 15 min
    - tox -e sanity           : 15 min

The wrapper captures combined stdout+stderr, returns a tail of the log
(capped to keep prompt sizes sane for the §6.7 retry feedback loop), and
surfaces a structured TestResult instead of raising on non-zero exit.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Protocol

DEFAULT_TIMEOUTS: dict = {
    "pack": 30 * 60,
    "export-to-docker": 15 * 60,
    "sanity": 15 * 60,
}

DEFAULT_SANITY_PIPELINE: List[str] = ["pack", "export-to-docker", "sanity"]

LOG_TAIL_LINES = 200


@dataclass
class TestResult:
    """Outcome of a single `tox -e <env>` invocation."""

    env: str
    ok: bool
    returncode: int
    log_tail: str
    timed_out: bool = False


class ToxRunner(Protocol):
    """Anything that can run `tox -e <env>` inside a rock folder."""

    def run(self, env: str, *, cwd: Path, timeout: int) -> TestResult: ...


class SubprocessToxRunner:
    """The real tox runner: shells out to `tox -e <env>`."""

    def run(self, env: str, *, cwd: Path, timeout: int) -> TestResult:
        try:
            completed = subprocess.run(
                ["tox", "-e", env],
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            tail = _tail_text(
                (exc.stdout or b"").decode(errors="replace")
                + (exc.stderr or b"").decode(errors="replace")
            )
            return TestResult(
                env=env, ok=False, returncode=-1, log_tail=tail, timed_out=True
            )
        combined = (completed.stdout or "") + (completed.stderr or "")
        return TestResult(
            env=env,
            ok=completed.returncode == 0,
            returncode=completed.returncode,
            log_tail=_tail_text(combined),
        )


def _tail_text(text: str, max_lines: int = LOG_TAIL_LINES) -> str:
    """Return the last `max_lines` lines of `text`."""
    lines = text.splitlines()
    return "\n".join(lines[-max_lines:])


def run_sanity_pipeline(
    rock_dir: Path,
    *,
    runner: Optional[ToxRunner] = None,
    envs: Optional[List[str]] = None,
    timeouts: Optional[dict] = None,
) -> List[TestResult]:
    """Run the sanity-test pipeline against `rock_dir`.

    Returns the list of TestResult objects, stopping at the first failure
    so the caller can feed the failing log back to the LLM.
    """
    runner = runner or SubprocessToxRunner()
    envs = envs or DEFAULT_SANITY_PIPELINE
    timeouts = timeouts or DEFAULT_TIMEOUTS

    results: List[TestResult] = []
    for env in envs:
        result = runner.run(env, cwd=rock_dir, timeout=timeouts[env])
        results.append(result)
        if not result.ok:
            break
    return results


def first_failure(results: List[TestResult]) -> Optional[TestResult]:
    """Return the first failing TestResult, or None if all passed."""
    for r in results:
        if not r.ok:
            return r
    return None
