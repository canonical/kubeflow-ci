import pytest
from requests_mock.mocker import Mocker
from scripts.branch_track_creation import *


def test_trim_charmcraft_dict_success():
    charmcraft_dict = {
        "bundle": "kubernetes",
        "name": "some-bundle",
        "applications": {
            "admission-webhook": {
                "charm": "admission-webhook",
                "channel": "1.4/stable",
                "scale": 1,
                "_github_repo_name": "admission-webhook-operator",
            },
            "argo-controller": {
                "charm": "argo-controller",
                "channel": "3.1/stable",
                "scale": 1,
                "_github_repo_name": "argo-operators",
            },
            "dex-auth": {
                "charm": "dex-auth",
                "channel": "2.28/stable",
                "scale": 1,
                "trust": True,
                "_github_repo_name": "dex-auth-operator",
            },
            "katib-db": {
                "charm": "charmed-osm-mariadb-k8s",
                "channel": "latest/stable",
                "scale": 1,
                "options": {"database": "katib"},
            },
        },
        "relations": [
            ["argo-controller", "dex-auth"],
            ["dex-auth", "admission-webhook"],
        ],
    }
    result = trim_charmcraft_dict(charmcraft_dict)
    assert result == {
        "admission-webhook": {
            "version": "1.4",
            "github_repo_name": "admission-webhook-operator",
        },
        "argo-controller": {"version": "3.1", "github_repo_name": "argo-operators"},
        "dex-auth": {"version": "2.28", "github_repo_name": "dex-auth-operator"},
    }


def test_trim_charmcraft_dict_no_github_repo_name():
    charmcraft_dict = {
        "bundle": "kubernetes",
        "name": "some-bundle",
        "applications": {
            "katib-db": {
                "charm": "charmed-osm-mariadb-k8s",
                "channel": "0.1/stable",
                "scale": 1,
                "options": {"database": "katib"},
            },
        },
        "relations": [
            ["argo-controller", "dex-auth"],
            ["dex-auth", "admission-webhook"],
        ],
    }
    result = trim_charmcraft_dict(charmcraft_dict)
    assert result == {}


def test_trim_charmcraft_dict_no_github_repo_name():
    charmcraft_dict = {
        "bundle": "kubernetes",
        "name": "some-bundle",
        "applications": {
            "minio": {
                "charm": "minio",
                "channel": "latest/stable",
                "scale": 1,
            },
        },
        "relations": [
            ["argo-controller", "dex-auth"],
            ["dex-auth", "admission-webhook"],
        ],
    }
    result = trim_charmcraft_dict(charmcraft_dict)
    assert result == {}


def test_trim_charmcraft_dict_input_missing_application_key():
    charmcraft_dict = {
        "bundle": "kubernetes",
        "name": "some-bundle",
    }
    with pytest.raises(Exception):
        trim_charmcraft_dict(charmcraft_dict)


def test_trim_charmcraft_dict_input_missing_charm_key():
    charmcraft_dict = {
        "bundle": "kubernetes",
        "name": "some-bundle",
        "applications": {
            "dex-app": {"scale": 1, "_github_repo_name": "dex-auth-operator"}
        },
    }
    with pytest.raises(Exception):
        trim_charmcraft_dict(charmcraft_dict)


def test_parse_yamls_success():
    result = parse_yamls("./tests")
    assert result == {
        "spark-k8s": {"version": "3.1", "github_repo_name": "spark-operator"},
        "admission-webhook": {
            "version": "1.4",
            "github_repo_name": "admission-webhook-operator",
        },
        "argo-controller": {"version": "3.1", "github_repo_name": "argo-operators"},
        "dex-auth": {"version": "2.28", "github_repo_name": "dex-auth-operator"},
    }


def test_parse_yaml_fail():
    with pytest.raises(Exception):
        parse_yamls("./nonexistent_directory")


def test_latest_commit_sha_repo_with_branch_main(requests_mock: Mocker):
    test_repo_name = "test-repo-name"
    requests_mock.get(
        f"{GITHUB_API_URL}/repos/{DEFAULT_REPO_OWNER}/{test_repo_name}/git/ref/heads/main",
        json={
            "ref": "refs/heads/master",
            "node_id": "REF_kwDOHFEUKrNyZWZzL2hlYWRzL2ZlYXR1cmVB",
            "url": "https://api.github.com/repos/canonical/test-repo-name/git/refs/heads/main",
            "object": {
                "sha": "2690d6ae5cfc14f85f254c1c1c88ceba243af1f9",
                "type": "commit",
                "url": "https://api.github.com/repos/canonical/test-repo-name/git/commits/2690d6ae5cfc14f85f254c1c1c88ceba243af1f9",
            },
        },
    )
    result = get_latest_commit_sha(test_repo_name)
    assert result == "2690d6ae5cfc14f85f254c1c1c88ceba243af1f9"


def test_latest_commit_sha_repo_with_branch_master(requests_mock: Mocker):
    test_repo_name = "test-repo-name"
    requests_mock.get(
        f"{GITHUB_API_URL}/repos/{DEFAULT_REPO_OWNER}/{test_repo_name}/git/ref/heads/main",
        json={
            "message": "Not Found",
            "documentation_url": "https://docs.github.com/rest/reference/git#get-a-reference",
        },
        status_code=404,
    )
    requests_mock.get(
        f"{GITHUB_API_URL}/repos/{DEFAULT_REPO_OWNER}/{test_repo_name}/git/ref/heads/master",
        json={
            "ref": "refs/heads/master",
            "node_id": "REF_kwDOHFEUKrNyZWZzL2hlYWRzL2ZlYXR1cmVB",
            "url": "https://api.github.com/repos/canonical/test-repo-name/git/refs/heads/master",
            "object": {
                "sha": "2690d6ae5cfc14f85f254c1c1c88ceba243af1f9",
                "type": "commit",
                "url": "https://api.github.com/repos/canonical/test-repo-name/git/commits/2690d6ae5cfc14f85f254c1c1c88ceba243af1f9",
            },
        },
    )
    result = get_latest_commit_sha(test_repo_name)
    assert result == "2690d6ae5cfc14f85f254c1c1c88ceba243af1f9"


def test_latest_commit_sha_repo_with_no_main_branches_found(requests_mock: Mocker):
    test_repo_name = "test-repo-name"
    requests_mock.get(
        f"{GITHUB_API_URL}/repos/{DEFAULT_REPO_OWNER}/{test_repo_name}/git/ref/heads/main",
        json={
            "message": "Not Found",
            "documentation_url": "https://docs.github.com/rest/reference/git#get-a-reference",
        },
        status_code=404,
    )
    requests_mock.get(
        f"{GITHUB_API_URL}/repos/{DEFAULT_REPO_OWNER}/{test_repo_name}/git/ref/heads/master",
        json={
            "message": "Not Found",
            "documentation_url": "https://docs.github.com/rest/reference/git#get-a-reference",
        },
        status_code=404,
    )

    result = get_latest_commit_sha(test_repo_name)
    assert result == ""
