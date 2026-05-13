# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Parse a rock's rockcraft.yaml.

The first non-empty comment lines at the top of a rockcraft.yaml maintained
by the Charmed Kubeflow team encode the upstream Dockerfile(s) the rock is
derived from, in the form:

    # Based on https://github.com/<org>/<repo>/blob/<ref>/<path>

This module extracts those URLs and the YAML `version:` field. It does not
attempt to round-trip the YAML; downstream stages handle rewriting.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List

import yaml

from .errors import RockcraftParseError

BASED_ON_RE = re.compile(r"#\s*Based\s+on\s+(\S+)", re.IGNORECASE)


@dataclass(frozen=True)
class RockcraftDoc:
    """Parsed view of a rock's rockcraft.yaml."""

    path: Path
    name: str
    version: str
    based_on_urls: List[str]
    raw_text: str


def load(rock_dir: Path) -> RockcraftDoc:
    """Read and parse `<rock_dir>/rockcraft.yaml`.

    Args:
        rock_dir: Path to the rock folder containing rockcraft.yaml.

    Returns:
        A RockcraftDoc with the parsed `# Based on` URLs and YAML fields.

    Raises:
        RockcraftParseError: if the file is missing, unparseable, has no
            `# Based on` comment line, or is missing required YAML fields.
    """
    yaml_path = rock_dir / "rockcraft.yaml"
    if not yaml_path.is_file():
        raise RockcraftParseError(f"rockcraft.yaml not found at {yaml_path}")

    raw_text = yaml_path.read_text()

    based_on_urls = _extract_based_on_urls(raw_text)
    if not based_on_urls:
        raise RockcraftParseError(
            f"{yaml_path}: no '# Based on <url>' comment found at top of file"
        )

    try:
        doc = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise RockcraftParseError(f"{yaml_path}: invalid YAML: {exc}") from exc

    if not isinstance(doc, dict):
        raise RockcraftParseError(f"{yaml_path}: top-level YAML must be a mapping")

    name = doc.get("name")
    version = doc.get("version")
    if not name:
        raise RockcraftParseError(f"{yaml_path}: missing required field 'name'")
    if not version:
        raise RockcraftParseError(f"{yaml_path}: missing required field 'version'")

    return RockcraftDoc(
        path=yaml_path,
        name=str(name),
        version=str(version),
        based_on_urls=based_on_urls,
        raw_text=raw_text,
    )


def _extract_based_on_urls(raw_text: str) -> List[str]:
    """Extract # Based on URLs from the leading comment block of a YAML file.

    Only the contiguous leading block of comments and blank lines is scanned;
    once the first non-comment, non-blank line is reached, scanning stops.
    This avoids picking up unrelated `# Based on` comments deeper in the file.
    """
    urls: List[str] = []
    for line in raw_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if not stripped.startswith("#"):
            break
        match = BASED_ON_RE.search(stripped)
        if match:
            urls.append(match.group(1))
    return urls
