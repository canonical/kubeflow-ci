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

import collections
import logging
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Protocol

log = logging.getLogger("bump-rock.tox")

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
    """The real tox runner: shells out to `tox -e <env>`.

    Streams each line of tox output to stderr the moment it arrives so the
    GitHub Actions log shows live progress, while keeping a bounded ring
    buffer of the most recent lines to surface as the log tail (for the
    inner LLM retry loop and for the workflow artifact).
    """

    def run(self, env: str, *, cwd: Path, timeout: int) -> TestResult:
        log.info("starting `tox -e %s` (cwd=%s, timeout=%ds)", env, cwd, timeout)
        t0 = time.monotonic()
        proc = subprocess.Popen(
            ["tox", "-e", env],
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        tail: collections.deque = collections.deque(maxlen=LOG_TAIL_LINES)
        timed_out = False
        prefix = f"[tox -e {env}] "

        assert proc.stdout is not None  # for type checkers
        try:
            for line in proc.stdout:
                # Strip the trailing newline for the streamed prefix copy,
                # but keep it for the ring buffer so reconstructing the
                # tail preserves shape.
                stripped = line.rstrip("\n")
                sys.stderr.write(prefix + stripped + "\n")
                sys.stderr.flush()
                tail.append(stripped)
                if time.monotonic() - t0 > timeout:
                    proc.kill()
                    timed_out = True
                    break
            proc.wait(timeout=max(1, timeout - int(time.monotonic() - t0)))
        except subprocess.TimeoutExpired:
            proc.kill()
            timed_out = True

        elapsed = time.monotonic() - t0
        rc = proc.returncode if not timed_out else -1
        ok = (not timed_out) and rc == 0
        log.info(
            "  -> `tox -e %s` finished rc=%d in %.1fs%s",
            env,
            rc,
            elapsed,
            " (timed out)" if timed_out else "",
        )
        return TestResult(
            env=env,
            ok=ok,
            returncode=rc,
            log_tail="\n".join(tail),
            timed_out=timed_out,
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
