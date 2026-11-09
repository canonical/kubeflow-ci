# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Tests for the LLM generate stage (prompt, validators, retry cap)."""
from pathlib import Path

from src import generate, rockcraft
from src.fetch import DockerfilePair
from src.llm import MockClient
from src.urls import UpstreamRef

FIXTURES = Path(__file__).parent / "fixtures"

PMML_OLD = UpstreamRef(org="k", repo="k", ref="v0.17.0", path="python/pmml.Dockerfile")
PMML_NEW = UpstreamRef(org="k", repo="k", ref="v0.18.0", path="python/pmml.Dockerfile")


def _make_pair():
    return DockerfilePair(
        old_ref=PMML_OLD, new_ref=PMML_NEW, old_text="FROM old", new_text="FROM new"
    )


def _respond(new_yaml, notes=""):
    """Wrap `new_yaml` in the tagged response format, listing every changed line."""
    old = (FIXTURES / "happy" / "rockcraft.yaml").read_text().splitlines()
    new = new_yaml.splitlines()
    diff = [f"- {line}" for line in old if line not in new]
    diff += [f"+ {line}" for line in new if line not in old]
    return (
        "<change>\nreason: bump\n" + "\n".join(diff) + "\n</change>\n"
        f"{notes}<rockcraft_yaml>\n{new_yaml}</rockcraft_yaml>\n"
    )


def _bumped_yaml(version="0.18.0", ref_in_url="v0.18.0", name="pmmlserver"):
    """Build a bumped rockcraft.yaml that mirrors the happy fixture."""
    return (
        f"# Based on https://github.com/kserve/kserve/blob/{ref_in_url}/python/pmml.Dockerfile\n"
        "#\n"
        "# See ../CONTRIBUTING.md for more details about the patterns used in this rock.\n"
        f"name: {name}\n"
        "summary: Pmml server for Kserve deployments\n"
        "description: \"Kserve Pmml server\"\n"
        f"version: \"{version}\"\n"
        "license: Apache-2.0\n"
        "base: ubuntu@24.04\n"
        "platforms:\n"
        "    amd64:\n"
    )


def test_strip_fences_removes_yaml_block():
    text = "```yaml\nname: foo\nversion: 1\n```"
    assert generate.strip_fences(text) == "name: foo\nversion: 1\n"


def test_strip_fences_passes_through_plain_text():
    assert generate.strip_fences("name: foo\n") == "name: foo\n"


def test_strip_fences_restores_trailing_newline():
    assert generate.strip_fences("name: foo") == "name: foo\n"


def test_validate_output_happy():
    doc = rockcraft.load(FIXTURES / "happy")
    assert generate.validate_output(_bumped_yaml(), doc, "v0.18.0") == []


def test_validate_output_rejects_unchanged_version():
    doc = rockcraft.load(FIXTURES / "happy")
    bad = _bumped_yaml(version="0.17.0", ref_in_url="v0.17.0")
    errors = generate.validate_output(bad, doc, "v0.18.0")
    assert any("version" in e for e in errors)


def test_validate_output_rejects_changed_name():
    doc = rockcraft.load(FIXTURES / "happy")
    bad = _bumped_yaml(name="renamed")
    errors = generate.validate_output(bad, doc, "v0.18.0")
    assert any("name" in e for e in errors)


def test_validate_output_rejects_stale_based_on_url():
    doc = rockcraft.load(FIXTURES / "happy")
    bad = _bumped_yaml(version="0.18.0", ref_in_url="v0.17.0")
    errors = generate.validate_output(bad, doc, "v0.18.0")
    assert any("based on" in e.lower() for e in errors)


def test_validate_output_rejects_invalid_yaml():
    doc = rockcraft.load(FIXTURES / "happy")
    errors = generate.validate_output("not: valid: yaml:::", doc, "v0.18.0")
    assert len(errors) == 1


def test_generate_returns_first_good_response():
    doc = rockcraft.load(FIXTURES / "happy")
    note = '<reviewer_note kind="test_suggestion">\ncheck the new binary\n</reviewer_note>\n'
    client = MockClient(responses=[_respond(_bumped_yaml(), notes=note)])
    result = generate.generate(
        client=client, doc=doc, pairs=[_make_pair()], target_version="v0.18.0"
    )
    assert result.attempts == 1
    assert result.rockcraft_yaml == _bumped_yaml()
    assert result.changes[0].reason == "bump"
    assert result.reviewer_notes == [
        generate.ReviewerNote(kind="test_suggestion", detail="check the new binary")
    ]


def test_generate_retries_with_validation_errors():
    doc = rockcraft.load(FIXTURES / "happy")
    bad = _respond(_bumped_yaml(version="0.17.0", ref_in_url="v0.17.0"))
    good = _respond(_bumped_yaml())
    client = MockClient(responses=[bad, good])
    result = generate.generate(
        client=client, doc=doc, pairs=[_make_pair()], target_version="v0.18.0"
    )
    assert result.attempts == 2
    assert len(client.calls) == 2
    # second call must include the assistant turn + corrective user turn
    second = client.calls[1]["messages"]
    assert second[-2].role == "assistant"
    assert second[-1].role == "user"
    assert "failed validation" in second[-1].content


