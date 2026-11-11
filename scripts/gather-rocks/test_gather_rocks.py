# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Unit tests for gather_rocks.py."""

import io
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import gather_rocks
import pytest
import requests
from gather_rocks import (
    DockerHubClient,
    OciRegistryClient,
    OutputFormat,
    RegistryChecker,
    RepositoryContext,
    RepositoryInfo,
    Rock,
    find_rock_dirs,
    get_file_paths,
    get_repositories,
    inspect_rock,
    resolve_registry,
    split_registry,
    tag_matches_version,
    write_output,
)
from github.GithubException import GithubException, UnknownObjectException

INFO = RepositoryInfo("canonical/foo-rocks", "canonical", "main")


def make_response(status: int, body=None, headers: dict | None = None) -> requests.Response:
    """Return a real response object, so that `.ok`, `.links` and `.raise_for_status()` work."""
    response = requests.Response()
    response.status_code = status
    response._content = json.dumps(body).encode() if body is not None else b""
    response.headers.update(headers or {})
    response.url = "https://registry.example"
    return response


def make_repository(full_name: str, archived: bool = False) -> MagicMock:
    """Return a mocked PyGithub repository."""
    repository = MagicMock(full_name=full_name, archived=archived, default_branch="main")
    repository.owner.login = full_name.split("/")[0]
    return repository


def make_context(**attributes) -> SimpleNamespace:
    """Return a repository context with no registry information, unless given."""
    defaults = {
        "info": INFO,
        "paths": set(),
        "uses_k8s_workflows": False,
        "repository_variable": None,
        "organization_variable": None,
        "read_yaml": MagicMock(return_value={}),
    }
    return SimpleNamespace(**(defaults | attributes))


# Tags and registries


@pytest.mark.parametrize(
    "tag, version, expected",
    [
        ("1.0", "1.0", True),
        ("1.0-abc1234", "1.0", True),
        ("1.0-abc1234-20260101000000", "1.0", True),
        ("1.0.1", "1.0", False),
        ("1.01", "1.0", False),
        # A `v` in front of the version number is ignored on both sides
        ("2.6.2-3f1565f", "v2.6.2", True),
        ("v2.6.2-3f1565f", "2.6.2", True),
        ("v2.6.2-3f1565f", "v2.6.2", True),
        # but only in front of a number
        ("llm-1.0", "vllm-1.0", False),
        ("vllm-1.0-abc1234", "vllm-1.0", True),
    ],
)
def test_tag_matches_version(tag, version, expected):
    assert tag_matches_version(tag, version) is expected


@pytest.mark.parametrize(
    "tags, expected",
    [
        # The build timestamp wins over the commit, and over tags without a timestamp
        (
            ["1.0-ffff-20260101000000", "1.0-aaaa-20261101000000", "1.0-zzzz", "1.0"],
            "1.0-aaaa-20261101000000",
        ),
        # Numbers are compared naturally
        (["1.0-ck8", "1.0-ck10", "1.0-ck9"], "1.0-ck10"),
        ([], None),
        (None, None),
    ],
)
def test_latest_tag(tags, expected):
    rock = Rock("canonical/foo-rocks", "main", "foo", tags=tags)
    assert rock.latest_tag == expected


@pytest.mark.parametrize(
    "registry, expected",
    [
        ("docker.io/charmedkubeflow", ("docker.io", "charmedkubeflow")),
        ("charmedkubeflow", ("docker.io", "charmedkubeflow")),
        ("ghcr.io/canonical/", ("ghcr.io", "canonical")),
        ("localhost:5000/team/project", ("localhost:5000", "team/project")),
    ],
)
def test_split_registry(registry, expected):
    assert split_registry(registry) == expected


# GitHub


def test_get_repositories_of_team_skips_archived_repositories():
    github = MagicMock()
    team = github.get_organization.return_value.get_team_by_slug.return_value
    team.get_repos.return_value = [
        make_repository("canonical/b-rocks"),
        make_repository("canonical/old-rocks", archived=True),
        make_repository("canonical/a-rocks"),
    ]

    repositories = get_repositories(github, "canonical/mlops", include_archived=False)

    github.get_organization.assert_called_once_with("canonical")
    github.get_organization.return_value.get_team_by_slug.assert_called_once_with("mlops")
    assert repositories == [
        RepositoryInfo("canonical/a-rocks", "canonical", "main"),
        RepositoryInfo("canonical/b-rocks", "canonical", "main"),
    ]


