# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Fetch old and new upstream Dockerfiles for a (ref, target_version) pair."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests

from .errors import UpstreamFetchError
from .urls import UpstreamRef

DEFAULT_TIMEOUT = 30  # seconds


@dataclass(frozen=True)
class DockerfilePair:
    """An old/new pair of upstream Dockerfile contents for one UpstreamRef."""

    old_ref: UpstreamRef
    new_ref: UpstreamRef
    old_text: str
    new_text: str


def fetch_text(
    ref: UpstreamRef,
    session: Optional[requests.Session] = None,
    *,
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    """Download the raw file content for `ref`.

    Raises:
        UpstreamFetchError: on any non-200 response.
    """
    sess = session or requests
    resp = sess.get(ref.raw_url(), timeout=timeout, allow_redirects=True)
    if resp.status_code != 200:
        raise UpstreamFetchError(
            f"failed to fetch {ref.raw_url()}: HTTP {resp.status_code}"
        )
    return resp.text


def fetch_pair(
    old_ref: UpstreamRef,
    new_ref: UpstreamRef,
    session: Optional[requests.Session] = None,
    *,
    timeout: int = DEFAULT_TIMEOUT,
) -> DockerfilePair:
    """Fetch both the old and new Dockerfile content for an UpstreamRef pair."""
    sess = session or requests.Session()
    old_text = fetch_text(old_ref, sess, timeout=timeout)
    new_text = fetch_text(new_ref, sess, timeout=timeout)
    return DockerfilePair(
        old_ref=old_ref, new_ref=new_ref, old_text=old_text, new_text=new_text
    )


def write_pair_to_disk(pair: DockerfilePair, out_dir: Path) -> dict:
    """Write the old/new files into `out_dir` with a stable naming scheme.

    Files are named after the Dockerfile basename plus an `.old` / `.new`
    suffix so that multiple Dockerfile pairs from one rock don't collide.

    Returns:
        A mapping with keys ``old`` and ``new`` pointing at the written paths.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    base = pair.old_ref.basename
    old_path = out_dir / f"{base}.old"
    new_path = out_dir / f"{base}.new"
    old_path.write_text(pair.old_text)
    new_path.write_text(pair.new_text)
    return {"old": old_path, "new": new_path}
