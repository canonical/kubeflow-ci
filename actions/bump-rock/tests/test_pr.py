# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Tests for PR metadata, branch naming, and the body template."""
from src import pr, repair, urls

OLD_REF = urls.UpstreamRef(
    org="kserve", repo="kserve", ref="v0.17.0", path="python/pmml.Dockerfile"
)
NEW_REF = urls.UpstreamRef(
    org="kserve", repo="kserve", ref="v0.18.0", path="python/pmml.Dockerfile"
)


def _result(ref, repaired_from=None):
    return repair.ValidationResult(ref=ref, ok=True, repaired_from=repaired_from)


def test_branch_name_basic():
    assert pr.branch_name("pmmlserver", "v0.18.0") == "bump/pmmlserver-v0.18.0"


def test_branch_name_with_suffix_unused_when_unique():
    name = pr.branch_name_with_suffix("pmmlserver", "v0.18.0", existing=["main"])
    assert name == "bump/pmmlserver-v0.18.0"


def test_branch_name_with_suffix_appends_timestamp_on_collision():
    name = pr.branch_name_with_suffix(
        "pmmlserver",
        "v0.18.0",
        existing=["main", "bump/pmmlserver-v0.18.0"],
    )
    assert name.startswith("bump/pmmlserver-v0.18.0-")
    suffix = name.removeprefix("bump/pmmlserver-v0.18.0-")
    assert suffix.isdigit()


def test_commit_message_and_pr_title_match():
    assert pr.commit_message("pmml", "v0.18.0") == "chore(pmml): bump to v0.18.0"
    assert pr.pr_title("pmml", "v0.18.0") == pr.commit_message("pmml", "v0.18.0")


def test_build_metadata_round_trip():
    md = pr.build_metadata(
        rock_name="pmmlserver",
        old_version="0.17.0",
        target_version="v0.18.0",
        resolved_pairs=[(_result(OLD_REF), _result(NEW_REF))],
        model="moonshotai/kimi-k2",
        attempts=1,
        sanity_envs_run=["pack", "sanity"],
        skip_tox=False,
    )
    assert md["rock_name"] == "pmmlserver"
    assert md["target_version"] == "v0.18.0"
    assert md["based_on"][0]["old_url"] == OLD_REF.blob_url()
    assert md["based_on"][0]["new_url"] == NEW_REF.blob_url()
    assert md["based_on"][0]["old_repaired_from"] is None
    assert md["based_on"][0]["new_repaired_from"] is None
    assert md["model"] == "moonshotai/kimi-k2"
    assert md["sanity_envs_run"] == ["pack", "sanity"]
    assert md["skip_tox"] is False


def test_build_metadata_captures_repair_history():
    broken_old = urls.UpstreamRef(
        org="kserve", repo="kserve", ref="v0.17.0", path="wrongdir/pmml.Dockerfile"
    )
    md = pr.build_metadata(
        rock_name="pmml",
        old_version="0.17.0",
        target_version="v0.18.0",
        resolved_pairs=[(_result(OLD_REF, repaired_from=broken_old), _result(NEW_REF))],
        model="x",
        attempts=1,
        sanity_envs_run=[],
        skip_tox=True,
    )
    assert md["based_on"][0]["old_repaired_from"] == broken_old.blob_url()
    assert md["based_on"][0]["new_repaired_from"] is None


def _happy_metadata(**overrides):
    md = pr.build_metadata(
        rock_name="pmmlserver",
        old_version="0.17.0",
        target_version="v0.18.0",
        resolved_pairs=[(_result(OLD_REF), _result(NEW_REF))],
        model="moonshotai/kimi-k2",
        attempts=2,
        sanity_envs_run=["pack", "export-to-docker", "sanity"],
        skip_tox=False,
    )
    md.update(overrides)
    return md


def test_pr_body_happy_path_has_no_follow_ups():
    body = pr.pr_body(_happy_metadata())
    assert "## Summary" in body
    assert "from `0.17.0` to upstream `v0.18.0`" in body
    assert OLD_REF.blob_url() in body
    assert NEW_REF.blob_url() in body
    assert "moonshotai/kimi-k2" in body
    assert "in 2 attempt(s)" in body
    assert "tox -e pack" in body
    assert "Reviewer follow-ups" not in body
    assert "AI-generated" in body
    assert body.endswith("\n")


def test_pr_body_skip_tox_notes_it():
    body = pr.pr_body(_happy_metadata(skip_tox=True, sanity_envs_run=[]))
    assert "Sanity tests were skipped" in body


def test_pr_body_sanity_failure_shows_warning_and_log_tail():
    md = _happy_metadata(
        sanity_ok=False,
        sanity_failure={
            "error": "sanity tests failed after 3 attempts; last failing env: pack",
            "attempts": [
                {
                    "attempt": 1,
                    "envs_run": ["pack"],
                    "failed_env": "pack",
                    "returncode": 1,
                    "timed_out": False,
                    "log_tail": "boom!\ntraceback line\n",
                }
            ],
        },
    )
    body = pr.pr_body(md)
    assert "Sanity tests did not pass" in body
    assert "draft" in body
    assert "## Sanity-test failure" in body
    assert "tox -e pack" in body
    assert "boom!" in body
    assert "traceback line" in body


def test_build_metadata_records_sanity_failure_payload():
    failure = {"error": "x", "attempts": []}
    md = pr.build_metadata(
        rock_name="pmml",
        old_version="0.17.0",
        target_version="v0.18.0",
        resolved_pairs=[(_result(OLD_REF), _result(NEW_REF))],
        model="x",
        attempts=3,
        sanity_envs_run=[],
        skip_tox=False,
        sanity_ok=False,
        sanity_failure=failure,
    )
    assert md["sanity_ok"] is False
    assert md["sanity_failure"] == failure


def test_pr_body_surfaces_repair_in_follow_ups():
    broken = urls.UpstreamRef(
        org="kserve", repo="kserve", ref="v0.17.0", path="wrongdir/pmml.Dockerfile"
    )
    md = pr.build_metadata(
        rock_name="pmmlserver",
        old_version="0.17.0",
        target_version="v0.18.0",
        resolved_pairs=[(_result(OLD_REF, repaired_from=broken), _result(NEW_REF))],
        model="x",
        attempts=1,
        sanity_envs_run=["pack", "sanity"],
        skip_tox=False,
    )
    body = pr.pr_body(md)
    assert "Reviewer follow-ups" in body
    assert broken.blob_url() in body
    assert OLD_REF.blob_url() in body