def test_get_repositories_includes_archived_repositories():
    github = MagicMock()
    github.get_user.return_value.type = "User"
    github.get_user.return_value.get_repos.return_value = [
        make_repository("someone/old-rocks", archived=True)
    ]

    repositories = get_repositories(github, "someone", include_archived=True)

    github.get_user.return_value.get_repos.assert_called_once_with(type="owner")
    assert [repository.full_name for repository in repositories] == ["someone/old-rocks"]


def test_get_repositories_of_organization():
    github = MagicMock()
    github.get_user.return_value.type = "Organization"
    github.get_organization.return_value.get_repos.return_value = [
        make_repository("canonical/a-rocks")
    ]

    repositories = get_repositories(github, "canonical", include_archived=False)

    github.get_organization.return_value.get_repos.assert_called_once_with(type="all")
    assert [repository.full_name for repository in repositories] == ["canonical/a-rocks"]


def test_get_file_paths_returns_only_files():
    repository = MagicMock()
    repository.get_git_tree.return_value.truncated = False
    repository.get_git_tree.return_value.tree = [
        SimpleNamespace(path="foo", type="tree"),
        SimpleNamespace(path="foo/rockcraft.yaml", type="blob"),
    ]

    assert get_file_paths(repository, INFO) == ["foo/rockcraft.yaml"]
    repository.get_git_tree.assert_called_once_with("main", recursive=True)


def test_get_file_paths_of_empty_repository():
    repository = MagicMock()
    repository.get_git_tree.side_effect = GithubException(409, {"message": "empty"}, {})
    assert get_file_paths(repository, INFO) == []


def test_get_file_paths_raises_other_errors():
    repository = MagicMock()
    repository.get_git_tree.side_effect = GithubException(403, {"message": "forbidden"}, {})
    with pytest.raises(GithubException):
        get_file_paths(repository, INFO)


def test_find_rock_dirs():
    paths = [
        "rockcraft.yaml",
        "b/rockcraft.yaml",
        "a/nested/rockcraft.yaml",
        "a/rock-ci-metadata.yaml",
        "c/rockcraft.yaml.bak",
        "d/my-rockcraft.yaml",
    ]
    assert find_rock_dirs(paths) == [".", "a/nested", "b"]


def make_repository_context(files: dict[str, str]) -> RepositoryContext:
    """Return a context for a repository with the given files and their content."""
    repository = MagicMock()
    repository.url = "/repos/canonical/foo-rocks"
    repository.get_contents.side_effect = lambda path, ref: SimpleNamespace(
        decoded_content=files[path].encode()
    )
    return RepositoryContext(MagicMock(), repository, INFO, list(files))


def test_read_yaml_keeps_values_as_strings():
    context = make_repository_context({"rockcraft.yaml": "name: foo\nversion: 1.10\n"})
    assert context.read_yaml("rockcraft.yaml") == {"name": "foo", "version": "1.10"}


@pytest.mark.parametrize(
    "workflow, expected",
    [
        ("uses: canonical/k8s-workflows/.github/workflows/build_rocks.yaml@abc", True),
        ("uses: canonical/charmed-kubeflow-workflows/.github/workflows/x.yaml@main", False),
    ],
)
def test_uses_k8s_workflows(workflow, expected):
    context = make_repository_context(
        {".github/workflows/push.yaml": "on: push", ".github/workflows/pr.yml": workflow}
    )
    assert context.uses_k8s_workflows is expected


def test_repository_variable():
    context = make_repository_context({})
    context.repository.get_variable.return_value.value = "ghcr.io/canonical"

    assert context.repository_variable == "ghcr.io/canonical"
    context.repository.get_variable.assert_called_once_with("ROCK_IMAGE_REGISTRY")


