# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

from requests_mock.mocker import Mocker

from scripts.branch_creation import (
    DEFAULT_REPO_OWNER,
    GITHUB_API_URL,
    create_git_branch,
    get_latest_commit_sha,
    get_modified_releases_dirs,
    parse_yamls,
    trim_bundle_dict,
)


def test_get_modified_releases_dirs_only_include_files_in_releases_dir():
    file_paths = [
        "scripts/branch_creation.py",
        "scripts/tests/test_branch_creation.py",
        "scripts/tests/test_bundle.yaml",
        "tox.ini",
    ]
    result = get_modified_releases_dirs(file_paths)
    assert result == set()


def test_get_modified_releases_dirs_only_include_yaml_changes():
    file_paths = [
        "releases/1.3/charm.yaml",
        "releases/1.4/script.py",
    ]
    result = get_modified_releases_dirs(file_paths)
    assert result == set(["releases/1.3"])


def test_get_modified_releases_dirs_no_duplicates_in_return():
    file_paths = [
        "releases/1.4/charm.yaml",
        "releases/1.4/bundle.yaml",
        "releases/1.2/bundle.yaml",
    ]
    result = get_modified_releases_dirs(file_paths)
    assert result == set(["releases/1.4", "releases/1.2"])


def test_trim_bundle_dict_success():
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
    result = trim_bundle_dict(charmcraft_dict)
    assert result == {
        "admission-webhook": {
            "version": "1.4",
            "github_repo_name": "admission-webhook-operator",
        },
        "argo-controller": {"version": "3.1", "github_repo_name": "argo-operators"},
        "dex-auth": {"version": "2.28", "github_repo_name": "dex-auth-operator"},
    }


def test_trim_bundle_dict_no_github_repo_name():
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
    result = trim_bundle_dict(charmcraft_dict)
    assert result == {}


def test_trim_bundle_dict_latest_track():
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
    result = trim_bundle_dict(charmcraft_dict)
    assert result == {}


def test_trim_bundle_dict_input_missing_application_key(caplog):
    charmcraft_dict = {
        "bundle": "kubernetes",
        "name": "some-bundle",
    }
    trim_bundle_dict(charmcraft_dict)
    assert "Unexpecting yaml format." in caplog.text


def test_trim_bundle_dict_input_missing_charm_key(caplog):
    charmcraft_dict = {
        "bundle": "kubernetes",
        "name": "some-bundle",
        "applications": {"dex-app": {"scale": 1, "_github_repo_name": "dex-auth-operator"}},
    }
    trim_bundle_dict(charmcraft_dict)
    assert "Unexpecting yaml format." in caplog.text


def test_parse_yamls_success():
    result = parse_yamls("scripts/tests")
    assert result == {
        "spark-k8s": {"version": "3.1", "github_repo_name": "spark-operator"},
        "admission-webhook": {
            "version": "1.4",
            "github_repo_name": "admission-webhook-operator",
        },
        "argo-controller": {"version": "3.1", "github_repo_name": "argo-operators"},
        "dex-auth": {"version": "2.28", "github_repo_name": "dex-auth-operator"},
    }


def test_parse_yaml_fail(caplog):
    parse_yamls("./nonexistent_directory")
    assert "Cannot proceed with script. Failed to find directory" in caplog.text


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


def test_create_git_branch_missing_sha(mocker, caplog):
    github_repo_name = "some-repo"
    new_branch_name = "new-branch-name"
    mocked_get_latest_commit_sha = mocker.patch("scripts.branch_creation.get_latest_commit_sha")
    mocked_get_latest_commit_sha.return_value = ""
    create_git_branch(github_repo_name, new_branch_name)
    assert "Failed to get latest sha from branch main or master for repository" in caplog.text


def test_create_git_branch_branch_created_successfully(mocker, caplog, requests_mock):
    github_repo_name = "some-repo"
    new_branch_name = "new-branch-name"
    mocked_get_latest_commit_sha = mocker.patch("scripts.branch_creation.get_latest_commit_sha")
    mocked_get_latest_commit_sha.return_value = "some-commit-sha"
    requests_mock.post(
        f"{GITHUB_API_URL}/repos/{DEFAULT_REPO_OWNER}/{github_repo_name}/git/refs",
        json={
            "ref": "refs/heads/new-branch-name",
            "node_id": "REF_kwDOHFEUKrNyZWZzL2hlYWRzL2ZlYXR1cmVB",
            "url": "https://api.github.com/repos/canonical/test-repo-name/git/refs/heads/new-branch-name",
            "object": {
                "sha": "some-commit-sha",
                "type": "commit",
                "url": "https://api.github.com/repos/canonical/test-repo-name/git/commits/some-commit-sha",
            },
        },
        status_code=201,
    )
    create_git_branch(github_repo_name, new_branch_name)
    assert (
        f"Branch `{new_branch_name}` is successfully created for repository `{github_repo_name}`"
        in caplog.text
    )


def test_create_git_branch_branch_already_exists(mocker, caplog, requests_mock):
    github_repo_name = "some-repo"
    new_branch_name = "new-branch-name"
    mocked_get_latest_commit_sha = mocker.patch("scripts.branch_creation.get_latest_commit_sha")
    mocked_get_latest_commit_sha.return_value = "some-commit-sha"
    requests_mock.post(
        f"{GITHUB_API_URL}/repos/{DEFAULT_REPO_OWNER}/{github_repo_name}/git/refs",
        json={
            "message": "Git ref already exists",
            "documentation_url": "https://docs.github.com/rest/reference/git#create-a-reference",
        },
        status_code=422,
    )
    create_git_branch(github_repo_name, new_branch_name)
    assert (
        f"Branch `{new_branch_name}` already exists in repository `{github_repo_name}`"
        in caplog.text
    )


def test_create_git_branch_other_errors(mocker, caplog, requests_mock):
    github_repo_name = "some-repo"
    new_branch_name = "new-branch-name"
    mocked_get_latest_commit_sha = mocker.patch("scripts.branch_creation.get_latest_commit_sha")
    mocked_get_latest_commit_sha.return_value = "some-commit-sha"
    requests_mock.post(
        f"{GITHUB_API_URL}/repos/{DEFAULT_REPO_OWNER}/{github_repo_name}/git/refs",
        json={
            "message": "Not found",
            "documentation_url": "https://docs.github.com/rest/reference/git#create-a-reference",
        },
        status_code=404,
    )
    create_git_branch(github_repo_name, new_branch_name)
    assert "Something went wrong." in caplog.text
