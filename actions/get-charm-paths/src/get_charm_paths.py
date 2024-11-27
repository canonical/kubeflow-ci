#!/bin/env python
import argparse
import os
from pathlib import Path

OUTPUT_VARIABLE_NAME = "charm_paths"


def find_charms_in_dir(base_dir: str = "./", charms_subdir="charms"):
    """
    Finds paths to charm directories in base_dir.

    Directories are identified as charm directories by the presence of a
    "metadata.yaml", "metadata.yml" or "charmcraft.yaml" file.

    Returns:
    * If any subdirectories of base_dir/charms_subdir/ are charm directories,
      then the list of these directories is returned.
    * If not, then if the base directory itself is a charm directory, that is
      returned.
    * Otherwise, returns []

        Directories returned are alphabetically sorted.
    """
    root_dir = Path(base_dir)
    charms_dir = root_dir / charms_subdir

    metadata_files = (
        list(charms_dir.glob("*/metadata.yaml"))
        + list(charms_dir.glob("*/metadata.yml"))
        + list(charms_dir.glob("*/charmcraft.yaml"))
    )

    if not metadata_files:
        # No nested charm directories found, check if the top level dir is
        # a charm
        metadata_files = (
            list(root_dir.glob("metadata.yaml"))
            + list(root_dir.glob("metadata.yml"))
            + list(root_dir.glob("charmcraft.yaml"))
        )

    # Return the parent directory of the relevant metadata_files and
    # remove duplicates
    parent_dirs = [metadata_file.parent for metadata_file in metadata_files]
    charm_dirs = sorted(list(set(parent_dirs)))

    return charm_dirs


def stringify_paths(paths):
    """
    Converts list of Paths to list of strings,
    appending a trailing slash just in case.
    """
    return [str(path) + "/" for path in paths]


def set_github_output(name, value):
    os.system(f'echo "{name}={value}" >> $GITHUB_OUTPUT')


def emit_to_github_action(name, data):
    """
    Emits data to STDOUT as an output named name in a format that GitHub
    Actions consumes
    """
    data = str(data)
    print(f"Found {name}: {data}")
    set_github_output(name, data)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Find charm directories. Searches for either nested "
        "charms  or whether the directory is itself a charm, printing a "
        "Github Action compatible output of a JSON list of the found charm "
        "directories"
    )

    parser.add_argument("base_dir", help="Directory to search for charms")
    parser.add_argument(
        "--charms-subdir", default="charms", help="Subdirectory to search for charms"
    )
    args = parser.parse_args()
    charm_dirs = find_charms_in_dir(args.base_dir, args.charms_subdir)
    charm_dirs = stringify_paths(charm_dirs)
    emit_to_github_action(name=OUTPUT_VARIABLE_NAME, data=charm_dirs)