@pytest.mark.parametrize(
    "error",
    [
        UnknownObjectException(404, {"message": "Not Found"}, {}),
        GithubException(403, {"message": "Must have admin rights"}, {}),
    ],
)
def test_repository_variable_missing_or_forbidden(error):
    context = make_repository_context({})
    context.repository.get_variable.side_effect = error
    assert context.repository_variable is None


def test_organization_variable_is_paginated():
    context = make_repository_context({})
    other = {"name": "OTHER", "value": "x"}
    registry = {"name": "ROCK_IMAGE_REGISTRY", "value": "docker.io/org"}
    context.github.requester.requestJsonAndCheck.side_effect = [
        ({}, {"total_count": 101, "variables": [other] * 100}),
        ({}, {"total_count": 101, "variables": [registry]}),
    ]

    assert context.organization_variable == "docker.io/org"
    assert context.github.requester.requestJsonAndCheck.call_count == 2


@pytest.mark.parametrize(
    "context_attributes, expected",
    [
        # The k8s-workflows ignore the variables and rock-ci-metadata.yaml
        (
            {"uses_k8s_workflows": True, "repository_variable": "docker.io/x"},
            "ghcr.io/canonical",
        ),
        (
            {
                "paths": {"foo/rock-ci-metadata.yaml"},
                "read_yaml": MagicMock(return_value={"registry": "ghcr.io/foo"}),
                "repository_variable": "docker.io/x",
            },
            "ghcr.io/foo",
        ),
        # A rock-ci-metadata.yaml without a registry falls back to the variables
        (
            {
                "paths": {"foo/rock-ci-metadata.yaml"},
                "read_yaml": MagicMock(return_value={"integrations": []}),
                "repository_variable": "docker.io/x",
            },
            "docker.io/x",
        ),
        (
            {"repository_variable": "docker.io/x", "organization_variable": "docker.io/y"},
            "docker.io/x",
        ),
        ({"organization_variable": "docker.io/y"}, "docker.io/y"),
        ({}, "docker.io/default"),
    ],
)
def test_resolve_registry(context_attributes, expected):
    context = make_context(**context_attributes)
    assert resolve_registry(context, "foo", "docker.io/default") == expected


def test_resolve_registry_reads_metadata_of_the_rock():
    context = make_context(
        paths={"rock-ci-metadata.yaml", "foo/rockcraft.yaml"},
        read_yaml=MagicMock(return_value={"registry": "ghcr.io/foo"}),
    )

    # The metadata at the root belongs to the rock at the root, not to the one in `foo`
    assert resolve_registry(context, "foo", "docker.io/default") == "docker.io/default"
    assert resolve_registry(context, ".", "docker.io/default") == "ghcr.io/foo"
    context.read_yaml.assert_called_once_with("rock-ci-metadata.yaml")


def test_inspect_rock():
    context = make_repository_context({"foo/rockcraft.yaml": "name: foo\nversion: '1.0'\n"})
    context.repository.get_variable.return_value.value = "docker.io/charmedkubeflow"

    rock = inspect_rock(context, "foo", "docker.io/default")

    assert rock == Rock(
        "canonical/foo-rocks",
        "main",
        "foo",
        name="foo",
        version="1.0",
        registry="docker.io/charmedkubeflow",
    )
    assert rock.image == "docker.io/charmedkubeflow/foo"


def test_inspect_rock_without_version():
    context = make_repository_context({"foo/rockcraft.yaml": "name: foo\n"})
    rock = inspect_rock(context, "foo", "docker.io/default")
    assert rock.error == "rockcraft.yaml has no name or version"
    assert rock.registry is None


def test_inspect_rock_with_github_error():
    context = make_repository_context({})
    context.repository.get_contents.side_effect = GithubException(500, {"message": "oops"}, {})
    rock = inspect_rock(context, "foo", "docker.io/default")
    assert rock.error == "GitHub error 500 oops"


# Registries


