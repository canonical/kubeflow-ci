from pathlib import Path
import pytest
from src.generate_and_compare import generate_and_compare_contributing, ResiduePlaceholdersError

EXPECTED_DIFFS = {
    "happy": [],  
    "missing_placeholders": ["- Some expected line", "+ Some generated line"],  
    "no_contrib": [
        "+ # Contributing",
        "+ ",
        "+ ## Overview",
        "+ ",
        "+ This document outlines the processes and practices recommended for contributing enhancements to test-charm.",
        "+ ",
        "+ ## Talk to us First",
        "+ ",
        "+ Before developing enhancements to this charm, you should [open an issue](/../../issues) explaining your use case. If you would like to chat with us about your use-cases or proposed implementation, you can reach us at [MLOps Mattermost public channel](https://chat.charmhub.io/charmhub/channels/mlops-documentation) or on [Discourse](https://discourse.charmhub.io/).",
        "+ ",
        "+ ## Pull Requests",
        "+ ",
        "+ Please help us out in ensuring easy to review branches by rebasing your pull request branch onto the `main` branch. This also avoids merge commits and creates a linear Git commit history.",
        "+ ",
        "+ All pull requests require review before being merged. Code review typically examines:",
        "+   - code quality",
        "+   - test coverage",
        "+   - user experience for Juju administrators of this charm.",
        "+ ",
        "+ ## Recommended Knowledge",
        "+ ",
        "+ Familiarising yourself with the [Charmed Operator Framework](https://juju.is/docs/sdk) library will help you a lot when working on new features or bug fixes.",
        "+ ",
        "+ ## Build Charm",
        "+ ",
        "+ To build test-charm run:",
        "+ ",
        "+ ```shell",
        "+ charmcraft pack",
        "+ ```",
        "+ ",
        "+ ## Developing",
        "+ ",
        "+ You can use the environments created by `tox` for development. For example, to load the `lint` environment into your shell, run:",
        "+ ",
        "+ ```shell",
        "+ tox --notest -e lint",
        "+ source .tox/lint/bin/activate",
        "+ ```",
        "+ ",
        "+ ### Testing",
        "+ ",
        "+ Use tox for testing. For example to test test, run:",
        "+ ",
        "+ ```shell",
        "+ tox -e test",
        "+ ```",
        "+ ",
        "+ See `tox.ini` for all available environments.",
        "+ ",
        "+ ### Deploy",
        "+ ",
        "+ ```bash",
        "+ # Create a model",
        "+ juju add-model dev",
        "+ # Enable DEBUG logging",
        "+ juju model-config logging-config=\"<root>=INFO;unit=DEBUG\"",
        "+ # Deploy the charm",
        "+ juju deploy ./test-charm_ubuntu-20.04-amd64.charm \\",
        "+   --resource oci-image=$(yq '.resources.\"oci-image\".\"upstream-source\"' metadata.yaml)",
        "+ ```",
        "+ ",
        "+ ## Updating the charm for new versions of the workload",
        "+ ",
        "+ To upgrade the source and resources of this charm, you must:",
        "+ ",
        "+ 1. Bump the `oci-image` in `metadata.yaml`",
        "+ 1. Update the charm source for any changes, such as:",
        "+     - YAML manifests in `src/` and/or any Kubernetes resource in `pod_spec` (UPDATED VALUE)",
        "+     - New or changed configurations passed to pebble workloads or through `pod.set_spec`",
        "+ 1. Ensure integration and unit tests are passing; fix/adapt them otherwise",
        "+ ",
        "+ ## Canonical Contributor Agreement",
        "+ ",
        "+ Canonical welcomes contributions to this charm. Please check out our [contributor agreement](https://ubuntu.com/legal/contributors) if you're interested in contributing.",
    ],
    "outdated": [
        "- ## Updating the charm for new versions of the workload",
        "- ",
        "- To upgrade the source and resources of this charm, you must:",
        "- ",
        "- 1. Bump the `oci-image` in `metadata.yaml`",
        "- 1. Update the charm source for any changes, such as:",
        "-     - YAML manifests in `src/` and/or any Kubernetes resource in `pod_spec`",
        "-     - New or changed configurations passed to pebble workloads or through `pod.set_spec`",
        "- 1. Ensure integration and unit tests are passing; fix/adapt them otherwise",
        "- ",
    ], 
}

@pytest.mark.parametrize(
    "charm_path, expected_diff",
    [
        ("./happy", EXPECTED_DIFFS["happy"]),
        ("./no_contrib", EXPECTED_DIFFS["no_contrib"]),
        ("./outdated", EXPECTED_DIFFS["outdated"]),
    ]
)
def test_generate_and_compare_contributing_diff(charm_path, expected_diff):
    temp_path = "temp"
    diff, _ = generate_and_compare_contributing(temp_path, charm_path)
    
    # Filter out lines that don't start with '+ ' or '- ' from the diff
    relevant_diff = [line for line in diff if line.startswith('+ ') or line.startswith('- ')]

    assert relevant_diff == expected_diff


def read_expected_contents(charm_path: str) -> str:
    """Read the expected contents of the contributing file from the expected file."""
    expected_file_path = Path(charm_path) / "contributing.md.expected"
    with open(expected_file_path, 'r') as f:
        return f.read()

@pytest.mark.parametrize(
    "charm_path",
    [
        "./happy",
        "./no_contrib",
        "./outdated",
    ]
)
def test_generate_and_compare_contributing_contents(charm_path):
    temp_path = "temp"
    _, generated_contents = generate_and_compare_contributing(temp_path, charm_path)
    
    expected_contents = read_expected_contents(charm_path)
    
    assert generated_contents == expected_contents

@pytest.mark.parametrize(
    "temp_path, charm_path, expected_error",
    [
        ("bad_temp", "happy", FileNotFoundError),
        ("temp", "missing_placeholders", ResiduePlaceholdersError),    
    ]
)
def test_generate_and_compare_contributing_failure(temp_path, charm_path, expected_error):
    with pytest.raises(expected_error):
        generate_and_compare_contributing(temp_path, charm_path)
