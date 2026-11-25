# Create Actions policies in charm repositories

The script in this directory creates a [GitHub Actions policy](https://docs.github.com/en/actions/concepts/about-actions-policies) in a list of charm repositories, or overwrites the policy with the same name if it already exists. It uses the [REST API endpoints for GitHub Actions policies](https://docs.github.com/en/rest/actions/policies).

## Requirements
```bash
pip install -r requirements.in
```

## Usage

### Repositories
You have to provide the target repositories in one of two ways, but not both:

* `--repositories-file`: a plain text file with one repository per line.
* `--repository`: a single repository, which can be repeated to target multiple repositories.

The default owner expected is `canonical`, but it can be overridden with the `--owner` option. Repositories that are given as `owner/name` are used as is:
```
admission-webhook-operator
canonical/argo-operators
```

This directory also provides a sample `repositories.txt` with the non-archived repositories of the [`mlops` team](https://github.com/orgs/canonical/teams/mlops) that have a `.github/workflows/on_pull_request_closed.yaml` workflow, as of 2026-11-25.

### Policy
You have to provide a JSON file with the policy, in the format expected by the [Create a repository Actions policy](https://docs.github.com/en/rest/actions/policies#create-a-repository-actions-policy) endpoint. The `name` of the policy is used to find an existing policy in each repository; if one is found, it is overwritten, otherwise a new one is created.

This directory provides `allow-pull-request-target.json`, which allows the `pull_request_target` event for `.github/workflows/on_pull_request_closed.yaml`. Since GitHub's [default policy for `pull_request_target`](https://docs.github.com/en/actions/reference/security/securely-using-pull_request_target#default-policy-for-pull_request_target) will block that event in public repositories from December 2, 2026, this policy is needed for the backport workflow to keep working.

Note that `allowed_events` is an allowlist: any event that is not listed is blocked for the workflows targeted by the policy.

### GitHub token
The GitHub token is passed with `--github-token` and needs administrator access on every target repository, since managing Actions policies is an admin-level operation.

### Command
Run the command while specifying the repositories (with either `--repositories-file` or `--repository`), the `--policy-file`, and the GitHub token to use for all operations.
```bash
python3 create-action-policy.py \
    --repositories-file <path-to-repositories-file> \
    --policy-file <path-to-policy-file> \
    --github-token <github-token>
```

Or, for specific repositories:
```bash
python3 create-action-policy.py \
    --repository <repository> \
    --repository <another-repository> \
    --policy-file <path-to-policy-file> \
    --github-token <github-token>
```

It is recommended to first run with `--dry-run`, which logs the changes that would be made without applying them. The dry run still reads the existing policies of each repository, to report whether a policy would be created or updated.

## Examples
To allow `pull_request_target` for the `on_pull_request_closed.yaml` workflow, run:
```bash
python3 create-action-policy.py \
    --repositories-file repositories.txt \
    --policy-file allow-pull-request-target.json \
    --github-token <github-token>
```

To do the same only for `kserve-operators` and `kfp-operators`, run:
```bash
python3 create-action-policy.py \
    --repository kserve-operators \
    --repository kfp-operators \
    --policy-file allow-pull-request-target.json \
    --github-token <github-token>
```
