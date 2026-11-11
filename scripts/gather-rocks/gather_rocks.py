#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Gather the rocks maintained by a GitHub user, organization or team.

The script scans the repositories of an owner for `rockcraft.yaml` files, works out the registry
and the name that each rock is published under, and checks that the image exists in the registry.
"""

import argparse
import csv
import json
import logging
import os
import re
import sys
import threading
from collections.abc import Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import StrEnum
from functools import cached_property
from pathlib import PurePosixPath
from typing import Any, TextIO
from urllib.parse import urljoin

import requests
import yaml
from github import Auth, Github
from github.GithubException import GithubException, UnknownObjectException
from github.Repository import Repository
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

ROCKCRAFT_FILE = "rockcraft.yaml"
ROCK_CI_METADATA_FILE = "rock-ci-metadata.yaml"
WORKFLOWS_DIR = ".github/workflows/"
# Repository (or organization) variable used by the charmed-kubeflow-workflows to publish rocks
REGISTRY_VARIABLE = "ROCK_IMAGE_REGISTRY"
# Reusable workflow from canonical/k8s-workflows, which publishes to `ghcr.io/<owner>`
K8S_WORKFLOWS_BUILD_ROCKS = "k8s-workflows/.github/workflows/build_rocks.yaml"
DEFAULT_REGISTRY = "docker.io/charmedkubeflow"
DEFAULT_WORKERS = 8

DOCKER_HUB_HOSTS = {"docker.io", "index.docker.io", "registry-1.docker.io"}
DOCKER_HUB_API = "https://hub.docker.com/v2"
REQUEST_TIMEOUT = 30
# Tags created by the charmed-kubeflow-workflows end with a `-YYYYMMDDhhmmss` build timestamp
TIMESTAMP_SUFFIX = re.compile(r"-(\d{14})$")
# A `v` in front of a version number, e.g. in `v2.6.2` but not in `vllm`
V_PREFIX = re.compile(r"^v(?=\d)")
# Anonymous requests cannot tell missing images apart from private ones, except on Docker Hub
IMAGE_NOT_FOUND = "Image not found in the registry, or private"


class OutputFormat(StrEnum):
    """Supported output formats."""

    TABLE = "table"
    SIMPLE = "simple"
    JSON = "json"
    YAML = "yaml"
    CSV = "csv"


@dataclass(frozen=True, slots=True)
class RepositoryInfo:
    """The details of a repository needed to scan it, which can be shared between threads."""

    full_name: str
    owner: str
    default_branch: str


@dataclass(slots=True)
class Rock:
    """A rock found in a repository, where it is published, and any problem found with it."""

    repository: str
    branch: str
    path: str
    name: str | None = None
    version: str | None = None
    registry: str | None = None
    tags: list[str] | None = None
    error: str | None = None

    @property
    def image(self) -> str | None:
        """Return the image the rock is published as, without a tag."""
        if self.registry and self.name:
            return f"{self.registry}/{self.name}"
        return None

    @property
    def latest_tag(self) -> str | None:
        """Return the most recent tag of the rock's version, if tags were gathered."""
        return max(self.tags, key=tag_sort_key) if self.tags else None

    @property
    def reference(self) -> str | None:
        """Return the image with its latest tag if there is one, e.g. to pull it."""
        if self.image and (tag := self.latest_tag):
            return f"{self.image}:{tag}"
        return self.image


def tag_sort_key(tag: str) -> tuple[str, list[tuple[int, int | str]]]:
    """Sort tags by their build timestamp suffix if they have one, then in natural order."""
    match = TIMESTAMP_SUFFIX.search(tag)
    timestamp = match.group(1) if match else ""
    parts = [(0, int(part)) if part.isdigit() else (1, part) for part in re.split(r"(\d+)", tag)]
    return timestamp, parts


def strip_v_prefix(version: str) -> str:
    """Remove the `v` in front of a version number, e.g. `v2.6.2` becomes `2.6.2`."""
    return V_PREFIX.sub("", version)


def tag_matches_version(tag: str, version: str) -> bool:
    """Return whether a tag was published for the given version, e.g. `1.0-abc1234` for `1.0`.

    A `v` in front of the version number is ignored on both sides, as some rocks are published
    with tags like `2.6.2-abc1234` while their version is `v2.6.2`, or the other way around.
    """
    tag, version = strip_v_prefix(tag), strip_v_prefix(version)
    return tag == version or tag.startswith(f"{version}-")


