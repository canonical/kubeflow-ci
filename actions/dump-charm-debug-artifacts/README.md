## Summary

Dumps logs relevant to kubernetes-based Juju charms to a GitHub Artifact.

Logs are both printed to screen and dumped to the artifact `<prefix>-juju-kubernetes-charmcraft-logs`. Prefix has the form of `<job_name>-<artifact_prefix_input>`, where `-<artifact_prefix_input>` is present only when passed as an input to the job.

Prerequisites for running this action in a workflow:
* charmcraft
* kubectl (with a kube config for the relevant cluster)
* Juju bootstrapped on the runner

Warning: This dumps a lot of details from your kubernetes cluster and juju models.
Before sending this information to anyone, you should inspect it to ensure no
sensitive information is being shared.

## Example usage

To use this as a GitHub action, do:

```yaml
- uses: canonical/kubeflow-ci/actions/dump-charm-debug-artifacts@version
  # always() if you want this to run on every run, regardless of failure. 
  # more details: https://docs.github.com/en/actions/learn-github-actions/expressions#status-check-functions
  if: always()
  with:
    artifact-prefix: {{ matrix.charm }} # optional, see note below
```

> [!IMPORTANT]
> When calling the action from multiple runs of the same job (i.e. using a matrix), it's crucial to define `artifact-prefix`. Otherwise, the action will fail trying to upload logs from different job runs to the same file.

To use this script directly, do:

```bash
bash logdump.bash
```
