# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
"""Helper to work with Juju bundles, preserving comments in the YAML"""

import copy
from pathlib import Path
from typing import Optional

from deepdiff import DeepDiff
from ruamel.yaml import YAML


class Bundle:
    """Juju bundle loader/dumper.

    This class uses ruamel.yaml instead of the typical pyyaml in order to preserve all comments,
    the order of the yaml, etc.  This way we can load/dump a yaml with comments without losing them
    or reordering the items.
    """

    def __init__(self, filename: Optional[str] = None):
        self._filename = filename
        self._data = None
        if self._filename:
            self.load_bundle()

    def deepcopy(self):
        """Returns a new deep copy of this Bundle"""
        newbundle = copy.deepcopy(self)
        return newbundle

    def diff(self, other):
        """Returns a diff between this and another object, in DeepDiff format"""
        return DeepDiff(self._data, other._data, ignore_order=True)

    def dump(self, filename: str):
        """Dumps as yaml to a file"""
        with open(filename, "w") as fout:
            yaml = YAML(typ="rt")
            yaml.dump(self.to_dict(), fout)

    def load_bundle(self):
        """Loads a YAML file as a bundle"""
        yaml = YAML(typ="rt")
        self._data = yaml.load(Path(self._filename).read_text())

    def to_dict(self):
        """Returns bundle as a dictionary"""
        return self._data

    def __eq__(self, other):
        """Compares self to another bundle"""
        return self._filename == other._filename and self.diff(other) == {}

    @property
    def applications(self):
        """Returns the applications in the bundle"""
        return self._data["applications"]