def split_registry(registry: str) -> tuple[str, str]:
    """Split a registry such as `docker.io/charmedkubeflow` into its host and namespace.

    A registry without a host, e.g. `charmedkubeflow`, refers to Docker Hub.
    """
    registry = registry.strip().strip("/")
    host, _, namespace = registry.partition("/")
    if namespace and ("." in host or ":" in host or host == "localhost"):
        return host, namespace
    return "docker.io", registry


# GitHub
def describe_github_error(error: GithubException) -> str:
    """Return the status and the message of a GitHub error."""
    message = error.data.get("message") if isinstance(error.data, dict) else error.data
    return f"{error.status} {message}"


def get_repositories(github: Github, owner: str, include_archived: bool) -> list[RepositoryInfo]:
    """Return the repositories of a user, an organization, or an organization's team.

    Args:
        github: authenticated GitHub client.
        owner: `<user>`, `<organization>` or `<organization>/<team-slug>`.
        include_archived: whether to include archived repositories.
    """
    if "/" in owner:
        organization, team = owner.split("/", 1)
        repositories = github.get_organization(organization).get_team_by_slug(team).get_repos()
    elif github.get_user(owner).type == "Organization":
        repositories = github.get_organization(owner).get_repos(type="all")
    else:
        repositories = github.get_user(owner).get_repos(type="owner")

    selected = []
    for repository in repositories:
        if repository.archived and not include_archived:
            logger.debug(f"Skipping archived repository `{repository.full_name}`")
            continue
        selected.append(
            RepositoryInfo(repository.full_name, repository.owner.login, repository.default_branch)
        )
    return sorted(selected, key=lambda repository: repository.full_name)


def get_file_paths(repository: Repository, info: RepositoryInfo) -> list[str]:
    """Return the paths of all files in the default branch of a repository."""
    try:
        tree = repository.get_git_tree(info.default_branch, recursive=True)
    except GithubException as error:
        if error.status == 409:  # The repository is empty
            return []
        raise
    if tree.truncated:
        logger.warning(f"The file tree of `{info.full_name}` is truncated, rocks may be missed")
    return [element.path for element in tree.tree if element.type == "blob"]


def find_rock_dirs(paths: Iterable[str]) -> list[str]:
    """Return the directories containing a rockcraft.yaml file, `.` being the repository root."""
    return sorted(
        str(PurePosixPath(path).parent)
        for path in paths
        if PurePosixPath(path).name == ROCKCRAFT_FILE
    )


class RepositoryContext:
    """Information about a repository that is shared by its rocks, fetched only when needed."""

    def __init__(
        self,
        github: Github,
        repository: Repository,
        info: RepositoryInfo,
        paths: list[str],
    ):
        self.github = github
        self.repository = repository
        self.info = info
        self.paths = set(paths)

    def read_text(self, path: str) -> str:
        """Return the content of a file in the default branch."""
        content = self.repository.get_contents(path, ref=self.info.default_branch)
        return content.decoded_content.decode()

    def read_yaml(self, path: str) -> dict[str, Any]:
        """Return the content of a YAML file, keeping every value as a string like `yq` does.

        This avoids unquoted versions such as `1.10` being turned into the float `1.1`.
        """
        data = yaml.load(self.read_text(path), Loader=yaml.BaseLoader)
        return data if isinstance(data, dict) else {}

    @cached_property
    def uses_k8s_workflows(self) -> bool:
        """Return whether the repository builds its rocks with the k8s-workflows."""
        workflows = sorted(
            path
            for path in self.paths
            if path.startswith(WORKFLOWS_DIR) and path.endswith((".yaml", ".yml"))
        )
        return any(K8S_WORKFLOWS_BUILD_ROCKS in self.read_text(path) for path in workflows)

    @cached_property
    def repository_variable(self) -> str | None:
        """Return the value of the registry variable of the repository, if set and readable."""
        try:
            return self.repository.get_variable(REGISTRY_VARIABLE).value
        except UnknownObjectException:
            return None
        except GithubException as error:
            logger.warning(
                f"Cannot read the variables of `{self.info.full_name}` ({error.status}), "
                "the token needs collaborator access"
            )
            return None

    @cached_property
    def organization_variable(self) -> str | None:
        """Return the value of the registry variable shared by the organization, if any."""
        try:
            for variable in self._organization_variables():
                if variable["name"] == REGISTRY_VARIABLE:
                    return variable["value"]
        except GithubException as error:
            logger.warning(
                f"Cannot read the organization variables of `{self.info.full_name}` "
                f"({error.status})"
            )
        return None

    def _organization_variables(self) -> Iterator[dict[str, Any]]:
        """Yield the organization variables that are shared with the repository."""
        url = f"{self.repository.url}/actions/organization-variables"
        page = 1
        while True:
            _, data = self.github.requester.requestJsonAndCheck(
                "GET", url, parameters={"per_page": 100, "page": page}
            )
            yield from data["variables"]
            if page * 100 >= data["total_count"]:
                return
            page += 1


