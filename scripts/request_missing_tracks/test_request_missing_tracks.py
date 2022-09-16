# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Test suite for request_missing_tracks"""

from unittest import mock

from juju import JujuFailedError
from request_missing_tracks import (
    Juju,
    get_charm_channel_map_for_applications,
    get_missing_tracks,
)


def test_get_charm_channel_map_for_applications():
    """Regular working test for get_charm_channel_map_for_applications"""
    # Arrange
    # Mock inputs
    applications = {
        f"app{i}": {"charm": f"someCharm{i}", "channel": f"track{i}/channel{i}"} for i in range(3)
    }

    # Mock juju_info outputs
    mock_juju_info_side_effect = [{"channel-map": i} for i in range(len(applications))]

    # Expected output
    expected_charm_channel_map = {f"someCharm{i}": i for i in range(len(applications))}

    # Act
    with mock.patch.object(Juju, "info", side_effect=mock_juju_info_side_effect) as mock_juju:
        charm_channel_map = get_charm_channel_map_for_applications(applications)

    # Assert
    assert mock_juju.call_count == len(applications)
    assert charm_channel_map == expected_charm_channel_map


def test_get_charm_channel_map_for_applications_for_non_existent_charm():
    """Test that we handle Juju raising errors, such as for non-existent charms"""
    # Arrange
    # Mock inputs
    applications = {
        f"app{i}": {"charm": f"someCharm{i}", "channel": f"track{i}/channel{i}"} for i in range(1)
    }

    # Mock juju_info outputs
    def mock_juju_info_side_effect(*args, **kwargs):
        raise JujuFailedError("", "", "")

    # Expected output
    expected_charm_channel_map = {}

    # Act
    with mock.patch.object(Juju, "info", side_effect=mock_juju_info_side_effect) as mock_juju:
        charm_channel_map = get_charm_channel_map_for_applications(applications)

    # Assert
    assert mock_juju.call_count == len(applications)
    assert charm_channel_map == expected_charm_channel_map


def test_get_missing_tracks():
    """Tests get_missing_tracks"""
    applications = {
        f"app{i}": {"charm": f"someCharm{i}", "channel": f"track{i}/channel{i}"} for i in range(3)
    }
    # charm_channel_map that has all charms and channels in the applications
    charm_channel_map = {
        application["charm"]: {f"{application['channel'].split('/')[0]}/someRandomRisk": None}
        for _, application in applications.items()
    }

    # With no missing tracks
    missing_tracks = get_missing_tracks(applications, charm_channel_map)
    assert len(missing_tracks) == 0

    # Rename a channel so we have one that is not in the charm_channel_map
    applications["app0"]["channel"] = "missingtrack/newchannel"
    missing_tracks = get_missing_tracks(applications, charm_channel_map)
    assert len(missing_tracks) == 1
    assert missing_tracks == {"someCharm0": "missingtrack"}

    # Remove a charm from the charm_channel_map, which should result in no change
    del charm_channel_map["someCharm1"]
    missing_tracks = get_missing_tracks(applications, charm_channel_map)
    assert len(missing_tracks) == 1
    assert missing_tracks == {"someCharm0": "missingtrack"}
