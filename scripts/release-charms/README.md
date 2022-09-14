# Summary

create_release_workflow_dispatch_manifest.py and workflow_dispatcher.py are scripts that together make it easier to batch-release many charms from one channel to another:
* workflow_dispatcher.py: accepts a YAML list of Github workflow dispatches and their inputs to execute, and executes them
* create_release_workflow_dispatch_manifest.py: inspects two bundle files (say `source` and `destination`) and computes all the release workflow dispatches that are needed to release charms in channels mentioned in `source` to the channels in `destination`.  These dispatches are output in the YAML format required by workflow_dispatcher.py

# create_release_workflow_dispatch_manifest.py

## Usage

Given the two bundle files:

source.yaml:
```yaml
bundle: kubernetes
name: kubeflow-lite
applications:
  # This charm is a single-charm repo, but is not owned by us (we do not 
  # add our _github_repo_name variable) and will be skipped
  single-not-our-charm:
    charm: single-not-our-charm-charm
    channel: 1.6/edge
    scale: 1
  # This charm will create a release from 1.6/edge to 1.6/stable
  single-should-release:
    charm: single-should-release-charm
    channel: 1.6/edge
    scale: 1
    _github_repo_name: single-should-release-repo  # Eg: github.com/canonical/single-should-release-repo
  # This charm from a multi-charm repo will create a release from 1.6/edge to 1.6/stable
  multi-should-release:
    charm: multi-should-release-charm
    channel: 1.6/edge
    scale: 1
    _github_repo_name: multi-should-release-repo
    _path_in_github_repo: charms/multi-should-release-charm
  # This charm does not need a release (both source and destination use channel=1.6/stable
  multi-no-release-needed:
    charm: multi-no-release-needed-charm
    channel: 1.6/stable
    scale: 1
    _github_repo_name: notebook-operators
    _path_in_github_repo: charms/jupyter-controller
```

and `destination.yaml`:
```yaml
bundle: kubernetes
name: kubeflow-lite
applications:
  single-not-our-charm:
    charm: single-not-our-charm-charm
    channel: 1.6/stable
    scale: 1
  single-should-release:
    charm: single-should-release-charm
    channel: 1.6/stable
    scale: 1
    _github_repo_name: single-should-release-repo
  multi-should-release:
    charm: multi-should-release-charm
    channel: 1.6/stable
    scale: 1
    _github_repo_name: multi-should-release-repo
    _path_in_github_repo: charms/multi-should-release-charm
  multi-no-release-needed:
    charm: multi-no-release-needed-charm
    channel: 1.6/stable
    scale: 1
    _github_repo_name: notebook-operators
    _path_in_github_repo: charms/jupyter-controller
```

If we execute `create_release_workflow_dispatch_manifest.py source.yaml destination.yaml`, we get the output `dispatch_manifest.yaml` file:

```yaml
- inputs:
    destination-channel: 1.6/stable
    origin-channel: 1.6/edge
  repository: canonical/single-should-release-repo
  workflow_name: release.yaml
- inputs:
    charm-name: multi-should-release-charm
    destination-channel: 1.6/stable
    origin-channel: 1.6/edge
  repository: canonical/multi-should-release-repo
  workflow_name: release.yaml
```

which has two workflow dispatches, one for each charm that needs a release.

# workflow_dispatcher.py

workflow_dispatcher.py executes one or more workflow dispatches, waiting on each to complete before moving on to the next.  Inputs are specified in a YAML list of the format:

```yaml
- repository: owner/repository-name # Repo where workflow will be dispatched
  workflow_name: some-workflow.yaml # Workflow to dispatch
  inputs: # Inputs to the workflow
    input1: value1
    input2: value2
```

## Usage

Given the file `dispatch_manifest.yaml` from the previous example, we can execute the workflow dispatches with:
```bash
workflow_dispatcher.py workflow_dispatch.yaml
```

This will by default execute a dry-run of the operation, outputting:

```
INFO:__main__:Dry run: would execute workflow release.yaml in repository canonical/single-should-release-repo with inputs {'destination-channel': '1.6/stable', 'origin-channel': '1.6/edge'}
INFO:__main__:Dry run: would execute workflow release.yaml in repository canonical/multi-should-release-repo with inputs {'charm-name': 'multi-should-release-charm', 'destination-channel': '1.6/stable', 'origin-channel': '1.6/edge'}
```

where we see the actions that would be taken.  If we like these actions, we can execute again using: 
```bash
GITHUB_PAT=SOME_GITHUB_PAT python workflow_dispatcher.py dispatch_manifest.yaml --no-dry-run
```

where `SOME_GITHUB_PAT` is a Github Personal Access Token that is allowed to create workflow dispatches on the repositories in the manifest.  This will result in the tool executing each one and waiting for them to complete.  