def resolve_registry(context: RepositoryContext, rock_dir: str, default_registry: str) -> str:
    """Return the registry a rock is published to.

    This mirrors the publishing workflows: the k8s-workflows always publish to `ghcr.io/<owner>`,
    while the charmed-kubeflow-workflows use the `registry` of the rock's rock-ci-metadata.yaml,
    or else the ROCK_IMAGE_REGISTRY variable of the repository or of the organization.
    """
    if context.uses_k8s_workflows:
        return f"ghcr.io/{context.info.owner}"

    metadata_path = str(PurePosixPath(rock_dir) / ROCK_CI_METADATA_FILE)
    if metadata_path in context.paths:
        if registry := context.read_yaml(metadata_path).get("registry"):
            return registry

    return context.repository_variable or context.organization_variable or default_registry


def inspect_rock(context: RepositoryContext, rock_dir: str, default_registry: str) -> Rock:
    """Return the rock in the given directory, with its name, version and registry."""
    rock = Rock(context.info.full_name, context.info.default_branch, rock_dir)
    try:
        rockcraft = context.read_yaml(str(PurePosixPath(rock_dir) / ROCKCRAFT_FILE))
        rock.name, rock.version = rockcraft.get("name"), rockcraft.get("version")
        if not rock.name or not rock.version:
            rock.error = "rockcraft.yaml has no name or version"
            return rock
        rock.registry = resolve_registry(context, rock_dir, default_registry)
    except GithubException as error:
        rock.error = f"GitHub error {describe_github_error(error)}"
    return rock


def scan_repository(github: Github, info: RepositoryInfo, default_registry: str) -> list[Rock]:
    """Return the rocks in the default branch of a repository.

    Args:
        github: a lazy GitHub client, so that getting the repository does not call the API.
        info: the repository to scan.
        default_registry: registry used when it cannot be found for a rock.
    """
    repository = github.get_repo(info.full_name)
    paths = get_file_paths(repository, info)
    rock_dirs = find_rock_dirs(paths)
    if not rock_dirs:
        return []

    logger.info(f"Found {len(rock_dirs)} rock(s) in `{info.full_name}`")
    context = RepositoryContext(github, repository, info, paths)
    return [inspect_rock(context, rock_dir, default_registry) for rock_dir in rock_dirs]


# Registries
def make_session() -> requests.Session:
    """Return an HTTP session that retries on rate limiting and server errors."""
    retries = Retry(
        total=5,
        backoff_factor=2,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retries))
    return session


class DockerHubClient:
    """Query Docker Hub through its own API.

    The registry API of Docker Hub answers 401 for missing images, which cannot be told apart from
    private ones, while the Docker Hub API answers 404.
    """

    def __init__(self, session: requests.Session):
        self.session = session

    def exists(self, namespace: str, name: str) -> bool:
        """Return whether the image exists."""
        url = f"{DOCKER_HUB_API}/namespaces/{namespace}/repositories/{name}"
        response = self.session.get(url, timeout=REQUEST_TIMEOUT)
        if response.status_code == 404:
            return False
        response.raise_for_status()
        return True

    def tags(self, namespace: str, name: str, version: str) -> list[str] | None:
        """Return the tags of the image that contain the version, or None if it does not exist."""
        url = f"{DOCKER_HUB_API}/namespaces/{namespace}/repositories/{name}/tags"
        params: dict[str, Any] | None = {"page_size": 100, "name": version}
        tags = []
        while url:
            response = self.session.get(url, params=params, timeout=REQUEST_TIMEOUT)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            data = response.json()
            tags.extend(result["name"] for result in data["results"])
            # The `next` URL already contains the query parameters
            url, params = data.get("next"), None
        return tags


