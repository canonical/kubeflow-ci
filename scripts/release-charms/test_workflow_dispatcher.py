from contextlib import nullcontext
from datetime import datetime, timedelta
from unittest import mock

import pytest

from workflow_dispatcher import TooManyRunsFoundError, NoRunsFoundError, RunTimeoutException, RunFailedException
from workflow_dispatcher import get_recent_run, wait_for_recent_workflow_run_completion, execute_workflow_and_wait


class FakeRun:
    def __init__(self, created_at, status="completed", conclusion="success"):
        self.created_at = created_at
        self.status = status
        self.conclusion = conclusion


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

WORKFLOW_RUNS = [FakeRun(created_at=t) for t in RUN_EXECUTION_TIMES]

WORKFLOW_WITH_RUNS = mock.Mock()
WORKFLOW_WITH_RUNS.get_runs.return_value = WORKFLOW_RUNS

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
    with context_raised:
        run = get_recent_run(workflow, execution_time)
        assert run == expected


def test_wait_for_recent_workflow_run_completion_successful():
    """Tests a successful case of running wait_for_recent_workflow_run_completion."""
    workflow = "some_workflow.yaml"
    execution_time = datetime.now()
    timeout = 300
    wait_between_checks = 0.1
    expected_run = RUN_SUCCESSFUL
    release_charms_side_effects = [NoRunsFoundError(''), expected_run]

    # mock get_recent_run to return a specific run after initially raising a NoRunsFoundError
    with mock.patch.object(
            release_charms, "get_recent_run", side_effect=release_charms_side_effects
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


def test_wait_for_recent_workflow_run_completion_successful():
    """Tests a successful case of running wait_for_recent_workflow_run_completion."""
    workflow = "some_workflow.yaml"
    execution_time = datetime.now()
    timeout = 2
    wait_between_checks = 0.1
    expected_run = RUN_SUCCESSFUL
    release_charms_side_effects = [NoRunsFoundError(''), expected_run]

    # mock get_recent_run to return a specific run after initially raising a NoRunsFoundError
    with mock.patch.object(
            release_charms, "get_recent_run", side_effect=release_charms_side_effects
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
    """Tests a failed execution of wait_for_recent_workflow_run_completion where no run is found.
    """
    workflow = "some_workflow.yaml"
    execution_time = datetime.now()
    timeout = 0.5
    wait_between_checks = 0.2
    release_charms_side_effects = [RunTimeoutException('')]

    # mock get_recent_run to return a specific run after initially raising a NoRunsFoundError
    with pytest.raises(RunTimeoutException) as raised_context:
        with mock.patch.object(
                release_charms, "get_recent_run", side_effect=release_charms_side_effects
        ) as mock_get_recent_run:
            wait_for_recent_workflow_run_completion(
                workflow=workflow,
                execution_time=execution_time,
                timeout=timeout,
                wait_between_checks=wait_between_checks,
            )

            mock_get_recent_run.assert_called_with(workflow=workflow, execution_time=execution_time)

    # Assert that we did not return a run with the exception
    assert raised_context.value.run is None


def test_wait_for_recent_workflow_run_completion_failed_run_not_complete():
    """Tests a failed execution where the run is not complete."""
    workflow = "some_workflow.yaml"
    execution_time = datetime.now()
    timeout = 0.5
    wait_between_checks = 0.2
    release_charms_side_effects = [RUN_INCOMPLETE]


    # mock get_recent_run to return a specific run after initially raising a NoRunsFoundError
    with pytest.raises(RunTimeoutException) as raised_context:
        with mock.patch.object(
                release_charms, "get_recent_run", side_effect=release_charms_side_effects
        ) as mock_get_recent_run:
            wait_for_recent_workflow_run_completion(
                workflow=workflow,
                execution_time=execution_time,
                timeout=timeout,
                wait_between_checks=wait_between_checks,
            )

            mock_get_recent_run.assert_called_with(workflow=workflow, execution_time=execution_time)

    # Assert that we did not return a run with the exception
    assert raised_context.value.run is RUN_INCOMPLETE


# successful run (RUN_SUCCESSFUL)
# concluded, not successful run (RUN_FAILED) -> RunFailedException
# not concluded -> Timeout
@pytest.mark.parametrize(
    "wait_for_recent_workflow_run_completion_side_effects, expected_run_returned, context_raised",
    (
        # successful run
        ([RUN_SUCCESSFUL], RUN_SUCCESSFUL, nullcontext()),
        # run concluded but not successful
        ([RUN_FAILED], None, pytest.raises(RunFailedException)),
        # run not concluded
        ([RunTimeoutException()], None, pytest.raises(RunTimeoutException)),
    )
)
def test_execute_workflow_and_wait(wait_for_recent_workflow_run_completion_side_effects, expected_run_returned, context_raised, mocker):
    repository = "some/repo"
    workflow_name = "some_workflow.yaml"
    inputs = {}

    # Mock

    # mock get_workflow_from_repository to return a specific workflow
    mock_workflow = mock.Mock()

    mock_get_workflow_from_repository = mocker.patch("release_charms.get_workflow_from_repository")
    mock_get_workflow_from_repository.return_value = mock_workflow

    mock_wait_for_recent_workflow_run_completion = mocker.patch("release_charms.wait_for_recent_workflow_run_completion")
    mock_wait_for_recent_workflow_run_completion.side_effect = wait_for_recent_workflow_run_completion_side_effects

    with context_raised:
        run = execute_workflow_and_wait(repository=repository, workflow_name=workflow_name, inputs=inputs)
        assert run == expected_run_returned

    pass


# TODO:
# * tests don't actually check that we update the run's data while waiting for completion