@pytest.mark.parametrize("status, expected", [(200, True), (404, False)])
def test_docker_hub_exists(status, expected):
    session = MagicMock()
    session.get.return_value = make_response(status, {})

    assert DockerHubClient(session).exists("charmedkubeflow", "foo") is expected
    assert session.get.call_args.args[0].endswith("/namespaces/charmedkubeflow/repositories/foo")


def test_docker_hub_exists_raises_other_errors():
    session = MagicMock()
    session.get.return_value = make_response(500, {})
    with pytest.raises(requests.HTTPError):
        DockerHubClient(session).exists("charmedkubeflow", "foo")


def test_docker_hub_tags_are_paginated():
    session = MagicMock()
    session.get.side_effect = [
        make_response(200, {"next": "https://hub/page2", "results": [{"name": "1.0-a"}]}),
        make_response(200, {"next": None, "results": [{"name": "1.0-b"}]}),
    ]

    assert DockerHubClient(session).tags("charmedkubeflow", "foo", "1.0") == ["1.0-a", "1.0-b"]
    first, second = session.get.call_args_list
    assert first.kwargs["params"] == {"page_size": 100, "name": "1.0"}
    assert second.args == ("https://hub/page2",)
    assert second.kwargs["params"] is None


def test_docker_hub_tags_of_missing_image():
    session = MagicMock()
    session.get.return_value = make_response(404, {})
    assert DockerHubClient(session).tags("charmedkubeflow", "foo", "1.0") is None


def test_oci_registry_fetches_anonymous_token_and_follows_pages():
    challenge = 'Bearer realm="https://ghcr.io/token",service="ghcr.io",scope="x"'
    session = MagicMock()
    session.get.side_effect = [
        make_response(401, {}, {"WWW-Authenticate": challenge}),
        make_response(200, {"token": "secret"}),
        make_response(
            200,
            {"tags": ["1.0-a"]},
            {"Link": '</v2/canonical/foo/tags/list?last=1.0-a&n=1000>; rel="next"'},
        ),
        make_response(200, {"tags": ["1.0-b"]}),
    ]
    client = OciRegistryClient(session, "ghcr.io")

    assert client.tags("canonical", "foo", "1.0") == ["1.0-a", "1.0-b"]

    unauthenticated, token, first_page, second_page = session.get.call_args_list
    assert unauthenticated.kwargs["headers"] == {}
    assert token.args == ("https://ghcr.io/token",)
    assert token.kwargs["params"] == {
        "service": "ghcr.io",
        "scope": "repository:canonical/foo:pull",
    }
    assert first_page.kwargs["headers"] == {"Authorization": "Bearer secret"}
    assert second_page.args == ("https://ghcr.io/v2/canonical/foo/tags/list?last=1.0-a&n=1000",)
    assert second_page.kwargs["headers"] == {"Authorization": "Bearer secret"}


def test_oci_registry_missing_image():
    challenge = 'Bearer realm="https://ghcr.io/token",service="ghcr.io"'
    session = MagicMock()
    session.get.side_effect = [
        make_response(401, {}, {"WWW-Authenticate": challenge}),
        make_response(403, {}),  # The registry refuses a token for a missing image
        make_response(404, {"errors": [{"code": "NAME_UNKNOWN"}]}),
    ]

    assert OciRegistryClient(session, "ghcr.io").exists("canonical", "foo") is False


def test_registry_checker_uses_client_per_host():
    checker = RegistryChecker(MagicMock())
    assert isinstance(checker.client("docker.io"), DockerHubClient)
    assert isinstance(checker.client("ghcr.io"), OciRegistryClient)
    assert checker.client("ghcr.io") is checker.client("ghcr.io")


def make_checked_rock(registry: str = "ghcr.io/canonical") -> Rock:
    """Return a rock that is ready to be checked."""
    return Rock("canonical/foo-rocks", "main", "foo", "foo", "1.0", registry)


@pytest.mark.parametrize("exists, error", [(True, None), (False, gather_rocks.IMAGE_NOT_FOUND)])
def test_registry_checker_skip_tags(exists, error):
    checker = RegistryChecker(MagicMock())
    client = MagicMock()
    client.exists.return_value = exists
    checker._clients["ghcr.io"] = client
    rock = make_checked_rock()

    checker.check(rock, skip_tags=True)

    assert rock.error == error
    assert rock.tags is None
    client.exists.assert_called_once_with("canonical", "foo")
    client.tags.assert_not_called()


