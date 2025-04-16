# Promote bundle charms to a different risk

> [!IMPORTANT]
> Scripts in this folder achieve the same goal as the ones in the [release-charms](./../release-charms/) directory. The `release-charms` ones seem a bit more appropriate as they use the repositories' promote workflow instead of running the promote commands themselves, which allows the team to monitor and keep a history of what happened. However, at the time of writing (April 2025), they are not functional. Due to time constraints, it was faster to create new ones than fix those. For a future effort, we should evaluate which ones are better for the job.


The scripts in this directory are used for mass promoting the charms of a bundle between channels. This is achieved using `charmcraft promote`:
```bash
charmcraft promote
    --name <charm-name>
    --from-channel <source-channel>
    --to-channel <destination-channel>
    --yes
```

## Usage
In order to promote charms from a bundle's channels to those of another, run the `promote-charms.py` script, passing as inputs the source bundle file and the destination bundle file:
```bash
python3 promote-charms.py <path-to-source-bundle.yaml-file> <path-to-destination-bundle.yaml-file>
```

It is recommended to first run a **dry run** to verify the expected results, using the `--dry-run` option.

For example:
```bash
python3 generate-promote-manifest.py ~/canonical/bundle-kubeflow/releases/1.10/candidate/bundle.yaml ~/canonical/bundle-kubeflow/releases/1.10/stable/bundle.yaml --dry-run
```

For proceeding with the actual promotion, remove the `--dry-run` and rerun.

> [!NOTE]
> The script does not promote charms that have a `_github_dependency_repo_name`,since those are not maintained by the Kubeflow team.

> [!NOTE]
> Ensure that you are logged in by running `charmcraft whoami`. If not, use `charmcraft login`.

