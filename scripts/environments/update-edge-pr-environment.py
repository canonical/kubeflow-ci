#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""This is a script for creating the edge-pr environment across our charm repos."""

import argparse
import logging
import sys
from typing import List

from github import Auth, Github
from github.GithubException import GithubException

DEFAULT_REPO_OWNER = "canonical"

logger = logging.getLogger(__name__)
logging.basicConfig(stream=sys.stdout, level=logging.INFO)


def parse_repositories_file(path: str) -> List[str]:
    """Return the list of repository names in the given file, ignoring blanks and comments."""
    with open(path, "r") as file:
        lines = [line.strip() for line in file]
    return [line for line in lines if line and not line.startswith("#")]


def full_repository_name(owner: str, repository_name: str) -> str:
    """Return the qualified repository name, prefixing the owner if it is not already set."""
    return repository_name if "/" in repository_name else f"{owner}/{repository_name}"


def update_repository(
    github: Github,
    owner: str,
    repository_name: str,
    environment_name: str,
    secret_name: str,
    secret_value: str,
    dry_run: bool,
) -> None:
    """Create the environment in the repository and add the secret to it."""
    full_name = full_repository_name(owner, repository_name)
    if dry_run:
        logger.info(
            f"[dry-run] Would set `{secret_name}` in `{environment_name}` of `{full_name}`"
        )
        return

    repository = github.get_repo(full_name)
    environment = repository.create_environment(environment_name)
    environment.create_secret(secret_name, secret_value)
    logger.info(f"Set `{secret_name}` in environment `{environment_name}` of `{full_name}`")


def main() -> None:
    """Parse the arguments and update every repository in the repositories file."""
    parser = argparse.ArgumentParser(
        description="Create an environment in charm repositories and add a secret to it."
    )
    parser.add_argument(
        "--repositories-file",
        required=True,
        help="path to a file with one repository name or owner/name per line",
    )
    parser.add_argument("--secret-value", required=True, help="value to store in the secret")
    parser.add_argument("--github-token", required=True, help="GitHub token used to call the API")
    parser.add_argument(
        "--owner",
        default=DEFAULT_REPO_OWNER,
        help="owner used for repositories that do not specify one",
    )
    parser.add_argument("--environment", required=True, help="name of the environment to create")
    parser.add_argument("--secret-name", required=True, help="name of the secret to create")
    parser.add_argument(
        "--dry-run", action="store_true", help="log the changes without applying them"
    )
    args = parser.parse_args()

    repositories = parse_repositories_file(args.repositories_file)
    if not repositories:
        logger.error(f"No repositories found in `{args.repositories_file}`. Script exited.")
        sys.exit(1)

    github = Github(auth=Auth.Token(args.github_token))
    failures = 0
    for repository_name in repositories:
        try:
            update_repository(
                github,
                args.owner,
                repository_name,
                args.environment,
                args.secret_name,
                args.secret_value,
                args.dry_run,
            )
        except GithubException as error:
            failures += 1
            full_name = full_repository_name(args.owner, repository_name)
            logger.error(f"Failed to update `{full_name}`: {error}")

    updated = len(repositories) - failures
    logger.info(f"{updated}/{len(repositories)} repositories updated.")
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
