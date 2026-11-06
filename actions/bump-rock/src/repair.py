# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Validate and repair upstream # Based on URLs.

Spec §6.4: the `# Based on` URL is human-maintained and is sometimes wrong,
stale, or pointing at a moved file. Before fetching, validate the URL and,
when broken, attempt a bounded repair: one GitHub tree listing at the ref,
look for files whose basename matches. If a unique match is found, use it.
Multiple matches are returned to the caller for further (LLM-assisted)
disambiguation in a later stage. Never trust a guessed URL without
re-validating it by HTTP fetch.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

import requests

from .errors import UpstreamRepairError
from .urls import UpstreamRef

GITHUB_API = "https://api.github.com"
DEFAULT_TIMEOUT = 30  # seconds

log = logging.getLogger("bump-rock.repair")


@dataclass
class ValidationResult:
    """Outcome of validating a single UpstreamRef."""

    ref: UpstreamRef
    ok: bool
    repaired_from: Optional[UpstreamRef] = None
    candidates: Optional[List[UpstreamRef]] = None
    error: Optional[str] = None

    @property
    def was_repaired(self) -> bool:
        return self.repaired_from is not None


def validate(
    ref: UpstreamRef,
    session: Optional[requests.Session] = None,
    *,
    timeout: int = DEFAULT_TIMEOUT,
) -> bool:
    """Return True iff the raw URL for `ref` exists (HTTP 200)."""
    sess = session or requests
    resp = sess.get(ref.raw_url(), timeout=timeout, allow_redirects=True)
    return resp.status_code == 200


def list_repo_tree(
    org: str,
    repo: str,
    ref: str,
    session: Optional[requests.Session] = None,
    *,
    timeout: int = DEFAULT_TIMEOUT,
    token: Optional[str] = None,
) -> List[str]:
    """List every file path in `org/repo` at `ref` via the GitHub API.

    Returns:
        A list of repo-relative file paths.

    Raises:
        UpstreamRepairError: if the GitHub API call fails or the response
            cannot be interpreted.
    """
    sess = session or requests
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = f"{GITHUB_API}/repos/{org}/{repo}/git/trees/{ref}?recursive=1"
    resp = sess.get(url, headers=headers, timeout=timeout)
    if resp.status_code != 200:
        raise UpstreamRepairError(
            f"GitHub tree listing failed for {org}/{repo}@{ref}: "
            f"HTTP {resp.status_code} {resp.text[:200]}"
        )
    body = resp.json()
    return [item["path"] for item in body.get("tree", []) if item.get("type") == "blob"]


def find_candidates(paths: List[str], basename: str) -> List[str]:
    """Return paths whose trailing component matches `basename` exactly."""
    return [p for p in paths if p.rsplit("/", 1)[-1] == basename]


def validate_or_repair(
    ref: UpstreamRef,
    session: Optional[requests.Session] = None,
    *,
    timeout: int = DEFAULT_TIMEOUT,
    token: Optional[str] = None,
) -> ValidationResult:
    """Validate `ref`; on 404 attempt a single bounded repair pass.

    The repair strategy is:
      1. List the repo tree at `ref.ref`.
      2. Find files whose basename equals `ref.basename`.
      3. If exactly one match exists, re-validate that candidate via HTTP
         and return it on success.
      4. If multiple candidates match, return them all unvalidated so a
         later stage (LLM-assisted disambiguation) can choose.

    Network errors during validation are surfaced as `ok=False` with an
    `error` message; they are not re-raised.
    """
    sess = session or requests.Session()

    log.info("validating upstream URL %s", ref.blob_url())
    if validate(ref, sess, timeout=timeout):
        log.info("  -> OK")
        return ValidationResult(ref=ref, ok=True)
    log.info("  -> 404, attempting bounded repair via tree listing")

    try:
        paths = list_repo_tree(
            ref.org, ref.repo, ref.ref, sess, timeout=timeout, token=token
        )
    except UpstreamRepairError as exc:
        log.warning("  -> tree listing failed: %s", exc)
        return ValidationResult(ref=ref, ok=False, error=str(exc))

    matches = find_candidates(paths, ref.basename)
    if not matches:
        return ValidationResult(
            ref=ref,
            ok=False,
            error=(
                f"no file named {ref.basename!r} found in "
                f"{ref.org}/{ref.repo}@{ref.ref}"
            ),
        )

    if len(matches) == 1:
        candidate = UpstreamRef(
            org=ref.org, repo=ref.repo, ref=ref.ref, path=matches[0]
        )
        log.info("  -> unique candidate %s, re-validating", candidate.blob_url())
        if validate(candidate, sess, timeout=timeout):
            log.info("  -> repaired")
            return ValidationResult(ref=candidate, ok=True, repaired_from=ref)
        return ValidationResult(
            ref=ref,
            ok=False,
            error=(
                f"single candidate {candidate.blob_url()} found in tree but "
                "did not pass HTTP re-validation"
            ),
        )

    candidate_refs = [
        UpstreamRef(org=ref.org, repo=ref.repo, ref=ref.ref, path=p) for p in matches
    ]
    return ValidationResult(
        ref=ref,
        ok=False,
        candidates=candidate_refs,
        error=(
            f"multiple files named {ref.basename!r} in tree: "
            + ", ".join(p for p in matches)
        ),
    )
