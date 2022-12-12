# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import json

import typer


def main(issue_file: str, n_groups: int):
    """
    Splits a list of repos into n_groups, where each group has roughly the same number of issues.

    Args:
        issue_file: filename to a file of JSON format with structure:
            [
                {
                    "issues": {"totalCount":7},
                    "name":"kubeflow-ci"
                },
                {   "issues": ...
                },
                ...
            ]
        n_groups: Number of roughly equal groups to split things into

    Return:
        Prints to screen a list of groups of repos, in JSON format
    """
    try:
        with open(issue_file) as f:
            repos = json.load(f)
    except FileNotFoundError as e:
        raise FileNotFoundError(
            f"Could not find input issue file '{issue_file}' - does this file exist?"
        ) from e

    # Sort repos by number of issues
    repos.sort(key=lambda x: x["issues"]["totalCount"], reverse=True)

    # Split into n_groups, adding the next repo to the group with the fewest issues
    groups = [{"n_issues": 0, "repos": []} for _ in range(n_groups)]

    for repo in repos:
        groups[0]["repos"].append(repo["name"])
        groups[0]["n_issues"] += repo["issues"]["totalCount"]
        groups.sort(key=lambda x: x["n_issues"])

    # Print to screen
    print(json.dumps(groups, indent=2))


if __name__ == "__main__":
    typer.run(main)