class OciRegistryClient:
    """Query a registry through the OCI distribution API, e.g. ghcr.io, with anonymous tokens."""

    def __init__(self, session: requests.Session, host: str):
        self.session = session
        self.host = host
        self._tokens: dict[str, str | None] = {}

    def exists(self, namespace: str, name: str) -> bool:
        """Return whether the image exists and is public."""
        return (
            self._list_tags(f"{namespace}/{name}", page_size=1, first_page_only=True) is not None
        )

    def tags(self, namespace: str, name: str, version: str) -> list[str] | None:
        """Return all the tags of the image, or None if it does not exist or is private.

        The registry API cannot filter tags, so all of them are returned regardless of the version.
        """
        return self._list_tags(f"{namespace}/{name}", page_size=1000)

    def _list_tags(
        self, repository: str, page_size: int, first_page_only: bool = False
    ) -> list[str] | None:
        """Return the tags of an image, or None if it does not exist or is private."""
        url = f"https://{self.host}/v2/{repository}/tags/list"
        params: dict[str, Any] | None = {"n": page_size}
        tags = []
        while True:
            response = self._get(repository, url, params)
            if response.status_code in (401, 403, 404):
                return None
            response.raise_for_status()
            tags.extend(response.json().get("tags") or [])
            # The `next` link is relative to the registry, and already contains the parameters
            next_url = response.links.get("next", {}).get("url")
            if first_page_only or not next_url:
                return tags
            url, params = urljoin(url, next_url), None

    def _get(
        self, repository: str, url: str, params: dict[str, Any] | None = None
    ) -> requests.Response:
        """Send a GET request, fetching an anonymous token if the registry asks for one."""
        response = self._send(repository, url, params)
        if response.status_code == 401 and repository not in self._tokens:
            challenge = response.headers.get("WWW-Authenticate", "")
            self._tokens[repository] = self._fetch_token(repository, challenge)
            response = self._send(repository, url, params)
        return response

    def _send(self, repository: str, url: str, params: dict[str, Any] | None) -> requests.Response:
        """Send a GET request with the token of the repository, if there is one."""
        headers = {}
        if token := self._tokens.get(repository):
            headers["Authorization"] = f"Bearer {token}"
        return self.session.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)

    def _fetch_token(self, repository: str, challenge: str) -> str | None:
        """Return an anonymous pull token, following the `WWW-Authenticate` challenge."""
        scheme, _, parameters = challenge.partition(" ")
        fields = dict(re.findall(r'(\w+)="([^"]*)"', parameters))
        if scheme.lower() != "bearer" or "realm" not in fields:
            return None
        params = {
            "service": fields.get("service"),
            "scope": f"repository:{repository}:pull",
        }
        response = self.session.get(fields["realm"], params=params, timeout=REQUEST_TIMEOUT)
        if not response.ok:
            # Registries refuse anonymous tokens for missing and private images alike
            return None
        data = response.json()
        return data.get("token") or data.get("access_token")


class RegistryChecker:
    """Check that the images of rocks exist, using the right client for each registry."""

    def __init__(self, session: requests.Session):
        self.session = session
        self._clients: dict[str, DockerHubClient | OciRegistryClient] = {}

    def client(self, host: str) -> DockerHubClient | OciRegistryClient:
        """Return the client for a registry host."""
        if host not in self._clients:
            if host in DOCKER_HUB_HOSTS:
                self._clients[host] = DockerHubClient(self.session)
            else:
                self._clients[host] = OciRegistryClient(self.session, host)
        return self._clients[host]

    def check(self, rock: Rock, skip_tags: bool) -> None:
        """Check that the rock's image exists and, unless skipped, gather its tags for its version.

        Problems are set as the error of the rock. When gathering tags, the existence of the image
        is deduced from the tags request, which halves the requests to Docker Hub and its rate
        limit.
        """
        host, namespace = split_registry(rock.registry)
        client = self.client(host)
        try:
            if skip_tags:
                if not client.exists(namespace, rock.name):
                    rock.error = IMAGE_NOT_FOUND
                return
            # Docker Hub filters tags by substring, so `2.6.2` finds both `2.6.2-*` and `v2.6.2-*`
            tags = client.tags(namespace, rock.name, strip_v_prefix(rock.version))
            if tags is None:
                rock.error = IMAGE_NOT_FOUND
                return
            matching = (tag for tag in tags if tag_matches_version(tag, rock.version))
            rock.tags = sorted(matching, key=tag_sort_key)
            if not rock.tags:
                rock.error = f"No tag for version {rock.version}"
        except requests.RequestException as error:
            rock.error = f"Registry error: {error}"


