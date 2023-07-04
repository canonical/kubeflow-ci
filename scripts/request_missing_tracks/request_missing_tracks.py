#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Script for requesting missing tracks in a bundle"""

import logging

import typer
from bundle import Bundle
from juju import Juju, JujuFailedError

logging.basicConfig()
logger = logging.getLogger(__name__)


from typing import Dict
...
def get_charm_channel_map_for_applications(applications: Dict[str, dict]) -> Dict[str, dict]:
    """Return a dict of {charm_name: charm_channel_map} for charms in a map of applications.

    The charm_channel_map returned is the channel_map key of the yaml returned for
    `juju info charmName --format yaml`.  For example, `juju info kubeflow-profiles --format yaml`
    yields (truncated):
        name: kubeflow-profiles
        description: Kubeflow Profiles and Access Management
        ...
        channel-map:
          1.4/edge:
            released-at: "2022-05-30T09:17:14.638764+00:00"
            track: "1.4"
            risk: edge
            revision: 63
            size: 8444768
            version: "63"
            architectures:
            - amd64
            series:
            - kubernetes
          1.4/stable:
            released-at: "2022-06-30T20:33:50.905677+00:00"
            track: "1.4"
            risk: stable
            revision: 63
            size: 8444768
            version: "63"
            architectures:
            - amd64
            series:
            - kubernetes
          ...

    Note that this returns {charm_name: charm_info}, not {application_name: charm_info}.  Multiple
    applications might deploy the same charm, and thus len(applications) >= len(returned).
    """
    logger.debug("Getting charm channel map for applications")
    charm_channel_map = {}
    for name, application in applications.items():
        logger.debug(f"Processing application: {name}")
        if application["charm"] not in charm_channel_map:
            logger.debug(
                f"Getting info from juju application '{name}' that deploys charm {application['charm']}"
            )
            try:
                juju_info = Juju.info(application["charm"])
                pass
            except JujuFailedError as e:
                print(
                    f"WARNING: Failed getting info for application '{name}'.  "
                    f"Does this charm exist?"
                    f"\nGot stderr from Juju: {e.stderr}"
                )
                continue
            charm_channel_map[application["charm"]] = juju_info["channel-map"]
        else:
            logger.debug(
                f"Skipping application '{name}' that deploys charm "
                f"'{application['charm']}' - charm alreaddy in map"
            )

    return charm_channel_map


def get_missing_tracks(applications: dict[str, dict], charm_channel_map: dict[str, dict]):
    """Returns charm and track for applications that deploy charms from non-existent tracks.

    Silently ignores any charms that are in appliocations but not in charm_channel_map
    """
    missing_tracks = {}
    for name, application in applications.items():
        charm = application["charm"]
        if charm not in charm_channel_map:
            # Skip if we do not have info on this charm
            logging.debug(f"No channel data found for charm {charm}.  Skipping this application")
            continue

        # Get first channel that matches this applications track
        application_track = application["channel"].split("/")[0]
        try:
            next(
                channel
                for channel in charm_channel_map[application["charm"]].keys()
                if channel.startswith(application_track)
            )
        except StopIteration:
            missing_tracks[application["charm"]] = application_track

    return missing_tracks


def print_missing_track_summary(missing_tracks: dict[str, str]):
    """Prints a formatted report for a missing-tracks dict"""
    if missing_tracks:
        print(
            "At least one track in the bundle found missing.  To create this track, submit the"
            " below request to: https://discourse.charmhub.io/c/charmhub-requests\n"
        )
        print("Subject:\nRequest: Add tracks to Charms\n")
        print(
            "Body:\nHello!  Can we please add the following tracks to the cited charms?  Thanks!\n"
        )
        print("\tCharm: Track\n")
        for charm, track in missing_tracks.items():
            print(f"\t{charm}: {track}")
    else:
        print("All tracks are present")


def main(
    bundle_file: str = typer.Argument(..., help="Path to Charm Bundle file"),
    verbose: bool = typer.Option(False, "--verbose"),
):
    """Parse a bundle file, printing the charm:track pairs in the bundle that do not exist."""
    if verbose:
        logger.info("Setting verbose logging")
        logger.setLevel(logging.DEBUG)

    bundle = Bundle(bundle_file)
    charm_channel_map = get_charm_channel_map_for_applications(bundle.applications)
    missing_tracks = get_missing_tracks(bundle.applications, charm_channel_map)
    print_missing_track_summary(missing_tracks)


if __name__ == "__main__":
    typer.run(main)
