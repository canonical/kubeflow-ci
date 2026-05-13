# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Full pre-PR pipeline: generate + sanity tests, with capped retry.

Spec §6.7 contract:
    - 1 initial sanity attempt + up to MAX_SANITY_ATTEMPTS - 1 re-generations.
    - On sanity failure, the tox log tail is fed back to the LLM as
      `additional_context` for the next generate call.
    - `tests/` (and every file other than `rockcraft.yaml`) is never touched.
    - When the cap is hit, no PR is opened; the last failure log is surfaced.
"""
from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from . import generate as generate_mod
from . import tox_runner as tox_mod
from .errors import BumpRockError
from .fetch import DockerfilePair
from .llm import LLMClient
from .rockcraft import RockcraftDoc

MAX_SANITY_ATTEMPTS = 3

log = logging.getLogger("bump-rock.run")


@dataclass
class AttemptOutcome:
    """One generate + sanity-test attempt."""

    attempt: int
    rockcraft_yaml: str
    test_results: List[tox_mod.TestResult] = field(default_factory=list)
    validator_errors: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.test_results) and all(r.ok for r in self.test_results)


@dataclass
class RunResult:
    """Outcome of the full pipeline."""

    ok: bool
    attempts: List[AttemptOutcome]
    final_rockcraft_yaml: Optional[str] = None
    final_error: Optional[str] = None


def run(
    *,
    client: LLMClient,
    doc: RockcraftDoc,
    pairs: List[DockerfilePair],
    target_version: str,
    work_dir: Path,
    runner: Optional[tox_mod.ToxRunner] = None,
    max_sanity_attempts: int = MAX_SANITY_ATTEMPTS,
    max_llm_retries: int = generate_mod.MAX_LLM_RETRIES,
    skip_tox: bool = False,
) -> RunResult:
    """Generate + sanity-test, retrying on failure up to the cap.

    The original `doc.path` is never modified. `work_dir` is the directory
    where the updated rockcraft.yaml is written for tox to consume; the
    caller is responsible for putting a copy of the rock folder there
    first (see `prepare_work_dir`).

    `skip_tox` is for local iteration on the prompt: short-circuits after
    the first successful generate, no rockcraft pack involved.
    """
    runner = runner or tox_mod.SubprocessToxRunner()
    attempts: List[AttemptOutcome] = []

    for attempt_no in range(1, max_sanity_attempts + 1):
        log.info("=== sanity attempt %d/%d ===", attempt_no, max_sanity_attempts)
        gen = generate_mod.generate(
            client=client,
            doc=doc,
            pairs=pairs,
            target_version=target_version,
            max_retries=max_llm_retries,
            additional_context=_build_history_context(attempts),
        )
        (work_dir / "rockcraft.yaml").write_text(gen.rockcraft_yaml)

        if not gen.ok:
            # Inner validator retries exhausted. Re-running generate with
            # the same prompt won't help (the model can't get past the
            # validators for this Dockerfile diff). Bail with the
            # best-effort yaml so the open-pr step can publish a draft.
            log.warning(
                "generate gave up after %d inner attempts with %d validator "
                "error(s); not retrying the outer loop.",
                gen.attempts,
                len(gen.validator_errors),
            )
            outcome = AttemptOutcome(
                attempt=attempt_no,
                rockcraft_yaml=gen.rockcraft_yaml,
                validator_errors=gen.validator_errors,
            )
            attempts.append(outcome)
            return RunResult(
                ok=False,
                attempts=attempts,
                final_rockcraft_yaml=gen.rockcraft_yaml,
                final_error=(
                    "LLM could not produce a rockcraft.yaml that passed the "
                    f"validators after {gen.attempts} attempts. See PR body "
                    "for the validator errors."
                ),
            )

        if skip_tox:
            log.info("--skip-tox set; short-circuiting after first generate")
            outcome = AttemptOutcome(attempt=attempt_no, rockcraft_yaml=gen.rockcraft_yaml)
            attempts.append(outcome)
            return RunResult(
                ok=True, attempts=attempts, final_rockcraft_yaml=gen.rockcraft_yaml
            )

        log.info("running tox sanity pipeline in %s", work_dir)
        results = tox_mod.run_sanity_pipeline(work_dir, runner=runner)
        outcome = AttemptOutcome(
            attempt=attempt_no,
            rockcraft_yaml=gen.rockcraft_yaml,
            test_results=results,
        )
        attempts.append(outcome)

        if outcome.ok:
            log.info("sanity pipeline passed on attempt %d", attempt_no)
            return RunResult(
                ok=True, attempts=attempts, final_rockcraft_yaml=gen.rockcraft_yaml
            )

        failed = tox_mod.first_failure(results)
        assert failed is not None  # ok=False implies at least one failure
        log.warning(
            "sanity attempt %d failed at `tox -e %s` (rc=%d, timeout=%s)",
            attempt_no,
            failed.env,
            failed.returncode,
            failed.timed_out,
        )

    last_failed = tox_mod.first_failure(attempts[-1].test_results)
    last_env = last_failed.env if last_failed else "<unknown>"
    final_error = (
        f"sanity tests failed after {max_sanity_attempts} attempts; "
        f"last failing env: {last_env}"
    )
    # Even on failure, propagate the most recent attempt's YAML so callers
    # that want to open a best-effort PR have something to write to disk.
    last_yaml = attempts[-1].rockcraft_yaml if attempts else None
    return RunResult(
        ok=False,
        attempts=attempts,
        final_rockcraft_yaml=last_yaml,
        final_error=final_error,
    )


def _build_history_context(attempts: List[AttemptOutcome]) -> str:
    """Render prior sanity-test attempts as input for the next generate call.

    Each prior attempt contributes its produced rockcraft.yaml plus the
    first failing `tox -e <env>` (with returncode/timeout and log tail).
    The model receives every prior attempt — not just the last — so it can
    see the trajectory and avoid repeating fixes that already failed.
    Attempts with no recorded test failure are skipped (they shouldn't reach
    the outer-retry path anyway).
    """
    sections: List[str] = []
    for outcome in attempts:
        failed = tox_mod.first_failure(outcome.test_results)
        if failed is None:
            continue
        descriptor = (
            "timed out" if failed.timed_out else f"returncode {failed.returncode}"
        )
        sections.append(
            f"--- attempt {outcome.attempt} — `tox -e {failed.env}` "
            f"failed ({descriptor}) ---"
        )
        sections.append("rockcraft.yaml produced:")
        sections.append(outcome.rockcraft_yaml)
        sections.append("log tail:")
        sections.append(failed.log_tail)
    return "\n\n".join(sections)


def prepare_work_dir(rock_dir: Path, work_dir: Path) -> Path:
    """Copy the rock folder into `work_dir` for tox to chew on.

    Spec safety rail: the workflow always operates on a copy, never the
    user's checkout. Caller is responsible for managing the lifetime of
    `work_dir`.
    """
    if work_dir.exists():
        shutil.rmtree(work_dir)
    shutil.copytree(rock_dir, work_dir)
    return work_dir


_IGNORE_PATH_PREFIXES = (
    ".tox",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "venv",
    # rockcraft build trees produced when not running in managed (LXD) mode.
    "parts",
    "stage",
    "prime",
)

_IGNORE_GLOBS = (
    "*.rock",  # rockcraft pack output (also gitignored upstream)
)


def _is_build_artifact(rel_path: Path) -> bool:
    """True if `rel_path` is something tox / rockcraft / pytest produces.

    Matches a known directory name anywhere along the path (not just the
    root) so nested artefacts like `tests/__pycache__/foo.pyc` are caught.
    """
    from fnmatch import fnmatch

    if any(part in _IGNORE_PATH_PREFIXES for part in rel_path.parts):
        return True
    return any(fnmatch(rel_path.name, g) for g in _IGNORE_GLOBS)


def assert_only_rockcraft_changed(rock_dir: Path, work_dir: Path) -> None:
    """Defence in depth for spec §6.6: no file other than rockcraft.yaml differs.

    Walks both trees and compares file bytes. Raises BumpRockError on any
    drift outside rockcraft.yaml. Files produced by tox / rockcraft pack /
    pytest (see `_IGNORE_PATH_PREFIXES` and `_IGNORE_GLOBS`) are tolerated.
    """

    def relevant_files(root: Path):
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(root)
            if _is_build_artifact(rel):
                continue
            yield rel

    work_files = set(relevant_files(work_dir))
    src_files = set(relevant_files(rock_dir))

    for rel in work_files | src_files:
        if str(rel) == "rockcraft.yaml":
            continue
        a = rock_dir / rel
        b = work_dir / rel
        if not a.exists() or not b.exists():
            raise BumpRockError(
                f"unexpected file change during run: {rel} "
                f"({'added' if not a.exists() else 'removed'})"
            )
        if a.read_bytes() != b.read_bytes():
            raise BumpRockError(
                f"unexpected file modification during run: {rel} "
                "(only rockcraft.yaml may change)"
            )
