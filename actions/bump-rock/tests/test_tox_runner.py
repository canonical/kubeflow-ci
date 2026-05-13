# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Tests for the tox runner wrapper."""
import io
from pathlib import Path
from unittest.mock import MagicMock, patch

from src import tox_runner


def test_tail_truncates():
    text = "\n".join(str(i) for i in range(500))
    tail = tox_runner._tail_text(text, max_lines=10)
    assert tail.splitlines() == [str(i) for i in range(490, 500)]


def _fake_popen(lines, returncode=0):
    """Build a Popen-like mock whose .stdout iterates `lines`."""
    proc = MagicMock()
    proc.stdout = iter(lines)
    proc.returncode = returncode
    proc.wait = MagicMock(return_value=returncode)
    proc.kill = MagicMock()
    return proc


def test_subprocess_runner_success(tmp_path):
    proc = _fake_popen(["building...\n", "ok\n"], returncode=0)
    with patch("subprocess.Popen", return_value=proc) as popen_mock:
        result = tox_runner.SubprocessToxRunner().run(
            "pack", cwd=tmp_path, timeout=60
        )
    assert result.ok is True
    assert result.returncode == 0
    assert "ok" in result.log_tail
    assert "building..." in result.log_tail
    args = popen_mock.call_args.args[0]
    assert args == ["tox", "-e", "pack"]
    assert popen_mock.call_args.kwargs["cwd"] == str(tmp_path)


def test_subprocess_runner_nonzero(tmp_path):
    proc = _fake_popen(["boom\n", "err\n"], returncode=1)
    with patch("subprocess.Popen", return_value=proc):
        result = tox_runner.SubprocessToxRunner().run(
            "sanity", cwd=tmp_path, timeout=60
        )
    assert result.ok is False
    assert result.returncode == 1
    assert "boom" in result.log_tail
    assert "err" in result.log_tail


def test_subprocess_runner_streams_to_stderr(tmp_path, capsys):
    proc = _fake_popen(["line-one\n", "line-two\n"], returncode=0)
    with patch("subprocess.Popen", return_value=proc):
        tox_runner.SubprocessToxRunner().run("pack", cwd=tmp_path, timeout=60)
    captured = capsys.readouterr()
    assert "[tox -e pack] line-one" in captured.err
    assert "[tox -e pack] line-two" in captured.err


def test_subprocess_runner_timeout(tmp_path):
    # Iterator yields one line then we patch time.monotonic to claim the
    # timeout has been exceeded so the runner kills the process.
    proc = _fake_popen(["slow...\n"] * 5, returncode=0)
    times = iter([0.0, 0.5, 999.0, 999.5, 1000.0, 1000.5, 1001.0, 1001.5])
    with patch("subprocess.Popen", return_value=proc), patch(
        "src.tox_runner.time.monotonic", side_effect=lambda: next(times)
    ):
        result = tox_runner.SubprocessToxRunner().run(
            "pack", cwd=tmp_path, timeout=1
        )
    assert result.ok is False
    assert result.timed_out is True
    assert "slow" in result.log_tail
    proc.kill.assert_called()


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
