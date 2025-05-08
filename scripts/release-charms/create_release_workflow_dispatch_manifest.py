#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Creates a workflow dispatch manifest to release charms from one bundle to another."""

import logging
from pathlib import Path

import typer
import yaml
from charmed_kubeflow_chisme.bundle import Bundle

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main(
    source_bundle: str = typer.Argument(
        ...,
        help="Path to a file defining the source channel for releases.  The file format "
        "expected is a standard bundle YAML file, where any charm that is in-scope for generating"
        "a release should also have the _github_repo_name key.  Additionally, if the charm is from"
        "a multi-charm repo, it should also include a _path_in_github_repo of the relative path"
        "to that charm in the repo, for example 'charms/my-charm'",
    ),
    destination_bundle: str = typer.Argument(
        ...,
        help="Path to a file defining the destination channel for releases.  The file format "
        "expected is a standard bundle YAML file, where any charm that is in-scope for generating"
        "a release should also have the _github_repo_name key.  Additionally, if the charm is from"
        "a multi-charm repo, it should also include a _path_in_github_repo of the relative path"
        "to that charm in the repo, for example 'charms/my-charm'",
    ),
    output_file: str = typer.Option(
        default="dispatch_manifest.yaml",
        help="Name of the output YAML file to write the dispatch manifest to",
    ),
):
    """Create a workflow dispatch manifest from Charm Bundle files."""
    source_bundle = Bundle(source_bundle)
    destination_bundle = Bundle(destination_bundle)

    release_dispatches = []

    for source_application_name, source_application in source_bundle.applications.items():
        # Find a matching application in the destination bundle
        try:
            validate_application_in_scope(source_application_name, source_application)
            destination_application = get_matching_application(
                source_application_name, source_application, destination_bundle
            )
            logger.info(
                f"Application {source_application_name} found in both bundles and requiring release."
            )
            repository = get_repository(source_application, destination_application)
            path_in_repo = get_path_in_repo(source_application, destination_application)
        except ApplicationMatchError as e:
            logger.info(str(e) + "  Skipping.")
            continue

        dispatch = build_release_dispatch_dict(
            source_application, destination_application, repository, path_in_repo
        )
        logger.info(
            f"Application {source_application_name} causing release of charm {source_application['charm']} from {dispatch['inputs']['origin-channel']}->{dispatch['inputs']['destination-channel']}"
        )
        release_dispatches.append(dispatch)

    write_output(release_dispatches, output_file)


class ApplicationMatchError(Exception):
    """Raised when the source and destination applications are not a match for release."""

    pass


def get_matching_application(
    source_application_name, source_application, destination_bundle
) -> bool:
    """Returns matching destination app if one matches, will be released, and has needed data.

    Otherwise, it raises ValueError with the reason for rejection.

    The applications constitute a release if:
    * they reference the same charm
    * they reference different channels
    """
    try:
        destination_application = destination_bundle.applications[source_application_name]
    except KeyError:
        raise ApplicationMatchError(
            f"Application {source_application_name} not found in destination bundle."
        )

    if source_application["charm"] != destination_application["charm"]:
        raise ApplicationMatchError(
            f"Source and destination charms for application {source_application_name} do not match"
            f".  Got {source_application['charm']}, {destination_application['charm']}, "
            f"respectively."
        )

    if source_application["channel"] == destination_application["channel"]:
        raise ApplicationMatchError(
            f"Source and destination for application {source_application_name} both reference the "
            f"same channel."
        )

    return destination_application


def get_repository(source_application, destination_application) -> str:
    """Returns the repository string for this charm, including owner"""
    try:
        # Check for the inputs we add to the charms we manage in our bundle files, adding
        # a default for owner if it is omitted
        source_repository = (
            f'{source_application.get("_github_repo_owner", "canonical")}/'
            f'{source_application["_github_repo_name"]}'
        )
        destination_repository = (
            f'{destination_application.get("_github_repo_owner", "canonical")}/'
            f'{destination_application["_github_repo_name"]}'
        )

    except KeyError:
        raise ApplicationMatchError(
            f"Application would have been released from {source_application['channel']}->"
            f"{destination_application['channel']}, but one or both are missing the required "
            f"additional variable _github_repo_name"
        )

    if source_repository != destination_repository:
        raise ValueError(
            f"Source and destination repositories do not match.  Got {source_repository} and"
            f"destination ({destination_repository}, respectively."
        )

    return source_repository


def get_path_in_repo(source_application, destination_application) -> str:
    """Returns the charm path within the repo, if they match, else raises ValueError"""
    source_path_in_repo = Path(source_application.get("_path_in_github_repo", "./"))
    destination_path_in_repo = Path(destination_application.get("_path_in_github_repo", "./"))
    if source_path_in_repo != destination_path_in_repo:
        raise ValueError(
            f"Source and destination _path_in_github_repo do not match.  Got {str(source_path_in_repo)}) and "
            f"{str(destination_path_in_repo)}, respectively."
        )

    if source_path_in_repo.is_absolute():
        raise ValueError(
            f"_path_in_github_repo variable must be a relative"
            f"path to the top of the Github repository.  Got '({str(source_path_in_repo)})'"
        )

    return source_path_in_repo


def build_release_dispatch_dict(
    source_application, destination_application, repository, path_in_repo
) -> dict:
    """Returns a dict representing a workflow dispatch run"""
    dispatch = {
        "repository": repository,
        "workflow_name": "release.yaml",
        "inputs": {
            "origin-channel": source_application["channel"],
            "destination-channel": destination_application["channel"],
        },
    }

    # If we are a multi-charm repo, add the charm-name
    if path_in_repo == Path("."):
        # Charm is in the Github repo root, so this is a single-charm repo
        # Do not add the charm-name to inputs
        pass
    else:
        # Validate the charm path to ensure it follows the hard-coded assumptions of the
        # release.yaml workflow
        if len(path_in_repo.parts) != 2 or path_in_repo.parts[0] != "charms":
            raise ValueError(
                f"Due to assumptions in the release.yaml action for multi-charm repos,"
                f" the _path_in_github_repo variable must be one "
                " of the following: './' or './charms/<charm-name>'.  "
                f"Got '{str(path_in_repo)}'"
            )
        dispatch["inputs"]["charm-name"] = path_in_repo.name
    return dispatch


def write_output(dispatches, output_file: str):
    """Writes the release dispatches to the output file"""
    with open(output_file, "w") as f:
        yaml.dump(dispatches, f, indent=2)


def validate_application_in_scope(name, app):
    """Checks that the app is in scope (managed by our team), else raises ApplicationMatchError

    Application is considered in scope if it has the mandatory additional variables we set in out
    bundles:
    * _github_repo_name
    """
    for var in ["_github_repo_name"]:
        if var not in app:
            raise ApplicationMatchError(
                f"Application {name} is missing required variable {var} and likely is not "
                f"controlled by our team."
            )


if __name__ == "__main__":
    typer.run(main)
