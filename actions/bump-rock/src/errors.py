# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Typed exceptions for the bump-rock workflow."""


class BumpRockError(Exception):
    """Base error raised by the bump-rock workflow."""


class RockcraftParseError(BumpRockError):
    """Raised when rockcraft.yaml cannot be parsed or lacks required fields."""


class UpstreamUrlError(BumpRockError):
    """Raised when a # Based on URL cannot be parsed or has inconsistent refs."""


class UpstreamFetchError(BumpRockError):
    """Raised when an upstream Dockerfile cannot be fetched."""


class UpstreamRepairError(BumpRockError):
    """Raised when a broken # Based on URL cannot be repaired."""
