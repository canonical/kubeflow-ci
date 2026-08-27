# Update environment secrets of charm repositories

The script in this directory creates an environment in a list of charm repositories and creates/updates a secret within that environment.

## Requirements
```bash
pip install -r requirements.in
```

## Usage

### Repositories
You have to provide a plain text file with one repository per line. The default owner expected is `canonical`, but it can be overridden with the `--owner` option:
```
canonical/admission-webhook-operator
canonical/argo-operators
```

This directory also provides a sample `repositories.txt` with the repositories that use the [data-platform-workflows](https://github.com/canonical/data-platform-workflows) `release_charm_pr` and `release_charm_edge` workflows, as of 2026-08-27.

### Tokens

#### Charmhub token
Generate a Charmhub token with the proper permissions, for example:
```shell
# --ttl is specified in seconds
charmcraft login --quiet --charm kfp-operators --channel 'latest/edge/pr-*' --ttl 31536000 --permission package-manage-releases --permission package-manage-revisions --permission package-view-revisions --export /dev/stdout
```

For a token that works for all charms and channels:
```shell
charmcraft login --quiet --ttl 31536000 --permission package-manage-releases --permission package-manage-revisions --permission package-view-revisions --export /dev/stdout
```

#### GitHub token
The GitHub token is passed with `--github-token` and needs administrator access on every target repository, since creating environments and environment secrets are both admin-level operations. A classic token needs the `repo` scope; a fine-grained token needs read and write access to "Environments" and "Secrets". Note that environments on private repositories require a paid GitHub plan.

### Command
Run the command while specifying the path to the `--repositories-file`, the environment to operate on, the secret to create, the value of the secret, and the GitHub token to use for all operations.
```bash
python3 update-edge-pr-environment \
    --repositories-file <path-to-repositories-file> \
    --environment <repository-environment> \
    --secret-name <secret-inside-environment> \
    --secret-value <secret-value> \
    --github-token <github-token>
```

It is recommended to first run with `--dry-run`, which logs the changes that would be made without applying them.

## Examples
This script was created to update the environment secrets for the [data-platform-workflows](https://github.com/canonical/data-platform-workflows) actions, specifically [release_charm_pr](https://github.com/canonical/data-platform-workflows/blob/6f9c6da60190e1860d33e82da04498a56ea64725/.github/workflows/release_charm_pr.md) and [release_charm_edge](https://github.com/canonical/data-platform-workflows/blob/6f9c6da60190e1860d33e82da04498a56ea64725/.github/workflows/release_charm_edge.md).

For `release_charm_pr`, run:
```bash
python3 update-edge-pr-environment \
    --repositories-file <path-to-repositories-file> \
    --environment edge-pr \
    --secret-name CHARMHUB_TOKEN_EDGE_PR \
    --secret-value <charmhub-token> \
    --github-token <github-token>
```

For `release_charm_edge`, run:
```bash
python3 update-edge-pr-environment \
    --repositories-file <path-to-repositories-file> \
    --environment edge \
    --secret-name CHARMHUB_TOKEN_EDGE \
    --secret-value <charmhub-token> \
    --github-token <github-token>
```
