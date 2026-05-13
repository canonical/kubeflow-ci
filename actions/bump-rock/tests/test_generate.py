# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Tests for the LLM generate stage (prompt, validators, retry cap)."""
from pathlib import Path

import pytest

from src import generate, rockcraft
from src.errors import BumpRockError
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


def _bumped_yaml(version="0.18.0", ref_in_url="v0.18.0", name="pmmlserver"):
    """Mirror the happy fixture exactly, only swapping the bump fields.

    Keeping byte-identity with the fixture is what lets the diff-tightness
    validator (spec §6.6) succeed on the "good" path.
    """
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


# --- diff-tightness validator (spec §6.6 + CI typo regression) -------------


_PMML_ORIGINAL_WITH_OVERRIDE = (
    "# Based on https://github.com/kserve/kserve/blob/v0.17.0/python/pmml.Dockerfile\n"
    "name: pmmlserver\n"
    'version: "0.17.0"\n'
    "base: ubuntu@24.04\n"
    "platforms:\n"
    "    amd64:\n"
    "parts:\n"
    "  python:\n"
    "    plugin: nil\n"
    "    source-tag: v0.17.0\n"
    "    override-build: |\n"
    "      mkdir -p $CRAFT_PART_INSTALL/usr/bin/\n"
    "      ln -s /usr/bin/python3.12 $CRAFT_PART_INSTALL/usr/bin/python\n"
)


def _bump_pmml(*, version_field='"0.18.0"', ref="v0.18.0", overrides=""):
    return (
        f"# Based on https://github.com/kserve/kserve/blob/{ref}/python/pmml.Dockerfile\n"
        "name: pmmlserver\n"
        f"version: {version_field}\n"
        "base: ubuntu@24.04\n"
        "platforms:\n"
        "    amd64:\n"
        "parts:\n"
        "  python:\n"
        "    plugin: nil\n"
        f"    source-tag: {ref}\n"
        "    override-build: |\n"
        + (
            overrides
            or "      mkdir -p $CRAFT_PART_INSTALL/usr/bin/\n"
              "      ln -s /usr/bin/python3.12 $CRAFT_PART_INSTALL/usr/bin/python\n"
        )
    )


def _doc_with(text):
    return rockcraft.RockcraftDoc(
        path=Path("/tmp/rockcraft.yaml"),
        name="pmmlserver",
        version="0.17.0",
        based_on_urls=[
            "https://github.com/kserve/kserve/blob/v0.17.0/python/pmml.Dockerfile"
        ],
        raw_text=text,
    )


def test_diff_validator_accepts_pure_version_bump():
    doc = _doc_with(_PMML_ORIGINAL_WITH_OVERRIDE)
    new = _bump_pmml()
    assert generate.validate_output(new, doc, "v0.18.0") == []


def test_diff_validator_catches_cra_part_install_typo():
    """Regression: the exact typo seen in attempt-1 of the failed CI run."""
    doc = _doc_with(_PMML_ORIGINAL_WITH_OVERRIDE)
    typo_overrides = (
        "      mkdir -p $CRA_PART_INSTALL/usr/bin/\n"
        "      ln -s /usr/bin/python3.12 $CRAFT_PART_INSTALL/usr/bin/python\n"
    )
    new = _bump_pmml(overrides=typo_overrides)
    errors = generate.validate_output(new, doc, "v0.18.0")
    assert any("diverges from the original" in e for e in errors)
    assert any("CRA_PART_INSTALL" in e for e in errors)


def test_diff_validator_catches_duplicated_yaml_key():
    """Regression: the `plugin plugin:` typo seen in attempt-3."""
    doc = _doc_with(_PMML_ORIGINAL_WITH_OVERRIDE)
    # Inject the typo by replacing `plugin:` in the bumped output.
    new = _bump_pmml().replace("plugin: nil", "plugin plugin: nil")
    errors = generate.validate_output(new, doc, "v0.18.0")
    assert any("diverges from the original" in e for e in errors)


def test_diff_validator_safe_change_lines_recognised():
    safe_minus = "-version: \"0.17.0\""
    safe_plus = "+version: \"0.18.0\""
    assert generate._is_safe_change_line(safe_minus)
    assert generate._is_safe_change_line(safe_plus)
    assert generate._is_safe_change_line("-    source-tag: v0.17.0")
    assert generate._is_safe_change_line(
        "-# Based on https://github.com/k/k/blob/v0.17.0/d"
    )
    assert not generate._is_safe_change_line(
        "-      mkdir -p $CRA_PART_INSTALL/usr/bin/"
    )


def test_generate_returns_first_good_response():
    doc = rockcraft.load(FIXTURES / "happy")
    client = MockClient(responses=[_bumped_yaml()])
    result = generate.generate(
        client=client, doc=doc, pairs=[_make_pair()], target_version="v0.18.0"
    )
    assert result.attempts == 1
    assert "version: \"0.18.0\"" in result.rockcraft_yaml


def test_generate_retries_with_validation_errors():
    doc = rockcraft.load(FIXTURES / "happy")
    bad = _bumped_yaml(version="0.17.0", ref_in_url="v0.17.0")
    good = _bumped_yaml()
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


def test_generate_raises_after_retry_cap():
    doc = rockcraft.load(FIXTURES / "happy")
    bad = _bumped_yaml(version="0.17.0", ref_in_url="v0.17.0")
    client = MockClient(responses=[bad, bad, bad])
    with pytest.raises(BumpRockError, match="after 3 attempts"):
        generate.generate(
            client=client,
            doc=doc,
            pairs=[_make_pair()],
            target_version="v0.18.0",
            max_retries=2,
        )
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
