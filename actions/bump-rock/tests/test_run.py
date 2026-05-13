# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Tests for the full pre-PR pipeline (generate + sanity, capped retry)."""
from pathlib import Path

import pytest

from src import rockcraft, run, tox_runner
from src.errors import BumpRockError
from src.fetch import DockerfilePair
from src.llm import MockClient
from src.urls import UpstreamRef

FIXTURES = Path(__file__).parent / "fixtures"

OLD = UpstreamRef(org="k", repo="k", ref="v0.17.0", path="python/pmml.Dockerfile")
NEW = UpstreamRef(org="k", repo="k", ref="v0.18.0", path="python/pmml.Dockerfile")
PAIR = DockerfilePair(old_ref=OLD, new_ref=NEW, old_text="FROM old", new_text="FROM new")


def _good_yaml(version="0.18.0", ref="v0.18.0"):
    return (
        f"# Based on https://github.com/kserve/kserve/blob/{ref}/python/pmml.Dockerfile\n"
        f"name: pmmlserver\n"
        f"summary: Pmml server for Kserve deployments\n"
        f"description: \"Kserve Pmml server\"\n"
        f"version: \"{version}\"\n"
        f"license: Apache-2.0\n"
        f"base: ubuntu@24.04\n"
        f"platforms:\n"
        f"    amd64:\n"
    )


class _SequenceRunner:
    """Stub ToxRunner that consumes a flat queue of per-invocation outcomes.

    `sequence` is the truth table the test wants exercised, in the same
    order tox envs are actually invoked. The sanity pipeline short-circuits
    on the first False, so the test must not enqueue outcomes that would
    never be consulted.
    """

    def __init__(self, sequence):
        self.sequence = list(sequence)
        self.invocations = 0
        self.envs_seen = []

    def run(self, env, *, cwd, timeout):
        self.envs_seen.append(env)
        ok = self.sequence.pop(0)
        self.invocations += 1
        return tox_runner.TestResult(
            env=env,
            ok=ok,
            returncode=0 if ok else 1,
            log_tail=f"{env}: {'ok' if ok else 'fail'}",
        )


def test_run_succeeds_on_first_attempt(tmp_path):
    doc = rockcraft.load(FIXTURES / "happy")
    client = MockClient(responses=[_good_yaml()])
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    stub = _SequenceRunner(sequence=[True, True, True])

    result = run.run(
        client=client,
        doc=doc,
        pairs=[PAIR],
        target_version="v0.18.0",
        work_dir=work_dir,
        runner=stub,
    )
    assert result.ok is True
    assert len(result.attempts) == 1
    assert (work_dir / "rockcraft.yaml").read_text() == _good_yaml()


def test_run_retries_on_pack_failure_then_succeeds(tmp_path):
    doc = rockcraft.load(FIXTURES / "happy")
    # attempt 1 fails at pack; attempt 2 passes everything.
    client = MockClient(responses=[_good_yaml(), _good_yaml()])
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    # attempt 1: pack fails (pipeline stops). attempt 2: all three pass.
    stub = _SequenceRunner(sequence=[False, True, True, True])

    result = run.run(
        client=client,
        doc=doc,
        pairs=[PAIR],
        target_version="v0.18.0",
        work_dir=work_dir,
        runner=stub,
    )
    assert result.ok is True
    assert len(result.attempts) == 2

    # Second LLM call must include the failure log as additional context.
    second_call = client.calls[1]["messages"][0].content
    assert "previous attempt failed sanity tests" in second_call
    assert "pack: fail" in second_call


def test_run_gives_up_after_max_attempts(tmp_path):
    doc = rockcraft.load(FIXTURES / "happy")
    client = MockClient(responses=[_good_yaml(), _good_yaml(), _good_yaml()])
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    # each attempt fails at pack -> 3 calls total before giving up.
    stub = _SequenceRunner(sequence=[False, False, False])

    result = run.run(
        client=client,
        doc=doc,
        pairs=[PAIR],
        target_version="v0.18.0",
        work_dir=work_dir,
        runner=stub,
    )
    assert result.ok is False
    assert len(result.attempts) == 3
    assert "after 3 attempts" in result.final_error


def test_run_skip_tox_short_circuits(tmp_path):
    doc = rockcraft.load(FIXTURES / "happy")
    client = MockClient(responses=[_good_yaml()])
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    stub = _SequenceRunner(sequence=[])  # should never be consulted

    result = run.run(
        client=client,
        doc=doc,
        pairs=[PAIR],
        target_version="v0.18.0",
        work_dir=work_dir,
        runner=stub,
        skip_tox=True,
    )
    assert result.ok is True
    assert stub.invocations == 0


def test_prepare_work_dir_copies_and_overwrites(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "rockcraft.yaml").write_text("name: pmml")
    (src / "tests").mkdir()
    (src / "tests" / "test_rock.py").write_text("assert True")

    work = tmp_path / "work"
    run.prepare_work_dir(src, work)
    assert (work / "rockcraft.yaml").read_text() == "name: pmml"
    assert (work / "tests" / "test_rock.py").exists()

    # Recreate to confirm it wipes pre-existing contents.
    (work / "stale.txt").write_text("x")
    run.prepare_work_dir(src, work)
    assert not (work / "stale.txt").exists()


def test_assert_only_rockcraft_changed_passes(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "rockcraft.yaml").write_text("old")
    (src / "tox.ini").write_text("ini")
    work = tmp_path / "work"
    run.prepare_work_dir(src, work)
    (work / "rockcraft.yaml").write_text("new")  # only this changes

    run.assert_only_rockcraft_changed(src, work)


def test_assert_only_rockcraft_changed_detects_other_edit(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "rockcraft.yaml").write_text("old")
    (src_dir / "tox.ini").write_text("ini")
    work = tmp_path / "work"
    run.prepare_work_dir(src_dir, work)
    (work / "tox.ini").write_text("modified")

    with pytest.raises(BumpRockError, match="tox.ini"):
        run.assert_only_rockcraft_changed(src_dir, work)


def test_assert_only_rockcraft_changed_tolerates_dot_tox(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "rockcraft.yaml").write_text("old")
    work = tmp_path / "work"
    run.prepare_work_dir(src, work)
    (work / ".tox").mkdir()
    (work / ".tox" / "stuff").write_text("build artifact")

    run.assert_only_rockcraft_changed(src, work)


def test_assert_only_rockcraft_changed_tolerates_rock_artifact(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "rockcraft.yaml").write_text("old")
    work = tmp_path / "work"
    run.prepare_work_dir(src, work)
    # Simulate `rockcraft pack` output.
    (work / "pmmlserver_0.18.0_amd64.rock").write_bytes(b"fake-oci-archive")

    run.assert_only_rockcraft_changed(src, work)
