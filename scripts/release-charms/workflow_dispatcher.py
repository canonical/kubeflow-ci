#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Executes and waits on one or more workflows defined by a YAML workflow_manifest file"""

import logging
import os
from datetime import datetime, timedelta
from time import sleep
from typing import Union

import github
import typer
import yaml
from github import Github, Repository, Workflow, WorkflowRun  # noqa: F401  # Workflow is used

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_workflow_from_repository(
    github_token: str,
    repository: Union[str, github.Repository.Repository],
    workflow_name="release.yaml",
) -> github.Workflow.Workflow:
    """Returns a workflow object from a repository.

    Note that this authenticates by

    Args:
        github_token: The github token to use for authentication.  Must have permission to
                      trigger workflow dispatches on this repository
        repository: The repository in which to execute the workflow, in the format "owner/repo" or
                    a github.Repository object.
        workflow_name: The name of the workflow to execute, typically the filename of the workflow

    Returns:
        A github.Workflow object
    """
    g = Github(login_or_token=github_token)
    if not isinstance(repository, Repository.Repository):
        repository = g.get_repo(repository)

    return repository.get_workflow(workflow_name)


def execute_workflow_and_wait(
    github_token: str,
    repository: Union[str, github.Repository.Repository],
    workflow_name="release.yaml",
    inputs: dict = None,
):
    """Executes a workflow and waits for it to complete.

    Args:
        github_token: The github token to use for authentication.  Must have permission to trigger
                      workflow dispatches on this repository.
        repository: The repository in which to execute the workflow, in the format "owner/repo" or
                    a github.Repository object.
        workflow_name: The name of the workflow to execute, typically the filename of the workflow
        inputs: A dictionary of inputs to pass to the workflow
    """
    # Name of the file in .github/workflows/ that we will execute.  This can also be the ID of the
    # workflow, but I don't know how to get that apart from first getting the name.
    workflow = get_workflow_from_repository(github_token, repository, workflow_name)

    ref = "main"
    # Get a timestamp immediately before we execute the workflow, in UTC, for filtering out past
    # runs
    execution_time = datetime.utcnow()
    result = workflow.create_dispatch(ref=ref, inputs=inputs)

    # TODO: multi-charm is using the single-charm repo workflow.  Update it!

    if not result:
        raise RunFailedError(
            "Workflow dispatch failed.  This could be due to an incorrect input or workflow name, "
            "or some other error.  By default, PyGithub package used to create the dispatch does "
            "not provide any information about the failure, but you can enable their debug logging"
            " by running with the flag --github_debug_logging."
        )
    logging.info(result)
    run = wait_for_recent_workflow_run_completion(workflow=workflow, execution_time=execution_time)

    if run.conclusion != "success":
        raise RunFailedError(
            f"Workflow {workflow_name} failed with conclusion {run.conclusion}", run=run
        )
    else:
        return run


class NoRunsFoundError(Exception):
    """Raised if no runs are found for a workflow."""

    pass