def test_generate_returns_invalid_result_after_retry_cap():
    """After total_attempts the call returns ok=False
    with the last candidate so callers can publish a best-effort PR."""
    doc = rockcraft.load(FIXTURES / "happy")
    bad = _respond(_bumped_yaml(version="0.17.0", ref_in_url="v0.17.0"))
    client = MockClient(responses=[bad, bad, bad])
    result = generate.generate(
        client=client,
        doc=doc,
        pairs=[_make_pair()],
        target_version="v0.18.0",
        max_retries=2,
    )
    assert result.ok is False
    assert result.attempts == 3
    assert "0.17.0" in result.rockcraft_yaml
    assert result.validator_errors
    assert len(client.calls) == 3


def test_build_user_prompt_includes_all_inputs():
    doc = rockcraft.load(FIXTURES / "happy")
    prompt = generate.build_user_prompt(doc, [_make_pair()], "v0.18.0")
    assert "Target version: v0.18.0" in prompt
    assert "current rockcraft.yaml" in prompt
    assert "FROM old" in prompt
    assert "FROM new" in prompt
    assert PMML_OLD.blob_url() in prompt
    assert PMML_NEW.blob_url() in prompt
    assert "upstream Dockerfile 1 diff (old -> new)" in prompt
    assert "-FROM old\n+FROM new" in prompt


def test_parse_response_splits_sections():
    text = (
        "<summary>\nUpstream now derives `ARGO_VERSION`.\n</summary>\n"
        "<change>\n"
        "reason: port the new build flag\n"
        "-   - cmake\n"
        "+   go build -trimpath\n"
        "</change>\n"
        '<reviewer_note kind="dropped_deviation">\n'
        "- ARGO_VERSION: v3.7.17\n"
        "</reviewer_note>\n"
        "<rockcraft_yaml>\n"
        "name: x\n"
        "# <change> inside the file is not a change block\n"
        "</rockcraft_yaml>\n"
    )
    parsed = generate.parse_response(text)
    assert parsed.errors == []
    assert parsed.summary == "Upstream now derives `ARGO_VERSION`."
    assert parsed.rockcraft_yaml == "name: x\n# <change> inside the file is not a change block\n"
    assert parsed.changes == [
        generate.Change(
            reason="port the new build flag",
            lines=["-   - cmake", "+   go build -trimpath"],
        )
    ]
    assert parsed.changes[0].removed == ["- cmake"]
    assert parsed.changes[0].added == ["go build -trimpath"]
    assert parsed.reviewer_notes == [
        generate.ReviewerNote(kind="dropped_deviation", detail="- ARGO_VERSION: v3.7.17")
    ]


def test_parse_response_requires_yaml_section():
    parsed = generate.parse_response("name: x\n")
    assert any("<rockcraft_yaml>" in e for e in parsed.errors)


def test_parse_response_rejects_bad_kind_and_missing_reason():
    text = (
        "<change>\n+ a\n</change>\n"
        '<reviewer_note kind="fyi">x</reviewer_note>\n'
        "<rockcraft_yaml>\na\n</rockcraft_yaml>"
    )
    errors = generate.parse_response(text).errors
    assert any("reason" in e for e in errors)
    assert any("'fyi'" in e for e in errors)


def test_validate_changes_accepts_fully_listed_diff():
    changes = [generate.Change(reason="r", lines=["- version: 1", "+ version: 2"])]
    assert generate.validate_changes("a\nversion: 1\n", "a\nversion: 2\n", changes) == []


def test_validate_changes_flags_unlisted_and_indentation_edits():
    errors = generate.validate_changes("a:\n  b: 1\nc: 1\n", "a:\n   b: 1\nc: 2\n", [])
    assert len(errors) == 1
    assert "not listed" in errors[0]
    for line in ("- b: 1", "+ b: 1", "- c: 1", "+ c: 2"):
        assert line in errors[0]


def test_validate_changes_flags_phantom_lines():
    changes = [generate.Change(reason="r", lines=["- c: 1", "+ c: 2", "+ d: 9"])]
    errors = generate.validate_changes("c: 1\n", "c: 2\n", changes)
    assert len(errors) == 1
    assert "+ d: 9" in errors[0]


def test_generate_retries_when_change_is_unlisted():
    doc = rockcraft.load(FIXTURES / "happy")
    sneaky = _respond(_bumped_yaml()).replace("license: Apache-2.0", "license: MIT")
    client = MockClient(responses=[sneaky, _respond(_bumped_yaml())])
    result = generate.generate(
        client=client, doc=doc, pairs=[_make_pair()], target_version="v0.18.0"
    )
    assert result.attempts == 2
    feedback = client.calls[1]["messages"][-1].content
    assert "not listed in any <change> block" in feedback
    assert "+ license: MIT" in feedback
