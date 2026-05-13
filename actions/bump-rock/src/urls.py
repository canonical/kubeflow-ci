# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Model and helpers for GitHub `# Based on` URLs.

The supported form is:

    https://github.com/<org>/<repo>/blob/<ref>/<path>

Both `blob` and `raw` forms are accepted on input; outputs always use the
`blob` form for display (matching what humans write) and derive the raw
download URL on demand.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Iterable, List
from urllib.parse import urlparse

from .errors import UpstreamUrlError

_GITHUB_URL_RE = re.compile(
    r"^/(?P<org>[^/]+)/(?P<repo>[^/]+)/(?P<kind>blob|raw)/(?P<ref>[^/]+)/(?P<path>.+)$"
)


@dataclass(frozen=True)
class UpstreamRef:
    """A parsed reference to an upstream file in a GitHub repo at a ref."""

    org: str
    repo: str
    ref: str
    path: str

    def blob_url(self) -> str:
        """Return the human-facing GitHub blob URL."""
        return f"https://github.com/{self.org}/{self.repo}/blob/{self.ref}/{self.path}"

    def raw_url(self) -> str:
        """Return the raw.githubusercontent.com URL used for downloads."""
        return (
            f"https://raw.githubusercontent.com/"
            f"{self.org}/{self.repo}/{self.ref}/{self.path}"
        )

    def with_ref(self, new_ref: str) -> "UpstreamRef":
        """Return a copy of this ref pointing at a different git ref."""
        return replace(self, ref=new_ref)

    @property
    def basename(self) -> str:
        """The trailing filename component of `path` (e.g. `pmml.Dockerfile`)."""
        return self.path.rsplit("/", 1)[-1]


def parse(url: str) -> UpstreamRef:
    """Parse a GitHub blob/raw URL into an UpstreamRef.

    Raises:
        UpstreamUrlError: if the URL is not a github.com or
            raw.githubusercontent.com URL of the expected shape.
    """
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise UpstreamUrlError(f"unsupported scheme in URL: {url!r}")

    if parsed.netloc == "github.com":
        match = _GITHUB_URL_RE.match(parsed.path)
        if not match:
            raise UpstreamUrlError(
                f"not a recognised github.com blob/raw URL: {url!r}"
            )
        return UpstreamRef(
            org=match.group("org"),
            repo=match.group("repo"),
            ref=match.group("ref"),
            path=match.group("path"),
        )

    if parsed.netloc == "raw.githubusercontent.com":
        parts = parsed.path.lstrip("/").split("/", 3)
        if len(parts) != 4:
            raise UpstreamUrlError(
                f"not a recognised raw.githubusercontent.com URL: {url!r}"
            )
        org, repo, ref, path = parts
        return UpstreamRef(org=org, repo=repo, ref=ref, path=path)

    raise UpstreamUrlError(f"URL host not supported: {url!r}")


def parse_all(urls: Iterable[str]) -> List[UpstreamRef]:
    """Parse every URL and assert they all share the same git ref.

    A single rockcraft.yaml derived from multiple Dockerfiles is supported
    only when those Dockerfiles all live at the same upstream ref. Mixed
    refs are out of scope for v1 (spec §6.3) and must fail fast.

    Raises:
        UpstreamUrlError: if URLs reference different refs.
    """
    refs = [parse(u) for u in urls]
    if not refs:
        return refs

    distinct_refs = {r.ref for r in refs}
    if len(distinct_refs) > 1:
        raise UpstreamUrlError(
            "multiple # Based on URLs reference different upstream refs: "
            + ", ".join(sorted(distinct_refs))
        )
    return refs