# Concurrency


class ThreadLocalClients:
    """Give each thread its own GitHub client and registry checker, as they are not thread-safe."""

    def __init__(self, token: str):
        self.token = token
        self._local = threading.local()

    @property
    def github(self) -> Github:
        """Return the lazy GitHub client of the current thread."""
        if not hasattr(self._local, "github"):
            self._local.github = Github(auth=Auth.Token(self.token), per_page=100, lazy=True)
        return self._local.github

    @property
    def registry_checker(self) -> RegistryChecker:
        """Return the registry checker of the current thread."""
        if not hasattr(self._local, "registry_checker"):
            self._local.registry_checker = RegistryChecker(make_session())
        return self._local.registry_checker


def gather_rocks(
    clients: ThreadLocalClients,
    repositories: list[RepositoryInfo],
    default_registry: str,
    workers: int,
) -> tuple[list[Rock], list[str]]:
    """Return the rocks of all the repositories, and the repositories that could not be scanned."""

    def scan(info: RepositoryInfo) -> list[Rock] | None:
        try:
            return scan_repository(clients.github, info, default_registry)
        except GithubException as error:
            logger.error(f"Failed to scan `{info.full_name}`: {describe_github_error(error)}")
            return None

    # The results are in the same order as the repositories
    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = list(executor.map(scan, repositories))
    rocks = [rock for result in results if result for rock in result]
    failed = [info.full_name for info, result in zip(repositories, results) if result is None]
    return rocks, failed


def check_rocks(
    clients: ThreadLocalClients, rocks: list[Rock], skip_tags: bool, workers: int
) -> None:
    """Check the images of all the rocks that were inspected without errors."""

    def check(rock: Rock) -> None:
        clients.registry_checker.check(rock, skip_tags)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        # Consume the results, so that unexpected exceptions are raised instead of being ignored
        list(executor.map(check, [rock for rock in rocks if rock.error is None]))


# Output


def to_record(rock: Rock, with_tags: bool, with_tag_list: bool) -> dict[str, Any]:
    """Return the rock as a flat dictionary for the output."""
    record = {
        "repository": rock.repository,
        "branch": rock.branch,
        "path": rock.path,
        "name": rock.name,
        "version": rock.version,
        "registry": rock.registry,
        "image": rock.image,
    }
    if with_tags:
        record["tag_count"] = len(rock.tags) if rock.tags is not None else None
        record["latest_tag"] = rock.latest_tag
    if with_tags and with_tag_list:
        record["tags"] = rock.tags
    record["error"] = rock.error
    return record


TABLE_COLUMNS = (
    "repository",
    "path",
    "image",
    "version",
    "tag_count",
    "latest_tag",
    "error",
)


def format_table(records: list[dict[str, Any]], fields: list[str]) -> str:
    """Return the records as a table with aligned columns, of the fields that are most useful."""
    columns = [column for column in TABLE_COLUMNS if column in fields]
    headers = [column.replace("_", " ").upper() for column in columns]
    rows = [["-" if record[c] is None else str(record[c]) for c in columns] for record in records]
    widths = [max(len(cell) for cell in column) for column in zip(headers, *rows)]
    lines = [headers, *rows]
    return "\n".join(
        "  ".join(cell.ljust(width) for cell, width in zip(line, widths)).rstrip()
        for line in lines
    )


def write_output(
    rocks: list[Rock], output_format: OutputFormat, skip_tags: bool, stream: TextIO
) -> None:
    """Write the rocks to the stream in the requested format."""
    with_tag_list = output_format in (OutputFormat.JSON, OutputFormat.YAML)
    records = [to_record(rock, not skip_tags, with_tag_list) for rock in rocks]
    # The fields are taken from an empty rock, so that they are known even without any rock
    fields = list(to_record(Rock("", "", ""), not skip_tags, with_tag_list))
    match output_format:
        case OutputFormat.TABLE:
            stream.write(format_table(records, fields) + "\n")
        case OutputFormat.SIMPLE:
            # One image per line, skipping the rocks whose image is unknown due to an error
            stream.writelines(f"{rock.reference}\n" for rock in rocks if rock.reference)
        case OutputFormat.JSON:
            stream.write(json.dumps(records, indent=2) + "\n")
        case OutputFormat.YAML:
            yaml.safe_dump(records, stream, sort_keys=False)
        case OutputFormat.CSV:
            writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(records)


