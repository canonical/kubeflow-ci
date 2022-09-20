#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Test suite for workflow_dispatcher.py"""

from contextlib import nullcontext
from datetime import datetime, timedelta
from unittest import mock

import pytest
import workflow_dispatcher
from workflow_dispatcher import (
    NoRunsFoundError,
    RunFailedError,
    RunTimeoutError,
    TooManyRunsFoundError,
    execute_workflow_and_wait,
    get_recent_run,
    wait_for_recent_workflow_run_completion,
)


class FakeRun:
    """A mock workflow Run object."""

    def __init__(
        self,
        created_at,
        status="completed",
        conclusion="success",
        html_url="http://something.com/",
    ):
        self.created_at = created_at
        self.status = status
        self.conclusion = conclusion
        self.html_url = html_url

    def update(self):
        """Mock update method"""
        pass


# Run execution times, spaced out by days
RUN_EXECUTION_TIMES = [
    datetime(2021, 1, 1, 0, 0, 0),
    datetime(2021, 1, 2, 0, 0, 0),
    datetime(2021, 1, 3, 0, 0, 0),
]

TIME_BEFORE_ALL_RUNS = RUN_EXECUTION_TIMES[0] - timedelta(seconds=1)
TIME_YIELDING_LAST_RUN = RUN_EXECUTION_TIMES[-1] - timedelta(seconds=1)
TIME_AFTER_ALL_RUNS = RUN_EXECUTION_TIMES[-1] + timedelta(seconds=1)

WORKFLOW_WITHOUT_RUNS = mock.Mock()
WORKFLOW_WITHOUT_RUNS.get_runs.return_value = []
WORKFLOW_WITHOUT_RUNS.name = "workflow_without_runs"
WORKFLOW_WITHOUT_RUNS.html_url = "http://stuff.com/workflow_without_runs"

WORKFLOW_RUNS = [FakeRun(created_at=t) for t in RUN_EXECUTION_TIMES]

WORKFLOW_WITH_RUNS = mock.Mock()
WORKFLOW_WITH_RUNS.get_runs.return_value = WORKFLOW_RUNS
WORKFLOW_WITH_RUNS.name = "workflow_without_runs"
WORKFLOW_WITH_RUNS.html_url = "http://stuff.com/workflow_without_runs"

RUN_SUCCESSFUL = FakeRun(created_at=datetime.now(), status="completed", conclusion="success")
RUN_FAILED = FakeRun(created_at=datetime.now(), status="completed", conclusion="not successful")
RUN_INCOMPLETE = FakeRun(
    created_at=datetime.now(), status="not completed", conclusion="not successful"
)


@pytest.mark.parametrize(
    "workflow, execution_time, expected, context_raised",
    (
        # successful execution yielding a single run
        (WORKFLOW_WITH_RUNS, TIME_YIELDING_LAST_RUN, WORKFLOW_RUNS[-1], nullcontext()),
        # unsuccessful execution due to too many runs
        (WORKFLOW_WITH_RUNS, TIME_BEFORE_ALL_RUNS, None, pytest.raises(TooManyRunsFoundError)),
        # unsuccessful executions due to no runs found (all filtered out)
        (WORKFLOW_WITH_RUNS, TIME_AFTER_ALL_RUNS, None, pytest.raises(NoRunsFoundError)),
        # unsuccessful executions due to no runs found (no runs exist)
        (
            WORKFLOW_WITHOUT_RUNS,
            datetime(year=1, month=1, day=1),
            None,
            pytest.raises(NoRunsFoundError),
        ),
    ),
)
def test_get_recent_run(workflow, execution_time, expected, context_raised):
    """Tests get_recent_run."""
    with context_raised:
        run = get_recent_run(workflow, execution_time)
        assert run == expected