def test_registry_checker_gathers_matching_tags_without_checking_existence():
    checker = RegistryChecker(MagicMock())
    client = MagicMock()
    client.tags.return_value = ["1.0-b-20260201000000", "2.0-a", "1.0-a-20260101000000"]
    checker._clients["ghcr.io"] = client
    rock = make_checked_rock()

    checker.check(rock, skip_tags=False)

    assert rock.error is None
    assert rock.tags == ["1.0-a-20260101000000", "1.0-b-20260201000000"]
    client.exists.assert_not_called()


def test_registry_checker_ignores_v_prefix_of_version():
    checker = RegistryChecker(MagicMock())
    client = MagicMock(**{"tags.return_value": ["2.6.2-3f1565f", "2.13.0-941be9a"]})
    checker._clients["docker.io"] = client
    rock = Rock("canonical/kserve-rocks", "main", "tf", "tf", "v2.6.2", "docker.io/x")

    checker.check(rock, skip_tags=False)

    client.tags.assert_called_once_with("x", "tf", "2.6.2")
    assert rock.tags == ["2.6.2-3f1565f"]
    assert rock.error is None


def test_registry_checker_no_tag_for_version():
    checker = RegistryChecker(MagicMock())
    checker._clients["ghcr.io"] = MagicMock(**{"tags.return_value": ["2.0-a"]})
    rock = make_checked_rock()

    checker.check(rock, skip_tags=False)

    assert rock.error == "No tag for version 1.0"
    assert rock.tags == []


def test_registry_checker_missing_image():
    checker = RegistryChecker(MagicMock())
    checker._clients["ghcr.io"] = MagicMock(**{"tags.return_value": None})
    rock = make_checked_rock()

    checker.check(rock, skip_tags=False)

    assert rock.error == gather_rocks.IMAGE_NOT_FOUND
    assert rock.tags is None


def test_registry_checker_records_errors():
    checker = RegistryChecker(MagicMock())
    checker._clients["ghcr.io"] = MagicMock(
        **{"tags.side_effect": requests.ConnectionError("down")}
    )
    rock = make_checked_rock()

    checker.check(rock, skip_tags=False)

    assert rock.error == "Registry error: down"


# Output


def make_full_rock() -> Rock:
    """Return a rock that has been inspected and checked."""
    return Rock(
        "canonical/foo-rocks",
        "main",
        "foo",
        "foo",
        "1.0",
        "ghcr.io/canonical",
        tags=["1.0-a", "1.0-b"],
    )


def test_write_json_includes_tags():
    stream = io.StringIO()
    write_output([make_full_rock()], OutputFormat.JSON, skip_tags=False, stream=stream)

    [record] = json.loads(stream.getvalue())
    assert record["image"] == "ghcr.io/canonical/foo"
    assert record["tag_count"] == 2
    assert record["latest_tag"] == "1.0-b"
    assert record["tags"] == ["1.0-a", "1.0-b"]


def test_write_json_without_tags():
    stream = io.StringIO()
    write_output([make_full_rock()], OutputFormat.JSON, skip_tags=True, stream=stream)

    [record] = json.loads(stream.getvalue())
    assert not {"tag_count", "latest_tag", "tags"} & record.keys()


def test_write_yaml():
    stream = io.StringIO()
    write_output([make_full_rock()], OutputFormat.YAML, skip_tags=False, stream=stream)
    assert "image: ghcr.io/canonical/foo\n" in stream.getvalue()


def test_write_simple():
    without_tags = Rock("canonical/bar-rocks", "main", "bar", "bar", "2.0", "docker.io/x", tags=[])
    with_error = Rock("canonical/baz-rocks", "main", "baz", error="rockcraft.yaml has no name")
    stream = io.StringIO()

    write_output([make_full_rock(), without_tags, with_error], OutputFormat.SIMPLE, False, stream)

    assert stream.getvalue() == "ghcr.io/canonical/foo:1.0-b\ndocker.io/x/bar\n"


