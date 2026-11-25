#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""This is a script for creating or updating an Actions policy across our charm repos."""

import argparse
import json
import logging
import sys
from typing import Any, Dict, List, Optional

from github import Auth, Github
from github.GithubException import GithubException

DEFAULT_REPO_OWNER = "canonical"
# See https://docs.github.com/en/rest/actions/policies
API_VERSION = "2026-03-10"
HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": API_VERSION,
}
PER_PAGE = 100

logger = logging.getLogger(__name__)
logging.basicConfig(stream=sys.stdout, level=logging.INFO)


def parse_repositories_file(path: str) -> List[str]:
    """Return the list of repository names in the given file, ignoring blanks and comments."""
    with open(path, "r") as file:
        lines = [line.strip() for line in file]
    return [line for line in lines if line and not line.startswith("#")]


def parse_policy_file(path: str) -> Dict[str, Any]:
    """Return the Actions policy in the given JSON file, which must at least have a name."""
    with open(path, "r") as file:
        policy = json.load(file)
    if not isinstance(policy, dict) or not policy.get("name"):
        raise ValueError(f"`{path}` must contain a JSON object with a `name`")
    return policy


def full_repository_name(owner: str, repository_name: str) -> str:
    """Return the qualified repository name, prefixing the owner if it is not already set."""
    return repository_name if "/" in repository_name else f"{owner}/{repository_name}"


def find_repository_policy(github: Github, full_name: str, name: str) -> Optional[Dict[str, Any]]:
    """Return the policy defined in the repository itself with the given name, if any.

    Policies inherited from the organization or enterprise are ignored (`has_parents=false`),
    since they cannot be updated through the repository endpoints.
    """
    page = 1
    while True:
        _, data = github.requester.requestJsonAndCheck(
            "GET",
            f"/repos/{full_name}/actions/policies",
            parameters={"has_parents": "false", "per_page": PER_PAGE, "page": page},
            headers=HEADERS,
        )
        policies = data.get("policies", [])
        for policy in policies:
            if policy.get("name") == name:
                return policy
        if len(policies) < PER_PAGE:
            return None
        page += 1


def update_repository(
    github: Github,
    owner: str,
    repository_name: str,
    policy: Dict[str, Any],
    dry_run: bool,
) -> None:
    """Create the Actions policy in the repository, or overwrite the one with the same name."""
    full_name = full_repository_name(owner, repository_name)
    name = policy["name"]
    existing = find_repository_policy(github, full_name, name)

    if dry_run:
        action = f"update policy {existing['id']}" if existing else "create policy"
        logger.info(f"[dry-run] Would {action} `{name}` in `{full_name}`")
        return

    if existing:
        _, data = github.requester.requestJsonAndCheck(
            "PUT",
            f"/repos/{full_name}/actions/policies/{existing['id']}",
            headers=HEADERS,
            input=policy,
        )
    else:
        _, data = github.requester.requestJsonAndCheck(
            "POST",
            f"/repos/{full_name}/actions/policies",
            headers=HEADERS,
            input=policy,
        )

    # Read the policy back from the API to confirm the write landed.
    _, data = github.requester.requestJsonAndCheck(
        "GET",
        f"/repos/{full_name}/actions/policies/{data['id']}",
        headers=HEADERS,
    )
    logger.info(
        f"{'Updated' if existing else 'Created'} policy `{data['name']}` (id: {data['id']}, "
        f"enforcement: {data['enforcement']}) in `{full_name}` "
        f"(updated_at: {data.get('updated_at')})"
    )


def main() -> None:
    """Parse the arguments and update every repository in the repositories file."""
    parser = argparse.ArgumentParser(
        description="Create or update an Actions policy in charm repositories."
    )
    repositories_group = parser.add_mutually_exclusive_group(required=True)
    repositories_group.add_argument(
        "--repositories-file",
        help="path to a file with one repository name or owner/name per line",
    )
    repositories_group.add_argument(
        "--repository",
        action="append",
        dest="repositories",
        help="repository name or owner/name, can be repeated to target multiple repositories",
    )
    parser.add_argument(
        "--policy-file",
        required=True,
        help="path to a JSON file with the Actions policy, as expected by the REST API",
    )
    parser.add_argument("--github-token", required=True, help="GitHub token used to call the API")
    parser.add_argument(
        "--owner",
        default=DEFAULT_REPO_OWNER,
        help="owner used for repositories that do not specify one",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="log the changes without applying them"
    )
    args = parser.parse_args()

    if args.repositories_file:
        repositories = parse_repositories_file(args.repositories_file)
        source = f"`{args.repositories_file}`"
    else:
        repositories = [repository.strip() for repository in args.repositories]
        repositories = [repository for repository in repositories if repository]
        source = "`--repository`"
    if not repositories:
        logger.error(f"No repositories found in {source}. Script exited.")
        sys.exit(1)

    try:
        policy = parse_policy_file(args.policy_file)
    except (OSError, ValueError) as error:
        logger.error(f"Invalid policy file: {error}. Script exited.")
        sys.exit(1)

    github = Github(auth=Auth.Token(args.github_token))
    failures = 0
    for repository_name in repositories:
        try:
            update_repository(github, args.owner, repository_name, policy, args.dry_run)
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