# Command line


def owner_type(value: str) -> str:
    """Validate the `--owner` option, which is `<user|organization>` or `<organization>/<team>`."""
    parts = value.split("/")
    if len(parts) > 2 or not all(parts):
        raise argparse.ArgumentTypeError(
            f"`{value}` is not a `<user|organization>` or an `<organization>/<team>`"
        )
    return value


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line arguments."""
    parser = argparse.ArgumentParser(
        description="Gather the rocks of a GitHub user, organization or team, and check where "
        "they are published."
    )
    parser.add_argument(
        "--owner",
        required=True,
        type=owner_type,
        help="`<user|organization>` to scan all its repositories, or `<organization>/<team>` to "
        "scan the repositories of a team, e.g. `canonical/mlops`",
    )
    parser.add_argument(
        "--github-token",
        default=os.environ.get("GITHUB_TOKEN"),
        help="GitHub token used to call the API, defaults to the GITHUB_TOKEN environment variable",
    )
    parser.add_argument(
        "--include-archived",
        action="store_true",
        help="also scan archived repositories",
    )
    parser.add_argument(
        "--skip-tags",
        action="store_true",
        help="only check that the images exist, without gathering their tags",
    )
    parser.add_argument(
        "--default-registry",
        default=DEFAULT_REGISTRY,
        help="registry used when it cannot be found for a rock (default: %(default)s)",
    )
    parser.add_argument(
        "--output-format",
        type=OutputFormat,
        choices=list(OutputFormat),
        default=OutputFormat.TABLE,
        help="format of the output, `simple` writes one image per line, with its latest tag if "
        "tags were gathered (default: %(default)s)",
    )
    parser.add_argument("--output-file", help="file to write the output to, instead of stdout")
    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help="number of repositories and images to check in parallel (default: %(default)s)",
    )
    parser.add_argument("--verbose", action="store_true", help="log debug messages")
    args = parser.parse_args(argv)
    if not args.github_token:
        parser.error("a GitHub token is required, pass --github-token or set GITHUB_TOKEN")
    if args.workers < 1:
        parser.error("--workers must be at least 1")
    return args


def log_summary(repositories: list[RepositoryInfo], rocks: list[Rock], failed: list[str]) -> None:
    """Log how many rocks were found, and which ones have problems."""
    logger.info(f"Found {len(rocks)} rock(s) in {len(repositories)} repositories")
    for rock in rocks:
        if rock.error:
            image = f" `{rock.image}`" if rock.image else ""
            logger.error(f"`{rock.repository}` `{rock.path}`{image}: {rock.error}")
    if failed:
        logger.error(f"Failed to scan {len(failed)} repositories: {', '.join(failed)}")


def main(argv: list[str] | None = None) -> int:
    """Gather the rocks, check their images, and write the result."""
    args = parse_args(argv)
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    github = Github(auth=Auth.Token(args.github_token), per_page=100)
    try:
        repositories = get_repositories(github, args.owner, args.include_archived)
    except GithubException as error:
        logger.error(
            f"Failed to list the repositories of `{args.owner}`: {describe_github_error(error)}"
        )
        return 1
    logger.info(f"Scanning {len(repositories)} repositories of `{args.owner}`")
    clients = ThreadLocalClients(args.github_token)
    rocks, failed = gather_rocks(clients, repositories, args.default_registry, args.workers)
    check_rocks(clients, rocks, args.skip_tags, args.workers)

    if args.output_file:
        with open(args.output_file, "w") as stream:
            write_output(rocks, args.output_format, args.skip_tags, stream)
    else:
        write_output(rocks, args.output_format, args.skip_tags, sys.stdout)

    log_summary(repositories, rocks, failed)
    # Problems with some rocks or repositories are reported, but do not fail the whole run
    return 0


if __name__ == "__main__":
    sys.exit(main())