def test_wait_for_recent_workflow_run_completion_successful():
    """Tests a successful case of running wait_for_recent_workflow_run_completion."""
    workflow = WORKFLOW_WITHOUT_RUNS
    execution_time = datetime.now()
    timeout = 2
    wait_between_checks = 0.1
    expected_run = RUN_SUCCESSFUL
    release_charms_side_effects = [NoRunsFoundError(""), expected_run]

    # mock get_recent_run to return a specific run after initially raising a NoRunsFoundError
    with mock.patch.object(
        workflow_dispatcher, "get_recent_run", side_effect=release_charms_side_effects
    ) as mock_get_recent_run:
        run = wait_for_recent_workflow_run_completion(
            workflow=workflow,
            execution_time=execution_time,
            timeout=timeout,
            wait_between_checks=wait_between_checks,
        )

        assert run == expected_run
        assert mock_get_recent_run.call_count == len(release_charms_side_effects)
        mock_get_recent_run.assert_called_with(workflow=workflow, execution_time=execution_time)


def test_wait_for_recent_workflow_run_completion_failed_no_run_found():
    """Tests a failed execution where no run is found."""
    workflow = WORKFLOW_WITHOUT_RUNS
    execution_time = datetime.now()
    timeout = 0.5
    wait_between_checks = 0.2
    release_charms_side_effects = [RunTimeoutError("")]

    # mock get_recent_run to return a specific run after initially raising a NoRunsFoundError
    with pytest.raises(RunTimeoutError) as raised_context:
        with mock.patch.object(
            workflow_dispatcher, "get_recent_run", side_effect=release_charms_side_effects
        ) as mock_get_recent_run:
            wait_for_recent_workflow_run_completion(
                workflow=workflow,
                execution_time=execution_time,
                timeout=timeout,
                wait_between_checks=wait_between_checks,
            )

            mock_get_recent_run.assert_called_with(
                workflow=workflow, execution_time=execution_time
            )

    # Assert that we did not return a run with the exception
    assert raised_context.value.run is None


def test_wait_for_recent_workflow_run_completion_failed_run_not_complete():
    """Tests a failed execution where the run is not complete."""
    workflow = WORKFLOW_WITHOUT_RUNS
    execution_time = datetime.now()
    timeout = 0.5
    wait_between_checks = 0.2
    release_charms_side_effects = [RUN_INCOMPLETE]

    # mock get_recent_run to return a specific run after initially raising a NoRunsFoundError
    with pytest.raises(RunTimeoutError) as raised_context:
        with mock.patch.object(
            workflow_dispatcher, "get_recent_run", side_effect=release_charms_side_effects
        ) as mock_get_recent_run:
            wait_for_recent_workflow_run_completion(
                workflow=workflow,
                execution_time=execution_time,
                timeout=timeout,
                wait_between_checks=wait_between_checks,
            )

            mock_get_recent_run.assert_called_with(
                workflow=workflow, execution_time=execution_time
            )

    # Assert that we did not return a run with the exception
    assert raised_context.value.run is RUN_INCOMPLETE


@pytest.mark.parametrize(
    "wait_for_recent_workflow_run_completion_side_effects, expected_run_returned, context_raised",
    (
        # successful run
        ([RUN_SUCCESSFUL], RUN_SUCCESSFUL, nullcontext()),
        # run concluded but not successful
        ([RUN_FAILED], None, pytest.raises(RunFailedError)),
        # run not concluded
        ([RunTimeoutError()], None, pytest.raises(RunTimeoutError)),
    ),
)
def test_execute_workflow_and_wait(
    wait_for_recent_workflow_run_completion_side_effects,
    expected_run_returned,
    context_raised,
    mocker,
):
    """Tests execute_workflow_and_wait."""
    github_token = ""
    repository = "some/repo"
    workflow_name = "some_workflow.yaml"
    inputs = {}

    # mock get_workflow_from_repository to return a specific workflow
    mock_workflow = mock.Mock()

    mock_get_workflow_from_repository = mocker.patch(
        "workflow_dispatcher.get_workflow_from_repository"
    )
    mock_get_workflow_from_repository.return_value = mock_workflow

    mock_wait_for_recent_workflow_run_completion = mocker.patch(
        "workflow_dispatcher.wait_for_recent_workflow_run_completion"
    )
    mock_wait_for_recent_workflow_run_completion.side_effect = (
        wait_for_recent_workflow_run_completion_side_effects
    )

    with context_raised:
        run = execute_workflow_and_wait(
            github_token=github_token,
            repository=repository,
            workflow_name=workflow_name,
            inputs=inputs,
        )
        assert run == expected_run_returned

    pass


# TODO:
# * tests don't actually check that we update the run's data while waiting for completion
