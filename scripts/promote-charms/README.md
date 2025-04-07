# Promote bundle charms to a different risk

> [!IMPORTANT]
> Scripts in this folder achieve the same things as the ones in the [release-charms](./../release-charms/) directory. The `release-charms` ones seem a bit more appropriate as they use the repositories' promote workflow instead of running the promote commands themselves, which allows the team to monitor and keep a history of what happened. However, at the time of writing (April 2025), they are not functional. Due to time constraints, it was faster to create new ones than fix those. For a future effort, we should evaluate which ones are better for the job.


The scripts in this directory are used for mass promoting the charms of a bundle between channels. This is achieved using the `charmcraft promote`:
```bash
charmcraft promote
    --name <charm-name>
    --from-channel <source-channel>
    --to-channel <destination-channel>
    --yes
```

## Step 1: Generate promote-manifest.yaml

In order to run the `promote.py` script, generate first the `promote-manifest.yaml` file. This is done using the `generate-promote-manifest.py` file and passing as inputs the source bundle file and the destination bundle file:
```bash
python3 generate-promote-manifest.py <path-to-source-bundle.yaml-file> <path-to-destination-bundle.yaml-file>
```
For example:
```bash
python3 generate-promote-manifest.py ~/canonical/bundle-kubeflow/releases/1.10/candidate/bundle.yaml ~/canonical/bundle-kubeflow/releases/1.10/stable/bundle.yaml
```

This creates a `promote-manifest.yaml` file in the form of:
```
applications:
  admission-webhook:
    charm: admission-webhook
    destination-channel: 1.10/stable
    source-channel: 1.10/candidate
  argo-controller:
    charm: argo-controller
    destination-channel: 3.4/stable
    source-channel: 3.4/candidate
[...]
```
> [!NOTE]
> The produced manifest does not include charms that have a `_github_dependency_repo_name`,since those are not maintained by Kubeflow team.

## Step 2: Run the promote.py script
First, ensure that you have logged in by running `charmcraft whoami`. If you 're not logged, run `charmcraft login`.
Using the previous `promote-manifest.yaml`, run the following command. There is also the `--dry-run` option which can be used in order to verify first that the promotions to-be-done are the expected ones. 
```bash
python3 promote.py ./promote-manifest.yaml
```
