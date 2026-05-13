# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Tests for the tox runner wrapper."""
import subprocess
from pathlib import Path
from unittest.mock import patch

from src import tox_runner


def test_tail_truncates():
    text = "\n".join(str(i) for i in range(500))
    tail = tox_runner._tail_text(text, max_lines=10)
    assert tail.splitlines() == [str(i) for i in range(490, 500)]


def test_subprocess_runner_success(tmp_path):
    fake = subprocess.CompletedProcess(
        args=["tox", "-e", "pack"], returncode=0, stdout="ok\n", stderr=""
    )
    with patch("subprocess.run", return_value=fake) as run_mock:
        result = tox_runner.SubprocessToxRunner().run(
            "pack", cwd=tmp_path, timeout=60
        )
    assert result.ok is True
    assert result.returncode == 0
    assert "ok" in result.log_tail
    assert run_mock.call_args.args[0] == ["tox", "-e", "pack"]
    assert run_mock.call_args.kwargs["cwd"] == str(tmp_path)
    assert run_mock.call_args.kwargs["timeout"] == 60


def test_subprocess_runner_nonzero(tmp_path):
    fake = subprocess.CompletedProcess(
        args=["tox", "-e", "sanity"], returncode=1, stdout="boom\n", stderr="err\n"
    )
    with patch("subprocess.run", return_value=fake):
        result = tox_runner.SubprocessToxRunner().run(
            "sanity", cwd=tmp_path, timeout=60
        )
    assert result.ok is False
    assert "boom" in result.log_tail
    assert "err" in result.log_tail


def test_subprocess_runner_timeout(tmp_path):
    exc = subprocess.TimeoutExpired(
        cmd="tox", timeout=1, output=b"partial\n", stderr=b""
    )
    with patch("subprocess.run", side_effect=exc):
        result = tox_runner.SubprocessToxRunner().run(
            "pack", cwd=tmp_path, timeout=1
        )
    assert result.ok is False
    assert result.timed_out is True
    assert "partial" in result.log_tail


class _StubRunner:
    """Minimal ToxRunner test double."""

    def __init__(self, outcomes):
        self.outcomes = outcomes
        self.calls = []

    def run(self, env, *, cwd, timeout):
        self.calls.append({"env": env, "cwd": cwd, "timeout": timeout})
        outcome = self.outcomes.pop(0)
        return tox_runner.TestResult(
            env=env,
            ok=outcome,
            returncode=0 if outcome else 1,
            log_tail="ok" if outcome else "fail",
        )


def test_run_sanity_pipeline_stops_on_first_failure(tmp_path):
    stub = _StubRunner([True, False])
    results = tox_runner.run_sanity_pipeline(tmp_path, runner=stub)
    assert [r.env for r in results] == ["pack", "export-to-docker"]
    assert [r.ok for r in results] == [True, False]


def test_run_sanity_pipeline_all_pass(tmp_path):
    stub = _StubRunner([True, True, True])
    results = tox_runner.run_sanity_pipeline(tmp_path, runner=stub)
    assert [r.env for r in results] == tox_runner.DEFAULT_SANITY_PIPELINE
    assert all(r.ok for r in results)


def test_first_failure_returns_first():
    results = [
        tox_runner.TestResult(env="pack", ok=True, returncode=0, log_tail=""),
        tox_runner.TestResult(env="sanity", ok=False, returncode=1, log_tail="x"),
    ]
    assert tox_runner.first_failure(results).env == "sanity"


def test_first_failure_returns_none_when_all_pass():
    results = [tox_runner.TestResult(env="pack", ok=True, returncode=0, log_tail="")]
    assert tox_runner.first_failure(results) is None