def test_write_simple_without_tags():
    rock = make_full_rock()
    rock.tags = None  # As with --skip-tags
    stream = io.StringIO()

    write_output([rock], OutputFormat.SIMPLE, skip_tags=True, stream=stream)

    assert stream.getvalue() == "ghcr.io/canonical/foo\n"


def test_write_csv_without_rocks_has_header():
    stream = io.StringIO()
    write_output([], OutputFormat.CSV, skip_tags=True, stream=stream)
    assert stream.getvalue() == "repository,branch,path,name,version,registry,image,error\n"


def test_write_table():
    stream = io.StringIO()
    write_output([make_full_rock()], OutputFormat.TABLE, skip_tags=False, stream=stream)

    header, row = stream.getvalue().splitlines()
    assert header.split() == [
        "REPOSITORY", "PATH", "IMAGE", "VERSION", "TAG", "COUNT", "LATEST", "TAG", "ERROR",
    ]  # fmt: skip
    assert row.split() == [
        "canonical/foo-rocks", "foo", "ghcr.io/canonical/foo", "1.0", "2", "1.0-b", "-",
    ]  # fmt: skip


# Command line


@pytest.mark.parametrize("owner", ["canonical", "canonical/mlops"])
def test_owner_is_valid(owner):
    args = gather_rocks.parse_args(["--owner", owner, "--github-token", "token"])
    assert args.owner == owner


@pytest.mark.parametrize("owner", ["a/b/c", "canonical/", "/mlops"])
def test_owner_is_invalid(owner):
    with pytest.raises(SystemExit):
        gather_rocks.parse_args(["--owner", owner, "--github-token", "token"])


def test_token_is_required(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with pytest.raises(SystemExit):
        gather_rocks.parse_args(["--owner", "canonical"])


def test_token_from_environment(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "from-env")
    assert gather_rocks.parse_args(["--owner", "canonical"]).github_token == "from-env"


def test_gather_rocks_keeps_order_and_reports_failures():
    repositories = [
        RepositoryInfo(f"canonical/{name}", "canonical", "main") for name in ("a", "b", "c")
    ]

    def scan(github, info, default_registry):
        if info.full_name == "canonical/b":
            raise GithubException(403, {"message": "Forbidden"}, {})
        return [Rock(info.full_name, "main", "rock")]

    with patch.object(gather_rocks, "scan_repository", side_effect=scan):
        rocks, failed = gather_rocks.gather_rocks(MagicMock(), repositories, "docker.io/x", 3)

    assert [rock.repository for rock in rocks] == ["canonical/a", "canonical/c"]
    assert failed == ["canonical/b"]


@pytest.mark.parametrize(
    "rock, failed",
    [
        (make_full_rock(), []),
        # Problems with rocks or repositories are reported, but do not fail the run
        (Rock("canonical/foo-rocks", "main", "foo", error=gather_rocks.IMAGE_NOT_FOUND), []),
        (make_full_rock(), ["canonical/bar"]),
    ],
)
def test_main_succeeds_despite_problems(rock, failed, capsys):
    with (
        patch.object(gather_rocks, "Github"),
        patch.object(gather_rocks, "get_repositories", return_value=[INFO]),
        patch.object(gather_rocks, "gather_rocks", return_value=([rock], failed)),
        patch.object(gather_rocks, "check_rocks") as check_rocks,
    ):
        assert gather_rocks.main(["--owner", "canonical/mlops", "--github-token", "x"]) == 0

    check_rocks.assert_called_once()
    assert "canonical/foo-rocks" in capsys.readouterr().out


def test_main_fails_if_repositories_cannot_be_listed():
    error = UnknownObjectException(404, {"message": "Not Found"}, {})
    with (
        patch.object(gather_rocks, "Github"),
        patch.object(gather_rocks, "get_repositories", side_effect=error),
        patch.object(gather_rocks, "gather_rocks") as gather,
    ):
        assert gather_rocks.main(["--owner", "canonical/nope", "--github-token", "x"]) == 1

    gather.assert_not_called()