class TooManyRunsFoundError(Exception):
    """Raised if too many runs are found for a workflow.

    This exception can optionally include a list of github.WorkflowRun objects.
    """

    def __init__(self, *args, runs=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.runs = runs


class RunFailedError(Exception):
    """Raised if the tracked run has failed.

    This exception can optionally include a github.WorkflowRun object.
    """

    def __init__(self, *args, run: WorkflowRun.WorkflowRun, **kwargs):
        super().__init__(*args, **kwargs)
        self.run = run


class RunTimeoutError(Exception):
    """Raised if the tracked run times out.

    This exception can optionally include a github.WorkflowRun object.
    """

    def __init__(self, *args, run: github.WorkflowRun = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.run = run


def get_recent_run(
    workflow: github.Workflow, execution_time: datetime
) -> github.WorkflowRun.WorkflowRun:
    """Returns the run that was executed after execution_time.

    Raises if:
    * NoRunsFoundError: There were no runs found since execution time
    * TooManyRunsFoundError: there has been more than one run since execution_time.
    """
    runs = list(filter(lambda run: run.created_at > execution_time, workflow.get_runs()))
    if len(runs) == 0:
        raise NoRunsFoundError("No runs found since execution time.")
    elif len(runs) > 1:
        raise TooManyRunsFoundError("Found more than one run since execution_time.", runs=runs)
    else:
        return runs[0]


def wait_for_recent_workflow_run_completion(
    workflow: github.Workflow,
    execution_time: datetime,
    timeout: Union[int, float] = 60,
    wait_between_checks: Union[int, float] = 1,
) -> github.WorkflowRun:
    """Waits for a recent workflow run to complete

    This finds the most recent workflow run, waits for it to complete, and returns it.  This is
    intended to be executed immediately after you have triggered a workflow run so that you can
    track its progress.  This is a hack to workaround how the Github API does not return the
    Run ID when you execute a workflow, making it difficult to execute and then track a run.

    Args:
        workflow: The workflow from which we want to wait the most recent run
        execution_time: Timestamp immediately before the workflow run was started, in UTC.  This is
                        used to filter out past runs.
        timeout: The maximum amount of time to wait for the workflow to complete, in seconds
        wait_between_checks: The amount of time to wait between checks for the workflow to complete

    Exceptions:
        RunTimeoutException: Raised if the workflow run is not found during the allowed timeout, or
                             if it is found but not completed.  If the workflow run is found, it
                             will be included in the `exception.run` attribute.

    Returns:
        The workflow run that was executed after execution_time.
    """
    reference_time = datetime.now()
    timeout = timedelta(seconds=timeout)

    def elapsed_time():
        """Returns the elapsed time since reference_time"""
        return datetime.now() - reference_time

    run = None
    logger.info(f"Looking for run of workflow '{workflow.name}' at url {workflow.url}")
    while elapsed_time() < timeout:
        # If we haven't found the run yet, look for it.  Else, keep using the same one
        if run is None:
            try:
                run = get_recent_run(workflow=workflow, execution_time=execution_time)
                logger.info(f"Found workflow run with url: {run.html_url}")
            except NoRunsFoundError:
                logger.info(
                    f"No runs found yet.  Sleeping {wait_between_checks} seconds and retrying."
                )
                sleep(wait_between_checks)
                continue
            except TooManyRunsFoundError as err:
                logger.error(
                    f"Found more than one run since execution_time {execution_time}: got runs {err.runs}"
                )
        else:
            logger.info("Updating workflow run's data")
            run.update()

        # Return run if complete
        logger.info(f"Checking run status for completion.  Current status is {run.status}")
        if run.status == "completed":
            return run

        sleep(wait_between_checks)

    if run is None:
        msg = "Timed out without finding a recent run for workflow"
        logger.error(msg)
        raise RunTimeoutError(msg)
    else:
        msg = "Timed out waiting for workflow to complete"
        logger.error(msg)
        raise RunTimeoutError(msg, run=run)


def get_github_token(dry_run: bool, github_pat_environment_variable: str = "GITHUB_PAT"):
    """Returns the Github token to use for authentication."""
    if dry_run:
        github_token = None
    else:
        github_token = os.environ.get(github_pat_environment_variable, None)
        if not github_token:
            raise ValueError(
                f"Environment variable {github_pat_environment_variable} is not set.  "
                f"This must be set to a Github Personal Access Token that can trigger"
                f"workflow dispatches."
            )
    return github_token


def main(
    dispatch_manifest: str = typer.Argument(
        ...,
        help="Path to the dispatch manifest YAML file.  This file is is a list of workflow "
        "dispatch executions, each of which is a dictionary with the keys ['repository', 'workflow_name', and "
        "'inputs'].  The 'inputs' key contains a dictionary of the inputs needed for the workflow dispatch",
    ),
    dry_run: bool = typer.Option(
        default=True,
        help="If true, do not actually execute the workflow.  This is useful for seeing what "
        "will happen before actually doing something irreversible",
    ),
    github_debug_logging: bool = typer.Option(
        default=False,
        help="If true, enable debug logging for the PyGithub package.  This is useful for "
        "debugging failures, but is very verbose and not recommended for normal use.",
    ),
    github_pat_environment_variable: str = typer.Option(
        default="GITHUB_PAT",
        help="The name of the environment variable that contains the Github Personal Access"
        "Token to use for authentication.  This token required for all execution except"
        "dry runs.",
    ),
):
    r"""Triggers one or more Github workflow dispatch runs

    This script triggers one or more Github repository workflow dispatches, as defined in a YAML
    dispatch_manifest file.  The execution uses the Github token found in the environment variable
    named by the github_pat_environment_variable argument.

    The dispatch_manifest is a YAML list of dictionaries, like
    (you can ignore the extra newlines... without them, the help text outputs even worse :/ ):

        - repository: "some-owner/some-repo"\n
          workflow_name: "some_workflow_file.yaml"\n
          inputs:\n
            workflow-input-1: "abc"\n
            workflow-input-2: "xyz"\n
        - repository: "some-other-other/some-other-repo"\n
          workflow_name: "some_other_workflow_file.yaml"\n
          inputs:\n
            another-input: "123"\n

    Each dispatch is executed in series and waited on until it completes.
    """
    if github_debug_logging:
        github.enable_console_debug_logging()

    github_token = get_github_token(
        dry_run=dry_run, github_pat_environment_variable=github_pat_environment_variable
    )

    with open(dispatch_manifest) as f:
        workflows_to_execute = yaml.safe_load(f)

    for workflow in workflows_to_execute:
        if dry_run:
            logger.info(
                f"Dry run: would execute workflow {workflow['workflow_name']} in repository {workflow['repository']} with inputs {workflow['inputs']}"
            )
        else:
            try:
                execute_workflow_and_wait(
                    github_token=github_token,
                    repository=workflow["repository"],
                    workflow_name=workflow["workflow_name"],
                    inputs=workflow["inputs"],
                )
            except RunTimeoutError as e:
                logger.info(
                    f"Workflow run for {workflow['workflow_name']} in repository {workflow['repository']} timed out with message: {e.message}"
                )


if __name__ == "__main__":
    typer.run(main)
